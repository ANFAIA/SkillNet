"""Persistence and PostgreSQL serialization for neutral experience attempts."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.learning_experience import (
    ExperienceAttempt,
    ExperienceIntent,
    ExperienceVariant,
    ImplementationBinding,
    NormalizedEvidence,
)


@dataclass(frozen=True, slots=True)
class ExperienceBindingChain:
    binding: ImplementationBinding
    variant: ExperienceVariant
    intent: ExperienceIntent


def _advisory_key(namespace: str, *parts: object) -> int:
    """Return a stable signed bigint accepted by PostgreSQL advisory locks."""

    raw = ":".join((namespace, *(str(part) for part in parts))).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big", signed=True)


class ExperienceAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_attempt(self, attempt_id: uuid.UUID) -> None:
        await self._lock(_advisory_key("experience-attempt", attempt_id))

    async def lock_learner_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> None:
        await self._lock(_advisory_key("learner-node", user_id, node_id))

    async def _lock(self, key: int) -> None:
        # Transaction-scoped locks disappear on commit *or rollback*. They serialize
        # retries even before the first insert exists, unlike SELECT FOR UPDATE.
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": key}
        )

    async def get_attempt(self, attempt_id: uuid.UUID) -> ExperienceAttempt | None:
        return await self.session.get(ExperienceAttempt, attempt_id)

    async def get_binding_chain(
        self, *, binding_id: uuid.UUID, org_id: uuid.UUID
    ) -> ExperienceBindingChain | None:
        query = (
            select(ImplementationBinding, ExperienceVariant, ExperienceIntent)
            .join(ExperienceVariant, ExperienceVariant.id == ImplementationBinding.variant_id)
            .join(ExperienceIntent, ExperienceIntent.id == ExperienceVariant.intent_id)
            .where(
                ImplementationBinding.id == binding_id,
                ImplementationBinding.org_id == org_id,
                ExperienceVariant.org_id == org_id,
                ExperienceIntent.org_id == org_id,
            )
        )
        row = (await self.session.execute(query)).one_or_none()
        if row is None:
            return None
        return ExperienceBindingChain(
            binding=row[0], variant=row[1], intent=row[2]
        )

    async def evidence_for_attempt(
        self, attempt_id: uuid.UUID
    ) -> Sequence[NormalizedEvidence]:
        query = (
            select(NormalizedEvidence)
            .where(NormalizedEvidence.attempt_id == attempt_id)
            .order_by(NormalizedEvidence.evidence_key)
        )
        return (await self.session.execute(query)).scalars().all()

    async def prior_failures(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> int:
        query = select(func.count()).select_from(ExperienceAttempt).where(
            ExperienceAttempt.user_id == user_id,
            ExperienceAttempt.node_id == node_id,
            ExperienceAttempt.passed.is_(False),
        )
        return int((await self.session.execute(query)).scalar_one())

    async def create_attempt(
        self,
        *,
        attempt: ExperienceAttempt,
        evidence: Sequence[NormalizedEvidence],
    ) -> None:
        self.session.add(attempt)
        self.session.add_all(evidence)
        await self.session.flush()


__all__ = ["ExperienceAttemptRepository", "ExperienceBindingChain"]
