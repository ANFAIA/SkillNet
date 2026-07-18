"""Document routes: upload, list, fetch, delete, and processing trigger."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile

from src.core.exceptions import ValidationError
from src.core.tasks import task_registry
from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.models import DocumentStatus
from src.repositories.document_repo import DocumentRepository
from src.schemas.common import PaginatedResponse
from src.schemas.document import DocumentRead
from src.services.document_service import DocumentService, run_document_ingestion

router = APIRouter(prefix="/documents", tags=["Documents"])


def _service(db: DBSession) -> DocumentService:
    return DocumentService(DocumentRepository(db))


def _parse_status(status: str | None) -> DocumentStatus | None:
    if status is None:
        return None
    try:
        return DocumentStatus(status)
    except ValueError as exc:
        raise ValidationError(f"Invalid status: {status}", field="status") from exc


@router.get("", response_model=PaginatedResponse[DocumentRead])
async def list_documents(
    admin: AdminUser,
    db: DBSession,
    status: Annotated[str | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[DocumentRead]:
    service = _service(db)
    rows, total = await service.repo.list_documents(
        org_id=admin.org_id,
        status=_parse_status(status),
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse[DocumentRead](
        items=[DocumentRead.model_validate(d) for d in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=DocumentRead, status_code=201)
async def upload_document(
    admin: AdminUser, db: DBSession, file: Annotated[UploadFile, File()]
) -> DocumentRead:
    content = await file.read()
    service = _service(db)
    doc = await service.create_document(
        org_id=admin.org_id,
        uploaded_by=admin.id,
        filename=file.filename or "upload",
        content=content,
    )
    await db.commit()
    return DocumentRead.model_validate(doc)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    admin: AdminUser, db: DBSession, document_id: uuid.UUID
) -> DocumentRead:
    service = _service(db)
    doc = await service.get_document(document_id, admin.org_id)
    return DocumentRead.model_validate(doc)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    admin: AdminUser, db: DBSession, document_id: uuid.UUID
) -> Response:
    service = _service(db)
    await service.delete_document(document_id, admin.org_id)
    await db.commit()
    return Response(status_code=204)


@router.post("/{document_id}/process", status_code=202)
async def process_document(
    admin: AdminUser, db: DBSession, document_id: uuid.UUID
) -> dict:
    service = _service(db)
    doc = await service.mark_processing(document_id, admin.org_id)
    await db.commit()
    task_registry.spawn(
        run_document_ingestion(doc.id), name=f"ingest:{doc.id}"
    )
    return {"status": "processing"}
