"""Blueprint Architect agent — decides screen structure without writing content.

Given the metadata of a learning node and the learner profile, this agent
produces a :class:`Blueprint`: a list of typed blocks with layout intent.
Content Writer and Interaction Designer fill those blocks later.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from src.core.logging import get_logger
from src.llm.parsing import parse_json_response

from src.agents.runtime.agents.types import (
    Blueprint,
    BlueprintBlock,
    criticality_rule,
    density_budget,
    scaffold_rule,
)

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

BLUEPRINT_SYSTEM = """\
Eres el arquitecto de pantallas de SkillNet. Decides la ESTRUCTURA de una pantalla de
aprendizaje. NO escribes contenido ni preguntas. Solo la forma.

Responde UNICAMENTE con JSON valido, sin texto antes ni despues:

{"blocks": [
  {"id": "<id_ascii>", "type": "<componente>", "intent": "<enganchar|concepto|verificar|refuerzo>", ...},
  ...
]}

## Filosofia: el componente interactivo ES la leccion

El aprendiz aprende HACIENDO, no leyendo. El componente central de la pantalla no es
decoracion: es la herramienta de aprendizaje. Una Table muestra datos reales que el
aprendiz necesita memorizar. Un BeforeAfter ensena la diferencia entre hacerlo bien y
hacerlo mal. Un StepByStepReveal guia un procedimiento paso a paso. Un DragOrder obliga
a reconstruir un proceso de memoria.

REGLA: el bloque de CONCEPTO siempre es interactivo o estructurado, NUNCA prosa.

## Componentes para el slot CONCEPTO (elige segun el material)

- Table: datos, listas, comparativas, propiedades. Indica columns: 1 o 2.
- StepByStepReveal: procedimiento con explicacion paso a paso. El aprendiz abre cada paso.
- BeforeAfter: comparacion visual de correcto vs incorrecto, antes vs despues.
- StepSequence: procedimiento corto de 3-7 pasos sin explicaciones largas.
- Chart: datos numericos comparables. Solo si hay cifras en la fuente.
- Callout: aviso critico o excepcion importante. Solo uno por pantalla.

## Componentes para el slot VERIFICAR

- QuizItem: pregunta con 4 opciones sobre un CASO CONCRETO. Indica item_type y bloom.
- DragOrder: ordenar pasos o prioridades arrastrando.

Elige el tipo de verificacion segun el concepto:
- Si el concepto es un procedimiento (StepSequence/StepByStepReveal) -> DragOrder
- Si el concepto tiene un bien/mal o antes/despues -> BeforeAfter
- En los demas casos -> QuizItem

## Estructura de la pantalla (4-6 bloques)

Cada bloque se muestra en su propia pantalla. Mas bloques = mas pantallas = experiencia
mas completa. MINIMO 4 bloques, idealmente 5-6.

1. ENGANCHAR — TextContent "lead". UNA SOLA FRASE: dato curioso, situacion real o reto.
   PROHIBIDO "Este nodo cubre...", "Se exploraran...", "En esta seccion...".
2. CONCEPTO — Uno o DOS bloques de contenido. Si el tema tiene varias facetas, usa dos
   bloques de concepto (ej: una Table + un StepByStepReveal, o un BeforeAfter + un Callout).
3. REFUERZO (opcional) — Callout con dato clave, o un segundo bloque de concepto.
4. VERIFICAR — OBLIGATORIO, SIEMPRE EL ULTIMO BLOQUE. QuizItem o DragOrder.
   El ejercicio cierra la pantalla. Nada va despues del ejercicio.
   TODOS los nodos DEBEN tener exactamente UN bloque QuizItem o DragOrder al final.
   Sin excepcion. Un nodo sin ejercicio no evalua nada.

## Reglas duras

- Los ids son ASCII sin tildes: "intro", "tabla", "q1".
- Cada id es unico.
- El primer bloque siempre es TextContent con variant "lead".
- El ULTIMO bloque siempre es QuizItem o DragOrder. NO HAY EXCEPCIONES.
  Un JSON sin un bloque de intent "verificar" al final es INVALIDO y sera rechazado.
- Tabs, Card y Accordion son contenedores: uselos SOLO cuando agrupan de verdad.
  Card para un caso practico cerrado. Tabs para 2-3 variantes del mismo procedimiento
  (por turno, por tipo de cliente). Accordion para excepciones que no todo el mundo
  necesita leer. Si no agrupan nada, no los pongas: esconden contenido tras un clic.
- El campo "note" es una instruccion breve para el agente que rellene el contenido.\
"""

# ---------------------------------------------------------------------------
# User prompt
# ---------------------------------------------------------------------------

def build_blueprint_prompt(
    *,
    title: str,
    summary: str,
    outcome: str | None,
    criticality: str,
    ui_format: str,
    effective_density: int,
    scaffold_band: str,
    role_title: str | None,
    sector: str | None,
    experience_level: str,
    target_bloom: str,
    shape_hints: Sequence[str],
) -> str:
    lines: list[str] = [
        f"FORMATO: {ui_format}",
        "",
        "NODO",
        f"- Titulo: {title}",
        f"- Resumen: {summary}",
    ]
    if outcome is not None:
        lines.append(f"- Resultado esperado: {outcome}")
    lines.append(f"- {criticality_rule(criticality)}")
    lines.append("")

    lines.append("APRENDIZ")
    lines.append(f"- Puesto: {role_title or 'sin declarar'}")
    lines.append(f"- Sector: {sector or 'sin declarar'}")
    lines.append(f"- Experiencia: {experience_level}")
    lines.append(f"- Nivel cognitivo objetivo: {target_bloom}")
    lines.append(f"- Presupuesto: {density_budget(effective_density)}")
    lines.append(f"- {scaffold_rule(scaffold_band)}")

    if shape_hints:
        lines.append("")
        lines.append("FORMA DEL MATERIAL (leido de la fuente)")
        for hint in shape_hints:
            lines.append(f"- {hint}")

    lines.append("")
    lines.append("Responde solo con el JSON.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default blueprint (fallback when LLM fails)
# ---------------------------------------------------------------------------

def default_blueprint(ui_format: str, shape_hints: Sequence[str]) -> Blueprint:
    blocks: list[BlueprintBlock] = [
        BlueprintBlock(id="intro", type="TextContent", intent="enganchar", variant="lead"),
    ]
    if any("Table" in h for h in shape_hints):
        blocks.append(BlueprintBlock(id="concepto", type="Table", intent="concepto", columns=2))
    elif any("StepSequence" in h or "StepByStepReveal" in h for h in shape_hints):
        blocks.append(BlueprintBlock(id="concepto", type="StepByStepReveal", intent="concepto"))
    else:
        blocks.append(BlueprintBlock(id="concepto", type="Table", intent="concepto", columns=1))

    if ui_format in ("exercise", "mixed"):
        blocks.append(BlueprintBlock(id="q1", type="QuizItem", intent="verificar", item_type="test", bloom="apply"))
    else:
        blocks.append(BlueprintBlock(id="q1", type="QuizItem", intent="verificar", item_type="test", bloom="understand"))

    return Blueprint(blocks=blocks)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def run_blueprint(
    *,
    title: str,
    summary: str,
    outcome: str | None,
    criticality: str,
    ui_format: str,
    effective_density: int,
    scaffold_band: str,
    role_title: str | None,
    sector: str | None,
    experience_level: str,
    target_bloom: str,
    shape_hints: Sequence[str],
    llm: Any,
) -> Blueprint:
    """Run the Blueprint Architect agent and return a screen structure."""

    user_prompt = build_blueprint_prompt(
        title=title,
        summary=summary,
        outcome=outcome,
        criticality=criticality,
        ui_format=ui_format,
        effective_density=effective_density,
        scaffold_band=scaffold_band,
        role_title=role_title,
        sector=sector,
        experience_level=experience_level,
        target_bloom=target_bloom,
        shape_hints=shape_hints,
    )

    raw, _usage = await llm.complete_with_usage(
        BLUEPRINT_SYSTEM,
        user_prompt,
        temperature=0.2,
        max_tokens=512,
        json_mode=True,
    )

    # --- Parse response ---------------------------------------------------
    blueprint = None
    try:
        blueprint = Blueprint.model_validate_json(raw)
    except (ValidationError, ValueError):
        try:
            data = parse_json_response(raw, context="blueprint")
            blueprint = Blueprint.model_validate(data)
        except Exception:
            log.warning("blueprint: LLM response unparseable, using default. raw=%s", raw[:300])
            blueprint = default_blueprint(ui_format, shape_hints)

    # --- Post-validation: ensure a verification block exists ---------------
    blueprint = _ensure_verification(blueprint, ui_format, target_bloom)
    return blueprint


def _ensure_verification(
    blueprint: Blueprint, ui_format: str, target_bloom: str
) -> Blueprint:
    """Append a QuizItem if the LLM omitted the mandatory verification block."""
    has_verification = any(
        b.type in ("QuizItem", "DragOrder") for b in blueprint.blocks
    )
    if has_verification:
        return blueprint
    log.warning("blueprint: no verification block, injecting QuizItem")
    bloom = "apply" if ui_format in ("exercise", "mixed") else "understand"
    blocks = list(blueprint.blocks) + [
        BlueprintBlock(
            id="q1", type="QuizItem", intent="verificar",
            item_type="test", bloom=target_bloom or bloom,
        ),
    ]
    return Blueprint(blocks=blocks)
