"""Slide Deck generator (roadmap §2c).

A single-stage pipeline plugged into the media spine:

* :mod:`spec` — a small litellm call turns the grounded bundle into a strict-JSON,
  Pydantic-validated deck whose slides carry **kit-block specs** (the vocabulary-unfreezing
  move: a slide is just kit blocks in a slide frame).
* :mod:`generator` — the :class:`~src.services.media.jobs.MediaGenerator` that runs the
  content stage, emits SSE progress, and persists ``slides[].citation_ids`` so the frontend
  can render the parallel citations panel.

Importing this package registers :class:`~src.services.media.slides.generator.SlidesGenerator`
under :data:`~src.models.media_artifact.MediaKind.SLIDES`, overriding the echo default.
"""

from src.services.media.slides.generator import SlidesGenerator, register

register()

__all__ = ["SlidesGenerator", "register"]
