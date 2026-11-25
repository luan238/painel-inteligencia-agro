"""Carrega e valida os arquivos de configuração (pasta config/)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

RAIZ = Path(__file__).resolve().parent.parent


def carregar_yaml(caminho: Path) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class Config:
    raiz: Path
    geral: dict
    fontes: list
    indicadores: list
    blocos_cfg: dict
    indicadores_inativos: list = field(default_factory=list)   # "ativo: false" no indicadores.yaml

    # ------------------------------------------------------------ atalhos
    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.geral["relatorio"].get("fuso_horario", "America/Sao_Paulo"))

    def agora(self) -> datetime:
        return datetime.now(self.tz)

    @property
    def blocos(self) -> list:
        return self.blocos_cfg["blocos"]

    def caminho(self, chave: str) -> Path:
        return self.raiz / self.geral["saidas"][chave]

    def indicador(self, ind_id: str) -> dict | None:
        return next((i for i in self.indicadores if i["id"] == ind_id), None)

    def bloco(self, bloco_id: str) -> dict | None:
        return next((b for b in self.blocos if b["id"] == bloco_id), None)

    def fonte(self, nome: str) -> dict | None:
        return next((f for f in self.fontes if f["nome"] == nome), None)

    def fontes_ativas(self) -> list:
        return [f for f in self.fontes if f.get("ativa", True)]

    # ------------------------------------------------------------ validação
    def problemas(self) -> list[str]:
        """Checa a consistência entre os arquivos de configuração."""
        erros: list[str] = []
        ids = [i["id"] for i in self.indicadores] + list(self.indicadores_inativos)
        duplicados = {i for i in ids if ids.count(i) > 1}
        if duplicados:
            erros.append(f"indicadores duplicados: {sorted(duplicados)}")
        blocos_ids = {b["id"] for b in self.blocos}
        nomes_fontes = {f["nome"] for f in self.fontes}
        for ind in self.indicadores:
            for campo in ("id", "nome", "bloco", "unidade", "faixa", "fontes"):
                if campo not in ind:
                    erros.append(f"indicador {ind.get('id')}: falta o campo '{campo}'")
            if ind.get("bloco") not in blocos_ids:
                erros.append(f"indicador {ind['id']}: bloco '{ind.get('bloco')}' não existe")
            faixa = ind.get("faixa") or [None, None]
            if len(faixa) != 2 or faixa[0] >= faixa[1]:
                erros.append(f"indicador {ind['id']}: faixa inválida {faixa}")
            for fonte in ind.get("fontes", []):
                if fonte.get("tipo") not in TIPOS_COLETOR:
                    erros.append(f"indicador {ind['id']}: tipo de fonte desconhecido '{fonte.get('tipo')}'")
                nome = fonte.get("fonte", "")
                if nome not in nomes_fontes and "(checagem)" not in nome and "EIA" not in nome:
                    erros.append(f"indicador {ind['id']}: fonte '{nome}' não está em fontes.yaml")
        for ind in self.indicadores:
            ref = ind.get("vol_referencia")
            for r in ([ref] if isinstance(ref, str) else (ref or [])):
                if r not in ids:
                    erros.append(f"indicador {ind['id']}: vol_referencia '{r}' não existe")
        for lista in ("painel_semanal", "painel_mensal", "projecoes"):
            for ind_id in self.blocos_cfg.get(lista, []):
                if ind_id not in ids:
                    erros.append(f"{lista}: indicador '{ind_id}' não existe")
        for sp in self.blocos_cfg.get("spreads", []):
            for lado in ("a", "b"):
                if sp.get(lado) not in ids:
                    erros.append(f"spread {sp['id']}: indicador '{sp.get(lado)}' não existe")
        for b in self.blocos:
            if len(b.get("elos", [])) == 0:
                erros.append(f"bloco {b['id']}: sem elos")
        for f in self.fontes:
            if not str(f.get("url", "")).startswith(("http://", "https://")):
                erros.append(f"fonte {f.get('nome')}: url inválida")
        vistos = set()
        for i, prov in enumerate((self.geral.get("llm") or {}).get("provedores") or []):
            nome = (prov or {}).get("nome") or f"#{i + 1}"
            if not str((prov or {}).get("base_url", "")).startswith("https://"):
                erros.append(f"llm.provedores {nome}: base_url deve começar com https://")
            if not (prov or {}).get("chave_env"):
                erros.append(f"llm.provedores {nome}: falta 'chave_env' (nome do secret com a chave)")
            if not ((prov or {}).get("modelos") or (prov or {}).get("modelo")):
                erros.append(f"llm.provedores {nome}: falta a lista 'modelos'")
            if nome in vistos:
                erros.append(f"llm.provedores: nome repetido '{nome}'")
            vistos.add(nome)
        return erros


TIPOS_COLETOR = {"bcb_ptax", "bcb_sgs", "b3_ajustes", "b3_boletim", "tabela_html", "regex_pagina", "json_api",
                 "csv_api", "yahoo"}


def carregar_config(raiz: Path | None = None) -> Config:
    raiz = Path(raiz or RAIZ)
    pasta = raiz / "config"
    todos = carregar_yaml(pasta / "indicadores.yaml").get("indicadores", [])
    return Config(
        raiz=raiz,
        geral=carregar_yaml(pasta / "configuracoes.yaml"),
        fontes=carregar_yaml(pasta / "fontes.yaml").get("fontes", []),
        indicadores=[i for i in todos if i.get("ativo", True) is not False],
        blocos_cfg=carregar_yaml(pasta / "blocos.yaml"),
        indicadores_inativos=[i["id"] for i in todos if i.get("ativo", True) is False],
    )
