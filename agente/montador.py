"""Monta o boletim final:
  • boletim_atual.json — exatamente as chaves que o index.html lê (+ extras
    opcionais: audio_script, ndf_parameters, data_quality, trusted_sources);
  • relatorio_atual.md — as 8 seções da metodologia (versão para ouvir,
    panorama, análise por complexo, WTD, MTD, projeções, pílula, payload) +
    qualidade dos dados.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader

from .calendario import DIAS_SEMANA, inicio_da_semana
from .numeros import fmt, fmt_pct, fmt_valor
from .projecoes import linha_painel

ICONE_STATUS = {"ok": "", "alerta": "⚠️ ", "desatualizado": "🕒 ", "indisponivel": "⛔ "}
NOME_TURNO = {"abertura": "Abertura", "meio_dia": "Meio do Dia", "fechamento": "Fechamento",
              "fim_de_semana": "Balanço de Fim de Semana"}
_RE_REF = re.compile(r"\s?\[(N\d+)\]")
_RE_ROTULO = re.compile(r"linha '([^']+)'|vencimento (\S+)")


def citar(texto: str, noticias: dict, modo: str = "html") -> str:
    """Troca [N3] pelo link da notícia (html/md) ou remove (texto)."""
    if not texto:
        return ""
    if modo == "html":
        texto = html.escape(texto, quote=False)

    def troca(m):
        n = noticias.get(m.group(1))
        if not n or modo == "texto":
            return ""
        if modo == "html":
            return (f' <a href="{n.url}" target="_blank" rel="noopener noreferrer">'
                    f'[{html.escape(n.fonte, quote=False)}]</a>')
        return f" [[{n.fonte}]]({n.url})"
    return _RE_REF.sub(troca, texto).strip()


def rotulo(m) -> str:
    r = _RE_ROTULO.search(m.detalhe or "")
    return (r.group(1) or r.group(2)) if r else ""


def texto_indicador(m) -> str:
    if not m.disponivel:
        return "⛔ Indisponível — nenhuma fonte retornou cotação válida"
    partes = []
    if m.var_dia_pct is not None:
        partes.append(f"{fmt_pct(m.var_dia_pct)} no dia")
    if m.var_semana_pct is not None:
        partes.append(f"{fmt_pct(m.var_semana_pct)} na semana")
    rot = rotulo(m)
    s = (ICONE_STATUS.get(m.status, "") + fmt_valor(m.valor, m.unidade, m.casas)
         + (f" [{rot}]" if rot and not re.search(r"\d{2}/\d{2}", rot) else "")
         + (f" ({' · '.join(partes)})" if partes else "")
         + f" — {m.fonte}, {m.data:%d/%m}")
    if m.status != "ok" and m.mensagens:
        s += f" · {m.mensagens[-1]}"
    return html.escape(s, quote=False)


def link_seguro(url: str) -> str:
    """Codifica aspas, espaços e sinais que poderiam quebrar o atributo href do painel."""
    return quote(url or "", safe=":/?&=%#@+,;~-._!*()[]$")


def _r(v, casas):
    return None if v is None else round(float(v), casas)


class Montador:
    def __init__(self, cfg):
        self.cfg = cfg
        self.env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "modelos")),
                               autoescape=False, trim_blocks=True, lstrip_blocks=True)
        self.env.filters["cel"] = lambda t: " ".join(str(t or "").split()).replace("|", "·")
        self.env.filters["data_br"] = lambda t: "/".join(reversed(str(t).split("-"))) if t else "—"

    # ------------------------------------------------------------------ JSON
    def montar(self, *, agora, turno, metricas: dict, spreads: list, blocos_txt: dict, fech: dict,
               noticias_bloco: dict, bandas: dict, registro, ndf: dict | None, eixo: list,
               qualidade: dict, fontes_status: list, saca_usd: float | None) -> dict:
        cfg, hoje = self.cfg, agora.date()
        bc = cfg.blocos_cfg
        todas = {n.id: n for lista in noticias_bloco.values() for n in lista}
        nome_turno = NOME_TURNO.get(turno, turno)

        # metadata + resumo executivo
        boletim: dict = {
            "metadata": {
                "target_regions": cfg.geral["relatorio"]["pracas"],
                "scope": html.escape(fech["escopo"], quote=False),
                "timestamp": f"{agora:%d/%m/%Y %H:%M} BRT — {nome_turno} de {DIAS_SEMANA[agora.weekday()]}",
                "analyst": cfg.geral["relatorio"]["analista"],
            },
            "executive_summary": {b["chave_resumo"]: citar(blocos_txt[b["id"]]["resumo_curto"], todas)
                                  for b in cfg.blocos},
        }

        # cotações do dia por complexo
        mi: dict = {b["id"]: {} for b in cfg.blocos}
        for m in metricas.values():
            mi.setdefault(m.bloco, {})[m.id] = texto_indicador(m)
        for s in spreads:
            if s.valor is not None:
                mi.setdefault(s.bloco, {})[s.id] = html.escape(
                    f"{ICONE_STATUS.get(s.status, '')}{fmt_valor(s.valor, s.unidade, s.casas)} — {s.composicao}", quote=False)
        if ndf:
            mi["cambio_e_energia"][f"ndf_teorico_{ndf['dc']}d"] = html.escape(
                f"R$ {fmt(ndf['ndf'], 4)} (spot R$ {fmt(ndf['spot'], 4)} · juros R$ {fmt(ndf['taxa_brl_aa'], 2)}% a.a. · "
                f"cupom {fmt(ndf['cupom_aa'], 2)}% a.a. · {ndf['du']} d.u.)", quote=False)
        boletim["market_indicators"] = mi

        # análise por complexo
        blocos_json = []
        for b in cfg.blocos:
            t = blocos_txt[b["id"]]
            lista = noticias_bloco.get(b["id"], [])
            fontes_ind = [m for m in metricas.values() if m.bloco == b["id"] and m.disponivel and m.url][:2]
            elos = []
            for e in t["elos"]:
                links = [{"label": html.escape(f"{todas[r].titulo} — {todas[r].fonte}", quote=False), "url": todas[r].url}
                         for r in e.get("referencias", []) if r in todas]
                for m in fontes_ind:
                    if len(links) < 3:
                        links.append({"label": html.escape(f"Cotação verificada: {m.nome_curto} — {m.fonte} ({m.data:%d/%m})",
                                                           quote=False), "url": link_seguro(m.url)})
                elos.append({"elo": e["elo"], "direction": citar(e["direcionamento"], todas), "reference_links": links})
            blocos_json.append({
                "title": html.escape(f"{b['titulo']} — {t['manchete']}", quote=False),
                "market_bias": citar(t["vies"], todas),
                "executive_summary": citar(t["resumo_executivo"], todas),
                "news_sources": [{"headline": html.escape(
                    f"{n.titulo} — {n.fonte} ({n.publicado_em[8:10]}/{n.publicado_em[5:7]} {n.publicado_em[11:16]})",
                    quote=False), "url": n.url} for n in lista],
                "strategic_directions_by_elo": elos,
            })
        boletim["detailed_blocks_and_news"] = blocos_json

        # evolução semanal
        ini_sem = inicio_da_semana(hoje)
        sabado = ini_sem + timedelta(days=6)
        fim_sem = min(hoje, sabado)
        semanal = []
        drivers = {k: v for b in cfg.blocos for k, v in blocos_txt[b["id"]]["drivers_semana"].items()}
        for i in bc.get("painel_semanal", []):
            m = metricas.get(i)
            if not m or not m.disponivel or m.var_semana_pct is None:
                continue
            semanal.append({"asset": m.nome_curto, "unit": m.unidade, "sunday_open_ref": _r(m.ref_semana, m.casas),
                            "current_value": _r(m.valor, m.casas), "weekly_change_pct": _r(m.var_semana_pct, 2),
                            "weekly_driver": citar(drivers.get(i, ""), todas)})
        if hoje > sabado or hoje.weekday() == 5:
            periodo = f"Semana encerrada (domingo {ini_sem:%d/%m} a sábado {sabado:%d/%m})"
        else:
            periodo = f"Semana corrente (WTD — domingo {ini_sem:%d/%m} a {DIAS_SEMANA[hoje.weekday()].lower()} {hoje:%d/%m})"
        boletim["weekly_evolution_wtd"] = {"period_start": f"{ini_sem:%d/%m/%Y}", "period_end": f"{fim_sem:%d/%m/%Y}",
                                           "period_current": periodo, "assets": semanal}

        # evolução mensal (janela de pregões)
        narr = {k: v for b in cfg.blocos for k, v in blocos_txt[b["id"]]["narrativas_mes"].items()}
        mensal = []
        meio = len(eixo) // 2
        for i in bc.get("painel_mensal", []):
            m = metricas.get(i)
            if not m or not m.disponivel:
                continue
            texto_mes = narr.get(i) or (
                "Histórico em formação: ainda não há cotação verificada antes do início do mês para calcular o acumulado."
                if m.var_mes_pct is None else
                f"No mês: {fmt_pct(m.var_mes_pct)} desde {m.data_ref_mes:%d/%m} ({fmt_valor(m.ref_mes, m.unidade, m.casas)}).")
            mensal.append({"asset": m.nome_curto, "unit": m.unidade, "month_open_value": _r(m.ref_mes, m.casas),
                           "mid_month_10_oct": m.janela[meio] if m.janela else None,
                           "current_value": _r(m.valor, m.casas), "mtd_change_pct": _r(m.var_mes_pct, 2),
                           "monthly_narrative": citar(texto_mes, todas), "daily_history": m.janela})
        boletim["monthly_evolution_mtd"] = {"month_start": hoje.replace(day=1).isoformat(), "current_date": hoje.isoformat(),
                                            "days_elapsed": len(eixo), "daily_dates": [f"{d:%d/%m}" for d in eixo],
                                            "assets": mensal}

        # projeções auditáveis
        gat = {k: v for b in cfg.blocos for k, v in blocos_txt[b["id"]]["gatilhos"].items()}
        boletim["audit_panel_projections"] = [
            {k: (html.escape(v, quote=False) if isinstance(v, str) else
                 {kk: html.escape(vv, quote=False) for kk, vv in v.items()})
             for k, v in linha_painel(metricas[i], bandas.get(i), registro, citar(gat.get(i, ""), todas, "texto")).items()}
            for i in bc.get("projecoes", []) if i in metricas]

        # pílula
        p = fech["pilula"]
        boletim["market_intelligence_pill"] = {
            "title": html.escape(p["titulo"], quote=False),
            "formula": html.escape(ndf["formula"], quote=False) if ndf else "—",
            "analysis": citar(p["analise"], todas),
            "strategic_takeaway": citar(p["conclusao"], todas),
        }

        # extras (o index.html atualizado usa; versões antigas ignoram)
        boletim["audio_script"] = citar(fech["roteiro_audio"], todas, "texto")
        if ndf:
            boletim["ndf_parameters"] = {"spot": _r(ndf["spot"], 4), "di_aa": _r(ndf["taxa_brl_aa"], 2),
                                         "cupom_aa": _r(ndf["cupom_aa"], 2), "du": ndf["du"], "dc": ndf["dc"],
                                         "ndf": _r(ndf["ndf"], 4), "saca_usd": _r(saca_usd, 2)}
        boletim["data_quality"] = qualidade
        boletim["labels"] = {**{m.id: m.nome_curto for m in metricas.values()}, **{s.id: s.nome for s in spreads},
                             **({f"ndf_teorico_{ndf['dc']}d": f"NDF teórico {ndf['dc']} dias"} if ndf else {})}
        boletim["trusted_sources"] = {
            "repo": os.environ.get("GITHUB_REPOSITORY", cfg.geral.get("repositorio", "")),
            "arquivo": "config/fontes.yaml",
            "gerado_em": agora.isoformat(timespec="minutes"),
            "regioes": fontes_status,
        }
        return boletim

    # -------------------------------------------------------------- Markdown
    def markdown(self, boletim: dict, *, agora, turno, metricas: dict, blocos_txt: dict, fech: dict,
                 noticias_bloco: dict, spreads: list, caminho_json: str) -> str:
        todas = {n.id: n for lista in noticias_bloco.values() for n in lista}
        tpl = self.env.get_template("relatorio.md.j2")
        return tpl.render(
            b=boletim, agora=agora, turno=NOME_TURNO.get(turno, turno), dia=DIAS_SEMANA[agora.weekday()],
            cfg=self.cfg, metricas=metricas, blocos=self.cfg.blocos, txt=blocos_txt, fech=fech,
            noticias=noticias_bloco, spreads=spreads, caminho_json=caminho_json,
            md=lambda t: citar(t, todas, "md"), fmt=fmt, fmt_pct=fmt_pct, fmt_valor=fmt_valor,
            por_nome={m.nome_curto: m for m in metricas.values()},
            icone=ICONE_STATUS, rotulo=rotulo,
            q=boletim["data_quality"], aviso=self.cfg.geral["relatorio"].get("aviso_legal", ""))


def salvar_json(boletim: dict, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(boletim, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(caminho)
