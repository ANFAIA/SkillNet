"""Generation job response schema."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GenerationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    output_type: str
    progress: dict
    result_course_id: uuid.UUID | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
