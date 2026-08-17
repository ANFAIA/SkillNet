import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config import settings
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


def _legacy_render(cache_key: str):
    # A fallback render is always legacy_stepper regardless of its ui_spec.
    return SimpleNamespace(
        status=NodeRenderStatus.FALLBACK,
        cache_key=f"{current_render_safety_prefix()}{cache_key}",
        ui_spec=None,
    )


@pytest.mark.asyncio
async def test_flat_pin_is_dropped_when_the_ready_pack_changes_the_key(monkeypatch) -> None:
    """A flat render pinned by prefetch before the pack was ready must not shadow the
    episode forever: once the pack lands the freshly computed key differs, so the pin is
    dropped and the next render regenerates the episode."""
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", True)
    render = _legacy_render("without-pack")
    service = _service(render)
    service.render_key_for = AsyncMock(
        return_value=SimpleNamespace(
            cache_key=f"{current_render_safety_prefix()}with-pack"
        )
    )

    result = await service.pinned_render(
        user_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        node=SimpleNamespace(),
        course=SimpleNamespace(),
        user=SimpleNamespace(),
    )

    assert result is None
    service.render_key_for.assert_awaited_once()


@pytest.mark.asyncio
async def test_flat_pin_stands_when_the_fresh_key_still_matches(monkeypatch) -> None:
    """An honest decline — a render produced *with* the pack that still came out flat —
    already carries the pack fragment, so its key matches and the pin is kept. That is what
    keeps the guard loop-safe."""
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", True)
    render = _legacy_render("with-pack")
    service = _service(render)
    service.render_key_for = AsyncMock(
        return_value=SimpleNamespace(
            cache_key=f"{current_render_safety_prefix()}with-pack"
        )
    )

    result = await service.pinned_render(
        user_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        node=SimpleNamespace(),
        course=SimpleNamespace(),
        user=SimpleNamespace(),
    )

    assert result is render
