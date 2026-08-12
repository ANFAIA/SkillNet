"""Read model for the deliberately factual Talent administration surface."""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import (
    Course,
    CourseSkill,
    Enrollment,
    EnrollmentStatus,
    Skill,
    User,
    UserRole,
    UserSkill,
)


class TalentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_people(
        self,
        *,
        org_id: uuid.UUID,
        search: str | None,
        course_id: uuid.UUID | None,
        skill_id: uuid.UUID | None,
        status: EnrollmentStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        filters = [User.org_id == org_id, User.role == UserRole.EMPLOYEE]
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(User.full_name.ilike(pattern), User.email.ilike(pattern))
            )
        if course_id or status:
            enrollment_filters = [Enrollment.user_id == User.id]
            if course_id:
                enrollment_filters.append(Enrollment.course_id == course_id)
            if status:
                enrollment_filters.append(Enrollment.status == status)
            filters.append(
                select(Enrollment.id).where(*enrollment_filters).exists()
            )
        if skill_id:
            filters.append(
                User.id.in_(
                    select(UserSkill.user_id).where(UserSkill.skill_id == skill_id)
                )
            )

        enrollment_scope = [Enrollment.user_id == User.id]
        if course_id:
            enrollment_scope.append(Enrollment.course_id == course_id)

        assigned = (
            select(func.count(Enrollment.id))
            .where(*enrollment_scope)
            .correlate(User)
            .scalar_subquery()
        )
        in_progress = (
            select(func.count(Enrollment.id))
            .where(
                *enrollment_scope,
                Enrollment.status == EnrollmentStatus.IN_PROGRESS,
            )
            .correlate(User)
            .scalar_subquery()
        )
        completed = (
            select(func.count(Enrollment.id))
            .where(
                *enrollment_scope,
                Enrollment.status == EnrollmentStatus.COMPLETED,
            )
            .correlate(User)
            .scalar_subquery()
        )
        skill_count = (
            select(func.count(UserSkill.id))
            .where(UserSkill.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        last_activity = (
            select(
                func.max(
                    func.coalesce(
                        Enrollment.completed_at,
                        Enrollment.started_at,
                        Enrollment.created_at,
                    )
                )
            )
            .where(*enrollment_scope)
            .correlate(User)
            .scalar_subquery()
        )
        stmt = (
            select(User, assigned, in_progress, completed, skill_count, last_activity)
            .where(*filters)
            .order_by(User.full_name)
            .offset(offset)
            .limit(limit)
        )
        count_stmt = select(func.count()).select_from(User).where(*filters)
        rows = (await self.session.execute(stmt)).all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return [
            {
                "user": row[0],
                "assigned_count": row[1],
                "in_progress_count": row[2],
                "completed_count": row[3],
                "skill_count": row[4],
                "last_activity_at": row[5],
            }
            for row in rows
        ], total

    async def get_person(self, org_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(
            User.id == user_id,
            User.org_id == org_id,
            User.role == UserRole.EMPLOYEE,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def person_enrollments(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Enrollment]:
        stmt = (
            select(Enrollment)
            .join(Course, Course.id == Enrollment.course_id)
            .where(Enrollment.user_id == user_id, Course.org_id == org_id)
            .options(selectinload(Enrollment.course))
            .order_by(Enrollment.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def skill_source_courses(
        self, org_id: uuid.UUID, user_id: uuid.UUID, skill_id: uuid.UUID
    ) -> list[Enrollment]:
        stmt = (
            select(Enrollment)
            .join(Course, Course.id == Enrollment.course_id)
            .join(CourseSkill, CourseSkill.course_id == Course.id)
            .where(
                Course.org_id == org_id,
                Enrollment.user_id == user_id,
                Enrollment.status == EnrollmentStatus.COMPLETED,
                CourseSkill.skill_id == skill_id,
            )
            .options(selectinload(Enrollment.course))
            .order_by(Enrollment.completed_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_courses(self, org_id: uuid.UUID) -> list[dict]:
        stmt = (
            select(
                Course,
                func.count(Enrollment.id),
                func.count(Enrollment.id).filter(
                    Enrollment.status == EnrollmentStatus.IN_PROGRESS
                ),
                func.count(Enrollment.id).filter(
                    Enrollment.status == EnrollmentStatus.COMPLETED
                ),
            )
            .outerjoin(Enrollment, Enrollment.course_id == Course.id)
            .where(Course.org_id == org_id)
            .group_by(Course.id)
            .order_by(Course.title)
        )
        result = []
        for course, assigned, progress, completed in (await self.session.execute(stmt)).all():
            skills = await self.session.execute(
                select(Skill.name)
                .join(CourseSkill, CourseSkill.skill_id == Skill.id)
                .where(CourseSkill.course_id == course.id)
                .order_by(Skill.name)
            )
            result.append(
                {
                    "course": course,
                    "assigned_count": assigned,
                    "in_progress_count": progress,
                    "completed_count": completed,
                    "skills": list(skills.scalars().all()),
                }
            )
        return result

    async def list_skills_summary(self, org_id: uuid.UUID) -> list[dict]:
        people = (
            select(func.count(UserSkill.id))
            .where(UserSkill.skill_id == Skill.id)
            .correlate(Skill)
            .scalar_subquery()
        )
        courses = (
            select(func.count(CourseSkill.id))
            .where(CourseSkill.skill_id == Skill.id)
            .correlate(Skill)
            .scalar_subquery()
        )
        stmt = (
            select(Skill, people, courses)
            .where(Skill.org_id == org_id)
            .order_by(Skill.name)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "skill": row[0],
                "people_count": row[1],
                "course_count": row[2],
            }
            for row in rows
        ]
