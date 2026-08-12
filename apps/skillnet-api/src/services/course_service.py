"""Course lifecycle business logic: CRUD plus publish/archive/delete rules."""

import uuid
from datetime import datetime, timezone

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.models import ContentStatus, Course, EnrollmentStatus
from src.repositories.course_repo import CourseRepository
from src.repositories.course_folder_repo import CourseFolderRepository


class CourseService:
    def __init__(self, repo: CourseRepository) -> None:
        self.repo = repo

    async def create(
        self,
        *,
        org_id: uuid.UUID,
        created_by: uuid.UUID,
        title: str,
        description: str | None = None,
        outcome: str | None = None,
        source_document_id: uuid.UUID | None = None,
        folder_id: uuid.UUID | None = None,
    ) -> Course:
        if folder_id is not None:
            folder = await CourseFolderRepository(self.repo.session).get_scoped(
                folder_id, org_id
            )
            if folder is None:
                raise NotFoundError("course_folders", str(folder_id))
        return await self.repo.create(
            org_id=org_id,
            created_by=created_by,
            title=title,
            description=description,
            outcome=outcome,
            source_document_id=source_document_id,
            folder_id=folder_id,
            status=ContentStatus.DRAFT,
        )

    async def get_scoped(self, course_id: uuid.UUID, org_id: uuid.UUID) -> Course:
        course = await self.repo.get_scoped(course_id, org_id)
        if course is None:
            raise NotFoundError("courses", str(course_id))
        return course

    async def update(
        self, *, course_id: uuid.UUID, org_id: uuid.UUID, changes: dict
    ) -> Course:
        course = await self.get_scoped(course_id, org_id)
        if "folder_id" in changes and changes["folder_id"] is not None:
            folder_id = changes["folder_id"]
            folder = await CourseFolderRepository(self.repo.session).get_scoped(
                folder_id, org_id
            )
            if folder is None:
                raise NotFoundError("course_folders", str(folder_id))
        clean = {
            k: v
            for k, v in changes.items()
            if v is not None or k == "folder_id"
        }
        if not clean:
            return course
        return await self.repo.update(course, **clean)

    async def publish(self, *, course_id: uuid.UUID, org_id: uuid.UUID) -> Course:
        course = await self.repo.get_detail(course_id, org_id)
        if course is None:
            raise NotFoundError("courses", str(course_id))
        if not course.title:
            raise ValidationError("A title is required to publish", field="title")
        if not course.outcome:
            raise ValidationError("An outcome is required to publish", field="outcome")
        has_lesson = any(module.lessons for module in course.modules)
        if not course.modules or not has_lesson:
            raise ValidationError(
                "A course needs at least one module with one lesson to publish"
            )
        return await self.repo.update(course, status=ContentStatus.PUBLISHED)

    async def archive(self, *, course_id: uuid.UUID, org_id: uuid.UUID) -> Course:
        course = await self.repo.get_with_enrollments(course_id, org_id)
        if course is None:
            raise NotFoundError("courses", str(course_id))
        now = datetime.now(timezone.utc)
        for enrollment in course.enrollments:
            if enrollment.status != EnrollmentStatus.COMPLETED:
                enrollment.status = EnrollmentStatus.COMPLETED
                enrollment.completed_at = now
        return await self.repo.update(course, status=ContentStatus.ARCHIVED)

    async def delete(self, *, course_id: uuid.UUID, org_id: uuid.UUID) -> None:
        course = await self.repo.get_with_enrollments(course_id, org_id)
        if course is None:
            raise NotFoundError("courses", str(course_id))
        if course.status != ContentStatus.DRAFT:
            raise ConflictError("Only draft courses can be deleted")
        if course.enrollments:
            raise ConflictError("Cannot delete a course that has enrollments")
        await self.repo.delete(course)
