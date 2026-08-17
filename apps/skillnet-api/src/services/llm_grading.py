"""LLM-based grading for open-ended exercise types (practical_case, dialogue).

Deterministic types are graded in ``exercise_service``. This module is the seam
that turns an admin-configured LLM into a rubric-based grader. If the model call
fails, the caller still gets a graceful "needs review" result.
"""

from __future__ import annotations

import json
from typing import Any

from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.llm.client import LLMService
from src.llm.parsing import parse_json_response
from src.schemas.exercise import AttemptResult

logger = get_logger(__name__)

_GRADER_SYSTEM = (
    "Eres un evaluador de respuestas abiertas. Evalua la "
    "respuesta de la persona contra los criterios dados. Se justo pero riguroso. "
    'Responde SOLO en JSON valido: {"score": <0..1>, "passed": <bool>, '
    '"feedback": "<comentario breve y util>"}.'
)

_PENDING = AttemptResult(
    score=0.5,
    passed=False,
    feedback="Respuesta registrada. Pendiente de evaluacion.",
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
    llm: LLMService, exercise_type: str, content: dict, answer: Any
) -> AttemptResult:
    """Grade a practical_case or dialogue answer with the LLM against its rubric."""
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
            _GRADER_SYSTEM,
            user_prompt,
            temperature=0.1,
            max_tokens=1024,
            json_mode=True,
        )
        data = parse_json_response(response)
    except LLMError:
        logger.warning("Open-answer grading unavailable; returning pending result")
        return _PENDING

    if not isinstance(data, dict):
        return _PENDING

    score = _clamp(data.get("score"))
    return AttemptResult(
        score=score,
        passed=score >= 0.6,
        feedback=data.get("feedback") or None,
        explanation=None,
    )
