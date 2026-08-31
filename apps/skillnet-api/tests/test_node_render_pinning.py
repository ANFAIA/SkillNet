"""The pin, and the one asymmetry inside it: ``ready`` is retained, ``fallback`` is not.

The pin is what makes a lesson stable — coming back tomorrow returns the same bytes
instead of a different screen (§5.5) — so the tests that matter here are the ones that
prove the promise is kept for a **good** render and *not* kept for a degraded one. A
``fallback`` pinned to perpetuity is how a transient generation failure became permanent:
a learner stayed fixed on yesterday's backup screen while two clean ``ready`` renders of
the same node existed that she was never going to see.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.models import NodeRenderStatus
from src.personalization.projection import project_longitudinal_history
from src.services.node_render_service import (
    FALLBACK_RETRY_MAX_ATTEMPTS,
    NodeRenderService,
    claim_fallback_retry,
    current_render_safety_prefix,
    fallback_retry_available,
    reset_fallback_retries,
)


def _service(render, *, cached=None, state=None):
    service = object.__new__(NodeRenderService)
    service.states = SimpleNamespace(
        get_by_user_and_node=AsyncMock(
            return_value=state
            or SimpleNamespace(
                render_pinned=True,
                active_render_id=uuid.uuid4(),
            )
        )
    )
    service.renders = SimpleNamespace(
        get_by_id=AsyncMock(return_value=render),
        find_cached=AsyncMock(return_value=cached),
    )
    return service


@pytest.fixture(autouse=True)
def _clean_retry_budget():
    """The budget is process-local, so it must not leak between tests."""
    reset_fallback_retries()
    yield
    reset_fallback_retries()


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
        id=uuid.uuid4(),
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
            cache_key=f"{current_render_safety_prefix()}with-pack",
            personalization_revision=0,
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
            cache_key=f"{current_render_safety_prefix()}with-pack",
            personalization_revision=0,
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


# --------------------------------------------------------------------------- #
# ready is retained, fallback is not
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_pinned_fallback_is_replaced_by_an_available_ready_render() -> None:
    """The production bug, in one test.

    A learner pinned to yesterday's ``fallback`` while a clean ``ready`` render of the same
    node exists must be handed the clean one — and repinned to it, so the swap happens once
    and the new render is then as stable as any other ``ready``.
    """
    fallback = _legacy_render("degraded")
    clean = SimpleNamespace(
        id=uuid.uuid4(),
        status=NodeRenderStatus.READY,
        cache_key=f"{current_render_safety_prefix()}fresh",
        ui_spec=None,
    )
    service = _service(fallback, cached=clean)
    service.render_key_for = AsyncMock(
        return_value=SimpleNamespace(
            cache_key=clean.cache_key, personalization_revision=0
        )
    )
    service.pin = AsyncMock(return_value=SimpleNamespace())

    result = await service.pinned_render(
        user_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        node=SimpleNamespace(),
        course=SimpleNamespace(),
        user=SimpleNamespace(),
    )

    assert result is clean
    service.pin.assert_awaited_once()
    assert service.pin.await_args.kwargs["render"] is clean


@pytest.mark.asyncio
async def test_a_pinned_fallback_is_still_served_when_nothing_better_exists() -> None:
    """No blank screens: with no ``ready`` to swap in, the backup content stays on screen.

    Serving it is not the same as retaining it — ``request_render`` still regenerates (see
    below); this only says the learner is never left staring at a 202.
    """
    fallback = _legacy_render("degraded")
    service = _service(fallback, cached=None)
    service.render_key_for = AsyncMock(
        return_value=SimpleNamespace(
            cache_key=fallback.cache_key, personalization_revision=0
        )
    )
    service.pin = AsyncMock()

    result = await service.pinned_render(
        user_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        node=SimpleNamespace(),
        course=SimpleNamespace(),
        user=SimpleNamespace(),
    )

    assert result is fallback
    service.pin.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_ready_pin_is_never_re_resolved(monkeypatch) -> None:
    """The reason the pin exists at all: a good render is not reconsidered.

    Not even a key recompute happens — that is what the "Estable" row of §5.5 promises, and
    the whole asymmetry is only defensible while this stays true.
    """
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", True)
    render = SimpleNamespace(
        id=uuid.uuid4(),
        status=NodeRenderStatus.READY,
        cache_key=f"{current_render_safety_prefix()}good",
        ui_spec={
            "generation": {"shell_mode": "episode", "episode_status": "ready"}
        },
    )
    service = _service(render, cached=SimpleNamespace(id=uuid.uuid4()))
    service.render_key_for = AsyncMock()
    service.pin = AsyncMock()

    result = await service.pinned_render(
        user_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        node=SimpleNamespace(),
        course=SimpleNamespace(),
        user=SimpleNamespace(),
    )

    assert result is render
    service.render_key_for.assert_not_awaited()
    service.pin.assert_not_awaited()
    service.renders.find_cached.assert_not_awaited()


# --------------------------------------------------------------------------- #
# The retry budget: bounded cost, not a regeneration loop
# --------------------------------------------------------------------------- #
def test_the_budget_allows_a_bounded_number_of_retries_per_key() -> None:
    key = "safety:x:some-degraded-key"

    # Each attempt is separated by the cooldown, so a poll loop cannot burn the budget in
    # one second — and the budget itself is finite, so a node that always fails settles on
    # serving the backup content for free.
    assert fallback_retry_available(key, now=0.0) is True
    for attempt in range(FALLBACK_RETRY_MAX_ATTEMPTS):
        moment = attempt * 10_000.0
        assert claim_fallback_retry(key, now=moment) is True
        assert fallback_retry_available(key, now=moment) is False
        assert claim_fallback_retry(key, now=moment) is False

    exhausted = FALLBACK_RETRY_MAX_ATTEMPTS * 10_000.0
    assert fallback_retry_available(key, now=exhausted) is False
    assert claim_fallback_retry(key, now=exhausted) is False


def test_the_budget_is_per_cache_key_so_one_bucket_does_not_starve_another() -> None:
    """Keyed by ``cache_key`` because the row is shared: one retry serves the whole bucket,
    and a different bucket's fallback gets its own attempts."""
    assert claim_fallback_retry("key-a", now=0.0) is True
    assert fallback_retry_available("key-a", now=0.0) is False
    assert fallback_retry_available("key-b", now=0.0) is True


@pytest.mark.asyncio
async def test_request_render_regenerates_over_a_pinned_fallback(monkeypatch) -> None:
    """A ``fallback`` pin does not stop the generation the way a ``ready`` pin does."""
    fallback = _legacy_render("degraded")
    service = NodeRenderService(SimpleNamespace())
    service.pinned_render = AsyncMock(return_value=fallback)  # type: ignore[method-assign]
    service.render_key_for = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(
            cache_key=fallback.cache_key,
            personalization_revision=0,
            effective_density=3,
            scaffold_band="neutral",
            knowledge_pack_key="",
            selection_strategy="off",
            selection_execution="off",
            generation_policy_key="screen-scheme/v1",
            longitudinal_decision_digest="d",
            longitudinal_history=project_longitudinal_history([], nodes_completed=0),
            language="es",
        )
    )
    service.renders = SimpleNamespace(find_cached=AsyncMock(return_value=None))
    spawned: list[dict] = []
    monkeypatch.setattr(
        "src.agents.runtime.runner.spawn_node_render",
        lambda state: spawned.append(state),
    )

    result = await service.request_render(
        user=SimpleNamespace(id=uuid.uuid4()),
        node=SimpleNamespace(
            id=uuid.uuid4(),
            reviewed_at=object(),
            org_id=uuid.uuid4(),
            course_id=uuid.uuid4(),
        ),
        course=SimpleNamespace(schema_version=1),
    )

    assert result.cached is False
    assert result.request_id
    assert len(spawned) == 1
    # And the slot it spent is gone, so the next visit does not spend another one.
    assert fallback_retry_available(fallback.cache_key) is False


def _unpinned_service(*, spent_row, key: str):
    """A request with **nothing** pinned and no cache hit: the state that had no budget.

    ``find_cached`` reads ``ready`` only, so it cannot see the row a failed run left behind,
    and there is no pin to carry the fallback budget either.
    """
    service = NodeRenderService(SimpleNamespace())
    service.pinned_render = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service.render_key_for = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(
            cache_key=key,
            personalization_revision=0,
            effective_density=3,
            scaffold_band="neutral",
            knowledge_pack_key="",
            selection_strategy="off",
            selection_execution="off",
            generation_policy_key="screen-scheme/v1",
            longitudinal_decision_digest="d",
            longitudinal_history=project_longitudinal_history([], nodes_completed=0),
            language="es",
        )
    )
    service.renders = SimpleNamespace(
        find_cached=AsyncMock(return_value=None),
        get_by_cache_key=AsyncMock(return_value=spent_row),
    )
    return service


def _failed_row(key: str):
    """What a run that could not produce a screen at all leaves behind."""
    return SimpleNamespace(
        id=uuid.uuid4(), status=NodeRenderStatus.FAILED, cache_key=key, ui_spec=None
    )


def _call(service, monkeypatch, *, spawned: list):
    monkeypatch.setattr(
        "src.agents.runtime.runner.spawn_node_render",
        lambda state: spawned.append(state),
    )
    return service.request_render(
        user=SimpleNamespace(id=uuid.uuid4()),
        node=SimpleNamespace(
            id=uuid.uuid4(),
            reviewed_at=object(),
            org_id=uuid.uuid4(),
            course_id=uuid.uuid4(),
        ),
        course=SimpleNamespace(schema_version=1),
    )


@pytest.mark.asyncio
async def test_a_failed_key_with_nothing_pinned_spends_the_same_budget(monkeypatch) -> None:
    """A generation was already spent on this key and served nothing: charge for the retry.

    The learner has no screen, so the client keeps asking — which is exactly why this is the
    most expensive state to leave uncapped. It still regenerates while the budget lasts.
    """
    key = f"{current_render_safety_prefix()}nothing-servable"
    spawned: list[dict] = []

    result = await _call(
        _unpinned_service(spent_row=_failed_row(key), key=key), monkeypatch,
        spawned=spawned,
    )

    assert len(spawned) == 1
    assert result.cached is False
    assert fallback_retry_available(key) is False


@pytest.mark.asyncio
async def test_a_failed_key_stops_generating_once_the_budget_is_spent(monkeypatch) -> None:
    """The loop that had no guard: ``GET /render`` answers ``202`` because nothing is
    pinned, the client re-arms ``POST /render``, and every poll bought a full LLM cycle
    because neither the cache nor the fallback pin could see that anything had been tried.
    """
    key = f"{current_render_safety_prefix()}nothing-servable-exhausted"
    for attempt in range(FALLBACK_RETRY_MAX_ATTEMPTS):
        assert claim_fallback_retry(key, now=attempt * 10_000.0) is True

    monkeypatch.setattr(
        "src.agents.runtime.runner.spawn_node_render",
        lambda _state: pytest.fail("an exhausted budget must not spawn a render"),
    )
    result = await _unpinned_service(spent_row=_failed_row(key), key=key).request_render(
        user=SimpleNamespace(id=uuid.uuid4()),
        node=SimpleNamespace(
            id=uuid.uuid4(),
            reviewed_at=object(),
            org_id=uuid.uuid4(),
            course_id=uuid.uuid4(),
        ),
        course=SimpleNamespace(schema_version=1),
    )

    assert result.cached is False
    assert result.request_id == ""
    assert result.render_id is None


@pytest.mark.asyncio
async def test_a_first_visit_to_a_fresh_key_is_never_charged(monkeypatch) -> None:
    """The guard reads ``failed`` only: a key nobody has tried generates for free, and a
    ``generating`` row is somebody else's run in flight, not a spent attempt."""
    key = f"{current_render_safety_prefix()}fresh-key"
    spawned: list[dict] = []

    await _call(_unpinned_service(spent_row=None, key=key), monkeypatch, spawned=spawned)
    generating = SimpleNamespace(
        id=uuid.uuid4(), status=NodeRenderStatus.GENERATING, cache_key=key, ui_spec=None
    )
    await _call(
        _unpinned_service(spent_row=generating, key=key), monkeypatch, spawned=spawned
    )

    assert len(spawned) == 2
    assert fallback_retry_available(key) is True


@pytest.mark.asyncio
async def test_request_render_holds_the_fallback_once_the_budget_is_spent(
    monkeypatch,
) -> None:
    """The loop guard: an exhausted key answers with the backup render and spends nothing."""
    fallback = _legacy_render("degraded")
    # Spend the whole budget, each attempt well past the previous cooldown.
    for attempt in range(FALLBACK_RETRY_MAX_ATTEMPTS):
        assert claim_fallback_retry(fallback.cache_key, now=attempt * 10_000.0) is True
    assert fallback_retry_available(fallback.cache_key) is False

    service = NodeRenderService(SimpleNamespace())
    service.pinned_render = AsyncMock(return_value=fallback)  # type: ignore[method-assign]
    service.render_key_for = AsyncMock()  # type: ignore[method-assign]
    monkeypatch.setattr(
        "src.agents.runtime.runner.spawn_node_render",
        lambda _state: pytest.fail("an exhausted budget must not spawn a render"),
    )

    result = await service.request_render(
        user=SimpleNamespace(id=uuid.uuid4()),
        node=SimpleNamespace(id=uuid.uuid4(), reviewed_at=object()),
        course=SimpleNamespace(),
    )

    assert result.cached is True
    assert result.render_id == fallback.id
    service.render_key_for.assert_not_awaited()
