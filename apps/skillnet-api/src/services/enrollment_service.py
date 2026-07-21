"""Enrollment business logic: assignment, progress, and removal rules."""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timezone

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.models import Enrollment, EnrollmentStatus
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.lesson_progress_repo import LessonProgressRepository


class EnrollmentService:
    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        course_repo: CourseRepository,
        exercise_repo: ExerciseRepository,
        lesson_progress_repo: LessonProgressRepository | None = None,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.course_repo = course_repo
        self.exercise_repo = exercise_repo
        self.lesson_progress_repo = lesson_progress_repo or LessonProgressRepository(
            enrollment_repo.session
        )

    async def assign(
        self,
        *,
        org_id: uuid.UUID,
        assigned_by: uuid.UUID,
        course_id: uuid.UUID,
        user_ids: list[uuid.UUID],
        deadline: date | None,
    ) -> list[Enrollment]:
        course = await self.course_repo.get_scoped(course_id, org_id)
        if course is None:
            raise NotFoundError("courses", str(course_id))

        created: list[Enrollment] = []
        for user_id in user_ids:
            existing = await self.enrollment_repo.get_by_user_and_course(
                user_id, course_id
            )
            if existing is not None:
                raise ConflictError(
                    f"User {user_id} is already enrolled in this course"
                )
            enrollment = await self.enrollment_repo.create(
                user_id=user_id,
                course_id=course_id,
                assigned_by=assigned_by,
                status=EnrollmentStatus.ASSIGNED,
                deadline=deadline,
            )
            created.append(enrollment)
        return created

    async def get_scoped(
        self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID
    ) -> Enrollment:
        enrollment = await self.enrollment_repo.get_with_course(enrollment_id)
        if enrollment is None or enrollment.course.org_id != org_id:
            raise NotFoundError("enrollments", str(enrollment_id))
        return enrollment

    async def list_enrollments(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        course_id: uuid.UUID | None,
        status: EnrollmentStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Enrollment], int]:
        return await self.enrollment_repo.list_enrollments(
            org_id=org_id,
            user_id=user_id,
            course_id=course_id,
            status=status,
            offset=offset,
            limit=limit,
        )

    async def compute_progress(
        self, *, enrollment: Enrollment, org_id: uuid.UUID
    ) -> float | None:
        """Fraction of lessons completed.

        A lesson is "completed" when:
        - it has been visited (a ``LessonProgress`` row exists), AND
        - all its exercises (if any) have a passing attempt.

        Progress = completed_lessons / total_lessons.
        """
        course = await self.course_repo.get_detail(enrollment.course_id, org_id)
        if course is None or not course.modules:
            return 1.0

        all_lessons = [
            lesson
            for module in course.modules
            for lesson in module.lessons
        ]
        if not all_lessons:
            return 1.0

        # Gather all lesson & exercise ids for batch queries.
        all_lesson_ids = [lesson.id for lesson in all_lessons]
        all_exercise_ids = [
            exercise.id
            for lesson in all_lessons
            for exercise in lesson.exercises
        ]

        visited = await self.lesson_progress_repo.completed_lesson_ids(
            user_id=enrollment.user_id, lesson_ids=all_lesson_ids
        )
        passed = await self.exercise_repo.passed_exercise_ids(
            user_id=enrollment.user_id, exercise_ids=all_exercise_ids
        )

        completed = 0
        for lesson in all_lessons:
            if lesson.id not in visited:
                continue
            lesson_exercise_ids = [ex.id for ex in lesson.exercises]
            if all(eid in passed for eid in lesson_exercise_ids):
                completed += 1

        return completed / len(all_lessons)

    async def complete(
        self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Enrollment, float]:
        """Mark an enrollment as completed, compute and store the final score.

        Returns the updated enrollment and its progress value.
        """
        enrollment = await self.get_scoped(
            enrollment_id=enrollment_id, org_id=org_id
        )
        if enrollment.user_id != user_id:
            raise ForbiddenError("You can only complete your own enrollments")

        if enrollment.status == EnrollmentStatus.COMPLETED:
            progress = await self.compute_progress(
                enrollment=enrollment, org_id=org_id
            )
            return enrollment, progress or 0.0

        progress = await self.compute_progress(
            enrollment=enrollment, org_id=org_id
        )
        if progress is None or progress < 1.0:
            raise ConflictError(
                "Cannot complete enrollment: not all lessons are finished. "
                f"Current progress: {int((progress or 0) * 100)}%"
            )
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = datetime.now(timezone.utc)
        enrollment.score = progress
        await self.enrollment_repo.session.flush()
        return enrollment, progress or 0.0

    async def delete(self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID) -> None:
        enrollment = await self.get_scoped(
            enrollment_id=enrollment_id, org_id=org_id
        )
        if enrollment.status != EnrollmentStatus.ASSIGNED:
            raise ConflictError("Only assigned (not started) enrollments can be removed")
        await self.enrollment_repo.delete(enrollment)
