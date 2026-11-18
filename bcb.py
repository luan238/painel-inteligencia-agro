"""APIs oficiais do Banco Central do Brasil (dados abertos).

PTAX:  https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/
SGS:   https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..rede import ErroColeta
from .base import Observacao

URL_PTAX = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
            "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
            "?@dataInicial='{ini}'&@dataFinalCotacao='{fim}'&$format=json")
URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json&dataInicial={ini}&dataFinal={fim}"
# páginas públicas (o link que aparece no painel; a API fica registrada no detalhe)
PAGINA_PTAX = "https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes"
PAGINA_SGS = "https://www3.bcb.gov.br/sgspub/localizarseries/localizarSeries.do?method=prepararTelaLocalizarSeries"


def coletar_ptax(fonte: dict, ind: dict, cliente, hoje: date, dias_historico: int = 60) -> list[Observacao]:
    ini = (hoje - timedelta(days=dias_historico)).strftime("%m-%d-%Y")
    url = URL_PTAX.format(ini=ini, fim=hoje.strftime("%m-%d-%Y"))
    dados = cliente.obter(url).json()
    itens = dados.get("value", [])
    if not itens:
        raise ErroColeta("API PTAX não retornou cotações no período")
    obs = []
    for item in itens:
        quando = datetime.fromisoformat(item["dataHoraCotacao"][:19])
        obs.append(Observacao(indicador=ind["id"], data=quando.date(), valor=float(item["cotacaoVenda"]),
                              fonte=fonte.get("fonte", "Banco Central do Brasil"),
                              url=fonte.get("url_publica", PAGINA_PTAX),
                              detalhe=f"PTAX venda — boletim de fechamento {quando:%d/%m/%Y %H:%M} (API olinda.bcb.gov.br)"))
    return obs


def coletar_sgs(fonte: dict, ind: dict, cliente, hoje: date, dias_historico: int = 60) -> list[Observacao]:
    serie = int(fonte["serie"])
    ini = (hoje - timedelta(days=dias_historico)).strftime("%d/%m/%Y")
    url = URL_SGS.format(serie=serie, ini=ini, fim=hoje.strftime("%d/%m/%Y"))
    dados = cliente.obter(url).json()
    if not isinstance(dados, list) or not dados:
        raise ErroColeta(f"série SGS {serie} sem dados no período")
    obs = []
    for item in dados:
        d = datetime.strptime(item["data"], "%d/%m/%Y").date()
        if d > hoje:                # a Selic meta vem preenchida até a próxima reunião do Copom
            continue
        obs.append(Observacao(indicador=ind["id"], data=d, valor=float(item["valor"]),
                              fonte=fonte.get("fonte", "Banco Central do Brasil"),
                              url=fonte.get("url_publica", PAGINA_SGS),
                              detalhe=f"SGS série {serie} (API api.bcb.gov.br)"))
    return obs
