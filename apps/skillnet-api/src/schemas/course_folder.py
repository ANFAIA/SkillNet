"""Contracts for flat course-library folders."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class CourseFolderAssignmentCreate(BaseModel):
    """Who gets this folder: named people, whole groups, or both.

    ``user_ids`` lost its ``min_length=1`` when ``group_ids`` arrived — an order that
    names only a group is valid — so the "say who" rule moved to the validator, where it
    can name both fields in one message.
    """

    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    #: Resolved to their members on the server. Same field, same meaning and the same
    #: single expansion point as ``EnrollmentCreate.group_ids``.
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    deadline: date | None = None

    @model_validator(mode="after")
    def someone_to_assign(self) -> "CourseFolderAssignmentCreate":
        if not self.user_ids and not self.group_ids:
            raise ValueError("Provide user_ids or group_ids")
        return self


class CourseFolderAssignmentResult(BaseModel):
    """Same three counts, in the same names, as ``EnrollmentAssignmentResult``.

    It is the same operation reached from the other side (folder -> people instead of
    people -> folder), and one vocabulary for it keeps the two screens' wording honest.
    """

    course_count: int
    created_count: int
    skipped_existing_count: int
    person_count: int = 0
    skipped_inactive_count: int = 0
