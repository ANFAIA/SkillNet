"""Read-only ProgressPort projection from SkillNet node mastery.

The learner never writes percent, status or mastery through this port. Missing
state is an honest not-started snapshot, not invented competence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.models.learner_node_state import LearnerNodeState, NodeState


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


def _status(state: NodeState | None) -> ProgressStatus:
    if state is None or state is NodeState.NOT_STARTED:
        return "not_started"
    if state is NodeState.MASTERED:
        return "completed"
    return "in_progress"


def _percent(row: LearnerNodeState | None) -> int:
    if row is None:
        return 0
    if row.state is NodeState.MASTERED:
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
    status = _status(None if row is None else row.state)
    progress = _percent(row)
    return ActivityProgress(
        component_id=component_id,
        status=status,
        progress=progress,
        level=_level(status, progress),
    )


__all__ = ["ActivityProgress", "project_activity_progress"]
