"""§7.5 course closing and the ``mastery <-> user_skills`` bridge of §3.3 / §7.1.

Unit level: no database, no network. The pieces under test are the ones B11 added,
and each is here for a reason a reader can check against the spec:

* :func:`apply_dynamic_closure` is the **only** mutation of ``enrollments`` on the
  dynamic branch, shared by the runtime and by the schema editor so the two cannot
  disagree about what "completed" means — the number a certificate prints.
* Its ``total_critical == 0`` case is the guard that keeps an admin editing a v2
  schema from reopening the completed **v1** enrollments of a course that has no
  ``course_nodes`` at all. Before B11 that path reopened them, silently.
* ``EnrollmentService.close_dynamic_if_mastered`` is gated on ``resolve_delivery``,
  the single decision point of §10.1. A static course must come out of it untouched
  even when it happens to have nodes and mastered states.
* ``mastery_to_level`` / ``SkillService.record_mastery`` are the §3.3 translation and
  the never-downgrade rule. A weak answer on one node may not retract a competence a
  human verified: ``user_skills`` is what "who knows X" answers.

The DB-touching halves (``node_progress`` and the recompute over many enrollments) are
exercised end to end in ``tests/integration/test_dynamic_flow.py``; they are pure
SQLAlchemy and §12.2 puts real SQL behind ``@pytest.mark.integration``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.models import (
    Course,
    CourseDeliveryMode,
    CourseSchemaStatus,
    EnrollmentStatus,
    NodeCriticality,
)
from src.models.user_skill import SkillLevel, UserSkill
from src.services.enrollment_service import (
    REOPENED_STATUS,
    EnrollmentService,
    NodeProgressRow,
    apply_dynamic_closure,
)
from src.services.mastery_service import evaluate_course_completion
from src.services.skill_service import SkillService, mastery_to_level

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
SKILL_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


# --------------------------------------------------------------------------- #
# Builders and fakes
# --------------------------------------------------------------------------- #
@dataclass
class FakeEnrollment:
    status: EnrollmentStatus
    completed_at: datetime | None = None
    score: float | None = None
    id: uuid.UUID = uuid.uuid4()
    user_id: uuid.UUID = USER_ID


def row(
    *,
    criticality: NodeCriticality = NodeCriticality.CRITICAL,
    state: str = "mastered",
    mastery: float = 0.9,
    archived: bool = False,
) -> NodeProgressRow:
    return NodeProgressRow(
        node_id=uuid.uuid4(),
        criticality=criticality,
        archived=archived,
        state=state,
        mastery=mastery,
    )


def make_course(
    *,
    mode: CourseDeliveryMode = CourseDeliveryMode.DYNAMIC,
    status: CourseSchemaStatus = CourseSchemaStatus.VALIDATED,
) -> Course:
    course = Course(
        org_id=ORG_ID,
        title="Politica de devoluciones",
        delivery_mode=mode,
        schema_status=status,
        schema_version=1,
        intent_density=3,
    )
    course.id = uuid.uuid4()
    return course


class FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalars(self) -> FakeResult:
        return self

    def first(self) -> Any:
        return self._value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeSession:
    """Enough of ``AsyncSession`` for a single-row read plus an ``add``/``flush``."""

    def __init__(self, value: Any = None) -> None:
        self.value = value
        self.added: list[Any] = []
        self.flushes = 0

    async def execute(self, _query: Any) -> FakeResult:
        return FakeResult(self.value)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1


class FakeEnrollmentRepo:
    """Only what ``EnrollmentService`` reads on the dynamic path."""

    def __init__(self, session: Any, enrollment: Any = None) -> None:
        self.session = session
        self.enrollment = enrollment
        self.lookups = 0

    async def get_by_user_and_course(self, _user_id, _course_id) -> Any:
        self.lookups += 1
        return self.enrollment


def make_service(session: Any, enrollment: Any = None) -> EnrollmentService:
    repo = FakeEnrollmentRepo(session, enrollment)
    return EnrollmentService(
        repo,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# apply_dynamic_closure — the one mutation
# --------------------------------------------------------------------------- #
def test_every_critical_node_mastered_completes_the_enrollment() -> None:
    enrollment = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    completion = evaluate_course_completion(
        [row(mastery=1.0), row(mastery=0.9)]
    )

    outcome = apply_dynamic_closure(enrollment, completion)

    assert outcome == "completed"
    assert enrollment.status == EnrollmentStatus.COMPLETED
    assert enrollment.completed_at is not None
    # The score is the mean mastery over the critical nodes and nothing else.
    assert enrollment.score == pytest.approx(0.95)


def test_every_node_must_be_mastered_regardless_of_criticality() -> None:
    """Closure now requires the whole course: any non-mastered node blocks it."""
    enrollment = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    completion = evaluate_course_completion(
        [
            row(mastery=0.9),
            row(criticality=NodeCriticality.RECOMMENDED, state="learning", mastery=0.1),
            row(criticality=NodeCriticality.CONTEXTUAL, state="not_started", mastery=0.0),
        ]
    )

    # A non-mastered recommended/contextual node now blocks closure too.
    assert apply_dynamic_closure(enrollment, completion) is None
    assert completion.can_complete is False
    assert len(completion.blocked_by) == 2

    # Once every node is mastered the course completes, and the score is the mean
    # mastery over all nodes.
    done = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    all_mastered = evaluate_course_completion(
        [
            row(mastery=0.9),
            row(criticality=NodeCriticality.RECOMMENDED, mastery=0.8),
            row(criticality=NodeCriticality.CONTEXTUAL, mastery=0.7),
        ]
    )
    assert apply_dynamic_closure(done, all_mastered) == "completed"
    assert done.score == pytest.approx((0.9 + 0.8 + 0.7) / 3)


def test_an_archived_critical_node_does_not_block_completion() -> None:
    enrollment = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    completion = evaluate_course_completion(
        [row(mastery=0.9), row(state="learning", mastery=0.2, archived=True)]
    )

    assert apply_dynamic_closure(enrollment, completion) == "completed"


def test_a_new_critical_node_reopens_a_completed_enrollment() -> None:
    enrollment = FakeEnrollment(
        status=EnrollmentStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
        score=1.0,
    )
    completion = evaluate_course_completion(
        [row(mastery=1.0), row(state="not_started", mastery=0.0)]
    )

    outcome = apply_dynamic_closure(enrollment, completion)

    assert outcome == "reopened"
    # Not `assigned`: the learner demonstrably started, and losing that would
    # re-trigger every "tienes formacion nueva" surface.
    assert enrollment.status == REOPENED_STATUS == EnrollmentStatus.IN_PROGRESS
    assert enrollment.completed_at is None


def test_a_needs_review_critical_node_keeps_the_enrollment_active() -> None:
    """§7.4: while a critical node is in ``needs_review`` the course stays ``active``."""
    enrollment = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    completion = evaluate_course_completion(
        [row(mastery=0.9), row(state="needs_review", mastery=0.4)]
    )

    assert apply_dynamic_closure(enrollment, completion) is None
    assert enrollment.status == EnrollmentStatus.IN_PROGRESS
    assert completion.can_complete is False
    assert len(completion.blocked_by) == 1


def test_a_course_with_no_critical_node_leaves_every_enrollment_alone() -> None:
    """The guard that protects v1 rows from a v2 schema edit.

    A course with no critical node cannot be evaluated by §7.5 — and a pure v1 course
    has no ``course_nodes`` at all, so it lands here. Reopening those enrollments is
    what the pre-B11 recompute did.
    """
    completed = FakeEnrollment(
        status=EnrollmentStatus.COMPLETED,
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        score=0.8,
    )
    completion = evaluate_course_completion([])

    assert apply_dynamic_closure(completed, completion) is None
    assert completed.status == EnrollmentStatus.COMPLETED
    assert completed.completed_at == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert completed.score == 0.8


def test_an_already_completed_enrollment_is_not_restamped() -> None:
    """Idempotence: the recompute runs on every PUT, so it must be a no-op when
    nothing changed. Restamping ``completed_at`` would rewrite history on each save."""
    stamped = datetime(2026, 2, 3, tzinfo=timezone.utc)
    enrollment = FakeEnrollment(
        status=EnrollmentStatus.COMPLETED, completed_at=stamped, score=0.91
    )
    completion = evaluate_course_completion([row(mastery=0.91)])

    assert apply_dynamic_closure(enrollment, completion) is None
    assert enrollment.completed_at == stamped
    assert enrollment.score == 0.91


# --------------------------------------------------------------------------- #
# The resolve_delivery gate — v1 safety
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_static_course_is_never_closed_by_the_node_rule() -> None:
    """§7.5 applies **only** on the dynamic branch, so v1's rule keeps its monopoly."""
    course = make_course(mode=CourseDeliveryMode.STATIC)
    enrollment = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    service = make_service(FakeSession(), enrollment)

    result = await service.close_dynamic_if_mastered(course=course, user_id=USER_ID)

    assert result == (None, None)
    assert enrollment.status == EnrollmentStatus.IN_PROGRESS
    # Not even the enrollment was looked up: the gate is the first statement.
    assert service.enrollment_repo.lookups == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_an_unvalidated_schema_is_not_the_dynamic_branch() -> None:
    course = make_course(status=CourseSchemaStatus.PROPOSED)
    service = make_service(FakeSession(), FakeEnrollment(EnrollmentStatus.IN_PROGRESS))

    assert await service.close_dynamic_if_mastered(
        course=course, user_id=USER_ID
    ) == (None, None)


@pytest.mark.asyncio
async def test_dynamic_progress_wins_even_when_v1_fallback_modules_exist() -> None:
    """A validated v2 course may retain v1 modules; §7.5 still owns its progress."""
    course = SimpleNamespace(
        id=uuid.uuid4(),
        delivery_mode=CourseDeliveryMode.DYNAMIC,
        schema_status=CourseSchemaStatus.VALIDATED,
        modules=[SimpleNamespace(lessons=[])],
    )

    class CourseRepo:
        async def get_detail(self, _course_id, _org_id):
            return course

    enrollment = FakeEnrollment(status=EnrollmentStatus.COMPLETED)
    enrollment.course_id = course.id
    service = EnrollmentService(
        FakeEnrollmentRepo(FakeSession(), enrollment),  # type: ignore[arg-type]
        CourseRepo(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
    )
    service.evaluate_dynamic = AsyncMock(
        return_value=SimpleNamespace(progress_percent=100)
    )

    assert await service.compute_progress(enrollment=enrollment, org_id=ORG_ID) == 1.0
    service.evaluate_dynamic.assert_awaited_once_with(
        course_id=course.id, user_id=USER_ID
    )


# --------------------------------------------------------------------------- #
# mastery -> skill_level (§3.3)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("mastery", "expected"),
    [
        (0.0, SkillLevel.LOW),
        (0.49, SkillLevel.LOW),
        (0.5, SkillLevel.MEDIUM),
        (0.84, SkillLevel.MEDIUM),
        (0.85, SkillLevel.HIGH),
        (1.0, SkillLevel.HIGH),
    ],
)
def test_the_mastery_to_skill_level_boundaries(mastery: float, expected) -> None:
    assert mastery_to_level(mastery) is expected


@pytest.mark.asyncio
async def test_record_mastery_grants_a_skill_the_user_did_not_have() -> None:
    session = FakeSession(value=None)
    service = SkillService(_repo(session))

    level = await service.record_mastery(
        user_id=USER_ID, skill_id=SKILL_ID, mastery=0.92
    )

    assert level is SkillLevel.HIGH
    assert len(session.added) == 1
    granted = session.added[0]
    assert isinstance(granted, UserSkill)
    assert granted.level is SkillLevel.HIGH
    assert granted.source == "node_mastery"


@pytest.mark.asyncio
async def test_record_mastery_never_downgrades_a_verified_skill() -> None:
    """The rule that makes ``user_skills`` trustworthy: one bad node cannot retract
    a level a peer or a supervisor verified."""
    verified = UserSkill(
        user_id=USER_ID, skill_id=SKILL_ID, level=SkillLevel.HIGH, source="peer_review"
    )
    session = FakeSession(value=verified)
    service = SkillService(_repo(session))

    assert await service.record_mastery(
        user_id=USER_ID, skill_id=SKILL_ID, mastery=0.30
    ) is None
    assert verified.level is SkillLevel.HIGH
    assert verified.source == "peer_review"
    assert session.flushes == 0


@pytest.mark.asyncio
async def test_record_mastery_raises_an_existing_level() -> None:
    existing = UserSkill(
        user_id=USER_ID, skill_id=SKILL_ID, level=SkillLevel.LOW, source="checkpoint"
    )
    session = FakeSession(value=existing)
    service = SkillService(_repo(session))

    assert await service.record_mastery(
        user_id=USER_ID, skill_id=SKILL_ID, mastery=0.88
    ) is SkillLevel.HIGH
    assert existing.level is SkillLevel.HIGH
    assert existing.source == "node_mastery"


@pytest.mark.asyncio
async def test_a_node_without_a_skill_writes_nothing() -> None:
    """``course_nodes.skill_id`` is nullable, so ``None`` in must mean ``None`` out —
    the caller should not need a guard."""
    session = FakeSession(value=None)
    service = SkillService(_repo(session))

    assert await service.record_mastery(
        user_id=USER_ID, skill_id=None, mastery=1.0
    ) is None
    assert session.added == []


@pytest.mark.asyncio
async def test_the_probe_prior_comes_from_user_skills() -> None:
    """§7.1: ``{"high": 0.85, "medium": 0.55, "low": 0.25}``, and 0.0 for nothing."""
    assert await SkillService(_repo(FakeSession(SkillLevel.HIGH))).mastery_prior_for(
        user_id=USER_ID, skill_id=SKILL_ID
    ) == pytest.approx(0.85)
    assert await SkillService(_repo(FakeSession(SkillLevel.MEDIUM))).mastery_prior_for(
        user_id=USER_ID, skill_id=SKILL_ID
    ) == pytest.approx(0.55)
    assert await SkillService(_repo(FakeSession(SkillLevel.LOW))).mastery_prior_for(
        user_id=USER_ID, skill_id=SKILL_ID
    ) == pytest.approx(0.25)
    assert await SkillService(_repo(FakeSession(None))).mastery_prior_for(
        user_id=USER_ID, skill_id=SKILL_ID
    ) == pytest.approx(0.0)
    # No skill on the node: no query, no prior.
    assert await SkillService(_repo(FakeSession(SkillLevel.HIGH))).mastery_prior_for(
        user_id=USER_ID, skill_id=None
    ) == pytest.approx(0.0)


class _Repo:
    def __init__(self, session: Any) -> None:
        self.session = session


def _repo(session: Any) -> Any:
    return _Repo(session)
