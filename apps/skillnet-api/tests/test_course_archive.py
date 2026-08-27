"""What archiving a course means: `CourseService.archive`/`unarchive`, and for whom.

Archiving is one sentence — "stop showing this course to the learners" — and until this
session the code said none of it:

* the learner's list never looked at `Course.status`, so an archived course kept
  appearing in "My Courses";
* what archiving did instead was close every open enrollment as `COMPLETED` with a
  `completed_at` of "now", handing a half-finished learner a finished record;
* and `unarchive` returned the course as a `draft`, leaving the course invisible until
  somebody published it again — while those falsely-completed rows stayed.

Now: `published` is the only archivable status (so `published` is also the status
`unarchive` restores, with no need to remember it), enrollments are never touched, and
the learner's list — and only the learner's list — filters archived courses out.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.models import ContentStatus, EnrollmentStatus, UserRole
from src.routes import enrollments as enrollment_routes
from src.services.course_service import CourseService


def _enrollment(status: EnrollmentStatus) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), status=status, completed_at=None, score=None
    )


def _course(
    status: ContentStatus, *, enrollments: list[SimpleNamespace] | None = None
) -> SimpleNamespace:
    """A v1 (static) course that would pass the publish checks."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Atencion en taquilla",
        outcome="Resolver una incidencia de acceso",
        status=status,
        delivery_mode="static",
        schema_status=None,
        modules=[SimpleNamespace(lessons=[SimpleNamespace(id=uuid.uuid4())])],
        enrollments=enrollments if enrollments is not None else [],
    )


def _repo(course: SimpleNamespace | None) -> SimpleNamespace:
    """The two reads `archive`/`unarchive` make, plus the one write.

    `get_detail` answers with the same object as `get_scoped`, which is what SQLAlchemy's
    identity map does in the real thing: `unarchive` reads the course, then delegates to
    `publish`, which reads it again.
    """
    return SimpleNamespace(
        get_scoped=AsyncMock(return_value=course),
        get_detail=AsyncMock(return_value=course),
        count_active_nodes=AsyncMock(return_value=0),
        update=AsyncMock(side_effect=lambda obj, **kwargs: obj),
    )


# --------------------------------------------------------------------------------------
# archive
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_archive_hides_a_published_course() -> None:
    course = _course(ContentStatus.PUBLISHED)
    repo = _repo(course)

    archived = await CourseService(repo).archive(course_id=course.id, org_id=uuid.uuid4())

    assert archived is course
    repo.update.assert_awaited_once_with(course, status=ContentStatus.ARCHIVED)


@pytest.mark.asyncio
async def test_archive_leaves_every_enrollment_exactly_as_it_was() -> None:
    """The regression that mattered: archiving used to grade people.

    It closed every open row as `COMPLETED` and stamped `completed_at`, so a learner
    half-way through the course ended up with a completed record — and the credit that
    goes with it — for a course they never finished. Nothing here may write to an
    enrollment: hiding a course is not an assessment of anybody.
    """
    rows = [
        _enrollment(EnrollmentStatus.ASSIGNED),
        _enrollment(EnrollmentStatus.IN_PROGRESS),
        _enrollment(EnrollmentStatus.COMPLETED),
    ]
    course = _course(ContentStatus.PUBLISHED, enrollments=rows)

    await CourseService(_repo(course)).archive(course_id=course.id, org_id=uuid.uuid4())

    assert [row.status for row in rows] == [
        EnrollmentStatus.ASSIGNED,
        EnrollmentStatus.IN_PROGRESS,
        EnrollmentStatus.COMPLETED,
    ]
    assert [row.completed_at for row in rows] == [None, None, None]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [ContentStatus.DRAFT, ContentStatus.ARCHIVED])
async def test_archive_refuses_anything_that_is_not_published(
    status: ContentStatus,
) -> None:
    """409, and no write.

    A draft is already invisible to learners, so archiving one hides nothing; allowing it
    is what made the way back a guess. The admin UI only ever offered the button for a
    published course — this is the same rule in the API.
    """
    course = _course(status)
    repo = _repo(course)

    with pytest.raises(ConflictError) as raised:
        await CourseService(repo).archive(course_id=course.id, org_id=uuid.uuid4())

    assert raised.value.status_code == 409
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_archive_is_scoped_to_the_organization() -> None:
    repo = _repo(None)

    with pytest.raises(NotFoundError):
        await CourseService(repo).archive(course_id=uuid.uuid4(), org_id=uuid.uuid4())
    repo.update.assert_not_awaited()


# --------------------------------------------------------------------------------------
# unarchive
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unarchive_returns_an_archived_course_to_published() -> None:
    course = _course(ContentStatus.ARCHIVED)
    repo = _repo(course)

    restored = await CourseService(repo).unarchive(
        course_id=course.id, org_id=uuid.uuid4()
    )

    assert restored is course
    # `published`, not `draft`: only a published course can be archived, so there is
    # nothing to guess — and the learners get their course back without a second publish.
    repo.update.assert_awaited_once_with(course, status=ContentStatus.PUBLISHED)


@pytest.mark.asyncio
async def test_unarchive_re_runs_the_publish_checks() -> None:
    """An archived course is not frozen: it can have lost its content meanwhile.

    Unarchiving publishes, so it answers the question publishing answers — is there
    anything to deliver? A course with no lesson left comes back as 422, not as a
    published course that opens onto nothing.
    """
    course = _course(ContentStatus.ARCHIVED)
    course.modules = []
    repo = _repo(course)

    with pytest.raises(ValidationError) as raised:
        await CourseService(repo).unarchive(course_id=course.id, org_id=uuid.uuid4())

    assert raised.value.status_code == 422
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [ContentStatus.DRAFT, ContentStatus.PUBLISHED])
async def test_unarchive_refuses_a_course_that_is_not_archived(
    status: ContentStatus,
) -> None:
    """409, and no write: "undo the archive" is meaningless when there was none."""
    course = _course(status)
    repo = _repo(course)

    with pytest.raises(ConflictError) as raised:
        await CourseService(repo).unarchive(course_id=course.id, org_id=uuid.uuid4())

    assert raised.value.status_code == 409
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_unarchive_is_scoped_to_the_organization() -> None:
    """A course of another org is a 404, not a 409 — the org must not learn it exists."""
    repo = _repo(None)

    with pytest.raises(NotFoundError):
        await CourseService(repo).unarchive(
            course_id=uuid.uuid4(), org_id=uuid.uuid4()
        )
    repo.update.assert_not_awaited()


# --------------------------------------------------------------------------------------
# Who stops seeing the course
# --------------------------------------------------------------------------------------
class _RecordingService:
    """Captures the kwargs `GET /enrollments` hands to the service."""

    def __init__(self) -> None:
        self.kwargs: dict = {}

    async def list_enrollments(self, **kwargs):  # noqa: ANN003, ANN201
        self.kwargs = kwargs
        return [], 0

    async def compute_progress(self, **_kwargs):  # noqa: ANN003, ANN201
        return None


async def _call_list(role: UserRole, service: _RecordingService, monkeypatch) -> None:
    monkeypatch.setattr(enrollment_routes, "_service", lambda _db: service)
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), role=role)
    await enrollment_routes.list_enrollments(user=user, db=None)


@pytest.mark.asyncio
async def test_a_learners_list_leaves_archived_courses_out(monkeypatch) -> None:
    """"My Courses" is the surface archiving exists for."""
    service = _RecordingService()
    await _call_list(UserRole.EMPLOYEE, service, monkeypatch)

    assert service.kwargs["include_archived_courses"] is False


@pytest.mark.asyncio
async def test_an_admin_reading_someones_record_still_sees_them(monkeypatch) -> None:
    """The employee drawer is history, not a catalogue.

    "You were enrolled in this course, and it is archived now" is something the admin
    has to be able to read; hiding it would make the record look emptier than the
    database is, and would hide the progress that archiving no longer destroys.
    """
    service = _RecordingService()
    await _call_list(UserRole.ADMIN, service, monkeypatch)

    assert service.kwargs["include_archived_courses"] is True
