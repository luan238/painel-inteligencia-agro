"""Página oficial "Ajustes do Pregão" da B3 (preços de ajuste dos futuros).

Mercadorias úteis: DOL (dólar), WDO (mini dólar), CCM (milho), BGI (boi gordo),
ICF (café arábica 4/5), SJC (soja CME), ETN (etanol), DI1 (juros).
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from ..numeros import ler_numero, normalizar
from ..rede import ErroColeta
from .base import Observacao, ler_data

URL_PADRAO = "https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/lum-ajustes-do-pregao-ptBR.asp"
_RE_ATUALIZADO = re.compile(r"atualizad[oa]\s*em\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})", re.I)


def extrair(html: str, fonte: dict, ind: dict, hoje: date, url: str = URL_PADRAO) -> list[Observacao]:
    soup = BeautifulSoup(html, "lxml")
    tabela = soup.find("table", id="tblDadosAjustes")
    if tabela is None:
        for t in soup.find_all("table"):
            cab = normalizar(t.get_text(" ", strip=True)[:300])
            if "mercadoria" in cab and "vencimento" in cab:
                tabela = t
                break
    if tabela is None:
        raise ErroColeta("tabela de ajustes não encontrada na página da B3")

    cabecalhos = [normalizar(th.get_text(" ", strip=True)) for th in tabela.find_all("th")]

    def col(*chaves):
        for i, c in enumerate(cabecalhos):
            if all(k in c for k in chaves):
                return i
        return None

    i_merc, i_venc = col("mercadoria"), col("vencimento")
    i_atual = col("ajuste", "atual")
    if None in (i_merc, i_venc, i_atual):
        i_merc, i_venc, i_atual = 0, 1, 3                # layout histórico da página

    alvo = str(fonte["mercadoria"]).upper()
    vencimento = fonte.get("vencimento", 1)
    mercadoria_atual, achadas = "", []
    for tr in tabela.find_all("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) <= max(i_venc, i_atual):
            continue
        if tds[i_merc]:
            mercadoria_atual = tds[i_merc].split("-")[0].strip().upper()
        if mercadoria_atual == alvo:
            achadas.append(tds)
    if not achadas:
        raise ErroColeta(f"mercadoria {alvo} não encontrada nos ajustes da B3")

    if isinstance(vencimento, int):
        if len(achadas) < vencimento:
            raise ErroColeta(f"{alvo}: só {len(achadas)} vencimentos listados")
        linha = achadas[vencimento - 1]
    else:
        linha = next((l for l in achadas if l[i_venc].strip().upper() == str(vencimento).upper()), None)
        if linha is None:
            raise ErroColeta(f"{alvo}: vencimento {vencimento} não encontrado")

    valor = ler_numero(linha[i_atual], "br")
    if valor is None:
        raise ErroColeta(f"{alvo} {linha[i_venc]}: ajuste sem valor ('{linha[i_atual]}')")
    texto = soup.get_text(" ", strip=True)
    m = _RE_ATUALIZADO.search(texto)
    d = ler_data(m.group(1), hoje) if m else None
    incerta = d is None
    return [Observacao(indicador=ind["id"], data=d or hoje, valor=valor, fonte=fonte.get("fonte", "B3"),
                       url=url, incerta=incerta,
                       detalhe=f"{alvo} vencimento {linha[i_venc]} — preço de ajuste atual"
                               + (" · data não informada na página" if incerta else ""))]


def coletar(fonte: dict, ind: dict, cliente, hoje: date, registro: dict | None = None) -> list[Observacao]:
    url = fonte.get("url") or (registro or {}).get("url_dados") or URL_PADRAO
    resp = cliente.obter(url, ignorar_robots=bool(fonte.get("ignorar_robots")))
    return extrair(resp.texto, fonte, ind, hoje, url)
