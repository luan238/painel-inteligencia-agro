"""Agro Intel Agent — linha de comando.

  python -m agente executar         gera o boletim (coleta → confere → analisa → escreve → publica)
  python -m agente checar-fontes    testa todas as fontes e gera relatorios/checagem_fontes.md
  python -m agente adicionar-fonte --nome "X" --url https://... --regiao Brasil
  python -m agente validar-config   confere a consistência dos arquivos de config/
  python -m agente testar-ia        manda um pedido curtinho a cada API gratuita da fila (confere as chaves)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import jsonschema
import yaml

from . import __version__
from .analise import calcular_metricas, calcular_ndf, calcular_spreads, eixo_janela
from .coletores import coletar_indicador
from .coletores.noticias import TIPOS_COM_NOTICIAS, ColetorNoticias, selecionar, url_segura
from .config import Config, carregar_config
from .historico import Historico
from .llm import ClienteLLM
from .montador import NOME_TURNO, Montador, link_seguro, salvar_json
from .numeros import fmt_valor
from .projecoes import RegistroProjecoes, calcular_bandas
from .rede import Cliente
from .redator import Redator
from .validacao import validar

ESQUEMA = Path(__file__).parent / "esquema_boletim.json"
CHAVES_FECHAMENTO = ["dolar_ptax", "selic_meta", "petroleo_wti", "soja_paranagua", "soja_cbot", "milho_campinas",
                     "trigo_parana", "algodao_ice", "cafe_arabica_cepea", "cafe_manhuacu", "boi_gordo_cepea"]


def turno_de(agora: datetime) -> str:
    if agora.weekday() >= 5:
        return "fim_de_semana"
    if agora.hour < 11:
        return "abertura"
    if agora.hour < 16:
        return "meio_dia"
    return "fechamento"


def _ler_json(caminho: Path) -> dict:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def log(msg: str) -> None:
    print(msg, flush=True)


# ------------------------------------------------------------------ checagens
def checar_boletim(boletim: dict, urls_permitidas: set) -> list[str]:
    erros = []
    esquema = json.loads(ESQUEMA.read_text(encoding="utf-8"))
    validador = jsonschema.Draft202012Validator(esquema)
    for e in sorted(validador.iter_errors(boletim), key=lambda e: list(e.path)):
        erros.append(f"schema: {'/'.join(map(str, e.path))}: {e.message[:150]}")
    mtd = boletim.get("monthly_evolution_mtd", {})
    n = mtd.get("days_elapsed")
    if len(mtd.get("daily_dates", [])) != n:
        erros.append("daily_dates precisa ter exatamente days_elapsed itens (senão o painel inventa a curva)")
    for a in mtd.get("assets", []):
        if len(a.get("daily_history", [])) != n:
            erros.append(f"daily_history de '{a.get('asset')}' precisa ter {n} itens")
    # todo link publicado precisa ter vindo da coleta
    for bloco in boletim.get("detailed_blocks_and_news", []):
        links = [n["url"] for n in bloco.get("news_sources", [])]
        links += [l["url"] for e in bloco.get("strategic_directions_by_elo", []) for l in e.get("reference_links", [])]
        for u in links:
            if u not in urls_permitidas or not url_segura(u):
                erros.append(f"link não originado da coleta: {u[:80]}")
    return erros


# ------------------------------------------------------------- status fontes
def status_das_fontes(cfg: Config, status_noticias: list, relatorio_coleta: dict) -> list:
    por_nome = {s["nome"]: s for s in status_noticias}
    cotacoes: dict[str, list] = {}
    for rels in relatorio_coleta.values():
        for r in rels:
            if r["status"] != "inativa":
                cotacoes.setdefault(r["fonte"], []).append(r)
    regioes: dict[str, list] = {}
    for f in cfg.fontes:
        item = {"nome": f["nome"], "url": f["url"], "tipo": f.get("tipo", "noticias"), "idioma": f.get("idioma", "pt"),
                "prioridade": f.get("prioridade", 3), "ativa": f.get("ativa", True),
                "observacao": f.get("observacao", ""), "status": "", "detalhe": ""}
        if not f.get("ativa", True):
            item["status"], item["detalhe"] = "desativada", "fora do uso (ativa: false)"
        else:
            partes, estados = [], []
            sn = por_nome.get(f["nome"])
            if sn:
                estados.append(sn["status"] if sn["status"] != "ok" or sn["itens_na_janela"] else "sem_itens")
                if sn["status"] in ("ok", "sem_itens"):
                    partes.append(f"{sn['itens_na_janela']} notícia(s) na janela via {sn['modo'] or '—'}"
                                  + (f" ({sn['feed']})" if sn.get("feed") else ""))
                else:
                    partes.append(f"notícias: {sn['mensagem'][:120]}")
            sc = cotacoes.get(f["nome"], [])
            if sc:
                ok = sum(1 for r in sc if r["status"] == "ok")
                estados.append("ok" if ok == len(sc) else ("parcial" if ok else
                               ("robots" if all(r["status"] == "robots" for r in sc) else "falha")))
                partes.append(f"cotações: {ok}/{len(sc)} leituras ok")
                erros = [r["mensagem"] for r in sc if r["status"] != "ok"]
                if erros:
                    partes.append(f"ex.: {erros[0][:120]}")
            if not estados:
                item["status"], item["detalhe"] = "nao_usada", "sem coleta neste turno"
            else:
                if all(e == "ok" for e in estados):
                    item["status"] = "ok"
                elif any(e in ("ok", "parcial") for e in estados):
                    item["status"] = "parcial"
                elif all(e == "robots" for e in estados):
                    item["status"] = "robots"
                elif all(e == "sem_itens" for e in estados):
                    item["status"] = "sem_itens"
                else:
                    item["status"] = "falha"
                item["detalhe"] = " · ".join(partes)
        regioes.setdefault(f.get("regiao", "Outra"), []).append(item)
    ordem = ["Brasil", "Argentina", "Internacional", "China"]
    return [{"regiao": r, "fontes": regioes[r]} for r in sorted(regioes, key=lambda r: (ordem.index(r) if r in ordem else 9, r))]


# ------------------------------------------------------------ etapas comuns
def _coletar_cotacoes(cfg: Config, cliente, hist, hoje):
    resultados, relatorio_coleta = {}, {}
    for ind in cfg.indicadores:
        obs, rel = coletar_indicador(ind, cfg, cliente, hoje)
        resultados[ind["id"]] = validar(ind, obs, hist, hoje, rel)
        relatorio_coleta[ind["id"]] = rel
        r = resultados[ind["id"]]
        log(f"  {r.status:<13} {ind['id']:<22} "
            + (f"{fmt_valor(r.valor, ind['unidade'], ind.get('casas', 2))} ({r.fonte}, {r.data:%d/%m})" if r.valor is not None else "—"))
    hist.salvar()
    return resultados, relatorio_coleta


def _calcular(cfg: Config, resultados, hist, hoje):
    g = cfg.geral
    eixo = eixo_janela(hoje, g["janela"]["pregoes"])
    metricas = {ind["id"]: calcular_metricas(ind, resultados[ind["id"]], hist.serie(ind["id"]), hoje, eixo,
                                             g["janela"].get("max_dias_repetidos", 2),
                                             g["projecoes"].get("janela_volatilidade", 21))
                for ind in cfg.indicadores}
    spreads = calcular_spreads(cfg.blocos_cfg.get("spreads", []), metricas)
    cn = g.get("ndf", {})
    spot, taxa = metricas.get(cn.get("indicador_spot")), metricas.get(cn.get("indicador_taxa_brl"))
    ndf = calcular_ndf(spot.valor, taxa.valor, float(cn.get("cupom_cambial_aa", 4.8)),
                       int(cn.get("prazo_dias_corridos", 160)), hoje) \
        if spot and spot.disponivel and taxa and taxa.disponivel else None
    saca = metricas.get(cn.get("indicador_saca_usd"))
    return eixo, metricas, spreads, ndf, (saca.valor if saca and saca.disponivel else None)


def _ids_do_bloco(cfg: Config, metricas: dict, bloco_id: str, lista: str, campo: str | None = None) -> list:
    return [i for i in cfg.blocos_cfg.get(lista, []) if i in metricas and metricas[i].bloco == bloco_id
            and metricas[i].disponivel and (campo is None or getattr(metricas[i], campo) is not None)]


def _valores(resultados: dict) -> dict:
    return {i: [r.data.isoformat(), round(r.valor, 6)] for i, r in resultados.items() if r.valor is not None and r.data}


def _publicar(cfg: Config, *, agora, turno, modo, metricas, spreads, ndf, saca_usd, eixo, blocos_txt, fech,
              por_bloco, bandas, registro, relatorio_coleta, status_noticias, texto_stats, noticias_stats,
              analise_em: str, saida_json=None, valores: dict) -> int:
    g = cfg.geral
    n_status = {s: sum(1 for m in metricas.values() if m.status == s) for s in ("ok", "alerta", "desatualizado", "indisponivel")}
    validos = n_status["ok"] + n_status["alerta"]
    qualidade = {
        "gerado_em": agora.isoformat(timespec="minutes"), "turno": turno, "versao_agente": __version__,
        "modo_atualizacao": modo, "analise_gerada_em": analise_em,
        "cotacoes_atualizadas_em": agora.isoformat(timespec="minutes"),
        "indicadores": {"total": len(metricas), **n_status},
        "lista_indicadores": [{
            "id": m.id, "nome": m.nome, "nome_curto": m.nome_curto, "bloco": m.bloco, "status": m.status,
            "valor": fmt_valor(m.valor, m.unidade, m.casas) if m.disponivel else None,
            "data": m.data.isoformat() if m.data else None, "fonte": m.fonte, "url": m.url,
            "mensagens": m.mensagens,
            "fontes": [{"fonte": r["fonte"], "status": r["status"], "mensagem": r["mensagem"][:160]}
                       for r in relatorio_coleta[m.id]]} for m in metricas.values()],
        "texto": texto_stats,
        "noticias": noticias_stats,
        "track_record": registro.placar(),
    }
    fontes_status = status_das_fontes(cfg, status_noticias, relatorio_coleta)
    montador = Montador(cfg)
    boletim = montador.montar(agora=agora, turno=turno, metricas=metricas, spreads=spreads, blocos_txt=blocos_txt,
                              fech=fech, noticias_bloco=por_bloco, bandas=bandas, registro=registro, ndf=ndf,
                              eixo=eixo, qualidade=qualidade, fontes_status=fontes_status, saca_usd=saca_usd)
    if modo == "cotacoes":
        hora_analise = datetime.fromisoformat(analise_em)
        boletim["metadata"]["timestamp"] = (f"{agora:%d/%m/%Y %H:%M} BRT — cotações atualizadas pelo monitor · "
                                            f"análise do {NOME_TURNO.get(turno, turno)} das {hora_analise:%H:%M}")
    urls_ok = {n.url for lista in por_bloco.values() for n in lista} | {link_seguro(m.url) for m in metricas.values() if m.url}
    erros = checar_boletim(boletim, urls_ok)
    if erros:
        log("✖ Boletim reprovado na checagem final — o arquivo anterior foi mantido:")
        for e in erros[:30]:
            log("   - " + e)
        return 2
    validos_pct = 100 * validos / max(1, len(metricas))
    minimo = g["coleta"].get("minimo_indicadores_validos_pct", 40)
    if validos_pct < minimo:
        log(f"✖ Só {validos_pct:.0f}% dos indicadores com dado válido (mínimo {minimo}%) — boletim anterior mantido.")
        return 3
    destino = Path(saida_json) if saida_json else cfg.caminho("json")
    salvar_json(boletim, destino)
    md = montador.markdown(boletim, agora=agora, turno=turno, metricas=metricas, blocos_txt=blocos_txt, fech=fech,
                           noticias_bloco=por_bloco, spreads=spreads, caminho_json=destino.name)
    caminho_md = cfg.caminho("relatorio_md")
    caminho_md.parent.mkdir(parents=True, exist_ok=True)
    caminho_md.write_text(md, encoding="utf-8")
    if modo == "completo":                       # o monitor não arquiva cada atualização de 20 min
        arquivo = cfg.caminho("arquivo_dir") / f"{agora:%Y}" / f"{agora:%m}"
        arquivo.mkdir(parents=True, exist_ok=True)
        base = f"{agora:%Y-%m-%d_%H%M}_{turno}"
        shutil.copy(destino, arquivo / f"{base}.json")
        (arquivo / f"{base}.md").write_text(md, encoding="utf-8")
    cfg.caminho("estado_cotacoes").write_text(json.dumps(valores, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"✔ Boletim publicado ({modo}): {destino} · {validos}/{len(metricas)} indicadores")
    return 0


# ------------------------------------------------------------------ executar
def executar(cfg: Config, agora: datetime | None = None, turno: str | None = None, llm=None,
             saida_json: Path | None = None) -> int:
    """Boletim completo: cotações + notícias + análise escrita pela IA (verificada)."""
    agora = agora or cfg.agora()
    hoje = agora.date()
    turno = turno or turno_de(agora)
    nome_turno = NOME_TURNO[turno]
    data_hora = f"{agora:%d/%m/%Y %H:%M} BRT"
    g = cfg.geral
    log(f"▶ Agro Intel Agent {__version__} — {nome_turno} {data_hora}")
    cliente = Cliente(g["coleta"])
    hist = Historico(cfg.caminho("historico_csv"))

    # 1-2) cotações conferidas e cálculos (código, não IA)
    resultados, relatorio_coleta = _coletar_cotacoes(cfg, cliente, hist, hoje)
    eixo, metricas, spreads, ndf, saca_usd = _calcular(cfg, resultados, hist, hoje)

    # 3) notícias
    checagem = _ler_json(cfg.caminho("checagem_fontes"))
    coletor = ColetorNoticias(cfg, cliente, agora, checagem.get("feeds", {}))
    todas = []
    for fonte in cfg.fontes_ativas():
        if fonte.get("tipo") in TIPOS_COM_NOTICIAS:
            todas += coletor.coletar_fonte(fonte)
            st = coletor.status[-1]
            log(f"  notícias {st['status']:<9} {fonte['nome'][:34]:<34} {st['itens_na_janela']:>3} na janela ({st['modo'] or '—'})")
    prioridades = {f["nome"]: f.get("prioridade", 3) for f in cfg.fontes}
    por_bloco = selecionar(todas, cfg.blocos, prioridades, g["noticias"].get("max_por_bloco", 10), agora)
    selecionadas = list({n.id: n for lista in por_bloco.values() for n in lista}.values())
    coletor.completar_resumos(selecionadas)
    pasta_not = cfg.caminho("noticias_dir")
    pasta_not.mkdir(parents=True, exist_ok=True)
    (pasta_not / f"{hoje.isoformat()}.json").write_text(json.dumps(
        {"gerado_em": agora.isoformat(), "status_fontes": coletor.status,
         "noticias": [n.como_dict() for n in todas]}, ensure_ascii=False, indent=1), encoding="utf-8")
    checagem["feeds"] = {**checagem.get("feeds", {}), **coletor.feeds}
    cfg.caminho("checagem_fontes").parent.mkdir(parents=True, exist_ok=True)
    cfg.caminho("checagem_fontes").write_text(json.dumps(checagem, ensure_ascii=False, indent=1), encoding="utf-8")

    # 4) auditoria das projeções vencidas
    registro = RegistroProjecoes(cfg.caminho("projecoes"))
    ids_proj_cfg = cfg.blocos_cfg.get("projecoes", [])
    auditadas = registro.auditar({i: hist.serie(i) for i in ids_proj_cfg})
    if auditadas:
        log(f"  auditoria: {auditadas} projeção(ões) conferida(s) com o valor realizado")

    # 5) texto por bloco (IA + verificador, ou automático)
    redator = Redator(cfg, llm if llm is not None else ClienteLLM(g.get("llm", {})))
    log(f"  texto: {redator.stats['modelo']}")
    blocos_txt = {}
    for b in cfg.blocos:
        ms = [m for m in metricas.values() if m.bloco == b["id"]]
        macro = [metricas[i] for i in ("dolar_ptax",) if i in metricas and b["id"] != "cambio_e_energia"]
        blocos_txt[b["id"]] = redator.escrever_bloco(
            b, ms, macro, [s for s in spreads if s.bloco == b["id"]], por_bloco.get(b["id"], []),
            ndf if b["id"] == "cambio_e_energia" else None, nome_turno, data_hora,
            _ids_do_bloco(cfg, metricas, b["id"], "painel_semanal", "var_semana_pct"),
            _ids_do_bloco(cfg, metricas, b["id"], "painel_mensal", "var_mes_pct"),
            _ids_do_bloco(cfg, metricas, b["id"], "projecoes"))

    # 6) bandas de projeção (viés da análise + volatilidade do código) e registro
    vieses = {k: v for t in blocos_txt.values() for k, v in t.get("vieses_projecao", {}).items()}
    bandas = {}
    for i in ids_proj_cfg:
        if i in metricas:
            banda = calcular_bandas(metricas[i], hoje, g["projecoes"], vieses.get(i, "neutro"))
            if banda:
                bandas[i] = banda
                if turno in g["projecoes"].get("registrar_nos_turnos", ["fechamento"]):
                    registro.registrar(banda, agora.isoformat(timespec="minutes"))
    registro.salvar()

    # 7) fechamento: escopo, pílula e roteiro de áudio
    fontes_ok = sum(1 for s in coletor.status if s["status"] == "ok" and s["itens_na_janela"])
    validos = sum(1 for m in metricas.values() if m.status in ("ok", "alerta"))
    resumo_coleta = {"ok": validos, "total": len(metricas), "noticias": len(selecionadas), "fontes": fontes_ok}
    chave = [metricas[i] for i in CHAVES_FECHAMENTO if i in metricas and metricas[i].disponivel]
    fech = redator.escrever_fechamento(blocos_txt, cfg.blocos, chave, ndf, nome_turno, data_hora,
                                       resumo_coleta, selecionadas)
    redator.finalizar()
    noticias_stats = {"coletadas": len(todas), "usadas": len(selecionadas), "fontes_ok": fontes_ok,
                      "fontes_com_falha": sum(1 for s in coletor.status if s["status"] in ("falha", "robots"))}

    # 8-9) publicar
    rc = _publicar(cfg, agora=agora, turno=turno, modo="completo", metricas=metricas, spreads=spreads, ndf=ndf,
                   saca_usd=saca_usd, eixo=eixo, blocos_txt=blocos_txt, fech=fech, por_bloco=por_bloco,
                   bandas=bandas, registro=registro, relatorio_coleta=relatorio_coleta,
                   status_noticias=coletor.status, texto_stats=redator.stats, noticias_stats=noticias_stats,
                   analise_em=agora.isoformat(timespec="minutes"), saida_json=saida_json,
                   valores=_valores(resultados))
    if rc == 0:
        # guarda a análise verificada para o monitor de cotações reaproveitar até o próximo turno
        cfg.caminho("ultima_analise").write_text(json.dumps({
            "gerado_em": agora.isoformat(timespec="minutes"), "turno": turno, "blocos_txt": blocos_txt,
            "fech": fech, "noticias": {k: [n.como_dict() for n in v] for k, v in por_bloco.items()},
            "status_noticias": coletor.status, "texto_stats": redator.stats, "noticias_stats": noticias_stats,
            "valores": _valores(resultados)}, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  {len(selecionadas)} notícias · texto: {redator.stats['modo']}")
    return rc


# ------------------------------------------------------------------ monitorar
def monitorar(cfg: Config, agora: datetime | None = None) -> int:
    """Monitor de cotações: confere SÓ as cotações (sem notícias, sem IA) e, se houver
    cotação nova, republica o boletim com os números novos e a última análise verificada."""
    agora = agora or cfg.agora()
    hoje = agora.date()
    g = cfg.geral
    saida_gh = os.environ.get("GITHUB_OUTPUT")

    def sinalizar(mudou: bool):
        if saida_gh:
            with open(saida_gh, "a", encoding="utf-8") as f:
                f.write(f"mudou={'sim' if mudou else 'nao'}\n")

    log(f"▶ Monitor de cotações — {agora:%d/%m/%Y %H:%M} BRT")
    analise = _ler_json(cfg.caminho("ultima_analise"))
    if not analise:
        log("  aguardando o primeiro boletim completo (ainda não há análise para reaproveitar)")
        sinalizar(False)
        return 0
    cliente = Cliente(g["coleta"])
    hist = Historico(cfg.caminho("historico_csv"))
    resultados, relatorio_coleta = _coletar_cotacoes(cfg, cliente, hist, hoje)
    valores = _valores(resultados)
    anteriores = _ler_json(cfg.caminho("estado_cotacoes")) or analise.get("valores", {})
    mudaram = sorted(i for i, v in valores.items() if anteriores.get(i) != v)
    if not mudaram:
        log("  sem cotação nova — nada a publicar")
        sinalizar(False)
        return 0
    log(f"  cotações novas: {', '.join(mudaram)}")

    eixo, metricas, spreads, ndf, saca_usd = _calcular(cfg, resultados, hist, hoje)
    registro = RegistroProjecoes(cfg.caminho("projecoes"))
    registro.auditar({i: hist.serie(i) for i in cfg.blocos_cfg.get("projecoes", [])})
    registro.salvar()

    from .coletores.noticias import Noticia
    por_bloco = {k: [Noticia(**d) for d in v] for k, v in analise.get("noticias", {}).items()}
    blocos_txt, fech = analise["blocos_txt"], analise["fech"]
    # cards semanais/mensais dos indicadores que mudaram passam a mostrar texto automático com os números novos
    redator = Redator(cfg, None)
    for b in cfg.blocos:
        ms = [m for m in metricas.values() if m.bloco == b["id"]]
        auto = redator._bloco_automatico(b, ms, [], _ids_do_bloco(cfg, metricas, b["id"], "painel_semanal", "var_semana_pct"),
                                         _ids_do_bloco(cfg, metricas, b["id"], "painel_mensal", "var_mes_pct"), [])
        t = blocos_txt.setdefault(b["id"], auto)
        for campo in ("drivers_semana", "narrativas_mes"):
            atual = t.setdefault(campo, {})
            for i, texto in auto[campo].items():
                if i in mudaram or i not in atual:
                    atual[i] = texto
    vieses = {k: v for t in blocos_txt.values() for k, v in t.get("vieses_projecao", {}).items()}
    bandas = {}
    for i in cfg.blocos_cfg.get("projecoes", []):
        if i in metricas:
            banda = calcular_bandas(metricas[i], hoje, g["projecoes"], vieses.get(i, "neutro"))
            if banda:
                bandas[i] = banda
    rc = _publicar(cfg, agora=agora, turno=analise.get("turno", "fechamento"), modo="cotacoes", metricas=metricas,
                   spreads=spreads, ndf=ndf, saca_usd=saca_usd, eixo=eixo, blocos_txt=blocos_txt, fech=fech,
                   por_bloco=por_bloco, bandas=bandas, registro=registro, relatorio_coleta=relatorio_coleta,
                   status_noticias=analise.get("status_noticias", []), texto_stats=analise.get("texto_stats", {}),
                   noticias_stats=analise.get("noticias_stats", {}), analise_em=analise["gerado_em"],
                   valores=valores)
    sinalizar(rc == 0)
    return 0 if rc in (0, 3) else rc


# ------------------------------------------------------------- checar fontes
def checar_fontes(cfg: Config) -> int:
    agora = cfg.agora()
    hoje = agora.date()
    cliente = Cliente(cfg.geral["coleta"])
    linhas_ind, rel_total = [], {}
    for ind in cfg.indicadores:
        obs, rel = coletar_indicador(ind, cfg, cliente, hoje)
        rel_total[ind["id"]] = rel
        for r in rel:
            linhas_ind.append((ind["id"], r))
    coletor = ColetorNoticias(cfg, cliente, agora, {})
    for fonte in cfg.fontes_ativas():
        if fonte.get("tipo") in TIPOS_COM_NOTICIAS:
            coletor.coletar_fonte(fonte)
    icone = {"ok": "✅", "erro": "❌", "falha": "❌", "robots": "🚫", "inativa": "⏸️", "sem_itens": "⚠️"}
    md = [f"# Checagem de fontes — {agora:%d/%m/%Y %H:%M}", "",
          "## Cotações", "", "| Indicador | Fonte | Status | Detalhe |", "|---|---|---|---|"]
    for ind_id, r in linhas_ind:
        md.append(f"| {ind_id} | {r['fonte']} | {icone.get(r['status'], '')} {r['status']} | {r['mensagem'][:160].replace('|', '/')} |")
    md += ["", "## Notícias", "", "| Fonte | Região | Status | Modo | Na janela | Lidos | Feed / mensagem |", "|---|---|---|---|---|---|---|"]
    for s in coletor.status:
        md.append(f"| {s['nome']} | {s['regiao']} | {icone.get(s['status'], '')} {s['status']} | {s['modo'] or '—'} | "
                  f"{s['itens_na_janela']} | {s['itens_lidos']} | {(s['feed'] or s['mensagem'])[:120].replace('|', '/')} |")
    md += ["", "Legenda: ✅ ok · ❌ erro · 🚫 bloqueado pelo robots.txt do site · ⚠️ sem itens · ⏸️ desativada"]
    destino_md = cfg.raiz / "relatorios" / "checagem_fontes.md"
    destino_md.parent.mkdir(parents=True, exist_ok=True)
    destino_md.write_text("\n".join(md), encoding="utf-8")
    checagem = _ler_json(cfg.caminho("checagem_fontes"))
    checagem.update({"gerado_em": agora.isoformat(timespec="minutes"), "indicadores": rel_total,
                     "noticias": coletor.status, "feeds": {**checagem.get("feeds", {}), **coletor.feeds}})
    cfg.caminho("checagem_fontes").write_text(json.dumps(checagem, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))
    return 0


# ----------------------------------------------------------- adicionar fonte
REGIOES = ("Brasil", "Argentina", "Internacional", "China", "Outra")
TIPOS = ("noticias", "cotacoes", "noticias_e_cotacoes", "relatorio_oficial", "api_oficial")


def adicionar_fonte(raiz: Path, nome: str, url: str, regiao: str = "Brasil", tipo: str = "noticias",
                    idioma: str = "pt", rss: str = "", observacao: str = "", prioridade: int = 2) -> str:
    """Acrescenta um site ao final de config/fontes.yaml (preservando os comentários)."""
    nome = " ".join(str(nome).split())[:80]
    url, rss = url.strip(), (rss or "").strip()
    if not nome:
        raise ValueError("informe o nome do site")
    if not url_segura(url):
        raise ValueError(f"URL inválida: {url!r} (use http:// ou https://)")
    if rss and not url_segura(rss):
        raise ValueError(f"RSS inválido: {rss!r}")
    regiao = regiao if regiao in REGIOES else "Outra"
    tipo = tipo if tipo in TIPOS else "noticias"
    idioma = idioma if idioma in ("pt", "es", "en", "zh") else "pt"
    caminho = Path(raiz) / "config" / "fontes.yaml"
    original = caminho.read_text(encoding="utf-8")
    atuais = (yaml.safe_load(original) or {}).get("fontes", [])
    for f in atuais:
        if f["nome"].lower() == nome.lower() or f["url"].rstrip("/") == url.rstrip("/"):
            raise ValueError(f"já existe na lista: {f['nome']} ({f['url']})")
    item = {"nome": nome, "url": url, "regiao": regiao, "tipo": tipo, "idioma": idioma, "ativa": True,
            "prioridade": int(prioridade)}
    if rss:
        item["rss"] = rss
    if observacao:
        item["observacao"] = " ".join(str(observacao).split())[:200]
    bloco = yaml.safe_dump([item], allow_unicode=True, sort_keys=False, width=200)
    bloco = "\n".join("  " + l if l else l for l in bloco.splitlines())
    novo = original.rstrip("\n") + "\n\n" + bloco + "\n"
    if len((yaml.safe_load(novo) or {}).get("fontes", [])) != len(atuais) + 1:
        raise ValueError("falha ao gravar a fonte (YAML inconsistente) — nada foi alterado")
    caminho.write_text(novo, encoding="utf-8")
    return nome


# ------------------------------------------------------------------- main
def testar_ia(cfg) -> int:
    """Confere cada API da fila e escreve o resultado no log (e no resumo da execução no GitHub)."""
    from .llm import testar_provedores
    linhas = testar_provedores(cfg.geral.get("llm", {}))
    icone = {True: "✔", False: "✖", None: "—"}
    tabela = ["| | IA | Modelo | Resultado |", "|---|---|---|---|"] + [
        f"| {icone[l['ok']]} | {l['nome']} | `{l['modelo']}` | {l['msg'].replace('|', '/')} |" for l in linhas]
    configuradas = [l for l in linhas if l["ok"] is not None]
    if not configuradas:
        rodape = "Nenhuma API configurada: o boletim usará só a IA local (gratuita e sem limite, porém mais lenta)."
    elif any(l["ok"] for l in configuradas):
        ordem = " → ".join(l["nome"] for l in configuradas if l["ok"])
        rodape = f"Fila em uso: {ordem} → IA local (rede de segurança)."
    else:
        rodape = "Nenhuma API respondeu: confira os secrets. O boletim continuará saindo com a IA local."
    texto = "### Teste das IAs gratuitas\n\n" + "\n".join(tabela) + "\n\n" + rodape + "\n"
    print(texto)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(texto)
    return 1 if configuradas and not any(l["ok"] for l in configuradas) else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m agente", description="Agro Intel Agent")
    sub = p.add_subparsers(dest="comando")
    e = sub.add_parser("executar", help="gera o boletim")
    e.add_argument("--turno", choices=list(NOME_TURNO), help="força o turno (padrão: pelo horário)")
    e.add_argument("--sem-ia", action="store_true", help="não chama a IA (texto automático)")
    e.add_argument("--saida", help="caminho alternativo do JSON")
    sub.add_parser("monitorar", help="confere só as cotações e republica se houver cotação nova")
    sub.add_parser("checar-fontes", help="testa todas as fontes")
    sub.add_parser("validar-config", help="confere os arquivos de configuração")
    sub.add_parser("testar-ia", help="testa cada API gratuita da fila (chaves e modelos)")
    a = sub.add_parser("adicionar-fonte", help="inclui um site em config/fontes.yaml")
    a.add_argument("--nome", required=True)
    a.add_argument("--url", required=True)
    a.add_argument("--regiao", default="Brasil", choices=REGIOES)
    a.add_argument("--tipo", default="noticias", choices=TIPOS)
    a.add_argument("--idioma", default="pt", choices=("pt", "es", "en", "zh"))
    a.add_argument("--rss", default="")
    a.add_argument("--observacao", default="")
    args = p.parse_args(argv)
    cfg = carregar_config()
    comando = args.comando or "executar"
    if comando == "validar-config":
        probs = cfg.problemas()
        print("\n".join(probs) if probs else "Configuração consistente ✔")
        return 1 if probs else 0
    if comando == "checar-fontes":
        return checar_fontes(cfg)
    if comando == "testar-ia":
        return testar_ia(cfg)
    if comando == "monitorar":
        if not cfg.problemas():
            from .calendario import eh_dia_util
            if not eh_dia_util(cfg.agora().date()):
                print("Hoje não há pregão — monitor em pausa.")
                return 0
        return monitorar(cfg)
    if comando == "adicionar-fonte":
        try:
            nome = adicionar_fonte(cfg.raiz, args.nome, args.url, args.regiao, args.tipo, args.idioma,
                                   args.rss, args.observacao)
        except ValueError as erro:
            print(f"✖ {erro}")
            return 1
        print(f"✔ Fonte '{nome}' adicionada em config/fontes.yaml")
        return 0
    probs = cfg.problemas()
    if probs:
        print("✖ Configuração inconsistente:\n  " + "\n  ".join(probs))
        return 1
    llm = ClienteLLM(cfg.geral.get("llm", {}), env={}, usar_local=False) if getattr(args, "sem_ia", False) else None
    return executar(cfg, turno=getattr(args, "turno", None), llm=llm, saida_json=getattr(args, "saida", None))


if __name__ == "__main__":
    sys.exit(main())
