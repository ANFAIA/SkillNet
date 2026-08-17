"""First-boot setup: status probe and the single-shot guard.

The full happy path (create owner + auto-login) needs a live DB and is covered
by manual/integration runs; here we pin the pure guard logic: status reflects
whether any user exists, and POST /setup is closed (409) once one does.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ConflictError
from src.routes.setup import setup, setup_status
from src.schemas.setup import SetupRequest


def _db_with_user(present: bool) -> object:
    result = SimpleNamespace(scalar_one_or_none=lambda: object() if present else None)
    return SimpleNamespace(execute=AsyncMock(return_value=result))


@pytest.mark.asyncio
async def test_status_false_when_no_users() -> None:
    status = await setup_status(db=_db_with_user(False))
    assert status.initialized is False


@pytest.mark.asyncio
async def test_status_true_when_a_user_exists() -> None:
    status = await setup_status(db=_db_with_user(True))
    assert status.initialized is True


@pytest.mark.asyncio
async def test_setup_409_once_initialized() -> None:
    body = SetupRequest(
        workspace_mode="individual",
        owner_full_name="Owner",
        owner_email="owner@example.dev",
        owner_password="secret12",
    )
    with pytest.raises(ConflictError):
        await setup(body=body, db=_db_with_user(True), strategy=object())


def test_setup_request_password_min_length() -> None:
    with pytest.raises(ValueError):
        SetupRequest(
            workspace_mode="individual",
            owner_full_name="Owner",
            owner_email="owner@example.dev",
            owner_password="short",  # < 8
        )
