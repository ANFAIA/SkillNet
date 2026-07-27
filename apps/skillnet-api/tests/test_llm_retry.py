"""Backoff shaped for a tokens-per-minute quota, not for a flaky socket.

The retry policy was `wait_exponential(multiplier=2, min=4, max=60)` over three
attempts, so the two waits were about 4 s and 8 s and the call gave up roughly twelve
seconds in. Against a *per-minute token* limit that is guaranteed to fail: the window
has not reset and will not for another forty-odd seconds.

Measured on Groq's free tier (6000 TPM) on 2026-07-27, generating a course from an
idea: the pipeline reached `review_quality` and died there, on a limit whose own error
message read "Please try again in 27.91s". Six LLM calls of work thrown away for want of
reading the number the provider had already supplied.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.config import settings
from src.llm.client import _retry_after_seconds, _retry_attempts, _retry_wait

GROQ_429 = (
    "litellm.RateLimitError: RateLimitError: GroqException - "
    '{"error":{"message":"Rate limit reached for model `llama-3.1-8b-instant` in '
    "organization `org_01ky` service tier `on_demand` on tokens per minute (TPM): "
    'Limit 6000, Used 3829, Requested 4962. Please try again in 27.91s.",'
    '"type":"tokens","code":"rate_limit_exceeded"}}'
)


def _state(exc: BaseException | None, attempt: int = 1) -> SimpleNamespace:
    outcome = SimpleNamespace(exception=lambda: exc) if exc is not None else None
    return SimpleNamespace(outcome=outcome, attempt_number=attempt)


# --------------------------------------------------------------------------------------
# Reading the provider's own estimate
# --------------------------------------------------------------------------------------
def test_the_wait_groq_asks_for_is_the_wait_we_take():
    assert _retry_after_seconds(RuntimeError(GROQ_429)) == pytest.approx(27.91)


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Please try again in 27.91s", 27.91),
        ("please try again in 5s", 5.0),
        ("Try again in 12.5 s later", 12.5),
        ("Rate limited", None),
        ("", None),
    ],
)
def test_the_estimate_is_read_when_present_and_not_invented_when_absent(message, expected):
    got = _retry_after_seconds(RuntimeError(message))
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected)


def test_no_exception_yields_no_estimate():
    assert _retry_after_seconds(None) is None


# --------------------------------------------------------------------------------------
# The wait itself
# --------------------------------------------------------------------------------------
def test_the_hinted_wait_crosses_the_window_the_old_policy_died_inside():
    """The whole point: 27.91 s, not the ~8 s the exponential policy would have waited."""
    wait = _retry_wait(_state(RuntimeError(GROQ_429), attempt=1))
    assert wait == pytest.approx(28.41)  # the hint, plus half a second of slack
    assert wait > 12.0, "must outlast the twelve seconds the old policy gave up after"


def test_without_a_hint_it_falls_back_to_exponential():
    first = _retry_wait(_state(RuntimeError("boom"), attempt=1))
    second = _retry_wait(_state(RuntimeError("boom"), attempt=2))
    third = _retry_wait(_state(RuntimeError("boom"), attempt=3))
    assert first < second < third


def test_a_single_wait_is_capped(monkeypatch: pytest.MonkeyPatch):
    """A provider that asks for ten minutes is asking for more than a request can give.
    Past a minute the TPM window has reset anyway."""
    monkeypatch.setattr(settings, "LLM_RETRY_MAX_WAIT_SECONDS", 90.0)
    assert _retry_wait(_state(RuntimeError("try again in 600s"))) == pytest.approx(90.0)


def test_the_wait_is_never_zero():
    assert _retry_wait(_state(RuntimeError("try again in 0s"))) >= 1.0


def test_the_ceiling_is_a_setting(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "LLM_RETRY_MAX_WAIT_SECONDS", 10.0)
    assert _retry_wait(_state(RuntimeError(GROQ_429))) == pytest.approx(10.0)


# --------------------------------------------------------------------------------------
# Attempts
# --------------------------------------------------------------------------------------
def test_the_default_allows_more_than_one_window():
    assert _retry_attempts() >= 4


def test_attempts_are_a_setting_and_never_below_one(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "LLM_MAX_ATTEMPTS", 7)
    assert _retry_attempts() == 7
    monkeypatch.setattr(settings, "LLM_MAX_ATTEMPTS", 0)
    assert _retry_attempts() == 1
