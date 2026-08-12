"""Minimal administrator Talent registry: people, courses and skills."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.models import EnrollmentStatus
from src.repositories.talent_repo import TalentRepository
from src.schemas.common import PaginatedResponse
from src.schemas.talent import (
    TalentCourseSummary,
    TalentPersonDetail,
    TalentPersonSummary,
    TalentSkillSummary,
)
from src.services.talent_service import TalentService

router = APIRouter(prefix="/talent", tags=["Talent"])


def _service(db: DBSession) -> TalentService:
    return TalentService(TalentRepository(db))


@router.get("/people", response_model=PaginatedResponse[TalentPersonSummary])
async def list_people(
    admin: AdminUser,
    db: DBSession,
    search: Annotated[str | None, Query()] = None,
    course_id: Annotated[uuid.UUID | None, Query()] = None,
    skill_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[EnrollmentStatus | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[TalentPersonSummary]:
    rows, total = await _service(db).list_people(
        org_id=admin.org_id,
        search=search,
        course_id=course_id,
        skill_id=skill_id,
        status=status,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse[TalentPersonSummary](
        items=[TalentPersonSummary(**row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/people/{user_id}", response_model=TalentPersonDetail)
async def person_detail(
    admin: AdminUser, db: DBSession, user_id: uuid.UUID
) -> TalentPersonDetail:
    return TalentPersonDetail(
        **await _service(db).person_detail(org_id=admin.org_id, user_id=user_id)
    )


@router.get("/courses", response_model=list[TalentCourseSummary])
async def list_courses(
    admin: AdminUser, db: DBSession
) -> list[TalentCourseSummary]:
    return [TalentCourseSummary(**row) for row in await _service(db).list_courses(admin.org_id)]


@router.get("/skills", response_model=list[TalentSkillSummary])
async def list_skills(
    admin: AdminUser, db: DBSession
) -> list[TalentSkillSummary]:
    return [TalentSkillSummary(**row) for row in await _service(db).list_skills(admin.org_id)]
