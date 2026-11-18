"""Verificador anti-alucinação: confere CADA número, referência e sequência
citados pela IA contra os dados que o sistema realmente coletou.

Um número no texto é aceito se, arredondado com as casas decimais escritas,
coincidir com algum valor permitido (cotações, variações, cálculos, ou números
presentes no texto das notícias entregues à IA). Inteiros pequenos (≤ 10) são
livres ("2 a 3 minutos", "4 elos").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .numeros import extrair_numeros, extrair_ordinais

_RE_URL = re.compile(r"https?://|www\.", re.I)
_RE_REF = re.compile(r"\[(N\d+)\]")
_ALTA = ("alta", "ganho", "valoriza")
_QUEDA = ("queda", "perda", "baixa", "desvaloriza")


@dataclass
class Problema:
    campo: str
    tipo: str            # numero | referencia | url | sequencia | estrutura
    trecho: str
    mensagem: str


class Verificador:
    def __init__(self, numeros: Iterable[float], textos: Iterable[tuple[str, str]] = (),
                 ids_validos: Iterable[str] = (), sequencias: Iterable[int] = (), inteiros_livres: int = 10):
        self.reps: set[tuple[int, str]] = set()
        self.inteiros_livres = inteiros_livres
        for v in numeros:
            self.permitir(v)
        for texto, estilo in textos:
            for n in extrair_numeros(texto or "", estilo):
                self.permitir(n.valor)
        self.ids = set(ids_validos)
        self.sequencias = [s for s in sequencias if s]

    def permitir(self, valor) -> None:
        if valor is None:
            return
        try:
            v = abs(float(valor))
        except (TypeError, ValueError):
            return
        for casas in range(0, 6):
            self.reps.add((casas, f"{v:.{casas}f}"))

    def numero_ok(self, valor: float, casas: int) -> bool:
        v = abs(valor)
        if casas == 0 and v <= self.inteiros_livres and float(v).is_integer():
            return True
        return (casas, f"{v:.{casas}f}") in self.reps

    def checar_texto(self, texto: str, campo: str) -> list[Problema]:
        problemas = []
        if not isinstance(texto, str) or not texto:
            return problemas
        if _RE_URL.search(texto):
            problemas.append(Problema(campo, "url", texto[:60], "o texto não pode conter links/URLs — cite [N#]"))
        for n in extrair_numeros(texto, "br"):
            if not self.numero_ok(n.valor, n.casas):
                ini = max(0, n.inicio - 30)
                problemas.append(Problema(campo, "numero", n.bruto,
                                          f"o número {n.bruto} (em “…{texto[ini:n.inicio + 25].strip()}…”) "
                                          f"não consta nos FATOS, CALCULOS ou NOTICIAS"))
        for ref in _RE_REF.findall(texto):
            if ref not in self.ids:
                problemas.append(Problema(campo, "referencia", ref, f"a notícia [{ref}] não existe nesta lista"))
        for n, palavra in extrair_ordinais(texto):
            if palavra.startswith(_ALTA):
                ok = n in [s for s in self.sequencias if s > 0]
            elif palavra.startswith(_QUEDA):
                ok = -n in [s for s in self.sequencias if s < 0]
            else:
                ok = n in [abs(s) for s in self.sequencias] or n <= 2
            if not ok:
                problemas.append(Problema(campo, "sequencia", f"{n}ª {palavra}",
                                          f"“{n}ª {palavra}” não corresponde a nenhuma sequência calculada"))
        return problemas

    def checar(self, obj, campo: str = "") -> list[Problema]:
        """Percorre dicionários/listas e confere todos os textos."""
        problemas = []
        if isinstance(obj, str):
            problemas.extend(self.checar_texto(obj, campo))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                problemas.extend(self.checar(v, f"{campo}.{k}" if campo else str(k)))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                problemas.extend(self.checar(v, f"{campo}[{i}]"))
        return problemas
