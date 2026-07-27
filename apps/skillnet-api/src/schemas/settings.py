"""Organization settings schemas (admin LLM configuration)."""

from __future__ import annotations

from pydantic import BaseModel


class OrgSettingsRead(BaseModel):
    name: str
    slug: str
    self_registration_enabled: bool = False
    # Effective LLM config (never exposes the API key).
    llm_configured: bool
    llm_model: str | None = None
    embedding_model: str | None = None
    llm_base_url: str | None = None
    #: Whether the tutor may lay its answers out in the SkillNet kit instead of plain
    #: prose. On unless the admin turned it off; see `services/org_features.py`.
    chat_generative_ui: bool = True


class LLMConfigUpdate(BaseModel):
    model: str
    base_url: str | None = None
    api_key: str | None = None


class FeaturesUpdate(BaseModel):
    """What an admin may switch on and off for their own organization.

    One field today. It is its own endpoint rather than a flag bolted onto
    `LLMConfigUpdate` because changing how answers are presented has nothing to do with
    which provider serves them, and an admin who edits one should not have to re-enter
    the other — least of all the API key.
    """

    chat_generative_ui: bool


class LLMTestResult(BaseModel):
    ok: bool
    detail: str | None = None
    model: str | None = None
