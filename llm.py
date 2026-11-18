"""Cliente de IA com fila de provedores gratuitos: nunca "dá pau" por limite de plano.

Ordem de uso (config/configuracoes.yaml → llm.provedores):
  1..N  APIs gratuitas e rápidas, de cima para baixo (padrão: Groq → NVIDIA Nemotron →
        Google Gemini → OpenRouter). Cada uma só entra se a chave dela existir nos secrets.
  N+1   API extra opcional (secrets LLM_BASE_URL, LLM_API_KEY, LLM_MODEL).
  último IA LOCAL (Ollama no próprio runner): gratuita e SEM limite — a rede de segurança.

Regras de troca:
  - limite por minuto (HTTP 429 com espera curta): a API "descansa" e o pedido vai para a
    próxima da fila; o bloco seguinte volta a tentar a preferida. Se só sobrar a IA local,
    vale mais esperar a API alguns segundos do que ir para a local (que leva minutos).
  - cota do dia, falta de crédito, chave recusada ou modelo inexistente: a API sai da fila
    até o fim desta execução (na próxima execução ela volta a ser tentada).
  - pedido grande demais para o plano grátis (HTTP 413): a API passa a receber o prompt
    enxuto (o redator remonta o pedido) ou um teto menor de resposta.
  - quando todas as APIs se esgotam, tudo vai para a IA local.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

import requests


class ErroLLM(Exception):
    """Nenhuma IA respondeu (ou, dentro do cliente, esta API saiu da fila)."""


class TrocaDeFormato(Exception):
    """O próximo provedor precisa do prompt enxuto: o redator remonta o pedido e chama de novo."""

    def __init__(self, compacto: bool):
        super().__init__("prompt enxuto" if compacto else "prompt completo")
        self.compacto = compacto


class _Pausa(Exception):
    def __init__(self, segundos: float, motivo: str):
        super().__init__(motivo)
        self.segundos = segundos


class _GrandeDemais(Exception):
    pass


_SEM_PROXY = {"http": None, "https": None}     # localhost nunca passa por proxy corporativo
_DIARIO = re.compile(r"per[ _-]?day|daily|\bTPD\b|\bRPD\b", re.I)
_GRANDE = re.compile(r"too large|context[ _]length|maximum context|tokens?_limit|reduce the length|"
                     r"prompt is too long|request too big|exceeds? the (?:max|limit)", re.I)
_SEM_MODELO = re.compile(r"model\b[^\n]{0,100}?(?:not found|does not exist|is not supported|unsupported|"
                         r"not available|decommissioned|deprecated|no longer)|unknown model|invalid model|"
                         r"no such model|model_not_found|not a valid model", re.I)
_MENCIONA_JSON = re.compile(r"json|response_format", re.I)
_ESPERA_TXT = re.compile(r"(?:try again|retry) in\s*([\d.]+\s*(?:ms|seconds?|s)\b|(?:[\d.]+h)?(?:[\d.]+m(?!s))?(?:[\d.]+s)?)", re.I)
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"([\d.]+)s"')
_LIMITE_PEDIDO = re.compile(r"Limit\s*(\d+)\s*,\s*Requested\s*(\d+)", re.I)


def _host(url: str) -> str:
    return re.sub(r"^https?://", "", url).split("/")[0]


def _segundos(txt: str) -> float | None:
    """'7.5s', '1m30.5s', '450ms', '2 seconds' → segundos."""
    txt = (txt or "").strip().lower()
    m = re.fullmatch(r"([\d.]+)\s*(ms|seconds?|s)", txt)
    if m:
        v = float(m.group(1))
        return v / 1000 if m.group(2) == "ms" else v
    partes = re.findall(r"([\d.]+)(h|ms|m|s)", txt)
    if not partes:
        return None
    return sum(float(v) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[u] for v, u in partes)


def _espera_sugerida(r) -> float | None:
    cab = getattr(r, "headers", None) or {}
    valor = cab.get("Retry-After") or cab.get("retry-after")
    if valor:
        try:
            return float(valor)
        except ValueError:
            pass
    texto = getattr(r, "text", "") or ""
    m = _RETRY_DELAY.search(texto)
    if m:
        return float(m.group(1))
    m = _ESPERA_TXT.search(texto)
    return _segundos(m.group(1)) if m and m.group(1) else None


@dataclass
class Provedor:
    nome: str
    base_url: str
    api_key: str
    modelos: list
    timeout: int
    max_tokens: int
    local: bool = False
    compacto: bool = False                 # recebe o prompt enxuto (menos notícias, resumos curtos)
    extras: dict = field(default_factory=dict)
    json_mode: bool = True
    esgotado: bool = False
    pausado_ate: float = 0.0
    pausas: int = 0                        # pausas seguidas sem nenhuma resposta boa
    ultima: float = 0.0
    aguardar_preparo: bool = False         # IA local ainda sendo instalada em segundo plano
    respostas: int = 0

    @property
    def modelo(self) -> str:
        return self.modelos[0]

    @property
    def descricao(self) -> str:
        return f"{self.modelo} @ {'IA local' if self.local else self.nome}"


def _local_no_ar(base_url: str) -> bool:
    """Confere rápido se há um servidor Ollama/compatível respondendo."""
    raiz = re.sub(r"/v1/?$", "", base_url)
    for url in (raiz + "/api/version", base_url + "/models"):
        try:
            if requests.get(url, timeout=3, proxies=_SEM_PROXY).status_code < 500:
                return True
        except requests.RequestException:
            continue
    return False


def _local_pronto(base_url: str, modelo: str) -> bool:
    """O servidor local está no ar e o modelo já foi baixado?"""
    raiz = re.sub(r"/v1/?$", "", base_url)
    try:
        r = requests.get(raiz + "/api/tags", timeout=5, proxies=_SEM_PROXY)
        if r.status_code == 200:
            nomes = {m.get("name") for m in r.json().get("models", [])} | \
                    {m.get("model") for m in r.json().get("models", [])}
            return modelo in nomes or f"{modelo}:latest" in nomes
        r = requests.get(base_url + "/models", timeout=5, proxies=_SEM_PROXY)
        return r.status_code == 200 and any(m.get("id") == modelo for m in r.json().get("data", []))
    except (requests.RequestException, ValueError, AttributeError):
        return False


def _ler_status(caminho: str) -> str:
    try:
        with open(caminho, encoding="utf-8") as f:
            return f.read().strip().lower()
    except OSError:
        return ""


def _provedores_api(cfg: dict, env) -> list[Provedor]:
    lista: list[Provedor] = []
    tempo, maxt = int(cfg.get("tempo_limite_s", 180)), int(cfg.get("max_tokens", 5000))
    for item in cfg.get("provedores") or []:
        if not isinstance(item, dict) or item.get("ativo", True) is False:
            continue
        chave = (env.get(str(item.get("chave_env") or "")) or "").strip()
        base = str(item.get("base_url") or "").rstrip("/")
        if not chave or not base:
            continue                                   # sem chave nos secrets: provedor pulado
        modelos = list(item.get("modelos") or ([item["modelo"]] if item.get("modelo") else []))
        escolhido = (env.get(str(item.get("modelo_env") or "")) or "").strip()
        if escolhido:                                  # variável do GitHub tem prioridade; a lista vira reserva
            modelos = [escolhido] + [m for m in modelos if m != escolhido]
        if not modelos:
            continue
        lista.append(Provedor(
            nome=str(item.get("nome") or _host(base)), base_url=base, api_key=chave, modelos=modelos,
            timeout=int(item.get("tempo_limite_s", tempo)), max_tokens=int(item.get("max_tokens", maxt)),
            compacto=bool(item.get("compacto", False)), extras=dict(item.get("parametros_extras") or {})))
    if env.get("LLM_BASE_URL") and env.get("LLM_MODEL"):
        base = env["LLM_BASE_URL"].rstrip("/")
        lista.append(Provedor(_host(base), base, env.get("LLM_API_KEY") or "", [env["LLM_MODEL"]], tempo, maxt,
                              compacto=env.get("LLM_COMPACTO") == "1"))
    return lista


class ClienteLLM:
    def __init__(self, cfg_llm: dict | None = None, env=None, usar_local: bool = True):
        env = env if env is not None else os.environ
        cfg = cfg_llm or {}
        self.temperatura = float(cfg.get("temperatura", 0.25))
        self.pausa = float(cfg.get("pausa_entre_chamadas_s", 2))
        self.espera_max = float(cfg.get("espera_maxima_s", 90))
        self.max_pausas = int(cfg.get("max_pausas_por_provedor", 4))
        self.provedores: list[Provedor] = _provedores_api(cfg, env)
        loc = cfg.get("local", {}) or {}
        self.espera_preparo = float(loc.get("espera_preparo_s", 900))
        self.status_preparo = env.get("IA_LOCAL_STATUS", "")
        if usar_local and loc.get("ativo", True) and env.get("LLM_LOCAL_DESATIVAR") != "1":
            base = (env.get("LLM_LOCAL_URL") or loc.get("base_url") or "http://localhost:11434/v1").rstrip("/")
            em_preparo = env.get("OLLAMA_EM_PREPARO") == "1"     # o workflow instala o Ollama em segundo plano
            if em_preparo or _local_no_ar(base):
                self.provedores.append(Provedor(
                    "IA local", base, "", [env.get("LLM_LOCAL_MODEL") or loc.get("modelo", "qwen2.5:7b")],
                    int(loc.get("tempo_limite_s", 1500)), int(loc.get("max_tokens", 3000)), local=True,
                    compacto=bool(loc.get("compacto", True)), aguardar_preparo=em_preparo))
        self.usados: list[str] = []
        self.erros: list[str] = []
        self.chamadas = 0

    # ----------------------------------------------------------- estado
    @property
    def configurado(self) -> bool:
        return any(not p.esgotado for p in self.provedores)

    @property
    def compacto(self) -> bool:
        """True quando o próximo pedido vai para um provedor que precisa do prompt enxuto."""
        p = self._escolher(esperar=False)
        return bool(p and p.compacto)

    @property
    def descricao(self) -> str:
        if self.usados:
            return self.resumo_uso
        return " → ".join(p.descricao for p in self.provedores) if self.provedores else "sem IA"

    @property
    def resumo_uso(self) -> str:
        """Quem respondeu e quantas vezes, na ordem em que entrou: 'gpt-oss @ Groq ×4 → … @ NVIDIA ×2'."""
        cont = {p.descricao: p.respostas for p in self.provedores}
        return " → ".join(f"{d} ×{cont.get(d, 1)}" for d in self.usados)

    # ----------------------------------------------------------- escolha
    def _escolher(self, esperar: bool) -> Provedor | None:
        agora = time.monotonic()
        ativos = [p for p in self.provedores if not p.esgotado]
        if not ativos:
            return None
        for p in ativos:                                  # 1ª API livre, na ordem de preferência
            if not p.local and p.pausado_ate <= agora:
                return p
        em_pausa = sorted((p for p in ativos if not p.local), key=lambda q: q.pausado_ate)
        local = next((p for p in ativos if p.local), None)
        if em_pausa and (local is None or em_pausa[0].pausado_ate - agora <= self.espera_max):
            p = em_pausa[0]                               # esperar alguns segundos sai mais rápido que a IA local
            if esperar:
                time.sleep(max(0.0, p.pausado_ate - agora))
                p.pausado_ate = 0.0
            return p
        return local

    def _tirar(self, p: Provedor, motivo: str) -> None:
        p.esgotado = True
        self.erros.append(f"{p.descricao}: {motivo}")

    # ----------------------------------------------------------- chamada
    def completar(self, mensagens: list[dict], compacto: bool | None = None) -> str:
        """Envia o pedido ao melhor provedor disponível. `compacto` diz como o prompt foi montado
        (None = o chamador não sabe remontar); se o provedor da vez precisar do prompt enxuto e o
        pedido veio completo, levanta TrocaDeFormato para o redator remontar."""
        while True:
            p = self._escolher(esperar=True)
            if p is None:
                raise ErroLLM("nenhuma IA disponível — " + " | ".join(self.erros[-4:]) if self.erros
                              else "nenhuma IA configurada")
            if compacto is False and p.compacto:
                raise TrocaDeFormato(True)
            try:
                if p.local and p.aguardar_preparo:
                    self._aguardar_local(p)
                texto = self._chamar(p, mensagens)
            except _Pausa as e:
                p.pausas += 1
                if p.pausas > self.max_pausas or e.segundos > self.espera_max:
                    self._tirar(p, f"{e} — fora da fila nesta execução")
                else:
                    p.pausado_ate = time.monotonic() + e.segundos
                continue
            except _GrandeDemais as e:
                if not p.compacto and compacto is False:
                    p.compacto = True                     # daqui em diante esta API recebe o prompt enxuto
                    raise TrocaDeFormato(True) from e
                self._tirar(p, f"pedido grande demais para o plano grátis ({e})")
                continue
            except ErroLLM as e:
                self._tirar(p, str(e))
                continue
            p.pausas = 0
            p.respostas += 1
            self.chamadas += 1
            if p.descricao not in self.usados:
                self.usados.append(p.descricao)
            return texto

    def _aguardar_local(self, p: Provedor) -> None:
        limite = time.monotonic() + self.espera_preparo
        while True:
            if _ler_status(self.status_preparo) == "falhou":
                raise ErroLLM("a instalação da IA local falhou (veja o passo 'Preparar a IA local' no log)")
            if _local_pronto(p.base_url, p.modelo):
                p.aguardar_preparo = False
                return
            if time.monotonic() >= limite:
                raise ErroLLM("a IA local não ficou pronta a tempo")
            time.sleep(10)

    def _chamar(self, p: Provedor, mensagens: list[dict]) -> str:
        espera = self.pausa - (time.monotonic() - p.ultima)
        if p.ultima and espera > 0 and not p.local:
            time.sleep(espera)
        cabecalhos = {"Content-Type": "application/json"}
        if p.api_key:
            cabecalhos["Authorization"] = f"Bearer {p.api_key}"
        if "openrouter.ai" in p.base_url:
            cabecalhos["X-Title"] = "Agro Intel Agent"
        for _ in range(8):                      # ajustes automáticos: modo JSON, parâmetros extras, modelo reserva
            payload = {"model": p.modelo, "messages": mensagens, "temperature": self.temperatura,
                       "max_tokens": p.max_tokens, **p.extras}
            if p.json_mode:
                payload["response_format"] = {"type": "json_object"}
            try:
                r = requests.post(f"{p.base_url}/chat/completions", json=payload, headers=cabecalhos,
                                  timeout=p.timeout, **({"proxies": _SEM_PROXY} if p.local else {}))
            except requests.Timeout as e:
                if p.local:
                    raise ErroLLM("a IA local demorou demais para responder") from e
                raise _Pausa(20, "tempo de resposta esgotado") from e
            except requests.RequestException as e:
                raise _Pausa(10 if p.local else 20, f"falha de conexão ({type(e).__name__})") from e
            finally:
                p.ultima = time.monotonic()
            st, txt = r.status_code, (r.text or "")
            if st == 429:
                if p.local:
                    raise _Pausa(10, "IA local ocupada")
                if _DIARIO.search(txt):
                    raise ErroLLM(f"cota do dia esgotada (HTTP 429): {txt[:160]}")
                seg = _espera_sugerida(r)
                seg = 20.0 if seg is None else seg + 1
                if seg > self.espera_max:
                    raise ErroLLM(f"limite atingido; liberação só em {seg / 60:.0f} min (HTTP 429)")
                raise _Pausa(seg, f"limite por minuto (HTTP 429), pausa de {seg:.0f}s")
            if st in (401, 403):
                raise ErroLLM(f"chave recusada (HTTP {st}) — confira o secret")
            if st == 402:
                raise ErroLLM("sem créditos na conta (HTTP 402)")
            if st == 413 or (st in (400, 422) and _GRANDE.search(txt)):
                m = _LIMITE_PEDIDO.search(txt)
                if m:                                       # ex.: Groq conta prompt + teto de resposta no limite por minuto
                    excesso = int(m.group(2)) - int(m.group(1)) + 200
                    if p.max_tokens - excesso >= 1200:
                        p.max_tokens -= excesso
                        continue
                raise _GrandeDemais(f"HTTP {st}")
            if st == 404 or (st in (400, 422) and _SEM_MODELO.search(txt)):
                if len(p.modelos) > 1:
                    self.erros.append(f"{p.descricao}: modelo indisponível, usando o próximo da lista")
                    p.modelos.pop(0)
                    continue
                raise ErroLLM(f"modelo indisponível (HTTP {st}): {txt[:160]}")
            if st in (400, 422):
                if p.extras and (any(k in txt for k in p.extras) or not (p.json_mode and _MENCIONA_JSON.search(txt))):
                    p.extras = {}                           # parâmetro opcional recusado: segue sem ele
                    continue
                if p.json_mode and _MENCIONA_JSON.search(txt):
                    p.json_mode = False                     # sem modo JSON: o JSON é pedido só pelo prompt
                    continue
                raise ErroLLM(f"pedido recusado (HTTP {st}): {txt[:200]}")
            if st >= 500:
                raise _Pausa(15, f"instabilidade no servidor (HTTP {st})")
            if st >= 400:
                raise ErroLLM(f"HTTP {st}: {txt[:200]}")
            try:
                return r.json()["choices"][0]["message"].get("content") or ""
            except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
                raise ErroLLM(f"resposta inesperada: {txt[:200]}") from e
        raise ErroLLM("ajustes automáticos esgotados sem resposta válida")


def extrair_json(texto: str) -> dict:
    """Extrai o objeto JSON da resposta (tolera ```json, <think>...</think> e texto extra)."""
    t = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip())
    inicio, fim = t.find("{"), t.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("resposta sem objeto JSON")
    return json.loads(t[inicio:fim + 1])


def testar_provedores(cfg_llm: dict | None, env=None) -> list[dict]:
    """Manda um pedido curtinho a cada API da fila (confere chaves e modelos sem gerar boletim)."""
    env = env if env is not None else os.environ
    cfg = cfg_llm or {}
    cli = ClienteLLM(cfg, env=env, usar_local=False)
    restantes = list(cli.provedores)
    linhas = []
    teste = [{"role": "system", "content": "Responda apenas com JSON."},
             {"role": "user", "content": 'Responda exatamente: {"ok": true}'}]
    for item in cfg.get("provedores") or []:
        if not isinstance(item, dict) or item.get("ativo", True) is False:
            continue
        nome = str(item.get("nome") or _host(str(item.get("base_url", ""))))
        p = next((q for q in restantes if q.nome == nome), None)
        if p is None:
            linhas.append({"nome": nome, "ok": None, "modelo": "—",
                           "msg": f"sem chave: crie o secret {item.get('chave_env')} para usar"})
            continue
        restantes.remove(p)
        linhas.append(_testar_um(cli, p, teste))
    for p in restantes:                                          # API extra (LLM_BASE_URL)
        linhas.append(_testar_um(cli, p, teste))
    return linhas


def _testar_um(cli: ClienteLLM, p: Provedor, teste: list[dict]) -> dict:
    p.max_tokens = min(p.max_tokens, 400)
    inicio = time.monotonic()
    try:
        cli._chamar(p, teste)
        return {"nome": p.nome, "ok": True, "modelo": p.modelo,
                "msg": f"respondeu em {time.monotonic() - inicio:.1f}s".replace(".", ",")}
    except _Pausa as e:
        return {"nome": p.nome, "ok": True, "modelo": p.modelo, "msg": f"chave aceita, mas no limite agora ({e})"}
    except _GrandeDemais:
        return {"nome": p.nome, "ok": True, "modelo": p.modelo, "msg": "chave aceita"}
    except ErroLLM as e:
        return {"nome": p.nome, "ok": False, "modelo": p.modelo, "msg": str(e)[:200]}
