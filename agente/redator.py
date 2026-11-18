"""Redação dos textos do relatório.

Fluxo por bloco: monta FATOS/CALCULOS/NOTICIAS → pede à IA um JSON → valida a
estrutura e passa no verificador (números, referências, sequências, URLs) →
se reprovado, devolve os problemas à IA e pede correção (até N tentativas) →
o que continuar reprovado é trocado por texto automático (determinístico).
Sem IA configurada, todo o texto é automático — o relatório nunca deixa de sair.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .llm import ErroLLM, TrocaDeFormato, extrair_json
from .numeros import fmt, fmt_pct, fmt_valor
from .verificador import Problema, Verificador

VIESES = {"alta", "baixa", "neutro"}


# --------------------------------------------------------------- utilidades
def _caminho_tokens(caminho: str) -> list:
    tokens = []
    for parte in caminho.split("."):
        m = re.match(r"^([^\[]+)((?:\[\d+\])*)$", parte)
        if not m:
            return []
        tokens.append(m.group(1))
        tokens.extend(int(i) for i in re.findall(r"\[(\d+)\]", m.group(2)))
    return tokens


def _obter(obj, tokens):
    for t in tokens:
        obj = obj[t]
    return obj


def _definir(obj, tokens, valor) -> bool:
    try:
        alvo = _obter(obj, tokens[:-1])
        alvo[tokens[-1]] = valor
        return True
    except (KeyError, IndexError, TypeError):
        return False


def _var_txt(pct, abs_, m) -> str:
    if pct is None:
        return "sem referência anterior"
    sinal = "+" if abs_ > 0 else ("−" if abs_ < 0 else "")
    return f"{fmt_pct(pct)} ({sinal}{fmt_valor(abs(abs_), m.unidade, m.casas)})"


def fato(m) -> dict:
    d = {"id": m.id, "nome": m.nome, "status": m.status}
    if m.disponivel:
        d.update({"valor": fmt_valor(m.valor, m.unidade, m.casas), "data": f"{m.data:%d/%m}", "fonte": m.fonte})
        if m.var_dia_pct is not None:
            d["var_dia"] = _var_txt(m.var_dia_pct, m.var_dia_abs, m) + f" vs {m.data_anterior:%d/%m}"
        if m.var_semana_pct is not None:
            d["var_semana"] = _var_txt(m.var_semana_pct, m.var_semana_abs, m) + f" desde {m.data_ref_semana:%d/%m}"
        if m.var_mes_pct is not None:
            d["var_mes"] = _var_txt(m.var_mes_pct, m.var_mes_abs, m) + f" desde {m.data_ref_mes:%d/%m}"
        if m.sequencia:
            d["sequencia"] = f"{abs(m.sequencia)} {'altas' if m.sequencia > 0 else 'quedas'} seguidas"
        if m.minimo_janela is not None:
            d["min_max_21_pregoes"] = f"{fmt_valor(m.minimo_janela, m.unidade, m.casas)} a {fmt_valor(m.maximo_janela, m.unidade, m.casas)}"
    if m.mensagens:
        d["alertas"] = m.mensagens
    return d


def numeros_de_metricas(ms) -> list:
    nums = []
    for m in ms:
        nums += [m.valor, m.anterior, m.var_dia_pct, m.var_dia_abs, m.ref_semana, m.var_semana_pct,
                 m.var_semana_abs, m.ref_mes, m.var_mes_pct, m.var_mes_abs, m.minimo_janela,
                 m.maximo_janela, abs(m.sequencia) if m.sequencia else None]
    return nums


def estilo_noticia(n) -> str:
    return "br" if n.idioma in ("pt", "es") else "en"


# ------------------------------------------------------------------ redator
class Redator:
    def __init__(self, cfg, llm=None, raiz: Path | None = None):
        self.cfg = cfg
        self.llm = llm
        pasta = Path(raiz or cfg.raiz) / "prompts"
        self.sistema = (pasta / "sistema.md").read_text(encoding="utf-8")
        self.tpl_bloco = (pasta / "bloco.md").read_text(encoding="utf-8")
        self.tpl_fech = (pasta / "fechamento.md").read_text(encoding="utf-8")
        self.tentativas = int(cfg.geral.get("llm", {}).get("tentativas_por_bloco", 3))
        usar_ia = bool(llm and llm.configurado)
        self.stats = {"modo": "ia_verificada" if usar_ia else "sem_ia",
                      "modelo": llm.descricao if llm else "sem IA",
                      "chamadas": 0, "respostas_reprovadas": 0, "corrigidos_pela_ia": 0,
                      "campos_verificados": 0, "campos_substituidos": 0, "blocos_com_ia": 0,
                      "erros_llm": [], "detalhes": []}
        cfg_llm = cfg.geral.get("llm", {}) or {}
        enxuto = cfg_llm.get("prompt_enxuto") or cfg_llm.get("local") or {}   # IA local e APIs de limite apertado
        self.max_not_local = int(enxuto.get("max_noticias_por_bloco", 6))
        self.max_resumo_local = int(enxuto.get("max_caracteres_resumo", 350))

    def finalizar(self) -> dict:
        """Fecha as estatísticas com o que de fato aconteceu (qual IA respondeu, se alguma)."""
        if self.llm is not None and getattr(self.llm, "usados", None):
            self.stats["modelo"] = getattr(self.llm, "resumo_uso", None) or " → ".join(self.llm.usados)
        self.stats["modo"] = "ia_verificada" if self.stats["blocos_com_ia"] else "sem_ia"
        if self.llm is not None and getattr(self.llm, "erros", None):
            self.stats["erros_llm"] = list(dict.fromkeys(self.stats["erros_llm"] + self.llm.erros))[:10]
        return self.stats

    # ----------------------------------------------------------- chamada IA
    def _ciclo(self, nome: str, montar) -> dict:
        """Pede o JSON, verifica, devolve problemas para correção e mescla com a reserva.

        `montar(compacto)` devolve (prompt, verificador, reserva, estrutura). Se a IA da vez precisar
        do prompt enxuto (IA local, plano grátis com limite de tokens), o pedido é remontado na hora."""
        compacto = bool(getattr(self.llm, "compacto", False)) if self.llm is not None else False
        prompt, verificador, reserva, estrutura = montar(compacto)
        if not (self.llm and self.llm.configurado):
            return reserva

        def inicio(p):
            return [{"role": "system", "content": self.sistema}, {"role": "user", "content": p}]

        mensagens = inicio(prompt)
        saida, problemas, reprovou_alguma_vez = None, [], False
        tentativa = trocas = 0
        while tentativa < self.tentativas:
            try:
                texto = self.llm.completar(mensagens, compacto=compacto)
            except TrocaDeFormato as t:
                trocas += 1
                if trocas > 3:
                    self.stats["erros_llm"].append(f"{nome}: trocas de formato em excesso")
                    break
                compacto = t.compacto
                prompt, verificador, reserva, estrutura = montar(compacto)
                mensagens, saida, problemas = inicio(prompt), None, []
                continue
            except ErroLLM as e:
                self.stats["erros_llm"].append(f"{nome}: {e}")
                break
            tentativa += 1
            self.stats["chamadas"] += 1
            try:
                bruto = extrair_json(texto)
            except (ValueError, json.JSONDecodeError) as e:
                reprovou_alguma_vez = True
                self.stats["respostas_reprovadas"] += 1
                mensagens += [{"role": "assistant", "content": texto[:4000] or "(resposta vazia)"},
                              {"role": "user", "content": f"Sua resposta não é um JSON válido ({e}). "
                                                          "Responda novamente APENAS com o objeto JSON completo."}]
                continue
            saida, problemas = estrutura(bruto)
            problemas += verificador.checar(saida)
            if not problemas:
                if reprovou_alguma_vez:
                    self.stats["corrigidos_pela_ia"] += 1
                break
            reprovou_alguma_vez = True
            self.stats["respostas_reprovadas"] += 1
            lista = "\n".join(f"- campo {p.campo}: {p.mensagem}" for p in problemas[:20])
            mensagens += [{"role": "assistant", "content": json.dumps(bruto, ensure_ascii=False)[:6000]},
                          {"role": "user", "content": "O verificador automático REPROVOU a resposta:\n" + lista +
                           "\n\nReescreva o JSON COMPLETO corrigindo esses pontos. Use somente números que "
                           "estão nos dados fornecidos e só IDs de notícias existentes."}]
        if saida is None:
            self.stats["detalhes"].append(f"{nome}: texto automático (IA sem resposta válida)")
            return reserva
        # mescla: campos ainda reprovados viram texto automático
        substituidos = set()
        for p in problemas:
            tokens = _caminho_tokens(p.campo)
            while tokens:
                try:
                    _definir(saida, tokens, _obter(reserva, tokens))
                    substituidos.add(p.campo)
                    break
                except (KeyError, IndexError, TypeError):
                    tokens = tokens[:-1]
        self.stats["blocos_com_ia"] += 1
        if substituidos:
            self.stats["campos_substituidos"] += len(substituidos)
            self.stats["detalhes"].append(f"{nome}: {len(substituidos)} campo(s) trocados por texto automático: "
                                          + ", ".join(sorted(substituidos))[:300])
        self.stats["campos_verificados"] += sum(1 for _ in _strings(saida))
        return saida

    # ---------------------------------------------------------------- blocos
    def escrever_bloco(self, bloco: dict, metricas: list, contexto_macro: list, spreads: list,
                       noticias: list, ndf: dict | None, turno: str, data_hora: str,
                       ids_semana: list, ids_mes: list, ids_proj: list) -> dict:
        fatos = [fato(m) for m in metricas] + [fato(m) for m in contexto_macro if m not in metricas]
        calculos = [{"id": s.id, "nome": s.nome, "valor": fmt_valor(s.valor, s.unidade, s.casas),
                     "composicao": s.composicao, "status": s.status} for s in spreads if s.valor is not None]
        if ndf:
            calculos.append({"id": "ndf", "nome": "NDF teórico (câmbio a termo)", "formula": ndf["formula"],
                             "pontos_forward": fmt(ndf["pontos_forward"], 4)})

        def montar(compacto: bool):
            return self._montar_bloco(compacto, bloco, metricas, contexto_macro, spreads, noticias, ndf, turno,
                                      data_hora, ids_semana, ids_mes, ids_proj, fatos, calculos)

        return self._ciclo(bloco["id"], montar)

    def _montar_bloco(self, compacto, bloco, metricas, contexto_macro, spreads, noticias, ndf, turno, data_hora,
                      ids_semana, ids_mes, ids_proj, fatos, calculos):
        if compacto:                                              # IA local / plano grátis apertado: prompt enxuto
            noticias = noticias[: self.max_not_local]
        lista_noticias = [{"id": n.id, "titulo": n.titulo, "fonte": n.fonte, "regiao": n.regiao,
                           "publicado": n.publicado_em[:16].replace("T", " "),
                           "resumo": n.resumo[: self.max_resumo_local if compacto else 700]}
                          for n in noticias]
        ids_validos = {n.id for n in noticias}
        verificador = Verificador(
            numeros=numeros_de_metricas(metricas + list(contexto_macro)) + [s.valor for s in spreads] +
            ([ndf["spot"], ndf["taxa_brl_aa"], ndf["cupom_aa"], ndf["du"], ndf["dc"], ndf["ndf"], ndf["pontos_forward"]] if ndf else []),
            textos=[(json.dumps(fatos + calculos, ensure_ascii=False), "br")] +
                   [(n.titulo + " " + n.resumo, estilo_noticia(n)) for n in noticias],
            ids_validos=ids_validos,
            sequencias=[m.sequencia for m in metricas + list(contexto_macro)])
        reserva = self._bloco_automatico(bloco, metricas, noticias, ids_semana, ids_mes, ids_proj)

        def json_ids(ids):
            return ", ".join(f'"{i}": "..."' for i in ids)

        recuo = None if compacto else 1                            # JSON sem recuo economiza tokens
        prompt = self.tpl_bloco.format(
            turno=turno, data_hora=data_hora, titulo_bloco=bloco["titulo"],
            fatos=json.dumps(fatos, ensure_ascii=False, indent=recuo),
            calculos=json.dumps(calculos, ensure_ascii=False, indent=recuo) if calculos else "[]",
            noticias=json.dumps(lista_noticias, ensure_ascii=False, indent=recuo) if lista_noticias else "[] (nenhuma notícia verificada neste turno)",
            elos_formato=",\n".join(f'    {{"elo": "{e}", "direcionamento": "...", "referencias": ["N#"]}}'
                                     for e in bloco["elos"]),
            ids_semana=json_ids(ids_semana), ids_mes=json_ids(ids_mes),
            ids_projecao=json_ids(ids_proj), ids_vies=", ".join(f'"{i}": "alta|baixa|neutro"' for i in ids_proj))

        def estrutura(bruto: dict):
            return self._estruturar_bloco(bruto, bloco, reserva, ids_validos, ids_semana, ids_mes, ids_proj)

        return prompt, verificador, reserva, estrutura

    def _estruturar_bloco(self, bruto, bloco, reserva, ids_validos, ids_semana, ids_mes, ids_proj):
        problemas: list[Problema] = []
        saida: dict = {}
        for k in ("resumo_curto", "manchete", "vies", "resumo_executivo"):
            v = bruto.get(k)
            if isinstance(v, str) and v.strip():
                saida[k] = v.strip()
            else:
                saida[k] = reserva[k]
                problemas.append(Problema(k, "estrutura", "", f"o campo '{k}' é obrigatório (texto)"))
        dest = [i for i in (bruto.get("noticias_destaque") or []) if isinstance(i, str)]
        invalidos = [i for i in dest if i not in ids_validos]
        if invalidos:
            problemas.append(Problema("noticias_destaque", "referencia", ",".join(invalidos),
                                      f"IDs inexistentes em noticias_destaque: {invalidos}"))
        saida["noticias_destaque"] = [i for i in dest if i in ids_validos] or reserva["noticias_destaque"]
        elos_in = bruto.get("elos") if isinstance(bruto.get("elos"), list) else []
        elos = []
        for i, nome in enumerate(bloco["elos"]):
            item = elos_in[i] if i < len(elos_in) and isinstance(elos_in[i], dict) else None
            if not item or not isinstance(item.get("direcionamento"), str) or not item["direcionamento"].strip():
                elos.append(reserva["elos"][i])
                problemas.append(Problema(f"elos[{i}].direcionamento", "estrutura", "",
                                          f"falta o direcionamento do elo '{nome}'"))
                continue
            refs = [r for r in (item.get("referencias") or []) if isinstance(r, str)]
            ruins = [r for r in refs if r not in ids_validos]
            if ruins:
                problemas.append(Problema(f"elos[{i}].referencias", "referencia", ",".join(ruins),
                                          f"IDs inexistentes nas referências do elo '{nome}': {ruins}"))
            elos.append({"elo": nome, "direcionamento": item["direcionamento"].strip(),
                         "referencias": [r for r in refs if r in ids_validos][:3]})
        saida["elos"] = elos
        for chave, ids in (("drivers_semana", ids_semana), ("narrativas_mes", ids_mes), ("gatilhos", ids_proj)):
            dados = bruto.get(chave) if isinstance(bruto.get(chave), dict) else {}
            saida[chave] = {}
            for i in ids:
                v = dados.get(i)
                if isinstance(v, str) and v.strip():
                    saida[chave][i] = v.strip()
                else:
                    saida[chave][i] = reserva[chave][i]
        vieses = bruto.get("vieses_projecao") if isinstance(bruto.get("vieses_projecao"), dict) else {}
        saida["vieses_projecao"] = {i: (str(vieses.get(i, "neutro")).lower() if str(vieses.get(i, "neutro")).lower()
                                        in VIESES else "neutro") for i in ids_proj}
        return saida, problemas

    def _bloco_automatico(self, bloco, metricas, noticias, ids_semana, ids_mes, ids_proj) -> dict:
        disp = [m for m in metricas if m.disponivel]

        def linha(m):
            partes = [f"{m.nome_curto}: {fmt_valor(m.valor, m.unidade, m.casas)}"]
            if m.var_dia_pct is not None:
                partes.append(f"{fmt_pct(m.var_dia_pct)} no pregão")
            if m.var_semana_pct is not None:
                partes.append(f"{fmt_pct(m.var_semana_pct)} na semana")
            return " ".join(partes[:1]) + (f" ({'; '.join(partes[1:])})" if len(partes) > 1 else "")

        altas = sum(1 for m in disp if (m.var_dia_pct or 0) > 0)
        top = noticias[:5]
        manchetes = "; ".join(f"[{n.id}] {n.titulo}" for n in top[:3])
        resumo_curto = ". ".join(linha(m) for m in disp[:4]) + "." if disp else "Sem cotações verificadas neste turno."
        mmap = {m.id: m for m in metricas}

        def drv(i):
            m = mmap.get(i)
            if not m or not m.disponivel or m.var_semana_pct is None:
                return "Sem referência semanal verificada."
            return (f"De {fmt_valor(m.ref_semana, m.unidade, m.casas)} ({m.data_ref_semana:%d/%m}) para "
                    f"{fmt_valor(m.valor, m.unidade, m.casas)} ({fmt_pct(m.var_semana_pct)} na semana).")

        def nar(i):
            m = mmap.get(i)
            if not m or not m.disponivel or m.var_mes_pct is None:
                return "Sem referência mensal verificada."
            return (f"No mês: de {fmt_valor(m.ref_mes, m.unidade, m.casas)} ({m.data_ref_mes:%d/%m}) para "
                    f"{fmt_valor(m.valor, m.unidade, m.casas)} ({fmt_pct(m.var_mes_pct)}).")

        return {
            "resumo_curto": resumo_curto,
            "manchete": "Leitura quantitativa do turno",
            "vies": (f"Leitura apenas quantitativa: {altas} de {len(disp)} indicadores do bloco subiram no último pregão."
                     if disp else "Sem cotações verificadas para definir viés."),
            "resumo_executivo": ("Indicadores verificados: " + "; ".join(linha(m) for m in disp) + "."
                                 if disp else "Nenhum indicador do bloco teve cotação verificada neste turno.")
                                + (f" Notícias em destaque: {manchetes}." if manchetes else ""),
            "noticias_destaque": [n.id for n in top],
            "elos": [{"elo": e, "direcionamento": "Análise de IA indisponível neste turno. Consulte os indicadores "
                                                  "verificados e as notícias de referência abaixo.",
                      "referencias": [n.id for n in noticias[:2]]} for e in bloco["elos"]],
            "drivers_semana": {i: drv(i) for i in ids_semana},
            "narrativas_mes": {i: nar(i) for i in ids_mes},
            "gatilhos": {i: "Rompimento da banda de volatilidade de curto prazo." for i in ids_proj},
            "vieses_projecao": {i: "neutro" for i in ids_proj},
        }

    # ------------------------------------------------------------- fechamento
    def escrever_fechamento(self, blocos_txt: dict, blocos_cfg: list, metricas_chave: list, ndf: dict | None,
                            turno: str, data_hora: str, resumo_coleta: dict, noticias_todas: list) -> dict:
        resumos = [{"bloco": b["titulo"], "manchete": blocos_txt[b["id"]]["manchete"],
                    "resumo": blocos_txt[b["id"]]["resumo_curto"], "vies": blocos_txt[b["id"]]["vies"]}
                   for b in blocos_cfg]
        fatos = [fato(m) for m in metricas_chave]
        ndf_txt = {"formula": ndf["formula"], "dias_uteis": ndf["du"], "dias_corridos": ndf["dc"]} if ndf else "indisponível"
        verificador = Verificador(
            numeros=numeros_de_metricas(metricas_chave) +
            ([ndf["spot"], ndf["taxa_brl_aa"], ndf["cupom_aa"], ndf["du"], ndf["dc"], ndf["ndf"], ndf["pontos_forward"]] if ndf else []),
            textos=[(json.dumps([resumos, fatos, ndf_txt], ensure_ascii=False), "br")] +
                   [(n.titulo + " " + n.resumo, estilo_noticia(n)) for n in noticias_todas],
            ids_validos={n.id for n in noticias_todas},
            sequencias=[m.sequencia for m in metricas_chave])
        reserva = self._fechamento_automatico(blocos_txt, blocos_cfg, ndf, turno, data_hora, resumo_coleta)
        prompt = self.tpl_fech.format(turno=turno, data_hora=data_hora,
                                      resumos=json.dumps(resumos, ensure_ascii=False, indent=1),
                                      fatos=json.dumps(fatos, ensure_ascii=False, indent=1),
                                      ndf=json.dumps(ndf_txt, ensure_ascii=False))

        def estrutura(bruto):
            problemas, saida = [], {}
            esc = bruto.get("escopo")
            saida["escopo"] = esc.strip()[:220] if isinstance(esc, str) and esc.strip() else reserva["escopo"]
            pil = bruto.get("pilula") if isinstance(bruto.get("pilula"), dict) else {}
            saida["pilula"] = {}
            for k in ("titulo", "analise", "conclusao"):
                v = pil.get(k)
                if isinstance(v, str) and v.strip():
                    saida["pilula"][k] = v.strip()
                else:
                    saida["pilula"][k] = reserva["pilula"][k]
                    problemas.append(Problema(f"pilula.{k}", "estrutura", "", f"falta pilula.{k}"))
            rot = bruto.get("roteiro_audio")
            if isinstance(rot, str) and len(rot.split()) >= 80:
                saida["roteiro_audio"] = rot.strip()
            else:
                saida["roteiro_audio"] = reserva["roteiro_audio"]
                problemas.append(Problema("roteiro_audio", "estrutura", "", "roteiro_audio ausente ou curto demais"))
            return saida, problemas

        return self._ciclo("fechamento", lambda compacto: (prompt, verificador, reserva, estrutura))

    def _fechamento_automatico(self, blocos_txt, blocos_cfg, ndf, turno, data_hora, resumo_coleta) -> dict:
        if ndf:
            pilula = {
                "titulo": f"NDF teórico de {ndf['dc']} dias: o carrego entre juros em reais e em dólares",
                "analise": (f"Com spot de R$ {fmt(ndf['spot'], 4)}, taxa em reais de {fmt(ndf['taxa_brl_aa'], 2)}% a.a. "
                            f"e cupom cambial de referência de {fmt(ndf['cupom_aa'], 2)}% a.a., o câmbio a termo teórico "
                            f"para {ndf['dc']} dias corridos ({ndf['du']} dias úteis) é R$ {fmt(ndf['ndf'], 4)}, "
                            f"{fmt(ndf['pontos_forward'], 4)} acima do spot. Essa diferença é o carrego: quem vende "
                            "dólar a termo recebe o diferencial de juros entre as duas moedas."),
                "conclusao": ("Para receitas futuras em dólar, a trava via NDF ou dólar futuro incorpora esse carrego; "
                              "compare com o preço da saca nas praças antes de definir o hedge."),
            }
        else:
            pilula = {"titulo": "Pílula indisponível", "analise": "Sem dados suficientes para o cálculo do NDF neste turno.",
                      "conclusao": "—"}
        roteiro = (f"Boa tarde a todos da mesa e parceiros do campo. Este é o boletim do turno de {turno}, {data_hora}. "
                   + " ".join(f"{b['titulo'].split(' ', 1)[-1]}: {blocos_txt[b['id']]['resumo_curto']}"
                              for b in blocos_cfg)
                   + " Vamos às tabelas e ao painel.")
        return {
            "escopo": (f"{turno.capitalize()} · {resumo_coleta.get('ok', 0)} de {resumo_coleta.get('total', 0)} indicadores "
                       f"verificados · {resumo_coleta.get('noticias', 0)} notícias de {resumo_coleta.get('fontes', 0)} fontes"),
            "pilula": pilula,
            "roteiro_audio": roteiro,
        }


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)
