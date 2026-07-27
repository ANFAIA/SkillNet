"""Document model (uploaded source material)."""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.models.document_chunk import DocumentChunk


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class DocumentOrigin(str, enum.Enum):
    """Where the text came from, and it is not a detail.

    ``UPLOADED`` is the company's own material: somebody chose it, and a course built
    on it can be defended. ``GENERATED`` is a source the model wrote from a one-line
    idea, so the course standing on it carries the model's knowledge and not the
    organisation's policy.

    A compliance course whose source silently turned out to be invented is the exact
    failure this product exists to avoid, so the distinction is a column and not a
    convention: it travels to every screen that shows a document, and the creator is
    told before the course is generated, not after.
    """

    UPLOADED = "uploaded"
    GENERATED = "generated"


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=DocumentStatus.PENDING,
    )
    origin: Mapped[DocumentOrigin] = mapped_column(
        SAEnum(
            DocumentOrigin,
            name="document_origin",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=DocumentOrigin.UPLOADED.value,
        default=DocumentOrigin.UPLOADED,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
