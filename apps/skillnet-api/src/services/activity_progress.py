"""Read-only ProgressPort projection from SkillNet node mastery.

The learner never writes percent, status or mastery through this port. Missing
state is an honest not-started snapshot, not invented competence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.models.learner_node_state import LearnerNodeState, NodeState
from src.services.node_progression import is_done


ProgressStatus = Literal["not_started", "in_progress", "completed"]
MasteryLevel = Literal["beginner", "intermediate", "advanced"]


@dataclass(frozen=True, slots=True)
class ActivityProgress:
    component_id: str
    status: ProgressStatus
    progress: int
    level: MasteryLevel

    def as_payload(self) -> dict[str, str | int]:
        return {
            "component_id": self.component_id,
            "status": self.status,
            "progress": self.progress,
            "level": self.level,
        }


def _status(row: LearnerNodeState | None) -> ProgressStatus:
    """"Completed" is ``node_progression.is_done``, not ``state is MASTERED``.

    This used to ask the evidence machine alone, which meant an expository node reported
    ``not_started`` for ever no matter how completely somebody worked through it — it has
    no graded item, so it never leaves that state. It was one of the two places that wrote
    the "done" predicate by hand outside the module that owns it.
    """
    if is_done(row):
        return "completed"
    if row is None or row.state is NodeState.NOT_STARTED:
        return "not_started"
    return "in_progress"


def _percent(row: LearnerNodeState | None) -> int:
    if row is None:
        return 0
    if is_done(row):
        return 100
    return max(0, min(100, round(float(row.mastery) * 100)))


def _level(status: ProgressStatus, percent: int) -> MasteryLevel:
    if status == "completed" or percent >= 80:
        return "advanced"
    if status == "not_started" or percent < 34:
        return "beginner"
    return "intermediate"


def project_activity_progress(
    component_id: str, row: LearnerNodeState | None
) -> ActivityProgress:
    status = _status(row)
    progress = _percent(row)
    return ActivityProgress(
        component_id=component_id,
        status=status,
        progress=progress,
        level=_level(status, progress),
    )


__all__ = ["ActivityProgress", "project_activity_progress"]
