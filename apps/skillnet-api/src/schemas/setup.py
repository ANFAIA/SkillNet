"""First-boot setup: initialize a self-hosted deployment from the UI.

The wizard runs once, before any user exists, to choose the deployment's
workspace mode and create the owner. See docs/design/audience-modes.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SetupStatus(BaseModel):
    #: True once at least one user exists — the setup wizard is then closed forever.
    initialized: bool
    #: When False, the SPA does not force the onboarding wizard (testing convenience).
    onboarding_enabled: bool = True


class SetupRequest(BaseModel):
    workspace_mode: Literal["organization", "individual"]
    #: The space/organization name. Required in `organization`; in `individual` it
    #: is derived (the owner's personal space), so the wizard need not send it.
    org_name: str | None = Field(default=None, max_length=200)
    owner_full_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=200)
