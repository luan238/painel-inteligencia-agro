"""Coletor genérico de tabelas HTML.

Escolhe a tabela pelo TÍTULO (texto que vem antes dela na página, legenda e
cabeçalhos), a LINHA pelo rótulo (ex.: 'Uberlândia') ou posição, e a COLUNA pelo
cabeçalho (ex.: 'Fechamento'). Se houver coluna de data, lê a série inteira
(isso preenche o histórico de uma vez).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup

from ..numeros import ler_numero, normalizar
from ..rede import ErroColeta
from .base import Observacao, estilo_da_fonte, ler_data

_TAGS_TITULO = {"h1", "h2", "h3", "h4", "h5", "h6", "caption", "strong", "b", "label"}
_RE_CLASSE_TITULO = re.compile(r"tit|title|cabec|header|info|nome|label", re.I)
_RE_FECHAMENTO = re.compile(r"(?:fechamento|atualizad[oa]|data|cota[cç][aã]o)\D{0,15}(\d{1,2}/\d{1,2}/\d{2,4})", re.I)
_RE_QUALQUER_DATA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_RE_NUMERO = re.compile(r"-?\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|-?\d+(?:[.,]\d+)?")


_RE_CELULA_NUMERICA = re.compile(r"[^\w]*(?:R\$|US\$|U\$S)?\s*-?[\d.,]+(?:\s*\(\s*-?[\d.,]+\s*\))?\s*%?")


def _parece_numero(celula: str) -> bool:
    return bool(_RE_CELULA_NUMERICA.fullmatch((celula or "").strip()))


def numero_da_celula(celula: str, estilo: str):
    """Número da célula; se ela tiver mais de um (ex.: '450,30 (-1,29)'), vale o primeiro."""
    v = ler_numero(celula, estilo)
    if v is not None:
        return v
    m = _RE_NUMERO.search(celula or "")
    return ler_numero(m.group(0), estilo) if m else None


@dataclass
class Tabela:
    contexto: str
    cabecalhos: list
    linhas: list = field(default_factory=list)
    data_contexto: str = ""

    def texto_busca(self) -> str:
        return normalizar(self.contexto + " " + " ".join(self.cabecalhos))


def tabelas_da_pagina(html: str) -> list[Tabela]:
    soup = BeautifulSoup(html, "lxml")
    tabelas = []
    for t in soup.find_all("table"):
        if t.find("table"):                       # tabela de layout que contém outras
            continue
        cabecalhos: list[str] = []
        linhas: list[list[str]] = []
        for tr in t.find_all("tr"):
            celulas = tr.find_all(["th", "td"])
            textos = [c.get_text(" ", strip=True) for c in celulas]
            if not any(textos):
                continue
            eh_cabecalho = tr.find_parent("thead") is not None or all(c.name == "th" for c in celulas)
            if eh_cabecalho and not linhas:
                cabecalhos = textos
            else:
                linhas.append(textos)
        if not cabecalhos and len(linhas) > 1 and len(linhas[0]) > 1 and \
                not any(_parece_numero(c) for c in linhas[0][1:]):
            cabecalhos = linhas.pop(0)                # cabeçalho escrito com <td> na 1ª linha
        # contexto: títulos e textos entre a tabela anterior e esta
        titulos, textos_antes = [], []
        ancestrais = {id(p) for p in t.parents}
        for el in t.find_all_previous(limit=80):
            if id(el) in ancestrais:              # o contêiner da própria tabela não é "título"
                continue
            if el.name == "table":
                break
            texto = el.get_text(" ", strip=True) if hasattr(el, "get_text") else ""
            if not texto or len(texto) > 200:
                continue
            classes = " ".join(el.get("class", [])) if hasattr(el, "get") else ""
            if el.name in _TAGS_TITULO or _RE_CLASSE_TITULO.search(classes):
                titulos.append(texto)
            textos_antes.append(texto)
        legenda = t.find("caption")
        contexto = " | ".join(([legenda.get_text(" ", strip=True)] if legenda else []) + titulos[:4])
        data_txt = ""
        for texto in textos_antes:                # o mais próximo da tabela vem primeiro
            m = _RE_FECHAMENTO.search(texto) or _RE_QUALQUER_DATA.search(texto)
            if m:
                data_txt = m.group(1) if m.lastindex else m.group(0)
                break
        if not data_txt:                          # data escrita no próprio cabeçalho (ex.: BCR)
            for c in cabecalhos:
                m = _RE_QUALQUER_DATA.search(c)
                if m:
                    data_txt = m.group(0)
                    break
        tabelas.append(Tabela(contexto=contexto, cabecalhos=cabecalhos, linhas=linhas, data_contexto=data_txt))
    return tabelas


def _indice_coluna(cabecalhos: list[str], chaves) -> int | None:
    if isinstance(chaves, int):
        return chaves
    norm = [normalizar(c) for c in cabecalhos]
    for chave in chaves or []:
        k = normalizar(chave)
        for i, c in enumerate(norm):
            if k in c and ("var" not in c or "var" in k) and ("%" not in c or "%" in k):
                return i
    return None


def _contem_todos(texto: str, termos) -> bool:
    return all(normalizar(t) in texto for t in (termos or []))


def _contem_algum(texto: str, termos) -> bool:
    return any(normalizar(t) in texto for t in (termos or []))


def extrair(html: str, fonte: dict, ind: dict, hoje: date, estilo: str = "br", url: str = "") -> list[Observacao]:
    tabelas = tabelas_da_pagina(html)
    if not tabelas:
        raise ErroColeta("nenhuma tabela encontrada na página")
    candidatas = [t for t in tabelas
                  if _contem_todos(t.texto_busca(), fonte.get("titulo_contem"))
                  and not _contem_algum(normalizar(t.contexto), fonte.get("titulo_nao_contem"))]
    if not candidatas:
        titulos = "; ".join(sorted({t.contexto[:60] for t in tabelas if t.contexto}))[:400]
        raise ErroColeta(f"nenhuma tabela com título contendo {fonte.get('titulo_contem')} "
                         f"(títulos na página: {titulos or 'sem títulos'})")
    erros = []
    for tab in candidatas:
        try:
            return _extrair_da_tabela(tab, fonte, ind, hoje, estilo, url)
        except ErroColeta as e:
            erros.append(str(e))
    raise ErroColeta(" / ".join(erros[:3]))


def _amostra(tab: Tabela) -> str:
    """Trecho da estrutura lida, para o relatório do Checar fontes mostrar o que a página tem."""
    cab = [c[:16] for c in tab.cabecalhos[:8]]
    linhas = [[c[:12] for c in l[:8]] for l in tab.linhas[:3]]
    return f" · cabeçalhos={cab} · linhas={linhas}"[:280]


def _extrair_da_tabela(tab: Tabela, fonte: dict, ind: dict, hoje: date, estilo: str, url: str) -> list[Observacao]:
    nome_fonte = fonte.get("fonte", "")
    col_data = _indice_coluna(tab.cabecalhos, fonte.get("coluna_data")) if fonte.get("coluna_data") else None
    col_valor = _indice_coluna(tab.cabecalhos, fonte.get("coluna_valor"))
    incerta = False
    por_posicao = False
    if col_valor is None and fonte.get("coluna_reserva") is not None:
        col_valor, por_posicao = int(fonte["coluna_reserva"]), True    # cabeçalho sem texto: vale a posição
        incerta = True

    # ---- modo série: tabela com uma coluna de datas (vários dias)
    if col_data is not None and col_valor is not None:
        obs = []
        for linha in tab.linhas:
            if max(col_data, col_valor) >= len(linha):
                continue
            d = ler_data(linha[col_data], hoje)
            v = ler_numero(linha[col_valor], estilo)
            if d and v is not None:
                obs.append(Observacao(indicador=ind["id"], data=d, valor=v, fonte=nome_fonte, url=url,
                                      detalhe=f"tabela '{tab.contexto[:60]}' · coluna '{tab.cabecalhos[col_valor]}'"))
        if obs:
            return obs

    # ---- modo valor: uma linha escolhida
    linha = None
    if fonte.get("linha_rotulo_padrao"):                # ex.: só linhas de vencimento ("Ene-27")
        padrao = re.compile(fonte["linha_rotulo_padrao"], re.I)
        linhas_validas = [l for l in tab.linhas if l and padrao.search(l[0].strip())]
        if not linhas_validas:
            raise ErroColeta(f"nenhuma linha com rótulo no formato {fonte['linha_rotulo_padrao']}" + _amostra(tab))
        tab = Tabela(contexto=tab.contexto, cabecalhos=tab.cabecalhos, linhas=linhas_validas,
                     data_contexto=tab.data_contexto)
    if fonte.get("linha_contem"):
        termos = [normalizar(t) for t in fonte["linha_contem"]]
        for l in tab.linhas:
            if l and any(t in normalizar(l[0]) for t in termos):
                linha = l
                break
        if linha is None:
            for l in tab.linhas:
                if any(t in normalizar(" ".join(l)) for t in termos):
                    linha = l
                    break
        if linha is None:
            raise ErroColeta(f"linha com {fonte['linha_contem']} não encontrada na tabela '{tab.contexto[:50]}'"
                             + _amostra(tab))
    elif fonte.get("primeira_linha_com_valor"):
        for l in tab.linhas:
            if col_valor is not None and col_valor < len(l):
                v = numero_da_celula(l[col_valor], estilo)
                if v:                                   # vazio, traço ou 0,00 = sem cotação nessa posição
                    linha = l
                    break
        if linha is None:
            raise ErroColeta(f"nenhuma linha com valor na coluna {fonte.get('coluna_valor')} da tabela "
                             f"'{tab.contexto[:50]}'" + _amostra(tab))
    else:
        n = int(fonte.get("linha", 1))
        if len(tab.linhas) < n:
            raise ErroColeta(f"tabela '{tab.contexto[:50]}' tem só {len(tab.linhas)} linhas")
        linha = tab.linhas[n - 1]

    if fonte.get("colunas_esperadas") and linha is not None:
        if len(linha) != int(fonte["colunas_esperadas"]):
            raise ErroColeta(f"a tabela mudou: {len(linha)} colunas em vez de {fonte['colunas_esperadas']}" + _amostra(tab))
        if por_posicao:
            incerta = False                       # leiaute conferido: posição + número exato de colunas

    valor = None
    if col_valor is not None and col_valor < len(linha):
        valor = numero_da_celula(linha[col_valor], estilo)
    if valor is None:                              # sem cabeçalho reconhecível: 1ª célula numérica
        for celula in linha[1:]:
            if "%" in celula:
                continue
            valor = ler_numero(celula, estilo)
            if valor is not None:
                incerta = True
                break
    if valor is None:
        raise ErroColeta(f"sem valor numérico na linha {linha[:4]}")

    d = ler_data(tab.data_contexto, hoje)
    for celula in linha:                           # data na própria linha tem prioridade
        if _RE_QUALQUER_DATA.search(celula):
            d = ler_data(celula, hoje) or d
            break
    if d is None:
        d = hoje
        incerta = True
    rotulo = linha[0] if linha else ""
    nome_col = tab.cabecalhos[col_valor] if (col_valor is not None and col_valor < len(tab.cabecalhos)) else "1ª coluna numérica"
    if por_posicao:
        nome_col = f"nº {col_valor + 1}, pela posição"
    return [Observacao(indicador=ind["id"], data=d, valor=valor, fonte=nome_fonte, url=url, incerta=incerta,
                       detalhe=f"tabela '{tab.contexto[:60]}' · linha '{rotulo[:30]}' · coluna '{nome_col}'"
                               + (" · data não informada na página" if not tab.data_contexto and d == hoje else ""))]


def coletar(fonte: dict, ind: dict, cliente, hoje: date, registro: dict | None = None) -> list[Observacao]:
    url = fonte["url"]
    resp = cliente.obter(url, ignorar_robots=bool(fonte.get("ignorar_robots")))
    return extrair(resp.texto, fonte, ind, hoje, estilo_da_fonte(registro, fonte), url)
