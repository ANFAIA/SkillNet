"""Video Overview generator (roadmap §2b) — narrated slides, NOT a real video model.

A three-stage pipeline plugged into the media spine, reusing already-committed machinery:

* :mod:`~src.services.media.slides.spec` — the slide deck content stage, reused verbatim.
* :mod:`narration` — a small litellm call turns the deck into one strict-JSON,
  Pydantic-validated narration line per slide (single host, grounded, carrying
  ``citation_ids``).
* :mod:`voice` — each line becomes one mp3 clip through the podcast TTS path (single
  host), cached per content hash.
* :mod:`generator` — the :class:`~src.services.media.jobs.MediaGenerator` that wires the
  three together, stores each clip, emits SSE progress, and persists per-slide
  ``narration`` + ``audio_ref`` + ``narration_citation_ids`` so the frontend player can
  sequence the slides, play each clip, and show the captions strip. Nothing is stitched
  into a video file — the player does the sequencing (§2b/§3 trap).

Importing this package registers :class:`~src.services.media.video.generator.VideoGenerator`
under :data:`~src.models.media_artifact.MediaKind.VIDEO`, overriding the echo default.
"""

from src.services.media.video.generator import VideoGenerator, register

register()

__all__ = ["VideoGenerator", "register"]
