"""Dashboard statistics response schema."""

from datetime import datetime

from pydantic import BaseModel


class RecentActivityItem(BaseModel):
    type: str
    user_name: str | None = None
    course_title: str | None = None
    at: datetime


class StatsResponse(BaseModel):
    total_employees: int
    active_employees: int
    total_courses: int
    published_courses: int
    draft_courses: int
    total_enrollments: int
    completed_enrollments: int
    in_progress_enrollments: int
    avg_score: float | None
    recent_activity: list[RecentActivityItem]
