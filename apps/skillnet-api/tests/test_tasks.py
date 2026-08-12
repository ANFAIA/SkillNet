import asyncio

from src.core.tasks import TaskRegistry


async def test_spawn_unique_reuses_an_inflight_named_task() -> None:
    registry = TaskRegistry()
    release = asyncio.Event()
    calls = 0

    async def worker() -> None:
        nonlocal calls
        calls += 1
        await release.wait()

    first = registry.spawn_unique(worker(), "knowledge-pack:course:v1")
    second = registry.spawn_unique(worker(), "knowledge-pack:course:v1")

    assert second is first
    await asyncio.sleep(0)
    assert calls == 1

    release.set()
    await first
