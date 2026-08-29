"""Who an artifact is *about* — the identity every media prompt must carry.

Four generator families (podcast, slides, infographic, video narration) each built their
user prompt out of the grounded bundle alone, and when the bundle came back empty the
prompt literally said "no source material; speak in general terms". A model told that has
no way of knowing the course is about boxing, so it wrote about healthy living and
financial literacy — and the artifact went out green, in ``done``, with nobody able to tell
it was wrong. The identity was never missing from the system: the job runner builds its
``MediaJobContext`` with ``course=`` and ``node=`` inside. It just never reached the prompt.

This module is the one place that fixes it, rather than the same paragraph copied into four
prompt builders that would drift apart the first time one of them was edited:

* :class:`MediaSubject` — the course/node identity, as plain strings.
* :func:`subject_from` — how the job runner's ``course``/``node`` become one.
* :func:`build_user_context` — the user-prompt block every family now starts with, and the
  single gate that refuses to generate when there is no context at all.

The refusal is the second half of the fix. An artifact that is confidently about the wrong
subject is worse than one that failed: a failure says so on the row, in the same place and
the same shape as every other media failure (``services/media/jobs.py``: a stable code, a
short safe sentence), and the owner can act on it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.exceptions import AppError
from src.services.media.grounding import GroundedBundle

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module free of ORM imports
    from src.models import Course, CourseNode

#: Free-text fields (descriptions, summaries) are clipped before they reach a prompt: they
#: are identity, not source material, and the passages below them are what deserves the
#: token budget.
_FIELD_CHARS = 400


class MediaContextError(AppError):
    """Nothing at all is known about what this artifact should be about.

    Raised *before* the LLM call, so no artifact is ever produced from an empty subject and
    an empty bundle. It is an :class:`AppError` (409) rather than a bare ``ValueError``
    because the request is well formed — it is the course's state that has nothing to
    generate from, and no retry against the same course will change that.
    """

    def __init__(
        self,
        message: str = (
            "There is nothing to generate from: this course has no source material and no "
            "title or objective to work from."
        ),
    ) -> None:
        super().__init__(message=message, code="media_no_context", status_code=409)


def _clip(value: object) -> str:
    """One model field as a short, prompt-safe string. Never ``None``, never oversized."""
    text = str(value or "").strip()
    return text[:_FIELD_CHARS]


@dataclass(frozen=True)
class MediaSubject:
    """The course (and, for a node-scoped artifact, the lesson) an artifact is about.

    Plain strings rather than the ORM objects on purpose: this travels into pure prompt
    builders that are unit-tested without a database, and it is the only shape they need.
    """

    course_title: str = ""
    course_description: str = ""
    course_outcome: str = ""
    node_title: str = ""
    node_summary: str = ""
    node_objective: str = ""

    def is_empty(self) -> bool:
        """True when nothing whatsoever identifies the subject."""
        return not any(
            (
                self.course_title,
                self.course_description,
                self.course_outcome,
                self.node_title,
                self.node_summary,
                self.node_objective,
            )
        )

    def headline(self) -> str:
        """One line for the system prompt: the topic, and the lesson when there is one."""
        course = self.course_title or "(curso sin titulo)"
        if self.node_title:
            return f'el curso "{course}", leccion "{self.node_title}"'
        return f'el curso "{course}"'

    def as_prompt_block(self) -> str:
        """The labelled identity block that opens the user prompt. Empty when unknown."""
        rows = [
            ("Curso", self.course_title),
            ("De que trata el curso", self.course_description),
            ("Resultado esperado del curso", self.course_outcome),
            ("Leccion", self.node_title),
            ("De que trata la leccion", self.node_summary),
            ("Objetivo de la leccion", self.node_objective),
        ]
        lines = [f"- {label}: {value}" for label, value in rows if value]
        if not lines:
            return ""
        return "\n".join(
            [
                "TEMA DEL ARTEFACTO (todo lo que produzcas trata de ESTO y de nada mas):",
                *lines,
            ]
        )


def subject_from(
    course: "Course | None", node: "CourseNode | None" = None
) -> MediaSubject:
    """Build the subject from the job's course/node. The node's fields only when scoped."""
    return MediaSubject(
        course_title=_clip(getattr(course, "title", "")),
        course_description=_clip(getattr(course, "description", "")),
        course_outcome=_clip(getattr(course, "outcome", "")),
        node_title=_clip(getattr(node, "title", "")),
        node_summary=_clip(getattr(node, "summary", "")),
        node_objective=_clip(getattr(node, "outcome", "")),
    )


#: What replaces the old "(No hay material de origen; habla en general.)". The difference is
#: the whole point: the model is told to stay on the subject stated above, not to improvise
#: a subject of its own.
_NO_PASSAGES_LINE = (
    "(No hay pasajes de origen citables. Escribe apoyandote UNICAMENTE en el tema "
    "indicado arriba: no cambies de tema, no elijas otro, no inventes datos.)"
)

_SOURCE_HEADER = "MATERIAL DE ORIGEN (cada bloque empieza con su marcador [Fuente cN: ...]):"


def build_user_context(
    bundle: GroundedBundle,
    subject: MediaSubject | None,
    *,
    sections: Sequence[str] = (),
) -> str:
    """The user-prompt context every media family shares: identity first, passages after.

    ``sections`` are extra blocks (the video narrator's slide summaries) placed between the
    two, so a caller does not have to re-glue the pieces in its own order.

    Raises :class:`MediaContextError` when neither half exists. Deliberately phrased over
    the *rendered* context string rather than over ``bundle.mode``: a new grounding mode
    must not need a change here, and a bundle whose passages are all blank is empty in
    every sense that matters to a prompt.
    """
    subject = subject or MediaSubject()
    passages = (bundle.as_prompt_context() or "").strip()
    if not passages and subject.is_empty():
        raise MediaContextError()

    parts: list[str] = []
    block = subject.as_prompt_block()
    if block:
        parts.append(block)
    parts.extend(section for section in sections if section)
    parts.append(_SOURCE_HEADER)
    parts.append(passages or _NO_PASSAGES_LINE)
    return "\n\n".join(parts)


def topic_rule(subject: MediaSubject | None) -> str:
    """The system-prompt sentence that pins the topic, or "" when nothing is known.

    Short on purpose: the identity itself lives in the user prompt, and this is the rule
    that keeps the model from drifting off it.
    """
    if subject is None or subject.is_empty():
        return ""
    return (
        f"El artefacto es para {subject.headline()}. Todo lo que escribas trata de ese "
        "tema; si el material de origen no cubre algo, no lo sustituyas por otro tema.\n\n"
    )


__all__ = [
    "MediaContextError",
    "MediaSubject",
    "build_user_context",
    "subject_from",
    "topic_rule",
]
