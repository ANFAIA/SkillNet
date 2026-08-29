"""Apply server-scored evidence to the learner domain in one transaction.

Providers grade or translate a submission before calling this service.  From this
boundary onwards the component that produced the evidence is irrelevant: node mastery,
profile signals, verified skills and dynamic-course closure all share one path.

The service deliberately does not commit.  The caller owns the transaction that also
persists the immutable attempt and normalized evidence rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from hashlib import blake2b

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Course, CourseNode, LearnerNodeState
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.learning_event_repo import LearningEventRepository
from src.repositories.skill_repo import SkillRepository
from src.services.enrollment_service import EnrollmentService
from src.services.learner_profile_service import LearnerProfileService, NodeSignalContext
from src.services.mastery_service import (
    Transition,
    mastery_prior,
    threshold_for,
    transition_on_answer,
)
from src.services.skill_service import SkillService


@dataclass(frozen=True, slots=True)
class MasteryEvidenceResult:
    state: LearnerNodeState
    transition: Transition


class MasteryEvidenceService:
    """Translate one trusted score into all learner-domain side effects."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        states: LearnerNodeStateRepository | None = None,
        profile_repository: LearnerProfileRepository | None = None,
    ) -> None:
        self.session = session
        self.states = states or LearnerNodeStateRepository(session)
        self.profile_repository = profile_repository or LearnerProfileRepository(session)
        self.events = LearningEventRepository(session)
        self.profiles = LearnerProfileService(
            LearnerProfileRepository(session), self.events
        )
        self.skills = SkillService(SkillRepository(session))
        self.enrollments = EnrollmentService(
            EnrollmentRepository(session),
            CourseRepository(session),
            ExerciseRepository(session),
        )

    async def apply(
        self,
        *,
        user_id: uuid.UUID,
        node: CourseNode,
        course: Course,
        score: float,
        passed: bool,
        error_kind: str | None,
        hints_used: int = 0,
        item_failures: int = 0,
    ) -> MasteryEvidenceResult:
        """Apply evidence without committing the surrounding transaction.

        ``item_failures`` is passed straight through to :func:`transition_on_answer` and
        carries its contract unchanged: **failures of the one item being answered**, before
        this answer, not failures of the node. The name used to be ``prior_failures``, and
        that vagueness cost real behaviour — three callers read the same parameter three
        different ways (per item, per node, and per node for the learner's whole life) and
        rule 8 started handing the worked solution to activities nobody had failed. If a
        caller cannot count per item, that is a defect to report, not a number to
        approximate: say so at the call site.
        """

        await self.lock_learner_node(user_id=user_id, node_id=node.id)
        skill_level = await self.skills.level_for_skill(
            user_id=user_id, skill_id=node.skill_id
        )
        state = await self.states.get_or_create(
            user_id=user_id,
            node_id=node.id,
            mastery=mastery_prior(skill_level),
        )
        transition = transition_on_answer(
            state=state.state,
            mastery=float(state.mastery or 0.0),
            consecutive_correct=int(state.consecutive_correct or 0),
            consecutive_failed=int(state.consecutive_failed or 0),
            score=score,
            passed=passed,
            threshold=threshold_for(node.criticality, node.mastery_threshold),
            hints_used=hints_used,
            item_failures=item_failures,
            error_kind=error_kind,
        )
        await self.states.apply_transition(state, transition)

        profile = await self.profile_repository.get_by_user(user_id)
        if profile is not None:
            if transition.increment_nodes_completed:
                await self.profiles.increment_nodes_completed(profile=profile)
                await self.profiles.refresh_format_vector(profile=profile)
            await self.profiles.apply_signals(
                profile=profile,
                context=await self._signal_context(user_id, node, state),
            )

        if transition.increment_nodes_completed:
            await self.skills.record_mastery(
                user_id=user_id,
                skill_id=node.skill_id,
                mastery=float(state.mastery or 0.0),
            )
            await self.enrollments.close_dynamic_if_mastered(
                course=course,
                user_id=user_id,
            )

        return MasteryEvidenceResult(state=state, transition=transition)

    async def lock_learner_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> None:
        """Serialize mastery transitions for one learner/node on PostgreSQL.

        The lock covers both first-row creation and later updates, so concurrent
        providers cannot race the unique constraint or overwrite each other's streak.
        Unit tests may use a non-PostgreSQL session, where row-level concurrency is not
        representative and this database-specific lock is intentionally skipped.
        """

        try:
            dialect = self.session.get_bind().dialect.name
        except (AttributeError, TypeError):
            return
        if dialect != "postgresql":
            return
        payload = user_id.bytes + node_id.bytes
        key = int.from_bytes(blake2b(payload, digest_size=8).digest(), "big", signed=True)
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": key},
        )

    async def _signal_context(
        self,
        user_id: uuid.UUID,
        node: CourseNode,
        state: LearnerNodeState,
    ) -> NodeSignalContext:
        unmastered = await self.states.unmastered_prerequisites(
            user_id=user_id,
            node_id=node.id,
        )
        recent = await self.events.recent_types_for_node(
            user_id=user_id,
            node_id=node.id,
            limit=3,
        )
        return NodeSignalContext(
            node_id=node.id,
            consecutive_failed=int(state.consecutive_failed or 0),
            consecutive_correct=int(state.consecutive_correct or 0),
            last_error_kind=state.last_error_kind,
            recent_event_types=tuple(recent),
            unmastered_prerequisites=len(unmastered),
        )


__all__ = ["MasteryEvidenceResult", "MasteryEvidenceService"]
