"""IA simulada para testes: monta respostas a partir dos FATOS do prompt e,
de propósito, INVENTA um número e uma referência na 1ª resposta de alguns
blocos — para provar que o verificador reprova e a correção funciona."""
from __future__ import annotations

import json
import re


def _entre(texto: str, inicio: str, fim: str) -> str:
    i = texto.index(inicio) + len(inicio)
    return texto[i:texto.index(fim, i)].strip()


class LLMFalso:
    configurado = True
    descricao = "modelo-de-teste @ local"

    def __init__(self, errar_em=("complexo_soja",), teimoso_em=()):
        self.errar_em = set(errar_em)        # erra na 1ª tentativa, corrige depois
        self.teimoso_em = set(teimoso_em)    # erra sempre (força troca por texto automático)
        self.chamadas = 0
        self.prompts: list[str] = []

    def completar(self, mensagens, compacto=None):
        self.chamadas += 1
        prompt = mensagens[1]["content"]
        self.prompts.append(mensagens[-1]["content"])
        corrigindo = len(mensagens) > 2
        if "BLOCO:" in prompt:
            return json.dumps(self._bloco(prompt, corrigindo), ensure_ascii=False)
        return json.dumps(self._fechamento(prompt), ensure_ascii=False)

    def _bloco(self, prompt, corrigindo):
        titulo = re.search(r"BLOCO: (.*)", prompt).group(1)
        fatos = json.loads(_entre(prompt, "FATOS (cotações verificadas pelo sistema):", "CALCULOS"))
        bruto_not = _entre(prompt, "NOTICIAS (coletadas hoje nas fontes confiáveis; cite pelo ID):", "Responda com um JSON")
        noticias = json.loads(bruto_not) if bruto_not.startswith("[") and not bruto_not.startswith("[] (") else []
        elos = re.findall(r'\{"elo": "(.*?)", "direcionamento"', prompt)

        def ids(campo):
            m = re.search(rf'"{campo}": \{{ (.*?) \}}', prompt)
            return re.findall(r'"([a-z0-9_]+)": "', m.group(1)) if m else []

        com_valor = [f for f in fatos if "valor" in f]
        f0 = com_valor[0] if com_valor else None
        ref = f" [{noticias[0]['id']}]" if noticias else ""
        base = (f"{f0['nome']} em {f0['valor']} ({f0.get('var_dia', 'sem variação')})" if f0 else "Sem cotações verificadas")
        mapa = {"Soja": "complexo_soja", "Milho": "complexo_milho_e_ddgs", "Algodão": "complexo_algodao",
                "Café": "complexo_cafe", "Câmbio": "cambio_e_energia"}
        bloco_id = next((v for k, v in mapa.items() if k in titulo), "")
        saida = {
            "resumo_curto": f"{base}.{ref}",
            "manchete": "Mercado ajusta posições no fechamento",
            "vies": f"Viés neutro com atenção ao câmbio{ref}.",
            "resumo_executivo": f"{base}. As notícias do dia reforçam a leitura{ref}.",
            "noticias_destaque": [n["id"] for n in noticias[:3]],
            "elos": [{"elo": e, "direcionamento": f"Acompanhar {f0['nome'] if f0 else 'os indicadores'} e escalonar decisões.",
                      "referencias": [n["id"] for n in noticias[:1]]} for e in elos],
            "drivers_semana": {i: f"Movimento semanal de {next((f.get('var_semana', '') for f in fatos if f['id'] == i), '')}." for i in ids("drivers_semana")},
            "narrativas_mes": {i: f"Acumulado do mês: {next((f.get('var_mes', '') for f in fatos if f['id'] == i), '')}." for i in ids("narrativas_mes")},
            "gatilhos": {i: "Mudança no câmbio ou no clima das principais praças." for i in ids("gatilhos")},
            "vieses_projecao": {i: ("alta" if k % 2 == 0 else "neutro") for k, i in enumerate(ids("vieses_projecao"))},
        }
        if (bloco_id in self.errar_em and not corrigindo) or bloco_id in self.teimoso_em:
            saida["resumo_executivo"] += " Os estoques devem cair para 999,37 mil toneladas [N999], a 4ª alta seguida."
            saida["elos"][0]["direcionamento"] += " Veja https://site-inventado.com/materia."
        return saida

    def _fechamento(self, prompt):
        fatos = json.loads(_entre(prompt, "FATOS PRINCIPAIS:", "CALCULO DO NDF"))
        resumos = json.loads(_entre(prompt, "RESUMOS DOS BLOCOS:", "FATOS PRINCIPAIS:"))
        frases = " ".join(r["resumo"] for r in resumos)
        f0 = next((f for f in fatos if "valor" in f), {"nome": "Indicadores", "valor": "—"})
        texto_audio = ("Boa noite a todos da mesa e parceiros do campo. Este é o fechamento do dia. " + frases + " ") * 2
        return {
            "escopo": f"Fechamento com {f0['nome']} em {f0['valor']}",
            "pilula": {"titulo": "Carrego do câmbio a termo", "analise": f"O {f0['nome']} está em {f0['valor']}.",
                       "conclusao": "Compare a trava com o preço físico antes de decidir."},
            "roteiro_audio": texto_audio + "Vamos às tabelas e ao painel.",
        }
