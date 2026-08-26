"""First-boot setup: initialize a self-hosted deployment from the UI.

The wizard runs once, before any user exists, to choose the deployment's
workspace mode and create the owner. See docs/design/audience-modes.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# Re-exported so every existing ``from src.schemas.setup import Capabilities`` keeps
# working. It moved to its own module when a capability stopped being a boolean and grew a
# status, a reason and an admin-only hint — see src/schemas/capabilities.py.
from src.schemas.capabilities import Capabilities


class SetupStatus(BaseModel):
    """The public, pre-authentication status payload.

    It is answered before anyone has signed in, so it carries each capability's ``status``
    and ``reason`` but never its ``hint``: a hint names environment variables, and telling
    an anonymous caller which key this deployment is missing is configuration disclosure
    (docs/design/security.md). The authenticated ``GET /settings/capabilities`` is where
    hints live.
    """

    #: True once at least one user exists — the setup wizard is then closed forever.
    initialized: bool
    #: When False, the SPA does not force the onboarding wizard (testing convenience).
    onboarding_enabled: bool = True
    #: The AI capabilities this deployment has, for capability-driven onboarding.
    capabilities: Capabilities
    #: Media kind -> the capability names it requires, so the frontend disables a Studio
    #: button from the backend's table instead of a hardcoded copy of it.
    media_requirements: dict[str, list[str]]


class SetupRequest(BaseModel):
    workspace_mode: Literal["organization", "individual"]
    #: The space/organization name. Required in `organization`; in `individual` it
    #: is derived (the owner's personal space), so the wizard need not send it.
    org_name: str | None = Field(default=None, max_length=200)
    owner_full_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=200)
