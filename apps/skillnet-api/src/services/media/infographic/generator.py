"""The :class:`InfographicGenerator` — the infographic's plug into the media spine (§2d).

It implements the spine's ``MediaGenerator`` protocol and wires the single content stage:

    grounded bundle --content agent--> validated infographic (facts as data)

and returns a **spec-only** :class:`GeneratedArtifact`: the sheet is structured JSON the
frontend renders as crisp HTML/SVG text we control, honouring the §2d/§3 rule that factual
text is never baked into a generated image. ``spec_json`` carries the title, the sections
with their stats and ``citation_ids``, and the bundle's citation metadata, so the frontend
renders the stylized sheet and the parallel citations panel.

Two SSE progress steps are emitted through the context's reporter — ``datos`` (extracting
the facts) and ``listo`` (done, with the section count).
"""

from __future__ import annotations

from src.core.logging import get_logger
from src.models import MediaKind
from src.services.media.infographic import spec as spec_mod
from src.services.media.jobs import (
    GeneratedArtifact,
    MediaJobContext,
    register_generator,
)

logger = get_logger(__name__)


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
        steering = spec.get("prompt") or spec.get("steering")

        await ctx.emit("datos", style=style)
        infographic = await spec_mod.generate_infographic(
            ctx.bundle,
            language=language,
            style=style,
            orientation=orientation,
            steering=steering if isinstance(steering, str) else None,
        )

        await ctx.emit("listo", sections=len(infographic.sections))
        logger.info(
            "Infographic generated: sections=%d style=%s orientation=%s grounding=%s",
            len(infographic.sections),
            infographic.style,
            infographic.orientation,
            ctx.bundle.mode,
        )

        spec_json = {
            "generator": "infographic",
            "title": infographic.title,
            "subtitle": infographic.subtitle,
            "orientation": infographic.orientation,
            "style": infographic.style,
            "language": infographic.language,
            "grounding_mode": ctx.bundle.mode,
            # The sections (facts as data) with per-section citation_ids — what the sheet
            # and the parallel panel read.
            "sections": [section.model_dump() for section in infographic.sections],
            # The citation metadata (document/section/page) each id resolves to.
            "citations": ctx.bundle.citations_payload(),
        }
        # Spec-only by design: no bytes, no image-baked facts.
        return GeneratedArtifact(spec_json=spec_json)


def register() -> None:
    """Register the infographic generator under ``MediaKind.INFOGRAPHIC`` (idempotent)."""
    register_generator(InfographicGenerator())


__all__ = ["InfographicGenerator", "register"]
