"""Leitura e formatação de números no padrão brasileiro (1.234,56) e
internacional (1,234.56), e extração de números de textos para o verificador."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MENOS = "−"


def sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e com espaços simples — para comparar rótulos."""
    return re.sub(r"\s+", " ", sem_acentos(str(texto)).lower()).strip()


# ------------------------------------------------------------------ leitura
_RE_NUM_CELULA = re.compile(r"[-+−]?\s*\d[\d.,\s]*")


def ler_numero(texto, estilo: str = "br") -> float | None:
    """Converte '1.611,06', 'R$ 5,4564', '-0,58%', '1,202.25' ou 12.5 em float.

    estilo: 'br' (vírgula decimal), 'en' (ponto decimal) ou 'auto'.
    """
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    s = str(texto).strip().replace(MENOS, "-").replace("\xa0", " ")
    m = _RE_NUM_CELULA.search(s)
    if not m:
        return None
    bruto = m.group(0).replace(" ", "")
    negativo = bruto.startswith("-")
    bruto = bruto.lstrip("+-").strip(".,")
    if not bruto:
        return None
    tem_ponto, tem_virgula = "." in bruto, "," in bruto
    if tem_ponto and tem_virgula:
        decimal = "," if bruto.rfind(",") > bruto.rfind(".") else "."
    elif tem_virgula:
        if estilo == "en" and re.fullmatch(r"\d{1,3}(,\d{3})+", bruto):
            decimal = None                        # 1,234 em inglês = mil
        else:
            decimal = ","
    elif tem_ponto:
        if estilo == "br" and re.fullmatch(r"\d{1,3}(\.\d{3})+", bruto):
            decimal = None                        # 1.234 em português = mil
        else:
            decimal = "."
    else:
        decimal = None
    if decimal == ",":
        bruto = bruto.replace(".", "").replace(",", ".")
    elif decimal == ".":
        bruto = bruto.replace(",", "")
    else:
        bruto = bruto.replace(".", "").replace(",", "")
    try:
        valor = float(bruto)
    except ValueError:
        return None
    return -valor if negativo else valor


# --------------------------------------------------------------- formatação
def fmt(valor: float | None, casas: int = 2) -> str:
    """5.4564 -> '5,4564'; 1611.06 -> '1.611,06'."""
    if valor is None:
        return "—"
    s = f"{abs(valor):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if valor < 0 and round(abs(valor), casas) != 0 else "") + s


def fmt_pct(valor: float | None, casas: int = 2, sinal: bool = True) -> str:
    if valor is None:
        return "—"
    s = fmt(valor, casas)
    if sinal and valor > 0 and round(valor, casas) != 0:
        s = "+" + s
    return s + "%"


_PREFIXOS_MOEDA = ("R$", "US$", "ARS", "€", "¥")


def fmt_valor(valor: float | None, unidade: str, casas: int = 2) -> str:
    """Formata com a unidade: 'R$/sc' -> 'R$ 158,52/sc'; '¢/lb' -> '78,36 ¢/lb'."""
    if valor is None:
        return "indisponível"
    num = fmt(valor, casas)
    unidade = unidade or ""
    for p in _PREFIXOS_MOEDA:
        if unidade.startswith(p):
            resto = unidade[len(p):]
            return f"{p} {num}{resto}"
    if unidade.startswith("%"):
        return f"{num}{unidade}"
    return f"{num} {unidade}".strip()


# ------------------------------------------------------- extração em textos
@dataclass
class NumeroNoTexto:
    valor: float
    casas: int
    bruto: str
    inicio: int
    eh_percentual: bool


# Trechos que contêm dígitos mas NÃO são números a conferir (mascarados antes)
_MASCARAS = [
    re.compile(r"\[(?:N|F|C)\d+\]"),                                   # referências [N3]
    re.compile(r"https?://\S+"),                                       # URLs (o verificador acusa à parte)
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),                         # 17/11/2026
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                              # 2026-11-17
    re.compile(r"\b\d{1,2}/\d{1,2}\b"),                                # 17/11, safra 26/27
    re.compile(r"\b\d{4}/\d{2,4}\b"),                                  # safra 2026/27
    re.compile(r"\b\d{1,2}h\d{0,2}\b|\b\d{1,2}:\d{2}\b", re.I),        # 16h38, 16h, 16:38
    re.compile(r"\b(?:jan|fev|feb|mar|abr|apr|mai|may|jun|jul|ago|aug|set|sep|out|oct|nov|dez|dec)[a-zç]*\.?/?\s?\d{2,4}\b", re.I),
    re.compile(r"\b[A-Z]{0,4}[FGHJKMNQUVXZ]\d{2}\b"),                  # códigos de contrato (ZSF27, X26)
    re.compile(r"(?<![\d.,])(?:19[5-9]\d|20[0-4]\d)(?![\d.,]*\d)"),     # anos
    re.compile(r"\b\d{1,3}\s?[ºª°]"),                                  # ordinais (conferidos à parte)
    re.compile(r"\b\d+\s?(?:min|minutos|seg)\b", re.I),                 # durações do roteiro
]

_RE_NUMERO = re.compile(r"(?<![\w])[-+−]?\d+(?:[.,]\d+)*")
_RE_ORDINAL = re.compile(r"\b(\d{1,3})\s?[ºª°]\s+(alta|queda|ganho|perda|baixa|valoriza|desvaloriza|sess|preg|dia|semana)", re.I)


def _mascarar(texto: str) -> str:
    for rx in _MASCARAS:
        texto = rx.sub(lambda m: " " * len(m.group(0)), texto)
    return texto


def extrair_numeros(texto: str, estilo: str = "br") -> list[NumeroNoTexto]:
    mascarado = _mascarar(texto)
    achados: list[NumeroNoTexto] = []
    for m in _RE_NUMERO.finditer(mascarado):
        bruto = m.group(0)
        valor = ler_numero(bruto, estilo)
        if valor is None:
            continue
        sem_sinal = bruto.lstrip("+-−")
        # casas decimais efetivamente escritas
        if estilo == "br":
            casas = len(sem_sinal.split(",")[1]) if "," in sem_sinal else 0
            if "," not in sem_sinal and "." in sem_sinal and not re.fullmatch(r"\d{1,3}(\.\d{3})+", sem_sinal):
                casas = len(sem_sinal.split(".")[-1])
        else:
            casas = len(sem_sinal.split(".")[1]) if "." in sem_sinal else 0
            if "." not in sem_sinal and "," in sem_sinal and not re.fullmatch(r"\d{1,3}(,\d{3})+", sem_sinal):
                casas = len(sem_sinal.split(",")[-1])
        depois = mascarado[m.end():m.end() + 12].lower()
        eh_pct = depois.lstrip().startswith(("%", "por cento", "p.p", "pp"))
        achados.append(NumeroNoTexto(valor=valor, casas=casas, bruto=bruto,
                                     inicio=m.start(), eh_percentual=eh_pct))
    return achados


def extrair_ordinais(texto: str) -> list[tuple[int, str]]:
    """Encontra afirmações do tipo '3ª alta seguida' -> [(3, 'alta')]."""
    return [(int(m.group(1)), m.group(2).lower()) for m in _RE_ORDINAL.finditer(texto)]
