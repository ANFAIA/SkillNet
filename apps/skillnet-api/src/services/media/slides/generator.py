"""The :class:`SlidesGenerator` — the slide deck's plug into the media spine (roadmap §2c).

It implements the spine's ``MediaGenerator`` protocol and wires two stages:

    grounded bundle --deck agent----> validated deck (kit blocks per slide)
                    --image model----> one NotebookLM-style illustration per slide (PNG)

The deck stage keeps the whole deck as structured JSON in ``spec_json`` (``slides`` with
their ``citation_ids``, kit-block specs, and the bundle's citation metadata), so the
frontend can render the parallel citations panel and fall back to the kit blocks. The image
stage then renders one **landscape illustration per slide** (the approved gallery look),
stores each via the :class:`AssetStore`, and writes its content-hash ``image_ref`` (+
``image_ext``) into that slide's ``spec_json`` entry — the same content-addressed pattern
the Video Overview uses for its per-slide audio. Each image is served by the per-slide
sub-asset route (``/artifacts/{id}/asset/{ref}``).

Image generation is best-effort per slide: a slide whose illustration fails simply carries
no ``image_ref`` and the frontend falls back to its kit blocks. The legacy decorative
``cover`` backdrop (top-level asset) is still supported when ``spec['cover']`` is set.

SSE progress: ``guion`` (writing the deck), then one ``ilustracion`` per slide (with its
index), then ``listo`` (done, with the slide count).
"""

from __future__ import annotations

from src.core.logging import get_logger
from src.models import MediaKind
from src.services.media.assets import AssetStore
from src.services.media.images import generate_image
from src.services.media.jobs import (
    GeneratedArtifact,
    MediaJobContext,
    register_generator,
)
from src.services.media.slides import spec as spec_mod
from src.services.media.visuals import slide_prompt

logger = get_logger(__name__)

#: Square-ish cover for a deck thumbnail; only used when a decorative cover is requested.
_COVER_SIZE = "1024x1024"
#: Landscape 16:9 for the per-slide illustrations (the approved gallery look).
_SLIDE_SIZE = "1536x1024"


class SlidesGenerator:
    """Generate a grounded, per-slide-structured slide deck for a course/node."""

    kind = MediaKind.SLIDES

    def __init__(self, asset_store: AssetStore | None = None) -> None:
        # Injectable for tests (a tmp-dir store); ``None`` -> the app's media assets dir at
        # generate time, so registration stays a zero-arg construction.
        self._asset_store = asset_store

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

        # Image stage: one NotebookLM-style landscape illustration per slide, stored and
        # referenced from spec_json by content hash (image_ref), best-effort per slide.
        store = self._asset_store or AssetStore()
        slides_out: list[dict] = []
        images = 0
        for i, slide in enumerate(deck.slides):
            await ctx.emit("ilustracion", slide=i + 1, total=len(deck.slides))
            slide_dict = slide.model_dump()
            stored = await self._render_slide(slide, store)
            if stored is not None:
                slide_dict["image_ref"] = stored[0]
                slide_dict["image_ext"] = stored[1]
                images += 1
            slides_out.append(slide_dict)

        # Optional decorative cover backdrop only — never text/facts baked into an image.
        cover_data: bytes | None = None
        cover_ext: str | None = None
        if spec.get("cover"):
            cover_data, cover_ext = await self._maybe_cover(deck, ctx)

        await ctx.emit("listo", slides=len(deck.slides))
        logger.info(
            "Slide deck generated: slides=%d images=%d theme=%s grounding=%s cover=%s",
            len(deck.slides),
            images,
            deck.theme,
            ctx.bundle.mode,
            cover_data is not None,
        )

        spec_json = {
            "generator": "slides",
            "theme": deck.theme,
            "language": deck.language,
            "grounding_mode": ctx.bundle.mode,
            # The deck with per-slide kit-block specs, citation_ids and (when available) the
            # illustration's image_ref — what the viewer and the parallel panel read.
            "slides": slides_out,
            # The citation metadata (document/section/page) each id resolves to.
            "citations": ctx.bundle.citations_payload(),
            "has_cover": cover_data is not None,
        }
        return GeneratedArtifact(spec_json=spec_json, data=cover_data, ext=cover_ext)

    async def _render_slide(
        self, slide: spec_mod.Slide, store: AssetStore
    ) -> tuple[str, str] | None:
        """Best-effort per-slide illustration. Returns ``(image_ref, image_ext)`` or ``None``."""
        prompt = slide_prompt(slide)
        try:
            data = await generate_image(prompt, size=_SLIDE_SIZE)
        except Exception as exc:  # noqa: BLE001 - per-slide visual is best-effort, not fatal
            logger.warning("Slide illustration generation failed, skipping: %s", exc)
            return None
        stored = store.store(data, "png")
        return stored.content_hash, stored.ext

    async def _maybe_cover(
        self, deck: spec_mod.SlideDeck, ctx: MediaJobContext
    ) -> tuple[bytes | None, str | None]:
        """Best-effort decorative cover. Never fatal: a failed image leaves a spec-only deck."""
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
