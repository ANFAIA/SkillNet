"""Provider-agnostic LLM access via litellm.

Every LLM call in the application goes through ``LLMService``. No module imports
the ``openai`` SDK directly. The provider is chosen entirely by configuration
(env vars, optionally overridden per organization), so switching between OpenAI,
Anthropic, DeepSeek, Ollama, etc. requires no code change.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import litellm
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
)

from src.config import settings
from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.core.secrets import unseal
from src.services import provider_health

logger = get_logger(__name__)

# litellm raises provider-specific errors; these are the transient ones worth retrying.
_RETRYABLE = (
    litellm.RateLimitError,
    litellm.APIConnectionError,
    litellm.Timeout,
    litellm.InternalServerError,
    litellm.ServiceUnavailableError,
)

#: Providers that limit **tokens per minute** say how long to wait, in the message body:
#: ``"Rate limit reached ... Please try again in 27.91s"`` (Groq, and OpenAI in the same
#: shape). Honouring that number is the difference between a retry that works and one
#: that is guaranteed not to.
_RETRY_AFTER = re.compile(r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*s", re.IGNORECASE)


def _retry_after_seconds(exc: BaseException | None) -> float | None:
    """The provider's own estimate, if it gave one."""
    if exc is None:
        return None
    match = _RETRY_AFTER.search(str(exc))
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:  # pragma: no cover - the regex already guarantees a float
        return None


def _retry_wait(state: Any) -> float:
    """How long to wait before the next provider attempt.

    Plain exponential backoff is the wrong shape for a *tokens per minute* quota. It was
    the shape in use, at ``multiplier=2, min=4, max=60`` over three attempts, so the two
    waits were about 4 s and 8 s: the call gave up roughly 12 s into a window that resets
    after 60. Measured on Groq's free tier on 2026-07-27, that is exactly how a course
    generation died at ``review_quality`` — an entire multi-step pipeline lost to a limit
    the provider had already said would clear in 27.91 s.

    So: use the provider's number when it gives one, fall back to exponential when it
    does not, and cap it. The half second on top is slack for clock skew — coming back
    a hair early costs another full window.
    """
    exc = state.outcome.exception() if state.outcome else None
    hinted = _retry_after_seconds(exc)
    if hinted is None:
        base = _setting_float("LLM_RETRY_BASE_SECONDS", 4.0)
        hinted = base * (2 ** max(state.attempt_number - 1, 0))
    ceiling = _setting_float("LLM_RETRY_MAX_WAIT_SECONDS", 90.0)
    return min(max(hinted + 0.5, 1.0), ceiling)


def _setting_float(name: str, default: float) -> float:
    """``getattr`` with a default, and **not** ``or default``.

    ``0 or 4.0`` is ``4.0``, so the idiomatic-looking guard silently turns a deliberate
    zero into the default. Only ``None`` should fall back.
    """
    value = getattr(settings, name, None)
    return default if value is None else float(value)


def _retry_attempts() -> int:
    value = getattr(settings, "LLM_MAX_ATTEMPTS", None)
    return max(int(5 if value is None else value), 1)


def _failure_message(exc: BaseException) -> str:
    """What the admin reads when a generation dies.

    ``LLM request failed: RateLimitError`` is technically accurate and practically
    useless: it sends somebody looking for a bug in a pipeline that is working exactly
    as designed and is simply out of quota. A tokens-per-minute limit is a plan problem
    with a plan solution, and the message should say which one it is — measured against
    Groq's free tier (6000 TPM), where a single module-generation call requests about
    5000 of them.
    """
    if isinstance(exc, litellm.RateLimitError):
        return (
            "LLM rate limit reached after every retry. The provider's quota is the "
            "limit here, not the content: generating a full course needs several "
            "large calls in a row. Retry when the quota window has cleared, or move "
            "to a plan with a higher tokens-per-minute allowance."
        )
    return f"LLM request failed: {type(exc).__name__}"


# --------------------------------------------------------------------------- #
# Reasoning models: the thinking is billed against the answer's budget
# --------------------------------------------------------------------------- #

#: Model-name fragments that mark a *reasoning* model — one that emits its chain of
#: thought into a separate ``reasoning`` field charged against the **same** ``max_tokens``
#: as the answer.
#:
#: Measured on Groq's ``openai/gpt-oss-120b`` with ``max_tokens=1200``: some calls spent
#: the entire budget thinking (4600+ characters of it) and came back with an empty
#: ``content``. The runtime read that as an invalid program and burned the repair loop on
#: it, so the symptom was an intermittent, expensive failure that blames the model for
#: something the caller's budget caused.
_REASONING_NAME_HINTS: tuple[str, ...] = (
    "gpt-oss",
    "reasoner",
    "reasoning",
    "thinking",
    "qwq",
    "magistral",
)

#: OpenAI's o-series (``o1``, ``o3-mini``, ``o4-mini``...). Anchored on the bare model
#: name so no ordinary model is caught by a stray two-character substring.
_O_SERIES = re.compile(r"^o[1-9](?:[-_.]|$)")

#: What an empty completion's budget is multiplied by before it is asked for again.
BUDGET_RETRY_MULTIPLIER = 3

#: One growth step. A second means paying three times over for one screen, and if 3x the
#: budget still returns nothing the prompt is wrong — no amount of budget fixes that.
MAX_BUDGET_RETRIES = 1

#: Log marker for "the budget ran out", greppable and deliberately not shared with any
#: other failure. An empty ``content`` with ``finish_reason == "length"`` is not a bad
#: answer, it is an *unfinished* one: it must not reach the repair loop, and whoever reads
#: the logs has to be able to tell the two apart at a glance.
BUDGET_EXHAUSTED = "llm.budget_exhausted"


def is_reasoning_model(model: str) -> bool:
    """Whether ``model`` spends its ``max_tokens`` on thinking **before it is asked to**.

    Deliberately a name check and not ``litellm.supports_reasoning``, which answers a
    different question — *can* this model reason if asked — and answers it wrong in both
    directions for this purpose (verified against litellm 1.91.3):

    * ``supports_reasoning("openai/gpt-oss-120b") -> False``, and that string is the one
      this deployment carries in ``.env``: Groq reached as an OpenAI-compatible endpoint
      through ``LLM_BASE_URL``. The registry alone would miss exactly the model that
      produced the bug (it only knows the ``groq/`` prefixed spelling).
    * ``supports_reasoning("anthropic/claude-sonnet-4-...") -> True``, but its extended
      thinking is **off** until requested. Treating it as a reasoning model would send
      ``reasoning_effort`` and switch thinking on for every v1 deployment on Anthropic —
      a behaviour and cost change nobody asked for, made by a bug fix for another model.

    What matters here is the narrow family that thinks unprompted and bills it against the
    answer's budget. That family is recognisable by name.
    """
    name = (model or "").rsplit("/", 1)[-1].lower()
    return bool(any(hint in name for hint in _REASONING_NAME_HINTS) or _O_SERIES.match(name))


def reasoning_kwargs(model: str) -> dict[str, Any]:
    """``reasoning_effort`` for a reasoning model, in the only form litellm passes through.

    Verified with ``litellm.utils.get_optional_params`` on 1.91.3 for
    ``openai/gpt-oss-120b``: a bare ``reasoning_effort`` raises ``UnsupportedParamsError``,
    ``drop_params=True`` silently discards it, and only ``allowed_openai_params`` forwards
    it to the provider. Forwarding it is what stops the model from thinking away the whole
    budget; the headroom below is the net for the providers that drop it anyway.
    """
    effort = str(getattr(settings, "LLM_REASONING_EFFORT", "none") or "none").lower()
    if effort == "none" or not is_reasoning_model(model):
        return {}
    return {"reasoning_effort": effort, "allowed_openai_params": ["reasoning_effort"]}


def budget_for(model: str, max_tokens: int) -> int:
    """The caller's ``max_tokens`` plus room for a reasoning model to think in."""
    if not is_reasoning_model(model):
        return max_tokens
    headroom = int(getattr(settings, "LLM_REASONING_TOKEN_HEADROOM", 0) or 0)
    return max_tokens + max(headroom, 0)


def _finish_reason(response_or_chunk: Any) -> str | None:
    """The first choice's ``finish_reason``, read defensively.

    A stream's usage chunk carries no ``choices`` at all, so indexing is not an option.
    """
    choices = getattr(response_or_chunk, "choices", None) or ()
    if not choices:
        return None
    return getattr(choices[0], "finish_reason", None)


def _message_content(response: Any) -> str:
    """The assistant text of a non-streamed response, ``""`` when there is none."""
    choices = getattr(response, "choices", None) or ()
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return getattr(message, "content", None) or ""


def _add_tokens(left: int | None, right: int | None) -> int | None:
    """Sum two counts, keeping ``None`` when neither side ever measured anything.

    ``0`` and ``None`` are different answers: ``0`` claims the call was free, ``None``
    says nobody counted.
    """
    if left is None and right is None:
        return None
    return int(left or 0) + int(right or 0)


@dataclass(frozen=True)
class Usage:
    """The provider's token accounting for one call.

    Both fields are ``None`` when the provider did not report usage; ``reason`` says why,
    so ``llm_usage_log`` and ``node_renders`` record a *known* gap instead of a silent one.
    Without this the §9.3 cost model — the economic justification for sharing a
    ``cache_key`` at all — can only ever be settled with latency, which measures nothing
    about money.
    """

    tokens_in: int | None = None
    tokens_out: int | None = None
    reason: str | None = None

    @classmethod
    def of(cls, response: Any) -> Usage:
        """Read litellm's ``usage`` block off a response (or a streaming chunk)."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return cls(reason="provider returned no usage block")
        tokens_in = getattr(usage, "prompt_tokens", None)
        tokens_out = getattr(usage, "completion_tokens", None)
        if tokens_in is None and tokens_out is None:
            return cls(reason="provider usage block carried no token counts")
        return cls(
            tokens_in=int(tokens_in) if tokens_in is not None else None,
            tokens_out=int(tokens_out) if tokens_out is not None else None,
        )

    def plus(self, other: Usage) -> Usage:
        """Add a second attempt's cost to this one.

        A call that burned its budget thinking and returned nothing was still billed.
        Reporting only the attempt that succeeded would understate the heavy tier's cost
        precisely where it is highest, which is the comparison §9.3 exists to make.
        """
        tokens_in = _add_tokens(self.tokens_in, other.tokens_in)
        tokens_out = _add_tokens(self.tokens_out, other.tokens_out)
        if tokens_in is None and tokens_out is None:
            return Usage(reason=other.reason or self.reason)
        return Usage(tokens_in=tokens_in, tokens_out=tokens_out)


@dataclass(frozen=True)
class LLMConfig:
    """Resolved connection settings for a single LLM call."""

    model: str
    api_base: str | None
    api_key: str | None


def resolve_llm_config(
    org_settings: dict[str, Any] | None = None,
    *,
    purpose: str | None = None,
) -> LLMConfig:
    """Resolve the effective LLM config.

    Precedence: organization settings override environment defaults. ``purpose``
    (``"generation"``, ``"tutor"``, ``"eval"``) selects an optional per-purpose
    model, falling back to the base model.
    """
    org_settings = org_settings or {}

    model = (
        org_settings.get(f"llm_{purpose}_model") if purpose else None
    ) or org_settings.get("llm_model")
    if not model and purpose:
        env_specific = getattr(settings, f"LLM_{purpose.upper()}_MODEL", None)
        model = env_specific or None
    model = model or settings.LLM_MODEL

    api_base = org_settings.get("llm_base_url") or settings.LLM_BASE_URL or None
    # `unseal`, because the org's key is encrypted at rest (src/core/secrets.py). It is a
    # no-op on the environment default and on a key stored before that existed.
    api_key = unseal(org_settings.get("llm_api_key")) or settings.LLM_API_KEY or None
    return LLMConfig(model=model, api_base=api_base, api_key=api_key)


class LLMService:
    """Thin async wrapper over litellm with retries and error normalization."""

    def __init__(self, config: LLMConfig) -> None:
        if not config.model:
            raise LLMError("No LLM model configured. Set LLM_MODEL or org settings.")
        self._config = config

    @property
    def model(self) -> str:
        return self._config.model

    def _base_kwargs(self, model: str | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": model or self._config.model}
        if self._config.api_base:
            kwargs["api_base"] = self._config.api_base
        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key
        return kwargs

    @retry(
        stop=stop_after_attempt(_retry_attempts()),
        wait=_retry_wait,
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    )
    async def _acompletion(self, **kwargs: Any) -> Any:
        return await litellm.acompletion(**kwargs)

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """Single-shot completion. Returns the assistant message text."""
        text, _usage = await self.complete_with_usage(
            system_prompt,
            user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        return text

    async def complete_with_usage(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> tuple[str, Usage]:
        """``complete`` plus the provider's token counts.

        A separate method rather than a changed return type: ``complete`` has eight call
        sites, most of them v1, and a batch presented as additive must not rewrite them.

        The returned ``Usage`` is the cost of **every** attempt, including one thrown away
        for coming back empty: that attempt was billed too.
        """
        model_name = model or self._config.model
        kwargs = self._base_kwargs(model)
        kwargs["messages"] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs["temperature"] = temperature
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        kwargs.update(reasoning_kwargs(model_name))

        budget = budget_for(model_name, max_tokens)
        spent = Usage(reason="no attempt reported usage")
        for attempt in range(MAX_BUDGET_RETRIES + 1):
            kwargs["max_tokens"] = budget
            response = await self._completion_call(kwargs)
            spent = spent.plus(Usage.of(response))
            content = _message_content(response)
            truncated = _finish_reason(response) == "length"
            # A length-truncated ``json_mode`` answer is unparseable however much text it
            # carries — the closing braces never arrived — so it must buy more budget like
            # the empty case rather than reach the caller's parser as invalid JSON. In
            # free-text mode a truncated answer is still an answer, so only an *empty* cut
            # is retried there.
            if not (truncated and (json_mode or not content)):
                return content, spent
            # Cut off before finishing: the model never reached (or never closed) the
            # answer. Handing this to the caller would look like an invalid generation and
            # start a repair loop over a program the model never wrote.
            if attempt == MAX_BUDGET_RETRIES:
                logger.error(
                    "%s: %s did not finish at max_tokens=%d after %d attempt(s); "
                    "giving up",
                    BUDGET_EXHAUSTED,
                    model_name,
                    budget,
                    attempt + 1,
                )
                break
            logger.warning(
                "%s: %s spent all %d tokens before finishing; retrying at %d",
                BUDGET_EXHAUSTED,
                model_name,
                budget,
                budget * BUDGET_RETRY_MULTIPLIER,
            )
            budget *= BUDGET_RETRY_MULTIPLIER
        return "", spent

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        tool_choice: str = "auto",
    ) -> tuple[str, list[dict[str, Any]]]:
        """One non-streamed turn with native function-calling.

        Returns ``(text, tool_calls)``. ``tool_calls`` is ``[]`` when the provider
        answered in prose; each entry is ``{"id", "name", "arguments"}`` with
        ``arguments`` already parsed from the provider's JSON string — a malformed
        JSON on the provider's end raises ``LLMError`` rather than handing the
        agent loop a string it would fail to call ``.get`` on.

        Separate from :meth:`complete`/:meth:`complete_with_usage`: those two have
        no ``tools`` concept and eight call sites between them that must not change
        shape for one new caller (the admin agent).
        """
        model_name = model or self._config.model
        kwargs = self._base_kwargs(model)
        kwargs["messages"] = messages
        kwargs["temperature"] = temperature
        kwargs["max_tokens"] = budget_for(model_name, max_tokens)
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
        kwargs.update(reasoning_kwargs(model_name))

        response = await self._completion_call(kwargs)
        choices = getattr(response, "choices", None) or ()
        message = getattr(choices[0], "message", None) if choices else None
        raw_calls = getattr(message, "tool_calls", None) or []

        tool_calls: list[dict[str, Any]] = []
        for call in raw_calls:
            function = getattr(call, "function", None)
            name = getattr(function, "name", None) or ""
            raw_arguments = getattr(function, "arguments", None) or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except (json.JSONDecodeError, TypeError) as exc:
                raise LLMError(
                    f"Provider requested tool '{name}' with malformed arguments"
                ) from exc
            tool_calls.append(
                {"id": getattr(call, "id", None), "name": name, "arguments": arguments}
            )

        return (getattr(message, "content", None) or ""), tool_calls

    async def _completion_call(self, kwargs: dict[str, Any]) -> Any:
        """One provider call, with provider errors normalized to :class:`LLMError`.

        The ``reasoning_effort`` retreat lives here because that parameter is *forced*
        through with ``allowed_openai_params`` (see :func:`reasoning_kwargs`): litellm no
        longer vets it, so a provider that rejects it would otherwise turn a knob we chose
        into a failed render. Dropping it and calling again costs one round trip; the
        token headroom still covers the case it was meant to prevent.
        """
        try:
            return await self._acompletion(**kwargs)
        except LLMError:
            raise
        except litellm.RateLimitError as exc:
            # After `_acompletion`'s own retries. A key that is present but out of quota
            # looks perfect to the config-only capability read; this is where it learns
            # otherwise (src/services/provider_health.py).
            provider_health.record_failure(provider_health.LLM, "quota")
            logger.error("LLM completion failed: %s", exc, exc_info=True)
            raise LLMError(_failure_message(exc)) from exc
        except litellm.BadRequestError as exc:
            if "reasoning_effort" not in kwargs:
                logger.error("LLM completion failed: %s", exc, exc_info=True)
                raise LLMError(_failure_message(exc)) from exc
            logger.warning(
                "Provider rejected reasoning_effort for %s; retrying without it: %s",
                kwargs.get("model"),
                exc,
            )
            kwargs.pop("reasoning_effort", None)
            kwargs.pop("allowed_openai_params", None)
            return await self._completion_call(kwargs)
        except Exception as exc:  # noqa: BLE001 - normalize all provider errors
            # Not `BadRequestError`, which is handled above: a request this app built
            # wrongly is not evidence that the provider is unwell.
            provider_health.record_failure(provider_health.LLM, "down")
            logger.error("LLM completion failed: %s", exc, exc_info=True)
            raise LLMError(_failure_message(exc)) from exc

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        usage_out: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion token deltas for a full message list (chat).

        ``usage_out`` is opt-in accounting: pass a dict and it is filled with
        ``tokens_in`` / ``tokens_out`` / ``reason`` from the provider's final chunk. It is
        opt-in because asking for it changes the request — ``stream_options`` is an
        OpenAI-ism, and ``drop_params`` is what stops a provider that has never heard of it
        from failing the whole render over accounting. The v1 chat path passes nothing and
        its request is byte-for-byte what it was.

        The usage chunk carries **no** ``choices``, which is why the delta is read
        defensively below: indexing ``choices[0]`` on it is an ``IndexError`` mid-stream.

        A stream that ends having yielded **nothing** with ``finish_reason == "length"``
        is retried on a bigger budget, exactly as the single-shot path is. This is the one
        that mattered in practice: ``genera_ui`` streams, so without it a reasoning model
        that thinks past its budget produces an empty program on the hot path. Retrying is
        safe only because nothing was yielded — the moment a delta is out, the attempt is
        final and the caller keeps whatever arrived.
        """
        model_name = model or self._config.model
        kwargs = self._base_kwargs(model)
        kwargs["messages"] = messages
        kwargs["temperature"] = temperature
        kwargs["stream"] = True
        kwargs.update(reasoning_kwargs(model_name))
        if usage_out is not None:
            kwargs["stream_options"] = {"include_usage": True}
            kwargs["drop_params"] = True
            usage_out.setdefault("reason", "provider reported no usage on the stream")

        budget = budget_for(model_name, max_tokens)
        spent = Usage(reason="provider reported no usage on the stream")
        growths = 0
        while True:
            kwargs["max_tokens"] = budget
            state: dict[str, Any] = {
                "produced": False,
                "finish_reason": None,
                "usage": Usage(),
                "retreat": False,
            }
            async for piece in self._stream_once(kwargs, state):
                yield piece
            spent = spent.plus(state["usage"])
            if usage_out is not None:
                usage_out["tokens_in"] = spent.tokens_in
                usage_out["tokens_out"] = spent.tokens_out
                usage_out["reason"] = spent.reason
            if state["retreat"]:
                # The knob was rejected and removed; same budget, one more go. It can only
                # happen once, because `reasoning_effort` is gone from `kwargs` for good.
                continue
            if state["produced"] or state["finish_reason"] != "length":
                return
            if growths >= MAX_BUDGET_RETRIES:
                logger.error(
                    "%s: %s streamed no content at max_tokens=%d; giving up",
                    BUDGET_EXHAUSTED,
                    model_name,
                    budget,
                )
                return
            logger.warning(
                "%s: %s spent all %d streamed tokens before answering; retrying at %d",
                BUDGET_EXHAUSTED,
                model_name,
                budget,
                budget * BUDGET_RETRY_MULTIPLIER,
            )
            growths += 1
            budget *= BUDGET_RETRY_MULTIPLIER

    @retry(
        stop=stop_after_attempt(_retry_attempts()),
        wait=_retry_wait,
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    )
    async def _open_stream(self, kwargs: dict[str, Any]) -> Any:
        """Open the stream, retrying the transient refusals.

        Only the *opening* is retried, and only before a single delta exists, so nothing
        can be replayed to the caller twice. Groq's free tier answers 429 readily and the
        non-streamed path has had this since day one; the streamed one is the expensive
        call, so losing a whole render to a rate limit is the worse of the two outcomes.
        """
        return await litellm.acompletion(**kwargs)

    async def _stream_once(
        self, kwargs: dict[str, Any], state: dict[str, Any]
    ) -> AsyncIterator[str]:
        """One streamed attempt, recording into ``state`` what the caller has to judge it by.

        ``state`` carries ``produced`` (was anything yielded), ``finish_reason``, the
        attempt's ``usage`` and ``retreat`` (the provider refused ``reasoning_effort``, so
        it was dropped and the attempt should simply be repeated).
        """
        try:
            response = await self._open_stream(kwargs)
            async for chunk in response:
                if getattr(chunk, "usage", None) is not None:
                    state["usage"] = state["usage"].plus(Usage.of(chunk))
                reason = _finish_reason(chunk)
                if reason:
                    state["finish_reason"] = reason
                choices = getattr(chunk, "choices", None) or ()
                if not choices:
                    continue
                delta = choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    state["produced"] = True
                    yield piece
        except litellm.BadRequestError as exc:
            if state["produced"] or "reasoning_effort" not in kwargs:
                logger.error("LLM stream failed: %s", exc, exc_info=True)
                raise LLMError(f"LLM stream failed: {type(exc).__name__}") from exc
            logger.warning(
                "Provider rejected reasoning_effort for %s; retrying the stream without "
                "it: %s",
                kwargs.get("model"),
                exc,
            )
            kwargs.pop("reasoning_effort", None)
            kwargs.pop("allowed_openai_params", None)
            state["retreat"] = True
        except Exception as exc:  # noqa: BLE001 - normalize all provider errors
            provider_health.record_failure(
                provider_health.LLM, provider_health.failure_kind(exc)
            )
            logger.error("LLM stream failed: %s", exc, exc_info=True)
            raise LLMError(f"LLM stream failed: {type(exc).__name__}") from exc
