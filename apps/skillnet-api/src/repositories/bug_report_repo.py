"""Data access for ``bug_reports``."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import BugReport
from src.repositories.base import BaseRepository


class BugReportRepository(BaseRepository[BugReport]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BugReport)

    async def count_since(self, user_id: uuid.UUID, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(BugReport)
            .where(BugReport.user_id == user_id, BugReport.created_at >= since)
        )
        return int(result.scalar_one())

    async def count_for_issue(self, issue_url: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(BugReport)
            .where(BugReport.issue_url == issue_url)
        )
        return int(result.scalar_one())

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 50
    ) -> Sequence[BugReport]:
        result = await self.session.execute(
            select(BugReport)
            .where(BugReport.user_id == user_id)
            .order_by(BugReport.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def list_for_org(
        self, org_id: uuid.UUID, *, limit: int = 200
    ) -> Sequence[BugReport]:
        result = await self.session.execute(
            select(BugReport)
            .where(BugReport.org_id == org_id)
            .order_by(BugReport.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
