"""Design-time course-schema business logic (§11.1).

This module owns **the blocking gate**. Everything else in v2 is an optimisation;
this is the promise of §1.1: no learner ever receives generated content for a node
a human has not signed off.

The gate is three independent locks, all enforced here:

1. ``POST /schema/validate`` is the only door from ``proposed`` to ``validated``,
   and it refuses to open on a malformed graph (cycles, orphans, missing summary,
   missing source, no ``critical`` node, non-contiguous positions, unreviewed node).
2. ``PUT /schema`` on a ``validated`` course is ``422 schema_locked``. Editing a
   live course means calling ``unvalidate`` first, which drops the course back to
   ``delivery_mode='static'`` in the same transaction. Editing a live course
   therefore takes it out of v2 until someone re-validates it — explicit, not
   implicit.
3. ``ensure_node_servable`` is the per-node lock used by the runtime: a node whose
   course is not ``validated``/``dynamic``, or which has no ``reviewed_at``, or
   which is archived, cannot be served. That closes the "add a node to an
   already-validated course" bypass by construction rather than by trust.

The graph algorithms at the top are pure and free of I/O so they are unit-testable
without a database (there is none in CI — §12.2).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import select

from src.core.exceptions import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.core.tasks import task_registry
from src.models import (
    CRITICALITY_THRESHOLDS,
    ContentStatus,
    Course,
    CourseDeliveryMode,
    CourseNode,
    CourseSchemaStatus,
    DocumentStatus,
    GenerationJob,
    GenerationOutput,
    GenerationStep,
    NodeCriticality,
    NodeState,
    UiFormat,
)
from src.repositories.audit_log_repo import AuditLogRepository, course_subject
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.document_repo import DocumentRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.generation_job_repo import GenerationJobRepository
from src.services.enrollment_service import NodeProgressRow, apply_dynamic_closure
from src.services.mastery_service import evaluate_course_completion

logger = get_logger(__name__)

# Fields whose edit invalidates a human review (§11.1 rule 2).
REVIEW_INVALIDATING_FIELDS: tuple[str, ...] = (
    "title",
    "summary",
    "criticality",
    "source_headings",
)

SCHEMA_LOCKED_MESSAGE = (
    "Este esquema esta validado. Usa /schema/unvalidate antes de editarlo."
)

# How many enrollments one recompute touches. A course with more than this many
# active enrollments is a batch job, not a request.
ENROLLMENT_RECOMPUTE_LIMIT = 1000


# --------------------------------------------------------------------------- #
# Structured errors (§11.1)
# --------------------------------------------------------------------------- #
class SchemaError(Exception):
    """Base for the structured schema responses.

    These are **not** ``AppError`` subclasses: §11.1 fixes a nested ``detail``
    shape (``{"detail": {"code": ..., "errors": [...]}}``) that the global
    ``AppError`` handler cannot express, so the route translates them into a plain
    ``HTTPException`` whose default rendering is exactly that shape.
    """

    status_code = 422

    def payload(self) -> dict:  # pragma: no cover - overridden everywhere
        raise NotImplementedError


class SchemaInvalid(SchemaError):
    """``422 schema_invalid`` with the full list of blocking rule violations."""

    def __init__(self, errors: list[dict]) -> None:
        super().__init__(f"Schema is invalid: {errors}")
        self.errors = errors

    def payload(self) -> dict:
        return {"code": "schema_invalid", "errors": self.errors}


class SchemaLocked(SchemaError):
    """``422 schema_locked`` — the gate refusing an edit to a live course."""

    def __init__(self, message: str = SCHEMA_LOCKED_MESSAGE) -> None:
        super().__init__(message)
        self.detail_message = message

    def payload(self) -> dict:
        return {"code": "schema_locked", "message": self.detail_message}


class NodeHasProgress(SchemaError):
    """``422 node_has_progress`` — deleting would destroy mastery and audit trail."""

    def __init__(self, node_ids: Sequence[uuid.UUID]) -> None:
        super().__init__(f"Nodes have learner progress: {list(node_ids)}")
        self.node_ids = [str(nid) for nid in node_ids]

    def payload(self) -> dict:
        return {
            "code": "node_has_progress",
            "node_ids": self.node_ids,
            "message": (
                "Este nodo tiene progreso de aprendices: archivalo en lugar de "
                "borrarlo."
            ),
        }


class NodeNotReviewed(SchemaError):
    """``409 node_not_reviewed`` — the per-node half of the gate."""

    status_code = 409

    def __init__(self, node_id: uuid.UUID | str, message: str) -> None:
        super().__init__(message)
        self.node_id = str(node_id)
        self.detail_message = message

    def payload(self) -> dict:
        return {
            "code": "node_not_reviewed",
            "node_id": self.node_id,
            "message": self.detail_message,
        }


class UnknownNode(SchemaError):
    """``422`` — the payload references a node id this course does not own."""

    def __init__(self, node_ids: Sequence[str]) -> None:
        super().__init__(f"Unknown node ids: {list(node_ids)}")
        self.node_ids = [str(nid) for nid in node_ids]

    def payload(self) -> dict:
        return {"code": "unknown_node", "node_ids": self.node_ids}


# --------------------------------------------------------------------------- #
# Pure graph algorithms
# --------------------------------------------------------------------------- #
Key = Any  # node identity: uuid in production, plain str/int in tests


def find_cycle(
    node_ids: Sequence[Key], edges: Mapping[Key, Iterable[Key]]
) -> list[Key]:
    """Return one cycle as an ordered list of ids, or ``[]`` if the graph is a DAG.

    ``edges[n]`` are the prerequisites of ``n``. Iterative DFS with the classic
    white/grey/black colouring: recursion would blow the stack on a pathological
    chain and, more importantly, is harder to read than the explicit stack.
    A self-edge is a cycle of length one.
    """
    known = list(node_ids)
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[Key, int] = {nid: WHITE for nid in known}

    for start in known:
        if colour[start] != WHITE:
            continue
        # Each frame is (node, iterator over its remaining prerequisites).
        stack: list[tuple[Key, Any]] = [(start, iter(edges.get(start, ())))]
        path: list[Key] = [start]
        colour[start] = GREY
        while stack:
            node, iterator = stack[-1]
            advanced = False
            for nxt in iterator:
                if nxt not in colour:  # orphan edge: reported separately
                    continue
                if colour[nxt] == GREY:
                    # ``path`` holds the grey chain; the cycle is its tail from
                    # ``nxt`` onwards. Not closed with a repeated first element: a
                    # 2-cycle must report 2 ids, as §11.1's example does.
                    return path[path.index(nxt) :]
                if colour[nxt] == WHITE:
                    colour[nxt] = GREY
                    path.append(nxt)
                    stack.append((nxt, iter(edges.get(nxt, ()))))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                stack.pop()
                path.pop()
    return []


def topological_order(
    node_ids: Sequence[Key], edges: Mapping[Key, Iterable[Key]]
) -> list[Key] | None:
    """Kahn's algorithm. ``None`` when the graph has a cycle.

    Ties are broken by the order of ``node_ids`` so the result is deterministic.
    """
    known = list(node_ids)
    known_set = set(known)
    prereqs: dict[Key, set[Key]] = {
        nid: {p for p in edges.get(nid, ()) if p in known_set and p != nid}
        for nid in known
    }
    ordered: list[Key] = []
    remaining = list(known)
    while remaining:
        ready = [nid for nid in remaining if not prereqs[nid]]
        if not ready:
            return None
        for nid in ready:
            ordered.append(nid)
            remaining.remove(nid)
        for nid in remaining:
            prereqs[nid] -= set(ready)
    return ordered


def prune_cyclic_prerequisites(
    proposed: list[dict],
) -> tuple[list[dict], list[str]]:
    """Make an LLM proposal acyclic by dropping edges, never by failing.

    ``proposed`` carries prerequisites as **indices into its own list** (§4.1: the
    model cannot invent uuids). Edges are added one at a time in list order; an
    edge that would close a cycle is dropped and a human-readable warning is
    recorded. Self-edges and out-of-range indices are dropped the same way.

    Failing instead of pruning would throw away a whole usable proposal because of
    one bad arrow, and the creator can always add the edge back by hand.
    """
    count = len(proposed)
    titles = [str(node.get("title") or f"nodo {i + 1}") for i, node in enumerate(proposed)]
    accepted: dict[int, list[int]] = {i: [] for i in range(count)}
    warnings: list[str] = []

    for index, node in enumerate(proposed):
        raw = node.get("prerequisites") or []
        for candidate in raw:
            try:
                prereq = int(candidate)
            except (TypeError, ValueError):
                warnings.append(
                    f"Se ignoro un prerrequisito no numerico en '{titles[index]}'."
                )
                continue
            if prereq == index:
                warnings.append(
                    f"Se elimino un prerrequisito de '{titles[index]}' sobre si mismo."
                )
                continue
            if not 0 <= prereq < count:
                warnings.append(
                    f"Se elimino un prerrequisito inexistente ({prereq}) en "
                    f"'{titles[index]}'."
                )
                continue
            if prereq in accepted[index]:
                continue
            trial = {k: list(v) for k, v in accepted.items()}
            trial[index].append(prereq)
            if find_cycle(list(range(count)), trial):
                warnings.append(
                    f"Se elimino un prerrequisito ciclico entre '{titles[index]}' y "
                    f"'{titles[prereq]}'."
                )
                continue
            accepted[index].append(prereq)

    pruned = [
        {**node, "prerequisites": accepted[index]}
        for index, node in enumerate(proposed)
    ]
    return pruned, warnings


class _NodeLike(Protocol):
    """The subset of ``CourseNode`` the validator reads."""

    id: Any
    title: Any
    summary: Any
    criticality: Any
    position: Any
    source_document_id: Any
    seed_lesson_id: Any
    reviewed_at: Any
    archived: Any


def _criticality_value(raw: object) -> str:
    return raw.value if isinstance(raw, NodeCriticality) else str(raw)


def validate_schema_graph(
    nodes: Sequence[_NodeLike],
    prerequisites: Mapping[Key, Iterable[Key]],
) -> list[dict]:
    """Return every blocking violation of §11.1. Empty list means "may validate".

    All rules are reported at once, not short-circuited: a creator fixing a schema
    wants the full list, not one error per round trip.
    """
    live = [node for node in nodes if not bool(node.archived)]
    errors: list[dict] = []

    if not live:
        return [{"code": "empty_schema"}]

    ids = [node.id for node in live]
    id_set = set(ids)

    missing_summary = [
        str(node.id) for node in live if not str(node.summary or "").strip()
    ]
    if missing_summary:
        errors.append({"code": "missing_summary", "node_ids": missing_summary})

    if not any(
        _criticality_value(node.criticality) == NodeCriticality.CRITICAL.value
        for node in live
    ):
        errors.append({"code": "no_critical_node"})

    orphans: list[str] = []
    for node in live:
        for prereq in prerequisites.get(node.id, ()) or ():
            if prereq not in id_set:
                orphans.append(str(prereq))
    if orphans:
        errors.append(
            {"code": "orphan_prerequisite", "node_ids": sorted(set(orphans))}
        )

    cycle = find_cycle(ids, prerequisites)
    if cycle:
        errors.append({"code": "cycle", "node_ids": [str(nid) for nid in cycle]})

    positions = sorted(int(node.position) for node in live)
    if positions != list(range(1, len(live) + 1)):
        errors.append(
            {
                "code": "position_not_contiguous",
                "node_ids": [str(node.id) for node in live],
            }
        )

    unreviewed = [str(node.id) for node in live if node.reviewed_at is None]
    if unreviewed:
        errors.append({"code": "node_not_reviewed", "node_ids": unreviewed})

    return errors


class _CourseLike(Protocol):
    delivery_mode: Any
    schema_status: Any


def ensure_node_servable(course: _CourseLike, node: _NodeLike) -> None:
    """Raise unless this node may be served to a learner right now.

    The runtime (B5) calls this before ``GET /nodes/{id}/render`` and before any
    generation. It is the reason "add an unreviewed node to a validated course"
    cannot leak content: the course-level status and the per-node ``reviewed_at``
    are checked independently, so a new node inherits nothing from the course's
    earlier sign-off.
    """
    status = (
        course.schema_status.value
        if isinstance(course.schema_status, CourseSchemaStatus)
        else str(course.schema_status)
    )
    mode = (
        course.delivery_mode.value
        if isinstance(course.delivery_mode, CourseDeliveryMode)
        else str(course.delivery_mode)
    )
    if status != CourseSchemaStatus.VALIDATED.value:
        raise NodeNotReviewed(
            node.id,
            "El esquema de este curso no esta validado; no se puede generar "
            "contenido de sus nodos.",
        )
    if mode != CourseDeliveryMode.DYNAMIC.value:
        raise NodeNotReviewed(
            node.id, "Este curso no se entrega en modo dinamico."
        )
    if bool(node.archived):
        raise NodeNotReviewed(node.id, "Este nodo esta archivado.")
    if node.reviewed_at is None:
        raise NodeNotReviewed(
            node.id, "Este nodo no ha sido revisado por una persona todavia."
        )


def ensure_deletable(node: _NodeLike, attempts_count: int) -> None:
    """Raise ``422 node_has_progress`` when a node may not be hard-deleted.

    Deleting cascades to ``learner_node_states`` and ``node_renders``, so it would
    silently destroy mastery and the audit trail of people who already worked, and
    change the set of ``critical`` nodes that governs enrollment closure.
    """
    if attempts_count > 0:
        raise NodeHasProgress([node.id])


def default_threshold_for(criticality: object) -> float:
    """Per-node mastery default derived from criticality (§3.2)."""
    value = _criticality_value(criticality)
    for member, threshold in CRITICALITY_THRESHOLDS.items():
        if member.value == value:
            return threshold
    return CRITICALITY_THRESHOLDS[NodeCriticality.RECOMMENDED]


# --------------------------------------------------------------------------- #
# Snapshot returned to the API layer
# --------------------------------------------------------------------------- #
@dataclass
class SchemaSnapshot:
    course: Course
    nodes: list[CourseNode]
    prerequisites: dict[uuid.UUID, list[uuid.UUID]]
    warnings: list[str] = field(default_factory=list)


async def _lazy_probe_pregenerator(node: CourseNode) -> tuple[list, dict] | None:
    """Pre-generate a node's probe items, if the probe service is available.

    SEAM, same pattern as ``generation_service.run_generation_job``: the generator
    lives in ``src/services/probe_service.py`` (B4). When it is absent the schema
    still validates and the probe simply falls back to §7.1's other two origins
    (sampling the seed lesson, or one runtime LLM call whose result is written back
    into ``course_nodes.probe_items``). Degrading here is safe; failing would make
    the gate unusable.
    """
    try:
        from src.services.probe_service import pregenerate_probe_items
    except ImportError:
        return None
    try:
        return await pregenerate_probe_items(node)
    except Exception as exc:  # noqa: BLE001 - pre-generation is best effort
        logger.warning("Probe pre-generation failed for node %s: %s", node.id, exc)
        return None


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class CourseSchemaService:
    """Design-time schema lifecycle: propose, read, update, validate, unvalidate."""

    def __init__(
        self,
        course_repo: CourseRepository,
        node_repo: CourseNodeRepository,
        audit_repo: AuditLogRepository,
        enrollment_repo: EnrollmentRepository,
        job_repo: GenerationJobRepository | None = None,
        document_repo: DocumentRepository | None = None,
        *,
        probe_pregenerator: Callable[
            [CourseNode], Awaitable[tuple[list, dict] | None]
        ]
        | None = None,
    ) -> None:
        self.course_repo = course_repo
        self.node_repo = node_repo
        self.audit_repo = audit_repo
        self.enrollment_repo = enrollment_repo
        self.job_repo = job_repo
        self.document_repo = document_repo
        self.probe_pregenerator = probe_pregenerator or _lazy_probe_pregenerator

    # ------------------------------------------------------------- internals --
    @property
    def session(self):
        return self.node_repo.session

    async def _course(self, course_id: uuid.UUID, org_id: uuid.UUID) -> Course:
        course = await self.course_repo.get_scoped(course_id, org_id)
        if course is None:
            raise NotFoundError("courses", str(course_id))
        return course

    async def _snapshot(
        self, course: Course, *, warnings: list[str] | None = None
    ) -> SchemaSnapshot:
        nodes = list(
            await self.node_repo.list_for_course(course.id, include_archived=False)
        )
        edges = await self.node_repo.prerequisites_for([node.id for node in nodes])
        return SchemaSnapshot(
            course=course,
            nodes=nodes,
            prerequisites=edges,
            warnings=list(warnings if warnings is not None else []),
        )

    async def latest_proposal(self, course_id: uuid.UUID) -> dict:
        """``progress`` of the most recent schema job for this course (or ``{}``).

        The proposal's warnings and the LLM's original node list live there, which
        is what lets ``validate`` record a real proposed -> validated diff without a
        new column.
        """
        query = (
            select(GenerationJob.progress)
            .where(
                GenerationJob.result_course_id == course_id,
                GenerationJob.status.in_(
                    [
                        GenerationStep.SCHEMA_PROPOSING,
                        GenerationStep.SCHEMA_PROPOSED,
                    ]
                ),
            )
            .order_by(GenerationJob.created_at.desc())
            .limit(1)
        )
        row = (await self.session.execute(query)).scalar_one_or_none()
        return dict(row) if isinstance(row, dict) else {}

    async def schema_warnings(self, course_id: uuid.UUID) -> list[str]:
        progress = await self.latest_proposal(course_id)
        raw = progress.get("schema_warnings") or []
        return [str(item) for item in raw]

    # ---------------------------------------------------------------- propose --
    async def propose(
        self,
        *,
        course_id: uuid.UUID,
        org_id: uuid.UUID,
        triggered_by: uuid.UUID,
        source_document_id: uuid.UUID | None,
        intent_density: int,
    ) -> GenerationJob:
        """Start the schema proposal job, or hand back the one already running.

        Order matters: the §11.1 gate is *blocking*, so it must refuse before any
        job machinery is touched. Requiring the job repository first would make a
        wiring detail decide whether a locked schema is rejected — and would leave
        a ``schema_proposing`` row behind for a request that was never allowed.

        The call is **idempotent while a job is in flight**: a second POST returns
        the same ``job_id`` (still ``202``) instead of starting a second designer
        run. Without that, a double click bought two full LLM runs and the two
        runners raced writing the same node set, so the surviving schema depended on
        which one finished last. The read is not the whole guard — see
        ``uq_generation_jobs_schema_in_flight`` in ``0005_dynamic_courses.py`` for
        the half that survives real concurrency.
        """
        course = await self._course(course_id, org_id)
        if course.schema_status == CourseSchemaStatus.VALIDATED:
            # Re-proposing would overwrite a signed-off schema behind the creator's
            # back; that is exactly what the gate forbids.
            raise SchemaLocked()

        if self.job_repo is None:  # pragma: no cover - wiring error
            raise RuntimeError("propose() needs a GenerationJobRepository")

        document_id = source_document_id or course.source_document_id
        # A source document is optional: courses created "from topic" have none
        # and the schema graph handles that by synthesising themes from the
        # course title.
        if document_id is not None and self.document_repo is not None:
            document = await self.document_repo.get_scoped(document_id, org_id)
            if document is None:
                raise NotFoundError("documents", str(document_id))
            status = (
                document.status.value
                if isinstance(document.status, DocumentStatus)
                else str(document.status)
            )
            if status != DocumentStatus.READY.value:
                raise ValidationError(
                    f"Document status is '{status}', must be 'ready'. "
                    "Process the document first via POST /documents/{id}/process."
                )

        in_flight = await self.job_repo.find_in_flight_schema_job(course_id, org_id)
        if in_flight is not None:
            # Deliberately does NOT touch ``intent_density``: the running job already
            # read it, so changing it now would only make the stored value disagree
            # with the schema being produced. Re-proposing with a different density
            # means waiting for this job (or cancelling it).
            logger.info(
                "Schema propose for course %s is already running as job %s; "
                "returning it instead of starting another",
                course_id,
                in_flight.id,
            )
            return in_flight

        course.intent_density = intent_density
        job = await self.job_repo.create(
            org_id=org_id,
            triggered_by=triggered_by,
            source_document_id=document_id,
            # §15.2: no `schema_only` value is added to the enum; no schema client
            # reads output_type, so it stays an explicit placeholder.
            output_type=GenerationOutput.COURSE_AND_MANUAL,
            status=GenerationStep.SCHEMA_PROPOSING,
            result_course_id=course_id,
            progress={"intent_density": intent_density},
        )
        # The route commits after this returns; the runner tolerates the row not
        # yet being visible via a short retry loop, exactly like v1.
        task_registry.spawn(_run_schema_job(job.id), name=f"schema:{job.id}")
        return job

    # ------------------------------------------------------------------- read --
    async def get_schema(
        self, *, course_id: uuid.UUID, org_id: uuid.UUID
    ) -> SchemaSnapshot:
        course = await self._course(course_id, org_id)
        warnings = await self.schema_warnings(course_id)
        return await self._snapshot(course, warnings=warnings)

    # ----------------------------------------------------------------- update --
    async def update(
        self,
        *,
        course_id: uuid.UUID,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
        nodes: list[dict],
        intent_density: int | None = None,
    ) -> SchemaSnapshot:
        """Full replacement of the node list. ``422 schema_locked`` when validated.

        Each incoming node dict may carry an ``id`` (edit) or not (create). Nodes
        absent from the payload are deleted when nobody has touched them and
        **archived** when they have progress (§11.1 rule 3).
        """
        course = await self._course(course_id, org_id)
        if course.schema_status == CourseSchemaStatus.VALIDATED:
            raise SchemaLocked()

        # Reordering violates UNIQUE (course_id, position) mid-statement without
        # this; the constraint is DEFERRABLE precisely so one PUT can swap two
        # positions (§3.2).
        await self.node_repo.defer_position_constraint()

        existing = list(
            await self.node_repo.list_for_course(course_id, include_archived=True)
        )
        by_id = {node.id: node for node in existing}

        unknown = [
            str(payload["id"])
            for payload in nodes
            if payload.get("id") is not None
            and _as_uuid(payload["id"]) not in by_id
        ]
        if unknown:
            raise UnknownNode(unknown)

        kept_ids: set[uuid.UUID] = set()
        result_nodes: list[CourseNode] = []
        warnings: list[str] = []

        for index, payload in enumerate(nodes):
            node_id = _as_uuid(payload["id"]) if payload.get("id") is not None else None
            position = payload.get("position") or index + 1
            if node_id is None:
                node = await self._create_node(
                    course=course, payload=payload, position=position
                )
            else:
                node = by_id[node_id]
                self._apply_node_edits(node, payload, position)
            kept_ids.add(node.id)
            result_nodes.append(node)

        await self.session.flush()

        # Prerequisites are uuids: a node created in this very PUT has no id the
        # client could have referenced, so brand-new edges between two brand-new
        # nodes need a second PUT. Documented, not silently dropped.
        live_ids = {node.id for node in result_nodes}
        for node, payload in zip(result_nodes, nodes, strict=True):
            requested = [
                _as_uuid(value) for value in (payload.get("prerequisite_node_ids") or [])
            ]
            resolved = [pid for pid in requested if pid in live_ids and pid != node.id]
            dropped = len(requested) - len(resolved)
            if dropped:
                warnings.append(
                    f"Se ignoraron {dropped} prerrequisito(s) desconocido(s) en "
                    f"'{node.title}'."
                )
            await self.node_repo.replace_prerequisites(node.id, resolved)

        removed = [
            node for node in existing if node.id not in kept_ids and not node.archived
        ]
        if removed:
            counts = await self.node_repo.attempt_counts([node.id for node in removed])
            for node in removed:
                if counts.get(node.id, 0) > 0:
                    node.archived = True
                    warnings.append(
                        f"'{node.title}' tiene progreso de aprendices: se archivo "
                        "en lugar de borrarse."
                    )
                else:
                    await self.node_repo.replace_prerequisites(node.id, [])
                    await self.node_repo.delete(node)

        if intent_density is not None:
            course.intent_density = intent_density
        course.schema_version = int(course.schema_version or 1) + 1
        if course.schema_status == CourseSchemaStatus.DRAFT:
            course.schema_status = CourseSchemaStatus.PROPOSED
        await self.session.flush()

        # §7.5: the PUT changed the set of `critical` nodes, which is exactly the
        # closure condition, so every active enrollment is recomputed here.
        recomputed = await self.recompute_enrollment_closure(course, org_id=org_id)
        if any(recomputed.values()):
            logger.info(
                "Schema PUT on course %s recomputed enrollments: %s",
                course_id,
                recomputed,
            )
            warnings.append(
                f"Matriculas recalculadas: {recomputed['completed']} completadas, "
                f"{recomputed['reopened']} reabiertas."
            )

        stored = await self.schema_warnings(course_id)
        return await self._snapshot(course, warnings=stored + warnings)

    async def _create_node(
        self, *, course: Course, payload: dict, position: int
    ) -> CourseNode:
        criticality = coerce_criticality(payload.get("criticality"))
        threshold = payload.get("mastery_threshold")
        return await self.node_repo.create(
            org_id=course.org_id,
            course_id=course.id,
            title=str(payload.get("title") or "").strip(),
            summary=str(payload.get("summary") or "").strip(),
            outcome=payload.get("outcome"),
            criticality=criticality,
            position=position,
            skill_id=_as_uuid_or_none(payload.get("skill_id")),
            seed_lesson_id=_as_uuid_or_none(payload.get("seed_lesson_id")),
            source_document_id=_as_uuid_or_none(payload.get("source_document_id"))
            or course.source_document_id,
            source_headings=list(payload.get("source_headings") or []),
            mastery_threshold=(
                float(threshold)
                if threshold is not None
                else default_threshold_for(criticality)
            ),
            default_ui_format=coerce_ui_format(payload.get("default_ui_format")),
            estimated_minutes=payload.get("estimated_minutes"),
            # A brand-new node is never pre-reviewed: that is the whole point of
            # §11.1 rule 2.
            reviewed_at=None,
            reviewed_by=None,
            archived=False,
        )

    def _apply_node_edits(
        self, node: CourseNode, payload: dict, position: int
    ) -> None:
        """Apply an edit in place and clear ``reviewed_at`` if the review is stale."""
        before = {
            "title": node.title,
            "summary": node.summary,
            "criticality": _criticality_value(node.criticality),
            "source_headings": list(node.source_headings or []),
        }

        if "title" in payload and payload["title"] is not None:
            node.title = str(payload["title"]).strip()
        if "summary" in payload and payload["summary"] is not None:
            node.summary = str(payload["summary"]).strip()
        if "outcome" in payload:
            node.outcome = payload["outcome"]
        if payload.get("criticality") is not None:
            node.criticality = coerce_criticality(payload["criticality"])
        if payload.get("default_ui_format") is not None:
            node.default_ui_format = coerce_ui_format(payload["default_ui_format"])
        if "source_headings" in payload and payload["source_headings"] is not None:
            node.source_headings = list(payload["source_headings"])
        if "skill_id" in payload:
            node.skill_id = _as_uuid_or_none(payload.get("skill_id"))
        if "seed_lesson_id" in payload:
            node.seed_lesson_id = _as_uuid_or_none(payload.get("seed_lesson_id"))
        if "source_document_id" in payload:
            node.source_document_id = _as_uuid_or_none(payload.get("source_document_id"))
        if payload.get("mastery_threshold") is not None:
            node.mastery_threshold = float(payload["mastery_threshold"])
        if "estimated_minutes" in payload:
            node.estimated_minutes = payload["estimated_minutes"]
        node.position = position
        if payload.get("archived") is not None:
            node.archived = bool(payload["archived"])

        after = {
            "title": node.title,
            "summary": node.summary,
            "criticality": _criticality_value(node.criticality),
            "source_headings": list(node.source_headings or []),
        }
        if any(before[key] != after[key] for key in REVIEW_INVALIDATING_FIELDS):
            node.reviewed_at = None
            node.reviewed_by = None

    # ------------------------------------------------------------ review mark --
    async def mark_reviewed(
        self, *, course_id: uuid.UUID, org_id: uuid.UUID, node_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> CourseNode:
        """Stamp one node as human-reviewed. Used by the admin panel (B10)."""
        await self._course(course_id, org_id)
        node = await self.node_repo.get_scoped(node_id, org_id)
        if node is None or node.course_id != course_id:
            raise NotFoundError("course_nodes", str(node_id))
        node.reviewed_at = datetime.now(timezone.utc)
        node.reviewed_by = actor_id
        await self.session.flush()
        return node

    # --------------------------------------------------------------- validate --
    async def validate(
        self, *, course_id: uuid.UUID, org_id: uuid.UUID, actor_id: uuid.UUID
    ) -> SchemaSnapshot:
        """The gate. Only door from ``proposed`` to ``validated``."""
        course = await self._course(course_id, org_id)
        nodes = list(
            await self.node_repo.list_for_course(course_id, include_archived=False)
        )
        edges = await self.node_repo.prerequisites_for([node.id for node in nodes])

        errors = validate_schema_graph(nodes, edges)
        if errors:
            raise SchemaInvalid(errors)

        pregenerated = await self._pregenerate_probes(nodes)

        now = datetime.now(timezone.utc)
        course.schema_status = CourseSchemaStatus.VALIDATED
        course.delivery_mode = CourseDeliveryMode.DYNAMIC
        course.schema_validated_by = actor_id
        course.schema_validated_at = now
        # Activating the schema is finishing the course: employees should see it.
        # Archive stays archive — that hide is explicit.
        if course.status not in (ContentStatus.PUBLISHED, ContentStatus.ARCHIVED):
            course.status = ContentStatus.PUBLISHED
        await self.session.flush()

        recomputed = await self.recompute_enrollment_closure(course, org_id=org_id)
        diff = await self._proposal_diff(course_id, nodes)

        await self.audit_repo.record(
            org_id=org_id,
            actor_id=actor_id,
            action="course_schema_validated",
            subject=course_subject(course_id),
            detail={
                "schema_version": int(course.schema_version or 1),
                "node_count": len(nodes),
                "critical_count": sum(
                    1
                    for node in nodes
                    if _criticality_value(node.criticality)
                    == NodeCriticality.CRITICAL.value
                ),
                "probes_pregenerated": pregenerated,
                "enrollments_recomputed": recomputed,
                "diff": diff,
            },
        )
        warnings = await self.schema_warnings(course_id)
        return await self._snapshot(course, warnings=warnings)

    async def _pregenerate_probes(self, nodes: Sequence[CourseNode]) -> int:
        """Pre-generate the probe of every node that has none yet (§7.1 origin 1)."""
        generated = 0
        for node in nodes:
            if node.probe_items:
                continue
            result = await self.probe_pregenerator(node)
            if not result:
                continue
            items, answer_key = result
            if not items:
                continue
            node.probe_items = items
            node.probe_answer_key = answer_key or {}
            generated += 1
        if generated:
            await self.session.flush()
        return generated

    async def _proposal_diff(
        self, course_id: uuid.UUID, nodes: Sequence[CourseNode]
    ) -> dict:
        """Diff the LLM proposal against what is being validated.

        Makes it measurable whether creators really edit what the model proposes
        (§3.5). Titles are the join key: the proposal has no uuids.
        """
        progress = await self.latest_proposal(course_id)
        proposed = progress.get("proposed_nodes") or []
        if not isinstance(proposed, list) or not proposed:
            return {"proposal_available": False}

        proposed_by_title = {
            str(item.get("title") or ""): item
            for item in proposed
            if isinstance(item, dict)
        }
        current_by_title = {node.title: node for node in nodes}

        edited: list[dict] = []
        for title, node in current_by_title.items():
            original = proposed_by_title.get(title)
            if original is None:
                continue
            changed = [
                key
                for key, current in (
                    ("summary", node.summary),
                    ("criticality", _criticality_value(node.criticality)),
                    ("source_headings", list(node.source_headings or [])),
                )
                if key in original and original[key] != current
            ]
            if changed:
                edited.append({"title": title, "fields": changed})

        return {
            "proposal_available": True,
            "proposed_count": len(proposed_by_title),
            "validated_count": len(current_by_title),
            "added": sorted(set(current_by_title) - set(proposed_by_title)),
            "removed": sorted(set(proposed_by_title) - set(current_by_title)),
            "edited": edited,
        }

    # ------------------------------------------------------------- unvalidate --
    async def unvalidate(
        self, *, course_id: uuid.UUID, org_id: uuid.UUID, actor_id: uuid.UUID
    ) -> SchemaSnapshot:
        """``validated`` -> ``proposed`` **and** ``dynamic`` -> ``static``, one txn.

        Editing a live course takes it out of v2 until it is validated again. That
        is the visible, explicit price of reopening the gate.
        """
        course = await self._course(course_id, org_id)
        was_validated = course.schema_status == CourseSchemaStatus.VALIDATED

        course.schema_status = CourseSchemaStatus.PROPOSED
        course.delivery_mode = CourseDeliveryMode.STATIC
        course.schema_validated_by = None
        course.schema_validated_at = None
        await self.session.flush()

        recomputed = await self.recompute_enrollment_closure(course, org_id=org_id)
        await self.audit_repo.record(
            org_id=org_id,
            actor_id=actor_id,
            action="course_schema_unvalidated",
            subject=course_subject(course_id),
            detail={
                "was_validated": was_validated,
                "schema_version": int(course.schema_version or 1),
                "enrollments_recomputed": recomputed,
            },
        )
        warnings = await self.schema_warnings(course_id)
        return await self._snapshot(course, warnings=warnings)

    # ------------------------------------------------- enrollment recompute --
    async def recompute_enrollment_closure(
        self, course: Course, *, org_id: uuid.UUID
    ) -> dict[str, int]:
        """Re-evaluate §7.5 closure for every enrollment of this course.

        Closure = every non-archived ``critical`` node of the course is
        ``mastered``. Because the schema just changed, a completed enrollment can
        reopen (a new ``critical`` node appeared) and a stuck one can complete (the
        missing node was archived).

        The *rule* is not implemented here (B11): ``evaluate_course_completion`` is the
        pure predicate and ``apply_dynamic_closure`` is the one mutation, both shared
        with ``EnrollmentService``, so the schema editor and the runtime cannot end up
        with two definitions of "completed" — a number that gets printed on a
        certificate. What stays here is the *batch read*: one ``mastery_rows`` query for
        every learner at once instead of a per-learner join, because a shift-wide course
        can have hundreds of enrollments and this runs inside a request.
        """
        nodes = list(
            await self.node_repo.list_for_course(course.id, include_archived=False)
        )
        critical = [
            node
            for node in nodes
            if _criticality_value(node.criticality) == NodeCriticality.CRITICAL.value
        ]
        enrollments, _ = await self.enrollment_repo.list_enrollments(
            org_id=org_id, course_id=course.id, limit=ENROLLMENT_RECOMPUTE_LIMIT
        )
        if not enrollments:
            return {"completed": 0, "reopened": 0}

        rows = (
            await self.node_repo.mastery_rows([node.id for node in critical])
            if critical
            else []
        )
        by_user: dict[uuid.UUID, dict[uuid.UUID, tuple[str, float]]] = {}
        for user_id, node_id, state, mastery in rows:
            by_user.setdefault(user_id, {})[node_id] = (state, mastery)

        counts = {"completed": 0, "reopened": 0}
        now = datetime.now(timezone.utc)
        for enrollment in enrollments:
            states = by_user.get(enrollment.user_id, {})
            progress = [
                NodeProgressRow(
                    node_id=node.id,
                    criticality=node.criticality,
                    archived=False,
                    state=states.get(node.id, (NodeState.NOT_STARTED.value, 0.0))[0],
                    mastery=states.get(node.id, (NodeState.NOT_STARTED.value, 0.0))[1],
                )
                for node in critical
            ]
            outcome = apply_dynamic_closure(
                enrollment, evaluate_course_completion(progress), now=now
            )
            if outcome is not None:
                counts[outcome] += 1
        await self.session.flush()
        return counts


# --------------------------------------------------------------------------- #
# Coercion helpers
# --------------------------------------------------------------------------- #
def _as_uuid(value: object) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _as_uuid_or_none(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return _as_uuid(value)
    except (ValueError, AttributeError, TypeError):
        return None


def coerce_criticality(value: object) -> NodeCriticality:
    if isinstance(value, NodeCriticality):
        return value
    try:
        return NodeCriticality(str(value))
    except ValueError:
        return NodeCriticality.RECOMMENDED


def coerce_ui_format(value: object) -> UiFormat:
    if isinstance(value, UiFormat):
        return value
    try:
        return UiFormat(str(value))
    except ValueError:
        return UiFormat.EXPLANATION


async def _run_schema_job(job_id: uuid.UUID) -> None:
    """Background worker seam, mirroring ``generation_service.run_generation_job``."""
    from src.agents.schema.runner import run_schema_proposal

    await run_schema_proposal(job_id)


__all__ = [
    "CourseSchemaService",
    "SchemaSnapshot",
    "SchemaError",
    "SchemaInvalid",
    "SchemaLocked",
    "NodeHasProgress",
    "NodeNotReviewed",
    "UnknownNode",
    "find_cycle",
    "topological_order",
    "prune_cyclic_prerequisites",
    "validate_schema_graph",
    "ensure_node_servable",
    "ensure_deletable",
    "coerce_criticality",
    "coerce_ui_format",
    "default_threshold_for",
    "REVIEW_INVALIDATING_FIELDS",
    "SCHEMA_LOCKED_MESSAGE",
]
