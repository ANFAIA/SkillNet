"""Skill schemas: taxonomy, who-knows, gaps, and verification."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ------------------------------------------------------------------
# Read schemas
# ------------------------------------------------------------------


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value is not None else None


class CourseSkillInput(BaseModel):
    id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value is not None else None

    @model_validator(mode="after")
    def require_reference(self) -> "CourseSkillInput":
        if self.id is None and self.name is None:
            raise ValueError("id or name is required")
        return self


class CourseSkillsReplace(BaseModel):
    skills: list[CourseSkillInput] = Field(max_length=20)


class SkillCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    name: str
    position: int
    skills: list[SkillRead] = []


class UserSkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    skill_id: uuid.UUID
    skill_name: str
    level: str
    source: str
    last_assessed_at: datetime | None = None


# ------------------------------------------------------------------
# Create schemas
# ------------------------------------------------------------------


class SkillCategoryCreate(BaseModel):
    name: str
    position: int = 0


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())


# ------------------------------------------------------------------
# Response schemas
# ------------------------------------------------------------------


class WhoKnowsEntry(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    level: str


class WhoKnowsResponse(BaseModel):
    skill: str
    employees: list[WhoKnowsEntry]


class GapReportEntry(BaseModel):
    skill_name: str
    total_users: int
    low: int
    medium: int
    high: int


class GapReport(BaseModel):
    gaps: list[GapReportEntry]


class VerifySkillRequest(BaseModel):
    user_id: uuid.UUID
    skill_name: str
    level: str
    source: str = "checkpoint"


class VerifySkillResponse(BaseModel):
    user_skill_id: uuid.UUID
    user_id: uuid.UUID
    skill_id: uuid.UUID
    skill_name: str
    level: str
    source: str
