"""Gera um boletim de EXEMPLO com dados FICTÍCIOS (internet e IA simuladas),
com histórico semeado e projeções antigas — para visualizar o painel completo.

    python tests/gerar_exemplo.py  →  exemplos/boletim_exemplo_FICTICIO.json (+ .md)
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).parent))

from agente import rede  # noqa: E402
from agente.__main__ import executar  # noqa: E402
from agente.analise import calcular_metricas, eixo_janela  # noqa: E402
from agente.config import carregar_config  # noqa: E402
from agente.coletores.base import Observacao  # noqa: E402
from agente.historico import Historico  # noqa: E402
from agente.projecoes import RegistroProjecoes, calcular_bandas  # noqa: E402
from agente.validacao import Resultado  # noqa: E402
from llm_falso import LLMFalso  # noqa: E402
from web_falsa import AGORA, HOJE, WebFalsa, serie  # noqa: E402

SERIES = {
    "dolar_ptax": ("ptax", 1), "dolar_futuro_b3": ("dol", 1), "selic_meta": ("selic", 1), "petroleo_wti": ("wti", 1),
    "petroleo_brent": ("brent", 1), "soja_cbot": ("soja_cbot", 0.01), "farelo_cbot": ("farelo", 1),
    "oleo_soja_cbot": ("oleo", 1), "soja_paranagua": ("paranagua", 1), "soja_parana": ("parana", 1),
    "soja_uberlandia": ("uberlandia", 1), "soja_b3": ("sjc", 1), "soja_rosario": ("rosario", 1),
    "milho_cbot": ("milho_cbot", 0.01), "milho_campinas": ("campinas", 1), "milho_b3": ("ccm1", 1),
    "milho_b3_2": ("ccm2", 1), "trigo_cbot": ("trigo_cbot", 0.01), "trigo_parana": ("trigo_pr", 1),
    "trigo_rs": ("trigo_rs", 1), "algodao_ice": ("algodao_ice", 1), "algodao_cepea": ("algodao_cepea", 1),
    "caroco_algodao_mt": ("caroco_mt", 1), "caroco_algodao_ba": ("caroco_ba", 1), "cafe_arabica_ice": ("cafe_ny", 1),
    "cafe_robusta_londres": ("robusta", 1), "cafe_arabica_cepea": ("cafe_cepea", 1), "cafe_manhuacu": ("manhuacu", 1),
    "boi_gordo_cepea": ("boi", 1), "boi_b3": ("bgi", 1),
}


def semear(cfg) -> None:
    hist = Historico(cfg.caminho("historico_csv"))
    for ind in cfg.indicadores:
        nome, fator = SERIES[ind["id"]]
        fonte = ind["fontes"][0]["fonte"]
        for d, v in serie(nome).items():
            if d >= HOJE:
                continue
            hist.registrar(Observacao(ind["id"], d, round(v * fator, 4), fonte, "https://exemplo.invalid/"), "ok", 1)
    hist.salvar()
    # projeções registradas em pregões passados (para o track record aparecer auditado)
    registro = RegistroProjecoes(cfg.caminho("projecoes"))
    datas = sorted(serie("ptax"))[-16:-6]
    for d in datas:
        eixo = eixo_janela(d, 21)
        for i in cfg.blocos_cfg["projecoes"]:
            ind = cfg.indicador(i)
            s = {k: v for k, v in hist.serie(i).items() if k <= d}
            res = Resultado(i, "ok", s[d], d, ind["fontes"][0]["fonte"], "")
            m = calcular_metricas(ind, res, s, d, eixo)
            banda = calcular_bandas(m, d, cfg.geral["projecoes"], "neutro")
            if banda:
                registro.registrar(banda, f"{d.isoformat()}T19:43:00-03:00")
    registro.salvar()


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    for pasta in ("config", "prompts"):
        shutil.copytree(RAIZ / pasta, tmp / pasta)
    cfg = carregar_config(tmp)
    cfg.geral["coleta"]["pausa_mesmo_site_s"] = 0
    cfg.geral["llm"]["pausa_entre_chamadas_s"] = 0
    semear(cfg)
    rede.definir_transporte(WebFalsa())
    try:
        rc = executar(cfg, agora=AGORA, turno="fechamento", llm=LLMFalso())
    finally:
        rede.definir_transporte(None)
    assert rc == 0, f"execução falhou ({rc})"
    destino = RAIZ / "exemplos"
    destino.mkdir(exist_ok=True)
    boletim = json.loads((tmp / "boletim_atual.json").read_text(encoding="utf-8"))
    boletim["metadata"]["scope"] = "⚠️ EXEMPLO COM DADOS FICTÍCIOS (internet e IA simuladas) — não usar para decisão"
    boletim["metadata"]["timestamp"] += " · EXEMPLO FICTÍCIO"
    (destino / "boletim_exemplo_FICTICIO.json").write_text(json.dumps(boletim, ensure_ascii=False, indent=2), encoding="utf-8")
    md = (tmp / "relatorios" / "relatorio_atual.md").read_text(encoding="utf-8")
    aviso = "> ⚠️ **EXEMPLO COM DADOS FICTÍCIOS** gerado com internet e IA simuladas, só para mostrar o formato.\n\n"
    (destino / "relatorio_exemplo_FICTICIO.md").write_text(aviso + md, encoding="utf-8")
    print(f"✔ exemplo gerado em {destino}")


if __name__ == "__main__":
    main()
