"""One-call course creation: the whole authoring flow behind a single coroutine.

Creating a dynamic course by hand is a seven-step API dance — create, propose,
poll the schema job, PUT the schema, poll the knowledge packs, review every node,
validate — plus the optional prewarm, enrolment and media artefacts. Agents (the
a2a tool, the CLI, an HTTP route) should not have to orchestrate that themselves.

:func:`create_course_end_to_end` drives the *existing* services end to end. It
reuses, never reimplements: :class:`CourseService`, :class:`CourseSchemaService`,
the knowledge-pack runner (with its bounded retry/supersede), the node-render
prewarm, :class:`EnrollmentService` and the media generators. It opens its own
sessions the way every background runner does (``async_session_factory``), spawns
the same background tasks the HTTP routes spawn, and then *waits* — with bounded
polling — for those tasks to reach a terminal state. It reports partial success
honestly ("7/8 nodes ready") instead of hanging forever.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.core.exceptions import CapabilityBlockedError
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.knowledge_pack.configured_generator import (
    GENERATOR_VERSION,
    ConfiguredKnowledgePackGenerator,
)
from src.knowledge_pack.runner import (
    KnowledgePackRunnerDependencies,
    spawn_packs_for_schema,
)
from src.llm.client import resolve_llm_config
from src.llm.fixtures import maybe_fixture_llm
from src.models import Organization
from src.models.generation_job import GenerationStep
from src.models.media_artifact import MediaKind
from src.repositories.audit_log_repo import AuditLogRepository
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.document_repo import DocumentRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.generation_job_repo import GenerationJobRepository
from src.repositories.lesson_progress_repo import LessonProgressRepository
from src.repositories.node_knowledge_pack_repo import NodeKnowledgePackRepository
from src.services.course_schema_service import CourseSchemaService
from src.services.enrollment_service import EnrollmentService
from src.services.media.jobs import enqueue_artifact, spawn_media_job
from src.services.node_render_service import spawn_prewarm_first_nodes

logger = get_logger(__name__)

# Terminal states we poll toward. The schema job is one background task; the
# knowledge packs are one per node.
_SCHEMA_DONE = GenerationStep.SCHEMA_PROPOSED
_SCHEMA_FAILED = GenerationStep.FAILED

# Bounded waits. DeepSeek is flaky at strict JSON, so the pack runner already
# retries/supersedes internally; these ceilings just stop us waiting forever when
# a node never converges. Callers can shorten/lengthen them.
DEFAULT_SCHEMA_TIMEOUT_S = 180.0
DEFAULT_PACK_TIMEOUT_S = 600.0
DEFAULT_POLL_INTERVAL_S = 3.0
DEFAULT_PACK_MAX_ATTEMPTS = 3


@dataclass
class NodePackStatus:
    node_id: uuid.UUID
    title: str
    status: str  # pending | ready | review_required | stale | failed | missing


@dataclass
class CourseEndToEndResult:
    """A structured, honest account of what the one-call flow achieved."""

    course_id: uuid.UUID
    title: str
    schema_status: str
    schema_version: int
    node_count: int = 0
    packs_ready: int = 0
    nodes: list[NodePackStatus] = field(default_factory=list)
    packs_all_ready: bool = False
    reviewed: bool = False
    validated: bool = False
    enrolled_user_id: uuid.UUID | None = None
    prewarm_spawned: bool = False
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "course_id": str(self.course_id),
            "title": self.title,
            "schema_status": self.schema_status,
            "schema_version": self.schema_version,
            "node_count": self.node_count,
            "packs_ready": self.packs_ready,
            "packs_all_ready": self.packs_all_ready,
            "packs_summary": f"{self.packs_ready}/{self.node_count} nodes ready",
            "nodes": [
                {"node_id": str(n.node_id), "title": n.title, "status": n.status}
                for n in self.nodes
            ],
            "reviewed": self.reviewed,
            "validated": self.validated,
            "enrolled_user_id": (
                str(self.enrolled_user_id) if self.enrolled_user_id else None
            ),
            "prewarm_spawned": self.prewarm_spawned,
            "artifacts": self.artifacts,
            "warnings": self.warnings,
        }


def _schema_service(db: Any) -> CourseSchemaService:
    return CourseSchemaService(
        CourseRepository(db),
        CourseNodeRepository(db),
        AuditLogRepository(db),
        EnrollmentRepository(db),
        GenerationJobRepository(db),
        DocumentRepository(db),
    )


def _enum_value(raw: Any) -> Any:
    return raw.value if hasattr(raw, "value") else raw


def _node_to_payload(node: Any, prerequisites: list[uuid.UUID]) -> dict[str, Any]:
    """Turn a proposed :class:`CourseNode` into an ``update()`` node dict (a PUT echo).

    Mirrors the field set of ``CourseNodeInput`` so re-persisting the proposal is a
    faithful no-op edit that only bumps the schema version.
    """
    return {
        "id": node.id,
        "title": node.title,
        "summary": node.summary,
        "outcome": node.outcome,
        "criticality": _enum_value(node.criticality),
        "position": node.position,
        "mastery_threshold": (
            float(node.mastery_threshold)
            if node.mastery_threshold is not None
            else None
        ),
        "default_ui_format": _enum_value(node.default_ui_format),
        "skill_id": node.skill_id,
        "seed_lesson_id": node.seed_lesson_id,
        "source_document_id": node.source_document_id,
        "source_headings": list(node.source_headings or []),
        "prerequisite_node_ids": list(prerequisites),
        "archived": bool(node.archived),
    }


async def _org_settings(db: Any) -> dict[str, Any]:
    from sqlalchemy import select

    result = await db.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    return dict(org.settings) if org and org.settings else {}


async def _generation_llm(db: Any):
    """The generation-purpose LLM, resolved from org settings exactly like the dep."""
    return maybe_fixture_llm(
        resolve_llm_config(await _org_settings(db), purpose="generation")
    )


async def create_course_end_to_end(
    title: str,
    *,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    document_id: uuid.UUID | None = None,
    intent_density: int = 3,
    description: str | None = None,
    outcome: str | None = None,
    enroll_user_id: uuid.UUID | None = None,
    generate_artifacts: list[str] | None = None,
    artifact_node_limit: int = 1,
    prewarm: bool = True,
    schema_timeout_s: float = DEFAULT_SCHEMA_TIMEOUT_S,
    pack_timeout_s: float = DEFAULT_PACK_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    pack_max_attempts: int = DEFAULT_PACK_MAX_ATTEMPTS,
) -> CourseEndToEndResult:
    """Create a dynamic course from a title (and optional document) in one call.

    Returns a :class:`CourseEndToEndResult` describing exactly how far the flow got:
    packs ready count, reviewed/validated flags, enrolment, artefacts. Never raises
    on partial success — a course whose packs never all converge still comes back
    validated (if the graph is valid) with an honest ``packs_ready`` count and a
    warning.
    """
    # --- 1. create the (draft) course -------------------------------------------
    async with async_session_factory() as db:
        from src.services.course_service import CourseService

        course = await CourseService(CourseRepository(db)).create(
            org_id=org_id,
            created_by=created_by,
            title=title,
            description=description,
            outcome=outcome,
            source_document_id=document_id,
        )
        await db.commit()
        course_id = course.id
        logger.info("orchestrator: created course %s (%s)", course_id, title)

    result = CourseEndToEndResult(
        course_id=course_id,
        title=title,
        schema_status="draft",
        schema_version=1,
    )

    # --- 2. propose the schema (spawns the designer job) ------------------------
    async with async_session_factory() as db:
        job = await _schema_service(db).propose(
            course_id=course_id,
            org_id=org_id,
            triggered_by=created_by,
            source_document_id=document_id,
            intent_density=intent_density,
        )
        await db.commit()
        job_id = job.id
        logger.info("orchestrator: proposing schema, job %s", job_id)

    # --- 3. wait for the schema job to finish -----------------------------------
    job_status = await _wait_for_schema(job_id, org_id, schema_timeout_s, poll_interval_s)
    if job_status != _SCHEMA_DONE.value:
        result.schema_status = "propose_failed"
        result.warnings.append(
            f"schema proposal did not complete (job status={job_status}); "
            "no nodes to generate"
        )
        return result

    # --- 4. persist the proposed schema (PUT), then spawn packs -----------------
    # We re-persist the proposed nodes via ``update()`` exactly like the create
    # wizard's PUT does. This is not busy-work: ``update()`` bumps
    # ``schema_version``, and the pack runner is keyed by version
    # (``knowledge-pack:{course}:v{n}``). Spawning at the *proposed* version would
    # collide by name with the shadow run ``persist_schema`` already started, so
    # ``spawn_unique`` would no-op and ``cancel_by_prefix`` would kill the shadow —
    # leaving zero packs. Bumping the version sidesteps that and supersedes cleanly.
    async with async_session_factory() as db:
        service = _schema_service(db)
        snapshot = await service.get_schema(course_id=course_id, org_id=org_id)
        proposed = list(snapshot.nodes)
        if not proposed:
            result.schema_status = snapshot.course.schema_status.value
            result.warnings.extend(snapshot.warnings)
            result.warnings.append("proposed schema has no nodes")
            return result
        node_payloads = [
            _node_to_payload(node, snapshot.prerequisites.get(node.id) or [])
            for node in proposed
        ]
        snapshot = await service.update(
            course_id=course_id,
            org_id=org_id,
            actor_id=created_by,
            nodes=node_payloads,
            intent_density=intent_density,
        )
        await db.commit()
        schema_version = int(snapshot.course.schema_version or 1)
        nodes = list(snapshot.nodes)
        result.schema_status = snapshot.course.schema_status.value
        result.schema_version = schema_version
        result.node_count = len(nodes)
        result.warnings.extend(snapshot.warnings)
        llm = await _generation_llm(db)

    # Reuse the runner's retry/supersede: max_attempts>1 so a flaky-DeepSeek node
    # is retried instead of being left as a permanent surprise on the course.
    spawn_packs_for_schema(
        course_id,
        org_id,
        schema_version,
        dependencies=KnowledgePackRunnerDependencies(
            generator=ConfiguredKnowledgePackGenerator(llm),
            max_attempts=pack_max_attempts,
        ),
    )
    logger.info(
        "orchestrator: spawned packs for %d nodes (schema v%d)",
        len(nodes),
        schema_version,
    )

    # --- 5. wait for packs to reach ready (bounded) -----------------------------
    node_status = await _wait_for_packs(
        course_id, org_id, schema_version, len(nodes), pack_timeout_s, poll_interval_s
    )
    result.nodes = node_status
    result.packs_ready = sum(1 for n in node_status if n.status == "ready")
    result.packs_all_ready = result.packs_ready == len(nodes)
    if not result.packs_all_ready:
        result.warnings.append(
            f"only {result.packs_ready}/{len(nodes)} knowledge packs reached ready "
            "within the timeout"
        )

    # --- 6. review every node (the human sign-off, done atomically) -------------
    async with async_session_factory() as db:
        service = _schema_service(db)
        snap = await service.get_schema(course_id=course_id, org_id=org_id)
        for node in snap.nodes:
            if node.reviewed_at is None and not node.archived:
                await service.mark_reviewed(
                    course_id=course_id,
                    org_id=org_id,
                    node_id=node.id,
                    actor_id=created_by,
                )
        await db.commit()
    result.reviewed = True

    # --- 7. validate the schema (the gate) --------------------------------------
    try:
        async with async_session_factory() as db:
            snap = await _schema_service(db).validate(
                course_id=course_id, org_id=org_id, actor_id=created_by
            )
            await db.commit()
            result.schema_status = snap.course.schema_status.value
            result.schema_version = int(snap.course.schema_version or 1)
            result.validated = snap.course.schema_status.value == "validated"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the whole flow
        logger.warning("orchestrator: validate failed for %s: %s", course_id, exc)
        result.warnings.append(f"validate failed: {exc}")
        return result

    # --- 7b. prewarm the first nodes' renders -----------------------------------
    if prewarm and result.validated:
        spawn_prewarm_first_nodes(
            course_id, org_id, result.schema_version, created_by
        )
        result.prewarm_spawned = True

    # --- 8. optional enrolment --------------------------------------------------
    if enroll_user_id is not None and result.validated:
        try:
            async with async_session_factory() as db:
                service = EnrollmentService(
                    EnrollmentRepository(db),
                    CourseRepository(db),
                    ExerciseRepository(db),
                    LessonProgressRepository(db),
                )
                await service.assign(
                    org_id=org_id,
                    assigned_by=created_by,
                    course_id=course_id,
                    user_ids=[enroll_user_id],
                    deadline=None,
                )
                await db.commit()
            result.enrolled_user_id = enroll_user_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("orchestrator: enrol failed: %s", exc)
            result.warnings.append(f"enrolment failed: {exc}")

    # --- 9. optional media artefacts for the first nodes ------------------------
    if generate_artifacts and result.validated:
        await _spawn_artifacts(
            course_id, org_id, generate_artifacts, artifact_node_limit, result
        )

    logger.info(
        "orchestrator: done course=%s validated=%s packs=%d/%d",
        course_id,
        result.validated,
        result.packs_ready,
        result.node_count,
    )
    return result


async def _wait_for_schema(
    job_id: uuid.UUID,
    org_id: uuid.UUID,
    timeout_s: float,
    poll_interval_s: float,
) -> str:
    """Poll the schema job until it is proposed/failed or the timeout elapses."""
    deadline = time.monotonic() + timeout_s
    last = "unknown"
    while time.monotonic() < deadline:
        async with async_session_factory() as db:
            job = await GenerationJobRepository(db).get_scoped(job_id, org_id)
        if job is not None:
            last = job.status.value if hasattr(job.status, "value") else str(job.status)
            if last in (_SCHEMA_DONE.value, _SCHEMA_FAILED.value):
                return last
        await asyncio.sleep(poll_interval_s)
    return last


async def _wait_for_packs(
    course_id: uuid.UUID,
    org_id: uuid.UUID,
    schema_version: int,
    node_count: int,
    timeout_s: float,
    poll_interval_s: float,
) -> list[NodePackStatus]:
    """Poll knowledge packs until every node is ready or the timeout elapses.

    Terminal-but-not-ready outcomes (failed after retries) still stop the wait once
    no node is left ``pending``/``stale``; there is nothing more to wait for.
    """
    deadline = time.monotonic() + timeout_s
    latest: list[NodePackStatus] = []
    while time.monotonic() < deadline:
        latest = await _pack_statuses(course_id, org_id, schema_version)
        ready = sum(1 for n in latest if n.status == "ready")
        if ready >= node_count:
            return latest
        in_flight = any(n.status in ("pending", "stale", "missing") for n in latest)
        if len(latest) >= node_count and not in_flight:
            # Everything has reached a terminal state; some may be failed/review.
            return latest
        await asyncio.sleep(poll_interval_s)
    return latest


async def _pack_statuses(
    course_id: uuid.UUID, org_id: uuid.UUID, schema_version: int
) -> list[NodePackStatus]:
    async with async_session_factory() as db:
        service = _schema_service(db)
        snap = await service.get_schema(course_id=course_id, org_id=org_id)
        by_id = {n.id: n for n in snap.nodes}
        rows = await NodeKnowledgePackRepository(db).latest_for_schema(
            course_id=course_id, org_id=org_id, schema_version=schema_version
        )
    seen: dict[uuid.UUID, str] = {}
    for row in rows:
        seen[row.node_id] = (
            row.status.value if hasattr(row.status, "value") else str(row.status)
        )
    out: list[NodePackStatus] = []
    for node_id, node in by_id.items():
        out.append(
            NodePackStatus(
                node_id=node_id,
                title=node.title,
                status=seen.get(node_id, "missing"),
            )
        )
    return out


async def _spawn_artifacts(
    course_id: uuid.UUID,
    org_id: uuid.UUID,
    kinds: list[str],
    node_limit: int,
    result: CourseEndToEndResult,
) -> None:
    """Enqueue the requested media artefacts for the first ``node_limit`` nodes."""
    valid = {k.value for k in MediaKind}
    async with async_session_factory() as db:
        course = await CourseRepository(db).get_scoped(course_id, org_id)
        nodes = await CourseNodeRepository(db).list_for_course(course_id)
        targets = list(nodes)[: max(0, node_limit)]
        for node in targets:
            for raw in kinds:
                kind = str(raw).strip().lower()
                if kind not in valid:
                    result.warnings.append(f"unknown artifact kind '{raw}'")
                    continue
                try:
                    artifact = await enqueue_artifact(
                        db,
                        course=course,
                        node=node,
                        kind=MediaKind(kind),
                        spec={"scope": "node"},
                    )
                except CapabilityBlockedError as exc:
                    # Best-effort by contract: a deployment that cannot make a podcast
                    # still gets its course. Recorded as a warning so the caller can say
                    # why the artefacts are missing instead of leaving it to be guessed.
                    result.warnings.append(f"skipped {kind}: {exc.message}")
                    continue
                result.artifacts.append(
                    {
                        "artifact_id": str(artifact.id),
                        "node_id": str(node.id),
                        "kind": kind,
                        "status": "pending",
                    }
                )
        await db.commit()
    # Spawn the jobs after the rows are committed (same order as the media route).
    for art in result.artifacts:
        spawn_media_job(uuid.UUID(art["artifact_id"]))


__all__ = [
    "CourseEndToEndResult",
    "NodePackStatus",
    "create_course_end_to_end",
    "GENERATOR_VERSION",
]
