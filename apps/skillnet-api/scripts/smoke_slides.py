"""Standalone smoke test for the Slide Deck content agent (roadmap §2c).

Generates a small deck from a hardcoded mini-bundle, validates the JSON spec, and reports
the slide count, the kit-block types used per slide, and citation coverage (which of the
bundle's citation ids the deck actually leaned on). Run it directly:

    uv run python scripts/smoke_slides.py

It makes ONE real, small ``gpt-4o-mini`` call (no image generation — the deck is spec-only
by default). The key lives in the repo-root ``.env`` (``LLM_API_KEY``), which is not the
directory pydantic-settings reads when running out of ``apps/skillnet-api``, so — like
``smoke_podcast.py`` — this script hunts it down and injects it into ``settings`` before
importing anything that touches a model.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# apps/skillnet-api/scripts/smoke_slides.py -> repo root is parents[3].
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"

_WANTED = ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "SLIDES_MODEL")


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

    from src.config import settings
    from src.services.media.grounding import GroundedBundle, GroundedPassage
    from src.services.media.slides.spec import generate_deck

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
        deck = await generate_deck(bundle, language="es", theme="default")
    except Exception as exc:  # noqa: BLE001 - report, do not raise
        print(f"SMOKE: DECK FAILED — {type(exc).__name__}: {exc}")
        return 1

    used_ids = sorted({cid for s in deck.slides for cid in s.citation_ids})
    coverage = f"{len(used_ids)}/{len(bundle.citation_ids())}"
    print(
        f"SMOKE: OK — {len(deck.slides)} slide(s), theme={deck.theme!r}, "
        f"citation coverage {coverage} (ids: {used_ids or '(none)'})"
    )
    for i, slide in enumerate(deck.slides, start=1):
        block_types = [b.type for b in slide.blocks]
        title = slide.title[:50].replace("\n", " ")
        print(f"        [{i}] {title!r} blocks={block_types} cites={slide.citation_ids}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
