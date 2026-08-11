"""Audio Overview / Podcast generator (roadmap §2a).

A three-stage pipeline plugged into the media spine:

* :mod:`script` — a small litellm call turns the grounded bundle into a strict-JSON,
  Pydantic-validated dialogue script (personas + one of four show formats).
* :mod:`voices` — the script becomes a single mp3: primary path is ElevenLabs
  Text-to-Dialogue (one call), fallback is per-turn TTS through the existing service
  concatenated with ffmpeg.
* :mod:`generator` — the :class:`~src.services.media.jobs.MediaGenerator` that wires the
  two together, emits SSE progress, and persists ``turns[].citation_ids`` so the frontend
  can render the parallel citations panel.

Importing this package registers :class:`~src.services.media.podcast.generator.PodcastGenerator`
under :data:`~src.models.media_artifact.MediaKind.PODCAST`, overriding the echo default.
"""

from src.services.media.podcast.generator import PodcastGenerator, register

register()

__all__ = ["PodcastGenerator", "register"]
