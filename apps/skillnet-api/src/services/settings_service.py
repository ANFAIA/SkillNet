"""Organization settings: read effective config and manage LLM provider.

LLM/embedding overrides are persisted in ``organizations.settings`` (jsonb) and
take precedence over environment defaults (see ``src.deps.llm``). The API key is
stored but never returned.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.llm.client import LLMConfig, LLMService, resolve_llm_config
from src.llm.embedding import resolve_embedding_config
from src.models import Organization
from src.schemas.settings import LLMTestResult, OrgSettingsRead

logger = get_logger(__name__)

_LLM_KEYS = ("llm_model", "llm_base_url", "llm_api_key")


class SettingsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_org(self) -> Organization:
        org = (await self.db.execute(select(Organization).limit(1))).scalar_one_or_none()
        if org is None:
            raise NotFoundError("organizations", "current")
        return org

    async def get_settings(self) -> OrgSettingsRead:
        org = await self._get_org()
        org_settings = dict(org.settings or {})
        llm = resolve_llm_config(org_settings)
        embedding = resolve_embedding_config(org_settings)
        return OrgSettingsRead(
            name=org.name,
            slug=org.slug,
            self_registration_enabled=bool(
                org_settings.get("self_registration_enabled", False)
            ),
            llm_configured=bool(llm.model),
            llm_model=llm.model or None,
            embedding_model=embedding.model or None,
            llm_base_url=llm.api_base,
        )

    async def update_llm(
        self, *, model: str, base_url: str | None, api_key: str | None
    ) -> OrgSettingsRead:
        org = await self._get_org()
        new_settings = dict(org.settings or {})
        new_settings["llm_model"] = model
        if base_url is not None:
            new_settings["llm_base_url"] = base_url
        if api_key:
            new_settings["llm_api_key"] = api_key
        # Reassign so SQLAlchemy detects the JSONB change.
        org.settings = new_settings
        await self.db.flush()
        return await self.get_settings()

    @staticmethod
    async def test_llm(
        *, model: str, base_url: str | None, api_key: str | None
    ) -> LLMTestResult:
        try:
            service = LLMService(
                LLMConfig(model=model, api_base=base_url or None, api_key=api_key or None)
            )
            reply = await service.complete(
                "You are a connection tester.",
                "Reply with the single word: OK",
                max_tokens=5,
                temperature=0.0,
            )
            return LLMTestResult(ok=True, detail=reply.strip()[:100] or "OK", model=model)
        except Exception as exc:  # noqa: BLE001 - report any provider failure to the admin
            logger.warning("LLM test failed: %s", exc)
            return LLMTestResult(ok=False, detail=f"{type(exc).__name__}: {exc}"[:300], model=model)
