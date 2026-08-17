"""Deployment workspace mode: the organization-only gate and mode exposure.

``require_organization_workspace`` must 404 collective surfaces (employees,
talent, stats, assignment, skills) in an ``individual`` deployment and be a
no-op in ``organization`` — the default that keeps every existing deployment
untouched. See docs/design/audience-modes.md.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import AppError
from src.deps.auth import require_organization_workspace
from src.models import WorkspaceMode


_USER = SimpleNamespace(org_id=uuid.uuid4())


def _db_returning(mode: WorkspaceMode | None) -> object:
    result = SimpleNamespace(scalar_one_or_none=lambda: mode)
    return SimpleNamespace(execute=AsyncMock(return_value=result))


@pytest.mark.asyncio
async def test_gate_is_noop_in_organization_mode() -> None:
    await require_organization_workspace(
        user=_USER, db=_db_returning(WorkspaceMode.ORGANIZATION)
    )


@pytest.mark.asyncio
async def test_gate_defaults_open_when_no_org_row_yet() -> None:
    # A fresh, un-bootstrapped database must not 404 the org surfaces.
    await require_organization_workspace(user=_USER, db=_db_returning(None))


@pytest.mark.asyncio
async def test_gate_404s_in_individual_mode() -> None:
    with pytest.raises(AppError) as exc:
        await require_organization_workspace(
            user=_USER, db=_db_returning(WorkspaceMode.INDIVIDUAL)
        )
    assert exc.value.status_code == 404


def test_workspace_mode_enum_values() -> None:
    # The migration's Postgres enum labels must match the Python enum values.
    assert WorkspaceMode.ORGANIZATION.value == "organization"
    assert WorkspaceMode.INDIVIDUAL.value == "individual"
