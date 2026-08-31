"""Organization settings schemas (admin LLM configuration)."""

from __future__ import annotations

from pydantic import BaseModel

from src.core.language import Language


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
    #: The language new courses are generated in when the request does not say and there
    #: is no source material to infer it from. ``None`` means the organization never
    #: chose, and the product default applies.
    language: Language | None = None


class FeaturesUpdate(BaseModel):
    """What an admin may change for their own organization.

    Its own endpoint on purpose: these are the only things on this surface an admin may
    write. The provider comes from the environment, so there is nothing else here for a
    form to change.

    ``language`` is optional and ``chat_generative_ui`` is not, which is not an
    oversight: omitting the language has to mean "leave it as it is", because a client
    that only wants to flip the switch must not silently reset the organization's
    language to the product default.
    """

    chat_generative_ui: bool
    language: Language | None = None


class LLMTestResult(BaseModel):
    ok: bool
    detail: str | None = None
    model: str | None = None
