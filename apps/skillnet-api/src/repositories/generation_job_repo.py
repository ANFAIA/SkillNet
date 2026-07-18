"""Generation job data access."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import GenerationJob
from src.repositories.base import BaseRepository


class GenerationJobRepository(BaseRepository[GenerationJob]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GenerationJob)

    async def get_scoped(
        self, id: uuid.UUID, org_id: uuid.UUID
    ) -> GenerationJob | None:
        job = await self.get_by_id(id)
        if job is None or job.org_id != org_id:
            return None
        return job
