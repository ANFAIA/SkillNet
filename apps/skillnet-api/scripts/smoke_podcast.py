"""Standalone smoke test for the Audio Overview / Podcast pipeline (roadmap §2a).

Generates a tiny dialogue from a hardcoded mini-bundle and synthesizes it end to end,
reporting which voice path was used (ElevenLabs Text-to-Dialogue vs the per-turn TTS +
ffmpeg fallback), the mp3 byte length, and the stored asset path. Run it directly:

    uv run python scripts/smoke_podcast.py

It makes REAL calls: one small ``gpt-4o-mini`` script call and one ElevenLabs synthesis. It
is kept deliberately tiny (short target, turns capped) to limit quota. The keys live in the
repo-root ``.env`` (``LLM_API_KEY``, ``TTS_API_KEY``), which is not the directory
pydantic-settings reads when running out of ``apps/skillnet-api``, so — like
``smoke_image.py`` — this script hunts them down and injects them into ``settings`` before
importing anything that touches a model.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# apps/skillnet-api/scripts/smoke_podcast.py -> repo root is parents[3].
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"

# Keys/config we want from the environment or the repo-root .env, in that order.
_WANTED = (
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "TTS_PROVIDER",
    "TTS_API_KEY",
    "TTS_VOICE",
    "PODCAST_SCRIPT_MODEL",
    "PODCAST_VOICE_A",
    "PODCAST_VOICE_B",
)

#: Cap the number of turns actually voiced, so a chatty script cannot burn quota.
_MAX_TURNS = 4


def _load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    file_values: dict[str, str] = {}
    if _ROOT_ENV.exists():
        for raw in _ROOT_ENV.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            file_values[key.strip()] = val.strip().strip('"').strip("'")
    for key in _WANTED:
        val = os.environ.get(key) or file_values.get(key)
        if val:
            values[key] = val
            os.environ[key] = val
    return values


async def _run() -> int:
    loaded = _load_env()
    if not loaded.get("LLM_API_KEY"):
        print("SMOKE: no LLM_API_KEY found (env or repo-root .env)")
        return 2
    if not loaded.get("TTS_API_KEY"):
        print("SMOKE: no TTS_API_KEY found (env or repo-root .env)")
        return 2

    from src.config import settings
    from src.services.media.assets import AssetStore
    from src.services.media.grounding import GroundedBundle, GroundedPassage
    from src.services.media.podcast.script import PodcastFormat, generate_script
    from src.services.media.podcast.voices import synthesize_podcast

    # Push the loaded values onto the already-instantiated settings object.
    for key, val in loaded.items():
        if hasattr(settings, key):
            setattr(settings, key, val)

    bundle = GroundedBundle(
        mode="chunks",
        passages=[
            GroundedPassage(
                citation_id="c1",
                text=(
                    "Las devoluciones se aceptan durante 30 dias naturales desde la compra, "
                    "con el producto en su estado original y el ticket."
                ),
                source_title="Manual de atencion al cliente",
                section="Devoluciones",
                page=12,
            ),
            GroundedPassage(
                citation_id="c2",
                text=(
                    "Si el producto llego defectuoso, la devolucion es gratuita y el plazo "
                    "se amplia a 60 dias."
                ),
                source_title="Manual de atencion al cliente",
                section="Productos defectuosos",
                page=13,
            ),
        ],
    )

    print(f"SMOKE: script agent with {settings.PODCAST_SCRIPT_MODEL} (The Brief, ~25s) ...")
    try:
        script = await generate_script(
            bundle, fmt=PodcastFormat.THE_BRIEF, language="es", target_seconds=25
        )
    except Exception as exc:  # noqa: BLE001 - report, do not raise
        print(f"SMOKE: SCRIPT FAILED — {type(exc).__name__}: {exc}")
        return 1

    if len(script.turns) > _MAX_TURNS:
        script.turns = script.turns[:_MAX_TURNS]
    total_ids = sorted({cid for t in script.turns for cid in t.citation_ids})
    print(
        f"SMOKE: script OK — {len(script.turns)} turn(s), "
        f"citation_ids used: {total_ids or '(none)'}"
    )
    for turn in script.turns:
        preview = turn.text[:70].replace("\n", " ")
        print(f"        [{turn.speaker}] {preview}...  cites={turn.citation_ids}")

    print(f"SMOKE: synthesizing via TTS_PROVIDER={settings.TTS_PROVIDER} ...")
    try:
        result = await synthesize_podcast(script)
    except Exception as exc:  # noqa: BLE001 - report, do not raise
        print(f"SMOKE: SYNTHESIS FAILED — {type(exc).__name__}: {exc}")
        return 1

    stored = AssetStore().store(result.data, result.ext)
    print(
        f"SMOKE: OK — voice_path={result.voice_path!r}, {len(result.data)} bytes, "
        f"hash {stored.content_hash[:12]}..., saved to {stored.path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
