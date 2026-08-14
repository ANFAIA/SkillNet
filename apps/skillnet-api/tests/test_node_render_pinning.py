import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.models import NodeRenderStatus
from src.services.node_render_service import (
    NodeRenderService,
    current_render_safety_prefix,
)


def _service(render):
    service = object.__new__(NodeRenderService)
    service.states = SimpleNamespace(
        get_by_user_and_node=AsyncMock(
            return_value=SimpleNamespace(
                render_pinned=True,
                active_render_id=uuid.uuid4(),
            )
        )
    )
    service.renders = SimpleNamespace(get_by_id=AsyncMock(return_value=render))
    return service


@pytest.mark.asyncio
async def test_current_prompt_pin_is_stable() -> None:
    render = SimpleNamespace(
        status=NodeRenderStatus.READY,
        cache_key=f"{current_render_safety_prefix()}abc123",
    )
    assert await _service(render).pinned_render(
        user_id=uuid.uuid4(), node_id=uuid.uuid4()
    ) is render


@pytest.mark.asyncio
async def test_prompt_deployment_invalidates_a_stale_pin() -> None:
    render = SimpleNamespace(
        status=NodeRenderStatus.READY,
        cache_key="abc123",
    )
    assert await _service(render).pinned_render(
        user_id=uuid.uuid4(), node_id=uuid.uuid4()
    ) is None
