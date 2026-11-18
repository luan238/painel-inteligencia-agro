"""Arquivo oficial e gratuito da B3 com os preços de ajuste do pregão.

A B3 publica todo dia, em "Pesquisa por pregão", o Boletim de preços (Price Report,
leiaute BVBG.086.01, arquivo PRaammdd.zip). Ele traz o PREÇO DE AJUSTE de todos os
contratos futuros: dólar (DOL), milho (CCM), boi gordo (BGI), soja CME (SJC), café
arábica (ICF) etc. É a mesma informação da antiga página "Ajustes do Pregão", que
saiu do ar, só que no formato de arquivo oficial.

O arquivo do dia sai depois do fechamento; antes disso o coletor usa o do pregão anterior.
O arquivo é grande (todas as séries da bolsa), então os ajustes já lidos ficam guardados em
data/b3_ajustes.json: cada arquivo é baixado uma vez só, e o monitor de 20 em 20 minutos não
volta a baixá-lo.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET

from ..rede import ErroColeta
from .base import Observacao

URL_ARQUIVO = "https://www.b3.com.br/pesquisapregao/download?filelist=PR{aammdd}.zip"
PAGINA_PUBLICA = ("https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/"
                  "boletins-diarios/pesquisa-por-pregao/pesquisa-por-pregao/")
MESES = "FGHJKMNQUVXZ"                       # código do mês de vencimento: F = jan … Z = dez
_RE_FUTURO = re.compile(r"^([A-Z0-9]{3})([FGHJKMNQUVXZ])(\d{2})$")
_cache: dict = {}                            # (id do cliente, data) → {ticker: (ajuste, data do pregão)}
CAMINHO_CACHE = None                         # data/b3_ajustes.json (definido por quem chama o coletor)
DIAS_NO_CACHE = 5


def usar_cache(caminho) -> None:
    global CAMINHO_CACHE
    CAMINHO_CACHE = caminho


def _ler_cache() -> dict:
    if not CAMINHO_CACHE:
        return {}
    try:
        return json.loads(open(CAMINHO_CACHE, encoding="utf-8").read())
    except (OSError, ValueError):
        return {}


def _gravar_cache(dia: date, precos: dict) -> None:
    if not CAMINHO_CACHE:
        return
    dados = _ler_cache()
    dados[dia.isoformat()] = {t: [v, d.isoformat() if d else None] for t, (v, d) in sorted(precos.items())}
    dados = {k: dados[k] for k in sorted(dados)[-DIAS_NO_CACHE:]}
    try:
        from pathlib import Path
        Path(CAMINHO_CACHE).parent.mkdir(parents=True, exist_ok=True)
        Path(CAMINHO_CACHE).write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError:
        pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def ler_xml(bruto: bytes) -> dict:
    """{ticker: (preço de ajuste, data do pregão)} só dos contratos futuros (ex.: CCMF27)."""
    precos: dict = {}
    for _, el in ET.iterparse(io.BytesIO(bruto), events=("end",)):
        if _local(el.tag) != "PricRpt":
            continue
        campos: dict = {}
        for sub in el.iter():
            nome = _local(sub.tag)
            if nome in ("TckrSymb", "Dt", "AdjstdQt") and nome not in campos and (sub.text or "").strip():
                campos[nome] = sub.text.strip()
        ticker = campos.get("TckrSymb", "")
        if _RE_FUTURO.match(ticker) and campos.get("AdjstdQt"):
            try:
                valor = float(campos["AdjstdQt"])
                dia = date.fromisoformat(campos["Dt"][:10]) if campos.get("Dt") else None
            except ValueError:
                valor = 0.0
            if valor:
                precos[ticker] = (valor, dia)
        el.clear()
    return precos


def ler_zip(dados: bytes) -> dict:
    """Abre o .zip (que às vezes vem com outro .zip dentro) e lê os XML."""
    precos: dict = {}
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for nome in z.namelist():
            bruto = z.read(nome)
            if bruto[:2] == b"PK":
                precos.update(ler_zip(bruto))
            elif nome.lower().endswith(".xml") or bruto.lstrip()[:1] == b"<":
                precos.update(ler_xml(bruto))
    return precos


def _precos_do_dia(cliente, dia: date, ignorar_robots: bool) -> dict | None:
    chave = (id(cliente), dia)
    if chave not in _cache:
        guardado = _ler_cache().get(dia.isoformat())
        if guardado:                                   # arquivo já baixado numa execução anterior
            _cache[chave] = {t: (v, date.fromisoformat(d) if d else None) for t, (v, d) in guardado.items()}
            return _cache[chave]
        url = URL_ARQUIVO.format(aammdd=dia.strftime("%y%m%d"))
        try:
            resp = cliente.obter(url, ignorar_robots=ignorar_robots)
            _cache[chave] = ler_zip(resp.conteudo) if resp.conteudo[:2] == b"PK" else None
            if _cache[chave]:
                _gravar_cache(dia, _cache[chave])
        except ErroColeta:
            _cache[chave] = None
        except (zipfile.BadZipFile, ET.ParseError):
            _cache[chave] = None
    return _cache[chave]


def contratos(precos: dict, mercadoria: str) -> list[str]:
    """Vencimentos disponíveis da mercadoria, do mais próximo ao mais distante."""
    achados = []
    for ticker in precos:
        m = _RE_FUTURO.match(ticker)
        if m and m.group(1) == mercadoria:
            achados.append((int(m.group(3)), MESES.index(m.group(2)), ticker))
    return [t for *_, t in sorted(achados)]


def coletar(fonte: dict, ind: dict, cliente, hoje: date, registro: dict | None = None) -> list[Observacao]:
    mercadoria = str(fonte["mercadoria"]).upper()
    vencimento = int(fonte.get("vencimento", 1))
    ignorar = bool(fonte.get("ignorar_robots"))
    precos, dia_arquivo = None, None
    for atraso in range(0, 7):                         # arquivo de hoje (após o fechamento) ou dos pregões anteriores
        dia = hoje - timedelta(days=atraso)
        if dia.weekday() >= 5:
            continue
        precos = _precos_do_dia(cliente, dia, ignorar)
        if precos:
            dia_arquivo = dia
            break
    if not precos:
        raise ErroColeta("boletim de preços da B3 (arquivo PR) não encontrado nos últimos pregões")
    lista = contratos(precos, mercadoria)
    if len(lista) < vencimento:
        raise ErroColeta(f"{mercadoria}: {len(lista)} vencimento(s) no boletim da B3 de {dia_arquivo:%d/%m/%Y}")
    ticker = lista[vencimento - 1]
    valor, dia_pregao = precos[ticker]
    return [Observacao(indicador=ind["id"], data=dia_pregao or dia_arquivo, valor=valor,
                       fonte=fonte.get("fonte", "B3"), url=PAGINA_PUBLICA,
                       detalhe=f"{ticker} · preço de ajuste (boletim oficial da B3)")]
