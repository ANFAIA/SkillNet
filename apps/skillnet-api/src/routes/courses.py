"""Course routes: CRUD plus generate/publish/archive lifecycle actions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from src.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from src.deps.auth import AdminUser, CurrentUser
from src.deps.db import DBSession
from src.models import Course, ContentStatus, UserRole
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.generation_job_repo import GenerationJobRepository
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
from src.services.course_service import CourseService
from src.services.generation_service import GenerationService

router = APIRouter(prefix="/courses", tags=["Courses"])


def _service(db: DBSession) -> CourseService:
    return CourseService(CourseRepository(db))


def _parse_status(status: str | None) -> ContentStatus | None:
    if status is None:
        return None
    try:
        return ContentStatus(status)
    except ValueError as exc:
        raise ValidationError(f"Invalid status: {status}", field="status") from exc


def _summary(course: Course, module_count: int | None) -> CourseRead:
    return CourseRead(
        id=course.id,
        title=course.title,
        description=course.description,
        outcome=course.outcome,
        status=course.status.value,
        source_document_id=course.source_document_id,
        created_at=course.created_at,
        module_count=module_count,
    )


def _detail(course: Course, *, strip: bool) -> CourseDetail:
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
        created_at=course.created_at,
        module_count=len(course.modules),
        modules=modules,
    )


@router.get("", response_model=PaginatedResponse[CourseRead])
async def list_courses(
    admin: AdminUser,
    db: DBSession,
    status: Annotated[str | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[CourseRead]:
    repo = CourseRepository(db)
    pairs, total = await repo.list_courses(
        org_id=admin.org_id,
        status=_parse_status(status),
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse[CourseRead](
        items=[_summary(course, count) for course, count in pairs],
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
    return _summary(course, 0)


@router.get("/{course_id}", response_model=CourseDetail)
async def get_course(
    user: CurrentUser, db: DBSession, course_id: uuid.UUID
) -> CourseDetail:
    repo = CourseRepository(db)
    course = await repo.get_detail(course_id, user.org_id)
    if course is None:
        raise NotFoundError("courses", str(course_id))

    strip = user.role == UserRole.EMPLOYEE
    if strip:
        enrollment_repo = EnrollmentRepository(db)
        enrollment = await enrollment_repo.get_by_user_and_course(user.id, course_id)
        if enrollment is None:
            raise ForbiddenError("You are not enrolled in this course")
    return _detail(course, strip=strip)


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
    return _summary(course, None)


@router.delete("/{course_id}", status_code=204)
async def delete_course(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> Response:
    service = _service(db)
    await service.delete(course_id=course_id, org_id=admin.org_id)
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
    return _summary(course, len(course.modules))


@router.post("/{course_id}/archive", response_model=CourseRead)
async def archive_course(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseRead:
    service = _service(db)
    course = await service.archive(course_id=course_id, org_id=admin.org_id)
    await db.commit()
    return _summary(course, None)
