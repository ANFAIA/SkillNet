"""Data access for the administrative audit trail (``audit_log``).

``record`` is the only writer. It rejects actions outside ``AUDIT_ACTIONS`` so a
typo becomes a loud failure at write time instead of an audit row nobody can query.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AUDIT_ACTIONS, AuditLog
from src.repositories.base import BaseRepository


def course_subject(course_id: uuid.UUID) -> str:
    return f"course:{course_id}"


def node_subject(node_id: uuid.UUID) -> str:
    return f"node:{node_id}"


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuditLog)

    async def record(
        self,
        *,
        org_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        action: str,
        subject: str,
        detail: dict | None = None,
    ) -> AuditLog:
        if action not in AUDIT_ACTIONS:
            raise ValueError(
                f"Unknown audit action {action!r}; expected one of {AUDIT_ACTIONS}"
            )
        return await self.create(
            org_id=org_id,
            actor_id=actor_id,
            action=action,
            subject=subject,
            detail=detail or {},
        )

    async def list_for_subject(
        self, *, org_id: uuid.UUID, subject: str, limit: int = 50
    ) -> Sequence[AuditLog]:
        query = (
            select(AuditLog)
            .where(AuditLog.org_id == org_id, AuditLog.subject == subject)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return (await self.session.execute(query)).scalars().all()
