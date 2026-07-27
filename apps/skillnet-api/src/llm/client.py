"""Provider-agnostic LLM access via litellm.

Every LLM call in the application goes through ``LLMService``. No module imports
the ``openai`` SDK directly. The provider is chosen entirely by configuration
(env vars, optionally overridden per organization), so switching between OpenAI,
Anthropic, DeepSeek, Ollama, etc. requires no code change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import litellm
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.core.exceptions import LLMError
from src.core.logging import get_logger

logger = get_logger(__name__)

# litellm raises provider-specific errors; these are the transient ones worth retrying.
_RETRYABLE = (
    litellm.RateLimitError,
    litellm.APIConnectionError,
    litellm.Timeout,
    litellm.InternalServerError,
    litellm.ServiceUnavailableError,
)


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
    api_key = org_settings.get("llm_api_key") or settings.LLM_API_KEY or None
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
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
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
        """
        kwargs = self._base_kwargs(model)
        kwargs["messages"] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs["temperature"] = temperature
        kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = await self._acompletion(**kwargs)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize all provider errors
            logger.error("LLM completion failed: %s", exc, exc_info=True)
            raise LLMError(f"LLM request failed: {type(exc).__name__}") from exc
        content = response.choices[0].message.content
        return content or "", Usage.of(response)

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
        """
        kwargs = self._base_kwargs(model)
        kwargs["messages"] = messages
        kwargs["temperature"] = temperature
        kwargs["max_tokens"] = max_tokens
        kwargs["stream"] = True
        if usage_out is not None:
            kwargs["stream_options"] = {"include_usage": True}
            kwargs["drop_params"] = True
            usage_out.setdefault("reason", "provider reported no usage on the stream")
        try:
            response = await litellm.acompletion(**kwargs)
            async for chunk in response:
                if usage_out is not None and getattr(chunk, "usage", None) is not None:
                    usage = Usage.of(chunk)
                    usage_out["tokens_in"] = usage.tokens_in
                    usage_out["tokens_out"] = usage.tokens_out
                    usage_out["reason"] = usage.reason
                choices = getattr(chunk, "choices", None) or ()
                if not choices:
                    continue
                delta = choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    yield piece
        except Exception as exc:  # noqa: BLE001 - normalize all provider errors
            logger.error("LLM stream failed: %s", exc, exc_info=True)
            raise LLMError(f"LLM stream failed: {type(exc).__name__}") from exc
