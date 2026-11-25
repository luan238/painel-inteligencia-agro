"""Testes de ponta a ponta: internet simulada + IA simulada."""
import json

from agente import rede
from agente.__main__ import adicionar_fonte, checar_boletim, executar
from llm_falso import LLMFalso
from web_falsa import AGORA, WebFalsa

import yaml


def _boletim(cfg):
    return json.loads(cfg.caminho("json").read_text(encoding="utf-8"))


def test_config_do_repositorio_consistente(cfg):
    assert cfg.problemas() == []


def test_boletim_completo_com_ia_verificada(cfg, web):
    llm = LLMFalso(errar_em=("complexo_soja",))
    assert executar(cfg, agora=AGORA, turno="fechamento", llm=llm) == 0
    b = _boletim(cfg)
    texto = json.dumps(b, ensure_ascii=False)
    # o que a IA inventou na 1ª resposta NÃO chegou ao boletim
    for inventado in ("999,37", "N999", "site-inventado", "4ª alta"):
        assert inventado not in texto
    q = b["data_quality"]["texto"]
    assert q["respostas_reprovadas"] >= 1 and q["corrigidos_pela_ia"] >= 1 and q["campos_substituidos"] == 0
    feedback = [p for p in llm.prompts if "REPROVOU" in p]
    assert feedback and "999,37" in feedback[0] and "N999" in feedback[0]   # a IA recebeu a lista de problemas
    # formato exigido pelo painel
    assert checar_boletim(b, {s["url"] for bl in b["detailed_blocks_and_news"] for s in bl["news_sources"]} |
                          {l["url"] for bl in b["detailed_blocks_and_news"] for e in bl["strategic_directions_by_elo"]
                           for l in e["reference_links"]}) == []
    mtd = b["monthly_evolution_mtd"]
    assert all(len(a["daily_history"]) == mtd["days_elapsed"] == len(mtd["daily_dates"]) for a in mtd["assets"])
    assert b["ndf_parameters"]["spot"] == 5.7324 and b["ndf_parameters"]["du"] > 0
    md = cfg.caminho("relatorio_md").read_text(encoding="utf-8")
    for secao in ("🎧 1.", "📈 2.", "🌱 3.", "📅 4.", "🗓️ 5.", "🎯 6.", "💡 7.", "💻 8."):
        assert secao in md


def test_ia_teimosa_vira_texto_automatico(cfg, web):
    assert executar(cfg, agora=AGORA, turno="fechamento", llm=LLMFalso(errar_em=(), teimoso_em=("complexo_cafe",))) == 0
    b = _boletim(cfg)
    assert "999,37" not in json.dumps(b, ensure_ascii=False)
    assert b["data_quality"]["texto"]["campos_substituidos"] >= 1


def test_sem_ia_o_boletim_sai_assim_mesmo(cfg, web):
    class SemIA:
        configurado = False
        descricao = "sem IA"
    assert executar(cfg, agora=AGORA, turno="abertura", llm=SemIA()) == 0
    b = _boletim(cfg)
    assert b["data_quality"]["texto"]["modo"] == "sem_ia"
    assert "Abertura" in b["metadata"]["timestamp"]


def test_tudo_fora_do_ar_mantem_boletim_anterior(cfg):
    cfg.caminho("json").write_text('{"anterior": true}', encoding="utf-8")
    rede.definir_transporte(WebFalsa(falhar_tudo=True))
    try:
        rc = executar(cfg, agora=AGORA, turno="fechamento", llm=LLMFalso())
    finally:
        rede.definir_transporte(None)
    assert rc == 3
    assert json.loads(cfg.caminho("json").read_text(encoding="utf-8")) == {"anterior": True}


def test_adicionar_fonte_preserva_comentarios(raiz_tmp):
    original = (raiz_tmp / "config" / "fontes.yaml").read_text(encoding="utf-8")
    adicionar_fonte(raiz_tmp, "Portal Teste", "https://www.teste.com.br/", "Brasil", "noticias", "pt", "",
                    "Observação: com dois-pontos")
    novo = (raiz_tmp / "config" / "fontes.yaml").read_text(encoding="utf-8")
    assert novo.startswith(original.rstrip("\n")) and "FONTES CONFIÁVEIS" in novo
    fontes = yaml.safe_load(novo)["fontes"]
    assert fontes[-1]["nome"] == "Portal Teste" and fontes[-1]["observacao"] == "Observação: com dois-pontos"
    for ruim in [("Portal Teste", "https://outro.com/"), ("X", "javascript:alert(1)"), ("Y", 'https://a.com/"><script>')]:
        try:
            adicionar_fonte(raiz_tmp, *ruim)
            raise AssertionError("deveria recusar")
        except ValueError:
            pass


def test_formulario_da_issue():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from adicionar_fonte_issue import ler_formulario
    corpo = ("### Nome do site\n\nFarmnews\n\n### URL\n\nhttps://www.farmnews.com.br/\n\n### Região\n\nBrasil\n\n"
             "### Tipo de conteúdo\n\nNotícias e Cotações\n\n### Idioma\n\nPortuguês\n\n### Feed RSS (opcional)\n\n_No response_\n\n"
             "### Observação\n\n_No response_")
    assert ler_formulario(corpo) == {"nome": "Farmnews", "url": "https://www.farmnews.com.br/", "regiao": "Brasil",
                                     "tipo": "noticias_e_cotacoes", "idioma": "pt"}


def test_monitor_publica_so_quando_ha_cotacao_nova(cfg, web, tmp_path, monkeypatch):
    from datetime import timedelta
    from agente.__main__ import monitorar
    saida = tmp_path / "gh_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(saida))
    # sem boletim completo anterior: o monitor só espera
    assert monitorar(cfg, agora=AGORA) == 0 and not cfg.caminho("json").exists()
    assert executar(cfg, agora=AGORA, turno="meio_dia", llm=LLMFalso(errar_em=())) == 0
    completo = _boletim(cfg)
    # mesmas cotações: nada é republicado
    assert monitorar(cfg, agora=AGORA + timedelta(minutes=20)) == 0
    assert _boletim(cfg) == completo
    assert saida.read_text().strip().endswith("mudou=nao")
    # PTAX muda: o monitor republica só os números
    ptax = json.loads(web.ptax_json)
    ptax["value"][-1]["cotacaoVenda"] = 5.7811
    web.ptax_json = json.dumps(ptax)
    assert monitorar(cfg, agora=AGORA + timedelta(minutes=40)) == 0
    novo = _boletim(cfg)
    assert saida.read_text().strip().endswith("mudou=sim")
    assert "R$ 5,7811" in novo["market_indicators"]["cambio_e_energia"]["dolar_ptax"]
    assert novo["executive_summary"] == completo["executive_summary"]          # análise verificada preservada
    assert novo["data_quality"]["modo_atualizacao"] == "cotacoes"
    assert novo["data_quality"]["analise_gerada_em"] == completo["data_quality"]["gerado_em"]
    assert "monitor" in novo["metadata"]["timestamp"]
    card = next(a for a in novo["weekly_evolution_wtd"]["assets"] if a["asset"].startswith("Dólar PTAX"))
    assert card["current_value"] == 5.7811 and "5,7811" in card["weekly_driver"]  # texto do card acompanha o número
    assert checar_boletim(novo, {s["url"] for bl in novo["detailed_blocks_and_news"] for s in bl["news_sources"]} |
                          {l["url"] for bl in novo["detailed_blocks_and_news"] for e in bl["strategic_directions_by_elo"]
                           for l in e["reference_links"]}) == []


def test_fila_de_ias_real_remonta_prompt_enxuto_e_publica(cfg, web, monkeypatch):
    """ClienteLLM de verdade (HTTP simulado): a NVIDIA recusa o prompt completo (HTTP 413), o redator
    remonta o pedido enxuto, a NVIDIA responde; depois a cota acaba e o resto vai para a IA local."""
    import agente.llm as llm

    falso = LLMFalso(errar_em=())
    vistos = []

    class R:
        def __init__(self, status, texto="", conteudo=None):
            self.status_code, self.text, self.headers, self._c = status, texto, {}, conteudo

        def json(self):
            return {"choices": [{"message": {"content": self._c}}]}

    def post(url, json, headers, timeout, **kw):
        msgs = json["messages"]
        c = msgs[1]["content"]
        enxuto = "BLOCO:" not in c or '\n {' not in c          # bloco enxuto = JSON sem recuo (fechamento não muda)
        vistos.append(("nvidia" if "nvidia" in url else "local", enxuto))
        if "nvidia" in url:
            if not enxuto:
                return R(413, "Request Entity Too Large")
            if sum(1 for v in vistos if v[0] == "nvidia") > 3:
                return R(429, "Rate limit exceeded: requests per day")
        return R(200, conteudo=falso.completar(msgs))

    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm, "_local_no_ar", lambda base: True)
    cliente = llm.ClienteLLM(cfg.geral["llm"], env={"NVIDIA_API_KEY": "nvapi-teste"})
    assert [p.nome for p in cliente.provedores] == ["NVIDIA", "IA local"] and not cliente.compacto
    assert executar(cfg, agora=AGORA, turno="fechamento", llm=cliente) == 0
    b = _boletim(cfg)
    q = b["data_quality"]["texto"]
    assert q["modo"] == "ia_verificada" and q["blocos_com_ia"] == len(cfg.blocos) + 1
    assert q["modelo"].startswith("nvidia/nemotron-3-super-120b-a12b @ NVIDIA ×2 → qwen2.5:7b @ IA local ×4")
    assert vistos[0] == ("nvidia", False) and all(enx for _, enx in vistos[1:])    # 1 recusa e só prompt enxuto depois
    assert any("cota do dia" in e for e in q["erros_llm"])


def test_checar_fontes_e_boletim_sem_as_pastas_data_e_relatorios(cfg, web):
    """O envio pelo navegador do GitHub pula pastas só com .gitkeep: o agente cria o que faltar."""
    import shutil
    from agente.__main__ import checar_fontes
    for pasta in ("data", "relatorios"):
        shutil.rmtree(cfg.raiz / pasta, ignore_errors=True)
    assert checar_fontes(cfg) == 0
    assert (cfg.raiz / "data" / "checagem_fontes.json").exists()
    assert (cfg.raiz / "relatorios" / "checagem_fontes.md").exists()
    shutil.rmtree(cfg.raiz / "data")
    assert executar(cfg, agora=AGORA, turno="fechamento", llm=LLMFalso(errar_em=())) == 0


def test_projecoes_das_pracas_fisicas_com_volatilidade_de_referencia(cfg, web):
    """Praça com histórico curto ganha banda pela volatilidade do mercado de referência (B3), e o
    histórico dos contratos da B3 é carregado dos arquivos oficiais de pregões passados."""
    from agente.historico import Historico
    assert executar(cfg, agora=AGORA, turno="fechamento", llm=LLMFalso(errar_em=())) == 0
    assert web.arquivos_b3_antigos >= 20                         # carga do histórico (uma vez)
    hist = Historico(cfg.caminho("historico_csv"))
    assert len(hist.serie("milho_b3")) >= 22 and "carga do histórico" in str(hist.registro("milho_b3", min(hist.serie("milho_b3"))))
    linhas = {l["commodity"]: l for l in _boletim(cfg)["audit_panel_projections"]}
    milho = linhas["Milho Campinas-SP"]
    assert "histórico insuficiente" not in milho["short_term_target_23_oct"] and "R$" in milho["short_term_target_23_oct"]
    assert "de Milho B3" in milho["audit_trigger"] and "histórico próprio ainda tem" in milho["audit_trigger"]
    assert "Soja B3 × Dólar PTAX" in linhas["Soja Paranaguá-PR"]["audit_trigger"]
    assert "Boi Gordo B3" in linhas["Boi gordo SP"]["audit_trigger"]
    # a 2ª execução não baixa os arquivos antigos de novo
    antes = web.arquivos_b3_antigos
    assert executar(cfg, agora=AGORA, turno="fechamento", llm=LLMFalso(errar_em=())) == 0
    assert web.arquivos_b3_antigos == antes
