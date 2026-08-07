"""Pydantic types and shared helpers for the multi-agent pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class BlueprintBlock(BaseModel):
    id: str
    type: str  # kit component name
    intent: Literal["enganchar", "concepto", "verificar", "refuerzo"]
    variant: str | None = None       # for TextContent
    columns: int | None = None       # for Table
    item_type: str | None = None     # for QuizItem
    bloom: str | None = None         # for QuizItem/DragOrder
    note: str | None = None          # free-form instruction for agents 2/3


class Blueprint(BaseModel):
    blocks: list[BlueprintBlock]


class ContentOutput(BaseModel):
    """OpenUI Lang declarations for content blocks, one per line."""
    declarations: str


class InteractionOutput(BaseModel):
    """OpenUI Lang declarations for interactive blocks + answer key."""
    declarations: str
    answer_key: dict


# ---------------------------------------------------------------------------
# Prompt-building helpers shared by all agents.
#
# These are the same values that ``src.llm.prompts.runtime`` uses for the
# monolithic ``genera_ui`` prompt.  They live here because the runtime module
# keeps them private (prefixed ``_``), and importing them would couple the
# agents to the monolithic prompt module's internals.
# ---------------------------------------------------------------------------

CRITICALITY_RULES: dict[str, str] = {
    "critical": (
        "TRATAMIENTO DEL NODO: es de cumplimiento obligatorio. Incluye un "
        'Callout("warn", "<texto tuyo resumiendo la prohibicion o limite>") si la fuente '
        "marca un limite o prohibicion. Solo uno. El texto del Callout lo redactas tu a "
        "partir de la fuente, no copies esta instruccion."
    ),
    "recommended": (
        "TRATAMIENTO DEL NODO: importancia media. No dramatices. Usa Callout solo si la "
        "fuente contiene una excepcion real que el aprendiz deba recordar."
    ),
    "contextual": (
        "TRATAMIENTO DEL NODO: contexto complementario. No hace falta ningun Callout "
        "salvo que la fuente contenga una advertencia explicita."
    ),
}

SCAFFOLD_RULES: dict[str, str] = {
    "novice": (
        "ANDAMIAJE ALTO: incluye un ejemplo resuelto paso a paso antes de pedir nada. "
        "Nombra cada paso. No des por sabido ningun termino del dominio."
    ),
    "neutral": (
        "ANDAMIAJE NEUTRO: ni ejemplos resueltos extra ni supresion de apoyos. "
        "Explica y pasa al caso concreto."
    ),
    "advanced": (
        "ANDAMIAJE BAJO: ve al caso limite y a las excepciones. No expliques lo basico "
        "ni repitas definiciones; esta persona ya demostro que lo domina."
    ),
}

DENSITY_BUDGET: dict[int, str] = {
    1: "2-3 bloques y frases muy cortas. Solo lo imprescindible.",
    2: "3 bloques como maximo y frases cortas.",
    3: "3-4 bloques. Explicacion normal, sin relleno.",
    4: "4-5 bloques. Puedes desarrollar mas dentro de cada bloque, no anadir mas bloques.",
    5: (
        "5 bloques como maximo, pero desarrollados: ejemplos y matices DENTRO de esos "
        "cinco. Nunca un sexto."
    ),
}


def criticality_rule(criticality: str) -> str:
    return CRITICALITY_RULES.get(
        str(criticality).strip().lower(), CRITICALITY_RULES["recommended"]
    )


def scaffold_rule(scaffold_band: str) -> str:
    return SCAFFOLD_RULES.get(scaffold_band, SCAFFOLD_RULES["neutral"])


def density_budget(effective_density: int) -> str:
    try:
        level = int(effective_density)
    except (TypeError, ValueError):
        level = 3
    return DENSITY_BUDGET.get(max(1, min(level, 5)), DENSITY_BUDGET[3])
