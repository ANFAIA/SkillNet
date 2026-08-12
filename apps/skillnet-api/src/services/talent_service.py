"""Assemble factual course progress and earned-skill views for administrators."""

import uuid

from src.core.exceptions import NotFoundError
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.lesson_progress_repo import LessonProgressRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.talent_repo import TalentRepository
from src.services.enrollment_service import EnrollmentService
from src.services.skill_service import SkillService


class TalentService:
    def __init__(self, repo: TalentRepository) -> None:
        self.repo = repo

    def _enrollment_service(self) -> EnrollmentService:
        session = self.repo.session
        return EnrollmentService(
            EnrollmentRepository(session),
            CourseRepository(session),
            ExerciseRepository(session),
            LessonProgressRepository(session),
        )

    async def list_people(self, **kwargs) -> tuple[list[dict], int]:
        rows, total = await self.repo.list_people(**kwargs)
        return [
            {
                "user_id": row["user"].id,
                "full_name": row["user"].full_name,
                "email": row["user"].email,
                **{key: value for key, value in row.items() if key != "user"},
            }
            for row in rows
        ], total

    async def person_detail(self, *, org_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        user = await self.repo.get_person(org_id, user_id)
        if user is None:
            raise NotFoundError("users", str(user_id))
        enrollments = await self.repo.person_enrollments(org_id, user_id)
        enrollment_service = self._enrollment_service()
        courses = []
        for enrollment in enrollments:
            progress = await enrollment_service.compute_progress(
                enrollment=enrollment, org_id=org_id
            )
            courses.append(
                {
                    "course_id": enrollment.course_id,
                    "title": enrollment.course.title,
                    "status": enrollment.status.value,
                    "progress": progress,
                    "started_at": enrollment.started_at,
                    "completed_at": enrollment.completed_at,
                }
            )
        skill_service = SkillService(SkillRepository(self.repo.session))
        user_skills = await skill_service.get_user_skills(org_id, user_id)
        skills = []
        for user_skill in user_skills:
            sources = await self.repo.skill_source_courses(
                org_id, user_id, user_skill["skill_id"]
            )
            skills.append(
                {
                    **user_skill,
                    "source_courses": [
                        {
                            "course_id": source.course_id,
                            "title": source.course.title,
                            "status": source.status.value,
                            "progress": 1.0,
                            "started_at": source.started_at,
                            "completed_at": source.completed_at,
                        }
                        for source in sources
                    ],
                }
            )
        return {
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "courses": courses,
            "skills": skills,
        }

    async def list_courses(self, org_id: uuid.UUID) -> list[dict]:
        return [
            {
                "course_id": row["course"].id,
                "title": row["course"].title,
                **{key: value for key, value in row.items() if key != "course"},
            }
            for row in await self.repo.list_courses(org_id)
        ]

    async def list_skills(self, org_id: uuid.UUID) -> list[dict]:
        return [
            {
                "skill_id": row["skill"].id,
                "name": row["skill"].name,
                "description": row["skill"].description,
                "people_count": row["people_count"],
                "course_count": row["course_count"],
            }
            for row in await self.repo.list_skills_summary(org_id)
        ]
