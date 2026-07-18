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


class LLMConfigUpdate(BaseModel):
    model: str
    base_url: str | None = None
    api_key: str | None = None


class LLMTestResult(BaseModel):
    ok: bool
    detail: str | None = None
    model: str | None = None
