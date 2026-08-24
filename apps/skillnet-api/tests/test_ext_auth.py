"""Auth hardening for /ext/v1 API keys: scopes and expires_at enforcement.

Before this, `_get_api_key` only checked `is_active` — the `scopes` column was stored
(and documented in docs/design/mcp-external-api.md, 8.1.1) but never read, and
`expires_at` didn't exist as a column at all. These tests pin the two properties that
matter: an expired or under-scoped key is rejected, and a key that satisfies both keeps
working exactly like before (the A2A internal key in particular, which carries
`skills:read`, `skills:write`, `users:read`, `courses:write` and no expiry).

Uses a fake repository instead of a real Postgres connection, in line with the rest of
the unit suite (`-m "not integration"`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from src.core.exceptions import ForbiddenError
from src.models.api_key import ApiKey
from src.routes.ext import auth as ext_auth


class _FakeDB:
    """Stands in for the AsyncSession: only `flush()` is exercised by `_get_api_key`."""

    async def flush(self) -> None:
        return None


def _make_key(
    *,
    scopes: list[str],
    is_active: bool = True,
    expires_at: datetime | None = None,
) -> ApiKey:
    return ApiKey(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        name="test key",
        key_hash="irrelevant",
        scopes=scopes,
        is_active=is_active,
        expires_at=expires_at,
    )


@pytest.fixture(autouse=True)
def _patch_repo(monkeypatch: pytest.MonkeyPatch):
    """Point `ApiKeyRepository.get_by_hash` at a key set by each test via `_current_key`."""

    state: dict[str, ApiKey | None] = {"key": None}

    async def _get_by_hash(self, key_hash: str) -> ApiKey | None:  # noqa: ARG001
        return state["key"]

    monkeypatch.setattr(ext_auth.ApiKeyRepository, "get_by_hash", _get_by_hash)
    yield state


async def _resolve(state, key: ApiKey | None, token: str = "sn_whatever") -> ApiKey:
    state["key"] = key
    return await ext_auth._get_api_key(db=_FakeDB(), authorization=f"Bearer {token}")


# --------------------------------------------------------------------------------------
# expires_at
# --------------------------------------------------------------------------------------
async def test_expired_key_is_rejected(_patch_repo):
    key = _make_key(scopes=["skills:read"], expires_at=datetime.utcnow() - timedelta(days=1))
    with pytest.raises(ForbiddenError):
        await _resolve(_patch_repo, key)


async def test_key_expiring_now_is_rejected(_patch_repo):
    """`<=` is deliberate: a key can't be valid for the exact expiry instant."""
    key = _make_key(scopes=["skills:read"], expires_at=datetime.utcnow())
    with pytest.raises(ForbiddenError):
        await _resolve(_patch_repo, key)


async def test_key_with_future_expiry_is_accepted(_patch_repo):
    key = _make_key(scopes=["skills:read"], expires_at=datetime.utcnow() + timedelta(days=30))
    resolved = await _resolve(_patch_repo, key)
    assert resolved is key


async def test_key_with_no_expiry_is_accepted(_patch_repo):
    key = _make_key(scopes=["skills:read"], expires_at=None)
    resolved = await _resolve(_patch_repo, key)
    assert resolved is key


async def test_inactive_key_is_still_rejected(_patch_repo):
    """Pre-existing behaviour, kept: `is_active=False` fails independently of expiry."""
    key = _make_key(scopes=["skills:read"], is_active=False)
    with pytest.raises(ForbiddenError):
        await _resolve(_patch_repo, key)


async def test_unknown_key_is_rejected(_patch_repo):
    with pytest.raises(ForbiddenError):
        await _resolve(_patch_repo, None)


# --------------------------------------------------------------------------------------
# scopes
# --------------------------------------------------------------------------------------
async def test_require_scope_rejects_key_missing_the_scope():
    key = _make_key(scopes=["skills:read"])
    dep = ext_auth.require_scope("skills:write")
    with pytest.raises(ForbiddenError):
        await dep(key)


async def test_require_scope_accepts_key_with_the_scope():
    key = _make_key(scopes=["skills:read", "skills:write"])
    dep = ext_auth.require_scope("skills:write")
    resolved = await dep(key)
    assert resolved is key


async def test_require_scope_error_never_echoes_the_key_material():
    key = _make_key(scopes=[])
    dep = ext_auth.require_scope("courses:write")
    with pytest.raises(ForbiddenError) as excinfo:
        await dep(key)
    assert "sn_" not in str(excinfo.value)
    assert str(key.id) not in str(excinfo.value)


# --------------------------------------------------------------------------------------
# A2A-style key: must keep working across every scope it is documented to carry
# --------------------------------------------------------------------------------------
async def test_a2a_style_key_satisfies_all_four_required_scopes(_patch_repo):
    """Mirrors `maybe_create_a2a_api_key` in src/core/bootstrap.py: no expiry, four scopes."""
    key = _make_key(
        scopes=["skills:read", "skills:write", "users:read", "courses:write"],
        expires_at=None,
    )
    resolved = await _resolve(_patch_repo, key)
    for scope in ("skills:read", "skills:write", "users:read", "courses:write"):
        dep = ext_auth.require_scope(scope)
        assert await dep(resolved) is resolved


async def test_bad_authorization_header_is_rejected(_patch_repo):
    state = _patch_repo
    state["key"] = _make_key(scopes=["skills:read"])
    with pytest.raises(ForbiddenError):
        await ext_auth._get_api_key(db=_FakeDB(), authorization="Token not-a-bearer")
