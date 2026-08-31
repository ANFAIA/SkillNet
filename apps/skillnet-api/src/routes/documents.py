"""Document routes: upload, list, fetch, delete, processing trigger, and source images."""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Query, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.exceptions import AppError, NotFoundError, ValidationError
from src.core.language import Language, accept_language, normalize_language
from src.core.logging import get_logger
from src.core.tasks import task_registry
from src.deps.auth import AdminUser, CurrentUser
from src.deps.db import DBSession
from src.deps.llm import LLMDep
from src.models import DocumentStatus, SourceImage
from src.repositories.document_repo import DocumentRepository
from src.repositories.source_image_repo import SourceImageRepository
from src.schemas.common import PaginatedResponse
from src.schemas.document import DocumentRead, SourceImageRead
from src.services.language_policy import ambient_language
from src.services.document_service import DocumentService, run_document_ingestion
from src.services.source_images import IMAGE_EXTENSIONS, SourceImageStore

logger = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

#: The wire code a client keys its "these bytes are gone" message off. Deliberately the
#: same string as media's ``asset_missing`` (``src/services/media/jobs.py``): to a client
#: the incident is identical whether the lost file was a generated artefact or an image
#: extracted from a document, so it must not need two messages for it. Spelled out rather
#: than imported so this route does not pull the whole media job machinery in for one
#: string; it is a wire contract, so it cannot drift without breaking clients anyway.
ASSET_MISSING_CODE = "asset_missing"

#: Image ids whose loss this process has already logged, so a learner reloading a lesson
#: with a lost figure does not print the same error line fifty times. The media fix records
#: "already reported" durably by demoting the row; ``source_images`` has no status column
#: (see :class:`SourceImageMissingError`), so the memory is per process and bounded: a
#: restart re-reporting once is the right trade for a set that can never grow without end.
_reported_missing: set[uuid.UUID] = set()

#: Distinct lost images remembered before the memory is dropped and starts again. Far more
#: than any real incident needs — a document has tens of images, not thousands — and the
#: point of the cap is only that a hostile or pathological caller cannot grow the set.
_REPORTED_MISSING_CAP = 512


class SourceImageMissingError(AppError):
    """The image was extracted and stored, and its file is no longer on this server.

    ``410 Gone`` rather than ``404``, for the reason
    :class:`~src.services.media.integrity.AssetMissingError` gives: the resource existed,
    the reference is valid, and a client that reads ``404`` cannot tell "this document
    never had that image" from "this deployment lost its source-image volume". Neither can
    an operator reading an access log.

    Unlike a media artefact, the row cannot be demoted to a failure state to stop it
    claiming bytes it no longer has: ``source_images`` has no status column. So the status
    code and the ``error`` log line **are** the whole report here, which is what makes the
    distinction load-bearing rather than a nicety. Recovery is the same shape in both
    stores, and both directions still work: the store is content-addressed, so restoring
    the volume brings the same bytes back at the same path and this route starts answering
    ``200`` again with nothing to undo, and re-processing the document re-extracts them.
    """

    def __init__(self, *, document_id: uuid.UUID, image_id: uuid.UUID) -> None:
        super().__init__(
            message=(
                "The image extracted from this document is no longer stored on this "
                "server. Process the document again."
            ),
            code=ASSET_MISSING_CODE,
            status_code=410,
            details={"document_id": str(document_id), "image_id": str(image_id)},
        )


def _report_missing_source_image(image: SourceImage, path: Path) -> None:
    """Log a lost source image once per process, at ``error``, with what locates it.

    ``error`` because that is what it is — the deployment lost customer material it still
    has a record of — and the path is in the line because it is the only thing that tells
    the operator which volume went missing.
    """
    if image.id in _reported_missing:
        logger.debug("Source image %s is already recorded as missing", image.id)
        return
    if len(_reported_missing) >= _REPORTED_MISSING_CAP:
        _reported_missing.clear()
    _reported_missing.add(image.id)
    logger.error(
        "Source image %s of document %s is recorded in source_images but %s is not on "
        "disk. Re-process the document to extract it again, or restore the source-image "
        "volume — the store is content-addressed, so a file back at that path is the same "
        "image. If this is every image at once, the volume was lost, not one file.",
        image.id,
        image.document_id,
        path,
    )


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
    #: What the document — and therefore the whole course built from it — comes out in.
    #: ``None`` means nobody chose, and the route falls back to ``Accept-Language``.
    language: Language | None = None

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: object) -> object:
        """Accept a locale tag where the field declares a language.

        A client sends what it has, and what a browser has is ``en-US``. Rejecting it
        with a 422 that names two valid values would push every caller into writing
        this line instead. An unrecognised tag becomes ``None`` rather than an error,
        for the reason ``normalize_language`` gives: a language nobody supports is
        indistinguishable from a language nobody asked for.
        """
        return normalize_language(value) if isinstance(value, str) else value


@router.post("/from-idea", response_model=DocumentRead, status_code=201)
async def create_document_from_idea(
    admin: AdminUser,
    db: DBSession,
    llm: LLMDep,
    body: SourceFromIdeaRequest,
    request: Request,
) -> DocumentRead:
    """Write a source document from an idea, then ingest it like any upload.

    The front half of "crear curso desde cero". It returns a normal ``Document`` in
    ``processing``, so the caller carries on down the ordinary path: create the course
    with this ``source_document_id`` and generate, or open the v2 schema screen. Nothing
    downstream branches on where the text came from — only the UI does, and only to say
    so. Declared **above** ``/{document_id}`` because ``from-idea`` would otherwise be
    parsed as a UUID path parameter and 422.

    The language cascade ends at the request headers on purpose. The body field is the
    creator's choice and wins; ``Accept-Language`` is only what the browser happens to
    be set to, so it goes through ``ambient_language`` and Spanish — the language every
    prompt already writes unprompted — reads as "nothing to say" rather than as an
    instruction. That is what keeps the existing path unchanged for the clients that
    have never heard of this field.
    """
    language = body.language or ambient_language(
        accept_language(request.headers.get("accept-language"))
    )
    service = _service(db)
    doc = await service.create_from_idea(
        org_id=admin.org_id,
        created_by=admin.id,
        title=body.title,
        idea=body.idea,
        llm=llm,
        language=language,
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
    user: CurrentUser, db: DBSession, document_id: uuid.UUID, image_id: uuid.UUID
) -> Response:
    """The stored bytes of one extracted image, or ``404`` / ``410``.

    Any member of the organization, not only an admin: a lesson may **place** one of
    these images (the ``SourceImage`` component of the kit — see
    ``src/agents/runtime/source_image_broker.py``), so the learner looking at that lesson
    has to be able to fetch the bytes. Listing stays admin-only, so this widens nothing
    that can be enumerated: both path parameters are unguessable UUIDs, the row is still
    resolved with both the org *and* the owning document, and the only ids a learner ever
    receives are the ones their own render already embedded.

    Same shape and the same discipline as ``GET /media/artifacts/{id}/asset``. Traversal
    is impossible by construction and then again by check: both path parameters are parsed
    as UUIDs by FastAPI, so no user-supplied text reaches the filesystem at all, and the
    path is *rebuilt* from the row (``org_id``, ``document_id``, ``content_hash``,
    extension) rather than taken from the stored ``asset_path`` string — with the hash
    required to be an anchored 64-character hex digest and the extension allow-listed, so
    a row corrupted by any future writer still cannot address a file outside the store.

    Three absences, and they are three different incidents, so they do not answer alike —
    the same criterion as ``GET /media/artifacts/{id}/asset`` (see
    :mod:`src.services.media.integrity`):

    * **No such row** for this org and this document is a ``404``. Normal, and nobody's
      fault: nothing was ever extracted under that id.
    * **A row this store could never have written** — a hash or an extension that fails
      :meth:`~src.services.source_images.SourceImageStore.path_for` — is also a ``404``,
      because there is no file to go looking for, but it is logged at ``error``: no writer
      in this codebase can produce such a row, so one existing is a bug, not a lost file.
    * **A row whose file is gone** is a ``410 asset_missing``, logged at ``error`` once per
      image (:func:`_report_missing_source_image`). This is the case that used to be a mute
      ``404``: the volume holding the customer's own material had been lost, every request
      answered not-found for ever, and nothing anywhere recorded that the rows and the disk
      disagreed. See :class:`SourceImageMissingError` for why the row is not demoted.

    The existence check is the read itself, so a healthy request pays for no extra syscall.
    """
    image = await SourceImageRepository(db).get_scoped(
        image_id, user.org_id, document_id
    )
    if image is None:
        raise NotFoundError("source_images", str(image_id))

    ext = Path(image.asset_path).suffix.lstrip(".").lower()
    store = SourceImageStore()
    try:
        path = store.path_for(image.org_id, image.document_id, image.content_hash, ext)
    except ValueError as exc:
        logger.error(
            "Source image %s of document %s cannot address a file in the store (%s); its "
            "content_hash or its asset_path extension is not one this store writes.",
            image.id,
            image.document_id,
            exc,
        )
        raise NotFoundError("source_images", str(image_id)) from exc

    try:
        data = store.read(path)
    except FileNotFoundError as exc:
        _report_missing_source_image(image, path)
        raise SourceImageMissingError(
            document_id=document_id, image_id=image_id
        ) from exc

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
