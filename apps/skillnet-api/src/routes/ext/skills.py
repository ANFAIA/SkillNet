"""External skills endpoints — authenticated via API key."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from src.deps.db import DBSession
from src.repositories.skill_repo import SkillRepository
from src.routes.ext.auth import ExtApiKey
from src.schemas.skill import (
    GapReport,
    GapReportEntry,
    SkillCategoryRead,
    UserSkillRead,
    VerifySkillRequest,
    VerifySkillResponse,
    WhoKnowsEntry,
    WhoKnowsResponse,
)
from src.services.skill_service import SkillService

router = APIRouter(prefix="/skills", tags=["Skills (external)"])

# Separate router for user-scoped paths that don't share the /skills prefix.
user_router = APIRouter(prefix="/users", tags=["Skills (external)"])


def _service(db: DBSession) -> SkillService:
    return SkillService(SkillRepository(db))


@router.get("", response_model=list[SkillCategoryRead])
async def list_skills(
    api_key: ExtApiKey,
    db: DBSession,
) -> list[SkillCategoryRead]:
    service = _service(db)
    categories = await service.list_skills(api_key.org_id)
    return [SkillCategoryRead(**c) for c in categories]


@router.get("/who-knows", response_model=WhoKnowsResponse)
async def who_knows(
    api_key: ExtApiKey,
    db: DBSession,
    skill: Annotated[str, Query(description="Skill name to search for")],
    min_level: Annotated[str | None, Query(description="Minimum level: low, medium, high")] = None,
) -> WhoKnowsResponse:
    service = _service(db)
    employees = await service.who_knows(api_key.org_id, skill, min_level)
    return WhoKnowsResponse(
        skill=skill,
        employees=[WhoKnowsEntry(**e) for e in employees],
    )


@router.get("/gaps", response_model=GapReport)
async def get_gaps(
    api_key: ExtApiKey,
    db: DBSession,
) -> GapReport:
    service = _service(db)
    gaps = await service.get_gap(api_key.org_id)
    return GapReport(gaps=[GapReportEntry(**g) for g in gaps])


@router.post("/verify", response_model=VerifySkillResponse, status_code=200)
async def verify_skill(
    api_key: ExtApiKey,
    db: DBSession,
    body: VerifySkillRequest,
) -> VerifySkillResponse:
    service = _service(db)
    result = await service.verify_skill(
        org_id=api_key.org_id,
        user_id=body.user_id,
        skill_name=body.skill_name,
        level=body.level,
        source=body.source,
    )
    await db.commit()
    return VerifySkillResponse(**result)


@user_router.get("/{user_id}/skills", response_model=list[UserSkillRead])
async def get_user_skills(
    api_key: ExtApiKey,
    db: DBSession,
    user_id: uuid.UUID,
) -> list[UserSkillRead]:
    service = _service(db)
    skills = await service.get_user_skills(api_key.org_id, user_id)
    return [UserSkillRead(**s) for s in skills]
