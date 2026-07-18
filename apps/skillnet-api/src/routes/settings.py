"""Organization settings routes (admin): read config, configure + test the LLM."""

from __future__ import annotations

from fastapi import APIRouter

from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.schemas.settings import LLMConfigUpdate, LLMTestResult, OrgSettingsRead
from src.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=OrgSettingsRead)
async def get_settings(admin: AdminUser, db: DBSession) -> OrgSettingsRead:
    return await SettingsService(db).get_settings()


@router.put("/llm", response_model=OrgSettingsRead)
async def update_llm(
    admin: AdminUser, db: DBSession, body: LLMConfigUpdate
) -> OrgSettingsRead:
    service = SettingsService(db)
    result = await service.update_llm(
        model=body.model, base_url=body.base_url, api_key=body.api_key
    )
    await db.commit()
    return result


@router.post("/llm/test", response_model=LLMTestResult)
async def test_llm(
    admin: AdminUser, db: DBSession, body: LLMConfigUpdate
) -> LLMTestResult:
    return await SettingsService.test_llm(
        model=body.model, base_url=body.base_url, api_key=body.api_key
    )
