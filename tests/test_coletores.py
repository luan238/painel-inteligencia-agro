"""Coletores de cotações e de notícias (sem internet)."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from agente.coletores import b3_ajustes, b3_boletim, bcb, coletar_indicador, outros, tabela_html
from agente.coletores.noticias import (ColetorNoticias, descobrir_feed, ler_feed, links_de_materias,
                                       metadados_materia, selecionar)
from agente.rede import BloqueadoPorRobots, Cliente, Resposta
from web_falsa import AGORA, paginas_cotacoes, paginas_legado

HOJE = date(2026, 11, 17)
IND = {"id": "t", "nome": "teste", "unidade": "R$", "faixa": [0, 1e9]}


class ClienteFixo:
    def __init__(self, conteudo: str):
        self.conteudo = conteudo

    def obter(self, url, **kw):
        return Resposta(url, 200, self.conteudo.encode("utf-8"), encoding="utf-8")


def test_ptax_formato_real_da_api():
    # trecho real devolvido pela API PTAX do BCB em 17/11/2026
    real = {"value": [
        {"cotacaoCompra": 5.65120, "cotacaoVenda": 5.65180, "dataHoraCotacao": "2026-11-13 13:03:27.375047"},
        {"cotacaoCompra": 5.73180, "cotacaoVenda": 5.73240, "dataHoraCotacao": "2026-11-16 13:06:32.509132"}]}
    obs = bcb.coletar_ptax({"fonte": "Banco Central do Brasil"}, IND, ClienteFixo(json.dumps(real)), HOJE)
    assert [(o.data, o.valor) for o in obs] == [(date(2026, 11, 13), 5.6518), (date(2026, 11, 16), 5.7324)]
    assert obs[0].url.startswith("https://www.bcb.gov.br/")       # link público, não a API


def test_sgs_ignora_datas_futuras():
    dados = [{"data": "16/11/2026", "valor": "13.75"}, {"data": "09/12/2026", "valor": "13.75"}]
    obs = bcb.coletar_sgs({"serie": 432}, IND, ClienteFixo(json.dumps(dados)), HOJE)
    assert [o.data for o in obs] == [date(2026, 11, 16)]


def test_tabela_por_titulo_linha_e_coluna():
    html = paginas_legado()["na_soja"]
    # Paraná, mas NÃO Paranaguá
    obs = tabela_html.extrair(html, {"titulo_contem": ["soja", "paran"], "titulo_nao_contem": ["paranagu"],
                                     "coluna_valor": ["vista"], "coluna_data": ["data"]}, IND, HOJE)
    assert len(obs) == 10 and max(obs, key=lambda o: o.data).valor == pytest.approx(152.10)
    obs = tabela_html.extrair(html, {"titulo_contem": ["soja", "físico"], "linha_contem": ["uberl"],
                                     "coluna_valor": ["preço"]}, IND, HOJE)
    assert obs[0].valor == pytest.approx(147.89) and obs[0].data == HOJE and not obs[0].incerta
    obs = tabela_html.extrair(html, {"titulo_contem": ["soja", "chicago"], "titulo_nao_contem": ["farelo", "óleo"],
                                     "linha": 1, "coluna_valor": ["fechamento"]}, IND, HOJE)
    assert obs[0].valor == pytest.approx(1202.25) and "Jan/27" in obs[0].detalhe
    with pytest.raises(Exception, match="nenhuma tabela"):
        tabela_html.extrair(html, {"titulo_contem": ["inexistente"]}, IND, HOJE)


def test_b3_ajustes_mercadoria_e_vencimento():
    html = paginas_legado()["b3_ajustes"]
    c1 = b3_ajustes.extrair(html, {"mercadoria": "CCM", "vencimento": 1}, IND, HOJE)[0]
    c2 = b3_ajustes.extrair(html, {"mercadoria": "CCM", "vencimento": "F27"}, IND, HOJE)[0]
    assert c1.valor == pytest.approx(66.88) and c2.valor == pytest.approx(71.35) and c1.data == HOJE
    assert "X26" in c1.detalhe


def test_feeds_rss_e_atom():
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><item><title>Soja sobe</title>
      <link>https://a.com/n/1-soja-sobe-hoje</link><pubDate>Tue, 17 Nov 2026 18:00:00 -0300</pubDate>
      <description><![CDATA[<p>Texto <b>forte</b></p>]]></description></item></channel></rss>"""
    itens = ler_feed(rss)
    assert itens[0]["titulo"] == "Soja sobe" and itens[0]["resumo"] == "Texto forte"
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Corn</title>
      <link rel="alternate" href="https://b.com/corn-up-today-x"/><updated>2026-11-17T12:00:00Z</updated></entry></feed>"""
    assert ler_feed(atom)[0]["url"] == "https://b.com/corn-up-today-x"
    assert ler_feed(b"<html><body>nao e feed</body></html>") is None
    html = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'
    assert descobrir_feed(html, "https://c.com/noticias/") == "https://c.com/feed.xml"


def test_links_e_metadados_de_materias():
    html = ('<a href="/noticias/soja-bate-recorde-em-paranagua_1.html">Soja bate recorde em Paranaguá nesta terça</a>'
            '<a href="/tag/soja">Tag soja com texto longo o suficiente</a><a href="https://outro.com/x-y-z">Fora do domínio daqui</a>')
    links = links_de_materias(html, "https://www.site.com.br/noticias/", 10)
    assert links == [("https://www.site.com.br/noticias/soja-bate-recorde-em-paranagua_1.html",
                      "Soja bate recorde em Paranaguá nesta terça")]
    meta = metadados_materia('<meta property="og:title" content="Título"><meta property="article:published_time" '
                             'content="2026-11-17T10:00:00-03:00"><article><p>' + "x" * 80 + '</p></article>', timezone.utc)
    assert meta["titulo"] == "Título" and meta["data"].hour == 10


def test_coleta_de_noticias_respeita_robots_e_janela(cfg, web):
    cliente = Cliente(cfg.geral["coleta"])
    with pytest.raises(BloqueadoPorRobots):
        cliente.obter("https://www.reuters.com/markets/commodities/")
    col = ColetorNoticias(cfg, cliente, AGORA)
    noticias = col.coletar_fonte(cfg.fonte("Notícias Agrícolas"))
    assert len(noticias) == 9                                      # a matéria de 9 dias atrás ficou fora
    assert col.status[-1]["modo"] == "rss"
    noticias += col.coletar_fonte(cfg.fonte("Agrolink"))           # sem feed: lê a página e abre as matérias
    assert col.status[-1]["modo"] == "pagina" and col.status[-1]["itens_na_janela"] == 2
    col.coletar_fonte(cfg.fonte("Reuters Commodities"))
    assert col.status[-1]["status"] == "robots"
    por_bloco = selecionar(noticias, cfg.blocos, {"Notícias Agrícolas": 1, "Agrolink": 1}, 10, AGORA)
    soja = [n.titulo for n in por_bloco["complexo_soja"]]
    assert any("China" in t for t in soja) and not any("Boi" in t for t in soja)
    ids = [n.id for lista in por_bloco.values() for n in lista]
    assert all(i.startswith("N") for i in ids)


def test_site_sem_feed_e_lembrado(cfg, web):
    c1 = ColetorNoticias(cfg, Cliente(cfg.geral["coleta"]), AGORA)
    c1.coletar_fonte(cfg.fonte("Agrolink"))
    assert c1.feeds["Agrolink"] == "pagina"
    web.acessos.clear()
    c2 = ColetorNoticias(cfg, Cliente(cfg.geral["coleta"]), AGORA, c1.feeds)
    assert len(c2.coletar_fonte(cfg.fonte("Agrolink"))) == 2
    assert not any(u.endswith(("/feed/", "/rss", "/rss.xml", "/feed.xml")) for u in web.acessos)


# ------------------------------------------------------------ fontes novas (18/11/2026)
def _fontes_reais(ind_id):
    """A configuração DE VERDADE do repositório: o teste falha se o arquivo for mexido sem querer."""
    import yaml
    from conftest import RAIZ
    dados = yaml.safe_load((RAIZ / "config" / "indicadores.yaml").read_text(encoding="utf-8"))
    return next(i for i in dados["indicadores"] if i["id"] == ind_id)


def test_canal_rural_praca_certa_e_nao_a_lista_de_altas():
    from web_falsa import _ultimo
    paginas = paginas_cotacoes()
    casos = [("soja_paranagua", "soja", _ultimo("paranagua")), ("soja_parana", "soja", _ultimo("parana")),
             ("milho_campinas", "milho", _ultimo("campinas")), ("trigo_parana", "trigo", _ultimo("trigo_pr")),
             ("trigo_rs", "trigo", _ultimo("trigo_rs")), ("cafe_arabica_cepea", "cafe", _ultimo("cafe_cepea")),
             ("boi_gordo_cepea", "boi", _ultimo("boi")), ("algodao_cepea", "algodao", _ultimo("algodao_cepea") / 100)]
    for ind_id, pagina_cr, esperado in casos:
        fonte = _fontes_reais(ind_id)["fontes"][0]
        html = paginas[f"https://www.canalrural.com.br/cotacoes/{pagina_cr}/"]
        o = outros.coletar_regex(fonte, {"id": ind_id}, ClienteFixo(html), HOJE)[0]
        assert o.valor == pytest.approx(round(esperado, 2)), ind_id      # nunca o 999,00 da lista "Maiores altas"
        assert o.data == HOJE and not o.incerta, ind_id


def test_bcr_chicago_primeira_posicao_com_valor_e_conversao(cfg):
    from web_falsa import _ultimo
    html = paginas_cotacoes()["https://www.bcr.com.ar/es/mercados/mercado-de-granos/cotizaciones/cotizaciones-internacionales-1"]

    class Cli(ClienteFixo):
        log = []
    for ind_id, base, casas in (("soja_cbot", _ultimo("soja_cbot") / 100, 3), ("milho_cbot", _ultimo("milho_cbot") / 100, 3),
                                ("trigo_cbot", _ultimo("trigo_cbot") / 100, 3), ("oleo_soja_cbot", _ultimo("oleo"), 2),
                                ("farelo_cbot", _ultimo("farelo"), 1)):
        ind = _fontes_reais(ind_id)
        obs, rel = coletar_indicador(ind, cfg, Cli(html), HOJE)
        assert rel[0]["status"] == "ok", rel
        assert obs[0].valor == pytest.approx(base, abs=10 ** -casas), ind_id
        assert "convertido de US$/t" in obs[0].detalhe and obs[0].data == HOJE and not obs[0].incerta
    soja = coletar_indicador(_fontes_reais("soja_cbot"), cfg, Cli(html), HOJE)[0][0]
    assert "Ene-27" in soja.detalhe                       # Dic-26 tem 0,00 na soja: pula para a 1ª posição cotada


def test_boletim_oficial_da_b3_vencimentos_e_dia_anterior():
    from web_falsa import _ultimo, boletim_b3_zip

    class Cli:
        def __init__(self):
            self.urls = []

        def obter(self, url, **kw):
            self.urls.append(url)
            if url.endswith("PR261117.zip"):
                return Resposta(url, 200, boletim_b3_zip())
            return Resposta(url, 200, b"<html>arquivo indisponivel</html>")

    cli = Cli()
    ccm1 = b3_boletim.coletar({"mercadoria": "CCM", "vencimento": 1}, IND, cli, date(2026, 11, 18))[0]
    ccm2 = b3_boletim.coletar({"mercadoria": "CCM", "vencimento": 2}, IND, cli, date(2026, 11, 18))[0]
    assert ccm1.valor == pytest.approx(_ultimo("ccm1"), abs=1e-3) and "CCMX26" in ccm1.detalhe
    assert ccm2.valor == pytest.approx(_ultimo("ccm2"), abs=1e-3) and ccm1.data == date(2026, 11, 17)
    assert sum("PR261118" in u for u in cli.urls) == 1    # o arquivo de 18/11 ainda não saiu: usa o de 17/11 (1 download)
    assert b3_boletim.coletar({"mercadoria": "DOL"}, IND, cli, date(2026, 11, 18))[0].valor == pytest.approx(_ultimo("dol"), abs=1e-3)
    with pytest.raises(Exception, match="vencimento"):
        b3_boletim.coletar({"mercadoria": "SJC", "vencimento": 2}, IND, cli, date(2026, 11, 18))
    assert b3_boletim.contratos(b3_boletim.ler_zip(boletim_b3_zip()), "BGI") == ["BGIX26", "BGIZ26"]


def test_boletim_da_b3_baixado_uma_vez_so(tmp_path):
    """O arquivo da B3 é grande: os ajustes ficam em data/b3_ajustes.json e o monitor não baixa de novo."""
    from web_falsa import boletim_b3_zip

    class Cli:
        downloads = 0

        def obter(self, url, **kw):
            if url.endswith("PR261117.zip"):
                Cli.downloads += 1
                return Resposta(url, 200, boletim_b3_zip())
            return Resposta(url, 404, b"")

    b3_boletim.usar_cache(tmp_path / "data" / "b3_ajustes.json")
    primeiro = b3_boletim.coletar({"mercadoria": "BGI"}, IND, Cli(), HOJE)[0]
    b3_boletim._cache.clear()                                  # nova execução (outro processo)
    segundo = b3_boletim.coletar({"mercadoria": "BGI"}, IND, Cli(), HOJE)[0]
    assert Cli.downloads == 1 and primeiro.valor == segundo.valor and segundo.data == HOJE
    assert "BGIX26" in (tmp_path / "data" / "b3_ajustes.json").read_text(encoding="utf-8")


def test_b3_mesmo_pregao_e_arquivo_de_outro_dia(tmp_path):
    """After-hours (registro com data D+1) é ignorado, e um arquivo antigo devolvido no lugar do
    pedido fica com a data do pregão dele."""
    import io
    import zipfile

    def arquivo(registros):
        xml = "".join(f"<PricRpt><TradDt><Dt>{d}</Dt></TradDt><SctyId><TckrSymb>{t}</TckrSymb></SctyId>"
                      f"<FinInstrmAttrbts><AdjstdQt>{v}</AdjstdQt></FinInstrmAttrbts></PricRpt>" for t, d, v in registros)
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("x.xml", f"<Document>{xml}</Document>")
        return b.getvalue()

    zip17 = arquivo([("CCMF27", "2026-11-17", 71.10), ("CCMF27", "2026-11-18", 71.40),
                     ("DOLZ26", "2026-11-17", 5786.4), ("BGIX26", "2026-11-17", 398.5)])

    class Cli:
        downloads = []

        def obter(self, url, **kw):
            Cli.downloads.append(url[-10:])
            return Resposta(url, 200, zip17)               # a B3 devolve o último arquivo que tem

    b3_boletim.usar_cache(tmp_path / "b3_ajustes.json")
    o = b3_boletim.coletar({"mercadoria": "CCM"}, IND, Cli(), date(2026, 11, 18))[0]
    assert o.valor == 71.10 and o.data == date(2026, 11, 17)      # nem o after-hours, nem a data errada
    assert Cli.downloads == ["261118.zip"]                        # o de 17/11 veio do cache gravado
    assert '"2026-11-18"' not in (tmp_path / "b3_ajustes.json").read_text(encoding="utf-8")


def test_tabela_sem_texto_no_cabecalho_usa_a_posicao():
    html = ("<h2>Precios Chicago/Kansas</h2><p>17/11/2026</p><table><thead><tr>" + "<th><img alt=''></th>" * 7 +
            "</tr></thead><tbody><tr><td>Dic-26</td><td>218,72 (2,94)</td><td>232,59</td><td>175,88</td><td>0,00</td>"
            "<td>1.369,71</td><td>369,49</td></tr><tr><td>Ene-27</td><td>0,00</td><td>0,00</td><td>0,00</td>"
            "<td>450,30 (-1,29)</td><td>1.375,44</td><td>367,28</td></tr></tbody></table>")
    fonte = {"titulo_contem": ["chicago"], "coluna_valor": ["soja"], "coluna_reserva": 4, "colunas_esperadas": 7,
             "primeira_linha_com_valor": True}
    o = tabela_html.extrair(html, fonte, IND, HOJE, estilo="br")[0]
    assert o.valor == 450.30 and not o.incerta and "pela posição" in o.detalhe and "Ene-27" in o.detalhe
    sem_conferir = {k: v for k, v in fonte.items() if k != "colunas_esperadas"}
    assert tabela_html.extrair(html, sem_conferir, IND, HOJE, estilo="br")[0].incerta   # posição sem conferir = incerta
    with pytest.raises(Exception, match="a tabela mudou"):
        tabela_html.extrair(html, {**fonte, "colunas_esperadas": 8}, IND, HOJE)
