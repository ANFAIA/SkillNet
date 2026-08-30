"""An embedding key and an embedding base URL travel together, or not at all.

The bug this fixes was silent and misleading, which is why it gets its own file. The
fallback in ``resolve_embedding_config`` used to be resolved field by field, so the most
natural configuration in the world —

    LLM_BASE_URL=https://api.deepseek.com
    LLM_API_KEY=<deepseek>
    EMBEDDING_API_KEY=<openai>        # the chat provider has no embeddings endpoint

— produced an OpenAI key pointed at DeepSeek's endpoint. The provider then answers
``401 ... your api key is invalid``, and the only reasonable reaction to that message is to
go and regenerate a key that was never the problem. Measured on a real deployment before
this test existed.
"""

from __future__ import annotations

import pytest

from src.config import settings as app_settings
from src.llm.embedding import resolve_embedding_config


@pytest.fixture(autouse=True)
def _llm_provider(monkeypatch: pytest.MonkeyPatch):
    """A deployment whose chat model lives behind its own base URL."""
    monkeypatch.setattr(app_settings, "LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(app_settings, "LLM_API_KEY", "clave-del-chat")
    monkeypatch.setattr(app_settings, "EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(app_settings, "EMBEDDING_API_KEY", "")


def test_una_clave_propia_no_hereda_la_url_del_chat(monkeypatch: pytest.MonkeyPatch):
    """The regression itself: own key, no own URL — the LLM's URL must NOT leak in."""
    monkeypatch.setattr(app_settings, "EMBEDDING_API_KEY", "clave-de-openai")

    config = resolve_embedding_config()

    assert config.api_key == "clave-de-openai"
    assert config.api_base is None, (
        "una clave de embeddings con la URL del chat manda esa clave al proveedor "
        "equivocado, y el 401 resultante culpa a la clave"
    )


def test_una_url_propia_no_hereda_la_clave_del_chat(monkeypatch: pytest.MonkeyPatch):
    """The mirror case: a keyless local embedding server must not receive the chat key."""
    monkeypatch.setattr(app_settings, "EMBEDDING_BASE_URL", "http://localhost:11434/v1")

    config = resolve_embedding_config()

    assert config.api_base == "http://localhost:11434/v1"
    assert config.api_key is None


def test_sin_ajustes_propios_se_hereda_el_proveedor_entero():
    """The documented fallback still works — as a provider, both fields together."""
    config = resolve_embedding_config()

    assert config.api_base == "https://api.deepseek.com"
    assert config.api_key == "clave-del-chat"


def test_los_ajustes_de_la_organizacion_siguen_la_misma_regla():
    """Per-organization settings are the same decision one layer up."""
    config = resolve_embedding_config({"embedding_api_key": "clave-de-la-org"})

    assert config.api_key == "clave-de-la-org"
    assert config.api_base is None


def test_el_modelo_si_conserva_su_respaldo(monkeypatch: pytest.MonkeyPatch):
    """A model name is not a credential: naming one without a key is not a contradiction."""
    monkeypatch.setattr(app_settings, "EMBEDDING_MODEL", "")
    monkeypatch.setattr(app_settings, "LLM_MODEL", "deepseek/deepseek-chat")

    assert resolve_embedding_config().model == "deepseek/deepseek-chat"
