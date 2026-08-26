"""Course lifecycle business logic: CRUD plus publish/archive/delete rules."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.models import (
    ArtifactGeneratePolicy,
    ContentStatus,
    Course,
    CourseTutorStyle,
    EnrollmentStatus,
    User,
)
from src.repositories.course_repo import CourseRepository
from src.repositories.course_folder_repo import CourseFolderRepository
from src.repositories.media_artifact_repo import MediaArtifactRepository
from src.services.course_delivery import resolve_delivery

logger = get_logger(__name__)


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
        generator_ids = changes.pop("artifact_generator_ids", None)
        raw_policy = changes.get("artifact_generate_policy")
        if raw_policy is not None:
            try:
                changes["artifact_generate_policy"] = ArtifactGeneratePolicy(raw_policy)
            except ValueError as exc:
                raise ValidationError(
                    "Invalid artifact generate policy",
                    field="artifact_generate_policy",
                ) from exc
        raw_tutor_style = changes.get("tutor_style")
        if raw_tutor_style is not None:
            try:
                changes["tutor_style"] = CourseTutorStyle(raw_tutor_style)
            except ValueError as exc:
                raise ValidationError(
                    "Invalid tutor style", field="tutor_style"
                ) from exc
        clean = {
            k: v
            for k, v in changes.items()
            if v is not None or k == "folder_id"
        }
        if clean:
            course = await self.repo.update(course, **clean)
        policy = course.artifact_generate_policy
        policy_changed = raw_policy is not None
        if generator_ids is not None or (
            policy_changed and policy != ArtifactGeneratePolicy.SELECTED
        ):
            ids = (
                []
                if policy != ArtifactGeneratePolicy.SELECTED
                else list(generator_ids or [])
            )
            if ids:
                unique = list(dict.fromkeys(ids))
                counted = (
                    await self.repo.session.execute(
                        select(func.count())
                        .select_from(User)
                        .where(User.id.in_(unique), User.org_id == org_id)
                    )
                ).scalar_one()
                if counted != len(unique):
                    raise ValidationError(
                        "One or more users are not in this organization",
                        field="artifact_generator_ids",
                    )
                ids = unique
            await self.repo.replace_artifact_generators(course.id, ids)
        return course

    async def publish(self, *, course_id: uuid.UUID, org_id: uuid.UUID) -> Course:
        course = await self.repo.get_detail(course_id, org_id)
        if course is None:
            raise NotFoundError("courses", str(course_id))
        if not course.title:
            raise ValidationError("A title is required to publish", field="title")
        if not course.outcome:
            raise ValidationError("An outcome is required to publish", field="outcome")
        if resolve_delivery(course) == "dynamic":
            if await self.repo.count_active_nodes(course.id) < 1:
                raise ValidationError("A course needs at least one node to publish")
        else:
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

        media = MediaArtifactRepository(self.repo.session)
        # Read the paths first: the rows cascade away with the course, and afterwards
        # there is nothing left to say which files were theirs.
        asset_paths = await media.list_asset_paths_for_course(course.id)
        try:
            await self.repo.delete(course)
        except IntegrityError as exc:
            # Something still points at this course with a restrictive foreign key.
            # A 500 here is what made a failed draft undeletable; a conflict at least
            # tells the admin what to do about it.
            raise ConflictError(
                "This course is still referenced by other records and cannot be "
                "deleted. Archive it instead."
            ) from exc
        await self._remove_orphan_assets(media, course_id, asset_paths)

    @staticmethod
    async def _remove_orphan_assets(
        media: MediaArtifactRepository, course_id: uuid.UUID, paths: list[str]
    ) -> None:
        """Delete the media files of the artifacts that just cascaded away.

        Best-effort and never fatal: the rows are already gone, so a file that cannot be
        removed is a stray byte on disk, not a failed delete. Paths another artifact
        still points at are left alone — the asset store dedups by content hash, so one
        file can serve several artifacts.
        """
        if not paths:
            return
        try:
            still_used = await media.paths_still_referenced(paths)
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            logger.warning(
                "Could not check media assets of deleted course %s: %s", course_id, exc
            )
            return
        for path in paths:
            if path in still_used:
                continue
            try:
                Path(path).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(
                    "Could not remove media asset %s of deleted course %s: %s",
                    path,
                    course_id,
                    exc,
                )
