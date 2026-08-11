"""Standalone smoke test for the Video Overview pipeline (roadmap §2b).

Narrated slides, NOT a real video model: generates a small deck from a hardcoded
mini-bundle, writes one narration line per slide, and synthesizes each slide's mp3 clip
through the podcast TTS path — reporting the slide count, per-slide narration + audio byte
lengths, citation coverage, and which TTS path was used. Run it directly:

    uv run python scripts/smoke_video.py

It makes REAL calls: two small ``gpt-4o-mini`` calls (deck + narration) and one ElevenLabs
synthesis per slide. It is kept deliberately tiny — the deck is truncated to ``_MAX_SLIDES``
before narration/voice — to limit quota. The keys live in the repo-root ``.env``
(``LLM_API_KEY``, ``TTS_API_KEY``), which is not the directory pydantic-settings reads when
running out of ``apps/skillnet-api``, so — like ``smoke_podcast.py`` — this script hunts
them down and injects them into ``settings`` before importing anything that touches a model.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# apps/skillnet-api/scripts/smoke_video.py -> repo root is parents[3].
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"

_WANTED = (
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "TTS_PROVIDER",
    "TTS_API_KEY",
    "TTS_VOICE",
    "SLIDES_MODEL",
    "VIDEO_NARRATION_MODEL",
    "PODCAST_VOICE_A",
)

#: Cap the slides actually narrated + voiced, so a chatty deck cannot burn quota.
_MAX_SLIDES = 2


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
    from src.services.media.slides.spec import generate_deck
    from src.services.media.video.narration import generate_narration
    from src.services.media.video.voice import synthesize_narration

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

    print(f"SMOKE: deck agent with {settings.SLIDES_MODEL} ...")
    try:
        deck = await generate_deck(
            bundle,
            language="es",
            theme="default",
            steering="Deck muy corto, 2 diapositivas.",
        )
    except Exception as exc:  # noqa: BLE001 - report, do not raise
        print(f"SMOKE: DECK FAILED — {type(exc).__name__}: {exc}")
        return 1

    if len(deck.slides) > _MAX_SLIDES:
        deck.slides = deck.slides[:_MAX_SLIDES]
    print(f"SMOKE: deck OK — {len(deck.slides)} slide(s) (capped at {_MAX_SLIDES})")

    print(f"SMOKE: narration agent with {settings.VIDEO_NARRATION_MODEL} ...")
    try:
        narration = await generate_narration(deck, bundle, language="es")
    except Exception as exc:  # noqa: BLE001 - report, do not raise
        print(f"SMOKE: NARRATION FAILED — {type(exc).__name__}: {exc}")
        return 1

    print(f"SMOKE: synthesizing {len(narration.lines)} clip(s) "
          f"via TTS_PROVIDER={settings.TTS_PROVIDER} ...")
    store = AssetStore()
    used_ids: set[str] = set()
    voice_paths: list[str] = []
    for i, (slide, line) in enumerate(zip(deck.slides, narration.lines), start=1):
        try:
            result = await synthesize_narration(line.text, language="es")
        except Exception as exc:  # noqa: BLE001 - report, do not raise
            print(f"SMOKE: SYNTHESIS FAILED (slide {i}) — {type(exc).__name__}: {exc}")
            return 1
        stored = store.store(result.data, result.ext)
        voice_paths.append(result.voice_path)
        used_ids.update(line.citation_ids)
        preview = line.text[:70].replace("\n", " ")
        print(
            f"        [{i}] {slide.title!r} narration={preview!r} "
            f"cites={line.citation_ids} audio={len(result.data)} bytes "
            f"path={result.voice_path!r} ref={stored.content_hash[:12]}..."
        )

    coverage = f"{len(used_ids)}/{len(bundle.citation_ids())}"
    print(
        f"SMOKE: OK — {len(deck.slides)} slide(s), voice_paths={voice_paths}, "
        f"citation coverage {coverage} (ids: {sorted(used_ids) or '(none)'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
