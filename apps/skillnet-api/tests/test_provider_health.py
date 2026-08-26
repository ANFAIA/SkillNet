"""The in-process registry of recent provider failures (src/services/provider_health.py).

It is called from ``except`` blocks on the hot path, so "never raises" is a property under
test, not a comment.
"""

from __future__ import annotations

import pytest

from src.schemas.capabilities import CapabilityReason
from src.services import provider_health


@pytest.fixture(autouse=True)
def _clean():
    provider_health.reset()
    yield
    provider_health.reset()


def test_a_healthy_provider_reports_nothing() -> None:
    assert provider_health.status_for(provider_health.LLM) is None


def test_a_recorded_failure_is_reported_as_its_reason() -> None:
    provider_health.record_failure(provider_health.IMAGES, "quota")

    assert provider_health.status_for(provider_health.IMAGES) == (
        CapabilityReason.PROVIDER_QUOTA,
    )


def test_failures_are_kept_per_provider() -> None:
    provider_health.record_failure(provider_health.TTS, "down")

    assert provider_health.status_for(provider_health.TTS) is not None
    assert provider_health.status_for(provider_health.LLM) is None


def test_quota_is_reported_before_down() -> None:
    provider_health.record_failure(provider_health.LLM, "down")
    provider_health.record_failure(provider_health.LLM, "quota")

    assert provider_health.status_for(provider_health.LLM) == (
        CapabilityReason.PROVIDER_QUOTA,
        CapabilityReason.PROVIDER_DOWN,
    )


def test_a_failure_expires_with_its_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 1_000.0}
    monkeypatch.setattr(provider_health.time, "monotonic", lambda: clock["now"])

    provider_health.record_failure(provider_health.IMAGES, "down")
    assert provider_health.status_for(provider_health.IMAGES) is not None

    clock["now"] += provider_health.FAILURE_TTL_SECONDS + 1
    assert provider_health.status_for(provider_health.IMAGES) is None


def test_recording_again_pushes_the_deadline_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 1_000.0}
    monkeypatch.setattr(provider_health.time, "monotonic", lambda: clock["now"])

    provider_health.record_failure(provider_health.IMAGES, "down")
    clock["now"] += provider_health.FAILURE_TTL_SECONDS - 1
    provider_health.record_failure(provider_health.IMAGES, "down")

    clock["now"] += provider_health.FAILURE_TTL_SECONDS - 1
    assert provider_health.status_for(provider_health.IMAGES) is not None


def test_reset_forgets_everything() -> None:
    provider_health.record_failure(provider_health.LLM, "quota")
    provider_health.record_failure(provider_health.TTS, "down")

    provider_health.reset()

    assert provider_health.status_for(provider_health.LLM) is None
    assert provider_health.status_for(provider_health.TTS) is None


def test_nonsense_input_is_ignored_and_never_raises() -> None:
    provider_health.record_failure("not-a-provider", "quota")
    provider_health.record_failure(provider_health.LLM, "not-a-kind")  # type: ignore[arg-type]
    provider_health.record_failure(None, None)  # type: ignore[arg-type]

    assert provider_health.status_for("not-a-provider") is None
    assert provider_health.status_for(provider_health.LLM) is None
    assert provider_health.status_for(None) is None  # type: ignore[arg-type]


class _WithStatus(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("boom")
        self.status_code = status_code


class _WithResponse(Exception):
    class _Resp:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    def __init__(self, status_code: int) -> None:
        super().__init__("boom")
        self.response = self._Resp(status_code)


class RateLimitError(Exception):
    """Named exactly as litellm names it — the classifier keys off the type name."""


@pytest.mark.parametrize("status", [429, 402])
def test_quota_statuses_classify_as_quota(status: int) -> None:
    assert provider_health.failure_kind(_WithStatus(status)) == "quota"
    assert provider_health.failure_kind(_WithResponse(status)) == "quota"


def test_other_failures_classify_as_down() -> None:
    assert provider_health.failure_kind(_WithStatus(500)) == "down"
    assert provider_health.failure_kind(RuntimeError("espeak missing")) == "down"
    assert provider_health.failure_kind(TimeoutError()) == "down"


def test_a_chained_status_survives_normalization() -> None:
    """The TTS providers wrap httpx errors in a RuntimeError with ``raise ... from exc``."""
    try:
        try:
            raise _WithStatus(429)
        except _WithStatus as exc:
            raise RuntimeError("Azure Speech request failed") from exc
    except RuntimeError as exc:
        assert provider_health.failure_kind(exc) == "quota"


def test_a_rate_limit_error_without_a_status_still_classifies_as_quota() -> None:
    assert provider_health.failure_kind(RateLimitError("slow down")) == "quota"


def test_classification_never_raises_on_a_hostile_exception() -> None:
    class _Hostile(Exception):
        @property
        def status_code(self):  # noqa: ANN201 - deliberately explosive
            raise ValueError("no")

    assert provider_health.failure_kind(_Hostile()) == "down"
