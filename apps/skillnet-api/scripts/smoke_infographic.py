"""Standalone smoke test for the Infographic content agent (roadmap §2d).

Generates a single infographic sheet from a hardcoded mini-bundle, validates the JSON spec,
and reports the section count, which sections carry a stat, and citation coverage. The
sheet is spec-only (facts as data, never baked into an image), so this makes ONE small real
``gpt-4o-mini`` call and no image call. Run it directly:

    uv run python scripts/smoke_infographic.py

Like the other smoke scripts, it hunts the ``LLM_API_KEY`` from the repo-root ``.env`` and
injects it into ``settings`` before importing anything that touches a model.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# apps/skillnet-api/scripts/smoke_infographic.py -> repo root is parents[3].
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"

_WANTED = ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "INFOGRAPHIC_MODEL")


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
    from src.services.media.infographic.spec import generate_infographic

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

    print(f"SMOKE: infographic agent with {settings.INFOGRAPHIC_MODEL} ...")
    try:
        info = await generate_infographic(bundle, language="es", style="default")
    except Exception as exc:  # noqa: BLE001 - report, do not raise
        print(f"SMOKE: INFOGRAPHIC FAILED — {type(exc).__name__}: {exc}")
        return 1

    used_ids = sorted({cid for s in info.sections for cid in s.citation_ids})
    with_stat = sum(1 for s in info.sections if s.stat)
    coverage = f"{len(used_ids)}/{len(bundle.citation_ids())}"
    print(
        f"SMOKE: OK — title={info.title!r}, {len(info.sections)} section(s), "
        f"{with_stat} with a stat, orientation={info.orientation}, "
        f"citation coverage {coverage} (ids: {used_ids or '(none)'})"
    )
    for i, section in enumerate(info.sections, start=1):
        stat = f" [{section.stat}]" if section.stat else ""
        line = section.one_line[:50].replace("\n", " ")
        print(f"        [{i}] {section.heading!r}{stat}: {line}...  cites={section.citation_ids}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
