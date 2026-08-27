"""Document response schema."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SourceImageRead(BaseModel):
    """One image kept from inside the document, with the provenance a caption needs."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page: int
    heading: str
    width: int
    height: int
    bytes: int
    #: What a vision model saw, or ``None`` when no ``VISION_MODEL`` was configured.
    description: str | None = None
    #: ``screenshot`` | ``diagram`` | ``photo`` | ``unknown``. What the picture *is*, which
    #: is what decides whether a lesson may rebuild it or has to show it as it is. Always
    #: ``"unknown"`` when nothing classified it — no vision model, or an unusable answer.
    #: See :class:`~src.models.source_image.SourceImageKind`.
    kind: str = "unknown"


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    file_type: str
    page_count: int | None = None
    size_bytes: int | None = None
    status: str
    #: ``"uploaded"`` or ``"generated"``. The client shows it, because a course built on
    #: a source the model wrote is not the same claim as one built on company material.
    #: See :class:`~src.models.document.DocumentOrigin`.
    origin: str = "uploaded"
    error_message: str | None = None
    created_at: datetime
    #: How many images extracted from this document are worth reusing — the ones the
    #: deterministic filter did NOT mark as furniture. Zero for anything that is not a
    #: processed PDF. It travels on the read schema so the creation screen can offer (or
    #: grey out) "reuse the document's own images" *before* the course is generated,
    #: rather than after, when the only remedy is regenerating it.
    reusable_image_count: int = 0

    @classmethod
    def of(cls, document: Any, *, reusable_image_count: int = 0) -> "DocumentRead":
        """Build from an ORM ``Document``, with the image count the row cannot carry.

        The count is a query over another table, so it is passed in rather than made a
        ``column_property``: a correlated subquery on the mapper would fire on every
        ``Document`` load in the whole application, including the generation pipeline's,
        to serve two routes.
        """
        read = cls.model_validate(document)
        return read.model_copy(update={"reusable_image_count": reusable_image_count})
