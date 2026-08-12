"""Business rules for the deliberately small course-folder feature."""

import uuid

from src.core.exceptions import ConflictError, NotFoundError
from src.models import CourseFolder
from src.repositories.course_folder_repo import CourseFolderRepository


class CourseFolderService:
    def __init__(self, repo: CourseFolderRepository) -> None:
        self.repo = repo

    async def list(self, org_id: uuid.UUID) -> list[tuple[CourseFolder, int]]:
        return list(await self.repo.list_with_counts(org_id))

    async def create(self, *, org_id: uuid.UUID, name: str) -> CourseFolder:
        if await self.repo.get_by_name(org_id, name):
            raise ConflictError("A folder with this name already exists", field="name")
        return await self.repo.create(org_id=org_id, name=name)

    async def update(
        self, *, org_id: uuid.UUID, folder_id: uuid.UUID, name: str
    ) -> CourseFolder:
        folder = await self.repo.get_scoped(folder_id, org_id)
        if folder is None:
            raise NotFoundError("course_folders", str(folder_id))
        duplicate = await self.repo.get_by_name(org_id, name)
        if duplicate is not None and duplicate.id != folder.id:
            raise ConflictError("A folder with this name already exists", field="name")
        return await self.repo.update(folder, name=name)

    async def delete(self, *, org_id: uuid.UUID, folder_id: uuid.UUID) -> None:
        folder = await self.repo.get_scoped(folder_id, org_id)
        if folder is None:
            raise NotFoundError("course_folders", str(folder_id))
        await self.repo.delete(folder)
