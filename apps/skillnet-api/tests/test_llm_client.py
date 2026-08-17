"""``LLMService``: token accounting, and the reasoning models that answer with nothing.

Two failures are pinned here, both measured against Groq rather than imagined:

1. **The empty answer.** ``openai/gpt-oss-120b`` is a reasoning model: it writes its chain
   of thought into a separate ``reasoning`` field that is billed against the *same*
   ``max_tokens`` as the answer. At ``max_tokens=1200`` some calls spent the whole budget
   thinking (4600+ characters of it) and returned ``content=""`` with
   ``finish_reason="length"``. That is not an invalid generation, it is an unfinished one,
   and the runtime treating it as invalid is what turned a budget mistake into an
   intermittent "the model is broken" with a wasted repair loop attached.
2. **Cost that cannot be seen.** ``tokens_in`` / ``tokens_out`` reaching ``node_renders``
   and ``llm_usage_log`` as NULL makes §9.3 unanswerable: prompt tuning without them is
   tuning quality with the price tag cut off.

Every provider payload below is a **recorded** response, kept in the wire shape litellm
returns, and rebuilt through litellm's own ``ModelResponse`` so the test exercises the same
attribute access the production path does.
"""

from __future__ import annotations

import logging
from typing import Any

import litellm
import pytest
from litellm.types.utils import ModelResponse, ModelResponseStream

from src.core.exceptions import LLMError
from src.llm.client import (
    BUDGET_EXHAUSTED,
    LLMConfig,
    LLMService,
    budget_for,
    is_reasoning_model,
    reasoning_kwargs,
)

REASONING_MODEL = "openai/gpt-oss-120b"
FAST_MODEL = "openai/llama-3.1-8b-instant"


# --------------------------------------------------------------------------- #
# Recorded payloads
# --------------------------------------------------------------------------- #

#: Recorded from Groq: the whole budget went into `reasoning`, `content` came back empty
#: and `finish_reason` is `length`. The reasoning text is elided to its measured size.
RECORDED_BUDGET_EXHAUSTED: dict[str, Any] = {
    "id": "chatcmpl-budget-exhausted",
    "object": "chat.completion",
    "created": 1753600000,
    "model": "openai/gpt-oss-120b",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "",
                "reasoning": "We need to produce a Screen(...). " + "x" * 4600,
            },
            "finish_reason": "length",
        }
    ],
    "usage": {"prompt_tokens": 812, "completion_tokens": 1200, "total_tokens": 2012},
}

#: The same prompt, same model, a call that did reach the answer.
RECORDED_OK: dict[str, Any] = {
    "id": "chatcmpl-ok",
    "object": "chat.completion",
    "created": 1753600001,
    "model": "openai/gpt-oss-120b",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": 'Screen(title: "Retencion")'},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 812, "completion_tokens": 96, "total_tokens": 908},
}

#: A **non-empty** answer cut off for length: the model wrote text but never reached the
#: end. In ``json_mode`` this is unparseable — the closing braces never arrived — so it
#: must be retried like the empty case rather than handed to the caller's parser.
RECORDED_TRUNCATED_NONEMPTY: dict[str, Any] = {
    "id": "chatcmpl-truncated",
    "object": "chat.completion",
    "created": 1753600005,
    "model": "openai/gpt-oss-120b",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": '{"must_preserve": [{"atom_id"'},
            "finish_reason": "length",
        }
    ],
    "usage": {"prompt_tokens": 812, "completion_tokens": 1200, "total_tokens": 2012},
}

#: An answer that is empty because the model had nothing to say — `finish_reason` is
#: `stop`. Nothing about it is a budget problem and nothing about it may be retried.
RECORDED_EMPTY_BUT_FINISHED: dict[str, Any] = {
    "id": "chatcmpl-empty-stop",
    "object": "chat.completion",
    "created": 1753600002,
    "model": "openai/gpt-oss-120b",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": ""},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 40, "completion_tokens": 0, "total_tokens": 40},
}


def _chunk(content: str | None, finish_reason: str | None = None) -> ModelResponseStream:
    return ModelResponseStream(
        id="chatcmpl-stream",
        object="chat.completion.chunk",
        created=1753600003,
        model="openai/gpt-oss-120b",
        choices=[{"index": 0, "delta": {"content": content}, "finish_reason": finish_reason}],
    )


def _usage_chunk(prompt_tokens: int, completion_tokens: int) -> ModelResponseStream:
    """The final chunk `stream_options={"include_usage": True}` asks for.

    It carries **no** choices, which is the shape the delta reader has to survive.
    """
    return ModelResponseStream(
        id="chatcmpl-stream",
        object="chat.completion.chunk",
        created=1753600004,
        model="openai/gpt-oss-120b",
        choices=[],
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #


class RecordedProvider:
    """``litellm.acompletion`` replaced by a queue of recorded outcomes.

    Each entry is a payload dict (a completion), a list of chunks (a stream) or an
    exception to raise. Every call's kwargs are kept so the test can assert on what was
    actually asked for — the budget and the reasoning knob are the whole point.
    """

    def __init__(self, *outcomes: Any) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(dict(kwargs))
        outcome = self._outcomes.pop(0) if self._outcomes else self._outcomes
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, list):
            return _replay(outcome)
        return ModelResponse(**outcome)

    @property
    def budgets(self) -> list[int]:
        return [call["max_tokens"] for call in self.calls]


async def _replay(chunks: list[ModelResponseStream]) -> Any:
    for chunk in chunks:
        yield chunk


def _service(model: str = REASONING_MODEL) -> LLMService:
    return LLMService(LLMConfig(model=model, api_base=None, api_key=None))


@pytest.fixture(autouse=True)
def _fixed_reasoning_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the two knobs, so a change to the shipped default cannot silently rewrite the
    numbers these tests assert."""
    from src.config import settings

    monkeypatch.setattr(settings, "LLM_REASONING_EFFORT", "low", raising=False)
    monkeypatch.setattr(settings, "LLM_REASONING_TOKEN_HEADROOM", 2048, raising=False)


# --------------------------------------------------------------------------- #
# Reasoning-model detection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "model",
    [
        "openai/gpt-oss-120b",
        "groq/openai/gpt-oss-120b",
        "deepseek/deepseek-reasoner",
        "o3-mini",
        "o1",
    ],
)
def test_reasoning_models_are_recognised(model: str) -> None:
    assert is_reasoning_model(model) is True


@pytest.mark.parametrize(
    "model",
    ["openai/llama-3.1-8b-instant", "gpt-4o-mini", "deepseek/deepseek-chat"],
)
def test_ordinary_models_are_not_mistaken_for_reasoning_models(model: str) -> None:
    """``llama-3.1-8b-instant`` is the fast tier of this deployment: giving it reasoning
    headroom on every render would pay for nothing."""
    assert is_reasoning_model(model) is False


def test_the_deployed_model_string_is_caught_even_though_litellm_misses_it() -> None:
    """``.env`` reaches Groq as an OpenAI-compatible endpoint, so the model string is
    ``openai/gpt-oss-120b`` — which litellm's registry does not know as a reasoning model.

    Detection by registry alone would leave exactly the model that produced the bug
    undetected, which is why detection is by name.
    """
    assert litellm.supports_reasoning(model=REASONING_MODEL) is False
    assert is_reasoning_model(REASONING_MODEL) is True


def test_a_model_whose_thinking_is_opt_in_is_left_alone() -> None:
    """The other direction, and the reason ``supports_reasoning`` is not the test used.

    litellm calls Claude Sonnet 4 a reasoning model — correctly, it *can* think — but its
    extended thinking is off until asked for. Sending ``reasoning_effort`` would switch it
    on for every v1 deployment on Anthropic: a cost and behaviour change made by a fix
    aimed at a different model.
    """
    claude = "anthropic/claude-sonnet-4-20250514"
    assert litellm.supports_reasoning(model=claude) is True
    assert is_reasoning_model(claude) is False
    assert reasoning_kwargs(claude) == {}


def test_headroom_is_added_only_where_thinking_is_billed() -> None:
    assert budget_for(REASONING_MODEL, 1200) == 1200 + 2048
    assert budget_for(FAST_MODEL, 1200) == 1200


def test_reasoning_effort_is_forced_through_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    """``allowed_openai_params`` is not decoration.

    Verified against litellm 1.91.3 for this model: a bare ``reasoning_effort`` raises
    ``UnsupportedParamsError`` and ``drop_params=True`` discards it silently. Only the
    allow-list forwards it to the provider.
    """
    from litellm.utils import get_optional_params

    kwargs = reasoning_kwargs(REASONING_MODEL)
    assert kwargs == {"reasoning_effort": "low", "allowed_openai_params": ["reasoning_effort"]}

    with pytest.raises(litellm.UnsupportedParamsError):
        get_optional_params(
            model=REASONING_MODEL,
            custom_llm_provider="openai",
            reasoning_effort="low",
        )
    forwarded = get_optional_params(
        model=REASONING_MODEL,
        custom_llm_provider="openai",
        max_tokens=1200,
        **kwargs,
    )
    assert forwarded["reasoning_effort"] == "low"


def test_no_reasoning_parameters_reach_an_ordinary_model() -> None:
    assert reasoning_kwargs(FAST_MODEL) == {}


def test_the_effort_knob_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """``none`` means "never send it": a provider that has never heard of the parameter is
    a support question the owner should be able to settle from ``.env``."""
    from src.config import settings

    monkeypatch.setattr(settings, "LLM_REASONING_EFFORT", "none", raising=False)
    assert reasoning_kwargs(REASONING_MODEL) == {}


# --------------------------------------------------------------------------- #
# complete_with_usage: the recorded usage block
# --------------------------------------------------------------------------- #


async def test_usage_comes_back_from_the_recorded_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordedProvider(RECORDED_OK)
    monkeypatch.setattr(litellm, "acompletion", provider)

    text, usage = await _service().complete_with_usage("sys", "user", max_tokens=1200)

    assert text == 'Screen(title: "Retencion")'
    assert (usage.tokens_in, usage.tokens_out, usage.reason) == (812, 96, None)


async def test_a_missing_usage_block_is_a_named_gap_not_a_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``0`` would claim the call was free. ``None`` plus a reason says nobody counted."""
    payload = {**RECORDED_OK}
    payload.pop("usage")
    provider = RecordedProvider(payload)
    monkeypatch.setattr(litellm, "acompletion", provider)

    _text, usage = await _service().complete_with_usage("sys", "user")

    assert (usage.tokens_in, usage.tokens_out) == (None, None)
    assert usage.reason


async def test_complete_keeps_its_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """``complete`` is the v1 path: it returns a string and nothing about it moved."""
    monkeypatch.setattr(litellm, "acompletion", RecordedProvider(RECORDED_OK))

    assert await _service().complete("sys", "user") == 'Screen(title: "Retencion")'


async def test_the_asked_budget_includes_the_thinking_room(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordedProvider(RECORDED_OK)
    monkeypatch.setattr(litellm, "acompletion", provider)

    await _service().complete_with_usage("sys", "user", max_tokens=1200)

    assert provider.budgets == [1200 + 2048]
    assert provider.calls[0]["reasoning_effort"] == "low"


# --------------------------------------------------------------------------- #
# complete_with_usage: the empty answer
# --------------------------------------------------------------------------- #


async def test_an_empty_answer_cut_off_for_length_is_retried_with_more_budget(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The recorded failure, replayed: budget exhausted, then the same call succeeds.

    What must NOT happen is the empty string reaching the caller, because the runtime
    reads that as an invalid program and spends a repair round on a program the model
    never got to write.
    """
    provider = RecordedProvider(RECORDED_BUDGET_EXHAUSTED, RECORDED_OK)
    monkeypatch.setattr(litellm, "acompletion", provider)

    with caplog.at_level(logging.WARNING):
        text, usage = await _service().complete_with_usage("sys", "user", max_tokens=1200)

    assert text == 'Screen(title: "Retencion")'
    assert provider.budgets == [3248, 3248 * 3]
    # Both attempts were billed; reporting only the survivor would understate the cost of
    # the heavy tier exactly where it is highest.
    assert (usage.tokens_in, usage.tokens_out) == (812 + 812, 1200 + 96)
    assert BUDGET_EXHAUSTED in caplog.text


async def test_the_budget_failure_is_logged_apart_from_a_bad_answer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Its own marker, at its own level. Tomorrow's tuning session has to be able to tell
    "the model wrote nonsense" from "we did not pay for enough tokens" by grepping."""
    monkeypatch.setattr(
        litellm, "acompletion", RecordedProvider(RECORDED_BUDGET_EXHAUSTED, RECORDED_OK)
    )

    with caplog.at_level(logging.WARNING):
        await _service().complete_with_usage("sys", "user", max_tokens=1200)

    budget_records = [r for r in caplog.records if BUDGET_EXHAUSTED in r.getMessage()]
    assert len(budget_records) == 1
    assert budget_records[0].levelno == logging.WARNING


async def test_the_retry_is_bounded(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """If 3x the budget still returns nothing the prompt is wrong, and a third full-price
    generation buys nothing. It gives up loudly instead."""
    provider = RecordedProvider(RECORDED_BUDGET_EXHAUSTED, RECORDED_BUDGET_EXHAUSTED)
    monkeypatch.setattr(litellm, "acompletion", provider)

    with caplog.at_level(logging.WARNING):
        text, usage = await _service().complete_with_usage("sys", "user", max_tokens=1200)

    assert text == ""
    assert len(provider.calls) == 2
    assert usage.tokens_out == 2400
    assert any(r.levelno == logging.ERROR for r in caplog.records)


async def test_truncated_json_with_content_is_retried_with_more_budget(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """In ``json_mode`` a length-cut answer is unparseable however much text it carries —
    the braces never closed. Handing that partial JSON to the caller's parser is exactly
    the ``KnowledgePackGenerationError: extractor returned invalid JSON`` failure; the
    client must buy more budget instead, like the empty case."""
    provider = RecordedProvider(RECORDED_TRUNCATED_NONEMPTY, RECORDED_OK)
    monkeypatch.setattr(litellm, "acompletion", provider)

    with caplog.at_level(logging.WARNING):
        text, _usage = await _service(FAST_MODEL).complete_with_usage(
            "sys", "user", max_tokens=1200, json_mode=True
        )

    assert text == 'Screen(title: "Retencion")'
    assert provider.budgets == [1200, 1200 * 3]
    assert BUDGET_EXHAUSTED in caplog.text


async def test_truncated_free_text_with_content_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside ``json_mode`` a cut-off answer is still an answer — a half-written prose
    reply is usable where half-written JSON is not — so it is returned, not paid for
    again."""
    provider = RecordedProvider(RECORDED_TRUNCATED_NONEMPTY)
    monkeypatch.setattr(litellm, "acompletion", provider)

    text, _usage = await _service(FAST_MODEL).complete_with_usage(
        "sys", "user", max_tokens=1200
    )

    assert text == '{"must_preserve": [{"atom_id"'
    assert len(provider.calls) == 1


async def test_an_answer_that_is_empty_on_purpose_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``finish_reason="stop"`` with no content is the model's answer, however useless.
    Paying for it three times over does not improve it."""
    provider = RecordedProvider(RECORDED_EMPTY_BUT_FINISHED)
    monkeypatch.setattr(litellm, "acompletion", provider)

    text, _usage = await _service().complete_with_usage("sys", "user")

    assert text == ""
    assert len(provider.calls) == 1


async def test_a_provider_that_refuses_the_reasoning_knob_still_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``allowed_openai_params`` takes litellm's validation off the parameter, so the
    provider is the only thing left saying no. Losing the render over a knob *we* chose
    would be worse than the problem the knob solves."""
    refusal = litellm.BadRequestError(
        message="unknown parameter reasoning_effort",
        model=REASONING_MODEL,
        llm_provider="openai",
    )
    provider = RecordedProvider(refusal, RECORDED_OK)
    monkeypatch.setattr(litellm, "acompletion", provider)

    text, _usage = await _service().complete_with_usage("sys", "user", max_tokens=1200)

    assert text == 'Screen(title: "Retencion")'
    assert "reasoning_effort" not in provider.calls[1]
    # The headroom stays: it is what covers the case the knob was there to prevent.
    assert provider.calls[1]["max_tokens"] == 3248


async def test_other_bad_requests_are_still_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    refusal = litellm.BadRequestError(
        message="context window exceeded",
        model=FAST_MODEL,
        llm_provider="openai",
    )
    monkeypatch.setattr(litellm, "acompletion", RecordedProvider(refusal))

    with pytest.raises(LLMError):
        await _service(FAST_MODEL).complete_with_usage("sys", "user")


# --------------------------------------------------------------------------- #
# stream: the same two problems on the path that matters
# --------------------------------------------------------------------------- #


async def test_the_stream_reports_usage_from_the_final_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``genera_ui`` streams, so a stream that cannot report usage is the expensive half
    of every render going unmeasured (§9.3)."""
    chunks = [_chunk("Screen("), _chunk('title: "X")', "stop"), _usage_chunk(812, 96)]
    provider = RecordedProvider(chunks)
    monkeypatch.setattr(litellm, "acompletion", provider)

    usage_out: dict[str, Any] = {}
    stream = _service().stream([{"role": "user", "content": "x"}], usage_out=usage_out)
    pieces = [p async for p in stream]

    assert "".join(pieces) == 'Screen(title: "X")'
    assert (usage_out["tokens_in"], usage_out["tokens_out"]) == (812, 96)
    assert usage_out["reason"] is None
    assert provider.calls[0]["stream_options"] == {"include_usage": True}


async def test_a_stream_that_never_started_is_retried_with_more_budget(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The reasoning model thought past its budget mid-stream: no deltas at all, then
    ``finish_reason="length"``. Retrying is safe precisely because nothing was yielded."""
    exhausted = [_chunk(None, "length"), _usage_chunk(812, 3248)]
    good = [_chunk("Screen("), _chunk('title: "X")', "stop"), _usage_chunk(812, 96)]
    provider = RecordedProvider(exhausted, good)
    monkeypatch.setattr(litellm, "acompletion", provider)

    usage_out: dict[str, Any] = {}
    with caplog.at_level(logging.WARNING):
        pieces = [
            p
            async for p in _service().stream(
                [{"role": "user", "content": "x"}], max_tokens=1200, usage_out=usage_out
            )
        ]

    assert "".join(pieces) == 'Screen(title: "X")'
    assert provider.budgets == [3248, 3248 * 3]
    assert (usage_out["tokens_in"], usage_out["tokens_out"]) == (1624, 3344)
    assert BUDGET_EXHAUSTED in caplog.text


async def test_a_stream_that_produced_something_is_never_replayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once a delta is out, the attempt is final: a retry would duplicate the text the
    caller already has, and ``genera_ui`` has already published it as a ``ui_block``."""
    truncated = [_chunk("Screen("), _chunk(None, "length")]
    provider = RecordedProvider(truncated, truncated)
    monkeypatch.setattr(litellm, "acompletion", provider)

    pieces = [p async for p in _service().stream([{"role": "user", "content": "x"}])]

    assert pieces == ["Screen("]
    assert len(provider.calls) == 1


async def test_the_v1_chat_request_is_unchanged_without_usage_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accounting is opt-in: asking for it changes the request, and the v1 chat path must
    keep sending byte-for-byte what it sent before."""
    provider = RecordedProvider([_chunk("hola", "stop")])
    monkeypatch.setattr(litellm, "acompletion", provider)

    pieces = [p async for p in _service(FAST_MODEL).stream([{"role": "user", "content": "x"}])]

    assert pieces == ["hola"]
    assert "stream_options" not in provider.calls[0]
    assert "reasoning_effort" not in provider.calls[0]
