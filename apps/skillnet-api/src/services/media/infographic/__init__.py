"""Infographic generator (roadmap §2d).

A single-stage pipeline plugged into the media spine:

* :mod:`spec` — a small litellm call turns the grounded bundle into a strict-JSON,
  Pydantic-validated sheet whose facts are **extracted as data** and verified against the
  passages (the §2d rule: image models cannot be trusted with facts).
* :mod:`generator` — the :class:`~src.services.media.jobs.MediaGenerator` that runs the
  content stage, emits SSE progress, and persists ``sections[].citation_ids`` so the
  frontend can render the stylized sheet (text drawn by us) and the parallel citations
  panel.

Importing this package registers
:class:`~src.services.media.infographic.generator.InfographicGenerator` under
:data:`~src.models.media_artifact.MediaKind.INFOGRAPHIC`, overriding the echo default.
"""

from src.services.media.infographic.generator import InfographicGenerator, register

register()

__all__ = ["InfographicGenerator", "register"]
