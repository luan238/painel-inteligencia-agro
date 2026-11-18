"""Coletores de cotações e de notícias (sem internet)."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from agente.coletores import b3_ajustes, bcb, tabela_html
from agente.coletores.noticias import (ColetorNoticias, descobrir_feed, ler_feed, links_de_materias,
                                       metadados_materia, selecionar)
from agente.rede import BloqueadoPorRobots, Cliente, Resposta
from web_falsa import AGORA, paginas_cotacoes

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
    html = paginas_cotacoes()["https://www.noticiasagricolas.com.br/cotacoes/soja"]
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
    html = paginas_cotacoes()["https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/lum-ajustes-do-pregao-ptBR.asp"]
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
