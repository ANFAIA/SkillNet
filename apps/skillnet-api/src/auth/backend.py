"""fastapi-users authentication backend: cookie transport + database strategy."""

from fastapi import Depends
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy

from src.auth.db import get_access_token_db
from src.config import settings

cookie_transport = CookieTransport(
    cookie_name=settings.COOKIE_NAME,
    cookie_max_age=settings.SESSION_LIFETIME_SECONDS,
    cookie_secure=settings.COOKIE_SECURE,
    cookie_httponly=True,
    cookie_samesite="lax",
)


def get_database_strategy(
    access_token_db=Depends(get_access_token_db),
) -> DatabaseStrategy:
    return DatabaseStrategy(
        access_token_db,
        lifetime_seconds=settings.SESSION_LIFETIME_SECONDS,
    )


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)
