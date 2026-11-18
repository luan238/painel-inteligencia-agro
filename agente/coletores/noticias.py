"""Coleta de notícias nos sites da lista de fontes confiáveis (config/fontes.yaml).

Para cada site ativo:
  1. usa o RSS informado, ou descobre o feed sozinho (<link rel="alternate">,
     /feed/, /rss...);
  2. sem feed, lê a página de últimas notícias, identifica os links de matérias
     e abre cada uma para pegar título, data de publicação e resumo (metadados
     Open Graph / JSON-LD);
  3. filtra pela janela de horas, remove duplicadas, classifica por complexo
     (palavras-chave em pt/es/en/zh) e ranqueia.

Só entram notícias COM data de publicação verificável e dentro da janela.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from lxml import etree

from ..numeros import normalizar
from ..rede import BloqueadoPorRobots, ErroColeta

BRT = ZoneInfo("America/Sao_Paulo")
TIPOS_COM_NOTICIAS = {"noticias", "noticias_e_cotacoes", "relatorio_oficial"}
SEM_FEED = "pagina"          # marcador: site sem RSS (lido pela página de notícias)

_EXCLUIR_CAMINHO = re.compile(
    r"/(tag|tags|categoria|category|categorias|author|autor|autores|page|pagina|login|entrar|assine|assinatura|"
    r"newsletter|contato|fale-conosco|sobre|quem-somos|privacidade|termos|busca|search|cotacoes|cotacao|"
    r"videos?|podcasts?|galeria|fotos|eventos|anuncie|cadastro|wp-content|feed)(/|$)", re.I)
_PARECE_MATERIA = re.compile(r"/[^/]*[a-z0-9]+-[a-z0-9]+-[a-z0-9]+[^/]*|/\d{4,}|\.(html?|ghtml|shtml)$", re.I)
_UTM = re.compile(r"^(utm_|fbclid|gclid|mc_)", re.I)
_CJK = re.compile(r"[㐀-鿿]")


@dataclass
class Noticia:
    titulo: str
    url: str
    fonte: str
    regiao: str
    idioma: str
    publicado_em: str              # ISO com fuso
    resumo: str = ""
    blocos: list = field(default_factory=list)
    pontuacao: float = 0.0
    id: str = ""

    def como_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ utilidades
def url_canonica(url: str) -> str:
    p = urlparse(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if not _UTM.match(k)])
    caminho = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower().removeprefix("www."), caminho, "", query, ""))


def url_segura(url: str) -> bool:
    """Só http(s), sem aspas/espaços (o painel insere o link em HTML)."""
    return bool(re.fullmatch(r"https?://[^\s\"'<>`]+", url or ""))


def _texto(html_ou_texto: str) -> str:
    if not html_ou_texto:
        return ""
    if "<" in html_ou_texto:
        html_ou_texto = BeautifulSoup(html_ou_texto, "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html_ou_texto).strip()


def ler_data_publicacao(texto: str | None, fuso_padrao=timezone.utc) -> datetime | None:
    if not texto:
        return None
    texto = str(texto).strip()
    try:
        d = parsedate_to_datetime(texto)            # RFC 822 (RSS)
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            m = re.search(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)", texto)
            if m:
                d = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
            else:
                m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\D+(\d{1,2})[:h](\d{2}))?", texto)
                if not m:
                    return None
                d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                             int(m.group(4) or 0), int(m.group(5) or 0))
    if d.tzinfo is None:
        d = d.replace(tzinfo=fuso_padrao)
    return d


# ------------------------------------------------------------------- feeds
def ler_feed(conteudo: bytes) -> list[dict] | None:
    """Lê RSS 2.0, RSS 1.0 (RDF) ou Atom. Retorna None se não for um feed."""
    try:
        parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=False)
        raiz = etree.fromstring(conteudo, parser=parser)
    except (etree.XMLSyntaxError, ValueError):
        return None
    if raiz is None or not isinstance(raiz.tag, str):
        return None
    if etree.QName(raiz).localname.lower() not in ("rss", "feed", "rdf"):
        return None
    itens = []
    for el in raiz.iter():
        if not isinstance(el.tag, str) or etree.QName(el).localname.lower() not in ("item", "entry"):
            continue
        item: dict = {}
        for filho in el:
            if not isinstance(filho.tag, str):
                continue
            nome = etree.QName(filho).localname.lower()
            valor = (filho.text or "").strip()
            if nome == "title":
                item["titulo"] = _texto(valor)
            elif nome == "link":
                href = filho.get("href")
                if href and filho.get("rel", "alternate") == "alternate":
                    item["url"] = href
                elif valor and "url" not in item:
                    item["url"] = valor
            elif nome == "guid" and valor.startswith("http") and "url" not in item:
                item["url_guid"] = valor
            elif nome in ("pubdate", "published", "date", "issued", "updated", "modified"):
                item.setdefault("data", valor)
            elif nome in ("description", "summary", "content", "encoded") and valor:
                item.setdefault("resumo", _texto(valor)[:1500])
        item.setdefault("url", item.pop("url_guid", ""))
        item.pop("url_guid", None)
        if item.get("titulo") and item.get("url"):
            itens.append(item)
    return itens


def descobrir_feed(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for link in soup.find_all("link", rel=True, href=True):
        rels = [r.lower() for r in (link.get("rel") or [])]
        tipo = (link.get("type") or "").lower()
        if "alternate" in rels and ("rss" in tipo or "atom" in tipo):
            return urljoin(base_url, link["href"])
    return None


def candidatos_feed(pagina: str) -> list[str]:
    p = urlparse(pagina)
    origem = f"{p.scheme}://{p.netloc}"
    base = pagina if pagina.endswith("/") else pagina + "/"
    cands = [base + "feed/", origem + "/feed/", origem + "/rss", origem + "/rss.xml", origem + "/feed.xml"]
    return list(dict.fromkeys(cands))


# ------------------------------------------------------ páginas de matérias
def links_de_materias(html: str, base_url: str, limite: int) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    dominio = urlparse(base_url).netloc.lower().removeprefix("www.")
    vistos, links = set(), []
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#")[0]
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc.lower().removeprefix("www.").endswith(dominio):
            continue
        if _EXCLUIR_CAMINHO.search(p.path) or not _PARECE_MATERIA.search(p.path):
            continue
        titulo = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if len(titulo) < 25:
            continue
        chave = url_canonica(url)
        if chave in vistos:
            continue
        vistos.add(chave)
        links.append((url, titulo))
        if len(links) >= limite:
            break
    return links


def metadados_materia(html: str, fuso_padrao) -> dict:
    soup = BeautifulSoup(html, "lxml")

    def meta(*nomes):
        for n in nomes:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n}) \
                or soup.find("meta", attrs={"itemprop": n})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    titulo = meta("og:title", "twitter:title") or (soup.title.get_text(strip=True) if soup.title else "")
    data = meta("article:published_time", "datePublished", "pubdate", "publishdate", "date",
                "DC.date.issued", "parsely-pub-date", "sailthru.date", "article:modified_time")
    if not data:
        for bloco in soup.find_all("script", type="application/ld+json"):
            try:
                dados = json.loads(bloco.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            pilha = dados if isinstance(dados, list) else [dados]
            while pilha and not data:
                obj = pilha.pop(0)
                if isinstance(obj, dict):
                    data = obj.get("datePublished") or obj.get("dateCreated")
                    pilha.extend(obj.get("@graph", []) if isinstance(obj.get("@graph"), list) else [])
            if data:
                break
    if not data:
        tempo = soup.find("time", datetime=True)
        data = tempo["datetime"] if tempo else None
    descricao = meta("og:description", "description", "twitter:description") or ""
    corpo = soup.find("article") or soup.find("main") or soup
    paragrafos = [p.get_text(" ", strip=True) for p in corpo.find_all("p")]
    paragrafos = [p for p in paragrafos if len(p) > 60][:4]
    return {"titulo": _texto(titulo), "data": ler_data_publicacao(data, fuso_padrao),
            "resumo": _texto(" ".join([descricao] + paragrafos))}


# ------------------------------------------------------------ classificação
def _compilar_palavras(blocos: list[dict]) -> dict:
    regras = {}
    for b in blocos:
        pads = []
        for kw in b.get("palavras_chave", []):
            k = normalizar(str(kw))
            pads.append(re.compile(re.escape(k)) if _CJK.search(k) else re.compile(r"\b" + re.escape(k) + r"\b"))
        regras[b["id"]] = pads
    return regras


def classificar(noticia: Noticia, regras: dict) -> dict:
    texto_titulo = normalizar(noticia.titulo)
    texto = texto_titulo + " " + normalizar(noticia.resumo[:600])
    pontos = {}
    for bloco_id, pads in regras.items():
        p = sum(2 if rx.search(texto_titulo) else 1 for rx in pads if rx.search(texto))
        if p:
            pontos[bloco_id] = p
    return pontos


# --------------------------------------------------------------- execução
class ColetorNoticias:
    def __init__(self, cfg, cliente, agora: datetime, feeds_conhecidos: dict | None = None):
        self.cfg, self.cliente, self.agora = cfg, cliente, agora
        n = cfg.geral.get("noticias", {})
        horas = n.get("janela_horas_fim_de_semana", 72) if agora.weekday() >= 5 or agora.weekday() == 0 and agora.hour < 12 \
            else n.get("janela_horas", 36)
        self.limite_data = agora - timedelta(hours=horas)
        self.max_por_fonte = n.get("max_itens_por_fonte", 15)
        self.max_baixar = n.get("max_materias_baixadas", 60)
        self.max_resumo = n.get("max_caracteres_resumo", 900)
        self.baixadas = 0
        self.feeds = dict(feeds_conhecidos or {})
        self.status: list[dict] = []

    def _abrir(self, url: str):
        return self.cliente.obter(url)

    def _feed_da_fonte(self, fonte: dict, pagina: str) -> tuple[str | None, list | None, str]:
        """Retorna (url_do_feed, itens, html_da_pagina)."""
        html_pagina = ""
        candidatos = [fonte["rss"]] if fonte.get("rss") else []
        conhecido = self.feeds.get(fonte["nome"])
        if conhecido == SEM_FEED and not candidatos:
            try:
                return None, None, self._abrir(pagina).texto
            except BloqueadoPorRobots:
                raise
            except ErroColeta:
                return None, None, ""
        if conhecido and conhecido != SEM_FEED:
            candidatos.append(conhecido)
        for url in candidatos:
            try:
                itens = ler_feed(self._abrir(url).conteudo)
                if itens:
                    return url, itens, html_pagina
            except ErroColeta:
                continue
        try:
            html_pagina = self._abrir(pagina).texto
        except BloqueadoPorRobots:
            raise
        except ErroColeta:
            html_pagina = ""
        descoberto = descobrir_feed(html_pagina, pagina) if html_pagina else None
        for url in ([descoberto] if descoberto else []) + candidatos_feed(pagina):
            try:
                itens = ler_feed(self._abrir(url).conteudo)
            except ErroColeta:
                continue
            if itens:
                return url, itens, html_pagina
        return None, None, html_pagina

    def coletar_fonte(self, fonte: dict) -> list[Noticia]:
        pagina = fonte.get("url_noticias") or fonte["url"]
        fuso = BRT if fonte.get("idioma", "pt") == "pt" else timezone.utc
        st = {"nome": fonte["nome"], "regiao": fonte.get("regiao", ""), "modo": "", "feed": "",
              "itens_lidos": 0, "itens_na_janela": 0, "sem_data": 0, "status": "ok", "mensagem": ""}
        noticias: list[Noticia] = []
        try:
            feed_url, itens, html = self._feed_da_fonte(fonte, pagina)
            brutos = []
            if itens:
                st["modo"], st["feed"] = "rss", feed_url
                self.feeds[fonte["nome"]] = feed_url
                for it in itens[: self.max_por_fonte * 2]:
                    brutos.append({"titulo": it.get("titulo", ""), "url": urljoin(feed_url, it.get("url", "")),
                                   "data": ler_data_publicacao(it.get("data"), fuso), "resumo": it.get("resumo", "")})
            elif html:
                st["modo"] = "pagina"
                if not fonte.get("rss"):
                    self.feeds[fonte["nome"]] = SEM_FEED
                for url, titulo in links_de_materias(html, pagina, min(self.max_por_fonte, 10)):
                    if self.baixadas >= self.max_baixar:
                        break
                    try:
                        self.baixadas += 1
                        meta = metadados_materia(self._abrir(url).texto, fuso)
                    except ErroColeta:
                        continue
                    brutos.append({"titulo": meta["titulo"] or titulo, "url": url, "data": meta["data"],
                                   "resumo": meta["resumo"]})
            else:
                st["status"], st["mensagem"] = "falha", "página e feed inacessíveis"
            st["itens_lidos"] = len(brutos)
            for b in brutos:
                if not b["data"]:
                    st["sem_data"] += 1
                    continue
                if not (self.limite_data <= b["data"] <= self.agora + timedelta(hours=2)):
                    continue
                if not url_segura(b["url"]) or not b["titulo"]:
                    continue
                noticias.append(Noticia(titulo=b["titulo"][:300], url=b["url"], fonte=fonte["nome"],
                                        regiao=fonte.get("regiao", ""), idioma=fonte.get("idioma", "pt"),
                                        publicado_em=b["data"].astimezone(BRT).isoformat(timespec="minutes"),
                                        resumo=b["resumo"][: self.max_resumo]))
            st["itens_na_janela"] = len(noticias)
            if st["status"] == "ok" and not brutos:
                st["status"], st["mensagem"] = "sem_itens", "nenhuma matéria reconhecida na página"
        except BloqueadoPorRobots as e:
            st["status"], st["mensagem"] = "robots", str(e)
        except Exception as e:                      # uma fonte nunca derruba a coleta
            st["status"], st["mensagem"] = "falha", f"{type(e).__name__}: {str(e)[:200]}"
        self.status.append(st)
        return noticias

    def completar_resumos(self, noticias: list[Noticia], minimo: int = 200) -> None:
        for n in noticias:
            if len(n.resumo) >= minimo or self.baixadas >= self.max_baixar:
                continue
            try:
                self.baixadas += 1
                meta = metadados_materia(self._abrir(n.url).texto, BRT)
                if len(meta["resumo"]) > len(n.resumo):
                    n.resumo = meta["resumo"][: self.max_resumo]
            except ErroColeta:
                continue


def selecionar(noticias: list[Noticia], blocos: list[dict], prioridades: dict, max_por_bloco: int,
               agora: datetime) -> dict[str, list[Noticia]]:
    """Remove duplicadas, classifica, ranqueia e numera (N1, N2...)."""
    regras = _compilar_palavras(blocos)
    unicas, vistos_url, vistos_titulo = [], set(), set()
    for n in sorted(noticias, key=lambda x: (prioridades.get(x.fonte, 3), x.publicado_em)):
        cu, ct = url_canonica(n.url), normalizar(re.sub(r"[^\w\s]", "", n.titulo))[:90]
        if cu in vistos_url or ct in vistos_titulo:
            continue
        vistos_url.add(cu)
        vistos_titulo.add(ct)
        unicas.append(n)
    por_bloco: dict[str, list[Noticia]] = {b["id"]: [] for b in blocos}
    for n in unicas:
        pontos = classificar(n, regras)
        n.blocos = sorted(pontos, key=pontos.get, reverse=True)
        for bloco_id, p in pontos.items():
            idade_h = max(0.0, (agora - datetime.fromisoformat(n.publicado_em)).total_seconds() / 3600)
            score = p + (3 - prioridades.get(n.fonte, 3)) * 0.8 + max(0.0, 2 - idade_h / 12)
            por_bloco[bloco_id].append((score, n))
    escolhidas: dict[str, list[Noticia]] = {}
    contador = 0
    ids: dict[str, str] = {}
    for b in blocos:
        lista, por_fonte = [], {}
        for score, n in sorted(por_bloco[b["id"]], key=lambda t: t[0], reverse=True):
            if por_fonte.get(n.fonte, 0) >= 4:
                continue
            por_fonte[n.fonte] = por_fonte.get(n.fonte, 0) + 1
            n.pontuacao = max(n.pontuacao, round(score, 2))
            if n.url not in ids:
                contador += 1
                ids[n.url] = f"N{contador}"
                n.id = ids[n.url]
            lista.append(n)
            if len(lista) >= max_por_bloco:
                break
        escolhidas[b["id"]] = lista
    return escolhidas
