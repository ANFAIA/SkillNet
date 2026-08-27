"""Organization settings routes (admin).

The line these routes draw, and why it is where it is:

**Infrastructure belongs to the environment.** The LLM provider, its base URL and its API
key are set in ``.env`` by whoever deploys SkillNet — the same person who owns the
provider account and pays its bill. There is no endpoint to change them, deliberately.
SkillNet is one organization per deployment (``bootstrap.py`` creates exactly one, and
everything else reads it back with ``select(Organization).limit(1)``), so "the
organization's provider" and "the deployment's provider" are the same thing, and having
two places to set it would be two sources of truth for no gain. The multi-tenant argument
for a web form — many companies in one instance, each with their own key, none with
server access — does not apply here.

**Product decisions belong to the admin.** Whether the tutor lays its answers out in the
SkillNet kit is not an infrastructure question, and the person running the training is the
one who should answer it. That is ``PUT /features``.

What is left of the provider on this surface is read-only, plus ``POST /llm/test``:
"is the AI configured, and does it answer?" is a real operational question an admin will
ask the moment something fails to generate, and answering it without an SSH session is
worth an endpoint. It reports on the **configured** provider and takes no credentials.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.schemas.capabilities import CapabilitiesReport
from src.schemas.settings import FeaturesUpdate, LLMTestResult, OrgSettingsRead
from src.services.capabilities import derive_capabilities
from src.services.media.requirements import requirements_payload
from src.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=OrgSettingsRead)
async def get_settings(admin: AdminUser, db: DBSession) -> OrgSettingsRead:
    return await SettingsService(db).get_settings()


@router.get("/capabilities", response_model=CapabilitiesReport)
async def get_capabilities(admin: AdminUser) -> CapabilitiesReport:
    """The same capabilities the public status endpoint reports, **with** the admin hints.

    The hint is the whole reason this endpoint exists: it names the environment variable to
    set, which is precisely what must not travel on the public ``GET /setup/status``. One
    derivation feeds both, called with ``include_hints`` flipped, so the two payloads can
    never disagree about what this deployment can do.

    No ``DBSession``: capabilities are read from ``settings`` and from the in-process
    provider-health registry, and asking the database would be a query for nothing.
    """
    return CapabilitiesReport(
        capabilities=derive_capabilities(include_hints=True),
        media_requirements=requirements_payload(),
    )


@router.put("/features", response_model=OrgSettingsRead)
async def update_features(
    admin: AdminUser, db: DBSession, body: FeaturesUpdate
) -> OrgSettingsRead:
    service = SettingsService(db)
    result = await service.update_features(chat_generative_ui=body.chat_generative_ui)
    await db.commit()
    return result


@router.post("/llm/test", response_model=LLMTestResult)
async def test_llm(admin: AdminUser, db: DBSession) -> LLMTestResult:
    """Ask the configured provider to answer, and report what happened.

    No body: there is nothing for the caller to supply, because there is nothing for the
    caller to change. Testing credentials that were posted in the same request would test
    something other than what the application actually uses.
    """
    return await SettingsService(db).test_configured_llm()
