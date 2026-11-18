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


def paginas_cotacoes() -> dict[str, str]:
    na = "https://www.noticiasagricolas.com.br/cotacoes/"
    p = {}
    p[na + "soja"] = pagina(
        _serie_tab("Indicador da Soja Cepea/Esalq - Paranaguá", "paranagua", "À vista R$"),
        _serie_tab("Indicador da Soja Cepea/Esalq - Paraná", "parana", "À vista R$"),
        _cot("Soja - Mercado Físico (Sindicatos e Cooperativas)", ["Praça", "Preço (R$/sc)", "Variação (%)"],
             [["Rio Verde/GO", "139,00", "+0,72"], ["Uberlândia/MG", fmt(_ultimo("uberlandia"), 2), fmt(_var("uberlandia"), 2)],
              ["Sorriso/MT", "131,50", "-0,38"]]),
        _cot("Soja - Bolsa de Chicago (CME Group)", ["Contrato", "Fechamento (US$ cents/bu)", "Variação (cents)"],
             [["Jan/27", fmt(_ultimo("soja_cbot"), 2), "-11,75"], ["Mar/27", "1.208,25", "+2,00"]]),
        _cot("Farelo de Soja - Bolsa de Chicago", ["Contrato", "Fechamento (US$/t curta)", "Variação"],
             [["Dez/26", fmt(_ultimo("farelo"), 2), "+0,70"]]),
        _cot("Óleo de Soja - Bolsa de Chicago", ["Contrato", "Fechamento (cents/lb)", "Variação"],
             [["Dez/26", fmt(_ultimo("oleo"), 2), "+0,35"]]),
    )
    p[na + "milho"] = pagina(
        _serie_tab("Indicador do Milho Esalq/B3 - Campinas", "campinas", "À vista R$"),
        _cot("Milho - Bolsa de Chicago (CME Group)", ["Contrato", "Fechamento (US$ cents/bu)", "Variação"],
             [["Dez/26", fmt(_ultimo("milho_cbot"), 2), "+1,50"]]),
    )
    p[na + "trigo"] = pagina(
        _cot("Preço Médio do Trigo Cepea/Esalq", ["Estado", "Valor (R$/t)", "Variação (%)"],
             [["Paraná", fmt(_ultimo("trigo_pr"), 2), fmt(_var("trigo_pr"), 2)],
              ["Rio Grande do Sul", fmt(_ultimo("trigo_rs"), 2), fmt(_var("trigo_rs"), 2)]]),
        _cot("Trigo - Bolsa de Chicago (CME Group)", ["Contrato", "Fechamento (US$ cents/bu)", "Variação"],
             [["Dez/26", fmt(_ultimo("trigo_cbot"), 2), "-3,25"]]),
    )
    p[na + "algodao"] = pagina(
        _cot("Algodão - Bolsa de Nova York (ICE Futures)", ["Contrato", "Fechamento (cents/lb)", "Variação"],
             [["Dez/26", fmt(_ultimo("algodao_ice"), 2), "+1,32"]]),
        _serie_tab("Indicador do Algodão em Pluma Cepea/Esalq", "algodao_cepea", "Valor (centavos de R$/lb)"),
        _cot("Caroço de Algodão", ["Praça", "Preço (R$/t)", "Variação (%)"],
             [["Mato Grosso", fmt(_ultimo("caroco_mt"), 2), fmt(_var("caroco_mt"), 2)],
              ["Oeste da Bahia", fmt(_ultimo("caroco_ba"), 2), fmt(_var("caroco_ba"), 2)]]),
    )
    p[na + "cafe"] = pagina(
        _cot("Café Arábica - Bolsa de Nova York (ICE Futures)", ["Contrato", "Fechamento (cents/lb)", "Variação"],
             [["Dez/26", fmt(_ultimo("cafe_ny"), 2), "-4,20"]]),
        _cot("Café Robusta - Bolsa de Londres (ICE Europe)", ["Contrato", "Fechamento (US$/t)", "Variação"],
             [["Jan/27", fmt(_ultimo("robusta"), 0), "+38"]]),
        _serie_tab("Indicador do Café Arábica Cepea/Esalq", "cafe_cepea", "À vista R$"),
        _cot("Café - Mercado Físico (Tipo 6, Bebida Dura)", ["Praça", "Preço (R$/sc)", "Variação (%)"],
             [["Guaxupé/MG", "1.702,00", "-1,73"], ["Manhuaçu/MG", fmt(_ultimo("manhuacu") + 2, 2), "+0,13"]]),
    )
    p[na + "boi-gordo"] = pagina(
        _serie_tab("Indicador do Boi Gordo Cepea/Esalq (Estado de São Paulo)", "boi", "À vista R$"),
        _cot("Boi Magro - São Paulo", ["Categoria", "Preço (R$/cab)", "Variação"], [["Boi magro", "5.467,50", "+0,30"]]),
    )
    p[na + "petroleo"] = pagina(
        _cot("Petróleo WTI - NYMEX", ["Contrato", "Fechamento (US$/barril)", "Variação"],
             [["Dez/26", fmt(_ultimo("wti"), 2), "+0,51"]]),
        _cot("Petróleo Brent - ICE Londres", ["Contrato", "Fechamento (US$/barril)", "Variação"],
             [["Jan/27", fmt(_ultimo("brent"), 2), "+0,42"]]),
    )
    p["https://www.agrolink.com.br/cotacoes/cafe-arabica-bebida-dura-tipo-6-safra-nova-sc-60kg"] = pagina(
        "<h1>Café Arábica Bebida Dura Tipo 6 — Saca 60 kg</h1><p>Atualizado em 17/11/2026</p>",
        "<table><thead><tr><th>Praça</th><th>Preço (R$)</th><th>Variação</th></tr></thead><tbody>"
        f"<tr><td>Manhuaçu/MG</td><td>{fmt(_ultimo('manhuacu'), 2)}</td><td>+0,10%</td></tr>"
        "<tr><td>Varginha/MG</td><td>1.660,00</td><td>+0,60%</td></tr></tbody></table>")
    p["https://www.agrolink.com.br/cotacoes/graos/soja"] = pagina(
        "<h1>Soja em grão — Saca 60 kg</h1><p>Atualizado em 17/11/2026</p>",
        "<table><thead><tr><th>Praça</th><th>Preço (R$)</th><th>Variação</th></tr></thead><tbody>"
        f"<tr><td>Uberlândia/MG</td><td>{fmt(_ultimo('uberlandia') * 1.001, 2)}</td><td>+0,50%</td></tr></tbody></table>")
    linhas_b3 = [("BGI - Boi gordo", "X26", "bgi"), ("", "Z26", None), ("CCM - Milho", "X26", "ccm1"),
                 ("", "F27", "ccm2"), ("DOL - Dólar comercial", "Z26", "dol"), ("", "F27", None),
                 ("SJC - Soja CME", "F27", "sjc")]
    trs = ""
    for merc, venc, nome in linhas_b3:
        v = _ultimo(nome) if nome else 1.0
        trs += f"<tr><td>{merc}</td><td>{venc}</td><td>{fmt(v * 0.998, 3)}</td><td>{fmt(v, 3)}</td><td>0,1</td><td>10,00</td></tr>"
    p["https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/lum-ajustes-do-pregao-ptBR.asp"] = pagina(
        "<p>Atualizado em : 17/11/2026</p>",
        "<table id='tblDadosAjustes'><thead><tr><th>Mercadoria</th><th>Vencimento</th><th>Preço de ajuste anterior</th>"
        "<th>Preço de ajuste Atual</th><th>Variação</th><th>Valor do ajuste por contrato (R$)</th></tr></thead>"
        f"<tbody>{trs}</tbody></table>")
    p["https://www.bcr.com.ar/es/mercados/mercado-de-granos/cotizaciones/cotizaciones-locales-0"] = pagina(
        "<h2>Precios Pizarra — Cámara Arbitral de Cereales de Rosario</h2><p>17/11/2026</p>",
        "<table><thead><tr><th>Producto</th><th>$/Tn</th><th>Var.</th></tr></thead><tbody>"
        f"<tr><td>Trigo</td><td>230.000,00</td><td>0</td></tr><tr><td>Soja</td><td>{fmt(_ultimo('rosario'), 2)}</td><td>+1.500</td></tr>"
        "</tbody></table>")
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
        if "bloomberg.com" in url:
            return Resposta(url, 403, b"forbidden")
        if "olinda.bcb.gov.br" in url and "CotacaoDolarPeriodo" in url:
            return Resposta(url, 200, self.ptax_json.encode(), encoding="utf-8")
        if "api.bcb.gov.br" in url and "sgs.432" in url:
            return Resposta(url, 200, self.selic_json.encode(), encoding="utf-8")
        if url in self.paginas:
            return Resposta(url, 200, self.paginas[url].encode("utf-8"), encoding="utf-8")
        return Resposta(url, 404, b"nao encontrado")
