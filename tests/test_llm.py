"""Fila de provedores de IA: APIs gratuitas em ordem → IA local sem limite."""
import pytest

import agente.llm as llm


class Resp:
    def __init__(self, status, texto="", conteudo=None, headers=None):
        self.status_code, self.text, self.headers = status, texto, headers or {}
        self._conteudo = conteudo

    def json(self):
        return {"choices": [{"message": {"content": self._conteudo}}]}


CFG = {
    "provedores": [
        {"nome": "Groq", "base_url": "https://api.groq.com/openai/v1", "chave_env": "GROQ_API_KEY",
         "modelo_env": "GROQ_MODEL", "modelos": ["openai/gpt-oss-120b", "openai/gpt-oss-20b"],
         "compacto": True, "max_tokens": 3000, "parametros_extras": {"reasoning_effort": "low"}},
        {"nome": "NVIDIA", "base_url": "https://integrate.api.nvidia.com/v1", "chave_env": "NVIDIA_API_KEY",
         "modelos": ["nvidia/nemotron-a", "nvidia/nemotron-b"]},
        {"nome": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
         "chave_env": "GEMINI_API_KEY", "modelos": ["gemini-flash-lite-latest"]},
        {"nome": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "chave_env": "OPENROUTER_API_KEY",
         "modelos": ["openrouter/free"]},
    ],
    "local": {"modelo": "qwen2.5:7b"},
}
TODAS = {"GROQ_API_KEY": "gsk_x", "NVIDIA_API_KEY": "nvapi-x", "GEMINI_API_KEY": "AIza-x", "OPENROUTER_API_KEY": "sk-or-x"}
MSG = [{"role": "user", "content": "oi"}]


@pytest.fixture
def relogio(monkeypatch):
    """Relógio falso: sleep() avança o tempo na hora (testes rápidos e determinísticos)."""
    t = {"agora": 1000.0, "dormiu": []}
    monkeypatch.setattr(llm.time, "monotonic", lambda: t["agora"])

    def dormir(s):
        t["dormiu"].append(round(s, 1))
        t["agora"] += s
    monkeypatch.setattr(llm.time, "sleep", dormir)
    monkeypatch.setattr(llm, "_local_no_ar", lambda base: True)
    return t


def roteiro(monkeypatch, respostas):
    """respostas: {trecho_da_url: [Resp, ...]} — cada chamada consome a próxima resposta daquele host."""
    chamadas = []

    def post(url, json, headers, timeout, **kw):
        chamadas.append((url, json["model"], json.get("max_tokens"), dict(json)))
        for trecho, fila in respostas.items():
            if trecho in url:
                return fila.pop(0) if len(fila) > 1 else fila[0]
        raise AssertionError(f"chamada inesperada: {url}")
    monkeypatch.setattr(llm.requests, "post", post)
    return chamadas


def ok(txt='{"ok": true}'):
    return Resp(200, conteudo=txt)


def test_ordem_da_fila_e_provedor_sem_chave_pulado(relogio):
    c = llm.ClienteLLM(CFG, env={"GROQ_API_KEY": "gsk_x", "GEMINI_API_KEY": "AIza"})
    assert [p.nome for p in c.provedores] == ["Groq", "Google Gemini", "IA local"]   # NVIDIA sem chave: pulada
    assert c.provedores[-1].local and c.compacto                                     # Groq usa prompt enxuto
    c2 = llm.ClienteLLM(CFG, env={**TODAS, "GROQ_MODEL": "qwen/qwen3.8-27b"}, usar_local=False)
    assert c2.provedores[0].modelos == ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert [p.nome for p in c2.provedores] == ["Groq", "NVIDIA", "Google Gemini", "OpenRouter"]


def test_cascata_quatro_apis_e_tudo_vai_para_a_ia_local(relogio, monkeypatch):
    chamadas = roteiro(monkeypatch, {
        "groq": [Resp(429, "Rate limit reached on tokens per day (TPD): Limit 200000, Used 199990")],
        "nvidia": [Resp(401, "Unauthorized")],
        "googleapis": [ok('{"de": "gemini"}'),
                       Resp(429, '{"error": {"message": "Quota exceeded", "details": [{"quotaId": '
                                 '"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}')],
        "openrouter": [Resp(429, "Rate limit exceeded: free-models-per-day")],
        "localhost": [ok('{"de": "local"}')],
    })
    c = llm.ClienteLLM(CFG, env=TODAS)
    assert c.completar(MSG) == '{"de": "gemini"}'
    assert [u[0].split("/")[2] for u in chamadas] == ["api.groq.com", "integrate.api.nvidia.com",
                                                      "generativelanguage.googleapis.com"]
    assert c.completar(MSG) == '{"de": "local"}'           # Gemini esgota a cota do dia → OpenRouter também → local
    assert [p.esgotado for p in c.provedores] == [True, True, True, True, False]
    assert c.completar(MSG) == '{"de": "local"}'           # o resto da execução vai direto para a IA local
    assert sum("groq" in u[0] for u in chamadas) == 1 and sum("nvidia" in u[0] for u in chamadas) == 1
    assert c.resumo_uso == "gemini-flash-lite-latest @ Google Gemini ×1 → qwen2.5:7b @ IA local ×2"
    assert any("cota do dia" in e for e in c.erros) and any("chave recusada" in e for e in c.erros)
    assert relogio["dormiu"] == [] or max(relogio["dormiu"]) <= 2.0   # nenhuma espera longa à toa


def test_limite_por_minuto_pausa_e_depois_volta_para_a_preferida(relogio, monkeypatch):
    chamadas = roteiro(monkeypatch, {
        "groq": [Resp(429, "Rate limit reached on tokens per minute (TPM): Limit 8000, Used 7000, Requested 3000. "
                           "Please try again in 7.5s.", headers={"retry-after": "8"}), ok('{"de": "groq"}')],
        "nvidia": [ok('{"de": "nvidia"}')],
    })
    c = llm.ClienteLLM(CFG, env={"GROQ_API_KEY": "g", "NVIDIA_API_KEY": "n"}, usar_local=False)
    assert c.completar(MSG) == '{"de": "nvidia"}'           # Groq descansando → NVIDIA atende na hora
    assert not c.provedores[0].esgotado and c.provedores[0].pausado_ate > relogio["agora"]
    relogio["agora"] += 10                                  # passou a pausa
    assert c.completar(MSG) == '{"de": "groq"}'             # volta para a preferida
    assert [u[0].split("/")[2] for u in chamadas] == ["api.groq.com", "integrate.api.nvidia.com", "api.groq.com"]


def test_espera_a_api_em_vez_de_cair_na_ia_local_lenta(relogio, monkeypatch):
    roteiro(monkeypatch, {
        "groq": [Resp(429, "Please try again in 1m2s"), ok('{"de": "groq"}')],
        "localhost": [ok('{"de": "local"}')],
    })
    c = llm.ClienteLLM(CFG, env={"GROQ_API_KEY": "g"})
    assert c.completar(MSG, compacto=True) == '{"de": "groq"}'
    assert 62.0 <= max(relogio["dormiu"]) <= 64.0          # esperou ~1 min pela Groq
    assert c.provedores[1].respostas == 0                  # a IA local nem foi chamada


def test_espera_longa_tira_da_fila_e_pausas_seguidas_tambem(relogio, monkeypatch):
    roteiro(monkeypatch, {
        "groq": [Resp(429, "Please try again in 7m12s")],
        "nvidia": [Resp(503, "busy")],
        "localhost": [ok()],
    })
    c = llm.ClienteLLM({**CFG, "max_pausas_por_provedor": 2}, env={"GROQ_API_KEY": "g", "NVIDIA_API_KEY": "n"})
    assert c.completar(MSG, compacto=True) == '{"ok": true}'
    assert c.provedores[0].esgotado and "liberação só em 7 min" in c.erros[0]
    nv = c.provedores[1]                                    # 3 falhas seguidas (> 2) → fora da fila por 5 min
    assert not nv.esgotado and nv.volta_em > relogio["agora"] and "fora da fila por 5 min" in c.erros[-1]


def test_instabilidade_troca_de_modelo_e_a_api_volta_depois(relogio, monkeypatch):
    chamadas = roteiro(monkeypatch, {
        "generativelanguage": [Resp(503, "model is overloaded"), ok('{"de": "gemini-2"}'),
                               Resp(503, "x"), Resp(503, "x"), Resp(503, "x"), Resp(503, "x"), Resp(503, "x"),
                               Resp(503, "x"), Resp(503, "x"), Resp(503, "x"), Resp(503, "x"), Resp(503, "x"),
                               ok('{"de": "gemini-de-volta"}')],
        "localhost": [ok('{"de": "local"}')],
    })
    cfg = {**CFG, "max_pausas_por_provedor": 2, "provedores": [
        {"nome": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
         "chave_env": "GEMINI_API_KEY", "modelos": ["gemini-flash-lite-latest", "gemini-flash-latest"]}]}
    c = llm.ClienteLLM(cfg, env={"GEMINI_API_KEY": "g"})
    assert c.completar(MSG, compacto=True) == '{"de": "gemini-2"}'          # 503 num modelo → o outro na hora
    assert [m for _, m, _, _ in chamadas] == ["gemini-flash-lite-latest", "gemini-flash-latest"]
    assert c.completar(MSG, compacto=True) == '{"de": "local"}'             # instável de vez → IA local…
    relogio["agora"] += 301
    assert c.completar(MSG, compacto=True) == '{"de": "gemini-de-volta"}'   # …e 5 min depois a API volta


def test_modelo_inexistente_usa_o_proximo_da_lista(relogio, monkeypatch):
    chamadas = roteiro(monkeypatch, {"nvidia": [Resp(404, "Function not found for account"), ok()]})
    c = llm.ClienteLLM(CFG, env={"NVIDIA_API_KEY": "n"}, usar_local=False)
    assert c.completar(MSG) == '{"ok": true}'
    assert [m for _, m, _, _ in chamadas] == ["nvidia/nemotron-a", "nvidia/nemotron-b"]
    assert c.provedores[0].modelo == "nvidia/nemotron-b"


def test_pedido_grande_demais_reduz_teto_ou_pede_prompt_enxuto(relogio, monkeypatch):
    chamadas = roteiro(monkeypatch, {
        "groq": [Resp(413, "Request too large for model on tokens per minute (TPM): Limit 8000, Requested 8600"), ok()],
        "nvidia": [Resp(413, "Request Entity Too Large")],
    })
    c = llm.ClienteLLM(CFG, env={"GROQ_API_KEY": "g"}, usar_local=False)
    assert c.completar(MSG, compacto=True) == '{"ok": true}'
    assert [t for _, _, t, _ in chamadas] == [3000, 2200]   # teto de resposta reduzido em 800 → cabe no limite
    c = llm.ClienteLLM(CFG, env={"NVIDIA_API_KEY": "n"}, usar_local=False)
    with pytest.raises(llm.TrocaDeFormato):                 # prompt completo grande demais → redator remonta enxuto
        c.completar(MSG, compacto=False)
    assert c.provedores[0].compacto and not c.provedores[0].esgotado


def test_troca_de_formato_quando_a_vez_e_da_ia_local(relogio, monkeypatch):
    roteiro(monkeypatch, {"nvidia": [Resp(429, "requests per day exceeded")], "localhost": [ok()]})
    c = llm.ClienteLLM(CFG, env={"NVIDIA_API_KEY": "n"})
    assert not c.compacto
    with pytest.raises(llm.TrocaDeFormato):
        c.completar(MSG, compacto=False)                   # NVIDIA esgotou → a vez é da local, que pede prompt enxuto
    assert c.compacto and c.completar(MSG, compacto=True) == '{"ok": true}'


def test_parametro_extra_recusado_e_modo_json_desligado(relogio, monkeypatch):
    chamadas = roteiro(monkeypatch, {"groq": [
        Resp(400, "unsupported parameter: reasoning_effort"),
        Resp(400, "json_validate_failed: Failed to generate JSON"),
        ok("```json\n{\"ok\": 1}\n```")]})
    c = llm.ClienteLLM(CFG, env={"GROQ_API_KEY": "g"}, usar_local=False)
    assert llm.extrair_json(c.completar(MSG)) == {"ok": 1}
    assert "reasoning_effort" in chamadas[0][3] and "reasoning_effort" not in chamadas[1][3]
    assert "response_format" in chamadas[1][3] and "response_format" not in chamadas[2][3]


def test_ia_local_em_preparo_e_aguardada(relogio, monkeypatch):
    monkeypatch.setattr(llm, "_local_no_ar", lambda base: False)       # ainda instalando em segundo plano
    prontos = iter([False, False, True])
    monkeypatch.setattr(llm, "_local_pronto", lambda base, modelo: next(prontos))
    roteiro(monkeypatch, {"localhost": [ok()]})
    assert llm.ClienteLLM(CFG, env={}).provedores == []                # fora do GitHub: sem servidor, sem local
    c = llm.ClienteLLM(CFG, env={"OLLAMA_EM_PREPARO": "1"})
    assert c.configurado and c.completar(MSG, compacto=True) == '{"ok": true}'
    assert relogio["dormiu"] == [10, 10]


def test_preparo_da_ia_local_falhou(relogio, monkeypatch, tmp_path):
    status = tmp_path / "status"
    status.write_text("falhou")
    c = llm.ClienteLLM(CFG, env={"OLLAMA_EM_PREPARO": "1", "IA_LOCAL_STATUS": str(status)})
    with pytest.raises(llm.ErroLLM, match="nenhuma IA disponível"):
        c.completar(MSG, compacto=True)
    assert "instalação da IA local falhou" in c.erros[0]


def test_api_extra_generica_e_sem_nenhuma_ia(relogio, monkeypatch):
    env = {"LLM_BASE_URL": "https://api.cerebras.ai/v1", "LLM_API_KEY": "csk", "LLM_MODEL": "gpt-oss-120b"}
    c = llm.ClienteLLM(CFG, env={**env, "GROQ_API_KEY": "g"}, usar_local=False)
    assert [p.nome for p in c.provedores] == ["Groq", "api.cerebras.ai"]
    monkeypatch.setattr(llm, "_local_no_ar", lambda base: False)
    nada = llm.ClienteLLM(CFG, env={})
    assert not nada.configurado and nada.descricao == "sem IA"
    with pytest.raises(llm.ErroLLM, match="nenhuma IA configurada"):
        nada.completar(MSG)


@pytest.mark.parametrize("texto,esperado", [("7.5s", 7.5), ("1m30.5s", 90.5), ("450ms", 0.45), ("2 seconds", 2.0)])
def test_leitura_do_tempo_de_espera(texto, esperado):
    assert llm._segundos(texto) == pytest.approx(esperado)
    assert llm._espera_sugerida(Resp(429, f"Please try again in {texto}.")) == pytest.approx(esperado)
    assert llm._espera_sugerida(Resp(429, '{"retryDelay": "33s"}')) == 33.0


def test_testar_ia_mostra_quem_responde(relogio, monkeypatch):
    roteiro(monkeypatch, {"groq": [ok()], "nvidia": [Resp(401, "bad key")],
                          "googleapis": [Resp(429, "Please retry in 20s")]})
    linhas = llm.testar_provedores(CFG, env={"GROQ_API_KEY": "g", "NVIDIA_API_KEY": "n", "GEMINI_API_KEY": "x"})
    assert [(l["nome"], l["ok"]) for l in linhas] == [("Groq", True), ("NVIDIA", False), ("Google Gemini", True),
                                                       ("OpenRouter", None)]
    assert "OPENROUTER_API_KEY" in linhas[3]["msg"] and "chave recusada" in linhas[1]["msg"]
