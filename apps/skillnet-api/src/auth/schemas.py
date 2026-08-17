"""Pydantic schemas for the fastapi-users User model."""

import uuid
from datetime import date

from fastapi_users import schemas
from pydantic import ConfigDict


class UserRead(schemas.BaseUser[uuid.UUID]):
    model_config = ConfigDict(from_attributes=True)

    full_name: str
    role: str
    learning_profile: str
    org_id: uuid.UUID
    accessibility: dict
    hired_at: date | None = None


class MeRead(UserRead):
    """The current user plus the deployment's workspace mode.

    ``workspace_mode`` lives on the organization, not the user, but the SPA reads
    ``/auth/me`` once on load and derives navigation from it, so it travels here to
    avoid a second round-trip. The value is a UX signal only — the API still
    enforces access server-side. See ``docs/design/audience-modes.md``.
    """

    workspace_mode: str


class UserCreate(schemas.BaseUserCreate):
    full_name: str
    org_id: uuid.UUID | None = None
    role: str = "employee"
    learning_profile: str = "standard"


class UserUpdate(schemas.BaseUserUpdate):
    full_name: str | None = None
    learning_profile: str | None = None
