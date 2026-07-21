"""API key authentication for external (machine-to-machine) routes."""

import hashlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header

from src.core.exceptions import ForbiddenError
from src.deps.db import DBSession
from src.models.api_key import ApiKey
from src.repositories.api_key_repo import ApiKeyRepository


async def _get_api_key(
    db: DBSession,
    authorization: str = Header(...),
) -> ApiKey:
    if not authorization.startswith("Bearer "):
        raise ForbiddenError("Invalid authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    repo = ApiKeyRepository(db)
    api_key = await repo.get_by_hash(key_hash)
    if api_key is None or not api_key.is_active:
        raise ForbiddenError("Invalid or inactive API key")
    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.flush()
    return api_key


ExtApiKey = Annotated[ApiKey, Depends(_get_api_key)]
