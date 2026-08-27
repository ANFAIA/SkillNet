"""The creation-run state a course now carries, and the pieces that write it.

These are the parts of the "a closed tab must not strand a course" work that need no
database: the failure classifier, the eager SSE subscription the progress stream depends
on, the task-registry lookup the finalize endpoint uses to stay idempotent, and the
projector that keeps a pre-0025 course reading ``idle``.
"""

import asyncio

import pytest

from src.core import sse
from src.core.exceptions import LLMError
from src.core.tasks import TaskRegistry
from src.models import CourseGenerationState
from src.routes.courses import _generation_state
from src.services import course_finalization as finalization


class _Fake:
    """A course-shaped object, the way the other projector tests build one."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# --------------------------------------------------------------------------------------
# The projector
# --------------------------------------------------------------------------------------
def test_generation_state_reads_the_enum_value():
    course = _Fake(generation_state=CourseGenerationState.FAILED)
    assert _generation_state(course) == "failed"


def test_generation_state_of_a_course_without_the_column_is_idle():
    """A course built before migration 0025 must read ``idle``, not crash the listing."""
    assert _generation_state(_Fake()) == "idle"


def test_every_state_round_trips_through_the_projector():
    for member in CourseGenerationState:
        assert _generation_state(_Fake(generation_state=member)) == member.value


# --------------------------------------------------------------------------------------
# Failure classification: a code and a safe sentence, never the exception
# --------------------------------------------------------------------------------------
def test_llm_failure_is_classified_without_leaking_the_exception():
    secret = "https://api.internal.example/v1 key=sk-abcdef"
    code, message = finalization.classify_failure(LLMError(secret))
    assert code == finalization.ERROR_LLM_FAILED
    assert secret not in message
    assert message == finalization.ERROR_MESSAGES[finalization.ERROR_LLM_FAILED]


def test_a_rejected_schema_is_its_own_code():
    from src.services.course_schema_service import SchemaInvalid

    code, _ = finalization.classify_failure(SchemaInvalid([{"code": "no_nodes"}]))
    assert code == finalization.ERROR_SCHEMA_REJECTED


def test_a_connection_failure_reads_as_the_provider_being_down():
    code, _ = finalization.classify_failure(ConnectionError("connection reset"))
    assert code == finalization.ERROR_PROVIDER_DOWN


def test_an_unrecognised_failure_falls_back_to_internal():
    code, message = finalization.classify_failure(RuntimeError("kaboom"))
    assert code == finalization.ERROR_INTERNAL
    assert "kaboom" not in message


def test_every_message_fits_the_column():
    # ``courses.generation_error`` is VARCHAR(500) in migration 0025.
    assert all(len(text) <= 500 for text in finalization.ERROR_MESSAGES.values())


# --------------------------------------------------------------------------------------
# `has_running`: what keeps the finalize endpoint idempotent
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_has_running_sees_a_live_task_and_forgets_a_finished_one():
    registry = TaskRegistry()
    release = asyncio.Event()

    async def waiter():
        await release.wait()

    registry.spawn(waiter(), name="finalize-course:abc")
    await asyncio.sleep(0)
    assert registry.has_running("finalize-course:abc") is True
    assert registry.has_running("finalize-course:other") is False

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert registry.has_running("finalize-course:abc") is False


# --------------------------------------------------------------------------------------
# The eager subscription the progress stream replays against
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_subscription_receives_events_published_before_it_is_consumed():
    """The whole point: register first, do work, and still get what was published.

    ``subscribe()`` is an async generator whose body does not run until the first await,
    so it registers nothing up front — a status read placed between the call and the
    first iteration would sit inside the window it was meant to close.
    """
    channel = "generation:test-eager"
    subscription = sse.Subscription(channel)
    try:
        assert sse.subscriber_count(channel) == 1
        await sse.publish(channel, "step", {"step": "generating"})
        event = await asyncio.wait_for(subscription.get(), timeout=1)
        assert event == {"type": "step", "data": {"step": "generating"}}
    finally:
        subscription.close()
    assert sse.subscriber_count(channel) == 0


@pytest.mark.asyncio
async def test_closing_a_subscription_twice_is_harmless():
    subscription = sse.Subscription("generation:test-idempotent")
    subscription.close()
    subscription.close()
    assert sse.subscriber_count("generation:test-idempotent") == 0


# --------------------------------------------------------------------------------------
# The state a just-connected client is handed
# --------------------------------------------------------------------------------------
def test_replay_maps_each_job_status_to_the_event_the_client_knows():
    import uuid

    from src.models import GenerationStep
    from src.routes.generation_jobs import _TERMINAL_EVENTS, _replay

    course_id = uuid.uuid4()

    assert _replay(GenerationStep.GENERATING, None, None) == (
        "step",
        {"step": "generating"},
    )
    assert _replay(GenerationStep.PUBLISHED, course_id, None) == (
        "completed",
        {"course_id": str(course_id)},
    )
    assert _replay(GenerationStep.SCHEMA_PROPOSED, course_id, None)[0] == "schema_ready"

    event, data = _replay(GenerationStep.FAILED, None, "provider down")
    assert event == "error" and data == {"message": "provider down"}

    # A job that finished before the client connected must still end the stream, or the
    # browser waits for an event that will never be published again.
    for status in (
        GenerationStep.PUBLISHED,
        GenerationStep.FAILED,
        GenerationStep.SCHEMA_PROPOSED,
    ):
        assert _replay(status, course_id, "x")[0] in _TERMINAL_EVENTS


def test_replay_of_a_running_job_is_not_terminal():
    from src.models import GenerationStep
    from src.routes.generation_jobs import _TERMINAL_EVENTS, _replay

    for status in (
        GenerationStep.PENDING,
        GenerationStep.EXTRACTING,
        GenerationStep.STRUCTURING,
        GenerationStep.GENERATING,
        GenerationStep.REVIEWING,
    ):
        assert _replay(status, None, None)[0] not in _TERMINAL_EVENTS


def test_the_startup_sweep_covers_every_non_terminal_job_status():
    """Terminal states must be left alone; everything else is dead after a restart."""
    from src.models import GenerationStep
    from src.services.startup_reconcile import _UNFINISHED_JOB_STATES

    terminal = {
        GenerationStep.SCHEMA_PROPOSED,
        GenerationStep.PUBLISHED,
        GenerationStep.FAILED,
    }
    assert set(_UNFINISHED_JOB_STATES) | terminal == set(GenerationStep)
    assert not set(_UNFINISHED_JOB_STATES) & terminal
