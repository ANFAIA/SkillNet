"""Admin course-schema routes (§11.1): propose, read, edit, validate, unvalidate.

Every route is behind ``require_dynamic_courses("admin")``, so with the flag ``off``
the whole surface 404s and is indistinguishable from routes that do not exist.

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

from fastapi import APIRouter, Depends, HTTPException

from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.deps.features import require_dynamic_courses
from src.repositories.audit_log_repo import AuditLogRepository
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.document_repo import DocumentRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.generation_job_repo import GenerationJobRepository
from src.schemas.course_schema import (
    CourseNodeRead,
    CourseSchemaRead,
    CourseSchemaUpdate,
    NodeReviewResponse,
    SchemaProposeRequest,
    SchemaProposeResponse,
)
from src.services.course_schema_service import (
    CourseSchemaService,
    SchemaError,
    SchemaSnapshot,
)

router = APIRouter(
    prefix="/courses",
    tags=["Course Schema"],
    dependencies=[Depends(require_dynamic_courses("admin"))],
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
    return _read(snapshot)


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
