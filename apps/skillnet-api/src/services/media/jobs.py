"""Async MediaArtifact job runner + the ``MediaGenerator`` interface (spine item #5).

This is the single most important primitive of the media roadmap (§2, §3 item #1): it makes
every artifact match NotebookLM's "background, non-blocking" contract. Enqueue returns
immediately with a ``pending`` row; the real work runs as a tracked background task that
walks the row ``pending -> running -> done|error`` and streams progress over the existing
in-process SSE pub/sub (``src/core/sse.py``), exactly the way node-render does — same
channel discipline, same wait-for-subscriber, same task registry.

**Modularity is the hard requirement here.** Each concrete artifact (podcast, slides,
infographic, ...) is a separate :class:`MediaGenerator` that plugs into the registry; the
runner knows nothing about any of them. This module ships only the runner, the interface,
and a trivial :class:`EchoGenerator` used as the default so the pipeline is provable
end-to-end before a single real generator exists. Real generators land later, one per
commit, and register themselves — overriding the echo for their kind.

The generation **core** (:func:`execute_generation`) is deliberately free of DB and SSE: it
takes a generator and an asset store, and returns a :class:`GenerationResult` describing the
new row state. That is the state machine, and it is unit-testable without Postgres, network
or an event loop subscriber. :func:`run_media_job` wraps it with the session, the SSE
events and the cancellation handling.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from src.core import sse
from src.core.logging import get_logger
from src.core.tasks import task_registry
from src.deps.db import async_session_factory
from src.models import (
    Course,
    CourseNode,
    MediaArtifact,
    MediaArtifactStatus,
    MediaKind,
)
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.media_artifact_repo import MediaArtifactRepository
from src.services.media.assets import AssetStore
from src.services.media.grounding import GroundedBundle, build_grounding_bundle

logger = get_logger(__name__)

#: How long the runner waits for the client to open the SSE stream before starting, so the
#: first ``media_step`` is not published into the void (the pub/sub keeps no backlog).
SUBSCRIBER_WAIT_SECONDS = 0.5

#: How much of a failure reaches the stored ``error`` column and the client.
_ERROR_CHARS = 500


def media_channel(artifact_id: str | uuid.UUID) -> str:
    """The SSE channel of one media job. Never shared with node-render's ``node:{id}``."""
    return f"media:{artifact_id}"


# --------------------------------------------------------------------------------------
# The generator interface and its inputs/outputs
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class MediaJobContext:
    """Everything a generator is handed: the request, the corpus, and the grounding bundle.

    ``spec`` is the caller's input (format preset, language, steering prompt, ...). ``bundle``
    is the cited source context assembled by the grounding builder — the unit every
    generator grounds on and emits ``citation_id``s against.
    """

    kind: MediaKind
    spec: dict
    bundle: GroundedBundle
    course: Course | None = None
    node: CourseNode | None = None


@dataclass(frozen=True)
class GeneratedArtifact:
    """What a generator returns: the grounded JSON spec, and optional rendered bytes.

    ``data`` is ``None`` for spec-only artifacts (a mind map is an explicit tree in
    ``spec_json``, not a file). When present, ``ext`` names the file type for the asset
    store and the HTTP layer.
    """

    spec_json: dict
    data: bytes | None = None
    ext: str | None = None


@runtime_checkable
class MediaGenerator(Protocol):
    """The plug-in contract. Each concrete artifact implements exactly this.

    ``kind`` is the artifact this generator produces (``None`` for the generic echo
    default). ``generate`` is fed the :class:`MediaJobContext` and returns a
    :class:`GeneratedArtifact`; it must raise on failure rather than return a broken spec,
    and it must let ``asyncio.CancelledError`` propagate.
    """

    kind: MediaKind | None

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact: ...


class EchoGenerator:
    """Trivial no-op generator that proves the pipeline end-to-end.

    Produces no bytes; echoes the input spec plus the grounding bundle's citations into
    ``spec_json``. Registered as the default for every kind that has no real generator yet,
    so ``POST /media/artifacts`` already walks the full pending->running->done path and
    streams SSE before podcast/slides/etc. exist.
    """

    kind: MediaKind | None = None

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
        return GeneratedArtifact(
            spec_json={
                "generator": "echo",
                "kind": ctx.kind.value,
                "input_spec": ctx.spec,
                "grounding_mode": ctx.bundle.mode,
                "citations": ctx.bundle.citations_payload(),
                "passages_seen": len(ctx.bundle.passages),
            }
        )


# --------------------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------------------
_GENERATORS: dict[MediaKind, MediaGenerator] = {}
_default_generator: MediaGenerator = EchoGenerator()


def register_generator(generator: MediaGenerator) -> None:
    """Register a concrete generator under its ``kind`` (overrides the echo default)."""
    if generator.kind is None:
        raise ValueError("A registered generator must declare a concrete kind")
    _GENERATORS[generator.kind] = generator


def get_generator(kind: MediaKind) -> MediaGenerator:
    """The generator for ``kind``, or the echo default while none is registered."""
    return _GENERATORS.get(kind, _default_generator)


# --------------------------------------------------------------------------------------
# The state machine core (no DB, no SSE — unit-testable)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class GenerationResult:
    """The new row state after one generation attempt."""

    status: MediaArtifactStatus
    spec_json: dict = field(default_factory=dict)
    asset_path: str | None = None
    content_hash: str | None = None
    error: str | None = None


async def execute_generation(
    ctx: MediaJobContext,
    generator: MediaGenerator,
    asset_store: AssetStore,
) -> GenerationResult:
    """Run one generator and turn its outcome into a row state.

    Success with bytes -> ``done`` + stored asset (deduped by content hash). Success
    without bytes -> ``done`` with a spec only. Any exception -> ``error`` with the
    message. ``CancelledError`` is re-raised untouched: a cancelled job is not a failed
    one, same rule as the node-render runner.
    """
    try:
        produced = await generator.generate(ctx)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - generator boundary; recorded, not swallowed
        logger.error("Media generator for %s failed: %s", ctx.kind, exc, exc_info=True)
        message = f"{type(exc).__name__}: {exc}"[:_ERROR_CHARS]
        return GenerationResult(status=MediaArtifactStatus.ERROR, error=message)

    asset_path: str | None = None
    digest: str | None = None
    if produced.data is not None:
        stored = asset_store.store(produced.data, produced.ext or "bin")
        asset_path = stored.path
        digest = stored.content_hash

    return GenerationResult(
        status=MediaArtifactStatus.DONE,
        spec_json=produced.spec_json,
        asset_path=asset_path,
        content_hash=digest,
    )


# --------------------------------------------------------------------------------------
# Enqueue + the background task (DB + SSE)
# --------------------------------------------------------------------------------------
async def enqueue_artifact(
    db,
    *,
    course: Course,
    kind: MediaKind,
    node: CourseNode | None = None,
    spec: dict | None = None,
) -> MediaArtifact:
    """Create the ``pending`` row. The caller commits, then calls :func:`spawn_media_job`.

    Kept separate from spawning so the row is committed inside the request's transaction
    before any background task can race to read it — the same order node-render uses.
    """
    return await MediaArtifactRepository(db).create(
        org_id=course.org_id,
        course_id=course.id,
        node_id=node.id if node else None,
        kind=kind,
        status=MediaArtifactStatus.PENDING,
        spec_json=spec or {},
    )


def spawn_media_job(artifact_id: uuid.UUID) -> asyncio.Task:
    """Fire the generation off as a tracked background task (strong ref kept)."""
    return task_registry.spawn(
        run_media_job(artifact_id), name=f"media-job:{artifact_id}"
    )


async def _mark_error(artifact_id: uuid.UUID, message: str) -> None:
    """Best-effort ``status = 'error'`` in a fresh session. Never raises."""
    try:
        async with async_session_factory() as db:
            artifact = await MediaArtifactRepository(db).get_by_id(artifact_id)
            if artifact is not None:
                artifact.status = MediaArtifactStatus.ERROR
                artifact.error = message[:_ERROR_CHARS]
                await db.commit()
    except Exception:  # noqa: BLE001 - failure bookkeeping must never raise
        logger.error("Failed to mark media artifact %s errored", artifact_id, exc_info=True)


async def run_media_job(artifact_id: uuid.UUID) -> None:
    """Drive one media job to completion, streaming progress over SSE.

    Own session (the request's is long gone). Walks the row to ``running``, builds the
    grounding bundle, runs the generator via :func:`execute_generation`, persists the
    result and publishes the terminal event. ``CancelledError`` marks the row errored and
    re-raises — a swallowed cancellation reports success for work not done.
    """
    channel = media_channel(artifact_id)
    subscribed = await sse.wait_for_subscriber(channel, SUBSCRIBER_WAIT_SECONDS)
    if not subscribed:
        logger.info("No SSE subscriber on %s; generating anyway", channel)

    try:
        async with async_session_factory() as db:
            repo = MediaArtifactRepository(db)
            artifact = await repo.get_by_id(artifact_id)
            if artifact is None:
                logger.warning("Media job %s: row vanished before it ran", artifact_id)
                return

            kind = artifact.kind
            spec = dict(artifact.spec_json or {})
            course = await CourseRepository(db).get_by_id(artifact.course_id)
            node = (
                await CourseNodeRepository(db).get_by_id(artifact.node_id)
                if artifact.node_id
                else None
            )

            artifact.status = MediaArtifactStatus.RUNNING
            await db.commit()
            await sse.publish(
                channel, "media_step", {"step": "running", "kind": kind.value}
            )

            bundle = (
                await build_grounding_bundle(
                    db, course=course, node=node, query=spec.get("query")
                )
                if course is not None
                else GroundedBundle(mode="empty", passages=[])
            )
            await sse.publish(
                channel,
                "media_step",
                {"step": "grounded", "mode": bundle.mode, "passages": len(bundle.passages)},
            )

            ctx = MediaJobContext(
                kind=kind, spec=spec, bundle=bundle, course=course, node=node
            )
            result = await execute_generation(ctx, get_generator(kind), AssetStore())

            artifact.status = result.status
            if result.spec_json:
                artifact.spec_json = result.spec_json
            artifact.asset_path = result.asset_path
            artifact.content_hash = result.content_hash
            artifact.error = result.error
            await db.commit()

        if result.status == MediaArtifactStatus.DONE:
            await sse.publish(
                channel,
                "media_done",
                {
                    "artifact_id": str(artifact_id),
                    "has_asset": result.asset_path is not None,
                },
            )
        else:
            await sse.publish(
                channel, "media_error", {"message": (result.error or "")[:200]}
            )
    except asyncio.CancelledError:
        await _mark_error(artifact_id, "cancelled")
        logger.info("Media job %s cancelled", artifact_id)
        raise
    except Exception as exc:  # noqa: BLE001 - top-level safety net, mirrors node runner
        logger.error("Media job %s failed: %s", artifact_id, exc, exc_info=True)
        await _mark_error(artifact_id, f"{type(exc).__name__}: {exc}")
        await sse.publish(channel, "media_error", {"message": str(exc)[:200]})


__all__ = [
    "media_channel",
    "MediaJobContext",
    "GeneratedArtifact",
    "MediaGenerator",
    "EchoGenerator",
    "register_generator",
    "get_generator",
    "GenerationResult",
    "execute_generation",
    "enqueue_artifact",
    "spawn_media_job",
    "run_media_job",
]
