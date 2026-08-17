"""Auth routes: fastapi-users login/logout plus a lightweight /auth/me."""

from fastapi import APIRouter
from sqlalchemy import select

from src.auth.schemas import MeRead, UserRead
from src.deps.auth import CurrentUser, auth_backend, fastapi_users
from src.deps.db import DBSession
from src.models import Organization, WorkspaceMode

router = APIRouter()

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth",
    tags=["Auth"],
)


@router.get("/auth/me", response_model=MeRead, tags=["Auth"])
async def me(user: CurrentUser, db: DBSession) -> MeRead:
    # Scoped to the user's own organization, not select().limit(1): correct even
    # if the database holds more than one organization row.
    mode = (
        await db.execute(
            select(Organization.workspace_mode).where(Organization.id == user.org_id)
        )
    ).scalar_one_or_none()
    mode_value = (mode or WorkspaceMode.ORGANIZATION).value
    base = UserRead.model_validate(user, from_attributes=True)
    return MeRead(**base.model_dump(), workspace_mode=mode_value)
