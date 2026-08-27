"""Focused business-rule tests for folders and atomic course skills."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.services.course_folder_service import CourseFolderService
from src.services.course_service import CourseService
from src.services.enrollment_service import EnrollmentService
from src.services.skill_service import SkillService


class _FakeSavepoint:
    """Stand-in for the SAVEPOINT `_enrol_once` wraps its insert in.

    Swallows nothing: an `IntegrityError` raised inside the block still propagates to
    the handler under test, which is the whole point of the savepoint.
    """

    async def __aenter__(self) -> "_FakeSavepoint":
        return self

    async def __aexit__(self, *exc_info) -> bool:  # noqa: ANN002
        return False


def _session_with_users(user_ids):
    """Fake session whose `execute(select(User.id)...)` returns those ids.

    `_assert_users_in_org` runs one `select(User.id).where(id.in_(...), org_id==...)`
    and reads `.all()` as `[(id,), ...]`. This mock reports exactly `user_ids` as the
    users that live in the queried org, so the caller can model "all present" or
    "one belongs to another org" by choosing what it returns.
    """
    result = SimpleNamespace(all=lambda: [(uid,) for uid in user_ids])
    return SimpleNamespace(
        execute=AsyncMock(return_value=result),
        begin_nested=lambda: _FakeSavepoint(),
    )


@pytest.mark.asyncio
async def test_folder_names_are_unique_case_insensitively() -> None:
    repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    )

    with pytest.raises(ConflictError):
        await CourseFolderService(repo).create(org_id=uuid.uuid4(), name="Soporte")


@pytest.mark.asyncio
async def test_replace_course_skills_reuses_names_and_deduplicates(monkeypatch) -> None:
    org_id = uuid.uuid4()
    course_id = uuid.uuid4()
    existing = SimpleNamespace(id=uuid.uuid4(), name="Validar entradas")
    repo = SimpleNamespace(
        session=object(),
        get_by_name=AsyncMock(return_value=existing),
        get_scoped=AsyncMock(),
        create=AsyncMock(),
        replace_course_skills=AsyncMock(),
    )
    course_repo = SimpleNamespace(get_scoped=AsyncMock(return_value=object()))
    monkeypatch.setattr(
        "src.repositories.course_repo.CourseRepository", lambda session: course_repo
    )

    result = await SkillService(repo).replace_course_skills(
        org_id=org_id,
        course_id=course_id,
        items=[
            {"id": None, "name": existing.name, "description": None},
            {"id": None, "name": existing.name, "description": None},
        ],
    )

    assert result == [existing]
    repo.replace_course_skills.assert_awaited_once_with(course_id, [existing])
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_course_skills_rejects_foreign_skill(monkeypatch) -> None:
    course_repo = SimpleNamespace(get_scoped=AsyncMock(return_value=object()))
    monkeypatch.setattr(
        "src.repositories.course_repo.CourseRepository", lambda session: course_repo
    )
    repo = SimpleNamespace(
        session=object(),
        get_scoped=AsyncMock(return_value=None),
    )
    skill_id = uuid.uuid4()

    with pytest.raises(NotFoundError):
        await SkillService(repo).replace_course_skills(
            org_id=uuid.uuid4(),
            course_id=uuid.uuid4(),
            items=[{"id": skill_id, "name": None, "description": None}],
        )


@pytest.mark.asyncio
async def test_assign_courses_is_idempotent_across_a_folder() -> None:
    org_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    user_id = uuid.uuid4()
    first_course_id = uuid.uuid4()
    second_course_id = uuid.uuid4()
    existing = SimpleNamespace(id=uuid.uuid4())
    created = SimpleNamespace(id=uuid.uuid4())
    enrollment_repo = SimpleNamespace(
        session=_session_with_users([user_id]),
        # `assign_courses` reads every (user, course) pair of the batch in one query and
        # only fetches the rows that snapshot flagged — here, the first course.
        existing_pairs=AsyncMock(return_value={(user_id, first_course_id)}),
        get_by_user_and_course=AsyncMock(side_effect=[existing]),
        create=AsyncMock(return_value=created),
    )
    course_repo = SimpleNamespace(get_scoped=AsyncMock(return_value=object()))
    exercise_repo = SimpleNamespace()

    enrollments, skipped = await EnrollmentService(
        enrollment_repo,
        course_repo,
        exercise_repo,
        lesson_progress_repo=SimpleNamespace(),
    ).assign_courses(
        org_id=org_id,
        assigned_by=admin_id,
        course_ids=[first_course_id, second_course_id],
        user_ids=[user_id],
        deadline=None,
    )

    assert enrollments == [created]
    assert skipped == 1
    assert course_repo.get_scoped.await_count == 2
    enrollment_repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_assign_rejects_a_user_from_another_organisation() -> None:
    """A course scoped to the admin's org must not enrol a learner of another org."""
    org_id = uuid.uuid4()
    own_user = uuid.uuid4()
    foreign_user = uuid.uuid4()
    enrollment_repo = SimpleNamespace(
        # Only `own_user` lives in `org_id`; `foreign_user` is absent from the query.
        session=_session_with_users([own_user]),
        get_by_user_and_course=AsyncMock(return_value=None),
        create=AsyncMock(),
    )
    course_repo = SimpleNamespace(get_scoped=AsyncMock(return_value=object()))
    service = EnrollmentService(
        enrollment_repo,
        course_repo,
        SimpleNamespace(),
        lesson_progress_repo=SimpleNamespace(),
    )

    with pytest.raises(ForbiddenError):
        await service.assign(
            org_id=org_id,
            assigned_by=uuid.uuid4(),
            course_id=uuid.uuid4(),
            user_ids=[own_user, foreign_user],
            deadline=None,
        )
    # Nothing is written when any user is out of tenant.
    enrollment_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_assign_courses_rejects_a_user_from_another_organisation() -> None:
    org_id = uuid.uuid4()
    own_user = uuid.uuid4()
    foreign_user = uuid.uuid4()
    enrollment_repo = SimpleNamespace(
        session=_session_with_users([own_user]),
        get_by_user_and_course=AsyncMock(return_value=None),
        create=AsyncMock(),
    )
    course_repo = SimpleNamespace(get_scoped=AsyncMock(return_value=object()))
    service = EnrollmentService(
        enrollment_repo,
        course_repo,
        SimpleNamespace(),
        lesson_progress_repo=SimpleNamespace(),
    )

    with pytest.raises(ForbiddenError):
        await service.assign_courses(
            org_id=org_id,
            assigned_by=uuid.uuid4(),
            course_ids=[uuid.uuid4()],
            user_ids=[own_user, foreign_user],
            deadline=None,
        )
    enrollment_repo.create.assert_not_awaited()


def _enrollment_service(enrollment_repo, course_repo=None) -> EnrollmentService:
    return EnrollmentService(
        enrollment_repo,
        course_repo or SimpleNamespace(get_scoped=AsyncMock(return_value=object())),
        SimpleNamespace(),
        lesson_progress_repo=SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_assign_skips_the_already_enrolled_instead_of_aborting_the_batch() -> None:
    """One learner who already has the course must not fail the other nine.

    `assign` used to raise `ConflictError` on the first existing row, so the whole
    request wrote nothing — while `assign_courses` skipped. The two agreeing is the
    point of the fix; the existing row is returned in place of a new one so
    `POST /enrollments` still answers one entry per requested user.
    """
    org_id = uuid.uuid4()
    course_id = uuid.uuid4()
    already, fresh = uuid.uuid4(), uuid.uuid4()
    existing = SimpleNamespace(id=uuid.uuid4(), user_id=already)
    created = SimpleNamespace(id=uuid.uuid4(), user_id=fresh)
    enrollment_repo = SimpleNamespace(
        session=_session_with_users([already, fresh]),
        existing_pairs=AsyncMock(return_value={(already, course_id)}),
        get_by_user_and_course=AsyncMock(side_effect=[existing]),
        create=AsyncMock(return_value=created),
    )

    enrollments = await _enrollment_service(enrollment_repo).assign(
        org_id=org_id,
        assigned_by=uuid.uuid4(),
        course_id=course_id,
        user_ids=[already, fresh],
        deadline=None,
    )

    # One row per requested user, in the requested order.
    assert enrollments == [existing, created]
    enrollment_repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_assign_collapses_a_repeated_user_id() -> None:
    """The same id twice in one body is one enrollment, not a self-inflicted conflict."""
    user_id = uuid.uuid4()
    created = SimpleNamespace(id=uuid.uuid4())
    enrollment_repo = SimpleNamespace(
        session=_session_with_users([user_id]),
        existing_pairs=AsyncMock(return_value=set()),
        get_by_user_and_course=AsyncMock(return_value=None),
        create=AsyncMock(return_value=created),
    )

    enrollments = await _enrollment_service(enrollment_repo).assign(
        org_id=uuid.uuid4(),
        assigned_by=uuid.uuid4(),
        course_id=uuid.uuid4(),
        user_ids=[user_id, user_id],
        deadline=None,
    )

    assert enrollments == [created]
    enrollment_repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_assign_survives_losing_the_insert_race() -> None:
    """A double click races two inserts; the loser must not become a 500.

    Models the race exactly: the batch snapshot says the pair is free, the INSERT then
    violates `uq_enrollments_user_course`, and the row the winner wrote is read back.
    The snapshot is precisely what cannot prevent this — it is one query taken before the
    loop, so it can be stale by the time the insert runs, which is why the SAVEPOINT is
    still the thing that saves the batch.
    """
    user_id = uuid.uuid4()
    winner_row = SimpleNamespace(id=uuid.uuid4())
    enrollment_repo = SimpleNamespace(
        session=_session_with_users([user_id]),
        existing_pairs=AsyncMock(return_value=set()),
        # The only read: the one in the `except IntegrityError` branch.
        get_by_user_and_course=AsyncMock(side_effect=[winner_row]),
        create=AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("duplicate key"))
        ),
    )

    enrollments = await _enrollment_service(enrollment_repo).assign(
        org_id=uuid.uuid4(),
        assigned_by=uuid.uuid4(),
        course_id=uuid.uuid4(),
        user_ids=[user_id],
        deadline=None,
    )

    assert enrollments == [winner_row]


@pytest.mark.asyncio
async def test_assign_still_raises_when_the_integrity_error_is_not_a_duplicate() -> None:
    """No row appears after the failure, so nothing can be reused: let it surface."""
    user_id = uuid.uuid4()
    enrollment_repo = SimpleNamespace(
        session=_session_with_users([user_id]),
        existing_pairs=AsyncMock(return_value=set()),
        get_by_user_and_course=AsyncMock(side_effect=[None]),
        create=AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("fk violation"))
        ),
    )

    with pytest.raises(IntegrityError):
        await _enrollment_service(enrollment_repo).assign(
            org_id=uuid.uuid4(),
            assigned_by=uuid.uuid4(),
            course_id=uuid.uuid4(),
            user_ids=[user_id],
            deadline=None,
        )


@pytest.mark.asyncio
async def test_moving_a_course_writes_the_folder_relationship_not_only_the_id(
    monkeypatch,
) -> None:
    """`folder_name` is projected from `course.folder`, so the move must set that too.

    Writing `folder_id` alone left the relationship — already loaded by `get_scoped` —
    pointing at the previous row, so `PUT /courses/{id}` answered with the new
    `folder_id` next to the old `folder_name` (or `null`).
    """
    org_id = uuid.uuid4()
    folder = SimpleNamespace(id=uuid.uuid4(), name="Soporte")
    course = SimpleNamespace(
        id=uuid.uuid4(),
        folder_id=None,
        folder=None,
        artifact_generate_policy=None,
    )
    repo = SimpleNamespace(
        session=object(),
        get_scoped=AsyncMock(return_value=course),
        update=AsyncMock(side_effect=lambda obj, **kwargs: obj),
        replace_artifact_generators=AsyncMock(),
    )
    monkeypatch.setattr(
        "src.services.course_service.CourseFolderRepository",
        lambda session: SimpleNamespace(get_scoped=AsyncMock(return_value=folder)),
    )

    await CourseService(repo).update(
        course_id=course.id, org_id=org_id, changes={"folder_id": folder.id}
    )

    repo.update.assert_awaited_once_with(course, folder=folder)


@pytest.mark.asyncio
async def test_unfiling_a_course_clears_the_relationship(monkeypatch) -> None:
    """`folder_id: null` must reach the ORM as `folder = None`, not be filtered out."""
    course = SimpleNamespace(
        id=uuid.uuid4(),
        folder_id=uuid.uuid4(),
        folder=SimpleNamespace(name="Archivo"),
        artifact_generate_policy=None,
    )
    repo = SimpleNamespace(
        session=object(),
        get_scoped=AsyncMock(return_value=course),
        update=AsyncMock(side_effect=lambda obj, **kwargs: obj),
        replace_artifact_generators=AsyncMock(),
    )

    await CourseService(repo).update(
        course_id=course.id, org_id=uuid.uuid4(), changes={"folder_id": None}
    )

    repo.update.assert_awaited_once_with(course, folder=None)
