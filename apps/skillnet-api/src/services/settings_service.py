"""Organization settings: read the effective config, switch product features.

**The LLM provider is not settable here.** It comes from the environment, because
SkillNet runs one organization per deployment (``bootstrap.py`` creates exactly one) and
so the deployment's provider and the organization's provider are the same thing — see
``src/routes/settings.py`` for the full reasoning.

``resolve_llm_config`` still *reads* an override out of ``organizations.settings``, and
that is deliberate rather than leftover: it is the precedence chain the two-tier runtime
router is built on (``src/agents/runtime/router.py``), it keeps working for a deployment
that stored a key before this changed, and it is the seam that would carry per-tenant
providers the day SkillNet grows a second organization. What went away is the endpoint
that let a web form write it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.core.language import Language
from src.core.logging import get_logger
from src.llm.client import resolve_llm_config
from src.llm.embedding import resolve_embedding_config
from src.llm.fixtures import maybe_fixture_llm
from src.models import Organization
from src.schemas.settings import LLMTestResult, OrgSettingsRead
from src.services.org_features import (
    CHAT_GENERATIVE_UI,
    ORG_LANGUAGE,
    chat_generative_ui_enabled,
    org_language,
)

logger = get_logger(__name__)

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
            workspace_mode=org.workspace_mode.value,
            self_registration_enabled=bool(
                org_settings.get("self_registration_enabled", False)
            ),
            llm_configured=bool(llm.model),
            llm_model=llm.model or None,
            embedding_model=embedding.model or None,
            llm_base_url=llm.api_base,
            chat_generative_ui=chat_generative_ui_enabled(org_settings),
            language=org_language(org_settings),
        )

    async def update_features(
        self, *, chat_generative_ui: bool, language: Language | None = None
    ) -> OrgSettingsRead:
        org = await self._get_org()
        new_settings = dict(org.settings or {})
        new_settings[CHAT_GENERATIVE_UI] = chat_generative_ui
        # Absent means "leave it alone", not "reset it": a client flipping the switch
        # sends no language, and it must not wipe the one the organization chose. Which
        # also means this endpoint cannot clear the language once set — the day that is
        # wanted it needs an explicit sentinel, not the absence of a field.
        if language is not None:
            new_settings[ORG_LANGUAGE] = language
        # Reassign so SQLAlchemy detects the JSONB change.
        org.settings = new_settings
        await self.db.flush()
        return await self.get_settings()

    async def test_configured_llm(self) -> LLMTestResult:
        """Ask the provider the application actually uses to answer.

        Resolved through ``resolve_llm_config``, not from anything the caller sent, so a
        green result means the *deployment* works — which is the only useful meaning. The
        previous version tested credentials posted in the same request, which could pass
        while the configured provider was broken, and did not survive the provider moving
        into the environment.
        """
        org = await self._get_org()
        config = resolve_llm_config(dict(org.settings or {}))
        try:
            service = maybe_fixture_llm(config)
            reply = await service.complete(
                "You are a connection tester.",
                "Reply with the single word: OK",
                max_tokens=5,
                temperature=0.0,
            )
            return LLMTestResult(
                ok=True, detail=reply.strip()[:100] or "OK", model=config.model
            )
        except Exception as exc:  # noqa: BLE001 - report any provider failure to the admin
            logger.warning("LLM test failed: %s", exc)
            return LLMTestResult(
                ok=False,
                detail=f"{type(exc).__name__}: {exc}"[:300],
                model=config.model,
            )
