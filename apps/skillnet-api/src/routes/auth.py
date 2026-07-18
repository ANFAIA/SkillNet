"""Auth routes: fastapi-users login/logout plus a lightweight /auth/me."""

from fastapi import APIRouter

from src.auth.schemas import UserRead
from src.deps.auth import CurrentUser, auth_backend, fastapi_users

router = APIRouter()

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth",
    tags=["Auth"],
)


@router.get("/auth/me", response_model=UserRead, tags=["Auth"])
async def me(user: CurrentUser) -> UserRead:
    return user
