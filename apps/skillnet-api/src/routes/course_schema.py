"""Admin course-schema routes (§11.1): propose, read, edit, validate, unvalidate.

``SchemaError`` is translated into a plain ``HTTPException`` here rather than
handled globally: §11.1 fixes a nested ``detail`` body
(``{"detail": {"code": "schema_invalid", "errors": [...]}}``) and FastAPI's default
``HTTPException`` rendering produces exactly that, whereas the app-wide ``AppError``
handler flattens ``detail`` to a string.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException

from src.core.exceptions import NotFoundError
from src.core.tasks import task_registry
from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.deps.llm import GenerationLLMDep
from src.knowledge_pack.configured_generator import ConfiguredKnowledgePackGenerator
from src.knowledge_pack.runner import (
    KnowledgePackRunnerDependencies,
    spawn_packs_for_schema,
)
from src.models import CourseGenerationState
from src.repositories.audit_log_repo import AuditLogRepository
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.document_repo import DocumentRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.generation_job_repo import GenerationJobRepository
from src.repositories.node_knowledge_pack_repo import NodeKnowledgePackRepository
from src.schemas.course_schema import (
    CourseFinalizationRead,
    CourseNodeRead,
    CourseSchemaRead,
    CourseSchemaUpdate,
    CourseKnowledgePacksRead,
    NodeKnowledgePackRead,
    NodeReviewResponse,
    SchemaProposeRequest,
    SchemaProposeResponse,
)
from src.services import course_finalization
from src.services.course_schema_service import (
    CourseSchemaService,
    SchemaError,
    SchemaSnapshot,
)
from src.services.node_render_service import spawn_prewarm_first_nodes

router = APIRouter(
    prefix="/courses",
    tags=["Course Schema"],
)


def _service(db: DBSession) -> CourseSchemaService:
    return CourseSchemaService(
        CourseRepository(db),
        CourseNodeRepository(db),
        AuditLogRepository(db),
        EnrollmentRepository(db),
        GenerationJobRepository(db),
        DocumentRepository(db),
    )


@contextlib.contextmanager
def _structured_errors() -> Iterator[None]:
    """Render ``SchemaError`` with the exact nested ``detail`` body of §11.1."""
    try:
        yield
    except SchemaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload()) from exc


def _read(snapshot: SchemaSnapshot) -> CourseSchemaRead:
    course = snapshot.course
    nodes = [
        CourseNodeRead(
            id=node.id,
            title=node.title,
            summary=node.summary,
            outcome=node.outcome,
            criticality=node.criticality.value,
            position=node.position,
            mastery_threshold=float(node.mastery_threshold),
            estimated_minutes=node.estimated_minutes,
            default_ui_format=node.default_ui_format.value,
            skill_id=node.skill_id,
            seed_lesson_id=node.seed_lesson_id,
            source_document_id=node.source_document_id,
            source_headings=list(node.source_headings or []),
            prerequisite_node_ids=list(snapshot.prerequisites.get(node.id) or []),
            reviewed_at=node.reviewed_at,
            reviewed_by=node.reviewed_by,
            archived=bool(node.archived),
        )
        for node in snapshot.nodes
    ]
    return CourseSchemaRead(
        course_id=course.id,
        schema_status=course.schema_status.value,
        schema_version=int(course.schema_version or 1),
        delivery_mode=course.delivery_mode.value,
        intent_density=int(course.intent_density or 3),
        validated_by=course.schema_validated_by,
        validated_at=course.schema_validated_at,
        warnings=list(snapshot.warnings),
        nodes=nodes,
    )


@router.post(
    "/{course_id}/schema/propose",
    response_model=SchemaProposeResponse,
    status_code=202,
)
async def propose_schema(
    admin: AdminUser,
    db: DBSession,
    course_id: uuid.UUID,
    body: SchemaProposeRequest | None = None,
) -> SchemaProposeResponse:
    payload = body or SchemaProposeRequest()
    with _structured_errors():
        job = await _service(db).propose(
            course_id=course_id,
            org_id=admin.org_id,
            triggered_by=admin.id,
            source_document_id=payload.source_document_id,
            intent_density=payload.intent_density,
        )
    await db.commit()
    return SchemaProposeResponse(job_id=str(job.id))


@router.get("/{course_id}/schema", response_model=CourseSchemaRead)
async def get_schema(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseSchemaRead:
    with _structured_errors():
        snapshot = await _service(db).get_schema(
            course_id=course_id, org_id=admin.org_id
        )
    return _read(snapshot)


@router.put("/{course_id}/schema", response_model=CourseSchemaRead)
async def update_schema(
    admin: AdminUser,
    db: DBSession,
    llm: GenerationLLMDep,
    course_id: uuid.UUID,
    body: CourseSchemaUpdate,
) -> CourseSchemaRead:
    with _structured_errors():
        snapshot = await _service(db).update(
            course_id=course_id,
            org_id=admin.org_id,
            actor_id=admin.id,
            nodes=[node.model_dump(exclude_unset=False) for node in body.nodes],
            intent_density=body.intent_density,
        )
    await db.commit()
    spawn_packs_for_schema(
        course_id,
        admin.org_id,
        int(snapshot.course.schema_version or 1),
        dependencies=KnowledgePackRunnerDependencies(
            generator=ConfiguredKnowledgePackGenerator(llm),
            # Retry a transient failure / lost-snapshot race / repairable review_required
            # pack a bounded number of times so a fresh course reaches "all nodes ready"
            # without a human re-triggering generation.
            max_attempts=3,
        ),
    )
    return _read(snapshot)


@router.post("/{course_id}/schema/review", response_model=CourseSchemaRead)
async def review_all_nodes(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseSchemaRead:
    """Mark every non-archived node of the course human-reviewed in one call.

    The §11.1 gate requires a ``reviewed_at`` on each node before ``validate`` can open,
    and the create wizard used to stamp them one HTTP call at a time (any silent failure
    left ``validate`` returning ``409 node_not_reviewed``). Finishing course creation is
    the owner's single act of sign-off, so this endpoint records it atomically for the
    whole graph: the wizard calls it right before ``validate`` and no node is left behind.
    """
    with _structured_errors():
        service = _service(db)
        snapshot = await service.get_schema(course_id=course_id, org_id=admin.org_id)
        for node in snapshot.nodes:
            if node.reviewed_at is None and not node.archived:
                await service.mark_reviewed(
                    course_id=course_id,
                    org_id=admin.org_id,
                    node_id=node.id,
                    actor_id=admin.id,
                )
        await db.commit()
        snapshot = await service.get_schema(course_id=course_id, org_id=admin.org_id)
    return _read(snapshot)


@router.post("/{course_id}/schema/validate", response_model=CourseSchemaRead)
async def validate_schema(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseSchemaRead:
    with _structured_errors():
        snapshot = await _service(db).validate(
            course_id=course_id, org_id=admin.org_id, actor_id=admin.id
        )
    await db.commit()
    # A validated course is now servable, but its node *renders* do not exist yet: the
    # first learner to open a node would otherwise pay the full generation latency as the
    # "Preparándose…" wait. Warm the first nodes' shared renders in the background (once
    # their packs are ready) so that very first open is an instant cache hit.
    spawn_prewarm_first_nodes(
        course_id,
        admin.org_id,
        int(snapshot.course.schema_version or 1),
        admin.id,
    )
    return _read(snapshot)


def _finalization(status: course_finalization.FinalizationStatus) -> CourseFinalizationRead:
    return CourseFinalizationRead(
        course_id=status.course_id,
        generation_state=status.generation_state,
        generation_error=status.generation_error,
        generation_failed_at=status.generation_failed_at,
        schema_status=status.schema_status,
        status=status.status,
        packs_ready=status.packs_ready,
        packs_total=status.packs_total,
    )


@router.post(
    "/{course_id}/schema/finalize",
    response_model=CourseFinalizationRead,
    status_code=202,
)
async def finalize_schema(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseFinalizationRead:
    """Finish creating this course on the server: wait for packs, review, validate.

    The three steps behind this 202 used to run as three round trips from the create
    wizard's tab, and ``validate`` is the only thing in the system that publishes a v2
    course — so a tab that stopped executing part-way through stranded the course as a
    draft forever, with nothing recording that a run had died. Now the browser makes one
    call and watches ``GET`` on this same path; closing the tab changes nothing.

    Idempotent by design. The claim is committed here, and the task is spawned under a
    per-course name, so a second call adopts the run already in flight instead of
    pushing a rival one through review and validate.
    """
    repo = CourseRepository(db)
    course = await repo.get_scoped(course_id, admin.org_id)
    if course is None:
        raise NotFoundError("courses", str(course_id))

    already_running = (
        course.generation_state is CourseGenerationState.IN_PROGRESS
        and task_registry.has_running(f"{course_finalization.TASK_PREFIX}{course_id}")
    )
    if not already_running:
        course_finalization.claim(course)
        await db.commit()
        await db.refresh(course)
        course_finalization.spawn(course_id, admin.org_id, admin.id)

    return _finalization(await course_finalization.read_status(db, course=course))


@router.get("/{course_id}/schema/finalize", response_model=CourseFinalizationRead)
async def get_finalization(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseFinalizationRead:
    """The wizard's single watch call: run state plus knowledge-pack progress."""
    course = await CourseRepository(db).get_scoped(course_id, admin.org_id)
    if course is None:
        raise NotFoundError("courses", str(course_id))
    return _finalization(await course_finalization.read_status(db, course=course))


@router.post("/{course_id}/schema/unvalidate", response_model=CourseSchemaRead)
async def unvalidate_schema(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseSchemaRead:
    with _structured_errors():
        snapshot = await _service(db).unvalidate(
            course_id=course_id, org_id=admin.org_id, actor_id=admin.id
        )
    await db.commit()
    return _read(snapshot)


@router.post(
    "/{course_id}/schema/nodes/{node_id}/review",
    response_model=NodeReviewResponse,
)
async def mark_node_reviewed(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID, node_id: uuid.UUID
) -> NodeReviewResponse:
    """Stamp one node as human-reviewed.

    §11.1 rule 2 makes ``reviewed_at`` a serving precondition, and the admin panel
    (B10) marks a node reviewed when the creator opens and edits it. Without this
    endpoint the gate could never be opened for any node, so ``validate`` would be
    permanently unreachable.
    """
    with _structured_errors():
        node = await _service(db).mark_reviewed(
            course_id=course_id,
            org_id=admin.org_id,
            node_id=node_id,
            actor_id=admin.id,
        )
    await db.commit()
    return NodeReviewResponse(
        node_id=node.id, reviewed_at=node.reviewed_at, reviewed_by=node.reviewed_by
    )


@router.get(
    "/{course_id}/schema/knowledge-packs",
    response_model=CourseKnowledgePacksRead,
)
async def get_knowledge_packs(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> CourseKnowledgePacksRead:
    """Inspection-only pack details embedded in the existing schema screen."""
    with _structured_errors():
        snapshot = await _service(db).get_schema(
            course_id=course_id, org_id=admin.org_id
        )
    schema_version = int(snapshot.course.schema_version or 1)
    rows = await NodeKnowledgePackRepository(db).latest_for_schema(
        course_id=course_id,
        org_id=admin.org_id,
        schema_version=schema_version,
    )
    nodes: list[NodeKnowledgePackRead] = []
    for row in rows:
        payload = dict(row.pack_payload or {})
        atoms = list(row.atoms or [])
        gaps = [
            str(item.get("description") or item.get("data_id") or "")
            for item in payload.get("missing_data", [])
            if isinstance(item, dict) and item.get("blocking")
        ]
        nodes.append(
            NodeKnowledgePackRead(
                id=row.id,
                node_id=row.node_id,
                status=row.status.value,
                generator_version=row.generator_version,
                pack_hash=row.pack_hash,
                markdown=row.markdown,
                atom_count=len(atoms),
                invariant_count=sum(
                    item.get("category") == "must_preserve"
                    for item in atoms
                    if isinstance(item, dict)
                ),
                required_evidence_count=sum(
                    bool(item.get("required"))
                    for item in payload.get("evidence_specs", [])
                    if isinstance(item, dict)
                ),
                blocking_gaps=[gap for gap in gaps if gap],
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                duration_ms=row.duration_ms,
                error_message=row.error_message,
                updated_at=row.updated_at,
            )
        )
    return CourseKnowledgePacksRead(
        course_id=course_id,
        schema_version=schema_version,
        nodes=nodes,
    )
