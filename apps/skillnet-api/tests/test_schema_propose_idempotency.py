"""``POST /courses/{id}/schema/propose`` is idempotent while a job is in flight (§11.1).

No DB, no network: the fakes of ``test_schema_gate`` plus a job repository that
answers ``find_in_flight_schema_job`` the way the real query would.

Why this file exists: ``propose`` had no guard at all. Two clicks bought two full
schema-designer runs over the same course, and the two runners wrote the same node
set, so which schema survived depended on which run finished last. That is a billing
hole and a lost-update race in one call.

The read tested here is only half the fix. The other half is the partial unique index
``uq_generation_jobs_schema_in_flight`` in ``0005_dynamic_courses.py``, which is what
holds when two requests both read "nothing running" before either inserts; it cannot
be exercised without Postgres (§12.2), so it is asserted in
``tests/integration/test_migration_0005.py`` territory rather than here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.models import CourseSchemaStatus, GenerationOutput, GenerationStep
from src.repositories.generation_job_repo import SCHEMA_JOB_IN_FLIGHT
from src.services import course_schema_service as service_module
from src.services.course_schema_service import SchemaLocked

from tests.test_schema_gate import ACTOR_ID, DOC_ID, ORG_ID, make_course, make_service


class FakeJob:
    """The columns ``propose`` and the guard touch."""

    def __init__(self, **kwargs) -> None:
        self.id = uuid.uuid4()
        self.created_at = kwargs.pop("created_at", datetime.now(timezone.utc))
        self.cancelled_at = None
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeJobRepo:
    """In-memory stand-in that filters exactly like ``find_in_flight_schema_job``.

    The status set comes from the repository on purpose: the fake mirrors the *shape*
    of the real query, and the *contents* of ``SCHEMA_JOB_IN_FLIGHT`` are what the
    tests below assert (a ``pending`` v1 content job must not be reused).
    """

    IN_FLIGHT = SCHEMA_JOB_IN_FLIGHT

    def __init__(self) -> None:
        self.jobs: list[FakeJob] = []
        self.creates = 0

    async def create(self, **kwargs) -> FakeJob:
        self.creates += 1
        job = FakeJob(
            **kwargs,
            created_at=datetime.now(timezone.utc) + timedelta(seconds=self.creates),
        )
        self.jobs.append(job)
        return job

    async def find_in_flight_schema_job(self, course_id, org_id) -> FakeJob | None:
        candidates = [
            job
            for job in self.jobs
            if job.result_course_id == course_id
            and job.org_id == org_id
            and job.status in self.IN_FLIGHT
            and job.cancelled_at is None
        ]
        candidates.sort(key=lambda job: job.created_at)
        return candidates[0] if candidates else None


class FakeRegistry:
    """Records spawns instead of running them; closes the coroutine it is handed."""

    def __init__(self) -> None:
        self.spawned: list[str] = []

    def spawn(self, coro, name: str) -> None:
        coro.close()
        self.spawned.append(name)


@pytest.fixture
def registry(monkeypatch) -> FakeRegistry:
    fake = FakeRegistry()
    monkeypatch.setattr(service_module, "task_registry", fake)
    return fake


def _service(course, job_repo):
    service, *_ = make_service(course, [], job_repo=job_repo)
    return service


async def _propose(service, course, *, intent_density: int = 3):
    return await service.propose(
        course_id=course.id,
        org_id=ORG_ID,
        triggered_by=ACTOR_ID,
        source_document_id=DOC_ID,
        intent_density=intent_density,
    )


async def test_two_proposes_in_a_row_share_one_job_and_one_designer_run(registry):
    """The headline: the second POST is still 202, with the same job_id."""
    course = make_course(status=CourseSchemaStatus.DRAFT)
    job_repo = FakeJobRepo()
    service = _service(course, job_repo)

    first = await _propose(service, course)
    second = await _propose(service, course)

    assert second.id == first.id
    assert job_repo.creates == 1
    assert registry.spawned == [f"schema:{first.id}"]


async def test_ten_rapid_proposes_still_buy_exactly_one_run(registry):
    course = make_course(status=CourseSchemaStatus.DRAFT)
    job_repo = FakeJobRepo()
    service = _service(course, job_repo)

    jobs = [await _propose(service, course) for _ in range(10)]

    assert len({job.id for job in jobs}) == 1
    assert job_repo.creates == 1
    assert len(registry.spawned) == 1


async def test_the_reused_job_does_not_silently_change_intent_density(registry):
    """The running job already read the density; moving it would only lie."""
    course = make_course(status=CourseSchemaStatus.DRAFT)
    service = _service(course, FakeJobRepo())

    await _propose(service, course, intent_density=3)
    await _propose(service, course, intent_density=5)

    assert course.intent_density == 3


@pytest.mark.parametrize(
    "terminal",
    [GenerationStep.SCHEMA_PROPOSED, GenerationStep.FAILED, GenerationStep.PUBLISHED],
)
async def test_a_finished_job_never_blocks_the_next_proposal(registry, terminal):
    course = make_course(status=CourseSchemaStatus.DRAFT)
    job_repo = FakeJobRepo()
    service = _service(course, job_repo)

    first = await _propose(service, course)
    first.status = terminal

    second = await _propose(service, course)

    assert second.id != first.id
    assert job_repo.creates == 2
    assert len(registry.spawned) == 2


async def test_a_cancelled_job_never_blocks_the_next_proposal(registry):
    course = make_course(status=CourseSchemaStatus.DRAFT)
    job_repo = FakeJobRepo()
    service = _service(course, job_repo)

    first = await _propose(service, course)
    first.cancelled_at = datetime.now(timezone.utc)

    second = await _propose(service, course)

    assert second.id != first.id
    assert job_repo.creates == 2


async def test_a_job_of_another_course_is_not_reused(registry):
    """The guard is per course, not per organization."""
    course = make_course(status=CourseSchemaStatus.DRAFT)
    other = make_course(status=CourseSchemaStatus.DRAFT)
    job_repo = FakeJobRepo()

    first = await _propose(_service(course, job_repo), course)
    second = await _propose(_service(other, job_repo), other)

    assert second.id != first.id
    assert job_repo.creates == 2


async def test_the_created_job_is_the_shape_the_guard_can_find(registry):
    """Guards the pair: the row ``create`` writes must match what the query filters."""
    course = make_course(status=CourseSchemaStatus.DRAFT)
    job_repo = FakeJobRepo()

    job = await _propose(_service(course, job_repo), course)

    assert job.status == GenerationStep.SCHEMA_PROPOSING
    assert job.result_course_id == course.id
    assert job.org_id == ORG_ID
    assert job.cancelled_at is None
    assert job.output_type == GenerationOutput.COURSE_AND_MANUAL


async def test_a_v1_content_job_of_the_same_course_is_not_mistaken_for_a_schema_job(
    registry,
):
    """``generation_service`` inserts its job as ``pending`` with the same course id.

    If ``pending`` counted as "a schema job in flight", asking for a schema while
    content generation was running would hand back the content job's id and never
    propose anything.
    """
    course = make_course(status=CourseSchemaStatus.DRAFT)
    job_repo = FakeJobRepo()
    content_job = await job_repo.create(
        org_id=ORG_ID,
        triggered_by=ACTOR_ID,
        source_document_id=DOC_ID,
        output_type=GenerationOutput.COURSE_AND_MANUAL,
        status=GenerationStep.PENDING,
        result_course_id=course.id,
        progress={},
    )

    job = await _propose(_service(course, job_repo), course)

    assert job.id != content_job.id
    assert job.status == GenerationStep.SCHEMA_PROPOSING
    assert GenerationStep.PENDING not in SCHEMA_JOB_IN_FLIGHT


async def test_the_gate_still_wins_over_the_dedup_guard(registry):
    """A validated schema is refused before any job is looked at (§11.1)."""
    course = make_course(status=CourseSchemaStatus.VALIDATED)
    job_repo = FakeJobRepo()

    with pytest.raises(SchemaLocked):
        await _propose(_service(course, job_repo), course)

    assert job_repo.creates == 0
    assert registry.spawned == []
