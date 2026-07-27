"""The two-tier runtime router of §4.3, and the model resolution behind it.

What is worth pinning here, and why each assertion exists:

* ``select_tier`` over **all five** members of the ``ui_format`` enum, ``simulation``
  included. It is off in this PR but it is a storable value, so the mapping has to be total —
  a ``KeyError`` on a value the database can hold is a 500 waiting for the day somebody
  writes it by hand.
* The **precedence** of ``resolve_llm_config`` for the two new purposes, including the case
  that matters most in practice: nothing configured at all, both tiers falling back to
  ``LLM_MODEL``. §4.3 promises "ningun proveedor concreto es requisito", and that promise is
  exactly this test.
* ``coerce_ui_format``, because the format comes out of a model. An 8B model asked for one of
  four words will occasionally answer with a fifth.

No network, no database, no LLM: everything here is a pure function over strings.
"""

from __future__ import annotations

import pytest

from src.agents.runtime.router import (
    ALLOWED_UI_FORMATS,
    DEFAULT_UI_FORMAT,
    FAST_PURPOSE,
    HEAVY_FORMATS,
    HEAVY_PURPOSE,
    coerce_ui_format,
    purpose_for,
    runtime_model_key,
    select_tier,
    tier_config,
)
from src.config import settings
from src.llm.client import resolve_llm_config
from src.llm.prompts.runtime import UI_MAX_TOKENS, ui_max_tokens
from src.models import UiFormat


# --- select_tier -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ui_format", "expected"),
    [
        ("explanation", "fast"),
        ("exercise", "fast"),
        ("chart", "heavy"),
        ("mixed", "heavy"),
        ("simulation", "heavy"),
    ],
)
def test_select_tier_covers_every_ui_format(ui_format: str, expected: str) -> None:
    assert select_tier(ui_format) == expected


def test_select_tier_is_total_over_the_enum() -> None:
    """Every member of the stored enum maps to a tier, ``simulation`` included."""
    for member in UiFormat:
        assert select_tier(member) in ("fast", "heavy")


def test_select_tier_accepts_the_enum_member_not_only_its_value() -> None:
    assert select_tier(UiFormat.CHART) == "heavy"
    assert select_tier(UiFormat.EXPLANATION) == "fast"


def test_an_unknown_format_is_treated_as_cheap() -> None:
    """Defaulting to ``fast`` is the safe direction: an unknown format cannot make the
    router silently start paying for the expensive model."""
    assert select_tier("bogus") == "fast"


def test_heavy_formats_and_allowed_formats_do_not_pretend_simulation_is_on() -> None:
    """``simulation`` is heavy *and* not offerable: nothing in the frozen kit renders one."""
    assert "simulation" in HEAVY_FORMATS
    assert "simulation" not in ALLOWED_UI_FORMATS
    assert ALLOWED_UI_FORMATS == {"explanation", "exercise", "chart", "mixed"}


# --- purpose_for -------------------------------------------------------------------


def test_purpose_for_maps_the_two_tiers() -> None:
    assert purpose_for("fast") == FAST_PURPOSE == "runtime_fast"
    assert purpose_for("heavy") == HEAVY_PURPOSE == "runtime_heavy"


def test_purpose_for_defaults_to_the_cheap_purpose() -> None:
    assert purpose_for("nonsense") == "runtime_fast"


def test_the_purposes_line_up_with_the_settings_fields() -> None:
    """``resolve_llm_config`` resolves ``LLM_{PURPOSE}_MODEL`` by name, so a typo in a purpose
    string would silently stop reading its env var instead of failing."""
    for purpose in (FAST_PURPOSE, HEAVY_PURPOSE):
        assert hasattr(settings, f"LLM_{purpose.upper()}_MODEL")


# --- coerce_ui_format --------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("explanation", "explanation"),
        ("exercise", "exercise"),
        ("chart", "chart"),
        ("mixed", "mixed"),
        ("  MIXED  ", "mixed"),
        (UiFormat.CHART, "chart"),
    ],
)
def test_coerce_keeps_every_offerable_format(raw: object, expected: str) -> None:
    assert coerce_ui_format(raw) == expected


@pytest.mark.parametrize("raw", ["simulation", "table", "", None, 7, "explanation!"])
def test_coerce_falls_back_for_anything_else(raw: object) -> None:
    """Including ``simulation``: storable, unrenderable, therefore never accepted."""
    assert coerce_ui_format(raw, "exercise") == "exercise"
    assert coerce_ui_format(raw) == DEFAULT_UI_FORMAT


def test_coerce_ignores_an_unusable_default_too() -> None:
    assert coerce_ui_format("nope", "simulation") == DEFAULT_UI_FORMAT


# --- resolve_llm_config precedence -------------------------------------------------


@pytest.fixture
def clean_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """No per-purpose model configured anywhere, and a recognisable base model."""
    monkeypatch.setattr(settings, "LLM_MODEL", "base/model")
    monkeypatch.setattr(settings, "LLM_RUNTIME_FAST_MODEL", None)
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", None)


def test_with_nothing_configured_both_tiers_fall_back_to_llm_model(
    clean_models: None,
) -> None:
    """The promise of §4.3: one model configured, and the whole feature works."""
    assert tier_config({}, "fast").model == "base/model"
    assert tier_config({}, "heavy").model == "base/model"


def test_env_per_tier_beats_the_base_model(
    clean_models: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LLM_RUNTIME_FAST_MODEL", "env/fast")
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", "env/heavy")
    assert tier_config({}, "fast").model == "env/fast"
    assert tier_config({}, "heavy").model == "env/heavy"


def test_org_settings_beat_the_env(
    clean_models: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LLM_RUNTIME_FAST_MODEL", "env/fast")
    org = {"llm_runtime_fast_model": "org/fast"}
    assert tier_config(org, "fast").model == "org/fast"


def test_org_base_model_beats_the_env_per_tier(
    clean_models: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented order is org-purpose -> org-base -> env-purpose -> env-base.

    An organization that configured a single model expects *that* model to be used, not an
    env var somebody set on the host months earlier.
    """
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", "env/heavy")
    org = {"llm_model": "org/base"}
    assert tier_config(org, "heavy").model == "org/base"


def test_the_router_adds_no_provider_of_its_own(clean_models: None) -> None:
    """Nothing in the router names a provider: it only picks a purpose."""
    direct = resolve_llm_config({}, purpose="runtime_heavy")
    assert tier_config({}, "heavy") == direct


def test_api_base_and_key_come_from_the_same_resolution(
    clean_models: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://example.invalid/v1")
    org = {"llm_api_key": "org-key"}
    config = tier_config(org, "fast")
    assert config.api_base == "https://example.invalid/v1"
    assert config.api_key == "org-key"


# --- the cache_key's model component -----------------------------------------------


def test_runtime_model_key_pins_both_tiers(
    clean_models: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both model ids go into the ``cache_key`` (§3.4).

    The tier is not known until ``decide_formato`` has run, but the cache lookup happens
    before the graph — so the key cannot hold "the model that generated". Pinning both keeps
    the invariant that matters: changing *either* configured model invalidates cached renders.
    """
    assert runtime_model_key({}) == "base/model|base/model"
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", "env/heavy")
    assert runtime_model_key({}) == "base/model|env/heavy"


def test_changing_only_the_heavy_model_changes_the_key(
    clean_models: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = runtime_model_key({})
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", "env/heavy")
    assert runtime_model_key({}) != before


# --- budgets ------------------------------------------------------------------------


def test_the_expensive_tier_gets_the_bigger_budget() -> None:
    """§4.2: 1200 tokens fast, 2400 heavy. A ``chart`` or ``mixed`` screen needs the room."""
    assert ui_max_tokens("fast") == UI_MAX_TOKENS["fast"] == 1200
    assert ui_max_tokens("heavy") == UI_MAX_TOKENS["heavy"] == 2400
    assert ui_max_tokens("nonsense") == UI_MAX_TOKENS["fast"]
