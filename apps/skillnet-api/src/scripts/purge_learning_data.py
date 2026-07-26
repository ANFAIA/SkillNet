"""Retention purge for v2 learning data.

    python -m src.scripts.purge_learning_data [--dry-run]

There is no ``background_jobs`` table and no worker in this PR (§1.3), so retention
is a CLI script: run it by hand or from a host cron entry. It is idempotent and
safe to run repeatedly.

Windows: ``asyncpg`` needs the selector event loop policy, which
``asyncio.run`` gives by default on Python 3.12.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from src.core.logging import configure_logging, get_logger
from src.deps.db import async_session_factory, engine
from src.models import LearningEvent, TermExplanation

logger = get_logger(__name__)

# Retention windows fixed by §3.3.
LEARNING_EVENTS_RETENTION_DAYS = 90
TERM_EXPLANATIONS_RETENTION_DAYS = 180


def _cutoff(days: int, *, now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) - timedelta(days=days)


async def purge(*, dry_run: bool = False) -> dict[str, int]:
    """Delete expired rows. Returns ``{table: rows}`` (rows that *would* go when
    ``dry_run``)."""
    events_cutoff = _cutoff(LEARNING_EVENTS_RETENTION_DAYS)
    terms_cutoff = _cutoff(TERM_EXPLANATIONS_RETENTION_DAYS)
    counts: dict[str, int] = {}

    async with async_session_factory() as session:
        if dry_run:
            counts["learning_events"] = (
                await session.execute(
                    select(func.count())
                    .select_from(LearningEvent)
                    .where(LearningEvent.created_at < events_cutoff)
                )
            ).scalar_one()
            counts["term_explanations"] = (
                await session.execute(
                    select(func.count())
                    .select_from(TermExplanation)
                    .where(TermExplanation.last_used_at < terms_cutoff)
                )
            ).scalar_one()
        else:
            events = await session.execute(
                delete(LearningEvent).where(LearningEvent.created_at < events_cutoff)
            )
            terms = await session.execute(
                delete(TermExplanation).where(
                    TermExplanation.last_used_at < terms_cutoff
                )
            )
            counts["learning_events"] = events.rowcount or 0
            counts["term_explanations"] = terms.rowcount or 0
            await session.commit()

    return counts


async def _main(dry_run: bool) -> None:
    try:
        counts = await purge(dry_run=dry_run)
    finally:
        await engine.dispose()
    verb = "would delete" if dry_run else "deleted"
    logger.info(
        "purge_learning_data: %s %d learning_events (>%dd) and %d term_explanations (>%dd)",
        verb,
        counts["learning_events"],
        LEARNING_EVENTS_RETENTION_DAYS,
        counts["term_explanations"],
        TERM_EXPLANATIONS_RETENTION_DAYS,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count expired rows without deleting anything.",
    )
    args = parser.parse_args()
    configure_logging("INFO")
    asyncio.run(_main(args.dry_run))


if __name__ == "__main__":
    main()
