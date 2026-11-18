"""Estrutura comum dos coletores de cotações."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

_RE_DATA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b")


@dataclass
class Observacao:
    indicador: str
    data: date
    valor: float
    fonte: str
    url: str
    coletado_em: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    detalhe: str = ""
    incerta: bool = False            # ex.: coluna achada por posição, data presumida

    def como_dict(self) -> dict:
        d = asdict(self)
        d["data"] = self.data.isoformat()
        return d


def ler_data(texto: str, hoje: date) -> date | None:
    """Lê 'dd/mm/aaaa', 'dd/mm/aa' ou 'dd/mm' (ano inferido, nunca no futuro)."""
    if not texto:
        return None
    m = _RE_DATA.search(str(texto))
    if not m:
        return None
    dia, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        if ano:
            ano_i = int(ano)
            if ano_i < 100:
                ano_i += 2000
            return date(ano_i, mes, dia)
        d = date(hoje.year, mes, dia)
        if d > hoje:
            d = date(hoje.year - 1, mes, dia)
        return d
    except ValueError:
        return None


def estilo_da_fonte(fonte_registro: dict | None, fonte_cfg: dict) -> str:
    if fonte_cfg.get("estilo_numero"):
        return fonte_cfg["estilo_numero"]
    idioma = (fonte_registro or {}).get("idioma", "pt")
    return "br" if idioma in ("pt", "es") else "en"
