"""Snapshot-safe storage for prepared per-node learning dossiers.

The repository does not know how a pack is generated. Its job is narrower: preserve
immutable snapshots and make terminal writes conditional on the snapshot that was claimed.
An old worker can finish, but it cannot revive a row made ``stale`` by a newer source.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import NodeKnowledgePackRecord, NodeKnowledgePackStatus
from src.repositories.base import BaseRepository


class NodeKnowledgePackRepository(BaseRepository[NodeKnowledgePackRecord]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NodeKnowledgePackRecord)

    async def get_snapshot(
        self,
        *,
        node_id: uuid.UUID,
        source_fingerprint: str,
        generator_version: str,
    ) -> NodeKnowledgePackRecord | None:
        query = select(NodeKnowledgePackRecord).where(
            NodeKnowledgePackRecord.node_id == node_id,
            NodeKnowledgePackRecord.source_fingerprint == source_fingerprint,
            NodeKnowledgePackRecord.generator_version == generator_version,
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def find_ready(
        self,
        *,
        node_id: uuid.UUID,
        source_fingerprint: str,
        generator_version: str,
    ) -> NodeKnowledgePackRecord | None:
        query = select(NodeKnowledgePackRecord).where(
            NodeKnowledgePackRecord.node_id == node_id,
            NodeKnowledgePackRecord.source_fingerprint == source_fingerprint,
            NodeKnowledgePackRecord.generator_version == generator_version,
            NodeKnowledgePackRecord.status == NodeKnowledgePackStatus.READY,
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def latest_for_schema(
        self,
        *,
        course_id: uuid.UUID,
        org_id: uuid.UUID,
        schema_version: int,
    ) -> list[NodeKnowledgePackRecord]:
        """Latest visible snapshot per node for the schema-details surface."""
        query = (
            select(NodeKnowledgePackRecord)
            .where(
                NodeKnowledgePackRecord.course_id == course_id,
                NodeKnowledgePackRecord.org_id == org_id,
                NodeKnowledgePackRecord.schema_version == schema_version,
            )
            .order_by(
                NodeKnowledgePackRecord.node_id,
                NodeKnowledgePackRecord.created_at.desc(),
            )
        )
        rows = (await self.session.execute(query)).scalars().all()
        latest: dict[uuid.UUID, NodeKnowledgePackRecord] = {}
        for row in rows:
            latest.setdefault(row.node_id, row)
        return list(latest.values())

    async def find_ready_for_schema(
        self,
        *,
        node_id: uuid.UUID,
        schema_version: int,
        generator_version: str,
    ) -> NodeKnowledgePackRecord | None:
        query = (
            select(NodeKnowledgePackRecord)
            .where(
                NodeKnowledgePackRecord.node_id == node_id,
                NodeKnowledgePackRecord.schema_version == schema_version,
                NodeKnowledgePackRecord.generator_version == generator_version,
                NodeKnowledgePackRecord.status == NodeKnowledgePackStatus.READY,
            )
            .order_by(NodeKnowledgePackRecord.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def claim_snapshot(
        self,
        *,
        org_id: uuid.UUID,
        course_id: uuid.UUID,
        node_id: uuid.UUID,
        source_fingerprint: str,
        schema_version: int,
        generator_version: str,
    ) -> NodeKnowledgePackRecord:
        """Return the current snapshot row, queued when no completed snapshot exists."""
        existing = await self.get_snapshot(
            node_id=node_id,
            source_fingerprint=source_fingerprint,
            generator_version=generator_version,
        )
        await self.mark_other_snapshots_stale(
            node_id=node_id,
            source_fingerprint=source_fingerprint,
            generator_version=generator_version,
        )
        if existing is not None:
            if existing.status not in (
                NodeKnowledgePackStatus.READY,
                NodeKnowledgePackStatus.REVIEW_REQUIRED,
            ):
                existing.status = NodeKnowledgePackStatus.PENDING
                existing.schema_version = schema_version
                existing.error_message = None
                await self.session.flush()
            return existing

        try:
            # A harmless unique-key race must not roll back the caller's transaction.
            async with self.session.begin_nested():
                record = NodeKnowledgePackRecord(
                    org_id=org_id,
                    course_id=course_id,
                    node_id=node_id,
                    source_fingerprint=source_fingerprint,
                    schema_version=schema_version,
                    generator_version=generator_version,
                    status=NodeKnowledgePackStatus.PENDING,
                )
                self.session.add(record)
                await self.session.flush()
            return record
        except IntegrityError:
            adopted = await self.get_snapshot(
                node_id=node_id,
                source_fingerprint=source_fingerprint,
                generator_version=generator_version,
            )
            if adopted is None:  # pragma: no cover - protected by the unique constraint
                raise
            return adopted

    async def mark_other_snapshots_stale(
        self,
        *,
        node_id: uuid.UUID,
        source_fingerprint: str,
        generator_version: str,
    ) -> int:
        """Retire older pending/ready snapshots without erasing their audit history."""
        result = await self.session.execute(
            update(NodeKnowledgePackRecord)
            .where(
                NodeKnowledgePackRecord.node_id == node_id,
                ~(
                    (NodeKnowledgePackRecord.source_fingerprint == source_fingerprint)
                    & (NodeKnowledgePackRecord.generator_version == generator_version)
                ),
                NodeKnowledgePackRecord.status.in_(
                    [
                        NodeKnowledgePackStatus.PENDING,
                        NodeKnowledgePackStatus.READY,
                        NodeKnowledgePackStatus.REVIEW_REQUIRED,
                    ]
                ),
            )
            .values(status=NodeKnowledgePackStatus.STALE)
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def mark_completed_if_claimed(
        self,
        record_id: uuid.UUID,
        *,
        source_fingerprint: str,
        generator_version: str,
        markdown: str,
        pack_payload: dict,
        pack_hash: str,
        atoms: list,
        provenance: dict,
        markdown_hash: str,
        atoms_hash: str,
        input_tokens: int | None,
        output_tokens: int | None,
        duration_ms: int | None,
        status: NodeKnowledgePackStatus,
    ) -> NodeKnowledgePackRecord | None:
        """Publish a valid terminal payload only for the snapshot originally claimed."""
        if status not in (
            NodeKnowledgePackStatus.READY,
            NodeKnowledgePackStatus.REVIEW_REQUIRED,
        ):
            raise ValueError("completed pack status must be ready or review_required")
        result = await self.session.execute(
            update(NodeKnowledgePackRecord)
            .where(
                NodeKnowledgePackRecord.id == record_id,
                NodeKnowledgePackRecord.source_fingerprint == source_fingerprint,
                NodeKnowledgePackRecord.generator_version == generator_version,
                NodeKnowledgePackRecord.status == NodeKnowledgePackStatus.PENDING,
            )
            .values(
                status=status,
                markdown=markdown,
                pack_payload=pack_payload,
                pack_hash=pack_hash,
                atoms=atoms,
                provenance=provenance,
                markdown_hash=markdown_hash,
                atoms_hash=atoms_hash,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                error_message=None,
            )
            .returning(NodeKnowledgePackRecord)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def mark_failed_if_claimed(
        self,
        record_id: uuid.UUID,
        *,
        source_fingerprint: str,
        generator_version: str,
        error_message: str,
    ) -> NodeKnowledgePackRecord | None:
        """Fail only the still-current pending snapshot; a stale worker stays stale."""
        result = await self.session.execute(
            update(NodeKnowledgePackRecord)
            .where(
                NodeKnowledgePackRecord.id == record_id,
                NodeKnowledgePackRecord.source_fingerprint == source_fingerprint,
                NodeKnowledgePackRecord.generator_version == generator_version,
                NodeKnowledgePackRecord.status == NodeKnowledgePackStatus.PENDING,
            )
            .values(status=NodeKnowledgePackStatus.FAILED, error_message=error_message[:2000])
            .returning(NodeKnowledgePackRecord)
        )
        await self.session.flush()
        return result.scalar_one_or_none()


__all__ = ["NodeKnowledgePackRepository"]
