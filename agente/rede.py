"""Acesso à internet: sessão HTTP com novas tentativas, pausa educada por site,
respeito ao robots.txt e um "transporte" substituível (usado nos testes offline)."""
from __future__ import annotations

import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOKEN_ROBO = "AgroIntelAgent"


class ErroColeta(Exception):
    """Falha ao obter ou interpretar uma fonte."""


class BloqueadoPorRobots(ErroColeta):
    """O robots.txt do site não permite a leitura desta página."""


@dataclass
class Resposta:
    url: str
    status: int
    conteudo: bytes
    headers: dict = field(default_factory=dict)
    encoding: str | None = None

    @property
    def texto(self) -> str:
        enc = self.encoding or "utf-8"
        try:
            return self.conteudo.decode(enc, errors="replace")
        except LookupError:
            return self.conteudo.decode("utf-8", errors="replace")

    def json(self):
        import json
        return json.loads(self.texto)


# Transporte substituível: função(url, metodo, dados, headers) -> Resposta
_transporte: Callable | None = None


def definir_transporte(func: Callable | None) -> None:
    """Troca o acesso real à internet por uma função (testes/modo offline)."""
    global _transporte
    _transporte = func


class Cliente:
    def __init__(self, cfg_coleta: dict | None = None):
        cfg = cfg_coleta or {}
        self.timeout = cfg.get("tempo_limite_s", 25)
        self.pausa = cfg.get("pausa_mesmo_site_s", 1.5)
        self.respeitar_robots = cfg.get("respeitar_robots_txt", True)
        self.user_agent = cfg.get("user_agent", f"Mozilla/5.0 (compatible; {TOKEN_ROBO}/1.0)")
        self.sessao = requests.Session()
        # erros de conexão: 1 tentativa só (o disjuntor pula o site no resto da execução);
        # respostas 429/5xx: novas tentativas com espera crescente
        retry = Retry(total=cfg.get("tentativas", 3), connect=0, read=0, status=cfg.get("tentativas", 3),
                      backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET", "POST"), raise_on_status=False)
        self.sessao.mount("https://", HTTPAdapter(max_retries=retry))
        self.sessao.mount("http://", HTTPAdapter(max_retries=retry))
        self.sessao.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8,es;q=0.7",
        })
        self._ultimo_acesso: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.log: list[dict] = []          # registro de cada acesso (auditoria)
        self._cache: dict[str, Resposta] = {}  # mesma página lida uma vez por execução
        self._falhas_url: dict[str, ErroColeta] = {}   # URL que já falhou não é tentada de novo
        self._falhas_host: dict[str, int] = {}         # host fora do ar é pulado (disjuntor)

    # ----------------------------------------------------------- robots.txt
    def permitido(self, url: str) -> bool:
        if not self.respeitar_robots:
            return True
        p = urlparse(url)
        origem = f"{p.scheme}://{p.netloc}"
        if origem not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                if self._falhas_host.get(p.netloc, 0) >= 1:
                    raise ErroColeta("host fora do alcance")
                r = self._baixar(origem + "/robots.txt", "GET", None)
                if r.status in (401, 403):
                    parser.disallow_all = True
                elif r.status >= 400:
                    parser.allow_all = True
                else:
                    parser.parse(r.texto.splitlines())
            except ErroColeta:
                self._falhas_host[p.netloc] = self._falhas_host.get(p.netloc, 0) + 1
                parser.allow_all = True        # sem robots.txt acessível = sem restrição declarada
            except Exception:
                parser.allow_all = True
            self._robots[origem] = parser
        parser = self._robots[origem]
        return parser.can_fetch(TOKEN_ROBO, url)

    # --------------------------------------------------------------- acesso
    def obter(self, url: str, *, ignorar_robots: bool = False, metodo: str = "GET",
              dados: dict | None = None) -> Resposta:
        if not ignorar_robots and not self.permitido(url):
            self.log.append({"url": url, "status": "robots"})
            raise BloqueadoPorRobots(f"robots.txt de {urlparse(url).netloc} não permite ler {url}")
        if metodo == "GET" and url in self._cache:
            return self._cache[url]
        if metodo == "GET" and url in self._falhas_url:
            raise self._falhas_url[url]
        host = urlparse(url).netloc
        if self._falhas_host.get(host, 0) >= 1:
            raise ErroColeta(f"{host} fora do alcance nesta execução (falhas de conexão repetidas)")
        try:
            resp = self._baixar(url, metodo, dados)
        except ErroColeta as e:
            self._falhas_host[host] = self._falhas_host.get(host, 0) + 1
            self._falhas_url[url] = e
            raise
        self.log.append({"url": url, "status": resp.status})
        if metodo == "GET" and resp.status < 400:
            self._cache[url] = resp
        if resp.status >= 400:
            erro = ErroColeta(f"HTTP {resp.status} em {url}")
            if metodo == "GET":
                self._falhas_url[url] = erro
            raise erro
        return resp

    def _baixar(self, url: str, metodo: str, dados: dict | None) -> Resposta:
        if _transporte is not None:
            return _transporte(url, metodo, dados, {})
        host = urlparse(url).netloc
        espera = self.pausa - (time.monotonic() - self._ultimo_acesso.get(host, 0))
        if espera > 0:
            time.sleep(espera)
        try:
            if metodo == "POST":
                r = self.sessao.post(url, data=dados, timeout=(8, self.timeout))
            else:
                r = self.sessao.get(url, timeout=(8, self.timeout))
        except requests.RequestException as e:
            raise ErroColeta(f"falha de conexão em {url}: {type(e).__name__}: {e}") from e
        finally:
            self._ultimo_acesso[host] = time.monotonic()
        encoding = r.encoding
        tipo = r.headers.get("Content-Type", "")
        if ("charset" not in tipo.lower()) and ("html" in tipo or "xml" in tipo or not tipo):
            encoding = r.apparent_encoding or encoding
        return Resposta(url=r.url, status=r.status_code, conteudo=r.content,
                        headers=dict(r.headers), encoding=encoding)
