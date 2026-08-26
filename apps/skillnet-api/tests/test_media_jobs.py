"""Unit tests for the media job-runner state machine (no DB/SSE/network).

Exercises :func:`execute_generation` and the generator registry — the parts that decide
the row's ``pending -> running -> done|error`` transitions — with fake generators and a
temp-dir asset store.
"""

import asyncio
from pathlib import Path

import pytest

from src.core.exceptions import LLMError
from src.models import MediaArtifactStatus, MediaKind
from src.services.media.assets import AssetStore
from src.services.media.grounding import GroundedBundle, GroundedPassage
from src.services.media.jobs import (
    ERROR_INTERNAL,
    ERROR_LLM_FAILED,
    ERROR_PROVIDER_QUOTA,
    EchoGenerator,
    GeneratedArtifact,
    MediaJobContext,
    execute_generation,
    get_generator,
    register_generator,
)


def _ctx(kind: MediaKind = MediaKind.REPORT) -> MediaJobContext:
    bundle = GroundedBundle(
        mode="chunks",
        passages=[GroundedPassage(citation_id="c1", text="t", source_title="Doc")],
    )
    return MediaJobContext(kind=kind, spec={"language": "es"}, bundle=bundle)


class _BytesGenerator:
    kind = MediaKind.INFOGRAPHIC

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
        return GeneratedArtifact(spec_json={"ok": True}, data=b"PNGDATA", ext="png")


class _BoomGenerator:
    kind = MediaKind.PODCAST

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
        raise RuntimeError("provider exploded")


class _CancelGenerator:
    kind = MediaKind.VIDEO

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
        raise asyncio.CancelledError()


@pytest.mark.asyncio
async def test_echo_generator_reaches_done_with_spec_and_no_asset(tmp_path: Path) -> None:
    result = await execute_generation(_ctx(), EchoGenerator(), AssetStore(tmp_path))

    assert result.status == MediaArtifactStatus.DONE
    assert result.asset_path is None
    assert result.content_hash is None
    assert result.spec_json["generator"] == "echo"
    assert result.spec_json["citations"] == [
        {
            "citation_id": "c1",
            "document": "Doc",
            "section": None,
            "page": None,
            "document_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_bytes_generator_stores_asset_and_records_hash(tmp_path: Path) -> None:
    store = AssetStore(tmp_path)

    result = await execute_generation(_ctx(), _BytesGenerator(), store)

    assert result.status == MediaArtifactStatus.DONE
    assert result.asset_path is not None
    assert result.content_hash is not None
    # The bytes actually landed in the store and round-trip.
    assert store.read(result.asset_path) == b"PNGDATA"
    assert Path(result.asset_path).suffix == ".png"


@pytest.mark.asyncio
async def test_generator_exception_transitions_to_error(tmp_path: Path) -> None:
    result = await execute_generation(_ctx(), _BoomGenerator(), AssetStore(tmp_path))

    assert result.status == MediaArtifactStatus.ERROR
    assert result.asset_path is None
    assert result.error_code == ERROR_INTERNAL
    assert result.error


@pytest.mark.asyncio
async def test_the_stored_failure_never_carries_the_exception_text(
    tmp_path: Path,
) -> None:
    """It used to be ``f"{type(exc).__name__}: {exc}"``, shown verbatim to the learner."""
    result = await execute_generation(_ctx(), _BoomGenerator(), AssetStore(tmp_path))

    assert "provider exploded" not in result.error
    assert "RuntimeError" not in result.error


@pytest.mark.asyncio
async def test_an_llm_failure_gets_its_own_code(tmp_path: Path) -> None:
    class _LLMDown:
        kind = MediaKind.SLIDES

        async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
            raise LLMError("LLM request failed: AuthenticationError")

    result = await execute_generation(_ctx(), _LLMDown(), AssetStore(tmp_path))

    assert result.error_code == ERROR_LLM_FAILED
    assert "AuthenticationError" not in result.error


@pytest.mark.asyncio
async def test_a_quota_failure_gets_its_own_code(tmp_path: Path) -> None:
    class _Quota(Exception):
        status_code = 429

    class _OutOfQuota:
        kind = MediaKind.SLIDES

        async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
            raise _Quota("rate limited")

    result = await execute_generation(_ctx(), _OutOfQuota(), AssetStore(tmp_path))

    assert result.error_code == ERROR_PROVIDER_QUOTA


@pytest.mark.asyncio
async def test_cancellation_propagates_not_swallowed(tmp_path: Path) -> None:
    with pytest.raises(asyncio.CancelledError):
        await execute_generation(_ctx(), _CancelGenerator(), AssetStore(tmp_path))


class _CoverGenerator:
    # A kind with no real generator, so registering here does not clobber a shipped one
    # (podcast/slides/infographic all self-register on import).
    kind = MediaKind.COVER_IMAGE

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
        return GeneratedArtifact(spec_json={"ok": True}, data=b"PNGDATA", ext="png")


def test_registry_overrides_default_echo_for_a_kind() -> None:
    # A kind that nothing registers a generator for resolves to the echo default.
    assert isinstance(get_generator(MediaKind.MINDMAP), EchoGenerator)

    gen = _CoverGenerator()
    register_generator(gen)

    assert get_generator(MediaKind.COVER_IMAGE) is gen
    # A kind still without a real generator keeps the echo default.
    assert isinstance(get_generator(MediaKind.MINDMAP), EchoGenerator)


def test_register_generator_rejects_missing_kind() -> None:
    with pytest.raises(ValueError):
        register_generator(EchoGenerator())
