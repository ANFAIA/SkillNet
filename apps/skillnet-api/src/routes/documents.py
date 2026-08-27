"""Document routes: upload, list, fetch, delete, processing trigger, and source images."""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from src.core.exceptions import NotFoundError, ValidationError
from src.core.tasks import task_registry
from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.deps.llm import LLMDep
from src.models import DocumentStatus
from src.repositories.document_repo import DocumentRepository
from src.repositories.source_image_repo import SourceImageRepository
from src.schemas.common import PaginatedResponse
from src.schemas.document import DocumentRead, SourceImageRead
from src.services.document_service import DocumentService, run_document_ingestion
from src.services.source_images import IMAGE_EXTENSIONS, SourceImageStore

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
    counts = await SourceImageRepository(db).count_reusable([d.id for d in rows])
    return PaginatedResponse[DocumentRead](
        items=[
            DocumentRead.of(d, reusable_image_count=counts.get(d.id, 0)) for d in rows
        ],
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


class SourceFromIdeaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    #: What the creator wants covered. Optional — a title alone is a thin but legitimate
    #: brief, and the prompt says so explicitly rather than guessing at an empty string.
    idea: str = Field(default="", max_length=4000)


@router.post("/from-idea", response_model=DocumentRead, status_code=201)
async def create_document_from_idea(
    admin: AdminUser, db: DBSession, llm: LLMDep, body: SourceFromIdeaRequest
) -> DocumentRead:
    """Write a source document from an idea, then ingest it like any upload.

    The front half of "crear curso desde cero". It returns a normal ``Document`` in
    ``processing``, so the caller carries on down the ordinary path: create the course
    with this ``source_document_id`` and generate, or open the v2 schema screen. Nothing
    downstream branches on where the text came from — only the UI does, and only to say
    so. Declared **above** ``/{document_id}`` because ``from-idea`` would otherwise be
    parsed as a UUID path parameter and 422.
    """
    service = _service(db)
    doc = await service.create_from_idea(
        org_id=admin.org_id,
        created_by=admin.id,
        title=body.title,
        idea=body.idea,
        llm=llm,
    )
    doc = await service.repo.update(doc, status=DocumentStatus.PROCESSING)
    await db.commit()
    task_registry.spawn(run_document_ingestion(doc.id), name=f"ingest:{doc.id}")
    return DocumentRead.model_validate(doc)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    admin: AdminUser, db: DBSession, document_id: uuid.UUID
) -> DocumentRead:
    service = _service(db)
    doc = await service.get_document(document_id, admin.org_id)
    counts = await SourceImageRepository(db).count_reusable([doc.id])
    return DocumentRead.of(doc, reusable_image_count=counts.get(doc.id, 0))


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    admin: AdminUser, db: DBSession, document_id: uuid.UUID
) -> Response:
    service = _service(db)
    await service.delete_document(document_id, admin.org_id)
    await db.commit()
    return Response(status_code=204)


@router.get("/{document_id}/images", response_model=list[SourceImageRead])
async def list_document_images(
    admin: AdminUser,
    db: DBSession,
    document_id: uuid.UUID,
    include_decorative: Annotated[bool, Query()] = False,
) -> list[SourceImageRead]:
    """The images kept from inside this document, in reading order.

    Furniture (the header logo, the rule under every title) is excluded by default:
    ``include_decorative=true`` is there so a human can look at what the deterministic
    filter rejected and disagree with it, which is the reason those rows are kept at all.

    Org scope comes from resolving the document first — an image is only reachable
    through the document that owns it.
    """
    await _service(db).get_document(document_id, admin.org_id)
    images = await SourceImageRepository(db).list_for_document(
        document_id, include_decorative=include_decorative
    )
    return [SourceImageRead.model_validate(image) for image in images]


@router.get("/{document_id}/images/{image_id}")
async def get_document_image(
    admin: AdminUser, db: DBSession, document_id: uuid.UUID, image_id: uuid.UUID
) -> Response:
    """The stored bytes of one extracted image, or ``404``.

    Same shape and the same discipline as ``GET /media/artifacts/{id}/asset``. Traversal
    is impossible by construction and then again by check: both path parameters are parsed
    as UUIDs by FastAPI, so no user-supplied text reaches the filesystem at all, and the
    path is *rebuilt* from the row (``org_id``, ``document_id``, ``content_hash``,
    extension) rather than taken from the stored ``asset_path`` string — with the hash
    required to be an anchored 64-character hex digest and the extension allow-listed, so
    a row corrupted by any future writer still cannot address a file outside the store.
    """
    image = await SourceImageRepository(db).get_scoped(
        image_id, admin.org_id, document_id
    )
    if image is None:
        raise NotFoundError("source_images", str(image_id))

    ext = Path(image.asset_path).suffix.lstrip(".").lower()
    store = SourceImageStore()
    try:
        path = store.path_for(image.org_id, image.document_id, image.content_hash, ext)
        data = store.read(path)
    except (ValueError, FileNotFoundError) as exc:
        # The row points at bytes that are gone (or at something this store would never
        # have written). A 404 the client can handle, not a 500.
        raise NotFoundError("source_images", str(image_id)) from exc

    return Response(
        content=data,
        media_type=IMAGE_EXTENSIONS[ext],
        # Content-addressed: these bytes never change under this id.
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


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
