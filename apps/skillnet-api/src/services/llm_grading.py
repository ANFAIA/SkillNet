"""LLM-based grading for open-ended exercise types (practical_case, dialogue).

Deterministic types are graded in ``exercise_service``. This module is the seam
that turns an admin-configured LLM into a rubric-based grader. If the model call
fails, the caller still gets a graceful "needs review" result.

Both halves of what the learner reads back are language-sensitive, and they are fixed
differently. The model's ``feedback`` is a generation, so the system prompt carries the
output-language rule (``with_language``). The graceful fallback is a literal this module
owns, so it gets a table — and it is the one a reviewer is most likely to hit, because it
is what a provider hiccup produces.

The rubric itself is deliberately **not** translated. It is what the course author wrote
and what the score has to be defensible against; restating it in another language on the
way into the prompt would mean grading against a paraphrase.
"""

from __future__ import annotations

import json
from typing import Any

from src.core.exceptions import LLMError
from src.core.language import DEFAULT_LANGUAGE, Language, normalize_language
from src.core.logging import get_logger
from src.llm.client import LLMService
from src.llm.parsing import parse_json_response
from src.llm.prompts.language import with_language
from src.schemas.exercise import AttemptResult
from src.services.language_policy import prompt_language

logger = get_logger(__name__)

_GRADER_SYSTEM = (
    "Eres un evaluador de respuestas abiertas. Evalua la "
    "respuesta de la persona contra los criterios dados. Se justo pero riguroso. "
    'Responde SOLO en JSON valido: {"score": <0..1>, "passed": <bool>, '
    '"feedback": "<comentario breve y util>"}.'
)

#: What the learner is told when the grader could not run. One per language, because this
#: is the sentence a reviewer sees the moment the provider rate-limits — the surface's
#: least reassuring moment is a bad one to also be unreadable.
_PENDING_FEEDBACK: dict[Language, str] = {
    "es": "Respuesta registrada. Pendiente de evaluacion.",
    "en": "Answer recorded. Pending review.",
}


def _pending(language: str | None) -> AttemptResult:
    """The graceful "not graded yet" result. Never raises, never scores badly.

    ``0.5`` and ``passed=False`` are unchanged: this is not a judgement about the answer,
    it is the absence of one, and the caller's mastery maths already treats it as such.
    """
    return AttemptResult(
        score=0.5,
        passed=False,
        feedback=_PENDING_FEEDBACK[normalize_language(language) or DEFAULT_LANGUAGE],
        explanation=None,
    )


def _clamp(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _build_criteria(exercise_type: str, content: dict) -> str:
    if exercise_type == "practical_case":
        rubric = content.get("rubric") or []
        return "Rubrica:\n" + json.dumps(rubric, ensure_ascii=False)
    # dialogue
    parts = []
    if content.get("system_prompt"):
        parts.append(f"Rol del interlocutor: {content['system_prompt']}")
    criteria = content.get("evaluation_criteria") or []
    parts.append("Criterios de evaluacion:\n" + json.dumps(criteria, ensure_ascii=False))
    return "\n\n".join(parts)


async def grade_open_answer(
    llm: LLMService,
    exercise_type: str,
    content: dict,
    answer: Any,
    *,
    language: str | None = None,
) -> AttemptResult:
    """Grade a practical_case or dialogue answer with the LLM against its rubric.

    ``language`` defaults to ``None``, which is the pre-existing behaviour byte for byte:
    the grader prompt is untouched and the pending feedback stays Spanish. Callers that
    know the course pass it; the ones that do not keep working.
    """
    context = content.get("context", "")
    question = content.get("question", "")
    criteria = _build_criteria(exercise_type, content)
    user_prompt = (
        f"=== CONTEXTO ===\n{context}\n\n"
        f"=== CONSIGNA ===\n{question}\n\n"
        f"=== {criteria} ===\n\n"
        f"=== RESPUESTA DE LA PERSONA ===\n"
        f"{json.dumps(answer, ensure_ascii=False, default=str)}"
    )

    try:
        response = await llm.complete(
            with_language(_GRADER_SYSTEM, prompt_language(language)),
            user_prompt,
            temperature=0.1,
            max_tokens=1024,
            json_mode=True,
        )
        data = parse_json_response(response)
    except LLMError:
        logger.warning("Open-answer grading unavailable; returning pending result")
        return _pending(language)

    if not isinstance(data, dict):
        return _pending(language)

    score = _clamp(data.get("score"))
    return AttemptResult(
        score=score,
        passed=score >= 0.6,
        feedback=data.get("feedback") or None,
        explanation=None,
    )
