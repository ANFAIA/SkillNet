"""The :class:`PodcastGenerator` — the podcast's plug into the media spine (roadmap §2a).

It implements the spine's ``MediaGenerator`` protocol and wires the two stages:

    grounded bundle --script agent--> validated script --voices--> one mp3

and returns a :class:`GeneratedArtifact` whose ``spec_json`` carries the full transcript
(``turns`` with their ``citation_ids``) plus the bundle's citation metadata, so the
frontend can render the parallel quotes panel, and whose ``data`` is the mp3 the spine
stores in the asset store.

Three SSE progress steps are emitted through the context's reporter — ``guion`` (writing
the script), ``voz`` (synthesizing), ``listo`` (done, with which voice path was used) —
so the player can show real stages instead of a spinner.
"""

from __future__ import annotations

from src.core.logging import get_logger
from src.models import MediaKind
from src.services.media.jobs import (
    GeneratedArtifact,
    MediaJobContext,
    register_generator,
)
from src.services.media.podcast import script as script_mod
from src.services.media.podcast import voices as voices_mod

logger = get_logger(__name__)


class PodcastGenerator:
    """Generate a grounded, two-host (or one-host) audio overview for a course/node."""

    kind = MediaKind.PODCAST

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
        spec = ctx.spec or {}
        fmt = script_mod.coerce_format(spec.get("format"))
        language = str(spec.get("language") or "es")
        steering = spec.get("prompt") or spec.get("steering") or spec.get("note")
        scope = str(spec.get("scope") or ("node" if ctx.node is not None else "course"))
        target_seconds = spec.get("target_seconds")
        if target_seconds is not None:
            try:
                target_seconds = int(target_seconds)
            except (TypeError, ValueError):
                target_seconds = None
        # A course-scoped podcast is the "full course" overview: a longer episode that walks
        # the whole corpus, not one node. When the caller did not pin a length, default a
        # two-host course episode to a fuller runtime than a single-node one.
        if target_seconds is None and scope == "course" and fmt is not script_mod.PodcastFormat.THE_BRIEF:
            target_seconds = 600

        await ctx.emit("guion", format=fmt.value)
        script = await script_mod.generate_script(
            ctx.bundle,
            fmt=fmt,
            language=language,
            target_seconds=target_seconds,
            steering=steering if isinstance(steering, str) else None,
        )

        await ctx.emit("voz", turns=len(script.turns))
        result = await voices_mod.synthesize_podcast(script)

        await ctx.emit("listo", voice_path=result.voice_path)
        logger.info(
            "Podcast generated: format=%s turns=%d voice_path=%s bytes=%d",
            script.format.value,
            len(script.turns),
            result.voice_path,
            len(result.data),
        )

        spec_json = {
            "generator": "podcast",
            "scope": scope,
            "format": script.format.value,
            "language": script.language,
            "target_seconds": script.target_seconds,
            "voice_path": result.voice_path,
            "grounding_mode": ctx.bundle.mode,
            # The transcript with per-turn citation_ids — what the parallel panel reads.
            "turns": [turn.model_dump() for turn in script.turns],
            # The citation metadata (document/section/page) each id resolves to.
            "citations": ctx.bundle.citations_payload(),
        }
        return GeneratedArtifact(spec_json=spec_json, data=result.data, ext=result.ext)


def register() -> None:
    """Register the podcast generator under ``MediaKind.PODCAST`` (idempotent)."""
    register_generator(PodcastGenerator())


__all__ = ["PodcastGenerator", "register"]
