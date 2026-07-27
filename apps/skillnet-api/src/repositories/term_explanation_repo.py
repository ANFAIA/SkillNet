"""Cache lookups for click-to-explain (§3.4, §8.4).

The key is ``(org_id, term_normalized, context_hash, language)`` — the ``context_hash``
is **not** optional: "Mercurio" in a chemistry node and "Mercurio" next to "planeta"
must not share a row. Omitting it is the design bug of the reference implementation.

The row has no ``user_id``, which is why only short terms are ever written: see
``explain_service.is_cacheable``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import TermExplanation
from src.repositories.base import BaseRepository


class TermExplanationRepository(BaseRepository[TermExplanation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TermExplanation)

    async def find(
        self,
        *,
        org_id: uuid.UUID,
        term_normalized: str,
        context_hash: str,
        language: str,
    ) -> TermExplanation | None:
        """The exact-key lookup backed by ``idx_term_expl_lookup``."""
        result = await self.session.execute(
            select(TermExplanation).where(
                TermExplanation.org_id == org_id,
                TermExplanation.term_normalized == term_normalized,
                TermExplanation.context_hash == context_hash,
                TermExplanation.language == language,
            )
        )
        return result.scalar_one_or_none()

    async def touch(self, row: TermExplanation) -> TermExplanation:
        """Register a cache hit: ``hit_count += 1`` and ``last_used_at = now()``.

        ``last_used_at`` drives the 180-day purge (``idx_term_expl_purge``), so a term
        that keeps being asked about keeps being kept.
        """
        row.hit_count = (row.hit_count or 0) + 1
        row.last_used_at = datetime.now(UTC)
        await self.session.flush()
        return row

    async def record(
        self,
        *,
        org_id: uuid.UUID,
        node_id: uuid.UUID | None,
        term: str,
        term_normalized: str,
        context_hash: str,
        language: str,
        explanation: str,
        model: str,
    ) -> TermExplanation:
        """Insert a fresh explanation, or refresh the row a concurrent request won.

        Two learners can miss the cache on the same term at the same time; the unique
        constraint would then reject the second insert. Re-checking inside the same
        transaction turns that race into a plain hit instead of a 500 at the end of an
        otherwise successful stream.
        """
        existing = await self.find(
            org_id=org_id,
            term_normalized=term_normalized,
            context_hash=context_hash,
            language=language,
        )
        if existing is not None:
            return await self.touch(existing)
        return await self.create(
            org_id=org_id,
            node_id=node_id,
            term=term,
            term_normalized=term_normalized,
            context_hash=context_hash,
            language=language,
            explanation=explanation,
            model=model,
        )
