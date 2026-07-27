"""Enrollment business logic: assignment, progress, and removal rules.

Two closing rules live here, and they must never mix:

* **v1 (static).** ``complete()``: every lesson visited and every exercise passed.
  Byte-for-byte the rule it has always been. Driven by the learner pressing "he
  terminado" on ``POST /enrollments/{id}/complete``.
* **v2 (dynamic).** §7.5: every non-archived ``critical`` node of the course is
  ``mastered`` — by demonstration, by probe or by ``waive``. ``recommended`` and
  ``contextual`` never block. ``score`` is the mean ``mastery`` over exactly those
  critical nodes. Nobody presses anything: the enrollment closes the moment the last
  critical node closes, and it can *reopen* when the creator adds a new critical node.

Which of the two applies is decided by ``resolve_delivery`` — the single decision point
of §10.1 — everywhere except one place, documented on
:meth:`recompute_dynamic_closure`, where it cannot be: ``PUT /courses/{id}/schema``
runs while the course is still ``proposed``, so the course is *by construction* not
dynamic yet at the moment §7.5 requires the recompute.

The rule itself is not written twice. ``mastery_service.evaluate_course_completion`` is
the pure form (unit-testable with plain dataclasses, no DB) and
:func:`apply_dynamic_closure` is the one function that turns its verdict into a mutation
of an ``enrollments`` row. ``CourseSchemaService.recompute_enrollment_closure`` calls
both, so the schema editor and the runtime can never disagree about what "completed"
means — which matters because that number is printed on a certificate.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select

from src.config import settings
from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.logging import get_logger
from src.models import Enrollment, EnrollmentStatus
from src.models.course_skill import CourseSkill
from src.models.user_skill import SkillLevel, UserSkill
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.repositories.lesson_progress_repo import LessonProgressRepository
from src.services.course_delivery import resolve_delivery
from src.services.mastery_service import (
    CourseCompletion,
    evaluate_course_completion,
)
from src.services.skill_service import mastery_to_level

logger = get_logger(__name__)

#: Where a dynamic enrollment goes when it stops being complete. Not ``ASSIGNED``:
#: the learner demonstrably started, and sending them back to "sin empezar" would
#: lose that fact and re-trigger every "tienes formación nueva" surface.
REOPENED_STATUS = EnrollmentStatus.IN_PROGRESS


@dataclass(frozen=True)
class NodeProgressRow:
    """One ``(course_nodes, learner_node_states)`` pair, as §7.5 needs it.

    ``mastery_service.NodeProgressLike`` is a structural protocol, so this is only a
    convenience: neither half of the rule lives in a single table, and the ORM has no
    row shaped like the join.
    """

    node_id: uuid.UUID
    criticality: Any
    archived: bool
    state: str
    mastery: float


def apply_dynamic_closure(
    enrollment: Any,
    completion: CourseCompletion,
    *,
    now: datetime | None = None,
) -> str | None:
    """Move one enrollment to match the §7.5 verdict. Returns what happened.

    ``"completed"``, ``"reopened"`` or ``None`` when the row already agreed with the
    verdict. Pure apart from the clock, so both callers (the runtime and the schema
    editor) share one definition of the mutation and not just of the predicate.

    ``total_critical == 0`` is treated as **"no opinion"**, never as "not complete":
    a course mid-edit with no critical node yet cannot be evaluated, and reopening
    every completed enrollment because the creator momentarily deleted the last
    critical node would corrupt real records for a transient state. The validation
    gate of §11.1 requires at least one critical node, so a *validated* course never
    reaches this branch.
    """
    if completion.total_critical == 0:
        return None

    moment = now or datetime.now(timezone.utc)
    if completion.can_complete and enrollment.status != EnrollmentStatus.COMPLETED:
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = moment
        enrollment.score = completion.score
        return "completed"
    if not completion.can_complete and enrollment.status == EnrollmentStatus.COMPLETED:
        enrollment.status = REOPENED_STATUS
        enrollment.completed_at = None
        return "reopened"
    return None


class EnrollmentService:
    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        course_repo: CourseRepository,
        exercise_repo: ExerciseRepository,
        lesson_progress_repo: LessonProgressRepository | None = None,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.course_repo = course_repo
        self.exercise_repo = exercise_repo
        self.lesson_progress_repo = lesson_progress_repo or LessonProgressRepository(
            enrollment_repo.session
        )

    async def assign(
        self,
        *,
        org_id: uuid.UUID,
        assigned_by: uuid.UUID,
        course_id: uuid.UUID,
        user_ids: list[uuid.UUID],
        deadline: date | None,
    ) -> list[Enrollment]:
        course = await self.course_repo.get_scoped(course_id, org_id)
        if course is None:
            raise NotFoundError("courses", str(course_id))

        created: list[Enrollment] = []
        for user_id in user_ids:
            existing = await self.enrollment_repo.get_by_user_and_course(
                user_id, course_id
            )
            if existing is not None:
                raise ConflictError(
                    f"User {user_id} is already enrolled in this course"
                )
            enrollment = await self.enrollment_repo.create(
                user_id=user_id,
                course_id=course_id,
                assigned_by=assigned_by,
                status=EnrollmentStatus.ASSIGNED,
                deadline=deadline,
            )
            created.append(enrollment)
        return created

    async def get_scoped(
        self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID
    ) -> Enrollment:
        enrollment = await self.enrollment_repo.get_with_course(enrollment_id)
        if enrollment is None or enrollment.course.org_id != org_id:
            raise NotFoundError("enrollments", str(enrollment_id))
        return enrollment

    async def list_enrollments(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        course_id: uuid.UUID | None,
        status: EnrollmentStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Enrollment], int]:
        return await self.enrollment_repo.list_enrollments(
            org_id=org_id,
            user_id=user_id,
            course_id=course_id,
            status=status,
            offset=offset,
            limit=limit,
        )

    async def compute_progress(
        self, *, enrollment: Enrollment, org_id: uuid.UUID
    ) -> float | None:
        """Fraction of lessons completed.

        A lesson is "completed" when:
        - it has been visited (a ``LessonProgress`` row exists), AND
        - all its exercises (if any) have a passing attempt.

        Progress = completed_lessons / total_lessons.
        """
        course = await self.course_repo.get_detail(enrollment.course_id, org_id)
        if course is None or not course.modules:
            return 1.0

        all_lessons = [
            lesson
            for module in course.modules
            for lesson in module.lessons
        ]
        if not all_lessons:
            return 1.0

        # Gather all lesson & exercise ids for batch queries.
        all_lesson_ids = [lesson.id for lesson in all_lessons]
        all_exercise_ids = [
            exercise.id
            for lesson in all_lessons
            for exercise in lesson.exercises
        ]

        visited = await self.lesson_progress_repo.completed_lesson_ids(
            user_id=enrollment.user_id, lesson_ids=all_lesson_ids
        )
        passed = await self.exercise_repo.passed_exercise_ids(
            user_id=enrollment.user_id, exercise_ids=all_exercise_ids
        )

        completed = 0
        for lesson in all_lessons:
            if lesson.id not in visited:
                continue
            lesson_exercise_ids = [ex.id for ex in lesson.exercises]
            if all(eid in passed for eid in lesson_exercise_ids):
                completed += 1

        return completed / len(all_lessons)

    async def complete(
        self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Enrollment, float]:
        """Mark an enrollment as completed, compute and store the final score.

        Returns the updated enrollment and its progress value.
        """
        enrollment = await self.get_scoped(
            enrollment_id=enrollment_id, org_id=org_id
        )
        if enrollment.user_id != user_id:
            raise ForbiddenError("You can only complete your own enrollments")

        if enrollment.status == EnrollmentStatus.COMPLETED:
            progress = await self.compute_progress(
                enrollment=enrollment, org_id=org_id
            )
            # Grant the skills even on the idempotent path. The status is not only
            # written here: `routes/lessons.py`, `exercise_service._update_enrollment_
            # progress` and `course_service` all flip an enrollment to `completed` the
            # moment progress reaches 1.0, and none of them assign skills. So by the time
            # the learner posts the explicit `/complete`, the early return above was
            # reached and `user_skills` stayed empty — the course was finished and taught
            # the org nothing. `_assign_course_skills` is idempotent (it only ever raises
            # a level, never lowers one), so re-running it converges on the intended end
            # state instead of depending on which side door closed the enrollment first.
            await self._assign_course_skills(enrollment.user_id, enrollment.course_id)
            return enrollment, progress or 0.0

        progress = await self.compute_progress(
            enrollment=enrollment, org_id=org_id
        )
        if progress is None or progress < 1.0:
            raise ConflictError(
                "Cannot complete enrollment: not all lessons are finished. "
                f"Current progress: {int((progress or 0) * 100)}%"
            )
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = datetime.now(timezone.utc)
        enrollment.score = progress
        await self.enrollment_repo.session.flush()

        # Assign skills linked to the course.
        await self._assign_course_skills(enrollment.user_id, enrollment.course_id)

        return enrollment, progress or 0.0

    async def _assign_course_skills(
        self,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
        level: SkillLevel | None = None,
    ) -> None:
        """Assign skills linked to the completed course to the user.

        When a user completes a course, they earn all skills associated
        with that course at 'medium' level (first completion) or keep
        their existing level if already higher.

        ``level`` is the v2 addition and defaults to ``MEDIUM``, so the v1 call site is
        unchanged. A dynamic course passes the ``mastery -> skill_level`` translation of
        §3.3 applied to ``enrollments.score``: finishing a course where every critical
        node was mastered at 0.95 is more evidence than finishing one at 0.72, and v1
        had no number to tell them apart. The never-downgrade rule below is untouched
        and is what makes passing a lower level harmless.
        """
        db = self.enrollment_repo.session
        granted = level or SkillLevel.MEDIUM

        # Find skills linked to this course.
        result = await db.execute(
            select(CourseSkill.skill_id).where(CourseSkill.course_id == course_id)
        )
        skill_ids = [row[0] for row in result.all()]
        if not skill_ids:
            return

        for skill_id in skill_ids:
            # Check if user already has this skill.
            existing = await db.execute(
                select(UserSkill).where(
                    UserSkill.user_id == user_id,
                    UserSkill.skill_id == skill_id,
                )
            )
            user_skill = existing.scalar_one_or_none()

            if user_skill is not None:
                # Only upgrade, never downgrade.
                level_order = {SkillLevel.LOW: 0, SkillLevel.MEDIUM: 1, SkillLevel.HIGH: 2}
                if level_order.get(user_skill.level, 0) < level_order[granted]:
                    user_skill.level = granted
                    user_skill.source = "course_completion"
                    user_skill.last_assessed_at = datetime.now(timezone.utc)
            else:
                db.add(UserSkill(
                    user_id=user_id,
                    skill_id=skill_id,
                    level=granted,
                    source="course_completion",
                ))

        await db.flush()
        logger.info(
            "Assigned %d skills to user %s from course %s",
            len(skill_ids), user_id, course_id,
        )

    # ------------------------------------------------------------------
    # §7.5 — course closing on the dynamic branch
    # ------------------------------------------------------------------

    async def node_progress(
        self, *, course_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[NodeProgressRow]:
        """The ``(node, state)`` join §7.5 evaluates, for one learner.

        Archived nodes are excluded at the query, and a node with no
        ``learner_node_states`` row counts as ``not_started`` with ``mastery = 0.0`` —
        which is the truth, and is what keeps a course from completing because nobody
        ever opened the last node.
        """
        db = self.enrollment_repo.session
        node_repo = CourseNodeRepository(db)
        nodes = list(await node_repo.list_for_course(course_id, include_archived=False))
        if not nodes:
            return []
        states = await LearnerNodeStateRepository(db).states_for_nodes(
            user_id=user_id, node_ids=[node.id for node in nodes]
        )
        rows: list[NodeProgressRow] = []
        for node in nodes:
            state = states.get(node.id)
            rows.append(
                NodeProgressRow(
                    node_id=node.id,
                    criticality=node.criticality,
                    archived=bool(node.archived),
                    state="not_started"
                    if state is None
                    else str(getattr(state.state, "value", state.state)),
                    mastery=float(getattr(state, "mastery", 0.0) or 0.0),
                )
            )
        return rows

    async def evaluate_dynamic(
        self, *, course_id: uuid.UUID, user_id: uuid.UUID
    ) -> CourseCompletion:
        """§7.5's verdict for one learner on one dynamic course. Writes nothing."""
        return evaluate_course_completion(
            await self.node_progress(course_id=course_id, user_id=user_id)
        )

    async def close_dynamic_if_mastered(
        self, *, course: Any, user_id: uuid.UUID
    ) -> tuple[Enrollment | None, CourseCompletion | None]:
        """Close (or reopen) this learner's enrollment after a node changed state.

        Called from ``POST /nodes/{id}/answer`` on the ``learning -> mastered``
        transition and from ``POST /nodes/{id}/waive``: those are the only two events
        that can make the last critical node of a course ``mastered``. Nothing else
        closes a dynamic course — there is no "he terminado" button, because the rule is
        computable and asking would let a learner claim a course they have not mastered.

        Gated on ``resolve_delivery``, so a static course is never touched by this path
        and its v1 rule keeps its monopoly. Returns ``(enrollment, completion)`` with
        ``enrollment = None`` when there is nothing enrolled (a learner may open a node
        of a published course they were never assigned) and ``completion = None`` when
        the course is not on the dynamic branch at all.
        """
        if resolve_delivery(course, settings) != "dynamic":
            return None, None

        completion = await self.evaluate_dynamic(
            course_id=course.id, user_id=user_id
        )
        enrollment = await self.enrollment_repo.get_by_user_and_course(
            user_id, course.id
        )
        if enrollment is None:
            return None, completion

        outcome = apply_dynamic_closure(enrollment, completion)
        if outcome is None:
            return enrollment, completion

        await self.enrollment_repo.session.flush()
        if outcome == "completed":
            # §7.5: `_assign_course_skills` keeps granting the course's skills, now with
            # the mastery translation of §3.3 and still only upwards.
            await self._assign_course_skills(
                user_id,
                course.id,
                mastery_to_level(completion.score or 0.0),
            )
        logger.info(
            "Dynamic enrollment %s for user %s on course %s: %s (%d/%d critical)",
            enrollment.id,
            user_id,
            course.id,
            outcome,
            completion.mastered_critical,
            completion.total_critical,
        )
        return enrollment, completion

    async def recompute_dynamic_closure(
        self,
        *,
        course: Any,
        org_id: uuid.UUID,
        enrollments: Iterable[Any] | None = None,
        limit: int = 1000,
    ) -> dict[str, int]:
        """Re-evaluate §7.5 for **every** enrollment of a course whose schema changed.

        §7.5 makes this mandatory in the same transaction as ``PUT /courses/{id}/schema``
        and ``POST …/schema/validate``: those calls change the set of critical nodes,
        which *is* the closing condition. A completed enrollment can reopen (a new
        critical node appeared) and a stuck one can complete (the node that was missing
        got archived). Without it, enrollment status would be a function of a schema
        that no longer exists.

        **The one place ``resolve_delivery`` is not the gate**, and deliberately: a
        ``PUT`` is only legal while the course is ``proposed`` (a validated schema is
        ``422 schema_locked``), so at that moment the course is not dynamic yet and a
        ``resolve_delivery`` gate would make the recompute §7.5 demands dead code. The
        gate that *is* correct here is inside :func:`apply_dynamic_closure`: with no
        critical node the function has no opinion, so a pure v1 course — which has no
        ``course_nodes`` at all — cannot have its enrollments touched by an admin
        editing somebody else's schema.

        ``enrollments`` is injectable so the caller can pass rows it already loaded.
        """
        rows_by_user: dict[uuid.UUID, list[NodeProgressRow]] = {}
        if enrollments is None:
            enrollments, _total = await self.enrollment_repo.list_enrollments(
                org_id=org_id,
                user_id=None,
                course_id=course.id,
                status=None,
                offset=0,
                limit=limit,
            )
        enrollments = list(enrollments)
        if not enrollments:
            return {"completed": 0, "reopened": 0}

        counts = {"completed": 0, "reopened": 0}
        now = datetime.now(timezone.utc)
        for enrollment in enrollments:
            rows = rows_by_user.get(enrollment.user_id)
            if rows is None:
                rows = await self.node_progress(
                    course_id=course.id, user_id=enrollment.user_id
                )
                rows_by_user[enrollment.user_id] = rows
            outcome = apply_dynamic_closure(
                enrollment, evaluate_course_completion(rows), now=now
            )
            if outcome is not None:
                counts[outcome] += 1
        await self.enrollment_repo.session.flush()
        return counts

    async def delete(self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID) -> None:
        enrollment = await self.get_scoped(
            enrollment_id=enrollment_id, org_id=org_id
        )
        if enrollment.status != EnrollmentStatus.ASSIGNED:
            raise ConflictError("Only assigned (not started) enrollments can be removed")
        await self.enrollment_repo.delete(enrollment)
