"""Coletores simples: regex numa página, API JSON genérica e Yahoo Finance."""
from __future__ import annotations

import os
import html
import re
from urllib.parse import quote
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ..numeros import ler_numero
from ..rede import ErroColeta
from .base import Observacao, estilo_da_fonte, ler_data

_RE_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expandir_env(texto: str) -> str:
    def troca(m):
        valor = os.environ.get(m.group(1))
        if not valor:
            raise ErroColeta(f"variável de ambiente {m.group(1)} não definida")
        return valor
    return _RE_VAR.sub(troca, texto)


def _url_publica(url: str) -> str:
    """Remove chaves de API da URL antes de gravá-la no histórico/painel."""
    return re.sub(r"(api_key|apikey|token|key)=[^&]+", r"\1=***", url, flags=re.I)


# -------------------------------------------------------------- regex_pagina
def coletar_regex(fonte: dict, ind: dict, cliente, hoje: date, registro: dict | None = None) -> list[Observacao]:
    url = fonte["url"]
    texto = cliente.obter(url, ignorar_robots=bool(fonte.get("ignorar_robots"))).texto
    texto = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", texto)
    texto = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", texto)))
    m = re.search(fonte["regex"], texto, re.I | re.S)
    if not m:
        raise ErroColeta(f"padrão não encontrado na página: {fonte['regex'][:60]}")
    valor = ler_numero(m.group(1), estilo_da_fonte(registro, fonte))
    if valor is None:
        raise ErroColeta(f"trecho capturado não é número: {m.group(1)[:30]}")
    d = None
    if fonte.get("regex_data"):
        md = re.search(fonte["regex_data"], texto, re.I | re.S)
        d = ler_data(md.group(1), hoje) if md else None
    return [Observacao(indicador=ind["id"], data=d or hoje, valor=valor, fonte=fonte.get("fonte", ""),
                       url=url, incerta=d is None, detalhe=f"regex '{fonte['regex'][:40]}'")]


# ----------------------------------------------------------------- json_api
def _navegar(obj, caminho: str):
    for parte in [p for p in caminho.split(".") if p]:
        if isinstance(obj, list):
            obj = obj[int(parte)]
        else:
            obj = obj[parte]
    return obj


def coletar_json(fonte: dict, ind: dict, cliente, hoje: date, registro: dict | None = None) -> list[Observacao]:
    if fonte.get("requer_env") and not os.environ.get(fonte["requer_env"]):
        raise ErroColeta(f"fonte opcional: defina o secret {fonte['requer_env']} para usá-la")
    url_real = _expandir_env(fonte["url"])
    url_pub = fonte.get("url_publica") or _url_publica(url_real)
    dados = cliente.obter(url_real, ignorar_robots=bool(fonte.get("ignorar_robots"))).json()
    obs = []
    if fonte.get("caminho_lista"):
        for item in _navegar(dados, fonte["caminho_lista"]):
            d = ler_data(str(item.get(fonte["campo_data"], "")).replace("-", "/"), hoje) \
                if "/" in str(item.get(fonte["campo_data"], "")) else _data_iso(item.get(fonte["campo_data"]))
            v = ler_numero(item.get(fonte["campo_valor"]), "en")
            if d and v is not None and d <= hoje:
                obs.append(Observacao(indicador=ind["id"], data=d, valor=v, fonte=fonte.get("fonte", ""),
                                      url=url_pub, detalhe="API JSON"))
    else:
        v = ler_numero(_navegar(dados, fonte["caminho_valor"]), "en")
        d = _data_iso(_navegar(dados, fonte["caminho_data"])) if fonte.get("caminho_data") else None
        if v is not None:
            obs.append(Observacao(indicador=ind["id"], data=d or hoje, valor=v, fonte=fonte.get("fonte", ""),
                                  url=url_pub, incerta=d is None, detalhe="API JSON"))
    if not obs:
        raise ErroColeta("API JSON sem valores utilizáveis")
    return obs


def coletar_csv(fonte: dict, ind: dict, cliente, hoje: date, registro: dict | None = None) -> list[Observacao]:
    """CSV público com data na 1ª coluna e valor na 2ª (ex.: FRED fredgraph.csv); "." = sem dado."""
    import csv
    import io
    url = _expandir_env(fonte["url"])
    url_pub = fonte.get("url_publica") or _url_publica(url)
    texto = cliente.obter(url, ignorar_robots=bool(fonte.get("ignorar_robots"))).texto
    linhas = list(csv.reader(io.StringIO(texto)))
    if len(linhas) < 2 or len(linhas[0]) < 2:
        raise ErroColeta(f"CSV sem colunas de data e valor: {texto[:80]!r}")
    i_data, i_valor = int(fonte.get("coluna_data", 0)), int(fonte.get("coluna_valor", 1))
    obs = []
    for linha in linhas[1:][-int(fonte.get("ultimas_linhas", 60)):]:
        if len(linha) <= max(i_data, i_valor):
            continue
        d = _data_iso(linha[i_data])
        v = ler_numero(linha[i_valor], "en") if linha[i_valor].strip() not in ("", ".") else None
        if d and v is not None and d <= hoje:
            obs.append(Observacao(indicador=ind["id"], data=d, valor=v, fonte=fonte.get("fonte", ""), url=url_pub,
                                  detalhe=f"CSV {linhas[0][i_valor]}"))
    if not obs:
        raise ErroColeta("CSV sem valores utilizáveis")
    return obs


def _data_iso(texto) -> date | None:
    try:
        return date.fromisoformat(str(texto)[:10])
    except (TypeError, ValueError):
        return None


# -------------------------------------------------------------------- yahoo
URL_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}?range=3mo&interval=1d"


def coletar_yahoo(fonte: dict, ind: dict, cliente, hoje: date, registro: dict | None = None) -> list[Observacao]:
    url = URL_YAHOO.format(simbolo=fonte["simbolo"])
    pagina = fonte.get("url_publica") or "https://finance.yahoo.com/quote/" + quote(fonte["simbolo"])
    dados = cliente.obter(url, ignorar_robots=bool(fonte.get("ignorar_robots"))).json()
    try:
        res = dados["chart"]["result"][0]
        fuso = ZoneInfo(res["meta"].get("exchangeTimezoneName", "UTC"))
        tempos = res.get("timestamp") or []
        fechamentos = res["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as e:
        raise ErroColeta(f"resposta inesperada do Yahoo: {e}") from e
    obs = []
    for ts, v in zip(tempos, fechamentos):
        if v is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(fuso).date()
        obs.append(Observacao(indicador=ind["id"], data=d, valor=float(v), fonte=fonte.get("fonte", "Yahoo"),
                              url=pagina, detalhe=f"{fonte['simbolo']} (fechamento diário)"))
    meta = res["meta"]
    if meta.get("regularMarketPrice") and meta.get("regularMarketTime"):
        d = datetime.fromtimestamp(meta["regularMarketTime"], tz=timezone.utc).astimezone(fuso).date()
        if not obs or d > obs[-1].data:
            obs.append(Observacao(indicador=ind["id"], data=d, valor=float(meta["regularMarketPrice"]),
                                  fonte=fonte.get("fonte", "Yahoo"), url=pagina,
                                  detalhe=f"{fonte['simbolo']} (último negócio)"))
    if not obs:
        raise ErroColeta("Yahoo sem cotações")
    return obs
