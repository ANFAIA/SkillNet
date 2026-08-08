"""Interaction Designer agent — creates QuizItem/DragOrder blocks + answer key.

Part of the 4-agent pipeline: Blueprint -> Content Writer + Interaction Designer
(parallel) -> Assembler.  This agent runs in parallel with the Content Writer and
works from the blueprint and source context, not from the written content.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from src.agents.runtime.agents.types import Blueprint, InteractionOutput, scaffold_rule
from src.core.logging import get_logger
from src.llm.parsing import parse_json_response
from src.llm.prompts.runtime import ANSWER_KEY_SENTINEL, clip_source
from src.render.prompt import render_prompt

logger = get_logger(__name__)

# ── system prompt ─────────────────────────────────────────────────────────────


@cache
def interaction_designer_system() -> str:
    """The system prompt for the interaction designer agent.

    Combines the generated OpenUI dialect prompt with interaction-specific
    instructions.  Cached: the artefact is immutable at runtime.
    """
    return render_prompt().rstrip("\n") + f"""

## SkillNet Interaction Designer: tu tarea especifica

Eres el disenador de INTERACCIONES de SkillNet. Recibes un blueprint y el contenido
ya escrito. Tu trabajo es escribir SOLO los bloques interactivos y de evaluacion.

Lo que SI haces:
- Escribir QuizItem y DragOrder, en dialecto OpenUI Lang.
- Una declaracion por linea: id = Componente(args...)
- Escribir el bloque {ANSWER_KEY_SENTINEL} con las respuestas correctas.
- Usar los ids EXACTOS del blueprint.
- Las preguntas se basan en el contenido escrito y/o en la fuente del nodo.

Lo que NO haces:
- NO escribir TextContent, Table, StepSequence ni ningun otro bloque de contenido.
- NO escribir la linea root = Stack(...).
- NO escribir prosa antes ni despues.

## Como hacer buenas preguntas

La pregunta evalua si el aprendiz APRENDIO el contenido, no si leyo la pantalla.

QuizItem de tipo "test":
- SIEMPRE 4 opciones.
- Los DISTRACTORES son errores plausibles, no tonterias.
- La pregunta plantea una SITUACION CONCRETA o pide un DATO ESPECIFICO de la fuente:
  BIEN: "Un cliente llama porque no recibio su entrada. Que haces primero?"
  BIEN: "Si buscas por email y no aparece, cual es el siguiente paso?"
  BIEN: "Cual es la diferencia entre descargar por Codigo y por Referencia?"
- PROHIBIDO preguntar sobre "el nodo", "la leccion", "el enfoque", "el objetivo",
  "lo que se explora", "el proposito de esta seccion". Eso no evalua nada.
  MAL: "Cual es el enfoque principal del nodo sobre la historia del MMA?"
  MAL: "Que se explora en esta leccion?"
  MAL: "Cual es el primer paso que debes seguir para acceder a...?" (demasiado literal)
- La respuesta correcta SIEMPRE se puede verificar con la fuente o el contenido escrito.
- La explicacion cita un DATO CONCRETO del contenido que justifica la respuesta.
- Las 4 opciones deben ser PLAUSIBLES: el aprendiz que no aprendio debe dudar.
- QuizItem: EXACTAMENTE 5 argumentos: QuizItem("id", "tipo", "bloom", "pregunta?", ["A", "B", "C", "D"]).

Para DragOrder:
- EXACTAMENTE 3 argumentos: DragOrder("instruccion", ["items..."], ["orden correcto..."]).
- 4-6 elementos, acciones concretas.

Ejemplo completo de salida:
q1 = QuizItem("q1", "test", "apply", "Un cliente celiaco pide una fritura. El aceite se uso antes para rebozados con harina. Que le dices?", ["Que si, el aceite no retiene gluten", "Que no es apto: el aceite tiene trazas de gluten", "Que pregunte al cocinero", "Que solo es peligroso si es alergico severo"])
---ANSWER-KEY---
{{"q1": {{"correct": 1, "explanation": "El aceite que frio un rebozado con harina contiene trazas de gluten por contaminacion cruzada."}}}}

Formato de la clave de respuestas:
Despues de las declaraciones, una linea con exactamente {ANSWER_KEY_SENTINEL} y a continuacion
un unico JSON:

{ANSWER_KEY_SENTINEL}
{{"q1": {{"correct": 2, "explanation": "Por que esa y no otra."}}}}

Forma de cada entrada segun item_type:
- "test": {{"correct": <indice 0-based>, "explanation": "..."}}
- "true_false": {{"correct": true|false, "explanation": "..."}}
- "fill_blank": {{"blanks": ["texto exacto"], "explanation": "..."}}
- "order_steps": {{"correct_order": [indices], "explanation": "..."}}

- El JSON de la clave es la UNICA parte de tu respuesta donde puede aparecer {{ o }}.
  No escribas JSON ni llaves dentro de las declaraciones del programa.

Responde con las declaraciones y su clave. Nada mas.
"""


# ── user prompt ───────────────────────────────────────────────────────────────


def build_interaction_prompt(
    *,
    blueprint: Blueprint,
    content_declarations: str,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    target_bloom: str,
    scaffold_band: str,
) -> str:
    """Build the user prompt for the interaction designer.

    Returns an empty string when the blueprint contains no interaction blocks,
    signalling to the caller that no LLM call is needed.
    """
    interaction_blocks = [
        b for b in blueprint.blocks if b.type in ("QuizItem", "DragOrder")
    ]
    if not interaction_blocks:
        return ""

    parts: list[str] = [
        "BLUEPRINT (escribe SOLO estos bloques, con estos ids exactos)",
    ]
    for block in interaction_blocks:
        item_type = block.item_type or "test"
        bloom = block.bloom or target_bloom
        parts.append(f"- {block.id}: {block.type} (item_type={item_type}, bloom={bloom})")

    parts.append("")
    parts.append(f"NODO: {title}")
    parts.append(f"RESUMEN: {summary}")
    parts.append(f"- Nivel cognitivo objetivo: {target_bloom}")
    parts.append(f"- {scaffold_rule(scaffold_band)}")

    if role_title:
        role_line = f"- Las preguntas son sobre situaciones de un/una {role_title}"
        if sector:
            role_line += f" del sector {sector}."
        else:
            role_line += "."
        parts.append(role_line)

    parts.append("")
    if content_declarations.strip():
        parts.append("CONTENIDO YA ESCRITO (tu pregunta debe basarse en esto)")
        parts.append(content_declarations)
    else:
        parts.append(
            "CONTENIDO: aun no escrito (se genera en paralelo). Basa la pregunta "
            "en el resumen del nodo y la fuente."
        )

    if source_context.strip():
        parts.append("")
        parts.append("FUENTE ORIGINAL (para verificar que la respuesta es correcta)")
        parts.append(clip_source(source_context, limit=3000))

    parts.append("")
    parts.append("Escribe las declaraciones y la clave de respuestas. Nada mas.")
    return "\n".join(parts)


# ── response parsing ──────────────────────────────────────────────────────────


def _parse_interaction_response(raw: str) -> InteractionOutput:
    """Split the raw LLM response into declarations and answer key."""
    if ANSWER_KEY_SENTINEL not in raw:
        return InteractionOutput(declarations=raw.strip(), answer_key={})

    program, _, tail = raw.partition(ANSWER_KEY_SENTINEL)
    try:
        answer_key = parse_json_response(tail)
    except Exception:
        answer_key = {}

    if not isinstance(answer_key, dict):
        answer_key = {}

    return InteractionOutput(declarations=program.strip(), answer_key=answer_key)


# ── main entry point ──────────────────────────────────────────────────────────


async def run_interaction_designer(
    *,
    blueprint: Blueprint,
    content_declarations: str,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    target_bloom: str,
    scaffold_band: str,
    llm: Any,
) -> InteractionOutput:
    """Run the Interaction Designer agent.

    Creates QuizItem and DragOrder declarations plus their answer key from the
    blueprint and source context.  Returns an empty ``InteractionOutput`` when
    the blueprint has no interaction blocks.
    """
    user_prompt = build_interaction_prompt(
        blueprint=blueprint,
        content_declarations=content_declarations,
        title=title,
        summary=summary,
        source_context=source_context,
        role_title=role_title,
        sector=sector,
        target_bloom=target_bloom,
        scaffold_band=scaffold_band,
    )

    if not user_prompt:
        logger.debug("interaction_designer: no interaction blocks in blueprint, skipping")
        return InteractionOutput(declarations="", answer_key={})

    system = interaction_designer_system()
    raw, _usage = await llm.complete_with_usage(
        system, user_prompt, temperature=0.3, max_tokens=600
    )

    result = _parse_interaction_response(raw)
    logger.debug(
        "interaction_designer: %d chars declarations, %d answer_key entries",
        len(result.declarations),
        len(result.answer_key),
    )
    return result
