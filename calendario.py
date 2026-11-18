"""Calendário de pregões da B3 (dias úteis + feriados nacionais) e janelas."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from dateutil.easter import easter


@lru_cache(maxsize=64)
def feriados(ano: int) -> frozenset:
    pascoa = easter(ano)
    dias = {
        date(ano, 1, 1),                      # Confraternização Universal
        pascoa - timedelta(days=48),          # Carnaval (segunda)
        pascoa - timedelta(days=47),          # Carnaval (terça)
        pascoa - timedelta(days=2),           # Sexta-feira Santa
        date(ano, 4, 21),                     # Tiradentes
        date(ano, 5, 1),                      # Dia do Trabalho
        pascoa + timedelta(days=60),          # Corpus Christi
        date(ano, 9, 7),                      # Independência
        date(ano, 10, 12),                    # N. Sra. Aparecida
        date(ano, 11, 2),                     # Finados
        date(ano, 11, 15),                    # Proclamação da República
        date(ano, 11, 20),                    # Consciência Negra (nacional desde 2024)
        date(ano, 12, 24),                    # sem pregão na B3
        date(ano, 12, 25),                    # Natal
        date(ano, 12, 31),                    # sem pregão na B3
    }
    return frozenset(dias)


def eh_dia_util(d: date) -> bool:
    return d.weekday() < 5 and d not in feriados(d.year)


def dia_util_anterior_ou_igual(d: date) -> date:
    while not eh_dia_util(d):
        d -= timedelta(days=1)
    return d


def somar_dias_uteis(d: date, n: int) -> date:
    passo = 1 if n >= 0 else -1
    restantes = abs(n)
    while restantes:
        d += timedelta(days=passo)
        if eh_dia_util(d):
            restantes -= 1
    return d


def dias_uteis_entre(inicio: date, fim: date) -> int:
    """Quantidade de dias úteis no intervalo (inicio, fim]."""
    if fim <= inicio:
        return 0
    n, d = 0, inicio
    while d < fim:
        d += timedelta(days=1)
        if eh_dia_util(d):
            n += 1
    return n


def ultimos_dias_uteis(ate: date, n: int) -> list[date]:
    """Os n últimos dias úteis terminando em `ate` (inclusive, se for útil)."""
    dias: list[date] = []
    d = ate
    while len(dias) < n:
        if eh_dia_util(d):
            dias.append(d)
        d -= timedelta(days=1)
    return sorted(dias)


def ultimo_dia_util_do_mes(ano: int, mes: int) -> date:
    prox = date(ano + (mes == 12), (mes % 12) + 1, 1)
    return dia_util_anterior_ou_igual(prox - timedelta(days=1))


def inicio_da_semana(hoje: date) -> date:
    """Domingo que abre a semana de referência (semana = domingo a sábado).

    No fim de semana o relatório faz o balanço da semana que acabou de fechar:
    no sábado é a própria semana; no domingo, a semana anterior.
    """
    domingo = hoje - timedelta(days=(hoje.weekday() + 1) % 7)
    if hoje.weekday() == 6:                     # domingo → semana que terminou ontem
        domingo -= timedelta(days=7)
    return domingo


DIAS_SEMANA = ["Segunda-Feira", "Terça-Feira", "Quarta-Feira", "Quinta-Feira",
               "Sexta-Feira", "Sábado", "Domingo"]
