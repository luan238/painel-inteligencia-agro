"""Cálculos determinísticos: variações (dia, semana, mês), janela de pregões,
sequências, volatilidade, spreads e NDF. Tudo aqui é código — nada vem da IA."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from .calendario import (dia_util_anterior_ou_igual, dias_uteis_entre, inicio_da_semana,
                         ultimos_dias_uteis)
from .numeros import fmt


@dataclass
class Metricas:
    id: str
    nome: str
    nome_curto: str
    bloco: str
    unidade: str
    casas: int
    status: str
    valor: float | None = None
    data: date | None = None
    fonte: str = ""
    url: str = ""
    detalhe: str = ""
    mensagens: list = field(default_factory=list)
    anterior: float | None = None
    data_anterior: date | None = None
    var_dia_pct: float | None = None
    var_dia_abs: float | None = None
    ref_semana: float | None = None
    data_ref_semana: date | None = None
    var_semana_pct: float | None = None
    var_semana_abs: float | None = None
    ref_mes: float | None = None
    data_ref_mes: date | None = None
    var_mes_pct: float | None = None
    var_mes_abs: float | None = None
    sequencia: int = 0               # +3 = três altas seguidas; -2 = duas quedas seguidas
    vol_diaria: float | None = None  # desvio-padrão dos retornos log diários
    n_obs: int = 0
    janela: list = field(default_factory=list)
    preenchidos: int = 0
    minimo_janela: float | None = None
    maximo_janela: float | None = None

    @property
    def disponivel(self) -> bool:
        return self.valor is not None and self.status != "indisponivel"

    def como_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, date):
                d[k] = v.isoformat()
        return d


def _ultimo_antes(serie: dict, limite: date):
    datas = [d for d in serie if d < limite]
    return (max(datas), serie[max(datas)]) if datas else (None, None)


def _pct(atual, ref):
    return None if (atual is None or not ref) else (atual / ref - 1) * 100


def eixo_janela(hoje: date, n: int) -> list[date]:
    return ultimos_dias_uteis(dia_util_anterior_ou_igual(hoje), n)


def calcular_metricas(ind: dict, resultado, serie: dict, hoje: date, eixo: list[date],
                      max_repetidos: int = 2, janela_vol: int = 21) -> Metricas:
    m = Metricas(id=ind["id"], nome=ind["nome"], nome_curto=ind.get("nome_curto", ind["nome"]),
                 bloco=ind["bloco"], unidade=ind["unidade"], casas=ind.get("casas", 2),
                 status=resultado.status, valor=resultado.valor, data=resultado.data,
                 fonte=resultado.fonte, url=resultado.url, detalhe=resultado.detalhe,
                 mensagens=list(resultado.mensagens))
    if m.valor is None:
        m.janela = [None] * len(eixo)
        return m
    serie = {d: v for d, v in serie.items() if d <= m.data}
    serie[m.data] = m.valor
    datas = sorted(serie)
    m.n_obs = len(datas)

    m.data_anterior, m.anterior = _ultimo_antes(serie, m.data)
    m.var_dia_pct = _pct(m.valor, m.anterior)
    m.var_dia_abs = None if m.anterior is None else m.valor - m.anterior

    m.data_ref_semana, m.ref_semana = _ultimo_antes(serie, inicio_da_semana(hoje))
    m.var_semana_pct = _pct(m.valor, m.ref_semana)
    m.var_semana_abs = None if m.ref_semana is None else m.valor - m.ref_semana

    m.data_ref_mes, m.ref_mes = _ultimo_antes(serie, hoje.replace(day=1))
    m.var_mes_pct = _pct(m.valor, m.ref_mes)
    m.var_mes_abs = None if m.ref_mes is None else m.valor - m.ref_mes

    # sequência de altas/quedas consecutivas
    seq, sinal = 0, 0
    for a, b in zip(reversed(datas[:-1]), reversed(datas[1:])):
        dif = serie[b] - serie[a]
        s = (dif > 0) - (dif < 0)
        if s == 0 or (sinal and s != sinal):
            break
        sinal = s
        seq += 1
    m.sequencia = seq * sinal

    # volatilidade (desvio-padrão dos retornos log dos últimos pregões)
    recentes = datas[-(janela_vol + 1):]
    rets = [math.log(serie[b] / serie[a]) for a, b in zip(recentes[:-1], recentes[1:]) if serie[a] > 0 and serie[b] > 0]
    if len(rets) >= 5:
        media = sum(rets) / len(rets)
        m.vol_diaria = math.sqrt(sum((r - media) ** 2 for r in rets) / (len(rets) - 1))

    # janela alinhada ao calendário de pregões (repete o último preço por no máx. N pregões)
    valores = []
    for d in eixo:
        if d in serie:
            valores.append(round(serie[d], m.casas))
            continue
        d_ult, v_ult = _ultimo_antes(serie, d)
        if d_ult is not None and dias_uteis_entre(d_ult, d) <= max_repetidos:
            valores.append(round(v_ult, m.casas))
            m.preenchidos += 1
        else:
            valores.append(None)
    m.janela = valores
    reais = [v for v in valores if v is not None]
    if reais:
        m.minimo_janela, m.maximo_janela = min(reais), max(reais)
    return m


# ------------------------------------------------------------------- spreads
@dataclass
class Spread:
    id: str
    nome: str
    bloco: str
    unidade: str
    casas: int
    valor: float | None
    data: date | None
    composicao: str
    status: str


def calcular_spreads(cfg_spreads: list, metricas: dict) -> list[Spread]:
    saida = []
    for sp in cfg_spreads:
        a, b = metricas.get(sp["a"]), metricas.get(sp["b"])
        casas = sp.get("casas", 2)
        if not a or not b or not a.disponivel or not b.disponivel:
            saida.append(Spread(sp["id"], sp["nome"], sp["bloco"], sp["unidade"], casas, None, None,
                                "componentes indisponíveis", "indisponivel"))
            continue
        valor = a.valor - b.valor if sp.get("operacao", "diferenca") == "diferenca" else a.valor / b.valor
        status = "ok" if a.status == b.status == "ok" else "alerta"
        datas = f"{a.data:%d/%m}" if a.data == b.data else f"{a.data:%d/%m} vs {b.data:%d/%m}"
        saida.append(Spread(sp["id"], sp["nome"], sp["bloco"], sp["unidade"], casas, valor, min(a.data, b.data),
                            f"{a.nome_curto} {fmt(a.valor, a.casas)} − {b.nome_curto} {fmt(b.valor, b.casas)} ({datas})",
                            status))
    return saida


# ----------------------------------------------------------------------- NDF
def calcular_ndf(spot: float, taxa_brl_aa: float, cupom_aa: float, dias_corridos: int, hoje: date) -> dict:
    """Forward teórico: F = S × (1+DI)^(du/252) ÷ (1 + cupom × dc/360)."""
    du = dias_uteis_entre(hoje, hoje + timedelta(days=dias_corridos))
    fator_brl = (1 + taxa_brl_aa / 100) ** (du / 252)
    fator_usd = 1 + (cupom_aa / 100) * (dias_corridos / 360)
    ndf = spot * fator_brl / fator_usd
    formula = (f"NDF ({dias_corridos} dias) = {fmt(spot, 4)} × (1 + {fmt(taxa_brl_aa / 100, 4)})^({du}/252) "
               f"÷ [1 + {fmt(cupom_aa / 100, 4)} × ({dias_corridos}/360)] = R$ {fmt(ndf, 4)}")
    return {"spot": spot, "taxa_brl_aa": taxa_brl_aa, "cupom_aa": cupom_aa, "du": du, "dc": dias_corridos,
            "ndf": ndf, "pontos_forward": ndf - spot, "formula": formula}
