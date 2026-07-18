"""Document business logic: validated upload to disk and ingestion seam."""

import uuid
from pathlib import Path

from src.config import settings
from src.core.exceptions import AppError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.models import Document, DocumentStatus
from src.repositories.document_repo import DocumentRepository

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


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
