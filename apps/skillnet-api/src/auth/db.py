"""fastapi-users database adapters for the User and AccessToken tables."""

from collections.abc import AsyncGenerator

from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase

from src.deps.db import DBSession
from src.models import AccessToken, User


async def get_user_db(
    session: DBSession,
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)


async def get_access_token_db(
    session: DBSession,
) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase, None]:
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)
