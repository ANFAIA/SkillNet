"""The :class:`InfographicGenerator` — the infographic's plug into the media spine (§2d).

It implements the spine's ``MediaGenerator`` protocol and wires two stages:

    grounded bundle --content agent--> validated infographic (facts as data)
                    --image model-----> clean editorial portrait poster (PNG)

The content stage extracts the facts as data and keeps them in ``spec_json`` (title,
sections with stats and ``citation_ids``, plus the bundle's citation metadata) so the
frontend can still render the parallel citations panel. The image stage then renders those
same facts as one clean editorial **portrait poster** and hands
the PNG back as the artifact's single main asset, served at ``/artifacts/{id}/asset``.

Image generation is best-effort: if it fails the artifact degrades to spec-only
(``has_image=False``) rather than erroring the whole job, and the frontend falls back to the
structured sheet.

Three SSE progress steps are emitted through the context's reporter — ``datos`` (extracting
the facts), ``imagen`` (rendering the poster) and ``listo`` (done, with the section count).
"""

from __future__ import annotations

from src.core.logging import get_logger
from src.models import MediaKind
from src.services.media.images import generate_image
from src.services.media.infographic import spec as spec_mod
from src.services.media.jobs import (
    GeneratedArtifact,
    MediaJobContext,
    register_generator,
)
from src.services.media.visuals import infographic_prompt

logger = get_logger(__name__)

#: Portrait poster aspect ratio.
_IMAGE_SIZE = "1024x1536"


class InfographicGenerator:
    """Generate a grounded, single-sheet infographic (facts as data) for a course/node."""

    kind = MediaKind.INFOGRAPHIC

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
        spec = ctx.spec or {}
        language = str(spec.get("language") or "es")
        style = str(spec.get("style") or "default")
        orientation = str(spec.get("orientation") or "portrait")
        if orientation not in ("portrait", "landscape"):
            orientation = "portrait"
        steering = spec.get("prompt") or spec.get("steering") or spec.get("note")
        scope = str(spec.get("scope") or ("node" if ctx.node is not None else "course"))

        await ctx.emit("datos", style=style)
        infographic = await spec_mod.generate_infographic(
            ctx.bundle,
            language=language,
            style=style,
            orientation=orientation,
            steering=steering if isinstance(steering, str) else None,
        )

        # Image stage: render the same facts as one clean editorial portrait poster.
        await ctx.emit("imagen")
        image = await self._render_poster(infographic)

        await ctx.emit("listo", sections=len(infographic.sections))
        logger.info(
            "Infographic generated: sections=%d style=%s orientation=%s grounding=%s image=%s",
            len(infographic.sections),
            infographic.style,
            infographic.orientation,
            ctx.bundle.mode,
            image is not None,
        )

        spec_json = {
            "generator": "infographic",
            "scope": scope,
            "title": infographic.title,
            "subtitle": infographic.subtitle,
            "orientation": infographic.orientation,
            "layout": infographic.layout,
            "style": infographic.style,
            "language": infographic.language,
            "grounding_mode": ctx.bundle.mode,
            # The sections (facts as data) with per-section citation_ids — what the parallel
            # panel reads (and the sheet the frontend falls back to if the image is missing).
            "sections": [section.model_dump() for section in infographic.sections],
            # The citation metadata (document/section/page) each id resolves to.
            "citations": ctx.bundle.citations_payload(),
            # Whether the poster PNG is available as the main asset.
            "has_image": image is not None,
        }
        return GeneratedArtifact(
            spec_json=spec_json,
            data=image,
            ext="png" if image is not None else None,
        )

    async def _render_poster(self, infographic: spec_mod.Infographic) -> bytes | None:
        """Best-effort editorial portrait poster. A failed image is not a failed job."""
        prompt = infographic_prompt(infographic)
        try:
            return await generate_image(prompt, size=_IMAGE_SIZE)
        except Exception as exc:  # noqa: BLE001 - visual is best-effort; spec still carries facts
            logger.warning("Infographic poster generation failed, continuing spec-only: %s", exc)
            return None


def register() -> None:
    """Register the infographic generator under ``MediaKind.INFOGRAPHIC`` (idempotent)."""
    register_generator(InfographicGenerator())


__all__ = ["InfographicGenerator", "register"]
