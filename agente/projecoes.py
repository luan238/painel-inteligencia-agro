"""Projeções auditáveis.

As faixas são calculadas por código a partir da volatilidade recente (bandas de
±σ). A IA só pode indicar um VIÉS (alta / baixa / neutro), que desloca o centro
da banda em uma fração de σ. Cada projeção é gravada em data/projecoes.jsonl e,
quando a data-alvo chega, o código confere o valor realizado e calcula o
histórico de acertos (track record) — sem autoavaliação da IA.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

from .calendario import dias_uteis_entre, somar_dias_uteis, ultimo_dia_util_do_mes
from .numeros import fmt, fmt_pct, fmt_valor

SINAL_VIES = {"alta": 1, "baixa": -1, "neutro": 0}


def calcular_bandas(m, hoje: date, cfg: dict, vies: str = "neutro") -> dict | None:
    n_vol = m.n_obs_vol if getattr(m, "vol_ref", None) else m.n_obs
    if not m.disponivel or m.vol_diaria is None or n_vol < cfg.get("minimo_pregoes_para_banda", 10):
        return None
    sig, k = m.vol_diaria, float(cfg.get("sigma", 1.0))
    desloc = float(cfg.get("deslocamento_vies_sigma", 0.5)) * SINAL_VIES.get(vies, 0)
    h1 = int(cfg.get("pregoes_curto_prazo", 5))
    alvo1 = somar_dias_uteis(m.data, h1)
    c1 = m.valor * math.exp(desloc * sig * math.sqrt(h1))
    alvo2 = ultimo_dia_util_do_mes(hoje.year, hoje.month)
    if dias_uteis_entre(m.data, alvo2) < 3:
        prox = date(hoje.year + (hoje.month == 12), hoje.month % 12 + 1, 1)
        alvo2 = ultimo_dia_util_do_mes(prox.year, prox.month)
    h2 = max(1, dias_uteis_entre(m.data, alvo2))
    c2 = m.valor * math.exp(desloc * sig * math.sqrt(h2))
    return {
        "indicador": m.id, "data_base": m.data.isoformat(), "valor_base": m.valor, "vies": vies,
        "sigma_diario": sig, "k": k, "vol_ref": getattr(m, "vol_ref", None), "n_vol": n_vol,
        "curto": {"alvo": alvo1.isoformat(), "pregoes": h1,
                  "min": c1 * math.exp(-k * sig * math.sqrt(h1)), "max": c1 * math.exp(k * sig * math.sqrt(h1))},
        "mes": {"alvo": alvo2.isoformat(), "pregoes": h2, "base": c2,
                "bull": c2 * math.exp(k * sig * math.sqrt(h2)), "bear": c2 * math.exp(-k * sig * math.sqrt(h2))},
    }


class RegistroProjecoes:
    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)
        self.itens: list[dict] = []
        if self.caminho.exists():
            with open(self.caminho, encoding="utf-8") as f:
                self.itens = [json.loads(l) for l in f if l.strip()]

    def registrar(self, banda: dict, criada_em: str) -> bool:
        chave = (banda["indicador"], banda["data_base"])
        if any((p["indicador"], p["data_base"]) == chave for p in self.itens):
            return False
        self.itens.append({**banda, "criada_em": criada_em, "auditoria": {"curto": None, "mes": None}})
        return True

    def auditar(self, series: dict) -> int:
        """Confere projeções vencidas contra o valor realizado. Retorna quantas foram auditadas."""
        n = 0
        for p in self.itens:
            serie = series.get(p["indicador"]) or {}
            if not serie:
                continue
            ultima = max(serie)
            for tipo in ("curto", "mes"):
                if p["auditoria"].get(tipo) is not None:
                    continue
                alvo = date.fromisoformat(p[tipo]["alvo"])
                if ultima < alvo:
                    continue
                datas_ok = [d for d in serie if d >= alvo]
                d_real = min(datas_ok)
                if dias_uteis_entre(alvo, d_real) > 3:      # sem dado perto do alvo: não audita
                    p["auditoria"][tipo] = {"sem_dado": True}
                    continue
                real = serie[d_real]
                lo, hi = (p["curto"]["min"], p["curto"]["max"]) if tipo == "curto" else (p["mes"]["bear"], p["mes"]["bull"])
                res = {"data_real": d_real.isoformat(), "valor_real": real, "dentro": lo <= real <= hi}
                if p.get("vies", "neutro") != "neutro":
                    res["direcao_certa"] = (real - p["valor_base"]) * SINAL_VIES[p["vies"]] > 0
                if tipo == "mes":
                    cen = {"base": p["mes"]["base"], "bull": p["mes"]["bull"], "bear": p["mes"]["bear"]}
                    res["cenario_mais_proximo"] = min(cen, key=lambda c: abs(cen[c] - real))
                p["auditoria"][tipo] = res
                n += 1
        return n

    def placar(self, indicador: str | None = None, ultimos: int = 60) -> dict:
        auds = [p["auditoria"]["curto"] for p in self.itens
                if (indicador is None or p["indicador"] == indicador)
                and p["auditoria"].get("curto") and not p["auditoria"]["curto"].get("sem_dado")]
        auds = auds[-ultimos:]
        direcao = [a["direcao_certa"] for a in auds if "direcao_certa" in a]
        return {"auditadas": len(auds), "acertos": sum(a["dentro"] for a in auds),
                "taxa_pct": round(100 * sum(a["dentro"] for a in auds) / len(auds), 1) if auds else None,
                "direcao_avaliadas": len(direcao), "direcao_acertos": sum(direcao)}

    def ultima_auditada(self, indicador: str) -> dict | None:
        auds = [p for p in self.itens if p["indicador"] == indicador and p["auditoria"].get("curto")
                and not p["auditoria"]["curto"].get("sem_dado")]
        return auds[-1] if auds else None

    def proxima_auditoria(self, indicador: str) -> str | None:
        pend = [p["curto"]["alvo"] for p in self.itens if p["indicador"] == indicador and not p["auditoria"].get("curto")]
        return min(pend) if pend else None

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for p in self.itens:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        tmp.replace(self.caminho)


def _metodo(banda: dict, m) -> str:
    sig = fmt_pct(banda["sigma_diario"] * 100, 2, sinal=False)
    if banda.get("vol_ref"):
        return (f"Método: banda de volatilidade (σ diário {sig} de {banda['vol_ref']}, {banda.get('n_vol')} pregões; "
                f"o histórico próprio ainda tem {m.n_obs} pregão(ões)).")
    return f"Método: banda de volatilidade (σ diário {sig}, {m.n_obs} pregões no histórico)."


def linha_painel(m, banda: dict | None, registro: RegistroProjecoes, gatilho: str) -> dict:
    """Monta a linha da 'Matriz de Projeções Auditáveis' no formato do painel."""
    u, c = m.unidade, m.casas
    placar = registro.placar(m.id)
    base = f"{fmt_valor(m.valor, u, c)} ({m.fonte}, {m.data:%d/%m})" if m.disponivel else "indisponível"
    if placar["auditadas"]:
        base += (f" · Track record: {placar['acertos']}/{placar['auditadas']} bandas acertadas "
                 f"({fmt(placar['taxa_pct'], 1)}%)")
    else:
        prox = registro.proxima_auditoria(m.id)
        base += " · Track record em formação" + (f" (1ª aferição em {date.fromisoformat(prox):%d/%m})" if prox else "")
    if banda is None:
        motivo = "histórico insuficiente para calcular volatilidade" if m.disponivel else "sem cotação válida"
        return {"commodity": m.nome_curto, "current_base": base,
                "short_term_target_23_oct": f"— ({motivo})",
                "end_of_month_30_oct": {"base_case": "—", "bull_case": "—", "bear_case": "—"},
                "audit_trigger": gatilho or "—"}
    vies_txt = {"alta": ", viés de alta", "baixa": ", viés de baixa"}.get(banda["vies"], "")
    curto = banda["curto"]
    alvo_txt = (f"{fmt_valor(curto['min'], u, c)} – {fmt_valor(curto['max'], u, c)} até "
                f"{date.fromisoformat(curto['alvo']):%d/%m} (banda ±{fmt(banda['k'], 1)}σ{vies_txt})")
    ult = registro.ultima_auditada(m.id)
    if ult:
        a = ult["auditoria"]["curto"]
        alvo_txt += (f" · Última aferição ({date.fromisoformat(a['data_real']):%d/%m}): {fmt(a['valor_real'], c)} "
                     f"{'✅ dentro' if a['dentro'] else '❌ fora'} da banda "
                     f"{fmt(ult['curto']['min'], c)}–{fmt(ult['curto']['max'], c)}")
    mes = banda["mes"]
    alvo_mes = date.fromisoformat(mes["alvo"])
    return {
        "commodity": m.nome_curto,
        "current_base": base,
        "short_term_target_23_oct": alvo_txt,
        "end_of_month_30_oct": {
            "base_case": f"{fmt_valor(mes['base'], u, c)} ({alvo_mes:%d/%m})",
            "bull_case": f"{fmt_valor(mes['bull'], u, c)} (+{fmt(banda['k'], 1)}σ)",
            "bear_case": f"{fmt_valor(mes['bear'], u, c)} (−{fmt(banda['k'], 1)}σ)",
        },
        "audit_trigger": (gatilho + " | " if gatilho else "") + _metodo(banda, m),
    }
