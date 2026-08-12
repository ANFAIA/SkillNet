"""Queries for rich activity definitions and learner state."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.activity_definition import ActivityDefinition, ActivityState
from src.repositories.base import BaseRepository


class ActivityDefinitionRepository(BaseRepository[ActivityDefinition]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ActivityDefinition)

    async def get_scoped(self, activity_id: uuid.UUID, org_id: uuid.UUID) -> ActivityDefinition | None:
        query = select(ActivityDefinition).where(ActivityDefinition.id == activity_id, ActivityDefinition.org_id == org_id)
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_version(
        self, *, org_id: uuid.UUID, definition_key: str, version: int
    ) -> ActivityDefinition | None:
        query = select(ActivityDefinition).where(
            ActivityDefinition.org_id == org_id,
            ActivityDefinition.definition_key == definition_key,
            ActivityDefinition.version == version,
        )
        return (await self.session.execute(query)).scalar_one_or_none()


class ActivityStateRepository(BaseRepository[ActivityState]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ActivityState)

    async def get_for_learner(self, activity_id: uuid.UUID, user_id: uuid.UUID) -> ActivityState | None:
        query = select(ActivityState).where(ActivityState.activity_id == activity_id, ActivityState.user_id == user_id)
        return (await self.session.execute(query)).scalar_one_or_none()

    async def save(self, *, activity: ActivityDefinition, user_id: uuid.UUID, state: dict) -> ActivityState:
        current = await self.get_for_learner(activity.id, user_id)
        if current is None:
            return await self.create(org_id=activity.org_id, activity_id=activity.id, user_id=user_id, state=state)
        return await self.update(current, state=state)
