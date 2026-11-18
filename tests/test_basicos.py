"""Números, calendário, verificador, validação e cálculos."""
from datetime import date

import pytest

from agente.analise import calcular_metricas, calcular_ndf, eixo_janela
from agente.calendario import dias_uteis_entre, eh_dia_util, feriados, inicio_da_semana, somar_dias_uteis
from agente.coletores.base import Observacao
from agente.historico import Historico
from agente.numeros import extrair_numeros, extrair_ordinais, fmt, fmt_pct, fmt_valor, ler_numero
from agente.validacao import Resultado, validar
from agente.verificador import Verificador


# ------------------------------------------------------------------ números
@pytest.mark.parametrize("texto,estilo,esperado", [
    ("1.611,06", "br", 1611.06), ("R$ 5,4564", "br", 5.4564), ("-0,58%", "br", -0.58), ("−2,9%", "br", -2.9),
    ("1,202.25", "en", 1202.25), ("12.0225", "br", 12.0225), ("5.500,00 pts", "br", 5500.0), ("1.553", "br", 1553.0),
    ("1,553", "en", 1553.0), ("4.725", "en", 4.725), ("US$ 318,50", "br", 318.5), ("445.000,00", "br", 445000.0),
])
def test_ler_numero(texto, estilo, esperado):
    assert ler_numero(texto, estilo) == pytest.approx(esperado)


def test_formatacao_brasileira():
    assert fmt(1611.06) == "1.611,06"
    assert fmt(5.4564, 4) == "5,4564"
    assert fmt_pct(-0.58) == "-0,58%" and fmt_pct(1.2) == "+1,20%"
    assert fmt_valor(158.52, "R$/sc") == "R$ 158,52/sc"
    assert fmt_valor(78.36, "¢/lb") == "78,36 ¢/lb"
    assert fmt_valor(13.75, "% a.a.") == "13,75% a.a."
    assert fmt_valor(-0.004, "R$") == "R$ 0,00"


def test_extracao_ignora_datas_horas_contratos_e_anos():
    texto = ("Soja caiu 0,58% para R$ 158,52/sc em 17/11/2026 às 16h38 (Jan/27, ZSF27) na safra 2026/27 "
             "e 26/27 [N3]; recorde desde 2014; 110 mi t")
    achados = [n.bruto for n in extrair_numeros(texto)]
    assert achados == ["0,58", "158,52", "110"]
    assert extrair_numeros("subiu 0,58% hoje")[0].eh_percentual


def test_ordinais():
    assert extrair_ordinais("é a 3ª queda seguida e o 2º pregão") == [(3, "queda"), (2, "preg")]


# --------------------------------------------------------------- calendário
def test_feriados_2026():
    f = feriados(2026)
    for d in (date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3), date(2026, 6, 4), date(2026, 11, 20)):
        assert d in f
    assert not eh_dia_util(date(2026, 11, 20)) and eh_dia_util(date(2026, 11, 17))


def test_dias_uteis_e_semana():
    assert dias_uteis_entre(date(2026, 11, 17), date(2026, 11, 30)) == 8
    assert somar_dias_uteis(date(2026, 11, 17), 5) == date(2026, 11, 25)
    assert inicio_da_semana(date(2026, 11, 17)) == date(2026, 11, 15)   # terça → domingo 15
    assert inicio_da_semana(date(2026, 11, 21)) == date(2026, 11, 15)   # sábado → mesma semana
    assert inicio_da_semana(date(2026, 11, 22)) == date(2026, 11, 15)   # domingo → semana que fechou


# --------------------------------------------------------------- verificador
def test_verificador_aceita_arredondamento_e_recusa_invencao():
    v = Verificador(numeros=[5.7324, -0.5812, 158.52], textos=[("China deve importar 110 milhões de t", "br"),
                                                              ("sales of 1,234,500 tonnes, up 12.5%", "en")],
                    ids_validos={"N1"}, sequencias=[3, -2])
    assert v.checar_texto("Dólar a R$ 5,73 (-0,58%) e soja a R$ 158,5; China 110 mi t, alta de 12,5% [N1]", "x") == []
    tipos = {p.tipo for p in v.checar_texto("Estoques em 999,37 mil t [N9] veja https://x.com", "x")}
    assert tipos == {"numero", "referencia", "url"}
    assert v.checar_texto("3ª alta seguida", "x") == []
    assert v.checar_texto("2ª queda seguida", "x") == []
    assert v.checar_texto("4ª alta seguida", "x")[0].tipo == "sequencia"
    assert v.checar_texto("entre 2 e 3 minutos", "x") == []          # inteiros pequenos são livres


# --------------------------------------------------------------- validação
IND = {"id": "soja_cbot", "nome": "Soja CBOT", "bloco": "complexo_soja", "unidade": "US$/bu", "casas": 4,
       "faixa": [6, 30], "fatores_aceitos": [1, 0.01], "var_max_dia_pct": 7, "defasagem_max_dias_uteis": 2}
HOJE = date(2026, 11, 17)


def _obs(valor, d=HOJE, fonte="A", prioridade=1):
    o = Observacao("soja_cbot", d, valor, fonte, "https://a.example/")
    o.prioridade = prioridade
    return o


def _hist(tmp_path, valores):
    h = Historico(tmp_path / "h.csv")
    for d, v in valores.items():
        h.registrar(_obs(v, d), "ok", 1)
    return h


def test_converte_centavos_e_aprova(tmp_path):
    r = validar(IND, [_obs(1202.25)], _hist(tmp_path, {date(2026, 11, 16): 12.10}), HOJE, [])
    assert r.status == "ok" and r.valor == pytest.approx(12.0225)


def test_rejeita_fora_da_faixa_e_usa_ultimo_valido(tmp_path):
    r = validar(IND, [_obs(99999)], _hist(tmp_path, {date(2026, 11, 16): 12.10}), HOJE, [])
    assert r.status == "desatualizado" and r.valor == 12.10 and r.data == date(2026, 11, 16)
    assert any("fora da faixa" in m for m in r.mensagens)


def test_salto_absurdo_rejeitado_e_salto_grande_alerta(tmp_path):
    h = _hist(tmp_path, {date(2026, 11, 16): 12.00})
    assert validar(IND, [_obs(18.0)], h, HOJE, []).status == "desatualizado"       # +50%: rejeitado
    r = validar(IND, [_obs(13.2)], _hist(tmp_path / "..", {date(2026, 11, 16): 12.00}), HOJE, [])
    assert r.status == "alerta" and r.valor == 13.2                                 # +10%: alerta


def test_divergencia_e_confirmacao_entre_fontes(tmp_path):
    r = validar(IND, [_obs(12.00, fonte="A"), _obs(12.60, fonte="B", prioridade=2)], _hist(tmp_path, {}), HOJE, [])
    assert r.status == "alerta" and r.fonte == "A" and "divergem" in r.mensagens[-1]
    r = validar(IND, [_obs(12.00, fonte="A"), _obs(12.01, fonte="B", prioridade=2)],
                _hist(tmp_path / "..", {}), HOJE, [])
    assert r.status == "ok" and "confirmado por 2 fontes" in r.mensagens[-1]


def test_dado_velho_e_data_futura(tmp_path):
    assert validar(IND, [_obs(12.0, date(2026, 11, 9))], _hist(tmp_path, {}), HOJE, []).status == "desatualizado"
    assert validar(IND, [_obs(12.0, date(2026, 11, 30))], _hist(tmp_path / "..", {}), HOJE, []).status == "indisponivel"


# ----------------------------------------------------------------- análise
def test_metricas_wtd_mtd_janela_sem_interpolar():
    ind = {**IND, "id": "x", "unidade": "R$/sc", "casas": 2}
    serie = {date(2026, 10, 30): 100.0, date(2026, 11, 13): 104.0, date(2026, 11, 16): 105.0, date(2026, 11, 17): 106.0}
    res = Resultado("x", "ok", 106.0, HOJE, "A", "https://a/")
    eixo = eixo_janela(HOJE, 8)
    m = calcular_metricas(ind, res, serie, HOJE, eixo, max_repetidos=2)
    assert m.var_dia_pct == pytest.approx(100 * (106 / 105 - 1))
    assert m.ref_semana == 104.0 and m.var_semana_pct == pytest.approx(100 * (106 / 104 - 1))
    assert m.ref_mes == 100.0 and m.var_mes_pct == pytest.approx(6.0)
    assert m.sequencia == 3                       # 100 → 104 → 105 → 106: três altas seguidas
    # 30/10 → só pode repetir até 2 pregões; depois fica em branco (None) até 13/11
    assert m.janela[-3:] == [104.0, 105.0, 106.0]
    assert None in m.janela and len(m.janela) == 8


def test_ndf_formula():
    r = calcular_ndf(5.0, 13.75, 4.8, 160, HOJE)
    esperado = 5.0 * (1.1375 ** (r["du"] / 252)) / (1 + 0.048 * 160 / 360)
    assert r["ndf"] == pytest.approx(esperado) and "NDF (160 dias)" in r["formula"]
