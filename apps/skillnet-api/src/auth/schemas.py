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


class UserCreate(schemas.BaseUserCreate):
    full_name: str
    org_id: uuid.UUID | None = None
    role: str = "employee"
    learning_profile: str = "standard"


class UserUpdate(schemas.BaseUserUpdate):
    full_name: str | None = None
    learning_profile: str | None = None
