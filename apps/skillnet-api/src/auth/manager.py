"""fastapi-users UserManager and its dependency provider."""

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin

from src.auth.db import get_user_db
from src.config import settings
from src.core.logging import get_logger
from src.models import User

logger = get_logger(__name__)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        logger.info("User registered: %s (id=%s)", user.email, user.id)


async def get_user_manager(
    user_db=Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)
