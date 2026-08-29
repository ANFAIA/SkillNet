"""The :class:`SlidesGenerator` — the slide deck's plug into the media spine (roadmap §2c).

It implements the spine's ``MediaGenerator`` protocol and wires two stages:

    grounded bundle --deck agent----> validated deck (kit blocks per slide)

The deck stage keeps the whole deck as structured JSON in ``spec_json`` (``slides`` with
their ``citation_ids``, kit-block specs, and the bundle's citation metadata), so the
frontend can render the parallel citations panel. Presentations deliberately use only the
shared component kit: no generated illustrations or decorative cover images.

SSE progress: ``guion`` (writing the deck), then ``listo`` (done, with the slide count).
"""

from __future__ import annotations

from src.core.logging import get_logger
from src.models import MediaKind
from src.services.media.jobs import (
    GeneratedArtifact,
    MediaJobContext,
    register_generator,
)
from src.services.media.slides import spec as spec_mod

logger = get_logger(__name__)


class SlidesGenerator:
    """Generate a grounded, per-slide-structured slide deck for a course/node."""

    kind = MediaKind.SLIDES

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
        spec = ctx.spec or {}
        language = str(spec.get("language") or "es")
        theme = str(spec.get("theme") or "default")
        steering = spec.get("prompt") or spec.get("steering")

        await ctx.emit("guion", theme=theme)
        deck = await spec_mod.generate_deck(
            ctx.bundle,
            subject=ctx.subject(),
            language=language,
            theme=theme,
            steering=steering if isinstance(steering, str) else None,
        )

        slides_out = [slide.model_dump() for slide in deck.slides]

        await ctx.emit("listo", slides=len(deck.slides))
        logger.info(
            "Slide deck generated: slides=%d theme=%s grounding=%s",
            len(deck.slides),
            deck.theme,
            ctx.bundle.mode,
        )

        spec_json = {
            "generator": "slides",
            "theme": deck.theme,
            "language": deck.language,
            "grounding_mode": ctx.bundle.mode,
            # The deck with per-slide kit-block specs and citation_ids.
            "slides": slides_out,
            # The citation metadata (document/section/page) each id resolves to.
            "citations": ctx.bundle.citations_payload(),
            "has_cover": False,
        }
        return GeneratedArtifact(spec_json=spec_json)


def register() -> None:
    """Register the slides generator under ``MediaKind.SLIDES`` (idempotent)."""
    register_generator(SlidesGenerator())


__all__ = ["SlidesGenerator", "register"]
