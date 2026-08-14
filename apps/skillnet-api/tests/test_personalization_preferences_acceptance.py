"""Acceptance contracts for declared preferences, cache partitioning and pins.

These tests intentionally use public pure functions and ``NodeRenderService`` rather
than implementation helpers. They are the executable subset of
``docs/personalization-preferences-acceptance.md`` (K01-K04, S01-S03).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.personalization.preferences import (
    DetailPreference,
    ImagePreference,
    InteractionPreference,
    LearningPreferences,
    WebPresentationPreference,
    preference_bucket,
)
from src.services.node_render_service import (
    NodeRenderService,
    build_render_key,
)


def _preferences(**overrides) -> LearningPreferences:
    values = {
        "web_presentation": WebPresentationPreference.BALANCED,
        "interaction": InteractionPreference.STANDARD,
        "detail": DetailPreference.STANDARD,
        "images": ImagePreference.WHEN_USEFUL,
        **overrides,
    }
    return LearningPreferences(**values)


def _render_key(preferences: LearningPreferences, *, node_id: uuid.UUID | None = None):
    profile = SimpleNamespace(
        nodes_completed=3,
        format_vector={"texto": 0.7},
        role_title="Dependiente",
        sector="retail",
        preset="standard",
        experience_level="some",
        learning_preferences=preferences.to_dict(),
    )
    return build_render_key(
        node=SimpleNamespace(id=node_id or uuid.UUID(int=1)),
        course=SimpleNamespace(schema_version=1, intent_density=3),
        profile=profile,
        node_state=SimpleNamespace(scaffold_band="neutral"),
        accessibility={},
        model_key="fixture/local|fixture/local",
        backend="openui",
    )


def test_same_normalized_bundle_produces_the_same_bucket_and_render_key() -> None:
    typed = _preferences(
        web_presentation=WebPresentationPreference.VISUAL,
        detail=DetailPreference.DETAILED,
        images=ImagePreference.PREFER,
    )
    reordered_mapping = {
        "images": "prefer",
        "version": 2,
        "detail": "detailed",
        "modality": "visual",
        "interaction": "standard",
    }

    assert preference_bucket(typed) == preference_bucket(reordered_mapping)

    first = _render_key(typed)
    second = _render_key(
        LearningPreferences(
            web_presentation=WebPresentationPreference.VISUAL,
            interaction=InteractionPreference.STANDARD,
            detail=DetailPreference.DETAILED,
            images=ImagePreference.PREFER,
        )
    )
    assert first.preference_bucket == second.preference_bucket
    assert first.cache_key == second.cache_key


@pytest.mark.parametrize(
    "changed",
    [
        _preferences(web_presentation=WebPresentationPreference.VISUAL),
        _preferences(interaction=InteractionPreference.INTERACTIVE),
        _preferences(detail=DetailPreference.DETAILED),
        _preferences(images=ImagePreference.PREFER),
    ],
    ids=("modality", "interaction", "detail", "images"),
)
def test_each_preference_axis_partitions_the_shared_render_cache(changed) -> None:
    baseline = _render_key(_preferences())
    variant = _render_key(changed)

    assert variant.preference_bucket != baseline.preference_bucket
    assert variant.cache_key != baseline.cache_key


@pytest.mark.asyncio
async def test_existing_pin_remains_authoritative_until_explicit_reselection(
    monkeypatch,
) -> None:
    """Saving settings must not silently replace a screen already being read (S01/S02)."""
    pinned = SimpleNamespace(id=uuid.UUID(int=9))
    service = NodeRenderService(SimpleNamespace())  # repositories are not reached
    service.pinned_render = AsyncMock(return_value=pinned)  # type: ignore[method-assign]
    service.render_key_for = AsyncMock()  # type: ignore[method-assign]
    monkeypatch.setattr(
        "src.agents.runtime.runner.spawn_node_render",
        lambda _state: pytest.fail("a pinned request must not spawn a render"),
    )

    result = await service.request_render(
        user=SimpleNamespace(id=uuid.UUID(int=2)),
        node=SimpleNamespace(id=uuid.UUID(int=3), reviewed_at=object()),
        course=SimpleNamespace(),
        force=False,
        preview=False,
    )

    assert result.cached is True
    assert result.render_id == pinned.id
    service.render_key_for.assert_not_awaited()


def test_next_unpinned_node_uses_the_new_preference_key() -> None:
    """The stable pin is local to the open node; future selection reads the new bundle."""
    next_node = uuid.UUID(int=4)
    old = _render_key(_preferences(), node_id=next_node)
    new = _render_key(
        _preferences(
            web_presentation=WebPresentationPreference.VISUAL,
            detail=DetailPreference.DETAILED,
            images=ImagePreference.PREFER,
        ),
        node_id=next_node,
    )

    assert old.cache_key != new.cache_key
    assert new.preference_bucket == "p3:visual:standard:detailed:prefer"


def test_render_affecting_accessibility_profiles_never_share_a_cache_key() -> None:
    """Regression: reduced-motion changes the planner shortlist, so it must key too."""
    profile = SimpleNamespace(
        nodes_completed=3,
        format_vector={"texto": 0.7},
        role_title="Dependiente",
        sector="retail",
        preset="standard",
        experience_level="some",
        learning_preferences=_preferences().to_dict(),
    )
    common = {
        "node": SimpleNamespace(id=uuid.UUID(int=8)),
        "course": SimpleNamespace(schema_version=1, intent_density=3),
        "profile": profile,
        "node_state": SimpleNamespace(scaffold_band="neutral"),
        "model_key": "fixture/local|fixture/local",
        "backend": "openui",
    }

    standard = build_render_key(**common, accessibility={})
    reduced = build_render_key(**common, accessibility={"reduce_motion": True})

    assert standard.accessibility_bucket == "a1:rm0:hc0:et0"
    assert reduced.accessibility_bucket == "a1:rm1:hc0:et0"
    assert standard.cache_key != reduced.cache_key
