"""Guards on the fixture LLM/embedding substitutes.

Every batch's graph tests run through these, so a silent regression here would look
like a bug in someone else's pipeline. No DB, no network.
"""

from pathlib import Path

import pytest

from src.core.exceptions import LLMError
from src.llm.client import LLMConfig, LLMService
from src.llm.embedding import EmbeddingConfig, EmbeddingService
from src.llm.fixtures import (
    FIXTURE_PREFIX,
    FixtureEmbeddingService,
    FixtureLLMService,
    maybe_fixture_embedder,
    maybe_fixture_llm,
    write_fixture,
)

SYSTEM = "You are a UI author."
USER = "Node: return policy."


def _llm(directory: Path) -> FixtureLLMService:
    config = LLMConfig(model="fixture/local", api_base=None, api_key=None)
    return FixtureLLMService(config, directory=directory)


def _embedder(dimensions: int = 384) -> FixtureEmbeddingService:
    return FixtureEmbeddingService(
        EmbeddingConfig(
            model="fixture/local", api_base=None, api_key=None, dimensions=dimensions
        )
    )


def test_write_then_complete_returns_the_recording_verbatim(tmp_path):
    payload = '{"format": "explanation"}'
    key = write_fixture(
        system_prompt=SYSTEM,
        user_prompt=USER,
        response=payload,
        relative_path="decide_formato/explanation.json",
        use_case="decide_formato",
        directory=tmp_path,
    )
    assert key == FixtureLLMService.key_for(SYSTEM, USER)
    assert len(key) == 16


async def test_complete_serves_the_fixture(tmp_path):
    write_fixture(
        system_prompt=SYSTEM,
        user_prompt=USER,
        response="raw dialect output",
        relative_path="genera_ui/openui_explanation.txt",
        directory=tmp_path,
    )
    result = await _llm(tmp_path).complete(SYSTEM, USER)
    assert result == "raw dialect output"


async def test_stream_reassembles_to_the_same_text(tmp_path):
    body = "x" * 100 + "\nend"
    write_fixture(
        system_prompt=SYSTEM,
        user_prompt=USER,
        response=body,
        relative_path="genera_ui/streamed.txt",
        directory=tmp_path,
    )
    service = _llm(tmp_path)
    chunks = [
        chunk
        async for chunk in service.stream(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER},
            ]
        )
    ]
    assert len(chunks) > 1, "streaming must emit deltas, not one blob"
    assert "".join(chunks) == body


async def test_stream_and_complete_share_one_key(tmp_path):
    """A 2-message chat list must hash to the same key ``complete`` uses."""
    write_fixture(
        system_prompt=SYSTEM,
        user_prompt=USER,
        response="same",
        relative_path="explain/term.json",
        directory=tmp_path,
    )
    service = _llm(tmp_path)
    streamed = "".join(
        [
            chunk
            async for chunk in service.stream(
                [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": USER},
                ]
            )
        ]
    )
    assert streamed == await service.complete(SYSTEM, USER)


async def test_missing_fixture_names_the_key_and_the_prompt(tmp_path):
    service = _llm(tmp_path)
    with pytest.raises(LLMError) as excinfo:
        await service.complete("unrecorded system", "unrecorded user")
    message = str(excinfo.value)
    assert FixtureLLMService.key_for("unrecorded system", "unrecorded user") in message
    assert "unrecorded user" in message


async def test_embeddings_are_deterministic_and_normalized():
    embedder = _embedder(dimensions=128)
    first = await embedder.embed_query("plazo de devolución")
    second = await embedder.embed_query("plazo de devolución")
    assert first == second
    assert len(first) == 128
    assert sum(value * value for value in first) == pytest.approx(1.0, abs=1e-6)
    other = await embedder.embed_query("otra cosa")
    assert other != first


async def test_embeddings_ignore_the_e5_prefix():
    """A query and its own ingested passage must land on the same vector, or the
    ``chunked`` branch of load_context could never retrieve anything."""
    embedder = _embedder()
    query = await embedder.embed_query("caja registradora")
    passage = (await embedder.embed_texts(["caja registradora"], prefix="passage: "))[0]
    assert query == passage


async def test_embed_texts_preserves_order():
    embedder = _embedder(dimensions=32)
    texts = ["uno", "dos", "tres"]
    vectors = await embedder.embed_texts(texts)
    assert len(vectors) == 3
    for text, vector in zip(texts, vectors, strict=True):
        assert vector == await embedder.embed_query(text)


def test_helpers_only_divert_fixture_models(monkeypatch):
    monkeypatch.setattr("src.llm.fixtures.settings.LLM_FIXTURE_MODE", "replay")
    real = maybe_fixture_llm(LLMConfig(model="gpt-4o-mini", api_base=None, api_key=None))
    assert type(real) is LLMService

    fake = maybe_fixture_llm(
        LLMConfig(model=f"{FIXTURE_PREFIX}local", api_base=None, api_key=None)
    )
    assert isinstance(fake, FixtureLLMService)

    real_embedder = maybe_fixture_embedder(
        EmbeddingConfig(
            model="multilingual-e5-small", api_base=None, api_key=None, dimensions=384
        )
    )
    assert type(real_embedder) is EmbeddingService
    fake_embedder = maybe_fixture_embedder(
        EmbeddingConfig(
            model=f"{FIXTURE_PREFIX}local", api_base=None, api_key=None, dimensions=384
        )
    )
    assert isinstance(fake_embedder, FixtureEmbeddingService)


def test_record_mode_wraps_the_real_service(monkeypatch):
    """With the fixture mode off (the default) v1 gets a plain LLMService."""
    from src.llm.fixtures import RecordingLLMService

    monkeypatch.setattr("src.llm.fixtures.settings.LLM_FIXTURE_MODE", "record")
    service = maybe_fixture_llm(
        LLMConfig(model="gpt-4o-mini", api_base=None, api_key=None)
    )
    assert isinstance(service, RecordingLLMService)
