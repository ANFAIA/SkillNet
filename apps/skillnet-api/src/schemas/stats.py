"""Dashboard statistics response schema."""

from datetime import datetime

from pydantic import BaseModel


class RecentActivityItem(BaseModel):
    type: str
    user_name: str | None = None
    course_title: str | None = None
    at: datetime


class StatsResponse(BaseModel):
    """What the admin dashboard shows. No mark, deliberately.

    It carried ``avg_score`` — ``AVG(enrollments.score)`` — until 2026-08-29. It is gone
    because **there are no exams**: nothing in the product grades a course, so an average
    mark had nothing to average. The column made that worse rather than causing it, by
    holding two different quantities on one 0..1 scale (the completed-lessons fraction on
    the v1 path, and mean node mastery in the v2 rows written before that date), which no
    query can separate after the fact. ``enrollments.score`` itself stays: it is the
    history of enrollments already closed, and v1 still writes it. What the dashboard
    reports about outcomes is the completion rate, which is the one thing every course
    here actually asserts.
    """

    total_employees: int
    active_employees: int
    total_courses: int
    published_courses: int
    draft_courses: int
    total_enrollments: int
    completed_enrollments: int
    in_progress_enrollments: int
    overdue_assignments: int
    recent_activity: list[RecentActivityItem]
