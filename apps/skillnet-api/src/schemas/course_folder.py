"""Contracts for flat course-library folders."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CourseFolderWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        clean = " ".join(value.split())
        if not clean:
            raise ValueError("must not be blank")
        return clean


class CourseFolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    course_count: int = 0
    created_at: datetime
    updated_at: datetime
