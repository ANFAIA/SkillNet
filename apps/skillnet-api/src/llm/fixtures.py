"""Recorded-fixture substitutes for ``LLMService`` and ``EmbeddingService``.

There are no API keys in this environment, so the whole pipeline has to be
runnable without the network. The answer is not "mock in every test" but a real
alternative implementation selected by configuration: any resolved model whose id
starts with ``fixture/`` is served from disk instead of from a provider.

Both classes subclass their real counterpart and honour the same async surface
(``complete``, ``stream``, ``embed_texts``, ``embed_query``, the ``model`` /
``dimensions`` properties) and the same error type (``LLMError``), so they are
drop-in substitutes rather than look-alikes.

Fixtures live **inside the package** (``src/llm/fixture_data/``), not under
``tests/``: ``docker/api.Dockerfile`` copies only ``.venv``, ``src``, ``alembic``,
``alembic.ini`` and ``pyproject.toml``, so a ``tests/`` path would make the
``fixtures`` compose profile impossible.
"""

from __future__ import annotations

import json
import random
from collections.abc import AsyncIterator
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.config import settings
from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.llm.client import LLMConfig, LLMService
from src.llm.embedding import EmbeddingConfig, EmbeddingService

logger = get_logger(__name__)

FIXTURE_PREFIX = "fixture/"
INDEX_FILENAME = "index.json"

# How many characters of the prompt go into the "missing fixture" message and into
# the index, so a human can tell which recording is absent.
_PREVIEW_CHARS = 160


def fixture_dir() -> Path:
    """Directory fixtures are read from and recorded into."""
    return Path(settings.LLM_FIXTURE_DIR)


def _fixture_key(system_prompt: str, user_prompt: str) -> str:
    return sha256(f"{system_prompt}\x00{user_prompt}".encode()).hexdigest()[:16]


def _preview(system_prompt: str, user_prompt: str) -> str:
    joined = f"{system_prompt} || {user_prompt}".replace("\n", " ")
    return joined[:_PREVIEW_CHARS]


def load_index(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Read ``index.json``. Returns ``{}`` when it does not exist yet."""
    path = (directory or fixture_dir()) / INDEX_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise LLMError(f"Fixture index at {path} is unreadable: {exc}") from exc
    return raw if isinstance(raw, dict) else {}


def write_fixture(
    *,
    system_prompt: str,
    user_prompt: str,
    response: str,
    relative_path: str,
    use_case: str = "",
    directory: Path | None = None,
) -> str:
    """Record one (prompt, response) pair and register it in ``index.json``.

    Returns the 16-hex key. Used both by ``LLM_FIXTURE_MODE=record`` and by tests
    that need to seed a fixture for a prompt they build themselves.
    """
    base = directory or fixture_dir()
    key = _fixture_key(system_prompt, user_prompt)
    target = base / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(response, encoding="utf-8")

    index = load_index(base)
    index[key] = {
        "file": relative_path,
        "prompt_preview": _preview(system_prompt, user_prompt),
        "use_case": use_case,
    }
    (base / INDEX_FILENAME).write_text(
        json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return key


class FixtureLLMService(LLMService):
    """Serves recorded responses. Activated when the resolved model starts with
    ``fixture/``. Never makes a network call."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        directory: Path | None = None,
    ) -> None:
        super().__init__(config)
        self._dir = directory or fixture_dir()

    @classmethod
    def key_for(cls, system_prompt: str, user_prompt: str) -> str:
        """Public form of the key, so tests can register a fixture for a prompt."""
        return _fixture_key(system_prompt, user_prompt)

    def _key(self, system_prompt: str, user_prompt: str) -> str:
        return _fixture_key(system_prompt, user_prompt)

    @staticmethod
    def _split_messages(messages: list[dict[str, str]]) -> tuple[str, str]:
        """Fold a chat message list into the same (system, user) pair ``complete``
        hashes, so a 2-message list yields the identical key."""
        system_parts = [
            m.get("content") or "" for m in messages if m.get("role") == "system"
        ]
        other_parts = [
            m.get("content") or "" for m in messages if m.get("role") != "system"
        ]
        return "\n".join(system_parts), "\n".join(other_parts)

    def _resolve(self, system_prompt: str, user_prompt: str) -> str:
        key = self._key(system_prompt, user_prompt)
        entry = load_index(self._dir).get(key)
        if entry is None:
            # Explicit and actionable, never an opaque KeyError.
            raise LLMError(
                f"No LLM fixture for key {key}. "
                f"Prompt preview: {_preview(system_prompt, user_prompt)!r}. "
                f"Record it with LLM_FIXTURE_MODE=record, or add it under "
                f"{self._dir} and register {key} in {INDEX_FILENAME}."
            )
        relative = entry.get("file") if isinstance(entry, dict) else entry
        if not relative:
            raise LLMError(f"Fixture index entry for {key} has no 'file' field.")
        path = self._dir / str(relative)
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LLMError(f"Fixture file {path} for key {key} is unreadable: {exc}") from exc

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
        """Return the recorded response verbatim.

        The fixture file holds exactly what the model would have emitted, so a
        ``.json`` fixture is valid under ``json_mode`` without any post-processing.
        """
        return self._resolve(system_prompt, user_prompt)

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Replay the recorded response as deltas, so streaming consumers (SSE,
        incremental parsing) exercise their real chunk-handling path."""
        system_prompt, user_prompt = self._split_messages(messages)
        text = self._resolve(system_prompt, user_prompt)
        step = 24
        for start in range(0, len(text), step):
            yield text[start : start + step]


class RecordingLLMService(LLMService):
    """Real provider calls that also write each (prompt, response) pair to disk.

    Selected by ``LLM_FIXTURE_MODE=record``. It exists as a subclass so that
    ``src/llm/client.py`` stays byte-for-byte untouched: with the fixture mode off
    (the default) nothing in the v1 path changes.
    """

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
        response = await super().complete(
            system_prompt,
            user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        key = _fixture_key(system_prompt, user_prompt)
        suffix = "json" if json_mode else "txt"
        try:
            write_fixture(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response=response,
                relative_path=f"recorded/{key}.{suffix}",
            )
        except (OSError, LLMError) as exc:  # recording must never break the call
            logger.warning("Could not record LLM fixture %s: %s", key, exc)
        return response


class FixtureEmbeddingService(EmbeddingService):
    """Deterministic per-text vectors, dimension = ``config.dimensions``.

    No network call. The vectors are **not** semantic: they let the pipeline run and
    support shape assertions, not relevance measurement — judging retrieval quality
    needs real keys and an ``@pytest.mark.integration`` test.

    The e5 ``query:``/``passage:`` prefix is deliberately ignored: hashing it would
    give a query and its own ingested passage two unrelated vectors, so the
    ``chunked`` branch of ``load_context`` could never retrieve anything and the
    wiring it is meant to exercise would go untested.
    """

    def _vector(self, text: str) -> list[float]:
        seed = int.from_bytes(sha256(text.encode()).digest()[:8], "big")
        rng = random.Random(seed)
        raw = [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
        norm = sum(value * value for value in raw) ** 0.5
        if norm == 0:  # pragma: no cover - only for a degenerate all-zero draw
            return raw
        return [value / norm for value in raw]

    async def embed_texts(
        self, texts: list[str], *, prefix: str = ""
    ) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def maybe_fixture_llm(config: LLMConfig) -> LLMService:
    """The one branch point for LLM construction. All 8 build sites call this."""
    if config.model.startswith(FIXTURE_PREFIX):
        return FixtureLLMService(config)
    if settings.LLM_FIXTURE_MODE == "record":
        return RecordingLLMService(config)
    return LLMService(config)


def maybe_fixture_embedder(config: EmbeddingConfig) -> EmbeddingService:
    """The one branch point for embedding construction."""
    if config.model.startswith(FIXTURE_PREFIX):
        return FixtureEmbeddingService(config)
    return EmbeddingService(config)
