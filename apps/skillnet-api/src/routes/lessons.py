"""Lesson routes: update lesson title/content for draft courses."""

import uuid

from fastapi import APIRouter

from src.core.exceptions import ConflictError, NotFoundError
from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.models import ContentStatus
from src.repositories.lesson_repo import LessonRepository
from src.schemas.course import LessonRead, LessonUpdate
from src.schemas.exercise import ExerciseRead

router = APIRouter(prefix="/lessons", tags=["Lessons"])


@router.put("/{lesson_id}", response_model=LessonRead)
async def update_lesson(
    admin: AdminUser,
    db: DBSession,
    lesson_id: uuid.UUID,
    body: LessonUpdate,
) -> LessonRead:
    repo = LessonRepository(db)
    lesson = await repo.get_with_course(lesson_id)
    if lesson is None or lesson.module.course.org_id != admin.org_id:
        raise NotFoundError("lessons", str(lesson_id))

    course = lesson.module.course
    if course.status != ContentStatus.DRAFT:
        raise ConflictError("Only draft courses can be edited")

    changes = body.model_dump(exclude_unset=True)
    if changes:
        lesson = await repo.update(lesson, **changes)
    await db.commit()

    exercises = [
        ExerciseRead(
            id=ex.id,
            type=ex.type.value,
            content=ex.content,
            position=ex.position,
        )
        for ex in lesson.exercises
    ]
    return LessonRead(
        id=lesson.id,
        title=lesson.title,
        content=lesson.content,
        position=lesson.position,
        exercises=exercises,
    )
