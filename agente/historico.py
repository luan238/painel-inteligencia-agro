"""Histórico de cotações (data/historico.csv).

Cada linha é uma observação de UMA fonte: data, indicador, valor, fonte, url,
coletado_em, status. Nada é apagado — o arquivo é a trilha de auditoria. A série
"consolidada" de cada indicador usa, por data, a fonte de maior prioridade que
passou nas checagens.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

CAMPOS = ["data", "indicador", "valor", "fonte", "prioridade", "url", "coletado_em", "status", "detalhe"]


class Historico:
    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)
        self.linhas: dict[tuple, dict] = {}
        if self.caminho.exists():
            with open(self.caminho, encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    r["valor"] = float(r["valor"])
                    r["prioridade"] = int(r.get("prioridade") or 9)
                    self.linhas[(r["data"], r["indicador"], r["fonte"])] = r

    def registrar(self, obs, status: str, prioridade: int) -> None:
        chave = (obs.data.isoformat(), obs.indicador, obs.fonte)
        anterior = self.linhas.get(chave)
        # não sobrescreve um valor aprovado com um rejeitado
        if anterior and anterior["status"] != "rejeitado" and status == "rejeitado":
            return
        if anterior and anterior["status"] == status and abs(anterior["valor"] - float(obs.valor)) < 1e-12:
            return                                  # mesmo valor já registrado: mantém a 1ª coleta
        self.linhas[chave] = {
            "data": obs.data.isoformat(), "indicador": obs.indicador, "valor": float(obs.valor),
            "fonte": obs.fonte, "prioridade": prioridade, "url": obs.url, "coletado_em": obs.coletado_em,
            "status": status, "detalhe": obs.detalhe[:200],
        }

    def serie(self, indicador: str, ate: date | None = None) -> dict[date, float]:
        """Série consolidada {data: valor} (fonte de maior prioridade aprovada)."""
        melhor: dict[str, dict] = {}
        for (d, ind, _), r in self.linhas.items():
            if ind != indicador or r["status"] == "rejeitado":
                continue
            if ate and d > ate.isoformat():
                continue
            if d not in melhor or r["prioridade"] < melhor[d]["prioridade"]:
                melhor[d] = r
        return {date.fromisoformat(d): r["valor"] for d, r in sorted(melhor.items())}

    def registro(self, indicador: str, d: date) -> dict | None:
        cands = [r for (dd, ind, _), r in self.linhas.items()
                 if ind == indicador and dd == d.isoformat() and r["status"] != "rejeitado"]
        return min(cands, key=lambda r: r["prioridade"]) if cands else None

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS)
            w.writeheader()
            for chave in sorted(self.linhas):
                w.writerow({k: self.linhas[chave].get(k, "") for k in CAMPOS})
        tmp.replace(self.caminho)
