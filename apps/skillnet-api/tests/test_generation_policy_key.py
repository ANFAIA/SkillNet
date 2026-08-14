from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.config import Settings, settings
from src.services import node_render_service
from src.services.node_render_service import (
    build_render_key,
    cache_key_uses_current_screen_contract,
    generation_policy_key,
)


def _render_key() -> node_render_service.RenderKey:
    return build_render_key(
        node=SimpleNamespace(id=uuid.UUID(int=41)),
        course=SimpleNamespace(schema_version=7, intent_density=3),
        profile=SimpleNamespace(
            nodes_completed=3,
            format_vector=None,
            role_title="Support agent",
            sector="events",
            preset="standard",
            experience_level="some",
            learning_preferences=None,
            personalization_revision=0,
        ),
        node_state=SimpleNamespace(scaffold_band="neutral"),
        accessibility={},
        model_key="fixture/local|fixture/local",
        backend="openui",
    )


def test_adaptive_episode_rollout_defaults_off() -> None:
    assert Settings.model_fields["ADAPTIVE_EPISODES"].default is False
    assert generation_policy_key(False) == "screen-scheme/v1"
    assert generation_policy_key(True) == "adaptive-episodes/v1"


def test_flag_off_keeps_render_identity_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", False)

    first = _render_key()
    second = _render_key()

    assert first == second
    assert first.generation_policy_key == "screen-scheme/v1"


def test_adaptive_and_screen_policies_never_share_cache_or_pin_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", False)
    screen = _render_key()
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", True)
    adaptive = _render_key()

    assert screen.generation_policy_key != adaptive.generation_policy_key
    assert screen.cache_key != adaptive.cache_key
    assert cache_key_uses_current_screen_contract(screen.cache_key) is False
    assert cache_key_uses_current_screen_contract(adaptive.cache_key) is True


def test_policy_version_change_invalidates_render_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", True)
    version_one = _render_key()
    monkeypatch.setattr(node_render_service, "ADAPTIVE_EPISODES_POLICY_VERSION", "v2")
    version_two = _render_key()

    assert version_one.generation_policy_key == "adaptive-episodes/v1"
    assert version_two.generation_policy_key == "adaptive-episodes/v2"
    assert version_one.cache_key != version_two.cache_key
