"""Document business logic: validated upload to disk and ingestion seam."""

import uuid
from pathlib import Path

from src.config import settings
from src.core.exceptions import AppError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.llm.client import LLMService
from src.llm.prompts.source import SOURCE_WRITER_SYSTEM, build_source_prompt
from src.models import Document, DocumentOrigin, DocumentStatus
from src.repositories.document_repo import DocumentRepository

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}

#: Generous, because the source is the input to the whole generation pipeline and a
#: thin one produces a thin course. Four to eight Markdown sections land well inside it.
SOURCE_MAX_TOKENS = 3000

#: Below this the model returned something that is not a document — an apology, an empty
#: string, a one-line refusal. Better to fail the request than to build a course on it.
_MIN_SOURCE_CHARS = 400


def _strip_code_fence(text: str) -> str:
    """Unwrap a whole-response ```` ``` ```` fence, and only that.

    Conservative on purpose: it unwraps only when the text both opens and closes with a
    fence, so a document that legitimately contains a fenced snippet in the middle is
    left exactly as written.
    """
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return text
    return "\n".join(lines[1:-1]).strip()


class DocumentService:
    def __init__(self, repo: DocumentRepository) -> None:
        self.repo = repo

    async def create_document(
        self,
        *,
        org_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        filename: str,
        content: bytes,
    ) -> Document:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Unsupported file type: {ext or '(none)'}", field="file"
            )
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise AppError(
                f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit",
                code="PAYLOAD_TOO_LARGE",
                status_code=413,
                field="file",
            )

        # Create the row first so the generated id can key the storage path.
        doc = await self.repo.create(
            org_id=org_id,
            uploaded_by=uploaded_by,
            title=filename,
            storage_path="",
            file_type=ext.lstrip("."),
            size_bytes=len(content),
            status=DocumentStatus.PENDING,
        )
        target_dir = Path(settings.UPLOAD_DIR) / str(org_id) / str(doc.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"original{ext}"
        target_path.write_bytes(content)
        return await self.repo.update(doc, storage_path=str(target_path))

    async def create_from_idea(
        self,
        *,
        org_id: uuid.UUID,
        created_by: uuid.UUID,
        title: str,
        idea: str,
        llm: LLMService,
    ) -> Document:
        """Write a source document from a one-line idea, then hand it to normal ingestion.

        The "desde cero" path in one method, and deliberately no more than that. The
        model writes Markdown, the Markdown is written to disk exactly where an upload
        would live, and the row that comes out is a plain ``Document`` with
        ``file_type='md'``. From here on nothing else in the system knows the difference:
        ``ingest_document`` parses, chunks and embeds it, the v1 pipeline extracts themes
        from it, the v2 designer picks node sources from its headings and the tutor
        retrieves from its chunks. That is the entire reason for synthesising a document
        instead of teaching the pipeline to work without one — the alternative is a
        second, less-tested path through every stage.

        ``origin=GENERATED`` is the one thing that *is* different, and it is a column so
        it cannot be lost. See :class:`~src.models.document.DocumentOrigin`.

        Status is ``PENDING`` on return: the caller commits and then spawns ingestion,
        the same two steps ``POST /documents/{id}/process`` performs.
        """
        clean_title = title.strip()
        if not clean_title:
            raise ValidationError("A title is required to write a source", field="title")

        text = (
            await llm.complete(
                SOURCE_WRITER_SYSTEM,
                build_source_prompt(title=clean_title, idea=idea),
                max_tokens=SOURCE_MAX_TOKENS,
                # Higher than the pipeline's 0.3: this call is writing prose from a
                # one-line brief rather than restructuring a document, and at 0.3 the
                # sections come out formulaic and near-identical between topics.
                temperature=0.6,
            )
        ).strip()
        # Models wrap long Markdown in a fence about a third of the time even when told
        # not to. Stripping it here is cheaper than a repair call and cannot lose content.
        text = _strip_code_fence(text)

        if len(text) < _MIN_SOURCE_CHARS:
            raise AppError(
                "The model did not return a usable source document for this topic. "
                "Try again with a more specific description.",
                code="SOURCE_GENERATION_FAILED",
                status_code=502,
            )

        return await self.persist_generated_markdown(
            org_id=org_id,
            created_by=created_by,
            title=clean_title,
            text=text,
        )

    async def persist_generated_markdown(
        self,
        *,
        org_id: uuid.UUID,
        created_by: uuid.UUID | None,
        title: str,
        text: str,
        status: DocumentStatus = DocumentStatus.PENDING,
        full_text: str | None = None,
        page_count: int | None = None,
    ) -> Document:
        """Write already-authored Markdown to the same place an upload would live.

        ``create_from_idea`` uses this after the course-wide writer. Per-node briefs
        use it after the schema exists, with ``full_text`` set so the runtime can
        read the excerpt before ingestion finishes.
        """
        clean_title = title.strip()
        if not clean_title:
            raise ValidationError("A title is required to write a source", field="title")
        body = _strip_code_fence(text.strip())
        payload: dict[str, object] = {
            "org_id": org_id,
            "uploaded_by": created_by,
            "title": clean_title,
            "storage_path": "",
            "file_type": "md",
            "size_bytes": len(body.encode("utf-8")),
            "status": status,
            "origin": DocumentOrigin.GENERATED,
        }
        if full_text is not None:
            payload["full_text"] = full_text
        if page_count is not None:
            payload["page_count"] = page_count
        doc = await self.repo.create(**payload)
        target_dir = Path(settings.UPLOAD_DIR) / str(org_id) / str(doc.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "generated.md"
        target_path.write_text(body, encoding="utf-8")
        return await self.repo.update(doc, storage_path=str(target_path))

    async def get_document(self, doc_id: uuid.UUID, org_id: uuid.UUID) -> Document:
        doc = await self.repo.get_scoped(doc_id, org_id)
        if doc is None:
            raise NotFoundError("documents", str(doc_id))
        return doc

    async def delete_document(self, doc_id: uuid.UUID, org_id: uuid.UUID) -> None:
        doc = await self.get_document(doc_id, org_id)
        storage_path = doc.storage_path
        await self.repo.delete(doc)
        # Best-effort file cleanup; DB rows (chunks) cascade at the model level.
        try:
            path = Path(storage_path)
            if path.exists():
                path.unlink()
                parent = path.parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
        except OSError as exc:
            logger.warning("Could not remove files for document %s: %s", doc_id, exc)

    async def mark_processing(self, doc_id: uuid.UUID, org_id: uuid.UUID) -> Document:
        doc = await self.get_document(doc_id, org_id)
        return await self.repo.update(doc, status=DocumentStatus.PROCESSING)


async def run_document_ingestion(document_id: uuid.UUID) -> None:
    """Background worker: hand off to the Phase 5 ingestion pipeline (lazy import).

    SEAM: ``src.services.ingestion`` does not exist until Phase 5. Until then we
    fail the document gracefully so Phase 3 stays importable and runnable.
    """
    try:
        from src.services.ingestion import ingest_document
    except ImportError:
        logger.warning(
            "Ingestion pipeline unavailable (Phase 5 not built); "
            "marking document %s as error",
            document_id,
        )
        async with async_session_factory() as session:
            repo = DocumentRepository(session)
            doc = await repo.get_by_id(document_id)
            if doc is not None:
                await repo.update(
                    doc,
                    status=DocumentStatus.ERROR,
                    error_message="Document ingestion pipeline is not available yet.",
                )
            await session.commit()
        return

    await ingest_document(document_id)
