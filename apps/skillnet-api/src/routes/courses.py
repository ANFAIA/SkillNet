"""Course routes: CRUD plus generate/publish/archive lifecycle actions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from src.core.exceptions import NotFoundError, ValidationError
from src.deps.auth import AdminUser, CurrentUser
from src.deps.db import DBSession
from src.models.base import as_utc
from src.models import Course, ContentStatus, CourseGenerationState, UserRole
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.generation_job_repo import GenerationJobRepository
from src.repositories.lesson_progress_repo import LessonProgressRepository
from src.schemas.common import PaginatedResponse
from src.schemas.course import (
    CourseCreate,
    CourseDetail,
    CourseRead,
    CourseUpdate,
    LessonRead,
    ModuleRead,
)
from src.schemas.exercise import ExerciseRead, strip_answers
from src.services.artifact_access import can_generate_artifacts
from src.services.course_access import assert_learner_can_open
from src.services.course_delivery import resolve_delivery
from src.services.course_service import CourseService
from src.services.generation_service import GenerationService
from src.services.node_progression import navigation_mode

router = APIRouter(prefix="/courses", tags=["Courses"])


def _delivery(course: Course) -> str:
    """The one thing v2 adds to this v1 file: which path this course is actually on.

    ``resolve_delivery`` and not ``course.delivery_mode``, because the column is only one
    of the two conditions (course opted in, schema validated). A course flagged
    ``dynamic`` whose schema is still in draft is served by the v1 tree, and a badge
    reading "dinamico" over it would send the creator looking for a node map that does
    not exist.
    """
    return resolve_delivery(course)


def _service(db: DBSession) -> CourseService:
    return CourseService(CourseRepository(db))


def _parse_status(status: str | None) -> ContentStatus | None:
    if status is None:
        return None
    try:
        return ContentStatus(status)
    except ValueError as exc:
        raise ValidationError(f"Invalid status: {status}", field="status") from exc


def _parse_generation_state(value: str | None) -> CourseGenerationState | None:
    """Validate the ``generation_state`` list filter, the way ``_parse_status`` does.

    The admin library needs "show me the courses whose creation died" as a first-class
    filter, and doing it client-side would only ever find the failures inside the page
    that happened to be fetched.
    """
    if value is None:
        return None
    try:
        return CourseGenerationState(value)
    except ValueError as exc:
        raise ValidationError(
            f"Invalid generation_state: {value}", field="generation_state"
        ) from exc


def _policy(course: Course) -> str:
    raw = getattr(course, "artifact_generate_policy", None)
    if raw is None:
        return "admin"
    return str(getattr(raw, "value", raw))


def _tutor_style(course: Course) -> str:
    raw = getattr(course, "tutor_style", None)
    if raw is None:
        return "socratic"
    return str(getattr(raw, "value", raw))


def _navigation_mode(course: Course) -> str:
    """The order rule this course declares, for the admin screen that edits it.

    The *declared* setting, not the one resolved for the caller: an admin editing a
    course must see the value they set, and ``resolve_navigation`` deliberately reports
    ``free`` to admins so their own preview is never paced. ``navigation_mode`` is the
    reader that answers the first question; the learner surface uses the other one.
    """
    return navigation_mode(course)


def _image_source_policy(course: Course) -> str:
    """What this course does with its source document's own images.

    ``getattr`` with a fallback for the same reason as ``_tutor_style``: a course row
    that predates migration 0028 (and the hand-built ``Course`` stand-ins the unit tests
    project) must read ``auto`` — the rule — rather than crash the listing.
    """
    raw = getattr(course, "image_source_policy", None)
    if raw is None:
        return "auto"
    return str(getattr(raw, "value", raw))


def _generation_state(course: Course) -> str:
    """Whether a creation run owns this course, and how the last one ended.

    ``getattr`` with a fallback for the same reason as ``_tutor_style``: the
    projectors are called with hand-built ``Course`` stand-ins in unit tests, and a
    course that predates migration 0025 must read ``idle``, never crash the list.
    """
    raw = getattr(course, "generation_state", None)
    if raw is None:
        return "idle"
    return str(getattr(raw, "value", raw))


def _can_generate(course: Course, user, generator_ids: list[uuid.UUID]) -> bool:
    return can_generate_artifacts(
        role=user.role,
        user_id=user.id,
        policy=_policy(course),
        generator_ids=generator_ids,
    )


def _summary(
    course: Course,
    module_count: int | None,
    node_count: int | None = None,
    *,
    user,
    generator_ids: list[uuid.UUID] | None = None,
) -> CourseRead:
    ids = list(generator_ids or [])
    return CourseRead(
        id=course.id,
        title=course.title,
        description=course.description,
        outcome=course.outcome,
        status=course.status.value,
        source_document_id=course.source_document_id,
        folder_id=course.folder_id,
        folder_name=(course.__dict__.get("folder").name if course.__dict__.get("folder") else None),
        created_at=course.created_at,
        updated_at=as_utc(course.updated_at),
        module_count=module_count,
        node_count=node_count,
        schema_status=course.schema_status.value if course.schema_status else None,
        is_demo=course.is_demo,
        delivery_mode=_delivery(course),
        artifact_generate_policy=_policy(course),
        artifact_generator_ids=ids,
        can_generate_artifacts=_can_generate(course, user, ids),
        tutor_style=_tutor_style(course),
        navigation_mode=_navigation_mode(course),
        image_source_policy=_image_source_policy(course),
        generation_state=_generation_state(course),
        generation_error=getattr(course, "generation_error", None),
        generation_failed_at=getattr(course, "generation_failed_at", None),
    )


def _detail(
    course: Course,
    *,
    strip: bool,
    node_count: int | None = None,
    user,
    generator_ids: list[uuid.UUID] | None = None,
) -> CourseDetail:
    modules = []
    for module in course.modules:
        lessons = []
        for lesson in module.lessons:
            exercises = [
                ExerciseRead(
                    id=exercise.id,
                    type=exercise.type.value,
                    content=(
                        strip_answers(exercise.content, exercise.type.value)
                        if strip
                        else exercise.content
                    ),
                    position=exercise.position,
                )
                for exercise in lesson.exercises
            ]
            lessons.append(
                LessonRead(
                    id=lesson.id,
                    title=lesson.title,
                    content=lesson.content,
                    position=lesson.position,
                    exercises=exercises,
                )
            )
        modules.append(
            ModuleRead(
                id=module.id,
                title=module.title,
                summary=module.summary,
                position=module.position,
                lessons=lessons,
            )
        )
    return CourseDetail(
        id=course.id,
        title=course.title,
        description=course.description,
        outcome=course.outcome,
        status=course.status.value,
        source_document_id=course.source_document_id,
        folder_id=course.folder_id,
        folder_name=(course.__dict__.get("folder").name if course.__dict__.get("folder") else None),
        created_at=course.created_at,
        updated_at=as_utc(course.updated_at),
        module_count=len(course.modules),
        node_count=node_count,
        schema_status=course.schema_status.value if course.schema_status else None,
        is_demo=course.is_demo,
        delivery_mode=_delivery(course),
        artifact_generate_policy=_policy(course),
        artifact_generator_ids=list(generator_ids or []),
        can_generate_artifacts=_can_generate(course, user, list(generator_ids or [])),
        tutor_style=_tutor_style(course),
        navigation_mode=_navigation_mode(course),
        image_source_policy=_image_source_policy(course),
        generation_state=_generation_state(course),
        generation_error=getattr(course, "generation_error", None),
        generation_failed_at=getattr(course, "generation_failed_at", None),
        modules=modules,
    )


@router.get("", response_model=PaginatedResponse[CourseRead])
async def list_courses(
    admin: AdminUser,
    db: DBSession,
    status: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    folder_id: Annotated[uuid.UUID | None, Query()] = None,
    unorganized: Annotated[bool, Query()] = False,
    generation_state: Annotated[str | None, Query()] = None,
    #: Opt-out, not a new default. Archived courses have always been part of an
    #: unfiltered listing and other callers (the demo lookup, the folder counts on
    #: other screens) still expect the whole catalogue; only the library asks to hide
    #: them, so the library is what passes ``include_archived=false``.
    include_archived: Annotated[bool, Query()] = True,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[CourseRead]:
    repo = CourseRepository(db)
    pairs, total = await repo.list_courses(
        org_id=admin.org_id,
        status=_parse_status(status),
        search=search,
        folder_id=folder_id,
        unorganized=unorganized,
        generation_state=_parse_generation_state(generation_state),
        include_archived=include_archived,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse[CourseRead](
        items=[_summary(course, mod_count, node_count, user=admin) for course, mod_count, node_count in pairs],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=CourseRead, status_code=201)
async def create_course(
    admin: AdminUser, db: DBSession, body: CourseCreate
) -> CourseRead:
    service = _service(db)
    payload = body.model_dump(exclude={"document_ids"})
    if body.source_document_id is None and body.document_ids:
        payload["source_document_id"] = body.document_ids[0]
    course = await service.create(
        org_id=admin.org_id, created_by=admin.id, **payload
    )
    await db.commit()
    return _summary(course, 0, user=admin)


@router.get("/{course_id}", response_model=CourseDetail)
async def get_course(
    user: CurrentUser, db: DBSession, course_id: uuid.UUID
) -> CourseDetail:
    repo = CourseRepository(db)
    course = await repo.get_detail(course_id, user.org_id)
    if course is None:
        raise NotFoundError("courses", str(course_id))

    # The gate knows who is a learner (and that an admin is not), so it runs
    # unconditionally; `strip` stays what it always was — a decision about the answer,
    # not about access.
    await assert_learner_can_open(
        user=user, course=course, enrollments=EnrollmentRepository(db)
    )
    strip = user.role == UserRole.EMPLOYEE
    node_count = len(await CourseNodeRepository(db).list_for_course(course_id))
    generator_ids = await repo.list_artifact_generator_ids(course.id)
    return _detail(
        course,
        strip=strip,
        node_count=node_count,
        user=user,
        generator_ids=generator_ids,
    )


@router.get("/{course_id}/progress")
async def get_course_progress(
    user: CurrentUser, db: DBSession, course_id: uuid.UUID
) -> dict:
    """Return the full progression state for the current user in a course.

    Each lesson reports its lock status, exercise counts, and completion.
    A lesson is locked when the previous lesson (ordered by module.position,
    lesson.position) has not been completed.
    """
    course_repo = CourseRepository(db)
    course = await course_repo.get_detail(course_id, user.org_id)
    if course is None:
        raise NotFoundError("courses", str(course_id))

    # Learners must be enrolled, and the course must still be open to them.
    await assert_learner_can_open(
        user=user, course=course, enrollments=EnrollmentRepository(db)
    )

    # Build ordered list of lessons across all modules.
    ordered_lessons = sorted(
        [
            (module, lesson)
            for module in course.modules
            for lesson in module.lessons
        ],
        key=lambda pair: (pair[0].position, pair[1].position),
    )

    if not ordered_lessons:
        return {
            "lessons": [],
            "can_complete": True,
            "total_lessons": 0,
            "completed_lessons": 0,
            "progress_percent": 100,
        }

    # Batch-fetch completion and exercise data.
    all_lesson_ids = [lesson.id for _, lesson in ordered_lessons]
    all_exercise_ids = [
        ex.id for _, lesson in ordered_lessons for ex in lesson.exercises
    ]

    progress_repo = LessonProgressRepository(db)
    visited = await progress_repo.completed_lesson_ids(
        user_id=user.id, lesson_ids=all_lesson_ids
    )

    exercise_repo = ExerciseRepository(db)
    passed = await exercise_repo.passed_exercise_ids(
        user_id=user.id, exercise_ids=all_exercise_ids
    )

    # Determine completion per lesson (visited + all exercises passed).
    def is_completed(lesson) -> bool:
        if lesson.id not in visited:
            return False
        lesson_ex_ids = [ex.id for ex in lesson.exercises]
        return all(eid in passed for eid in lesson_ex_ids)

    lessons_out = []
    completed_count = 0
    for idx, (module, lesson) in enumerate(ordered_lessons):
        completed = is_completed(lesson)
        if completed:
            completed_count += 1

        # First lesson is always unlocked; others require previous completed.
        locked = False
        if idx > 0:
            prev_lesson = ordered_lessons[idx - 1][1]
            locked = not is_completed(prev_lesson)

        lesson_ex_ids = [ex.id for ex in lesson.exercises]
        exercises_passed = sum(1 for eid in lesson_ex_ids if eid in passed)

        lessons_out.append({
            "lesson_id": str(lesson.id),
            "module_id": str(module.id),
            "position": idx + 1,
            "completed": completed,
            "locked": locked,
            "exercises_pending": len(lesson_ex_ids) - exercises_passed,
            "exercises_total": len(lesson_ex_ids),
            "exercises_passed": exercises_passed,
        })

    total = len(ordered_lessons)
    progress_pct = int((completed_count / total) * 100) if total else 100
    return {
        "lessons": lessons_out,
        "can_complete": completed_count == total,
        "total_lessons": total,
        "completed_lessons": completed_count,
        "progress_percent": progress_pct,
    }


@router.put("/{course_id}", response_model=CourseRead)
async def update_course(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID, body: CourseUpdate
) -> CourseRead:
    service = _service(db)
    course = await service.update(
        course_id=course_id,
        org_id=admin.org_id,
        changes=body.model_dump(exclude_unset=True),
    )
    await db.commit()
    generator_ids = await CourseRepository(db).list_artifact_generator_ids(course.id)
    return _summary(course, None, user=admin, generator_ids=generator_ids)


@router.delete("/{course_id}", status_code=204)
async def delete_course(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> Response:
    service = _service(db)
    await service.delete(
        course_id=course_id, org_id=admin.org_id, actor_id=admin.id
    )
    await db.commit()
    return Response(status_code=204)


@router.post("/{course_id}/generate", status_code=202)
async def generate_course(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID, body: dict | None = None
) -> dict:
    course = await _service(db).get_scoped(course_id, admin.org_id)
    payload = body or {}
    raw_source = payload.get("source_document_id")
    source_document_id = (
        uuid.UUID(str(raw_source)) if raw_source else course.source_document_id
    )
    output_type = payload.get("output_type") or "course_and_manual"

    if source_document_id is None:
        raise ValidationError(
            "A source document is required. "
            "Create the course with document_ids or provide source_document_id in the body.",
        )

    from src.models.document import Document
    from sqlalchemy import select
    result = await db.execute(
        select(Document).where(Document.id == source_document_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundError("documents", str(source_document_id))
    if doc.status != "ready":
        raise ValidationError(
            f"Document status is '{doc.status}', must be 'ready'. "
            "Process the document first via POST /documents/{id}/process."
        )

    generation = GenerationService(GenerationJobRepository(db))
    job = await generation.create_and_start(
        db,
        org_id=admin.org_id,
        triggered_by=admin.id,
        course_id=course.id,
        source_document_id=source_document_id,
        output_type=output_type,
    )
    await db.commit()
    return {"job_id": str(job.id)}


@router.post("/{course_id}/publish", response_model=CourseRead)
async def publish_course(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseRead:
    service = _service(db)
    course = await service.publish(course_id=course_id, org_id=admin.org_id)
    await db.commit()
    return _summary(course, len(course.modules), user=admin)


@router.post("/{course_id}/archive", response_model=CourseRead)
async def archive_course(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseRead:
    """Hide a published course from the learners. 409 for any other status.

    Only ``published`` — archiving a draft hides nothing, and it is what used to make
    the way back a guess. Enrollments are left untouched, so the progress of everyone
    part-way through survives and ``POST …/unarchive`` restores the course as it was.
    See ``CourseService.archive``.
    """
    service = _service(db)
    course = await service.archive(course_id=course_id, org_id=admin.org_id)
    await db.commit()
    return _summary(course, None, user=admin)


@router.post("/{course_id}/unarchive", response_model=CourseRead)
async def unarchive_course(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseRead:
    """Return an archived course to ``published`` — the way back from archive.

    ``published`` and not ``draft``: only a published course can be archived, so that is
    the status it had, and the learners who were part-way through get their course back
    without waiting for a second publish. The publish checks still run (an archived
    course can still be edited, so it can have lost its last node meanwhile) and answer
    422 when there is nothing left to deliver; 409 when the course is not archived. See
    ``CourseService.unarchive``.
    """
    service = _service(db)
    course = await service.unarchive(course_id=course_id, org_id=admin.org_id)
    await db.commit()
    return _summary(course, None, user=admin)
