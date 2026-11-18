"""Lê o corpo de uma issue criada pelo formulário "Nova fonte" do GitHub e
acrescenta o site em config/fontes.yaml. Usado pelo workflow nova-fonte.yml.

O corpo chega pela variável de ambiente CORPO_ISSUE (nunca interpolado no
shell, para evitar injeção de comandos).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.__main__ import adicionar_fonte  # noqa: E402

CAMPOS = {
    "nome do site": "nome", "url": "url", "endereço": "url", "região": "regiao", "regiao": "regiao",
    "tipo de conteúdo": "tipo", "tipo": "tipo", "idioma": "idioma", "feed rss (opcional)": "rss",
    "rss": "rss", "observação": "observacao", "observacao": "observacao",
}
TIPOS = {"notícias": "noticias", "cotações": "cotacoes", "notícias e cotações": "noticias_e_cotacoes",
         "relatório oficial": "relatorio_oficial", "api oficial": "api_oficial"}
IDIOMAS = {"português": "pt", "espanhol": "es", "inglês": "en", "chinês": "zh"}


def ler_formulario(corpo: str) -> dict:
    dados = {}
    for bloco in re.split(r"^###\s+", corpo or "", flags=re.M)[1:]:
        titulo, _, valor = bloco.partition("\n")
        chave = CAMPOS.get(titulo.strip().lower())
        valor = valor.strip()
        if chave and valor and valor != "_No response_":
            dados[chave] = valor
    if "tipo" in dados:
        dados["tipo"] = TIPOS.get(dados["tipo"].lower(), "noticias")
    if "idioma" in dados:
        dados["idioma"] = IDIOMAS.get(dados["idioma"].lower(), dados["idioma"].lower()[:2])
    return dados


def main() -> int:
    dados = ler_formulario(os.environ.get("CORPO_ISSUE", ""))
    saida = Path(os.environ.get("GITHUB_OUTPUT", "/dev/null"))
    try:
        nome = adicionar_fonte(RAIZ, dados.get("nome", ""), dados.get("url", ""), dados.get("regiao", "Brasil"),
                               dados.get("tipo", "noticias"), dados.get("idioma", "pt"), dados.get("rss", ""),
                               dados.get("observacao", ""))
    except ValueError as erro:
        with open(saida, "a", encoding="utf-8") as f:
            f.write(f"resultado=erro\nmensagem={str(erro)[:300]}\n")
        print(f"✖ {erro}")
        return 0
    with open(saida, "a", encoding="utf-8") as f:
        f.write(f"resultado=ok\nmensagem=Fonte '{nome}' adicionada em config/fontes.yaml\n")
    print(f"✔ Fonte '{nome}' adicionada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
