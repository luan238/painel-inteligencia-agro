"""Conferência automática de cada cotação antes de ela entrar no relatório.

Checagens:
  • faixa plausível (fora = rejeitado; tenta fatores de unidade, ex. centavos→US$)
  • variação diária (acima do limite = alerta; 3x o limite = rejeitado)
  • defasagem (dado velho = desatualizado)
  • data no futuro (rejeitado)
  • divergência entre fontes (acima da tolerância = alerta)
  • leitura incerta (coluna por posição / data presumida = alerta)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .calendario import dias_uteis_entre
from .numeros import fmt, fmt_pct


@dataclass
class Resultado:
    indicador: str
    status: str                      # ok | alerta | desatualizado | indisponivel
    valor: float | None = None
    data: date | None = None
    fonte: str = ""
    url: str = ""
    detalhe: str = ""
    mensagens: list = field(default_factory=list)
    fontes: list = field(default_factory=list)   # relatório por fonte (coleta)

    def como_dict(self) -> dict:
        return {"indicador": self.indicador, "status": self.status, "valor": self.valor,
                "data": self.data.isoformat() if self.data else None, "fonte": self.fonte,
                "url": self.url, "detalhe": self.detalhe, "mensagens": self.mensagens}


def _ultimo_antes(serie: dict, d: date):
    anteriores = [k for k in serie if k < d]
    if not anteriores:
        return None, None
    k = max(anteriores)
    return k, serie[k]


def validar(ind: dict, observacoes: list, historico, hoje: date, relatorio_fontes: list) -> Resultado:
    faixa_min, faixa_max = ind["faixa"]
    var_max = float(ind.get("var_max_dia_pct", 8))
    defasagem_max = int(ind.get("defasagem_max_dias_uteis", 2))
    fatores = ind.get("fatores_aceitos", [1])
    tolerancia = float(ind.get("divergencia_max_pct", max(0.5, var_max / 4)))
    casas = ind.get("casas", 2)
    serie_hist = historico.serie(ind["id"])
    mensagens: list[str] = []

    # 1) normaliza unidade e aplica checagens individuais, registrando tudo no histórico
    ultima_data = max((o.data for o in observacoes), default=None)
    prioridade_na_serie: dict = {}
    aprovadas = []
    for o in sorted(observacoes, key=lambda o: (o.data, getattr(o, "prioridade", 9))):
        prioridade = getattr(o, "prioridade", 9)
        if not (faixa_min <= o.valor <= faixa_max):
            for f in fatores:
                if f != 1 and faixa_min <= o.valor * f <= faixa_max:
                    o.detalhe += f" · convertido (×{f})"
                    o.valor = round(o.valor * f, 6)
                    break
        status, msg = "ok", ""
        if o.data > hoje:
            status, msg = "rejeitado", f"{o.fonte}: data no futuro ({o.data:%d/%m/%Y}) — descartado"
        elif not (faixa_min <= o.valor <= faixa_max):
            status, msg = "rejeitado", (f"{o.fonte}: valor {o.valor} fora da faixa plausível "
                                        f"[{faixa_min}–{faixa_max}] — descartado")
        else:
            _, anterior = _ultimo_antes(serie_hist, o.data)
            if anterior:
                var = (o.valor / anterior - 1) * 100
                if abs(var) > 3 * var_max:
                    status, msg = "rejeitado", (f"{o.fonte}: salto de {fmt_pct(var)} em 1 pregão (mais de 3× o "
                                                f"limite de {var_max}%) — provável erro de leitura, descartado")
                elif abs(var) > var_max:
                    msg = f"{o.fonte}: variação de {fmt_pct(var)} no pregão, acima do limite de {var_max}% — confira"
        historico.registrar(o, status, prioridade)
        if status != "rejeitado":
            aprovadas.append(o)
            if o.data not in prioridade_na_serie or prioridade < prioridade_na_serie[o.data]:
                serie_hist = {**serie_hist, o.data: o.valor}
                prioridade_na_serie[o.data] = prioridade
        if msg and o.data == ultima_data:
            mensagens.append(msg)

    if not aprovadas:
        # sem dado novo válido: usa o último valor aprovado do histórico, marcado
        if serie_hist:
            d_ult = max(serie_hist)
            reg = historico.registro(ind["id"], d_ult) or {}
            mensagens.append(f"sem cotação nova válida; último valor confiável é de {d_ult:%d/%m/%Y}")
            return Resultado(ind["id"], "desatualizado" if dias_uteis_entre(d_ult, hoje) <= 10 else "indisponivel",
                             serie_hist[d_ult], d_ult, reg.get("fonte", ""), reg.get("url", ""),
                             reg.get("detalhe", ""), mensagens, relatorio_fontes)
        mensagens.append("nenhuma fonte retornou valor válido")
        return Resultado(ind["id"], "indisponivel", mensagens=mensagens, fontes=relatorio_fontes)

    # 2) escolhe a data mais recente e, nela, a fonte de maior prioridade
    d_final = max(o.data for o in aprovadas)
    do_dia = sorted([o for o in aprovadas if o.data == d_final], key=lambda o: getattr(o, "prioridade", 9))
    escolhida = do_dia[0]
    status = "ok"

    # 3) checagem cruzada entre fontes no mesmo dia
    if len(do_dia) > 1:
        vals = [o.valor for o in do_dia]
        diverg = (max(vals) / min(vals) - 1) * 100 if min(vals) > 0 else 0
        if diverg > tolerancia:
            status = "alerta"
            mensagens.append("fontes divergem " + fmt_pct(diverg, sinal=False) + ": " +
                             "; ".join(f"{o.fonte} {fmt(o.valor, casas)}" for o in do_dia))
        else:
            mensagens.append(f"confirmado por {len(do_dia)} fontes (diferença {fmt_pct(diverg, sinal=False)})")

    # 4) defasagem e leitura incerta
    atraso = dias_uteis_entre(d_final, hoje)
    if atraso > defasagem_max:
        status = "desatualizado"
        mensagens.append(f"último dado é de {d_final:%d/%m/%Y} ({atraso} pregões atrás)")
    if escolhida.incerta and status == "ok":
        status = "alerta"
        mensagens.append("leitura incerta (" + ("data presumida" if "data" in escolhida.detalhe else "coluna por posição") + ")")
    if any("acima do limite" in m for m in mensagens) and status == "ok":
        status = "alerta"

    return Resultado(ind["id"], status, escolhida.valor, d_final, escolhida.fonte, escolhida.url,
                     escolhida.detalhe, mensagens, relatorio_fontes)
