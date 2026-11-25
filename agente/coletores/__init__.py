"""Registro dos coletores de cotações e execução por indicador."""
from __future__ import annotations

import os
from datetime import date

from ..rede import BloqueadoPorRobots, ErroColeta
from . import b3_ajustes, b3_boletim, bcb, outros, tabela_html
from .base import Observacao

COLETORES = {
    "bcb_ptax": lambda f, i, c, h, r: bcb.coletar_ptax(f, i, c, h),
    "bcb_sgs": lambda f, i, c, h, r: bcb.coletar_sgs(f, i, c, h),
    "b3_ajustes": b3_ajustes.coletar,
    "b3_boletim": b3_boletim.coletar,
    "tabela_html": tabela_html.coletar,
    "regex_pagina": outros.coletar_regex,
    "json_api": outros.coletar_json,
    "csv_api": outros.coletar_csv,
    "yahoo": outros.coletar_yahoo,
}


def coletar_indicador(ind: dict, cfg, cliente, hoje: date):
    """Roda todas as fontes ativas do indicador.

    Retorna (observacoes, relatorio_fontes) — relatorio_fontes tem uma linha por
    fonte com status 'ok' / 'erro' / 'robots' / 'inativa' e a mensagem.
    """
    observacoes: list[Observacao] = []
    relatorio = []
    for prioridade, fonte in enumerate(ind.get("fontes", []), start=1):
        nome = fonte.get("fonte", "?")
        registro = cfg.fonte(nome)
        linha = {"fonte": nome, "tipo": fonte.get("tipo"), "prioridade": prioridade,
                 "url": fonte.get("url") or (registro or {}).get("url_dados") or (registro or {}).get("url", "")}
        if fonte.get("ativa") is False or (registro is not None and registro.get("ativa") is False):
            relatorio.append({**linha, "status": "inativa", "mensagem": "fonte desativada na configuração"})
            continue
        if fonte.get("requer_env") and not os.environ.get(fonte["requer_env"]):
            relatorio.append({**linha, "status": "inativa",
                              "mensagem": f"opcional — defina o secret {fonte['requer_env']} no GitHub para ativar"})
            continue
        try:
            obs = COLETORES[fonte["tipo"]](fonte, ind, cliente, hoje, registro)
            fator = fonte.get("fator")
            for o in obs:
                o.indicador = ind["id"]
                o.fonte = nome
                setattr(o, "prioridade", prioridade)
                if fator:                            # conversão de unidade declarada na config
                    o.valor = round(o.valor * float(fator), 6)
                    o.detalhe += f" · convertido de {fonte.get('unidade_origem', 'outra unidade')} (×{fator})"
            observacoes.extend(obs)
            ultima = max(obs, key=lambda o: o.data)
            relatorio.append({**linha, "status": "ok", "mensagem": f"{len(obs)} valor(es); último {ultima.valor} em "
                              f"{ultima.data:%d/%m/%Y}" + (f" · {ultima.detalhe[:150]}" if ultima.detalhe else "")})
        except BloqueadoPorRobots as e:
            relatorio.append({**linha, "status": "robots", "mensagem": str(e)})
        except ErroColeta as e:
            relatorio.append({**linha, "status": "erro", "mensagem": str(e)[:420]})
        except Exception as e:                       # nunca deixa uma fonte derrubar o relatório
            relatorio.append({**linha, "status": "erro", "mensagem": f"{type(e).__name__}: {str(e)[:250]}"})
    return observacoes, relatorio
