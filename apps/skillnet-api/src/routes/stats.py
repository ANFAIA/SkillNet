"""Admin dashboard statistics endpoint."""

import uuid

from fastapi import APIRouter
from sqlalchemy import func, literal, select, union_all

from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.models import (
    ContentStatus,
    Course,
    Enrollment,
    EnrollmentStatus,
    User,
    UserRole,
)
from src.schemas.stats import RecentActivityItem, StatsResponse

router = APIRouter(prefix="/stats", tags=["Stats"])


@router.get("", response_model=StatsResponse)
async def get_stats(admin: AdminUser, db: DBSession) -> StatsResponse:
    org_id: uuid.UUID = admin.org_id

    # --- Employee counts ---
    emp_q = select(
        func.count().label("total"),
        func.count().filter(User.is_active.is_(True)).label("active"),
    ).where(User.org_id == org_id, User.role == UserRole.EMPLOYEE)
    emp_row = (await db.execute(emp_q)).one()
    total_employees: int = emp_row.total
    active_employees: int = emp_row.active

    # --- Course counts ---
    # Excludes the pre-baked demo course (`is_demo`) seeded for the onboarding tour:
    # it isn't content the admin authored, so counting it as "published" or folding
    # its activity into the feed made a genuinely empty org look non-empty.
    course_q = select(
        func.count().label("total"),
        func.count()
        .filter(Course.status == ContentStatus.PUBLISHED)
        .label("published"),
        func.count()
        .filter(Course.status == ContentStatus.DRAFT)
        .label("draft"),
    ).where(Course.org_id == org_id, Course.is_demo.is_(False))
    course_row = (await db.execute(course_q)).one()
    total_courses: int = course_row.total
    published_courses: int = course_row.published
    draft_courses: int = course_row.draft

    # --- Enrollment counts ---
    enroll_q = (
        select(
            func.count().label("total"),
            func.count()
            .filter(Enrollment.status == EnrollmentStatus.COMPLETED)
            .label("completed"),
            func.count()
            .filter(Enrollment.status == EnrollmentStatus.IN_PROGRESS)
            .label("in_progress"),
        )
        .join(Course, Enrollment.course_id == Course.id)
        .where(Course.org_id == org_id, Course.is_demo.is_(False))
    )
    enroll_row = (await db.execute(enroll_q)).one()
    total_enrollments: int = enroll_row.total
    completed_enrollments: int = enroll_row.completed
    in_progress_enrollments: int = enroll_row.in_progress

    # --- Average score (only enrollments with a score) ---
    avg_q = (
        select(func.avg(Enrollment.score))
        .join(Course, Enrollment.course_id == Course.id)
        .where(
            Course.org_id == org_id,
            Course.is_demo.is_(False),
            Enrollment.score.isnot(None),
        )
    )
    avg_score: float | None = (await db.execute(avg_q)).scalar()

    # --- Recent activity (last 10 events) ---
    # Union of: completed enrollments, published courses, new employees
    completed_q = (
        select(
            literal("enrollment_completed").label("type"),
            User.full_name.label("user_name"),
            Course.title.label("course_title"),
            Enrollment.completed_at.label("at"),
        )
        .join(User, Enrollment.user_id == User.id)
        .join(Course, Enrollment.course_id == Course.id)
        .where(
            Course.org_id == org_id,
            Course.is_demo.is_(False),
            Enrollment.status == EnrollmentStatus.COMPLETED,
            Enrollment.completed_at.isnot(None),
        )
    )

    published_q = select(
        literal("course_published").label("type"),
        literal(None).label("user_name"),
        Course.title.label("course_title"),
        Course.updated_at.label("at"),
    ).where(
        Course.org_id == org_id,
        Course.is_demo.is_(False),
        Course.status == ContentStatus.PUBLISHED,
    )

    new_users_q = select(
        literal("user_created").label("type"),
        User.full_name.label("user_name"),
        literal(None).label("course_title"),
        User.created_at.label("at"),
    ).where(
        User.org_id == org_id,
        User.role == UserRole.EMPLOYEE,
    )

    activity_sub = union_all(completed_q, published_q, new_users_q).subquery()
    activity_q = (
        select(activity_sub).order_by(activity_sub.c.at.desc()).limit(10)
    )
    activity_rows = (await db.execute(activity_q)).all()

    recent_activity = [
        RecentActivityItem(
            type=row.type,
            user_name=row.user_name,
            course_title=row.course_title,
            at=row.at,
        )
        for row in activity_rows
    ]

    return StatsResponse(
        total_employees=total_employees,
        active_employees=active_employees,
        total_courses=total_courses,
        published_courses=published_courses,
        draft_courses=draft_courses,
        total_enrollments=total_enrollments,
        completed_enrollments=completed_enrollments,
        in_progress_enrollments=in_progress_enrollments,
        avg_score=round(avg_score, 2) if avg_score is not None else None,
        recent_activity=recent_activity,
    )
