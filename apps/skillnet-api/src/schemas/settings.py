"""Organization settings schemas (admin LLM configuration)."""

from __future__ import annotations

from pydantic import BaseModel


class OrgSettingsRead(BaseModel):
    name: str
    slug: str
    #: Deployment mode: "organization" or "individual". See audience-modes.md.
    workspace_mode: str = "organization"
    self_registration_enabled: bool = False
    # Effective LLM config (never exposes the API key).
    llm_configured: bool
    llm_model: str | None = None
    embedding_model: str | None = None
    llm_base_url: str | None = None
    #: Whether the tutor may lay its answers out in the SkillNet kit instead of plain
    #: prose. On unless the admin turned it off; see `services/org_features.py`.
    chat_generative_ui: bool = True


class FeaturesUpdate(BaseModel):
    """What an admin may switch on and off for their own organization.

    One field today, and its own endpoint on purpose: it is the only thing on this
    surface an admin may write. The provider comes from the environment, so there is
    nothing else here for a form to change.
    """

    chat_generative_ui: bool


class LLMTestResult(BaseModel):
    ok: bool
    detail: str | None = None
    model: str | None = None
