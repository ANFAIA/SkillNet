"""Exercise routes: submit an attempt and read attempt history."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from src.deps.auth import CurrentUser, EmployeeUser
from src.deps.db import DBSession
from src.deps.llm import OptionalLLMDep
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.schemas.exercise import AttemptRead, AttemptRequest, AttemptResult
from src.services.exercise_service import ExerciseService

router = APIRouter(prefix="/exercises", tags=["Exercises"])


def _service(db: DBSession) -> ExerciseService:
    return ExerciseService(ExerciseRepository(db), EnrollmentRepository(db))


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
