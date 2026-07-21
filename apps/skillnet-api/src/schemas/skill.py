"""Skill schemas: taxonomy, who-knows, gaps, and verification."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ------------------------------------------------------------------
# Read schemas
# ------------------------------------------------------------------


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None


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
    name: str
    description: str | None = None
    category_id: uuid.UUID | None = None


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
