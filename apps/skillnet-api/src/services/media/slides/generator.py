"""The :class:`SlidesGenerator` — the slide deck's plug into the media spine (roadmap §2c).

It implements the spine's ``MediaGenerator`` protocol and wires the single content stage:

    grounded bundle --deck agent--> validated deck (kit blocks per slide)

and returns a :class:`GeneratedArtifact` whose ``spec_json`` carries the whole deck
(``slides`` with their ``citation_ids`` and kit-block specs) plus the bundle's citation
metadata, so the frontend can render each slide with the existing kit components and the
parallel citations panel.

A deck is a **spec-only** artifact by default: the slides are structured JSON rendered by
us, never a baked image (the §2d/§3 trap). An optional decorative cover thumbnail can be
generated via the image model, but only for the cover backdrop and never carrying facts;
it is off unless ``spec['cover']`` is set and degrades to spec-only if generation fails.

Two SSE progress steps are emitted through the context's reporter — ``guion`` (writing the
deck) and ``listo`` (done, with the slide count) — so the UI can show real stages.
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

#: Square-ish cover for a deck thumbnail; only used when a decorative cover is requested.
_COVER_SIZE = "1024x1024"


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
            language=language,
            theme=theme,
            steering=steering if isinstance(steering, str) else None,
        )

        # Optional decorative cover backdrop only — never text/facts baked into an image.
        cover_data: bytes | None = None
        cover_ext: str | None = None
        if spec.get("cover"):
            cover_data, cover_ext = await self._maybe_cover(deck, ctx)

        await ctx.emit("listo", slides=len(deck.slides))
        logger.info(
            "Slide deck generated: slides=%d theme=%s grounding=%s cover=%s",
            len(deck.slides),
            deck.theme,
            ctx.bundle.mode,
            cover_data is not None,
        )

        spec_json = {
            "generator": "slides",
            "theme": deck.theme,
            "language": deck.language,
            "grounding_mode": ctx.bundle.mode,
            # The deck with per-slide kit-block specs and citation_ids — what the viewer
            # and the parallel panel read.
            "slides": [slide.model_dump() for slide in deck.slides],
            # The citation metadata (document/section/page) each id resolves to.
            "citations": ctx.bundle.citations_payload(),
            "has_cover": cover_data is not None,
        }
        return GeneratedArtifact(spec_json=spec_json, data=cover_data, ext=cover_ext)

    async def _maybe_cover(
        self, deck: spec_mod.SlideDeck, ctx: MediaJobContext
    ) -> tuple[bytes | None, str | None]:
        """Best-effort decorative cover. Never fatal: a failed image leaves a spec-only deck."""
        from src.services.media.images import generate_image

        title = deck.slides[0].title if deck.slides else "Curso"
        prompt = (
            "Fondo decorativo abstracto para la portada de una presentacion educativa "
            f"sobre '{title}'. Estilo limpio y profesional, SIN texto ni numeros, solo "
            "formas y color."
        )
        try:
            await ctx.emit("portada")
            data = await generate_image(prompt, size=_COVER_SIZE)
            return data, "png"
        except Exception as exc:  # noqa: BLE001 - decorative; a failed cover is not a failed deck
            logger.warning("Slide deck cover generation failed, continuing spec-only: %s", exc)
            return None, None


def register() -> None:
    """Register the slides generator under ``MediaKind.SLIDES`` (idempotent)."""
    register_generator(SlidesGenerator())


__all__ = ["SlidesGenerator", "register"]
