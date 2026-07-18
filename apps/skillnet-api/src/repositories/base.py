"""Generic async CRUD repository shared by every domain repository."""

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.exceptions import NotFoundError
from src.models.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """CRUD building block. Flushes (never commits); routes own the transaction."""

    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self.session = session
        self.model = model

    async def get_by_id(self, id: uuid.UUID) -> T | None:
        return await self.session.get(self.model, id)

    async def get_or_404(self, id: uuid.UUID) -> T:
        obj = await self.get_by_id(id)
        if obj is None:
            raise NotFoundError(self.model.__tablename__, str(id))
        return obj

    async def list(
        self,
        *,
        filters: list[ColumnElement[bool]] | None = None,
        order_by: Any = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[T], int]:
        query = select(self.model)
        count_query = select(func.count()).select_from(self.model)

        if filters:
            for f in filters:
                query = query.where(f)
                count_query = count_query.where(f)

        if order_by is not None:
            query = query.order_by(order_by)

        total = (await self.session.execute(count_query)).scalar_one()
        result = await self.session.execute(query.offset(offset).limit(limit))
        return result.scalars().all(), total

    async def create(self, **kwargs: Any) -> T:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj: T, **kwargs: Any) -> T:
        for key, value in kwargs.items():
            setattr(obj, key, value)
        await self.session.flush()
        return obj

    async def delete(self, obj: T) -> None:
        await self.session.delete(obj)
        await self.session.flush()
