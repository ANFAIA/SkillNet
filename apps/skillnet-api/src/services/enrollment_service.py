"""Enrollment business logic: assignment, progress, and removal rules."""

import uuid
from collections.abc import Sequence
from datetime import date

from src.core.exceptions import ConflictError, NotFoundError
from src.models import Enrollment, EnrollmentStatus
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository


class EnrollmentService:
    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        course_repo: CourseRepository,
        exercise_repo: ExerciseRepository,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.course_repo = course_repo
        self.exercise_repo = exercise_repo

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
        """Fraction of modules where every exercise has a passing attempt."""
        course = await self.course_repo.get_detail(enrollment.course_id, org_id)
        if course is None or not course.modules:
            return 0.0

        exercise_ids: list[uuid.UUID] = [
            exercise.id
            for module in course.modules
            for lesson in module.lessons
            for exercise in lesson.exercises
        ]
        passed = await self.exercise_repo.passed_exercise_ids(
            user_id=enrollment.user_id, exercise_ids=exercise_ids
        )

        completed = 0
        for module in course.modules:
            module_exercise_ids = [
                exercise.id
                for lesson in module.lessons
                for exercise in lesson.exercises
            ]
            if all(eid in passed for eid in module_exercise_ids):
                completed += 1
        return completed / len(course.modules)

    async def delete(self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID) -> None:
        enrollment = await self.get_scoped(
            enrollment_id=enrollment_id, org_id=org_id
        )
        if enrollment.status != EnrollmentStatus.ASSIGNED:
            raise ConflictError("Only assigned (not started) enrollments can be removed")
        await self.enrollment_repo.delete(enrollment)
