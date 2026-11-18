import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).parent))

from agente import rede  # noqa: E402
from agente.config import carregar_config  # noqa: E402
from web_falsa import WebFalsa  # noqa: E402


@pytest.fixture
def raiz_tmp(tmp_path):
    """Cópia isolada de config/ e prompts/ — os testes nunca tocam no repositório."""
    for pasta in ("config", "prompts"):
        shutil.copytree(RAIZ / pasta, tmp_path / pasta)
    return tmp_path


@pytest.fixture
def cfg(raiz_tmp):
    c = carregar_config(raiz_tmp)
    c.geral["coleta"]["pausa_mesmo_site_s"] = 0
    c.geral["llm"]["pausa_entre_chamadas_s"] = 0
    return c


@pytest.fixture
def web():
    w = WebFalsa()
    rede.definir_transporte(w)
    yield w
    rede.definir_transporte(None)


@pytest.fixture(autouse=True)
def chave_eia_de_teste(monkeypatch):
    """A fonte da EIA só roda com chave; nos testes a EIA é simulada pela WebFalsa."""
    monkeypatch.setenv("EIA_API_KEY", "chave-de-teste")
    from agente.coletores import b3_boletim
    b3_boletim._cache.clear()
    b3_boletim.usar_cache(None)
