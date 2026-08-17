"""Background, snapshot-safe generation of prepared node knowledge packs.

The runner is deliberately outside both schema persistence and learner delivery.  A
schema can finish and be published while its packs are prepared in the background;
an unavailable model, a malformed output, or one bad node must therefore never make
the course unavailable.

Every database phase opens its own session.  In particular, no transaction is held
while waiting for an LLM.  The record service's conditional terminal writes make a
late worker harmless when the node source has changed in the meantime.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Protocol

from sqlalchemy import select

from src.agents.runtime.nodes import load_source_context
from src.core.logging import get_logger
from src.core.tasks import task_registry
from src.deps.db import async_session_factory
from src.knowledge_pack.configured_generator import GENERATOR_VERSION
from src.knowledge_pack.node_source import seed_node_source
from src.models import Course, CourseNode, NodeKnowledgePackStatus
from src.repositories.node_knowledge_pack_repo import NodeKnowledgePackRepository
from src.services.node_knowledge_pack_service import (
    CompletedKnowledgePack,
    KnowledgePackSnapshot,
    NodeKnowledgePackService,
)

logger = get_logger(__name__)

DEFAULT_CONCURRENCY = 5
# A pack is up to three LLM calls (extract, review, coverage-repair). Under a throttled
# provider each carries its own rate-limit backoff, so the per-node ceiling has to cover
# all three plus their waits — 120s timed the third call out on the free tier.
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_GENERATOR_VERSION = GENERATOR_VERSION


class KnowledgePackGenerator(Protocol):
    """The small seam between this background runner and an LLM-backed generator."""

    async def generate(
        self,
        *,
        course: Course,
        node: CourseNode,
        source_context: str,
        snapshot: KnowledgePackSnapshot,
    ) -> CompletedKnowledgePack: ...


SessionFactory = Callable[[], Any]
CourseLoader = Callable[[Any, uuid.UUID], Awaitable[Course | None]]
NodesLoader = Callable[[Any, uuid.UUID, uuid.UUID], Awaitable[Sequence[CourseNode]]]
SourceLoader = Callable[[Any, CourseNode, uuid.UUID], Awaitable[str]]
ServiceFactory = Callable[[Any], NodeKnowledgePackService]
SourceDrafter = Callable[..., Awaitable[str]]
SourcePersister = Callable[[Any, CourseNode, str, Course], Awaitable[None]]


async def _load_course(db: Any, course_id: uuid.UUID) -> Course | None:
    return await db.get(Course, course_id)


async def _load_nodes(
    db: Any, course_id: uuid.UUID, org_id: uuid.UUID
) -> Sequence[CourseNode]:
    result = await db.execute(
        select(CourseNode)
        .where(
            CourseNode.course_id == course_id,
            CourseNode.org_id == org_id,
            CourseNode.archived.is_(False),
        )
        .order_by(CourseNode.position)
    )
    return tuple(result.scalars().all())


def _service_for_session(db: Any) -> NodeKnowledgePackService:
    return NodeKnowledgePackService(NodeKnowledgePackRepository(db))


@dataclass(frozen=True)
class KnowledgePackRunnerDependencies:
    """Injectable I/O boundary; unit tests need neither Postgres nor a model."""

    generator: KnowledgePackGenerator
    session_factory: SessionFactory = async_session_factory
    load_course: CourseLoader = _load_course
    load_nodes: NodesLoader = _load_nodes
    load_source: SourceLoader = load_source_context
    service_for_session: ServiceFactory = _service_for_session
    draft_source: SourceDrafter | None = None
    persist_source: SourcePersister | None = None
    generator_version: str = DEFAULT_GENERATOR_VERSION
    concurrency: int = DEFAULT_CONCURRENCY
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    # Bounded automatic retry of a node that did not reach ``ready``. Defaults to one
    # attempt so existing callers and unit fixtures keep their exact single-shot
    # behaviour; the production wiring in ``routes/course_schema.py`` raises it so a
    # transient provider error, a lost snapshot race, or a repairable review_required
    # pack is retried instead of being left as a permanent "surprise" on the course.
    max_attempts: int = 1
    retry_backoff_seconds: float = 2.0

    def __post_init__(self) -> None:
        if not self.generator_version.strip():
            raise ValueError("generator_version is required")
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least one")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")


@dataclass(frozen=True)
class NodePackRunResult:
    node_id: uuid.UUID
    outcome: str
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class KnowledgePackRunMetrics:
    course_id: uuid.UUID
    org_id: uuid.UUID
    schema_version: int
    results: tuple[NodePackRunResult, ...]
    duration_ms: int

    @property
    def ready(self) -> int:
        return sum(result.outcome == "ready" for result in self.results)

    @property
    def skipped(self) -> int:
        return sum(result.outcome == "skipped" for result in self.results)

    @property
    def stale(self) -> int:
        return sum(result.outcome == "stale" for result in self.results)

    @property
    def failed(self) -> int:
        return sum(result.outcome == "failed" for result in self.results)

    @property
    def review_required(self) -> int:
        return sum(result.outcome == "review_required" for result in self.results)

    @property
    def input_tokens(self) -> int:
        return sum(result.input_tokens or 0 for result in self.results)

    @property
    def output_tokens(self) -> int:
        return sum(result.output_tokens or 0 for result in self.results)


def source_fingerprint(
    *, node: CourseNode, source_context: str, schema_version: int
) -> str:
    """Stable identity of the exact source material a worker is allowed to publish.

    The source text is included by digest, never emitted to logs or stored redundantly.
    Node metadata is deliberately selected field-by-field so unrelated ORM state and
    relationship loading cannot make a snapshot vary between processes.
    """

    value = {
        "schema_version": schema_version,
        "node": {
            "id": str(node.id),
            "title": node.title,
            "summary": node.summary,
            "outcome": node.outcome,
            "criticality": getattr(node.criticality, "value", str(node.criticality)),
            "position": node.position,
            "source_document_id": str(node.source_document_id or ""),
            "source_headings": list(node.source_headings or ()),
            "mastery_threshold": node.mastery_threshold,
            "default_ui_format": getattr(
                node.default_ui_format, "value", str(node.default_ui_format)
            ),
        },
        "source_context_sha256": hashlib.sha256(
            source_context.encode("utf-8")
        ).hexdigest(),
    }
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def run_packs_for_schema(
    course_id: str | uuid.UUID,
    org_id: str | uuid.UUID,
    schema_version: int,
    *,
    dependencies: KnowledgePackRunnerDependencies,
) -> KnowledgePackRunMetrics:
    """Prepare packs for one already-persisted course schema in the background.

    ``dependencies`` is intentionally required for now: this makes model selection
    explicit at the call site and prevents a new hidden provider path.  Wiring a default
    configured generator is a later integration step, not a prerequisite for proving the
    runner with fixture or benchmark generators.
    """

    cid = _as_uuid(course_id)
    oid = _as_uuid(org_id)
    if schema_version < 1:
        raise ValueError("schema_version must be positive")

    started = time.perf_counter()
    course, nodes = await _load_schema_snapshot(cid, oid, schema_version, dependencies)
    semaphore = asyncio.Semaphore(dependencies.concurrency)

    async def limited(node_id: uuid.UUID) -> NodePackRunResult:
        async with semaphore:
            return await _run_node(
                course=course,
                node_id=node_id,
                org_id=oid,
                schema_version=schema_version,
                dependencies=dependencies,
            )

    results = await asyncio.gather(*(limited(node.id) for node in nodes))
    metrics = KnowledgePackRunMetrics(
        course_id=cid,
        org_id=oid,
        schema_version=schema_version,
        results=tuple(results),
        duration_ms=_elapsed_ms(started),
    )
    logger.info(
        "Knowledge-pack shadow run course=%s schema=%s nodes=%s ready=%s skipped=%s "
        "review_required=%s stale=%s failed=%s duration_ms=%s input_tokens=%s output_tokens=%s",
        cid,
        schema_version,
        len(metrics.results),
        metrics.ready,
        metrics.skipped,
        metrics.review_required,
        metrics.stale,
        metrics.failed,
        metrics.duration_ms,
        metrics.input_tokens,
        metrics.output_tokens,
    )
    return metrics


def spawn_packs_for_schema(
    course_id: str | uuid.UUID,
    org_id: str | uuid.UUID,
    schema_version: int,
    *,
    dependencies: KnowledgePackRunnerDependencies,
) -> None:
    """Schedule the runner after a durable schema commit.

    Any in-flight run for an *earlier* schema version of this course is cancelled first.
    Each ``PUT /schema`` bumps ``schema_version`` and spawns a fresh run; without this
    the previous run would keep going with a now-stale source fingerprint, and the two
    would race — the older one publishing packs the newer run immediately marks stale,
    which is exactly the "stale limbo" this supersede removes.
    """
    task_registry.cancel_by_prefix(f"knowledge-pack:{course_id}:")
    coroutine = run_packs_for_schema(
        course_id,
        org_id,
        schema_version,
        dependencies=dependencies,
    )
    try:
        task_registry.spawn_unique(
            coroutine,
            name=f"knowledge-pack:{course_id}:v{schema_version}",
        )
    except Exception:
        coroutine.close()
        logger.warning(
            "Could not schedule knowledge-pack run course=%s schema=%s",
            course_id,
            schema_version,
            exc_info=True,
        )


async def _load_schema_snapshot(
    course_id: uuid.UUID,
    org_id: uuid.UUID,
    schema_version: int,
    dependencies: KnowledgePackRunnerDependencies,
) -> tuple[Course, Sequence[CourseNode]]:
    """Load the schema once, then each node worker reloads its own source in a new session."""

    async with dependencies.session_factory() as db:
        course = await dependencies.load_course(db, course_id)
        if course is None or course.org_id != org_id:
            raise ValueError("course was not found in this organization")
        if course.schema_version != schema_version:
            raise ValueError(
                "schema_version does not match the persisted course; refusing a stale run"
            )
        nodes = await dependencies.load_nodes(db, course_id, org_id)
    return course, nodes


# Outcomes that a bounded retry can plausibly turn into ``ready``: a transient
# provider/timeout failure, a snapshot lost to a superseding run, or a pack the
# reviewer flagged as review_required (a fresh extraction can close the gap).
_RETRYABLE_OUTCOMES = frozenset({"failed", "stale", "review_required"})


async def _run_node(
    *,
    course: Course,
    node_id: uuid.UUID,
    org_id: uuid.UUID,
    schema_version: int,
    dependencies: KnowledgePackRunnerDependencies,
) -> NodePackRunResult:
    """Attempt one node, retrying a non-``ready`` outcome up to ``max_attempts``.

    A ``review_required`` snapshot is terminal to ``claim`` (it is a legitimate
    finished state), so before re-attempting one we explicitly reopen the row; a
    ``failed``/``stale`` row is reopened by ``claim`` itself. ``ready``/``skipped``
    returns immediately. The last observed result is returned once attempts run out,
    so a node that genuinely cannot be prepared is reported, not hidden.
    """
    last: NodePackRunResult | None = None
    last_record_id: uuid.UUID | None = None
    for attempt in range(1, dependencies.max_attempts + 1):
        if attempt > 1 and last is not None and last.outcome == "review_required":
            await _reopen_snapshot(dependencies, last_record_id)
        result, record_id = await _attempt_node(
            course=course,
            node_id=node_id,
            org_id=org_id,
            schema_version=schema_version,
            dependencies=dependencies,
        )
        if result.outcome in ("ready", "skipped"):
            return result
        last = result
        last_record_id = record_id
        if attempt < dependencies.max_attempts and result.outcome in _RETRYABLE_OUTCOMES:
            logger.info(
                "Retrying knowledge-pack node=%s attempt=%s/%s after outcome=%s",
                node_id,
                attempt,
                dependencies.max_attempts,
                result.outcome,
            )
            if dependencies.retry_backoff_seconds > 0:
                await asyncio.sleep(
                    min(dependencies.retry_backoff_seconds * attempt, 30.0)
                )
            continue
        break
    return last if last is not None else _result(node_id, "failed", time.perf_counter())


async def _reopen_snapshot(
    dependencies: KnowledgePackRunnerDependencies, record_id: uuid.UUID | None
) -> None:
    """Reset a terminal-but-not-ready snapshot to ``pending`` so a retry regenerates it."""
    if record_id is None:
        return
    try:
        async with dependencies.session_factory() as db:
            repo = dependencies.service_for_session(db).store
            reopen = getattr(repo, "reopen_snapshot", None)
            if reopen is not None:
                await reopen(record_id)
                await _commit(db)
    except Exception:  # noqa: BLE001 - a failed reopen just means the retry re-claims as-is.
        logger.warning("Could not reopen knowledge-pack snapshot %s", record_id, exc_info=True)


async def _attempt_node(
    *,
    course: Course,
    node_id: uuid.UUID,
    org_id: uuid.UUID,
    schema_version: int,
    dependencies: KnowledgePackRunnerDependencies,
) -> tuple[NodePackRunResult, uuid.UUID | None]:
    started = time.perf_counter()
    snapshot: KnowledgePackSnapshot | None = None
    record: Any | None = None
    try:
        # Source, optional per-node draft, and the claim happen before pack generation.
        # A generation never keeps a connection or transaction open for tens of seconds.
        async with dependencies.session_factory() as db:
            node = await _load_one_node(db, node_id, org_id, course.id)
            if node is None:
                return _result(node_id, "failed", started, error="node no longer exists"), None
            source_context = await dependencies.load_source(db, node, org_id)

        if not source_context.strip():
            source_context = await asyncio.wait_for(
                _draft_node_source(dependencies, course, node),
                timeout=dependencies.timeout_seconds,
            )

        async with dependencies.session_factory() as db:
            node = await _load_one_node(db, node_id, org_id, course.id)
            if node is None:
                return _result(node_id, "failed", started, error="node no longer exists"), None
            existing = await dependencies.load_source(db, node, org_id)
            if (
                not existing.strip()
                and source_context.strip()
                and dependencies.persist_source is not None
            ):
                await dependencies.persist_source(db, node, source_context, course)
            snapshot = KnowledgePackSnapshot(
                org_id=org_id,
                course_id=course.id,
                node_id=node.id,
                source_fingerprint=source_fingerprint(
                    node=node, source_context=source_context, schema_version=schema_version
                ),
                schema_version=schema_version,
                generator_version=dependencies.generator_version,
            )
            service = dependencies.service_for_session(db)
            record = await service.claim(snapshot)
            await _commit(db)
            if record.status in (
                NodeKnowledgePackStatus.READY,
                NodeKnowledgePackStatus.REVIEW_REQUIRED,
            ):
                outcome = (
                    "skipped"
                    if record.status == NodeKnowledgePackStatus.READY
                    else "review_required"
                )
                return _result(node_id, outcome, started), record.id

        generated = await asyncio.wait_for(
            dependencies.generator.generate(
                course=course,
                node=node,
                source_context=source_context,
                snapshot=snapshot,
            ),
            timeout=dependencies.timeout_seconds,
        )

        async with dependencies.session_factory() as db:
            completed = await dependencies.service_for_session(db).complete(
                SimpleNamespace(id=record.id), snapshot=snapshot, pack=generated
            )
            await _commit(db)
        if completed is None:
            return _result(node_id, "stale", started, generated), record.id
        return _result(node_id, completed.status.value, started, generated), record.id
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - failure is isolated to this node by design.
        message = f"{type(exc).__name__}: {str(exc)[:500]}"
        logger.warning("Knowledge-pack generation failed node=%s: %s", node_id, message)
        if snapshot is not None and record is not None:
            try:
                async with dependencies.session_factory() as db:
                    await dependencies.service_for_session(db).fail(
                        SimpleNamespace(id=record.id), snapshot=snapshot, error_message=message
                    )
                    await _commit(db)
            except Exception:  # noqa: BLE001 - never hide the original generation failure.
                logger.exception("Could not mark knowledge-pack failure node=%s", node_id)
        return (
            _result(node_id, "failed", started, error=message),
            record.id if record is not None else None,
        )


async def _draft_node_source(
    dependencies: KnowledgePackRunnerDependencies,
    course: Course,
    node: CourseNode,
) -> str:
    """Write a per-node brief when the schema has no uploaded excerpt yet."""

    drafter = dependencies.draft_source
    if drafter is None:
        drafter = getattr(dependencies.generator, "draft_source", None)
    if drafter is not None:
        try:
            text = await drafter(course=course, node=node)
            if text and str(text).strip():
                return str(text).strip()
        except Exception:  # noqa: BLE001 - the schema seed is enough to keep the pack moving.
            logger.warning(
                "Node source draft failed node=%s; using the schema briefing",
                node.id,
                exc_info=True,
            )
    return seed_node_source(course=course, node=node)


async def _load_one_node(
    db: Any, node_id: uuid.UUID, org_id: uuid.UUID, course_id: uuid.UUID
) -> CourseNode | None:
    node = await db.get(CourseNode, node_id)
    if node is None or node.org_id != org_id or node.course_id != course_id or node.archived:
        return None
    return node


async def _commit(db: Any) -> None:
    commit = getattr(db, "commit", None)
    if commit is not None:
        await commit()


def _result(
    node_id: uuid.UUID,
    outcome: str,
    started: float,
    generated: CompletedKnowledgePack | None = None,
    error: str | None = None,
) -> NodePackRunResult:
    return NodePackRunResult(
        node_id=node_id,
        outcome=outcome,
        duration_ms=_elapsed_ms(started),
        input_tokens=generated.input_tokens if generated else None,
        output_tokens=generated.output_tokens if generated else None,
        error=error,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


__all__ = [
    "DEFAULT_CONCURRENCY",
    "DEFAULT_GENERATOR_VERSION",
    "DEFAULT_TIMEOUT_SECONDS",
    "KnowledgePackGenerator",
    "KnowledgePackRunMetrics",
    "KnowledgePackRunnerDependencies",
    "NodePackRunResult",
    "run_packs_for_schema",
    "spawn_packs_for_schema",
    "source_fingerprint",
]
