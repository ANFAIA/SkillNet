"""Provider-agnostic embeddings via litellm.

Used by document ingestion (batch) and chat retrieval (single query). The model
and endpoint fall back to the LLM provider when no dedicated embedding provider
is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import litellm
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.core.secrets import unseal

logger = get_logger(__name__)

_BATCH_SIZE = 32


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    api_base: str | None
    api_key: str | None
    dimensions: int


def resolve_embedding_config(org_settings: dict[str, Any] | None = None) -> EmbeddingConfig:
    """Resolve embedding config; embeddings fall back to the LLM provider."""
    org_settings = org_settings or {}
    model = (
        org_settings.get("embedding_model")
        or settings.EMBEDDING_MODEL
        or org_settings.get("llm_model")
        or settings.LLM_MODEL
    )
    api_base = (
        org_settings.get("embedding_base_url")
        or settings.EMBEDDING_BASE_URL
        or org_settings.get("llm_base_url")
        or settings.LLM_BASE_URL
        or None
    )
    # Both org-stored keys go through `unseal`: they are encrypted at rest
    # (src/core/secrets.py), and it is a no-op on the environment defaults.
    api_key = (
        unseal(org_settings.get("embedding_api_key"))
        or settings.EMBEDDING_API_KEY
        or unseal(org_settings.get("llm_api_key"))
        or settings.LLM_API_KEY
        or None
    )
    return EmbeddingConfig(
        model=model,
        api_base=api_base,
        api_key=api_key,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )


class EmbeddingService:
    """Async embedding client. Returns plain ``list[float]`` vectors."""

    def __init__(self, config: EmbeddingConfig) -> None:
        if not config.model:
            raise LLMError("No embedding model configured.")
        self._config = config
        self._is_e5 = "e5" in config.model.lower()

    @property
    def dimensions(self) -> int:
        return self._config.dimensions

    @property
    def _accepts_dimensions(self) -> bool:
        """Whether the provider lets us ask for a specific output size.

        Only OpenAI's ``text-embedding-3-*`` family, deliberately narrow: sending
        ``dimensions`` to a provider that does not know the parameter is an error, not an
        ignored hint, so an allowlist is the safe direction to be wrong in.

        This is what makes "one OpenAI key and it works" true. ``text-embedding-3-small``
        returns 1536 components by default, the column is ``vector(768)``, and without
        asking for 768 every chunk insert fails — the API truncates for us (Matryoshka
        embeddings, so a truncated vector is still a usable one, not a broken one).
        """
        return "text-embedding-3" in self._config.model

    def _kwargs(self, texts: list[str]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": self._config.model, "input": texts}
        if self._config.api_base:
            kwargs["api_base"] = self._config.api_base
        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key
        if self._accepts_dimensions:
            kwargs["dimensions"] = self._config.dimensions
        return kwargs

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30), reraise=True)
    async def _aembedding(self, texts: list[str]) -> Any:
        return await litellm.aembedding(**self._kwargs(texts))

    async def embed_texts(self, texts: list[str], *, prefix: str = "") -> list[list[float]]:
        """Embed many texts (batched). Preserves input order."""
        if not texts:
            return []
        if self._is_e5 and prefix:
            texts = [f"{prefix}{t}" for t in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            try:
                response = await self._aembedding(batch)
            except Exception as exc:  # noqa: BLE001 - normalize provider errors
                logger.error("Embedding failed: %s", exc, exc_info=True)
                raise LLMError(f"Embedding request failed: {type(exc).__name__}") from exc
            vectors.extend(item["embedding"] for item in response.data)
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        result = await self.embed_texts([text], prefix="query: ")
        return result[0]
