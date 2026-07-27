"""``llm_usage_log`` — one row per LLM call made by the v2 runtime (§3.5, §4.3).

This table exists to settle **one** open decision with data instead of a hypothesis: the
real fast/heavy ratio (§14.2 #1 assumes 90/10 and says so). It is written from a single
place, :func:`log_usage`, wrapped around the calls of the new nodes. v1 nodes are not
instrumented in this PR, on purpose — adding a write to a v1 code path is exactly the kind
of change a batch presented as additive should not make.

:func:`log_usage` **never raises**. Accounting that can break a learner's screen is worse
than accounting that occasionally loses a row.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models import USE_CASES, LlmUsageLog
from src.repositories.base import BaseRepository

logger = get_logger(__name__)


class LlmUsageRepository(BaseRepository[LlmUsageLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LlmUsageLog)

    async def record(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        use_case: str,
        purpose: str,
        model: str,
        tier: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        duration_ms: int | None = None,
        ok: bool = True,
    ) -> LlmUsageLog:
        """Append one call. Rejects an unknown ``use_case`` loudly.

        A typo in ``use_case`` produces rows nobody will ever query, which is worse than
        useless: it makes the ratio *look* measured while the denominator is wrong.
        """
        if use_case not in USE_CASES:
            raise ValueError(
                f"Unknown LLM use_case {use_case!r}; expected one of {USE_CASES}"
            )
        return await self.create(
            org_id=org_id,
            user_id=user_id,
            use_case=use_case,
            purpose=purpose,
            model=model,
            tier=tier,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            ok=ok,
        )

    async def tier_counts(self, *, org_id: uuid.UUID, use_case: str) -> dict[str, int]:
        """``{tier: calls}`` for one use case — the fast/heavy ratio of §14.2 #1."""
        query = (
            select(LlmUsageLog.tier, func.count())
            .where(LlmUsageLog.org_id == org_id, LlmUsageLog.use_case == use_case)
            .group_by(LlmUsageLog.tier)
        )
        rows = (await self.session.execute(query)).all()
        return {(tier or "unknown"): int(count) for tier, count in rows}

    async def list_recent(
        self, *, org_id: uuid.UUID, limit: int = 50
    ) -> Sequence[LlmUsageLog]:
        query = (
            select(LlmUsageLog)
            .where(LlmUsageLog.org_id == org_id)
            .order_by(LlmUsageLog.created_at.desc())
            .limit(limit)
        )
        return (await self.session.execute(query)).scalars().all()


async def log_usage(
    session_factory,
    *,
    org_id: uuid.UUID | str,
    user_id: uuid.UUID | str | None,
    use_case: str,
    purpose: str,
    model: str,
    tier: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    duration_ms: int | None = None,
    ok: bool = True,
) -> None:
    """The single writer. Opens its own session, commits, and swallows every failure.

    ``session_factory`` is injected rather than imported so a graph node can pass the same
    factory it was monkeypatched with, and so this stays callable from tests with no DB.
    """
    try:
        async with session_factory() as db:
            await LlmUsageRepository(db).record(
                org_id=_uuid(org_id),
                user_id=_uuid(user_id) if user_id else None,
                use_case=use_case,
                purpose=purpose,
                model=model,
                tier=tier,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                duration_ms=duration_ms,
                ok=ok,
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - accounting must never break a render
        logger.warning("Could not log LLM usage for %s: %s", use_case, exc)


def _uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


__all__ = ["LlmUsageRepository", "log_usage"]
