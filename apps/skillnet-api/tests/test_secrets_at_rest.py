"""The provider API key an organization stores is encrypted in the database.

`organizations.settings` is JSONB, and an admin who points SkillNet at their own DeepSeek
or OpenAI account puts a key in it. The API has never handed that key back — `GET
/settings` reports `llm_configured` and the model name, nothing else — but it sat in
Postgres in clear text, which means a dump, a backup, a replica or a support query leaked
a live credential belonging to somebody else's company.

What these tests pin is not the cipher. It is the three properties that decide whether
shipping this breaks anybody:

1. a key written today is unreadable in the column and readable by the application;
2. a key written *before* today still works, untouched;
3. a key that cannot be decrypted degrades to "no key" instead of taking the API down.
"""

from __future__ import annotations

import pytest

from src.config import settings as app_settings
from src.core.secrets import PREFIX, is_sealed, seal, unseal
from src.llm.client import resolve_llm_config
from src.llm.embedding import resolve_embedding_config

KEY = "sk-deepseek-a-real-looking-secret-0123456789"


# --------------------------------------------------------------------------------------
# 1. Round trip, and the ciphertext really is one
# --------------------------------------------------------------------------------------
def test_a_sealed_key_comes_back_intact():
    assert unseal(seal(KEY)) == KEY


def test_the_stored_form_does_not_contain_the_key():
    """The point of the exercise: what lands in the column must be useless on its own."""
    stored = seal(KEY)
    assert stored != KEY
    assert KEY not in stored
    assert "deepseek" not in stored
    assert stored.startswith(PREFIX)


def test_two_seals_of_the_same_key_differ():
    """Fernet carries a random IV, so an attacker cannot tell two organizations use the
    same key by comparing columns."""
    assert seal(KEY) != seal(KEY)
    assert unseal(seal(KEY)) == unseal(seal(KEY)) == KEY


def test_sealing_is_idempotent():
    """A settings update that carries the stored value back in must not double-encrypt."""
    once = seal(KEY)
    assert seal(once) == once
    assert unseal(seal(once)) == KEY


@pytest.mark.parametrize("empty", [None, ""])
def test_nothing_is_sealed_into_something(empty):
    assert seal(empty) == empty
    assert unseal(empty) is None


# --------------------------------------------------------------------------------------
# 2. Deploying this must not break an installation that already stored a key
# --------------------------------------------------------------------------------------
def test_a_legacy_plaintext_key_is_still_read():
    assert not is_sealed(KEY)
    assert unseal(KEY) == KEY


def test_resolve_llm_config_reads_both_forms(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app_settings, "LLM_API_KEY", "env-key")
    assert resolve_llm_config({"llm_api_key": seal(KEY)}).api_key == KEY
    assert resolve_llm_config({"llm_api_key": KEY}).api_key == KEY
    assert resolve_llm_config({}).api_key == "env-key"


def test_resolve_embedding_config_reads_both_forms(monkeypatch: pytest.MonkeyPatch):
    # `EMBEDDING_BASE_URL` is cleared because this test is about `unseal` reading sealed and
    # plain keys, not about which provider wins: an embedding base URL of its own now means
    # the embedding provider is declared, and a declared provider does not borrow the chat
    # model's key. See `tests/test_embedding_provider_pairing.py`. Without this line the
    # assertion passes or fails depending on what the developer happens to have in `.env`.
    monkeypatch.setattr(app_settings, "EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(app_settings, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(app_settings, "LLM_API_KEY", "env-key")
    assert resolve_embedding_config({"embedding_api_key": seal(KEY)}).api_key == KEY
    # Falls back to the LLM key, sealed the same way.
    assert resolve_embedding_config({"llm_api_key": seal(KEY)}).api_key == KEY
    assert resolve_embedding_config({"llm_api_key": KEY}).api_key == KEY


# --------------------------------------------------------------------------------------
# 3. A rotated SECRET_KEY degrades, it does not crash
# --------------------------------------------------------------------------------------
def test_a_key_sealed_under_another_secret_reads_as_absent(monkeypatch: pytest.MonkeyPatch):
    stored = seal(KEY)
    monkeypatch.setattr(app_settings, "SECRET_KEY", "a-completely-different-secret-key-x")
    assert unseal(stored) is None


def test_after_rotation_the_environment_default_takes_over(monkeypatch: pytest.MonkeyPatch):
    """Which is the honest outcome: the organization has no usable key, so it has none,
    and the admin re-enters it. Raising here would take down every request that touches
    an LLM over a condition a form field fixes."""
    stored = seal(KEY)
    monkeypatch.setattr(app_settings, "SECRET_KEY", "a-completely-different-secret-key-x")
    monkeypatch.setattr(app_settings, "LLM_API_KEY", "env-key")
    assert resolve_llm_config({"llm_api_key": stored}).api_key == "env-key"


def test_garbage_in_the_column_does_not_raise():
    assert unseal(f"{PREFIX}not-base64-at-all!!") is None


def test_the_secret_key_actually_keys_it(monkeypatch: pytest.MonkeyPatch):
    """Guards against a derivation that silently ignores SECRET_KEY — which would look
    identical in every other test here."""
    monkeypatch.setattr(app_settings, "SECRET_KEY", "secret-number-one-padded-out-abcdef")
    first = seal(KEY)
    monkeypatch.setattr(app_settings, "SECRET_KEY", "secret-number-two-padded-out-abcdef")
    assert unseal(first) is None
