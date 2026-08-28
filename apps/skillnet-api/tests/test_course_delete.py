"""Delete rules for a course, the audit row it leaves, and the file cleanup.

The incident behind this file: a generation run left a course in DRAFT, the admin retried,
and the abandoned draft could not be removed — the route existed but nothing called it, and
calling it 500'd because ``generation_jobs.result_course_id`` had no ``ON DELETE``. The
schema half of that fix is migration 0024; the file cleanup is here.

The *rules* have since changed. Deleting used to be refused for anything that was not an
empty draft, which is why this file was mostly a list of refusals. It is not a refusal
list any more: an admin may delete a course in any status and with people enrolled in it,
``enrollments.course_id`` cascades (migration 0032), and the safeguard is the
``course_deleted`` row in ``audit_log`` — asserted here, because it is the only thing left
once the course is gone.
"""

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import ConflictError, NotFoundError
from src.models import AUDIT_ACTIONS, ChatSession, ContentStatus, Enrollment, GenerationJob
from src.services import course_service as course_service_module
from src.services.course_service import CourseService


def _course(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        title="Cómo aprende tu cerebro",
        status=ContentStatus.DRAFT,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _repo(course, *, enrollments: tuple[int, int] = (0, 0), **overrides):
    defaults = dict(
        session=object(),
        get_scoped=AsyncMock(return_value=course),
        count_enrollments=AsyncMock(return_value=enrollments),
        delete=AsyncMock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _media(monkeypatch, *, paths: list[str], still_referenced: set[str] | None = None):
    """Stand in for the ``MediaArtifactRepository`` the service builds from the session."""
    fake = SimpleNamespace(
        list_asset_paths_for_course=AsyncMock(return_value=paths),
        paths_still_referenced=AsyncMock(return_value=still_referenced or set()),
    )
    monkeypatch.setattr(
        course_service_module, "MediaArtifactRepository", lambda session: fake
    )
    return fake


def _audit(monkeypatch):
    """Stand in for the ``AuditLogRepository`` the service builds from the session."""
    fake = SimpleNamespace(record=AsyncMock())
    monkeypatch.setattr(
        course_service_module, "AuditLogRepository", lambda session: fake
    )
    return fake


def _integrity_error() -> IntegrityError:
    return IntegrityError("DELETE FROM courses", {}, Exception("FK violation"))


@pytest.mark.asyncio
async def test_delete_removes_a_draft_with_no_enrollments(monkeypatch) -> None:
    course = _course()
    repo = _repo(course)
    _media(monkeypatch, paths=[])
    _audit(monkeypatch)

    await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    repo.delete.assert_awaited_once_with(course)


@pytest.mark.asyncio
async def test_delete_removes_a_published_course(monkeypatch) -> None:
    """The status check is gone: an admin deletes their own content in any state."""
    course = _course(status=ContentStatus.PUBLISHED)
    repo = _repo(course)
    _media(monkeypatch, paths=[])
    _audit(monkeypatch)

    await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    repo.delete.assert_awaited_once_with(course)


@pytest.mark.asyncio
async def test_delete_removes_an_archived_course_with_enrollments(monkeypatch) -> None:
    """Enrollments no longer block either — they cascade (migration 0032)."""
    course = _course(status=ContentStatus.ARCHIVED)
    repo = _repo(course, enrollments=(34, 12))
    _media(monkeypatch, paths=[])
    _audit(monkeypatch)

    await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    repo.delete.assert_awaited_once_with(course)


@pytest.mark.asyncio
async def test_delete_records_who_removed_what_and_how_much(monkeypatch) -> None:
    """The audit row is the whole safeguard, so it carries the numbers, not a flag."""
    course = _course(title="Seguridad alimentaria", status=ContentStatus.PUBLISHED)
    repo = _repo(course, enrollments=(34, 12))
    _media(monkeypatch, paths=[])
    audit = _audit(monkeypatch)
    org_id, actor_id = uuid.uuid4(), uuid.uuid4()

    await CourseService(repo).delete(
        course_id=course.id, org_id=org_id, actor_id=actor_id
    )

    call = audit.record.await_args.kwargs
    assert call["action"] == "course_deleted"
    assert call["org_id"] == org_id
    assert call["actor_id"] == actor_id
    assert call["subject"] == f"course:{course.id}"
    assert call["detail"] == {
        "title": "Seguridad alimentaria",
        "status": "published",
        "enrollment_count": 34,
        "completed_enrollment_count": 12,
    }


def test_course_deleted_is_a_known_audit_action() -> None:
    """``AuditLogRepository.record`` rejects anything outside this closed tuple."""
    assert "course_deleted" in AUDIT_ACTIONS


@pytest.mark.asyncio
async def test_delete_of_an_unknown_course_is_a_404_not_a_silent_success(
    monkeypatch,
) -> None:
    repo = _repo(None, get_scoped=AsyncMock(return_value=None))
    _media(monkeypatch, paths=[])
    _audit(monkeypatch)

    with pytest.raises(NotFoundError):
        await CourseService(repo).delete(course_id=uuid.uuid4(), org_id=uuid.uuid4())

    repo.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_foreign_key_violation_becomes_a_conflict_not_a_500(
    monkeypatch,
) -> None:
    course = _course()
    repo = _repo(course, delete=AsyncMock(side_effect=_integrity_error()))
    _media(monkeypatch, paths=[])
    audit = _audit(monkeypatch)

    with pytest.raises(ConflictError) as excinfo:
        await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    assert excinfo.value.status_code == 409
    # Nothing was destroyed, so there is nothing to account for.
    audit.record.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_unlinks_the_media_assets_of_the_course(
    monkeypatch, tmp_path: Path
) -> None:
    asset = tmp_path / "9f86d081.mp3"
    asset.write_bytes(b"podcast")
    course = _course()
    repo = _repo(course)
    _media(monkeypatch, paths=[str(asset)])
    _audit(monkeypatch)

    await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    assert not asset.exists()


@pytest.mark.asyncio
async def test_a_missing_asset_file_does_not_fail_the_delete(
    monkeypatch, tmp_path: Path
) -> None:
    missing = tmp_path / "gone.mp3"
    course = _course()
    repo = _repo(course)
    _media(monkeypatch, paths=[str(missing)])
    _audit(monkeypatch)

    await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    repo.delete.assert_awaited_once_with(course)


@pytest.mark.asyncio
async def test_an_asset_another_artifact_still_points_at_is_kept(
    monkeypatch, tmp_path: Path
) -> None:
    """The store dedups by content hash, so one file can serve several artifacts."""
    shared = tmp_path / "shared.png"
    shared.write_bytes(b"infographic")
    mine = tmp_path / "mine.png"
    mine.write_bytes(b"cover")
    course = _course()
    repo = _repo(course)
    _media(
        monkeypatch,
        paths=[str(shared), str(mine)],
        still_referenced={str(shared)},
    )
    _audit(monkeypatch)

    await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    assert shared.exists()
    assert not mine.exists()


@pytest.mark.parametrize(
    ("model", "column"),
    [(GenerationJob, "result_course_id"), (ChatSession, "course_id")],
)
def test_the_bookkeeping_references_to_a_course_are_set_null(model, column) -> None:
    """The schema half of the fix, asserted without a database.

    Both columns are nullable and both foreign keys clear themselves when the course
    goes; without that, deleting any generated course raises ``ForeignKeyViolation``.
    """
    col = model.__table__.c[column]
    fks = [fk for fk in col.foreign_keys if fk.column.table.name == "courses"]

    assert col.nullable is True
    assert [fk.ondelete for fk in fks] == ["SET NULL"]


def test_enrollments_cascade_with_their_course() -> None:
    """Migration 0032, asserted without a database.

    ``enrollments.course_id`` was the one restrictive reference left, and it is what
    made "delete a course somebody is enrolled in" a ``ForeignKeyViolation`` rather than
    a delete. It is not nullable and never could be — an enrollment names a course by
    definition — so ``CASCADE`` is the only ``ON DELETE`` that is not a lie.
    """
    col = Enrollment.__table__.c["course_id"]
    fks = [fk for fk in col.foreign_keys if fk.column.table.name == "courses"]

    assert col.nullable is False
    assert [fk.ondelete for fk in fks] == ["CASCADE"]
