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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from src.core import sse
from src.core.exceptions import LLMError
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
from src.services.capabilities import derive_capabilities
from src.services.media.requirements import ensure_kind_is_available
from src.services import provider_health
from src.services.media.assets import AssetStore
from src.services.media.grounding import GroundedBundle, build_grounding_bundle
from src.services.media.subject import MediaContextError, MediaSubject, subject_from

logger = get_logger(__name__)

#: How long the runner waits for the client to open the SSE stream before starting, so the
#: first ``media_step`` is not published into the void (the pub/sub keeps no backlog).
SUBSCRIBER_WAIT_SECONDS = 0.5

#: How much of a failure reaches the stored ``error`` column and the client.
_ERROR_CHARS = 500

#: Stable failure codes. The row's ``error`` column and the ``media_error`` SSE event both
#: carry one, and the frontend keys its message off the code — never off the text.
#:
#: What used to travel was ``f"{type(exc).__name__}: {exc}"``: a provider's raw exception
#: string, shown verbatim to a learner. That is unreadable at best, and at worst it is a
#: URL, a model name or an account identifier from inside the deployment. The code is the
#: contract; the message beside it is short, safe and English.
ERROR_LLM_FAILED = "llm_failed"
ERROR_PROVIDER_QUOTA = "provider_quota"
ERROR_PROVIDER_DOWN = "provider_down"
ERROR_CANCELLED = "cancelled"
ERROR_INTERNAL = "internal_error"
#: Nothing to generate from: no source passages *and* no course/node identity. Not a
#: provider failure and not a bug — the course itself has nothing to say yet, and a retry
#: against the same course would produce the same nothing.
ERROR_NO_CONTEXT = "no_context"
#: The one code no generation ever produces: it is recorded *afterwards*, when a row that
#: says ``done`` turns out to have no file behind it (``services/media/integrity.py``).
ERROR_ASSET_MISSING = "asset_missing"

_ERROR_MESSAGES: dict[str, str] = {
    ERROR_LLM_FAILED: "The AI provider could not produce this content.",
    ERROR_PROVIDER_QUOTA: "The provider is out of quota. Try again later.",
    ERROR_PROVIDER_DOWN: "The provider is unavailable right now. Try again later.",
    ERROR_CANCELLED: "The generation was cancelled.",
    ERROR_NO_CONTEXT: (
        "This course has no material to generate from. Add a source document or write the "
        "lesson content first."
    ),
    ERROR_INTERNAL: "This generation failed. The details are in the server log.",
    ERROR_ASSET_MISSING: (
        "The generated file is no longer stored on this server. Generate it again."
    ),
}


def error_message(code: str) -> str:
    """The short, user-safe sentence for a failure code.

    The map is private on purpose — nothing outside this module may put its own text on a
    row — but the sentences have to be reachable by the one other writer of ``error``
    (:mod:`src.services.media.integrity`), so it reads them through here rather than
    keeping a second copy that can drift.
    """
    return _ERROR_MESSAGES.get(code, _ERROR_MESSAGES[ERROR_INTERNAL])


def classify_failure(exc: BaseException) -> tuple[str, str]:
    """Map an exception to ``(error_code, safe message)``. Never leaks the exception text.

    The full exception, with its traceback, is logged at the point of failure — the
    operator keeps everything, the user gets a code and a sentence.
    """
    # Checked before the provider buckets: an empty subject is not the provider's fault,
    # and telling the owner "try again later" for it would be a lie.
    if isinstance(exc, MediaContextError):
        return ERROR_NO_CONTEXT, _ERROR_MESSAGES[ERROR_NO_CONTEXT]
    kind = provider_health.failure_kind(exc)
    if kind == "quota":
        return ERROR_PROVIDER_QUOTA, _ERROR_MESSAGES[ERROR_PROVIDER_QUOTA]
    if isinstance(exc, LLMError):
        return ERROR_LLM_FAILED, _ERROR_MESSAGES[ERROR_LLM_FAILED]
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ERROR_PROVIDER_DOWN, _ERROR_MESSAGES[ERROR_PROVIDER_DOWN]
    return ERROR_INTERNAL, _ERROR_MESSAGES[ERROR_INTERNAL]

#: A generator's optional progress reporter: ``(step, extra) -> awaitable``. The runner
#: binds one to the job's SSE channel and hands it to the generator via the context, so a
#: multi-stage generator (podcast: guion -> voz -> listo) can stream its own steps without
#: knowing anything about SSE, the channel, or the artifact id.
ProgressFn = Callable[[str, dict], Awaitable[None]]


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
    #: Optional per-stage progress reporter, bound to the job's SSE channel by the runner.
    #: ``None`` off the hot path (unit tests, the echo default) — use :meth:`emit`, which
    #: is a no-op when it is unset, rather than calling this directly.
    progress: ProgressFn | None = None

    def subject(self) -> MediaSubject:
        """Who this artifact is about — the identity that must reach the prompt.

        The course and the node have always been here; before this existed every generator
        read them only to label ``scope``, so a boxing course produced an artifact that had
        never been told the word "boxing". Every family now asks for this and passes it to
        its prompt builder.
        """
        return subject_from(self.course, self.node)

    async def emit(self, step: str, **extra: object) -> None:
        """Publish one intermediate progress step, or do nothing if unwired.

        Additive and safe to call from any generator: the runner injects the reporter, and
        every caller that builds a context without one (tests, the echo default) simply
        gets a silent no-op.
        """
        if self.progress is not None:
            await self.progress(step, dict(extra))


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
    #: The user-safe failure message. ``None`` unless ``status`` is ``ERROR``.
    error: str | None = None
    #: The stable failure code the client keys its own message off. Paired with ``error``.
    error_code: str | None = None


async def execute_generation(
    ctx: MediaJobContext,
    generator: MediaGenerator,
    asset_store: AssetStore,
) -> GenerationResult:
    """Run one generator and turn its outcome into a row state.

    Success with bytes -> ``done`` + stored asset (deduped by content hash). Success
    without bytes -> ``done`` with a spec only. Any exception -> ``error`` with a stable
    code and a safe message, the exception itself going to the log and nowhere else.
    ``CancelledError`` is re-raised untouched: a cancelled job is not a failed one, same
    rule as the node-render runner.
    """
    try:
        produced = await generator.generate(ctx)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - generator boundary; recorded, not swallowed
        logger.error("Media generator for %s failed: %s", ctx.kind, exc, exc_info=True)
        code, message = classify_failure(exc)
        return GenerationResult(
            status=MediaArtifactStatus.ERROR,
            error=message[:_ERROR_CHARS],
            error_code=code,
        )

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

    Raises :class:`CapabilityBlockedError` when the deployment cannot produce this kind.
    The check lives here, at the one place every starter passes through, rather than on
    the route that happens to be user-facing today: the studio was gated and the lesson
    player's own audio/video button was not, so the learner got exactly the accepted-then-
    dead job the gate exists to prevent. A caller that spawns artefacts best-effort (the
    seed, the end-to-end orchestrator) catches this and skips instead of failing.
    """
    ensure_kind_is_available(kind, derive_capabilities())
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


async def _mark_error(artifact_id: uuid.UUID, code: str) -> None:
    """Best-effort ``status = 'error'`` in a fresh session. Never raises.

    Takes a *code*, not a message: the stored message is looked up from the code, so no
    caller can accidentally hand this an exception string on its way to a user's screen.
    """
    try:
        async with async_session_factory() as db:
            artifact = await MediaArtifactRepository(db).get_by_id(artifact_id)
            if artifact is not None:
                artifact.status = MediaArtifactStatus.ERROR
                artifact.error = _ERROR_MESSAGES.get(
                    code, _ERROR_MESSAGES[ERROR_INTERNAL]
                )[:_ERROR_CHARS]
                artifact.error_code = code
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

            async def _report(step: str, extra: dict) -> None:
                await sse.publish(channel, "media_step", {"step": step, **extra})

            ctx = MediaJobContext(
                kind=kind,
                spec=spec,
                bundle=bundle,
                course=course,
                node=node,
                progress=_report,
            )
            result = await execute_generation(ctx, get_generator(kind), AssetStore())

            artifact.status = result.status
            if result.spec_json:
                artifact.spec_json = result.spec_json
            artifact.asset_path = result.asset_path
            artifact.content_hash = result.content_hash
            artifact.error = result.error
            artifact.error_code = result.error_code
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
            # Same event name the frontend already listens to, same ``message`` key; the
            # message is now the safe one and ``code`` rides alongside it.
            await sse.publish(
                channel,
                "media_error",
                {
                    "message": (result.error or "")[:200],
                    "code": result.error_code or ERROR_INTERNAL,
                },
            )
    except asyncio.CancelledError:
        await _mark_error(artifact_id, ERROR_CANCELLED)
        logger.info("Media job %s cancelled", artifact_id)
        raise
    except Exception as exc:  # noqa: BLE001 - top-level safety net, mirrors node runner
        logger.error("Media job %s failed: %s", artifact_id, exc, exc_info=True)
        code, message = classify_failure(exc)
        await _mark_error(artifact_id, code)
        await sse.publish(channel, "media_error", {"message": message, "code": code})


__all__ = [
    "ERROR_ASSET_MISSING",
    "ERROR_CANCELLED",
    "ERROR_INTERNAL",
    "ERROR_LLM_FAILED",
    "ERROR_NO_CONTEXT",
    "ERROR_PROVIDER_DOWN",
    "ERROR_PROVIDER_QUOTA",
    "classify_failure",
    "error_message",
    "media_channel",
    "ProgressFn",
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
