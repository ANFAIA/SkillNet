"""Delete rules for a course, and the cleanup that follows a successful one.

The incident behind this file: a generation run left a course in DRAFT, the admin retried,
and the abandoned draft could not be removed — the route existed but nothing called it, and
calling it 500'd because ``generation_jobs.result_course_id`` had no ``ON DELETE``. The
schema half of the fix is migration 0024; the rules and the file cleanup are here.
"""

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import ConflictError
from src.models import ChatSession, ContentStatus, GenerationJob
from src.services import course_service as course_service_module
from src.services.course_service import CourseService


def _course(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        title="Cómo aprende tu cerebro",
        status=ContentStatus.DRAFT,
        enrollments=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _repo(course, **overrides):
    defaults = dict(
        session=object(),
        get_with_enrollments=AsyncMock(return_value=course),
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


def _integrity_error() -> IntegrityError:
    return IntegrityError("DELETE FROM courses", {}, Exception("FK violation"))


@pytest.mark.asyncio
async def test_delete_removes_a_draft_with_no_enrollments(monkeypatch) -> None:
    course = _course()
    repo = _repo(course)
    _media(monkeypatch, paths=[])

    await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    repo.delete.assert_awaited_once_with(course)


@pytest.mark.asyncio
async def test_delete_refuses_a_published_course(monkeypatch) -> None:
    course = _course(status=ContentStatus.PUBLISHED)
    repo = _repo(course)
    _media(monkeypatch, paths=[])

    with pytest.raises(ConflictError) as excinfo:
        await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    assert "draft" in str(excinfo.value).lower()
    repo.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_refuses_a_course_with_enrollments(monkeypatch) -> None:
    course = _course(enrollments=[SimpleNamespace(id=uuid.uuid4())])
    repo = _repo(course)
    _media(monkeypatch, paths=[])

    with pytest.raises(ConflictError) as excinfo:
        await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    assert "enrollments" in str(excinfo.value).lower()
    repo.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_foreign_key_violation_becomes_a_conflict_not_a_500(
    monkeypatch,
) -> None:
    course = _course()
    repo = _repo(course, delete=AsyncMock(side_effect=_integrity_error()))
    _media(monkeypatch, paths=[])

    with pytest.raises(ConflictError) as excinfo:
        await CourseService(repo).delete(course_id=course.id, org_id=uuid.uuid4())

    assert excinfo.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_unlinks_the_media_assets_of_the_course(
    monkeypatch, tmp_path: Path
) -> None:
    asset = tmp_path / "9f86d081.mp3"
    asset.write_bytes(b"podcast")
    course = _course()
    repo = _repo(course)
    _media(monkeypatch, paths=[str(asset)])

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
