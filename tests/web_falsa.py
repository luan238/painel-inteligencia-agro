"""Internet simulada para os testes (nenhum acesso real à rede).

As páginas imitam a ESTRUTURA típica dos sites (títulos + tabelas, RSS, Atom,
páginas de matéria com metadados), com valores FICTÍCIOS gerados por passeio
aleatório determinístico. Servem para testar o agente ponta a ponta.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from email.utils import format_datetime
from zoneinfo import ZoneInfo

from agente.calendario import eh_dia_util
from agente.numeros import fmt
from agente.rede import Resposta

BRT = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 11, 17, 19, 40, tzinfo=BRT)
HOJE = AGORA.date()
FERIADO_FRED = date(2026, 11, 11)      # dia sem cotação na série do FRED (vem como ".")

# (valor final, vol diária) — valores FICTÍCIOS para teste
BASES = {
    "ptax": (5.7324, 0.008), "selic": (13.75, 0.0), "wti": (90.40, 0.02), "brent": (97.80, 0.018),
    "soja_cbot": (1202.25, 0.011), "farelo": (318.50, 0.012), "oleo": (51.20, 0.015),
    "paranagua": (158.52, 0.006), "parana": (152.10, 0.006), "uberlandia": (147.89, 0.007),
    "milho_cbot": (445.25, 0.012), "campinas": (66.77, 0.006), "trigo_cbot": (596.50, 0.014),
    "trigo_pr": (1572.66, 0.004), "trigo_rs": (1454.93, 0.005), "algodao_ice": (78.36, 0.013),
    "algodao_cepea": (410.04, 0.006), "caroco_mt": (695.36, 0.01), "caroco_ba": (983.33, 0.008),
    "cafe_ny": (279.75, 0.018), "robusta": (4285.0, 0.015), "cafe_cepea": (1611.14, 0.01),
    "manhuacu": (1586.00, 0.011), "boi": (392.70, 0.004), "dol": (5761.5, 0.008), "ccm1": (66.88, 0.007),
    "ccm2": (71.35, 0.007), "bgi": (407.00, 0.005), "sjc": (26.34, 0.01), "rosario": (445000.0, 0.012),
    "icf": (523.40, 0.018), "cnl": (1385.00, 0.015),
}


def dias_uteis(n: int, ate: date = HOJE) -> list[date]:
    dias, d = [], ate
    while len(dias) < n:
        if eh_dia_util(d):
            dias.append(d)
        d -= timedelta(days=1)
    return sorted(dias)


def serie(nome: str, n: int = 45) -> dict[date, float]:
    """Passeio aleatório determinístico que TERMINA no valor de BASES."""
    final, vol = BASES[nome]
    rnd = random.Random(nome)
    dias = dias_uteis(n)
    valores = [final]
    for _ in dias[1:]:
        valores.append(valores[-1] / (1 + rnd.gauss(0.0004, vol)))
    valores.reverse()
    return {d: v for d, v in zip(dias, valores)}


def _cot(titulo: str, cab: list[str], linhas: list[list[str]], data: date = HOJE) -> str:
    th = "".join(f"<th>{c}</th>" for c in cab)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in linhas)
    return (f'<div class="cotacao"><div class="info"><h2>{titulo}</h2>'
            f'<div class="fechamento">Fechamento: {data:%d/%m/%Y}</div></div>'
            f'<table class="cot-fisicas"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')


def _serie_tab(titulo, nome, col, n=10):
    s = serie(nome)
    datas = sorted(s)[-n:][::-1]
    linhas = []
    for i, d in enumerate(datas):
        ant = s[sorted(s)[sorted(s).index(d) - 1]]
        linhas.append([f"{d:%d/%m/%Y}", fmt(s[d], 2), fmt((s[d] / ant - 1) * 100, 2)])
    return _cot(titulo, ["Data", col, "Variação (%)"], linhas)


def _ultimo(nome):
    s = serie(nome)
    return s[max(s)]


def _var(nome):
    s = serie(nome)
    d = sorted(s)
    return (s[d[-1]] / s[d[-2]] - 1) * 100


def pagina(*blocos) -> str:
    return "<html><head><meta charset='utf-8'><title>Cotações</title></head><body>" + "".join(blocos) + "</body></html>"


def _canal_rural(produto: str, titulo: str, linhas: list[tuple[str, str, str, float]], decoy: str, data: date = HOJE) -> str:
    """Imita a página de cotações do Canal Rural: lista 'Maiores altas' (com outro valor, de propósito)
    e a tabela 'Praças de …' com Praça | UF | Unidade | Preço | Variação."""
    trs = "".join(f"<tr><td><a href='?praca=x'>{praca}</a></td><td>{uf}</td><td>{un}</td><td>R$ {fmt(v, 2)}</td>"
                  f"<td>+0,50% alta de 0,50%</td></tr>" for praca, uf, un, v in linhas)
    return pagina(
        f"<h1>Cotação do {produto}</h1><section><h3>Maiores altas</h3><ul><li>{decoy} <span>+3,05%</span> "
        f"<span>R$ 999,00</span></li></ul></section>",
        f"<h2>{titulo}</h2><p>Fechamento de {data:%d/%m/%Y}</p>",
        "<table><thead><tr><th>Praça</th><th>UF</th><th>Unidade</th><th>Preço</th><th>Variação</th></tr></thead>"
        f"<tbody>{trs}</tbody></table><p>Fonte: CMA · Atualizado em {data:%d/%m/%Y} 15:27</p>")


def _bcr_chicago() -> str:
    """Imita 'Precios Chicago/Kansas' da BCR como o robô lê: cabeçalho só com o título e a data,
    13 colunas (posição + preço e variação de 6 produtos), '-' ou 0,00 = sem contrato."""
    soja_t = _ultimo("soja_cbot") / 100 / 0.0272155
    milho_t = _ultimo("milho_cbot") / 100 / 0.0254012
    trigo_t = _ultimo("trigo_cbot") / 100 / 0.0272155
    oleo_t = _ultimo("oleo") / 0.0453592
    farelo_t = _ultimo("farelo") / 0.90718474
    linhas = [
        ["Dic-26", fmt(trigo_t, 2), "2,94", "232,59", "5,14", fmt(milho_t, 2), "-0,79", "-", "-",
         fmt(oleo_t, 2), "-1,54", fmt(farelo_t, 2), "0,77"],
        ["Ene-27", "0,00", "0,00", "0,00", "0,00", "0,00", "0,00", fmt(soja_t, 2), "-1,29", "1.375,44", "-2,87", "367,28", "0,99"],
        ["Mar-27", "224,23", "3,40", "236,82", "5,60", "180,80", "0,20", "452,42", "-0,64", "1.387,35", "-3,09", "368,39", "1,87"],
    ]
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in linhas)
    return pagina("<h2>Cotizaciones Internacionales</h2><h3>Precios Chicago/Kansas</h3>",
                  "<table><thead><tr><th>Precios de cierre (U$S / TN)</th><th></th><th>17/11/2026</th></tr>"
                  "<tr><th></th><th></th></tr></thead>"
                  f"<tbody>{trs}"
                  "<tr><td>(1) Trigo duro colorado de invierno (Kansas)</td></tr></tbody></table>")


def boletim_b3_zip(dia: date = HOJE) -> bytes:
    """Imita o arquivo PRaammdd.zip da B3: zip com outro zip dentro e o XML BVBG.086 (Price Report)."""
    import io
    import zipfile
    itens = [("BGIX26", "bgi"), ("BGIZ26", None), ("CCMX26", "ccm1"), ("CCMF27", "ccm2"), ("DOLZ26", "dol"),
             ("DOLF27", None), ("SJCF27", "sjc"), ("CCMF27C070", None), ("PETR4", None),
             ("ICFH27", None), ("ICFZ26", "icf"), ("CNLF27", "cnl"), ("CNLH27", None)]
    rel = ""
    for ticker, nome in itens:
        v = _ultimo(nome) if nome else 1.0
        rel += (f"<PricRpt><TradDt><Dt>{dia:%Y-%m-%d}</Dt></TradDt><SctyId><TckrSymb>{ticker}</TckrSymb></SctyId>"
                f"<FinInstrmAttrbts><LastPric>{v * 1.001:.3f}</LastPric><AdjstdQt>{v:.3f}</AdjstdQt>"
                f"<PrvsAdjstdQt>{v * 0.998:.3f}</PrvsAdjstdQt></FinInstrmAttrbts></PricRpt>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?><Document xmlns="urn:bvmf.052.01.xsd"><BizGrp>'
           f'<Document xmlns="urn:bvmf.217.01.xsd">{rel}</Document></BizGrp></Document>').encode()
    interno = io.BytesIO()
    with zipfile.ZipFile(interno, "w") as z:
        z.writestr(f"BVBG.086.01_BV000328{dia:%Y%m%d}0328000001.xml", xml)
    externo = io.BytesIO()
    with zipfile.ZipFile(externo, "w") as z:
        z.writestr(f"PR{dia:%y%m%d}.zip", interno.getvalue())
    return externo.getvalue()


def paginas_cotacoes() -> dict[str, str]:
    cr = "https://www.canalrural.com.br/cotacoes/"
    p = {}
    sc = "saca de 60 kg"
    p[cr + "soja/"] = _canal_rural("soja", "Praças de Soja", [
        ("Sorriso", "MT", sc, 136.0), ("Paranaguá", "PR", sc, _ultimo("paranagua")),
        ("Cascavel", "PR", sc, _ultimo("parana")), ("Paranaguá (PRI)", "PR", sc, 141.0)], "Paranaguá · PR")
    p[cr + "milho/"] = _canal_rural("milho", "Praças de Milho", [
        ("Campinas", "SP", sc, _ultimo("campinas")), ("CIF · Santos", "SP", sc, 71.0)], "Campinas · SP")
    p[cr + "trigo/"] = _canal_rural("trigo", "Praças de Trigo", [
        ("FOB · Ponta Grossa", "PR", "tonelada", _ultimo("trigo_pr")),
        ("CIF · Porto Alegre", "RS", "tonelada", _ultimo("trigo_rs"))], "Ponta Grossa · PR")
    p[cr + "algodao/"] = _canal_rural("algodão", "Praças de Algodão", [
        ("Em pluma · Rondonópolis", "MT", "libra-peso", _ultimo("algodao_cepea") / 100),
        ("Em pluma · Barreiras", "BA", "libra-peso", 3.98)], "Rondonópolis · MT")
    p[cr + "cafe/"] = _canal_rural("café", "Praças de Café", [
        ("Arábica · Sul de Minas", "MG", sc, _ultimo("cafe_cepea")),
        ("Conilon · Vitória", "ES", sc, 1610.0)], "Sul de Minas · MG")
    p[cr + "boi/"] = _canal_rural("boi gordo", "Praças de Boi gordo", [
        ("São Paulo", "SP", "arroba", _ultimo("boi")), ("Cuiabá", "MT", "arroba", 375.0),
        ("Indsaf Boi SP AP · São Paulo", "SP", "—", 397.82)], "São Paulo · SP")
    p["https://www.bcr.com.ar/es/mercados/mercado-de-granos/cotizaciones/cotizaciones-internacionales-1"] = _bcr_chicago()
    p["https://www.agrolink.com.br/cotacoes/cafe-arabica-bebida-dura-tipo-6-safra-nova-sc-60kg"] = pagina(
        "<h1>Preço de Café Arábica Bebida Dura Tipo 6 Sc 60Kg</h1>",
        "<table><thead><tr><th>Favorito</th><th>Praça</th><th>Preço (R$)</th><th>Variação</th><th>Atualização</th>"
        f"<th>Freq.</th><th>Ver</th></tr></thead><tbody><tr><td colspan='7'><b>{HOJE:%d/%m/%Y}</b></td></tr>"
        f"<tr><td></td><td>Manhuaçu (MG)</td><td>{fmt(_ultimo('manhuacu'), 2)}</td><td>▲ 0,1%</td><td>{HOJE:%d/%m/%y}</td>"
        "<td>Diário</td><td>Histórico</td></tr><tr><td></td><td>Varginha (MG)</td><td>1.660,00</td><td>▲ 0,6%</td>"
        f"<td>{HOJE:%d/%m/%y}</td><td>Diário</td><td>Histórico</td></tr></tbody></table>")
    du = dias_uteis(4)
    grupos = ""
    for d in du[::-1]:
        grupos += (f'<tr><td colspan="7"><b>{d:%d/%m/%Y}</b></td></tr>'
                   f'<tr><td><i class="fav"></i></td><td>Barreiras (BA)</td><td>{fmt(_ultimo("caroco_ba") if d == HOJE else 966.67, 2)}</td>'
                   f'<td>▲ 0,7%</td><td>{d:%d/%m/%y}</td><td>Diário</td><td><a href="#">Histórico</a></td></tr>'
                   f'<tr><td><i class="fav"></i></td><td>Cuiabá (MT)</td><td>{fmt(_ultimo("caroco_mt"), 2)}</td>'
                   f'<td>estável</td><td>{du[1]:%d/%m/%y}</td><td>Diário</td><td><a href="#">Histórico</a></td></tr>')
    p["https://www.agrolink.com.br/cotacoes/algodao-em-caroco-1ton"] = pagina(
        "<h1>Preço de Algodão em Caroço 1ton</h1><p>Atualizado até as 18h30 (horário de Brasília)</p>",
        "<table><thead><tr><th>Favorito</th><th>Praça</th><th>Preço (R$)</th><th>Variação</th><th>Atualização</th>"
        f"<th>Freq.</th><th>Ver</th></tr></thead><tbody>{grupos}</tbody></table>")
    p["https://www.agrolink.com.br/regional/mg/uberlandia/cotacoes"] = pagina(
        "<h1>Cotações — Uberlândia (MG)</h1>",
        "<table><thead><tr><th>Produto</th><th>Local</th><th>Preço (R$)</th><th>Última Atualização</th><th>Freq.</th>"
        "</tr></thead><tbody><tr><td>Boi Gordo 15Kg</td><td>Uberlândia (MG)</td><td>380,00</td><td>17/11/2026</td><td>Diário</td></tr>"
        f"<tr><td>Soja em Grão Sc 60Kg</td><td>Uberlândia (MG)</td><td>{fmt(_ultimo('uberlandia'), 2)}</td>"
        "<td>17/11/2026</td><td>Diário</td></tr></tbody></table>")
    dr = dias_uteis(5)[::-1]
    cab = "".join(f"<th>{d:%d/%m/%Y}</th>" for d in dr)
    soja = "".join(f"<td>$ {fmt(_ultimo('rosario') if i == 0 else 550000.0, 2)}</td>" for i in range(5))
    p["https://www.bcr.com.ar/es/mercados/mercado-de-granos/cotizaciones/cotizaciones-locales-0"] = pagina(
        "<h2>Precios Cámara Arbitral de Cereales de Rosario</h2><p>(Pesos por Tn)</p>",
        f"<table><thead><tr><th>Fecha Negociación</th><th>Trading date</th>{cab}</tr></thead><tbody>"
        "<tr><td>Trigo</td><td>Wheat</td>" + "<td>$ 293.040,00</td>" * 5 + "</tr>"
        f"<tr><td>Soja</td><td>Soybean</td>{soja}</tr>"
        "<tr><td>Girasol</td><td>Sunseed</td>" + "<td>S/C</td>" * 5 + "</tr></tbody></table>")
    return p


def paginas_legado() -> dict[str, str]:
    """Leiautes antigos (Notícias Agrícolas e página 'Ajustes do Pregão' da B3), mantidos só para
    testar os coletores genéricos de tabela; os sites reais deixaram de atender o robô."""
    p = {}
    p["na_soja"] = pagina(
        _serie_tab("Indicador da Soja Cepea/Esalq - Paranaguá", "paranagua", "À vista R$"),
        _serie_tab("Indicador da Soja Cepea/Esalq - Paraná", "parana", "À vista R$"),
        _cot("Soja - Mercado Físico (Sindicatos e Cooperativas)", ["Praça", "Preço (R$/sc)", "Variação (%)"],
             [["Rio Verde/GO", "139,00", "+0,72"], ["Uberlândia/MG", fmt(_ultimo("uberlandia"), 2), fmt(_var("uberlandia"), 2)],
              ["Sorriso/MT", "131,50", "-0,38"]]),
        _cot("Soja - Bolsa de Chicago (CME Group)", ["Contrato", "Fechamento (US$ cents/bu)", "Variação (cents)"],
             [["Jan/27", fmt(_ultimo("soja_cbot"), 2), "-11,75"], ["Mar/27", "1.208,25", "+2,00"]]),
    )
    linhas_b3 = [("BGI - Boi gordo", "X26", "bgi"), ("", "Z26", None), ("CCM - Milho", "X26", "ccm1"),
                 ("", "F27", "ccm2"), ("DOL - Dólar comercial", "Z26", "dol"), ("", "F27", None),
                 ("SJC - Soja CME", "F27", "sjc")]
    trs = ""
    for merc, venc, nome in linhas_b3:
        v = _ultimo(nome) if nome else 1.0
        trs += f"<tr><td>{merc}</td><td>{venc}</td><td>{fmt(v * 0.998, 3)}</td><td>{fmt(v, 3)}</td><td>0,1</td><td>10,00</td></tr>"
    p["b3_ajustes"] = pagina(
        "<p>Atualizado em : 17/11/2026</p>",
        "<table id='tblDadosAjustes'><thead><tr><th>Mercadoria</th><th>Vencimento</th><th>Preço de ajuste anterior</th>"
        "<th>Preço de ajuste Atual</th><th>Variação</th><th>Valor do ajuste por contrato (R$)</th></tr></thead>"
        f"<tbody>{trs}</tbody></table>")
    return p


def _rss(itens: list[tuple[str, str, datetime, str]]) -> str:
    corpo = "".join(f"<item><title>{t}</title><link>{u}</link><pubDate>{format_datetime(d)}</pubDate>"
                    f"<description><![CDATA[<p>{r}</p>]]></description></item>" for t, u, d, r in itens)
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Feed</title>{corpo}</channel></rss>'


def paginas_noticias() -> dict[str, str]:
    h = lambda horas: AGORA - timedelta(hours=horas)  # noqa: E731
    na = "https://www.noticiasagricolas.com.br"
    p = {}
    p[na + "/noticias/"] = ('<html><head><link rel="alternate" type="application/rss+xml" href="/rss/noticias.xml">'
                           '</head><body>Notícias</body></html>')
    p[na + "/rss/noticias.xml"] = _rss([
        ("Soja recua em Chicago com previsão de safra recorde no Brasil", na + "/noticias/soja/431001-soja-recua-em-chicago",
         h(3), "Contratos de janeiro caíram 11,75 cents. Consultoria estima safra brasileira em 184,95 milhões de toneladas."),
        ("Importações de soja pela China em 2026/27 estimadas em 110 mi t, diz adido do USDA",
         na + "/noticias/soja/431002-china-110-mi-t", h(5), "Adido do USDA em Pequim projeta 110 milhões de toneladas."),
        ("Milho sobe em Chicago com avanço da produção de etanol nos EUA", na + "/noticias/milho/431003-milho-etanol",
         h(4), "Produção semanal de etanol subiu para 1,12 milhão de barris por dia."),
        ("Dólar fecha em alta com payroll forte nos EUA e cautela fiscal", na + "/noticias/politica-economia/431004-dolar",
         h(2), "A moeda americana subiu 0,44% no mercado à vista."),
        ("Café arábica recua em Nova York com perspectiva de exportações maiores", na + "/noticias/cafe/431005-cafe-ny",
         h(6), "Exportações brasileiras de café devem crescer 8% no ano-safra."),
        ("Boi gordo renova recorde nominal no indicador paulista", na + "/noticias/boi/431006-boi-recorde",
         h(7), "Escalas de abate curtas sustentam a arroba; China lidera compras."),
        ("Algodão sobe mais de 1,5% em Nova York com fundos comprando", na + "/noticias/algodao/431007-algodao-ny",
         h(8), "Exportações de algodão do Brasil faturaram 25,3% a mais em outubro."),
        ("Trigo: baixa oferta de grão de qualidade sustenta preços no Paraná", na + "/noticias/trigo/431008-trigo-pr",
         h(9), "Moinhos recorrem à importação; chuvas afetaram qualidade no Sul."),
        ("Petróleo cai com expectativa de acordo no Oriente Médio", na + "/noticias/petroleo/431009-petroleo",
         h(5), "Brent e WTI recuaram após sinais de negociação diplomática."),
        ("Notícia antiga de soja fora da janela", na + "/noticias/soja/420000-antiga", h(24 * 9), "velha"),
    ])
    p["https://www.canalrural.com.br/"] = "<html><head><title>Canal Rural</title></head><body>sem link de feed</body></html>"
    p["https://www.canalrural.com.br/feed/"] = _rss([
        ("Plantio de soja em Mato Grosso chega a 96% da área prevista", "https://www.canalrural.com.br/agricultura/plantio-soja-mt-96",
         h(10), "Imea aponta plantio em 96,07% da área de soja no estado."),
        ("Frigoríficos aceleram abates para atender cota da China", "https://www.canalrural.com.br/pecuaria/frigorificos-cota-china",
         h(12), "Cota chinesa de 1,1 milhão de toneladas de carne bovina reabre em janeiro."),
    ])
    p["https://www.agrolink.com.br/noticias/"] = (
        '<html><body><h1>Notícias</h1>'
        '<a href="/noticias/fertilizantes-importacao-acelera-em-outubro_521001.html">Importação de fertilizantes acelera em outubro e soma 4,26 milhões de t</a>'
        '<a href="/noticias/cafe-manhuacu-mantem-precos-firmes_521002.html">Café: praça de Manhuaçu mantém preços firmes no físico</a>'
        '<a href="/tag/soja">Tag soja</a><a href="/contato">Fale conosco agora mesmo com a gente</a></body></html>')
    p["https://www.agrolink.com.br/noticias/fertilizantes-importacao-acelera-em-outubro_521001.html"] = (
        '<html><head><meta property="og:title" content="Importação de fertilizantes acelera em outubro e soma 4,26 milhões de t">'
        f'<meta property="article:published_time" content="{h(20).isoformat()}">'
        '<meta property="og:description" content="Importações de fertilizantes somaram 4,26 milhões de toneladas em outubro, alta de 2,7% na média diária."></head>'
        '<body><article><p>As importações brasileiras de fertilizantes aceleraram na reta final de outubro, segundo a Secex.</p></article></body></html>')
    p["https://www.agrolink.com.br/noticias/cafe-manhuacu-mantem-precos-firmes_521002.html"] = (
        '<html><head><meta property="og:title" content="Café: praça de Manhuaçu mantém preços firmes no físico">'
        f'<script type="application/ld+json">{json.dumps({"@type": "NewsArticle", "datePublished": h(11).isoformat()})}</script>'
        '</head><body><article><p>Os preços do café arábica tipo 6 seguiram firmes nas Matas de Minas nesta terça-feira.</p></article></body></html>')
    p["https://www.world-grain.com/"] = ('<html><head><link rel="alternate" type="application/atom+xml" href="https://www.world-grain.com/atom.xml">'
                                          '</head><body></body></html>')
    p["https://www.world-grain.com/atom.xml"] = (
        '<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>World Grain</title>'
        f'<entry><title>US soybean export sales top 1.2 million tonnes</title><link href="https://www.world-grain.com/articles/23001-us-soybean-export-sales"/>'
        f'<updated>{h(14).astimezone(ZoneInfo("UTC")).isoformat()}</updated><summary>Net sales of 1,234,500 tonnes for 2026/27, up 12.5% from the prior week.</summary></entry>'
        '</feed>')
    return p


class WebFalsa:
    """Transporte para agente.rede.definir_transporte()."""

    def __init__(self, falhar_tudo: bool = False):
        self.paginas = {**paginas_cotacoes(), **paginas_noticias()}
        self.boletim_b3 = boletim_b3_zip()
        self.falhar_tudo = falhar_tudo
        self.acessos: list[str] = []
        ptax = serie("ptax")
        self.ptax_json = json.dumps({"value": [
            {"cotacaoCompra": round(v - 0.0006, 4), "cotacaoVenda": round(v, 4), "dataHoraCotacao": f"{d} 13:05:11.123"}
            for d, v in ptax.items()]})
        self.selic_json = json.dumps([{"data": f"{d:%d/%m/%Y}", "valor": "13.75"} for d in dias_uteis(30)]
                                     + [{"data": "09/12/2026", "valor": "13.75"}])

    def __call__(self, url, metodo, dados, headers):
        self.acessos.append(url)
        if self.falhar_tudo:
            return Resposta(url, 503, b"indisponivel")
        if url.endswith("/robots.txt"):
            if "reuters.com" in url:
                return Resposta(url, 200, b"User-agent: *\nDisallow: /")
            return Resposta(url, 200, b"User-agent: *\nAllow: /")
        if "bloomberg.com" in url or "noticiasagricolas.com.br/cotacoes" in url:    # como os sites reais
            return Resposta(url, 403, b"forbidden")
        if "b3.com.br/pesquisapregao/download" in url:
            if url.endswith(f"PR{HOJE:%y%m%d}.zip"):
                return Resposta(url, 200, self.boletim_b3, headers={"Content-Type": "application/zip"})
            return Resposta(url, 200, b"<html>arquivo indisponivel</html>")
        if "fred.stlouisfed.org/graph/fredgraph.csv" in url:
            cod = url.split("id=")[-1]
            nome = "wti" if cod == "DCOILWTICO" else "brent"
            linhas = [f"observation_date,{cod}"] + [f"{d:%Y-%m-%d},{'.' if d == FERIADO_FRED else f'{v:.2f}'}"
                                                    for d, v in sorted(serie(nome).items()) if d <= HOJE - timedelta(days=2)]
            return Resposta(url, 200, ("\n".join(linhas) + "\n").encode(), encoding="utf-8")
        if "api.eia.gov" in url:
            nome = "wti" if "RWTC" in url else "brent"
            dados = [{"period": f"{d:%Y-%m-%d}", "value": round(v, 2)} for d, v in sorted(serie(nome).items())[-30:]
                     if d <= HOJE - timedelta(days=2)]
            return Resposta(url, 200, json.dumps({"response": {"data": dados[::-1]}}).encode(), encoding="utf-8")
        if "olinda.bcb.gov.br" in url and "CotacaoDolarPeriodo" in url:
            return Resposta(url, 200, self.ptax_json.encode(), encoding="utf-8")
        if "api.bcb.gov.br" in url and "sgs.432" in url:
            return Resposta(url, 200, self.selic_json.encode(), encoding="utf-8")
        if url in self.paginas:
            return Resposta(url, 200, self.paginas[url].encode("utf-8"), encoding="utf-8")
        return Resposta(url, 404, b"nao encontrado")
