"""Transactional, provider-neutral bridge from submissions to learner mastery."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from src.models import UserRole
from src.models.activity_definition import ActivityDefinition
from src.models.learning_experience import ExperienceAttempt, NormalizedEvidence
from src.repositories.activity_definition_repo import (
    ActivityDefinitionRepository,
    ActivityStateRepository,
)
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.experience_attempt_repo import ExperienceAttemptRepository
from src.schemas.learning_experience import (
    ExperienceAttemptRead,
    ExperienceAttemptSubmission,
    NormalizedEvidenceRead,
)
from src.services.activity_definitions import ActivityDefinitionService
from src.services.activity_ports import PortDeclined
from src.services.course_delivery import resolve_delivery
from src.services.mastery_evidence_service import MasteryEvidenceService


def _digest(value: object) -> str:
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def attempt_request_digest(
    *, activity_id: uuid.UUID, body: ExperienceAttemptSubmission
) -> str:
    """Canonical fingerprint used to distinguish a retry from a collision."""

    return _digest(
        {
            "attempt_id": str(body.attempt_id),
            "activity_id": str(activity_id),
            "binding_id": str(body.binding_id),
            "submission": body.submission,
            "duration_ms": body.duration_ms,
        }
    )


def _is_admin(user: Any) -> bool:
    return str(getattr(user.role, "value", user.role)) == UserRole.ADMIN.value


class ExperienceAttemptService:
    """Own one atomic attempt; the route remains the transaction boundary."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        attempts: ExperienceAttemptRepository | None = None,
        activities: ActivityDefinitionService | None = None,
        mastery: MasteryEvidenceService | None = None,
        nodes: CourseNodeRepository | None = None,
        courses: CourseRepository | None = None,
        enrollments: EnrollmentRepository | None = None,
    ) -> None:
        self.session = session
        self.attempts = attempts or ExperienceAttemptRepository(session)
        self.activities = activities or ActivityDefinitionService(
            ActivityDefinitionRepository(session), ActivityStateRepository(session)
        )
        self.mastery = mastery or MasteryEvidenceService(session)
        self.nodes = nodes or CourseNodeRepository(session)
        self.courses = courses or CourseRepository(session)
        self.enrollments = enrollments or EnrollmentRepository(session)

    async def submit(
        self,
        *,
        user: Any,
        activity_id: uuid.UUID,
        body: ExperienceAttemptSubmission,
    ) -> ExperienceAttemptRead:
        request_digest = attempt_request_digest(activity_id=activity_id, body=body)

        # Lock first: an exact concurrent retry waits for the winner to commit and then
        # reads its immutable result. A rolled-back winner leaves no row, so the waiter
        # safely evaluates once instead.
        await self.attempts.lock_attempt(body.attempt_id)
        existing = await self.attempts.get_attempt(body.attempt_id)
        if existing is not None:
            if (
                existing.user_id != user.id
                or existing.org_id != user.org_id
                or existing.request_digest != request_digest
            ):
                raise ConflictError(
                    "attempt_id is already associated with another submission",
                    field="attempt_id",
                )

        activity = await self.activities.get(activity_id, user.org_id)
        chain = await self.attempts.get_binding_chain(
            binding_id=body.binding_id, org_id=user.org_id
        )
        if chain is None:
            raise NotFoundError("implementation_bindings", str(body.binding_id))

        node, course = await self._authorize_chain(
            user=user, activity=activity, chain=chain
        )
        if existing is not None:
            return await self._read(existing)
        evaluated = await self.activities.evaluate(activity, body.submission)
        if isinstance(evaluated, PortDeclined):
            raise ValidationError(
                f"activity cannot be evaluated: {evaluated.reason}",
                field="submission",
            )
        outcome, score, passed, hints_used, error_kind = self._validated_score(evaluated)

        # Different attempt IDs for the same learner/node are serialized as well. This
        # prevents two transitions from reading the same mastery state.
        await self.attempts.lock_learner_node(user_id=user.id, node_id=node.id)
        prior_failures = await self.attempts.prior_failures(
            user_id=user.id, node_id=node.id
        )
        mastery = await self.mastery.apply(
            user_id=user.id,
            node=node,
            course=course,
            score=score,
            passed=passed,
            error_kind=error_kind,
            hints_used=hints_used,
            prior_failures=prior_failures,
        )

        state_value = str(getattr(mastery.state.state, "value", mastery.state.state))
        public_result = {
            **evaluated,
            "mastery": float(mastery.state.mastery or 0.0),
            "state": state_value,
            "consecutive_correct": int(mastery.state.consecutive_correct or 0),
            "consecutive_failed": int(mastery.state.consecutive_failed or 0),
            "show_worked_solution": mastery.transition.show_worked_solution,
        }
        attempt = ExperienceAttempt(
            id=body.attempt_id,
            org_id=user.org_id,
            user_id=user.id,
            course_id=course.id,
            node_id=node.id,
            intent_id=chain.intent.id,
            variant_id=chain.variant.id,
            binding_id=chain.binding.id,
            activity_definition_id=activity.id,
            request_digest=request_digest,
            outcome=outcome,
            score=score,
            passed=passed,
            hints_used=hints_used,
            duration_ms=body.duration_ms,
            result=public_result,
        )
        # Evidence keeps the binding's opaque immutable reference. Consumers do not
        # parse it, while audits retain the exact provider/version provenance.
        implementation_ref = chain.binding.definition_ref
        evidence_values = {
            "evidence_key": "primary",
            "objective_id": chain.intent.objective_id,
            "objective_version": chain.intent.objective_version,
            "evidence_type": (
                chain.intent.required_evidence[0]
                if chain.intent.required_evidence
                else "performance"
            ),
            "score": score,
            "outcome": outcome,
            "error_kind": error_kind,
            "hints_used": hints_used,
            "duration_ms": body.duration_ms,
            "implementation_ref": implementation_ref,
        }
        evidence = NormalizedEvidence(
            id=uuid.uuid4(),
            attempt_id=body.attempt_id,
            **evidence_values,
            evidence_digest=_digest(evidence_values),
        )
        await self.attempts.create_attempt(attempt=attempt, evidence=[evidence])
        if getattr(mastery.transition, "increment_nodes_completed", False):
            # Progress advanced: pre-warm the next nodes on this learner's own key so the
            # following lessons are ready when they reach them (sliding window). The warm task
            # runs in its own sessions off committed state; scheduling it is fire-and-forget.
            from src.services.node_render_service import spawn_prewarm_sliding_window

            spawn_prewarm_sliding_window(
                user_id=user.id,
                node_id=node.id,
                course_id=course.id,
                org_id=user.org_id,
            )
        return await self._read(attempt, evidence=[evidence])

    async def _authorize_chain(self, *, user: Any, activity: ActivityDefinition, chain):
        binding = chain.binding
        variant = chain.variant
        intent = chain.intent
        if binding.variant_id != variant.id or variant.intent_id != intent.id:
            raise ValidationError("invalid experience binding chain", field="binding_id")
        if binding.activity_definition_id != activity.id:
            raise ValidationError(
                "binding_id does not implement the requested activity",
                field="binding_id",
            )
        if intent.course_id != activity.course_id or intent.node_id != activity.node_id:
            raise ValidationError(
                "activity does not belong to the bound experience intent",
                field="binding_id",
            )
        node = await self.nodes.get_scoped(intent.node_id, user.org_id)
        if node is None or node.archived or node.course_id != intent.course_id:
            raise NotFoundError("course_nodes", str(intent.node_id))
        course = await self.courses.get_scoped(intent.course_id, user.org_id)
        if course is None or resolve_delivery(course) != "dynamic":
            raise NotFoundError("course_nodes", str(intent.node_id))
        if not _is_admin(user):
            enrollment = await self.enrollments.get_by_user_and_course(
                user.id, course.id
            )
            if enrollment is None:
                raise ForbiddenError("You are not enrolled in this course")
        return node, course

    @staticmethod
    def _validated_score(
        evaluated: dict,
    ) -> tuple[str, float, bool, int, str | None]:
        outcome = evaluated.get("outcome")
        if outcome not in {"correct", "incorrect", "partial"}:
            raise ValidationError("evaluation did not produce scored evidence")
        score_value = evaluated.get("score")
        passed_value = evaluated.get("passed")
        if isinstance(score_value, bool) or not isinstance(score_value, (int, float)):
            raise ValidationError("evaluation returned an invalid score")
        score = float(score_value)
        if not 0.0 <= score <= 1.0 or not isinstance(passed_value, bool):
            raise ValidationError("evaluation returned an invalid scoring shape")
        hints_value = evaluated.get("hints_used", 0)
        if isinstance(hints_value, bool) or not isinstance(hints_value, int) or hints_value < 0:
            raise ValidationError("evaluation returned an invalid hints_used")
        raw_error = evaluated.get("error_kind")
        if raw_error is not None and not isinstance(raw_error, str):
            raise ValidationError("evaluation returned an invalid error_kind")
        # A provider adapter may supply a richer, server-owned classification. The
        # neutral bridge must not infer pedagogy from a concrete component ID.
        error_kind = raw_error or (None if passed_value else f"{outcome}_response")
        return outcome, score, passed_value, hints_value, error_kind

    async def _read(
        self,
        attempt: ExperienceAttempt,
        *,
        evidence: list[NormalizedEvidence] | None = None,
    ) -> ExperienceAttemptRead:
        rows = (
            evidence
            if evidence is not None
            else list(await self.attempts.evidence_for_attempt(attempt.id))
        )
        return ExperienceAttemptRead(
            attempt_id=attempt.id,
            org_id=attempt.org_id,
            user_id=attempt.user_id,
            course_id=attempt.course_id,
            node_id=attempt.node_id,
            intent_id=attempt.intent_id,
            variant_id=attempt.variant_id,
            binding_id=attempt.binding_id,
            activity_definition_id=attempt.activity_definition_id,
            request_digest=attempt.request_digest,
            outcome=attempt.outcome,
            score=attempt.score,
            passed=attempt.passed,
            hints_used=attempt.hints_used,
            duration_ms=attempt.duration_ms,
            result=dict(attempt.result or {}),
            created_at=attempt.created_at,
            evidence=[NormalizedEvidenceRead.model_validate(row) for row in rows],
        )


__all__ = ["ExperienceAttemptService", "attempt_request_digest"]
