"""Exercise grading (pure) and attempt submission (DB-bound)."""

import uuid
from typing import Any

from src.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from src.llm.client import LLMService
from src.models import ExerciseAttempt, User, UserRole
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.schemas.exercise import AttemptResult

_OPEN_TYPES = {"practical_case", "dialogue"}


def _norm(answer: Any, key: str) -> Any:
    """Accept either a bare value or a ``{key: value}`` wrapper."""
    if isinstance(answer, dict) and key in answer:
        return answer[key]
    return answer


def _grade_test(content: dict, answer: Any) -> float:
    selected = _norm(answer, "selected")
    return 1.0 if selected == content.get("correct") else 0.0


def _grade_true_false(content: dict, answer: Any) -> float:
    given = _norm(answer, "answer")
    return 1.0 if bool(given) == bool(content.get("correct")) else 0.0


def _grade_fill_blank(content: dict, answer: Any) -> float:
    expected = content.get("blanks") or []
    given = _norm(answer, "answers")
    if not isinstance(given, list) or len(given) != len(expected):
        return 0.0
    for exp, got in zip(expected, given, strict=True):
        if str(exp).strip().lower() != str(got).strip().lower():
            return 0.0
    return 1.0


def _grade_order_steps(content: dict, answer: Any) -> float:
    expected = content.get("correct_order") or []
    given = _norm(answer, "order")
    return 1.0 if given == expected else 0.0


_DETERMINISTIC = {
    "test": _grade_test,
    "true_false": _grade_true_false,
    "fill_blank": _grade_fill_blank,
    "order_steps": _grade_order_steps,
}


def grade(exercise_type: str, content: dict, answer: Any) -> AttemptResult:
    """Grade an answer. Pure and importable without any DB or LLM dependency."""
    explanation = content.get("explanation")

    if exercise_type in _DETERMINISTIC:
        score = _DETERMINISTIC[exercise_type](content, answer)
        return AttemptResult(
            score=score,
            passed=score >= 1.0,
            feedback=None,
            explanation=explanation,
        )

    if exercise_type in _OPEN_TYPES:
        # Deterministic, LLM-free fallback. LLM grading (when configured) is
        # applied by ``ExerciseService.submit_attempt`` via ``grade_open_answer``.
        return AttemptResult(
            score=0.5,
            passed=False,
            feedback="Respuesta registrada. Pendiente de evaluacion.",
            explanation=None,
        )

    raise ValidationError(f"Unknown exercise type: {exercise_type}")


class ExerciseService:
    def __init__(
        self,
        exercise_repo: ExerciseRepository,
        enrollment_repo: EnrollmentRepository,
    ) -> None:
        self.exercise_repo = exercise_repo
        self.enrollment_repo = enrollment_repo

    async def submit_attempt(
        self,
        *,
        user: User,
        exercise_id: uuid.UUID,
        answer: Any,
        llm: LLMService | None = None,
    ) -> AttemptResult:
        exercise = await self.exercise_repo.get_with_course(exercise_id)
        if exercise is None:
            raise NotFoundError("exercises", str(exercise_id))
        course = exercise.lesson.module.course
        if course.org_id != user.org_id:
            raise NotFoundError("exercises", str(exercise_id))

        enrollment = await self.enrollment_repo.get_by_user_and_course(
            user.id, course.id
        )
        if enrollment is None:
            raise ForbiddenError("You are not enrolled in this course")

        exercise_type = exercise.type.value
        if exercise_type in _OPEN_TYPES and llm is not None:
            from src.services.llm_grading import grade_open_answer

            result = await grade_open_answer(
                llm, exercise_type, exercise.content, answer
            )
        else:
            result = grade(exercise_type, exercise.content, answer)
        await self._persist(user.id, exercise_id, answer, result)
        return result

    async def _persist(
        self,
        user_id: uuid.UUID,
        exercise_id: uuid.UUID,
        answer: Any,
        result: AttemptResult,
    ) -> None:
        attempt = ExerciseAttempt(
            user_id=user_id,
            exercise_id=exercise_id,
            answer=answer,
            score=result.score,
            passed=result.passed,
            feedback=result.feedback,
        )
        self.exercise_repo.session.add(attempt)
        await self.exercise_repo.session.flush()

    async def list_attempts(
        self, *, requester: User, exercise_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> list[ExerciseAttempt]:
        exercise = await self.exercise_repo.get_with_course(exercise_id)
        if exercise is None:
            raise NotFoundError("exercises", str(exercise_id))
        if exercise.lesson.module.course.org_id != requester.org_id:
            raise NotFoundError("exercises", str(exercise_id))

        is_admin = requester.role == UserRole.ADMIN
        target_user_id = user_id if (is_admin and user_id) else requester.id
        attempts = await self.exercise_repo.list_attempts(
            exercise_id=exercise_id, user_id=target_user_id
        )
        return list(attempts)
