"""The :class:`VideoGenerator` — the Video Overview's plug into the media spine (§2b).

The Video Overview is **narrated slides shipped as HTML**, never a real generative video
model (roadmap §2b, and the §3 trap note: do NOT chase Cinematic/Veo — ship
narrated-slides-as-HTML). It implements the spine's ``MediaGenerator`` protocol and wires
three stages, all reusing already-committed machinery:

    grounded bundle --slides content stage--> deck
                    --narration agent--------> one spoken line per slide
                    --podcast TTS path-------> one mp3 clip per slide (stored, cached)

Nothing is stitched into a video file: each slide's clip is stored on its own in the asset
store and referenced from ``spec_json`` by its content hash, and the **frontend player**
does the sequencing (advance on ``ended``, scrub across slides). This keeps the pipeline
ffmpeg-free and the artifact editable.

The output spec is the deck, with each slide augmented by its ``narration`` line, that
line's ``narration_citation_ids`` (the captions strip's provenance), and an ``audio_ref``
(the content hash the per-slide asset route serves). Because there are *many* clips rather
than one rendered file, the artifact is **spec-only** to the spine (``data=None``): the
generator stores the clips itself and the spine stores no top-level asset.

Four SSE progress steps are emitted through the context's reporter — ``diapositivas``
(deck), ``narracion`` (lines), ``voz`` (synthesizing clips), ``listo`` (done, with the
dominant voice path) — so the player shows real stages instead of a spinner.
"""

from __future__ import annotations

from collections import Counter

from src.core.logging import get_logger
from src.models import MediaKind
from src.services.media.assets import AssetStore
from src.services.media.images import generate_image
from src.services.media.jobs import (
    GeneratedArtifact,
    MediaJobContext,
    register_generator,
)
from src.services.media.slides import spec as slides_spec
from src.services.media.video import narration as narration_mod
from src.services.media.video import voice as voice_mod
from src.services.media.visuals import slide_prompt

logger = get_logger(__name__)

#: Landscape 16:9 for the per-slide illustrations (the approved gallery look).
_SLIDE_SIZE = "1536x1024"


def _summarize_voice_paths(paths: list[str]) -> str:
    """One label for a batch of per-slide voice paths: the single one, or ``mixed``.

    Every clip taking the same route (all ``dialogue``, all ``fallback``, all ``cache``)
    reports that route; a mix reports ``mixed`` so the smoke test/UI can see it was not
    uniform. An empty batch (no slides voiced) reports ``none``.
    """
    unique = set(paths)
    if not unique:
        return "none"
    if len(unique) == 1:
        return next(iter(unique))
    return "mixed"


class VideoGenerator:
    """Generate a grounded, narrated slideshow (Video Overview) for a course/node."""

    kind = MediaKind.VIDEO

    def __init__(self, asset_store: AssetStore | None = None) -> None:
        # Injectable for tests (a tmp-dir store); ``None`` -> the app's media assets dir at
        # generate time, so registration stays a zero-arg construction.
        self._asset_store = asset_store

    async def generate(self, ctx: MediaJobContext) -> GeneratedArtifact:
        spec = ctx.spec or {}
        language = str(spec.get("language") or "es")
        theme = str(spec.get("theme") or "default")
        steering = spec.get("prompt") or spec.get("steering")
        steering = steering if isinstance(steering, str) else None

        # Stage 1: the slide deck (reuse the slides content stage verbatim).
        await ctx.emit("diapositivas", theme=theme)
        deck = await slides_spec.generate_deck(
            ctx.bundle, language=language, theme=theme, steering=steering
        )

        # Stage 2: one narration line per slide (grounded, carrying citation_ids).
        await ctx.emit("narracion", slides=len(deck.slides))
        narration = await narration_mod.generate_narration(
            deck, ctx.bundle, language=language, steering=steering
        )

        # Stage 3: one mp3 clip per slide via the podcast TTS path, stored + cached, plus one
        # NotebookLM-style landscape illustration per slide (best-effort), stored the same
        # content-addressed way and referenced from spec_json by image_ref.
        await ctx.emit("voz", slides=len(deck.slides))
        await ctx.emit("ilustraciones", slides=len(deck.slides))
        store = self._asset_store or AssetStore()
        slides_out: list[dict] = []
        voice_paths: list[str] = []
        images = 0
        for slide, line in zip(deck.slides, narration.lines):
            result = await voice_mod.synthesize_narration(line.text, language=language)
            stored = store.store(result.data, result.ext)
            voice_paths.append(result.voice_path)

            slide_dict = slide.model_dump()
            slide_dict["narration"] = line.text
            slide_dict["narration_citation_ids"] = line.citation_ids
            slide_dict["audio_ref"] = stored.content_hash
            slide_dict["audio_ext"] = stored.ext

            image = await self._render_slide(slide, store)
            if image is not None:
                slide_dict["image_ref"] = image[0]
                slide_dict["image_ext"] = image[1]
                images += 1
            slides_out.append(slide_dict)

        voice_path = _summarize_voice_paths(voice_paths)
        await ctx.emit("listo", slides=len(slides_out), voice_path=voice_path)
        logger.info(
            "Video overview generated: slides=%d images=%d voice_path=%s grounding=%s clips=%s",
            len(slides_out),
            images,
            voice_path,
            ctx.bundle.mode,
            Counter(voice_paths),
        )

        spec_json = {
            "generator": "video",
            "theme": deck.theme,
            "language": deck.language,
            "grounding_mode": ctx.bundle.mode,
            "voice_path": voice_path,
            # The deck, each slide augmented with narration + its clip's audio_ref. What the
            # frontend player renders/plays and the captions strip reads.
            "slides": slides_out,
            # The citation metadata (document/section/page) each id resolves to.
            "citations": ctx.bundle.citations_payload(),
        }
        # Spec-only to the spine: the per-slide clips and illustrations are stored above,
        # not one top-level file, so there is no single ``data`` to hand back.
        return GeneratedArtifact(spec_json=spec_json)

    async def _render_slide(
        self, slide: slides_spec.Slide, store: AssetStore
    ) -> tuple[str, str] | None:
        """Best-effort per-slide illustration. Returns ``(image_ref, image_ext)`` or ``None``."""
        prompt = slide_prompt(slide)
        try:
            data = await generate_image(prompt, size=_SLIDE_SIZE)
        except Exception as exc:  # noqa: BLE001 - per-slide visual is best-effort, not fatal
            logger.warning("Video slide illustration generation failed, skipping: %s", exc)
            return None
        stored = store.store(data, "png")
        return stored.content_hash, stored.ext


def register() -> None:
    """Register the video generator under ``MediaKind.VIDEO`` (idempotent)."""
    register_generator(VideoGenerator())


__all__ = ["VideoGenerator", "register"]
