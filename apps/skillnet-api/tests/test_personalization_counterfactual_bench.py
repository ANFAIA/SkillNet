#!/usr/bin/env python
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from scripts.personalization_counterfactual_bench import run

from src.services.node_render_service import NodeRenderService


def test_counterfactual_matrix_audits_complete_didact_universe() -> None:
    report = run(repetitions=2)

    assert report["didact_universe"]["complete"] is True
    assert report["didact_universe"]["count"] == 34
    assert len(report["didact_universe"]["type_ids"]) == 34
    assert report["summary"]["pairs"] == 14
    assert report["summary"]["critical_fact_recall"] == 1.0
    assert report["summary"]["intraprofile_noise_cases"] == 0


def test_each_declared_preference_reaches_prompt_and_cache() -> None:
    rows = run(repetitions=1)["counterfactuals"]
    declared = [row for row in rows if row["changed_axis"] in {"presentation", "detail", "images"}]

    assert declared
    assert all(row["prompt_changed"] for row in declared)
    assert all(row["cache_invalidated"] for row in declared)


def test_hot_vector_changes_bucket_but_cold_vector_is_suppressed() -> None:
    rows = {row["case_id"]: row for row in run(repetitions=1)["counterfactuals"]}

    assert rows["vector-exercise-hot"]["vector_bucket"].startswith("ejercicio:")
    assert rows["vector-data-hot"]["vector_bucket"].startswith("dato:")
    assert rows["vector-cold-calibration"]["vector_bucket"] == ""
    assert rows["vector-cold-calibration"]["calibrating"] is True


def test_accessibility_short_blocks_changes_effective_density_and_key() -> None:
    rows = {row["case_id"]: row for row in run(repetitions=1)["counterfactuals"]}
    short = rows["accessibility-short-blocks"]

    assert short["effective_density"] == 2
    assert short["cache_invalidated"] is True


def test_bench_has_no_semantic_change_without_cache_invalidation() -> None:
    report = run(repetitions=1)

    assert report["summary"]["semantic_change_without_cache_invalidation"] == []
    reduced = next(
        row
        for row in report["counterfactuals"]
        if row["case_id"] == "accessibility-reduced-motion"
    )
    assert reduced["accessibility_bucket"] == "a1:rm1:hc0:et0"
    assert reduced["cache_invalidated"] is True


@pytest.mark.asyncio
async def test_an_existing_pin_is_stable_while_preferences_change(monkeypatch) -> None:
    """The current screen stays fixed; explicit reselection is a separate action."""
    pinned = SimpleNamespace(id=uuid.UUID(int=9))
    service = NodeRenderService(SimpleNamespace())
    service.pinned_render = AsyncMock(return_value=pinned)  # type: ignore[method-assign]
    service.render_key_for = AsyncMock()  # type: ignore[method-assign]
    monkeypatch.setattr(
        "src.agents.runtime.runner.spawn_node_render",
        lambda _state: pytest.fail("a pinned request must not generate or repin"),
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
