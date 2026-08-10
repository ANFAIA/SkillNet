"""Standalone smoke test for the image-generation utility and the OpenRouter key.

Generates one small image through ``src.services.media.images.generate_image`` and reports
success/failure plus the byte length; on success it stores the result in the asset store as
a demo. Run it directly:

    uv run python scripts/smoke_image.py

The OpenRouter key lives in the repo-root ``.env`` (``OPENROUTER_API_KEY``), which is not
the directory pydantic-settings reads from when the API runs out of ``apps/skillnet-api``.
So this script hunts the key down explicitly: environment first, then the repo-root
``.env``, and injects it into ``settings`` and ``os.environ`` before importing anything that
touches the model.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def _load_openrouter_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    # apps/skillnet-api/scripts/smoke_image.py -> repo root is parents[3].
    root_env = Path(__file__).resolve().parents[3] / ".env"
    if root_env.exists():
        for line in root_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


async def _run() -> int:
    key = _load_openrouter_key()
    if not key:
        print("SMOKE: no OPENROUTER_API_KEY found (env or repo-root .env)")
        return 2
    os.environ["OPENROUTER_API_KEY"] = key

    from src.config import settings
    from src.services.media.assets import AssetStore
    from src.services.media.images import generate_image

    settings.OPENROUTER_API_KEY = key

    prompt = (
        "A clean, minimal flat-illustration icon of a croissant on a plain background, "
        "soft pastel colors, no text."
    )
    print(f"SMOKE: generating one image with {settings.IMAGE_MODEL} ...")
    try:
        data = await generate_image(prompt, size="512x512", fallback=False)
    except Exception as exc:  # noqa: BLE001 - the whole point is to report the error
        print(f"SMOKE: FAILED — {type(exc).__name__}: {exc}")
        return 1

    stored = AssetStore().store(data, "png")
    print(
        f"SMOKE: OK — {len(data)} bytes, hash {stored.content_hash[:12]}..., "
        f"saved to {stored.path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
