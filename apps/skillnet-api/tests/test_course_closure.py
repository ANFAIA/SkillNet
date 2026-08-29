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
from src.services.mastery_service import CourseCompletion, evaluate_course_completion
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
    started_at: datetime | None = None


def row(
    *,
    criticality: NodeCriticality = NodeCriticality.CRITICAL,
    state: str = "mastered",
    mastery: float = 0.9,
    archived: bool = False,
    attempts_count: int = 0,
    probe_score: float | None = None,
) -> NodeProgressRow:
    """A ``(node, learner state)`` row. Unmeasured unless a test says otherwise.

    The default is deliberately the awkward case rather than the convenient one: a node
    that closed without asking anything is what these tests are mostly about, and a
    builder that quietly supplied evidence would hide it.
    """
    return NodeProgressRow(
        node_id=uuid.uuid4(),
        criticality=criticality,
        archived=archived,
        state=state,
        mastery=mastery,
        attempts_count=attempts_count,
        probe_score=probe_score,
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
    # And no mark. Closing a dynamic course records that it was closed; the mean mastery
    # it used to write here could not tell a node nobody was asked about from one
    # answered wrong, so it is gone rather than improved.
    assert enrollment.score is None


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

    # Once every node is mastered the course completes — and still writes no score.
    done = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    all_mastered = evaluate_course_completion(
        [
            row(mastery=0.9, attempts_count=3),
            row(criticality=NodeCriticality.RECOMMENDED, mastery=0.8, attempts_count=3),
            row(criticality=NodeCriticality.CONTEXTUAL, mastery=0.7, attempts_count=3),
        ]
    )
    assert apply_dynamic_closure(done, all_mastered) == "completed"
    assert done.score is None
    # The evidence is still computed, it just never becomes a mark on the enrollment:
    # its one job is choosing the level the course's skills are accredited at.
    assert all_mastered.measured_mastery == pytest.approx((0.9 + 0.8 + 0.7) / 3)


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


def test_an_unfinished_critical_node_keeps_the_enrollment_active() -> None:
    """§7.4: while a critical node is still being learnt the course stays ``active``."""
    enrollment = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    completion = evaluate_course_completion(
        [row(mastery=0.9), row(state="learning", mastery=0.4)]
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


# --------------------------------------------------------------------------- #
# assigned -> in_progress on the dynamic branch
#
# The transition the v2 path simply did not have. `apply_dynamic_closure` only ever writes
# `completed` or reopens a `completed` row, so a learner could work through 57% of a course
# and their enrollment still said `assigned`: "Pendiente" on the dashboard, and 0 under
# "Cursos activos". v1 has always stamped it on the first lesson visit.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_first_interaction_starts_a_dynamic_enrollment() -> None:
    course = make_course()
    enrollment = FakeEnrollment(status=EnrollmentStatus.ASSIGNED)
    service = make_service(FakeSession(), enrollment)

    started = await service.mark_dynamic_started(course=course, user_id=USER_ID)

    assert started is enrollment
    assert enrollment.status == EnrollmentStatus.IN_PROGRESS
    assert enrollment.started_at is not None


@pytest.mark.asyncio
async def test_a_second_visit_does_not_move_started_at() -> None:
    """Idempotence: this runs on every served render, so it must be a no-op after the
    first one. Rewriting ``started_at`` per visit would make "when did they begin" mean
    "when were they last here"."""
    course = make_course()
    first = datetime(2026, 3, 1, tzinfo=timezone.utc)
    enrollment = FakeEnrollment(
        status=EnrollmentStatus.IN_PROGRESS, started_at=first
    )
    service = make_service(FakeSession(), enrollment)

    assert await service.mark_dynamic_started(course=course, user_id=USER_ID) is None
    assert enrollment.started_at == first
    assert enrollment.status == EnrollmentStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_a_completed_enrollment_is_not_reopened_by_a_revisit() -> None:
    """Re-reading a finished course is not starting it: only `assigned` moves."""
    course = make_course()
    enrollment = FakeEnrollment(
        status=EnrollmentStatus.COMPLETED,
        completed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        score=0.9,
    )
    service = make_service(FakeSession(), enrollment)

    assert await service.mark_dynamic_started(course=course, user_id=USER_ID) is None
    assert enrollment.status == EnrollmentStatus.COMPLETED
    assert enrollment.completed_at == datetime(2026, 4, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_a_static_course_is_never_started_by_the_v2_path() -> None:
    """v1 stamps this itself in ``routes/lessons.py``; two authorities would be the bug."""
    course = make_course(mode=CourseDeliveryMode.STATIC)
    enrollment = FakeEnrollment(status=EnrollmentStatus.ASSIGNED)
    service = make_service(FakeSession(), enrollment)

    assert await service.mark_dynamic_started(course=course, user_id=USER_ID) is None
    assert enrollment.status == EnrollmentStatus.ASSIGNED
    assert service.enrollment_repo.lookups == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_an_unenrolled_viewer_starts_nothing() -> None:
    """An admin previewing a node is exempt from the enrollment check, so there may be
    no row at all. That is not an error and it must not raise."""
    course = make_course()
    service = make_service(FakeSession(), None)

    assert await service.mark_dynamic_started(course=course, user_id=USER_ID) is None


def test_reopening_backfills_a_missing_started_at() -> None:
    """A reopened enrollment is ``in_progress``, and an ``in_progress`` row with no
    ``started_at`` is exactly the "Pendiente at 57%" shape this batch removes."""
    enrollment = FakeEnrollment(
        status=EnrollmentStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
        score=1.0,
    )
    completion = evaluate_course_completion(
        [row(mastery=1.0), row(state="not_started", mastery=0.0)]
    )

    assert apply_dynamic_closure(enrollment, completion) == "reopened"
    assert enrollment.status == EnrollmentStatus.IN_PROGRESS
    assert enrollment.started_at is not None


def test_reopening_does_not_move_a_real_started_at() -> None:
    kept = datetime(2026, 1, 15, tzinfo=timezone.utc)
    enrollment = FakeEnrollment(
        status=EnrollmentStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
        score=1.0,
        started_at=kept,
    )
    completion = evaluate_course_completion(
        [row(mastery=1.0), row(state="not_started", mastery=0.0)]
    )

    assert apply_dynamic_closure(enrollment, completion) == "reopened"
    assert enrollment.started_at == kept


# --------------------------------------------------------------------------- #
# What a completion accredits, now that it carries no mark
# --------------------------------------------------------------------------- #
def completion(measured: float | None, measured_nodes: int = 2) -> CourseCompletion:
    """A closable verdict, varying only in whether the course measured anything."""
    return CourseCompletion(
        can_complete=True,
        blocked_by=(),
        measured_mastery=measured,
        measured_nodes=0 if measured is None else measured_nodes,
        mastered_critical=2,
        total_critical=2,
        progress_percent=100,
    )


@pytest.mark.asyncio
async def test_a_course_that_measured_nothing_accredits_nothing() -> None:
    """The tail of dropping the score, and the reason it is not just a deletion.

    The level used to come from the mean mastery over every node, so a course whose nodes
    ask nothing averaged to 0.0 and handed `low` to everyone who finished it — a claim
    about a person, in the table that answers "who knows X", from evidence that does not
    exist. `None` is not a low measurement, so nothing is written at all: the completed
    enrollment already records the true fact, which is that they went through it.
    """
    course = make_course()
    enrollment = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    service = make_service(FakeSession(), enrollment)
    service.evaluate_dynamic = AsyncMock(return_value=completion(None))
    service._assign_course_skills = AsyncMock()

    _row, verdict = await service.close_dynamic_if_mastered(
        course=course, user_id=USER_ID
    )

    assert enrollment.status == EnrollmentStatus.COMPLETED
    assert enrollment.score is None
    assert verdict is not None and verdict.measured_mastery is None
    service._assign_course_skills.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_course_that_measured_accredits_at_the_measured_level() -> None:
    """And the other half: real evidence still grants, at the level it supports.

    Nothing about this path changed except which nodes the mean is over — the silences
    are no longer averaged in, so a learner who answered well is no longer dragged down
    to `medium` by the expository nodes sitting next to the graded ones.
    """
    course = make_course()
    enrollment = FakeEnrollment(status=EnrollmentStatus.IN_PROGRESS)
    service = make_service(FakeSession(), enrollment)
    service.evaluate_dynamic = AsyncMock(return_value=completion(0.92))
    service._assign_course_skills = AsyncMock()

    await service.close_dynamic_if_mastered(course=course, user_id=USER_ID)

    service._assign_course_skills.assert_awaited_once_with(
        USER_ID, course.id, SkillLevel.HIGH
    )


@pytest.mark.asyncio
async def test_reopening_accredits_nothing_even_when_the_course_measured() -> None:
    """A skill is granted by closing, and reopening is the opposite of closing.

    Worth pinning because the never-downgrade rule would make a stray grant here
    invisible until somebody wondered why an unfinished course had already accredited.
    """
    course = make_course()
    enrollment = FakeEnrollment(
        status=EnrollmentStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    service = make_service(FakeSession(), enrollment)
    service.evaluate_dynamic = AsyncMock(
        return_value=CourseCompletion(
            can_complete=False,
            blocked_by=("n2",),
            measured_mastery=0.95,
            measured_nodes=1,
            mastered_critical=1,
            total_critical=2,
            progress_percent=50,
        )
    )
    service._assign_course_skills = AsyncMock()

    await service.close_dynamic_if_mastered(course=course, user_id=USER_ID)

    assert enrollment.status == REOPENED_STATUS
    service._assign_course_skills.assert_not_awaited()
