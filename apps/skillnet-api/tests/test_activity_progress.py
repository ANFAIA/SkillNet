from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.models.learner_node_state import NodeState
from src.services.activity_authoring_validators import (
    ActivityDefinitionShapeError,
    validate_component_definition,
)
from src.services.activity_progress import project_activity_progress


def test_missing_node_state_is_not_started_beginner() -> None:
    snapshot = project_activity_progress("didact.progress", None)
    assert snapshot.status == "not_started"
    assert snapshot.progress == 0
    assert snapshot.level == "beginner"


def test_mastered_node_is_completed_advanced() -> None:
    row = SimpleNamespace(state=NodeState.MASTERED, mastery=0.4)
    snapshot = project_activity_progress("didact.mastery-badge", row)
    assert snapshot.status == "completed"
    assert snapshot.progress == 100
    assert snapshot.level == "advanced"


def test_a_finished_expository_node_is_completed_without_being_mastered() -> None:
    """"Completed" is ``node_progression.is_done``, not ``state is MASTERED``.

    This projection used to ask the evidence machine alone, so a node with no graded item
    reported ``not_started`` for ever — the same defect the padlocks had, in the second of
    the two places that wrote the predicate by hand.
    """
    row = SimpleNamespace(
        state=NodeState.NOT_STARTED, mastery=0.0, completed_at="2026-08-29T10:00:00Z"
    )
    snapshot = project_activity_progress("didact.progress", row)
    assert snapshot.status == "completed"
    assert snapshot.progress == 100


def test_learning_node_uses_clamped_mastery_percent() -> None:
    row = SimpleNamespace(state=NodeState.LEARNING, mastery=0.62)
    snapshot = project_activity_progress("didact.progress", row)
    assert snapshot.status == "in_progress"
    assert snapshot.progress == 62
    assert snapshot.level == "intermediate"


def test_authored_progress_cannot_include_host_owned_percent() -> None:
    with pytest.raises(ActivityDefinitionShapeError, match="host-owned"):
        validate_component_definition("didact.progress", {"kind": "lesson", "label": "Lección", "value": 80})


def test_authored_mastery_cannot_include_host_owned_level() -> None:
    with pytest.raises(ActivityDefinitionShapeError, match="host-owned"):
        validate_component_definition("didact.mastery-badge", {"label": "Dominio", "level": "advanced"})
