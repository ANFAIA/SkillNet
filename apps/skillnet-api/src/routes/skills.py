"""Internal administrator skill catalogue and course-skill assignment."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.repositories.skill_repo import SkillRepository
from src.schemas.common import PaginatedResponse
from src.schemas.skill import (
    CourseSkillsReplace,
    SkillCreate,
    SkillRead,
    SkillUpdate,
)
from src.services.skill_service import SkillService

router = APIRouter(tags=["Skills"])


def _service(db: DBSession) -> SkillService:
    return SkillService(SkillRepository(db))


@router.get("/skills", response_model=PaginatedResponse[SkillRead])
async def list_skills(
    admin: AdminUser,
    db: DBSession,
    search: Annotated[str | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[SkillRead]:
    rows, total = await _service(db).list_flat(
        org_id=admin.org_id, search=search, offset=offset, limit=limit
    )
    return PaginatedResponse[SkillRead](
        items=[SkillRead.model_validate(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/skills", response_model=SkillRead, status_code=201)
async def create_skill(
    admin: AdminUser, db: DBSession, body: SkillCreate
) -> SkillRead:
    skill = await _service(db).create_skill(
        org_id=admin.org_id, name=body.name, description=body.description
    )
    await db.commit()
    return SkillRead.model_validate(skill)


@router.put("/skills/{skill_id}", response_model=SkillRead)
async def update_skill(
    admin: AdminUser,
    db: DBSession,
    skill_id: uuid.UUID,
    body: SkillUpdate,
) -> SkillRead:
    skill = await _service(db).update_skill(
        org_id=admin.org_id,
        skill_id=skill_id,
        changes=body.model_dump(exclude_unset=True),
    )
    await db.commit()
    return SkillRead.model_validate(skill)


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill(
    admin: AdminUser, db: DBSession, skill_id: uuid.UUID
) -> Response:
    await _service(db).delete_skill(org_id=admin.org_id, skill_id=skill_id)
    await db.commit()
    return Response(status_code=204)


@router.get("/courses/{course_id}/skills", response_model=list[SkillRead])
async def list_course_skills(
    admin: AdminUser, db: DBSession, course_id: uuid.UUID
) -> list[SkillRead]:
    rows = await _service(db).list_course_skills(
        org_id=admin.org_id, course_id=course_id
    )
    return [SkillRead.model_validate(row) for row in rows]


@router.put("/courses/{course_id}/skills", response_model=list[SkillRead])
async def replace_course_skills(
    admin: AdminUser,
    db: DBSession,
    course_id: uuid.UUID,
    body: CourseSkillsReplace,
) -> list[SkillRead]:
    rows = await _service(db).replace_course_skills(
        org_id=admin.org_id,
        course_id=course_id,
        items=[item.model_dump() for item in body.skills],
    )
    await db.commit()
    return [SkillRead.model_validate(row) for row in rows]
