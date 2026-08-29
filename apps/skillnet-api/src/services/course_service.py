"""Course lifecycle business logic: CRUD plus publish/archive/delete rules."""

import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.models import (
    ArtifactGeneratePolicy,
    ContentStatus,
    Course,
    CourseImageSourcePolicy,
    CourseNavigationMode,
    CourseTutorStyle,
    User,
)
from src.repositories.audit_log_repo import AuditLogRepository, course_subject
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
        moving_folder = "folder_id" in changes
        new_folder = None
        if moving_folder and changes["folder_id"] is not None:
            folder_id = changes["folder_id"]
            new_folder = await CourseFolderRepository(self.repo.session).get_scoped(
                folder_id, org_id
            )
            if new_folder is None:
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
        raw_navigation = changes.get("navigation_mode")
        if raw_navigation is not None:
            try:
                changes["navigation_mode"] = CourseNavigationMode(raw_navigation)
            except ValueError as exc:
                raise ValidationError(
                    "Invalid navigation mode", field="navigation_mode"
                ) from exc
        raw_image_policy = changes.get("image_source_policy")
        if raw_image_policy is not None:
            try:
                changes["image_source_policy"] = CourseImageSourcePolicy(
                    raw_image_policy
                )
            except ValueError as exc:
                raise ValidationError(
                    "Invalid image source policy", field="image_source_policy"
                ) from exc
        clean = {k: v for k, v in changes.items() if v is not None}
        if moving_folder:
            # Write the *relationship*, not only the column. The route projects the
            # course it gets back here, and `folder_name` comes from `course.folder`;
            # assigning `folder_id` alone leaves an already-loaded `folder` pointing at
            # the previous row, so the response carried the new id next to the old name
            # (or `null`). Assigning the object — the very one already fetched to
            # validate the move — keeps both in step: SQLAlchemy syncs the column from
            # the relationship on flush. `None` is a legal value here (unfile the
            # course), which is why it is set explicitly and not filtered out above.
            clean.pop("folder_id", None)
            clean["folder"] = new_folder
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
        """Take a published course out of circulation. 409 for any other status.

        Two things this deliberately does **not** do:

        - It does not touch the enrollments. It used to close every open one as
          ``COMPLETED`` with a ``completed_at`` of "now", which turned a learner who was
          halfway through into a learner who finished — credit included — and could not
          be undone, because nothing recorded what the row said before. Archiving hides
          a course; it does not grade anyone. Leaving the rows alone is also what makes
          :meth:`unarchive` lossless: the progress is still there, exactly as it was.
        - It does not accept a ``draft``. Archiving a draft means nothing (a draft is
          already invisible to learners) and it is what made the way back a guess: with
          ``published`` as the only archivable status, ``published`` is also the status
          to restore. The admin UI only ever offered the button for a published course;
          this closes the same hole in the API.
        """
        course = await self.get_scoped(course_id, org_id)
        if course.status != ContentStatus.PUBLISHED:
            raise ConflictError(
                "Only published courses can be archived", field="status"
            )
        return await self.repo.update(course, status=ContentStatus.ARCHIVED)

    async def unarchive(self, *, course_id: uuid.UUID, org_id: uuid.UUID) -> Course:
        """Bring an archived course back to ``published``. 409 if it was not archived.

        ``published`` and not ``draft``: :meth:`archive` only accepts a published course,
        so ``published`` is the previous status with certainty — there is nothing to
        record and nothing to guess. Returning it as a draft was the old answer to a
        question that no longer exists, and it had a cost: the course stayed invisible to
        the learners who were part-way through it until an admin noticed it needed a
        second publish.

        The publish checks are re-run rather than skipped. The course passed them once,
        but that was before it was archived, and an archived course is not frozen — its
        schema can still be edited (``course_schema_service`` keeps an archived course
        archived precisely so that editing is possible), which means its last active node
        or lesson can be gone by now. Since unarchiving publishes, it has to answer the
        same question publishing answers: is there anything to deliver? The reuse also
        keeps a single definition of "publishable" instead of a second, laxer one here.

        Enrollments are untouched, and there is nothing to repair: archiving no longer
        changes them, so every learner comes back exactly where they were.
        """
        course = await self.get_scoped(course_id, org_id)
        if course.status != ContentStatus.ARCHIVED:
            raise ConflictError(
                "Only archived courses can be unarchived", field="status"
            )
        return await self.publish(course_id=course_id, org_id=org_id)

    async def delete(
        self,
        *,
        course_id: uuid.UUID,
        org_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Remove a course, whatever its status and whoever is enrolled in it.

        This used to refuse anything that was not an empty draft. The refusal was not a
        safety property, only an obstacle: an admin who wants a published course gone
        archives it, finds it still there, and ends up asking somebody with database
        access. Every other tool in this category lets you delete your own content.

        The safeguard is no longer a prohibition, it is a record. What disappears here
        is other people's training history — ``enrollments.course_id`` cascades since
        migration 0032 — so before the row goes, an ``audit_log`` entry says who removed
        what, when, in which status, and how many enrollments (and how many completed
        ones) went with it. That row is all that is left of the accountability once the
        data is gone, which is why it is written in the same transaction as the delete.

        The caller is expected to have warned in proportion: the library shows the exact
        numbers and asks for the title to be typed back when completed enrollments are
        involved.
        """
        course = await self.get_scoped(course_id, org_id)
        deleted_title = course.title
        deleted_status = course.status.value
        # Counted before the delete, for the same reason the asset paths are read
        # before it: afterwards nothing can say how much there was.
        enrollment_count, completed_count = await self.repo.count_enrollments(course_id)

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
        await AuditLogRepository(self.repo.session).record(
            org_id=org_id,
            actor_id=actor_id,
            action="course_deleted",
            subject=course_subject(course_id),
            detail={
                "title": deleted_title,
                "status": deleted_status,
                "enrollment_count": enrollment_count,
                "completed_enrollment_count": completed_count,
            },
        )
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
