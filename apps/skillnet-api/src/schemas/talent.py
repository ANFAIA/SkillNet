"""Small, factual administrator views of learning and earned skills."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TalentPersonSummary(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    assigned_count: int
    in_progress_count: int
    completed_count: int
    skill_count: int
    last_activity_at: datetime | None = None


class TalentCourseProgress(BaseModel):
    course_id: uuid.UUID
    title: str
    status: str
    progress: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TalentSkillEntry(BaseModel):
    skill_id: uuid.UUID
    skill_name: str
    level: str
    source: str
    last_assessed_at: datetime | None = None
    source_courses: list[TalentCourseProgress] = Field(default_factory=list)


class TalentPersonDetail(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    courses: list[TalentCourseProgress]
    skills: list[TalentSkillEntry]


class TalentCourseSummary(BaseModel):
    course_id: uuid.UUID
    title: str
    assigned_count: int
    in_progress_count: int
    completed_count: int
    skills: list[str]


class TalentSkillSummary(BaseModel):
    skill_id: uuid.UUID
    name: str
    description: str | None = None
    people_count: int
    course_count: int
