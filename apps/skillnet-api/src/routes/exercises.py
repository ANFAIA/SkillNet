"""Exercise routes: submit an attempt, read attempt history, and update content."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from src.core.exceptions import ConflictError, NotFoundError
from src.deps.auth import AdminUser, CurrentUser, EmployeeUser
from src.deps.db import DBSession
from src.deps.llm import OptionalLLMDep
from src.models import ContentStatus
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.schemas.exercise import AttemptRead, AttemptRequest, AttemptResult, CorrectResult, ExerciseRead, ExerciseUpdate
from src.services.exercise_service import ExerciseService

router = APIRouter(prefix="/exercises", tags=["Exercises"])


def _service(db: DBSession) -> ExerciseService:
    return ExerciseService(ExerciseRepository(db), EnrollmentRepository(db), CourseRepository(db))


@router.put("/{exercise_id}", response_model=ExerciseRead)
async def update_exercise(
    admin: AdminUser,
    db: DBSession,
    exercise_id: uuid.UUID,
    body: ExerciseUpdate,
) -> ExerciseRead:
    repo = ExerciseRepository(db)
    exercise = await repo.get_with_course(exercise_id)
    if exercise is None or exercise.lesson.module.course.org_id != admin.org_id:
        raise NotFoundError("exercises", str(exercise_id))

    course = exercise.lesson.module.course
    if course.status != ContentStatus.DRAFT:
        raise ConflictError("Only draft courses can be edited")

    changes = body.model_dump(exclude_unset=True)
    if changes:
        exercise = await repo.update(exercise, **changes)
    await db.commit()

    return ExerciseRead(
        id=exercise.id,
        type=exercise.type.value,
        content=exercise.content,
        position=exercise.position,
    )


@router.post("/{exercise_id}/attempt", response_model=AttemptResult)
async def attempt_exercise(
    employee: EmployeeUser,
    db: DBSession,
    exercise_id: uuid.UUID,
    body: AttemptRequest,
    llm: OptionalLLMDep,
) -> AttemptResult:
    service = _service(db)
    result = await service.submit_attempt(
        user=employee, exercise_id=exercise_id, answer=body.answer, llm=llm
    )
    await db.commit()
    return result


@router.post("/{exercise_id}/correct", response_model=CorrectResult)
async def correct_exercise(
    employee: EmployeeUser,
    db: DBSession,
    exercise_id: uuid.UUID,
) -> CorrectResult:
    service = _service(db)
    result = await service.correct_exercise(
        user=employee, exercise_id=exercise_id
    )
    await db.commit()
    return result


@router.get("/{exercise_id}/attempts", response_model=list[AttemptRead])
async def list_attempts(
    user: CurrentUser,
    db: DBSession,
    exercise_id: uuid.UUID,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[AttemptRead]:
    service = _service(db)
    attempts = await service.list_attempts(
        requester=user, exercise_id=exercise_id, user_id=user_id
    )
    return [AttemptRead.model_validate(a) for a in attempts]
