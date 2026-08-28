"""Reclaim the renders a ``PROMPT_VERSION`` bump evicted, one bounded batch per boot.

``PROMPT_VERSION`` is part of the ``cache_key`` (§3.4), so bumping it invalidates every
cached render at once — that is the point, and it is cheap. What it is **not** is a
delete: the rows stay in ``node_renders``, each holding a ``ui_spec`` and a ``dialect``,
unreachable for the rest of the deployment's life because nothing will ever compute their
key again. ``adf53d8`` (``runtime/42`` → ``runtime/43``) did exactly that. Nobody should
have to open ``psql`` to finish the job, so the product finishes it itself.

**What gets deleted, and nothing else.** A row goes only when all three hold:

1. it is not a preview (``is_preview = false``). A preview key is salted per request or
   written by hand (``src/services/org_demo_seed.py`` pre-bakes demo renders with a key
   that never contained a prompt version at all), so "the prompt moved" proves nothing
   about whether it is still reachable;
2. its ``prompt_version`` differs from the one in force now — ``NULL`` included, which
   means "written by a build older than migration 0031";
3. **nothing references it**, checked against every foreign key in
   :data:`RENDER_REFERENCES`.

Condition 3 is the whole design. A plain ``DELETE`` would not be a cleanup, it would be a
loss of history, and the database would not complain once:
``node_render_views.render_id`` is ``ON DELETE CASCADE``, so the record of which learner
saw which screen would go with it; the other three are ``SET NULL``, so an attempt would
survive with no link to the screen it answered — and that link is the evidence behind a
mastery claim and behind a certificate. What is left after condition 3 is a screen that
was generated and that nobody ever opened.

The list in :data:`RENDER_REFERENCES` is the part that rots. The day a fifth table points
at ``node_renders`` and this file is not touched, the sweep starts deleting rows that are
in use, silently, because neither a ``SET NULL`` nor a ``CASCADE`` raises.
``tests/test_render_retention.py`` reads the real foreign keys off ``Base.metadata`` and
fails when one of them is not listed here — the same guard
``tests/test_gdpr_erasure.py`` puts on ``ERASURE_ORDER``.

One-time cost, stated plainly: on the first boot after 0031 every row is ``NULL`` and so
reads as stale. A render generated shortly before that deploy, under the version that is
still current, and never opened by anybody, is therefore swept and regenerated on next
demand. That costs money, never evidence — condition 3 still applies to it — and it
happens once, because everything written from 0031 onwards carries its version.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.logging import get_logger
from src.models import NodeRender
from src.models.base import Base
from src.services.node_render_service import current_prompt_version

logger = get_logger(__name__)


@dataclass(frozen=True)
class RenderReference:
    """One foreign key pointing at ``node_renders``, and what it costs to ignore it."""

    #: Referencing table, as it is named in the database.
    table: str
    #: Referencing column.
    column: str
    #: The ``ON DELETE`` action Postgres would take if the sweep deleted the row anyway.
    #: Recorded because it is what makes the damage silent, not because the sweep uses it.
    on_delete: str


#: Every foreign key into ``node_renders``. Written out by hand: this is the list the
#: sweep consults, and a fifth reference that is not here is a row deleted out from under
#: whoever needed it. ``tests/test_render_retention.py`` compares it against the real
#: schema and fails if the two disagree.
RENDER_REFERENCES: tuple[RenderReference, ...] = (
    # The audit trail of who saw what. CASCADE: it would be deleted, not orphaned.
    RenderReference("node_render_views", "render_id", "CASCADE"),
    # The learner's answers. SET NULL would leave the answer with no screen behind it.
    RenderReference("node_attempts", "render_id", "SET NULL"),
    # The screen a learner is pinned to right now (Vision A).
    RenderReference("learner_node_states", "active_render_id", "SET NULL"),
    # Provenance of an extracted activity.
    RenderReference("activity_definitions", "source_render_id", "SET NULL"),
)

#: Rows deleted per boot. Sized for the boot path, not for a one-shot cleanup: the API
#: restarts on every deploy and every ``docker compose restart``, so the queue drains over
#: a handful of them and no single boot pays for the whole backlog. 500 rows of
#: ``ui_spec`` + ``dialect`` is a few tens of MB of dead tuples — one ordinary autovacuum
#: pass — and a transaction short enough that a health check never notices it.
RETENTION_BATCH = 500

#: How far past the batch the candidate scan looks, purely so the log can say how much is
#: left without a second pass over the anti-joins. Saturating it reports a lower bound
#: instead of a count, which is honest and costs nothing.
_CANDIDATE_PROBE = RETENTION_BATCH * 10


@dataclass(frozen=True)
class RetentionReport:
    """What the sweep did. ``ran`` is false when it was switched off or it failed."""

    ran: bool
    deleted: int = 0
    #: Stale, unreferenced rows still waiting after this batch. A lower bound when
    #: :attr:`remaining_is_lower_bound` is set.
    remaining: int = 0
    remaining_is_lower_bound: bool = False
    #: Why it did not run. ``None`` when it did.
    skipped_reason: str | None = None


def _sweepable(prompt_version: str) -> tuple:
    """The three conditions, as SQL. Used for the scan *and* again for the delete."""
    clauses = [
        # A preview key is salted or hand-written, so the prompt version says nothing
        # about whether it can still be reached.
        NodeRender.is_preview.is_(False),
        # NULL is distinct from any version: no stamp means an older build wrote it.
        NodeRender.prompt_version.is_distinct_from(prompt_version),
    ]
    for reference in RENDER_REFERENCES:
        # Resolved through the metadata so the tuple above is the single place the
        # reference is spelled out; a wrong name raises here instead of silently
        # dropping a condition.
        column = Base.metadata.tables[reference.table].c[reference.column]
        clauses.append(~select(1).where(column == NodeRender.id).exists())
    return tuple(clauses)


async def sweep_evicted_renders(
    session: AsyncSession,
    *,
    prompt_version: str | None = None,
    batch: int = RETENTION_BATCH,
) -> RetentionReport:
    """Delete up to ``batch`` unreachable, unreferenced renders. Commits. Never raises.

    Never raises on purpose: this is an optional disk reclamation, and an optional
    cleanup that can stop the API from starting is worse than the disk it saves.
    """
    if not settings.RENDER_CACHE_SWEEP:
        logger.info(
            "Render cache sweep: off (RENDER_CACHE_SWEEP=false). Renders evicted by a "
            "PROMPT_VERSION bump stay in node_renders."
        )
        return RetentionReport(ran=False, skipped_reason="disabled")

    version = prompt_version or current_prompt_version()
    try:
        conditions = _sweepable(version)
        candidates = (
            await session.execute(
                # No ORDER BY: any stale row is as good as any other to remove, and
                # ordering would force the whole candidate set to be materialized and
                # sorted on every boot instead of stopping at the limit.
                select(NodeRender.id).where(*conditions).limit(_CANDIDATE_PROBE)
            )
        ).scalars().all()

        doomed = list(candidates[:batch])
        deleted = 0
        if doomed:
            # The conditions are repeated here rather than trusting the ids: at boot
            # nothing else is running (one worker, no requests served yet), but a sweep
            # that deletes by id alone would become wrong the day it is called elsewhere.
            result = await session.execute(
                delete(NodeRender).where(NodeRender.id.in_(doomed), *conditions)
            )
            deleted = int(result.rowcount or 0)
            await session.commit()

        remaining = len(candidates) - len(doomed)
        saturated = len(candidates) >= _CANDIDATE_PROBE
        report = RetentionReport(
            ran=True,
            deleted=deleted,
            remaining=remaining,
            remaining_is_lower_bound=saturated,
        )
    except Exception as exc:  # noqa: BLE001 - see the docstring: boot wins over disk
        await session.rollback()
        logger.error(
            "Render cache sweep failed (prompt version %s): %s. Nothing was deleted; "
            "the API is starting anyway.",
            version,
            exc,
            exc_info=exc,
        )
        return RetentionReport(ran=False, skipped_reason="error")

    if report.deleted:
        logger.warning(
            "Render cache sweep: deleted %s node_render(s) that no view, attempt, "
            "learner state or activity referenced and that no longer match prompt "
            "version %s. %s%s still waiting.",
            report.deleted,
            version,
            "at least " if report.remaining_is_lower_bound else "",
            report.remaining,
        )
    else:
        logger.info(
            "Render cache sweep: nothing to reclaim under prompt version %s.", version
        )
    return report


__all__ = [
    "RETENTION_BATCH",
    "RenderReference",
    "RENDER_REFERENCES",
    "RetentionReport",
    "sweep_evicted_renders",
]
