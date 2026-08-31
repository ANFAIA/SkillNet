"""Exercise grading (pure) and attempt submission (DB-bound)."""

import uuid
from datetime import datetime, timezone
from typing import Any

from src.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from src.llm.client import LLMService
from src.models import Enrollment, EnrollmentStatus, ExerciseAttempt, User, UserRole
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.schemas.exercise import AttemptResult, CorrectResult
from src.services.language_policy import resolve_language

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


def _build_correct_answer(exercise_type: str, content: dict) -> dict:
    """Build the answer payload that would score 1.0 for a deterministic exercise."""
    if exercise_type == "test":
        return {"selected": content.get("correct")}
    if exercise_type == "true_false":
        return {"answer": content.get("correct")}
    if exercise_type == "fill_blank":
        return {"answers": content.get("blanks") or []}
    if exercise_type == "order_steps":
        return {"order": content.get("correct_order") or []}
    raise ValidationError(f"Cannot auto-correct exercise type: {exercise_type}")


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
        # A score of 0.5 is considered acceptable for subjective exercises.
        return AttemptResult(
            score=0.5,
            passed=True,
            feedback="Respuesta registrada. Pendiente de evaluacion manual.",
            explanation=None,
        )

    raise ValidationError(f"Unknown exercise type: {exercise_type}")


class ExerciseService:
    def __init__(
        self,
        exercise_repo: ExerciseRepository,
        enrollment_repo: EnrollmentRepository,
        course_repo: CourseRepository,
    ) -> None:
        self.exercise_repo = exercise_repo
        self.enrollment_repo = enrollment_repo
        self.course_repo = course_repo

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

        # Transition assigned -> in_progress on first interaction.
        if enrollment.status == EnrollmentStatus.ASSIGNED:
            enrollment.status = EnrollmentStatus.IN_PROGRESS
            enrollment.started_at = datetime.now(timezone.utc)

        exercise_type = exercise.type.value
        if exercise_type in _OPEN_TYPES and llm is not None:
            from src.services.llm_grading import grade_open_answer

            result = await grade_open_answer(
                llm,
                exercise_type,
                exercise.content,
                answer,
                # The feedback is text the learner reads, so it follows the course.
                language=resolve_language(course=course),
            )
        else:
            result = grade(exercise_type, exercise.content, answer)
        await self._persist(user.id, exercise_id, answer, result)

        # Recompute progress and mark completed if all modules are done.
        await self._update_enrollment_progress(enrollment, user.org_id)

        return result

    async def _update_enrollment_progress(
        self, enrollment: Enrollment, org_id: uuid.UUID
    ) -> None:
        """Recompute progress from passed exercises; complete if 100%."""
        from src.services.enrollment_service import EnrollmentService

        svc = EnrollmentService(
            self.enrollment_repo, self.course_repo, self.exercise_repo
        )
        progress = await svc.compute_progress(
            enrollment=enrollment, org_id=org_id
        )
        if (
            progress is not None
            and progress >= 1.0
            and enrollment.status != EnrollmentStatus.COMPLETED
        ):
            enrollment.status = EnrollmentStatus.COMPLETED
            enrollment.completed_at = datetime.now(timezone.utc)
            enrollment.score = progress
        await self.exercise_repo.session.flush()

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

    async def correct_exercise(
        self,
        *,
        user: User,
        exercise_id: uuid.UUID,
    ) -> CorrectResult:
        """Submit the known-correct answer on behalf of the user and return
        the result together with the correct answer so the UI can display it."""
        exercise = await self.exercise_repo.get_with_course(exercise_id)
        if exercise is None:
            raise NotFoundError("exercises", str(exercise_id))
        course = exercise.lesson.module.course
        if course.org_id != user.org_id:
            raise NotFoundError("exercises", str(exercise_id))

        exercise_type = exercise.type.value
        if exercise_type not in _DETERMINISTIC:
            raise ValidationError(
                f"Cannot auto-correct exercise type: {exercise_type}"
            )

        correct_answer = _build_correct_answer(exercise_type, exercise.content)
        result = await self.submit_attempt(
            user=user, exercise_id=exercise_id, answer=correct_answer
        )
        return CorrectResult(
            score=result.score,
            passed=result.passed,
            feedback=result.feedback,
            explanation=result.explanation,
            correct_answer=correct_answer,
        )

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
