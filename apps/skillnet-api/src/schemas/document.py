"""Document response schema."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
