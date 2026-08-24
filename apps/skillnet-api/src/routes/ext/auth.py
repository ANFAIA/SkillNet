"""API key authentication for external (machine-to-machine) routes."""

import hashlib
from datetime import datetime
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
    if api_key.expires_at is not None and api_key.expires_at <= datetime.utcnow():
        raise ForbiddenError("Invalid or inactive API key")
    # Update last_used_at. Naive on purpose, and the one place in the codebase that is:
    # `api_keys.last_used_at` is a TIMESTAMP WITHOUT TIME ZONE, and migration 0006 names it
    # explicitly as the column left naive because converting it would be churn, not a fix.
    # (The unused `timezone` import that sat above until 2026-08-04 read like the opposite.)
    api_key.last_used_at = datetime.utcnow()
    await db.flush()
    return api_key


ExtApiKey = Annotated[ApiKey, Depends(_get_api_key)]


def require_scope(scope: str):
    """Build a dependency that additionally requires ``scope`` on the API key.

    Kept separate from ``_get_api_key`` so every route still gets the shared
    validity checks (hash lookup, ``is_active``, ``expires_at``) and only adds the
    scope check it actually needs — see the scopes table in
    ``docs/design/mcp-external-api.md`` (8.1.1) for what each scope is meant to gate.
    """

    async def _dep(api_key: ExtApiKey) -> ApiKey:
        if scope not in api_key.scopes:
            raise ForbiddenError(f"API key is missing required scope: {scope}")
        return api_key

    return _dep


RequireSkillsRead = Annotated[ApiKey, Depends(require_scope("skills:read"))]
RequireSkillsWrite = Annotated[ApiKey, Depends(require_scope("skills:write"))]
RequireUsersRead = Annotated[ApiKey, Depends(require_scope("users:read"))]
RequireCoursesWrite = Annotated[ApiKey, Depends(require_scope("courses:write"))]
