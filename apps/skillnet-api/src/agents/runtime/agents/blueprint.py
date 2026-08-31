"""Blueprint Architect agent — decides screen structure without writing content.

Given the metadata of a learning node and the learner profile, this agent
produces a :class:`Blueprint`: a list of typed blocks with layout intent.
Content Writer and Interaction Designer fill those blocks later.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from src.core.language import Language
from src.core.logging import get_logger
from src.llm.prompts.language import with_language
from src.llm.parsing import parse_json_response

from src.agents.runtime.assessment import AssessmentPlan
from src.agents.runtime.screen_scheme import ScreenScheme
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
- BeforeAfter: comparacion visual de correcto vs incorrecto, antes vs despues.
- StepSequence: procedimiento corto de 3-7 pasos sin explicaciones largas.
- Chart: datos numericos comparables. Solo si hay cifras en la fuente.
- Callout: aviso critico o excepcion importante. Solo uno por pantalla.

Elige el bloque de CONCEPTO por la forma del contenido:
- Contrasta lo correcto con lo incorrecto, o un antes con un despues -> BeforeAfter
- Varios elementos comparados por varios atributos -> Table
- Pasos en orden que se entienden solos -> StepSequence

## Componentes para el slot VERIFICAR

- QuizItem: pregunta sobre un CASO CONCRETO. Indica item_type y bloom. El item_type NO es
  siempre "test"; elige segun lo que se evalua:
    - "test": 4 opciones, aplicar una regla a un caso.
    - "true_false": juzgar si una afirmacion es verdadera o falsa.
    - "fill_blank": recordar un termino o cifra clave rellenando un hueco.
- DragOrder: ordenar los pasos de un procedimiento arrastrando.

Elige el tipo de verificacion segun el concepto:
- Si el concepto es un procedimiento (StepSequence) -> DragOrder
- Si hay que recordar un dato o termino exacto -> QuizItem "fill_blank"
- Si hay que juzgar una regla como cierta o falsa -> QuizItem "true_false"
- Si hay que aplicar una regla a una situacion -> QuizItem "test"

## Estructura de la pantalla (4-6 bloques)

Cada bloque se muestra en su propia pantalla. Mas bloques = mas pantallas = experiencia
mas completa. MINIMO 4 bloques, idealmente 5-6.

1. ENGANCHAR — TextContent "lead". UNA SOLA FRASE: dato curioso, situacion real o reto.
   PROHIBIDO "Este nodo cubre...", "Se exploraran...", "En esta seccion...".
2. CONCEPTO — Uno o DOS bloques de contenido. Si el tema tiene varias facetas, usa dos
   bloques de concepto (ej: una Table + una StepSequence, o un BeforeAfter + un Callout).
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
- Card es el unico contenedor: agrupa un caso practico cerrado bajo su titulo. Nada
  de esconder contenido detras de un clic — el aprendiz no lee lo que no pulsa.
- El campo "note" es una instruccion breve para el agente que rellene el contenido.
- SOLO ESTRUCTURA. Cada bloque lleva UNICAMENTE id, type, intent y sus atributos
  ("variant", "columns", "item_type", "bloom", "note"). PROHIBIDO escribir el contenido
  real: nada de campos "text", "before", "after", "rows", "options" ni frases largas. El
  contenido lo escribe otro agente. Un JSON largo es un JSON mal hecho: manten cada bloque
  en una linea corta.\
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
    siblings: Sequence[str] = (),
    assessment_hint: str = "",
    presentation_preference: str = "balanced",
    detail_preference: str = "standard",
    image_preference: str = "when_useful",
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
    presentation_rules = {
        "balanced": "Combina representaciones segun el objetivo y la fuente.",
        "visual": "Prioriza estructura visual cuando aclare la fuente.",
        "textual": "Prioriza texto estructurado y tablas cuando sean suficientes.",
        "interactive": "Prioriza practica e interaccion cuando el catalogo lo permita.",
    }
    detail_rules = {
        "concise": "Estructura una pantalla concisa.",
        "standard": "Usa un nivel de detalle equilibrado.",
        "detailed": "Permite mas detalle, sin inventar contenido.",
    }
    image_rules = {
        "when_useful": "Imagenes solo si aportan valor y estan disponibles.",
        "prefer": "Prefiere imagenes utiles disponibles; no las inventes.",
        "avoid": "No solicites ni incluyas imagenes.",
    }
    lines.append(f"- {presentation_rules.get(presentation_preference, presentation_rules['balanced'])}")
    lines.append(f"- {detail_rules.get(detail_preference, detail_rules['standard'])}")
    lines.append(f"- {image_rules.get(image_preference, image_rules['when_useful'])}")
    lines.append("- Son preferencias: la evidencia, seguridad y objetivo mandan.")

    if shape_hints:
        lines.append("")
        lines.append("FORMA DEL MATERIAL (leido de la fuente)")
        for hint in shape_hints:
            lines.append(f"- {hint}")

    if assessment_hint.strip():
        # El bloque de cierre lo fija el planificador (assessment.py); el blueprint tiene
        # que estructurar la pantalla en consecuencia (p.ej. una StepSequence si el cierre
        # es un DragOrder). Ademas se impone despues por si el LLM no lo respeta.
        lines.append("")
        lines.append("CÓMO CIERRA LA PANTALLA (el bloque VERIFICAR ya esta decidido)")
        lines.append(f"- {assessment_hint.strip()}")

    if siblings:
        lines.append("")
        lines.append("OTRAS PANTALLAS DEL CURSO (ya cubren esto: NO lo repitas)")
        lines.extend(f"- {sibling}" for sibling in siblings)
        lines.append(
            "Tu pantalla cubre UNICAMENTE su propio titulo. El resto del manual es "
            "contexto que ya tiene otra pantalla; no lo resumas ni lo introduzcas."
        )

    lines.append("")
    lines.append("Responde solo con el JSON.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default blueprint (fallback when LLM fails)
# ---------------------------------------------------------------------------

def default_blueprint(
    ui_format: str,
    shape_hints: Sequence[str],
    scheme: ScreenScheme | None = None,
) -> Blueprint:
    if scheme is not None:
        return blueprint_from_scheme(scheme, ui_format)
    blocks: list[BlueprintBlock] = [
        BlueprintBlock(id="intro", type="TextContent", intent="enganchar", variant="lead"),
    ]
    if any("Table" in h for h in shape_hints):
        blocks.append(BlueprintBlock(id="concepto", type="Table", intent="concepto", columns=2))
    elif any("StepSequence" in h for h in shape_hints):
        # StepSequence, no StepByStepReveal: este ultimo no existe en el kit y el validador
        # lo rechazaria como componente desconocido, tirando el nodo al fallback.
        blocks.append(BlueprintBlock(id="concepto", type="StepSequence", intent="concepto"))
    else:
        blocks.append(BlueprintBlock(id="concepto", type="Table", intent="concepto", columns=1))

    if ui_format in ("exercise", "mixed"):
        blocks.append(BlueprintBlock(id="q1", type="QuizItem", intent="verificar", item_type="test", bloom="apply"))
    else:
        blocks.append(BlueprintBlock(id="q1", type="QuizItem", intent="verificar", item_type="test", bloom="understand"))

    return Blueprint(blocks=blocks)


def blueprint_from_scheme(
    scheme: ScreenScheme,
    ui_format: str,
    target_bloom: str = "understand",
) -> Blueprint:
    """The planned slots, not an invented structure."""

    bloom = "apply" if ui_format in ("exercise", "mixed") else target_bloom
    concept_kwargs: dict[str, Any] = {
        "id": "concepto",
        "type": scheme.concept_block,
        "intent": "concepto",
    }
    if scheme.concept_block == "Table":
        concept_kwargs["columns"] = 2
    if scheme.practice_block == "DragOrder":
        practice = BlueprintBlock(
            id="ejercicio", type="DragOrder", intent="verificar", bloom=bloom
        )
    elif scheme.practice_block == "QuizItem":
        practice = BlueprintBlock(
            id="q1",
            type="QuizItem",
            intent="verificar",
            item_type=scheme.practice_item_type or "test",
            bloom=bloom,
        )
    else:
        practice = BlueprintBlock(
            id="practica",
            type=scheme.practice_block,
            intent="verificar",
            item_type=scheme.practice_item_type,
        )
    return Blueprint(
        blocks=[
            BlueprintBlock(
                id="intro", type="TextContent", intent="enganchar", variant="lead"
            ),
            BlueprintBlock(**concept_kwargs),
            practice,
        ]
    )


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
    siblings: Sequence[str] = (),
    assessment: AssessmentPlan | None = None,
    scheme: ScreenScheme | None = None,
    presentation_preference: str = "balanced",
    detail_preference: str = "standard",
    image_preference: str = "when_useful",
    language: Language | None = None,
) -> Blueprint:
    """Return the screen structure. A planned scheme is the structure; no LLM invents it.

    ``language`` reaches this agent even though it writes no prose: the blueprint's
    ``intent`` and block choices are enum-shaped, but the model also echoes the node's
    title and summary into the JSON it returns, and a Spanish system prompt is what
    decides which language those come back in.
    """

    if scheme is not None:
        return blueprint_from_scheme(scheme, ui_format, target_bloom)

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
        siblings=siblings,
        assessment_hint=assessment.instruction() if assessment else "",
        presentation_preference=presentation_preference,
        detail_preference=detail_preference,
        image_preference=image_preference,
    )

    raw, _usage = await llm.complete_with_usage(
        with_language(BLUEPRINT_SYSTEM, language),
        user_prompt,
        temperature=0.2,
        # 512 truncaba el JSON cuando el modelo colaba contenido en los bloques (medido
        # en el nodo de alergenos: BeforeAfter con "before"/"after" enteros, cortado a
        # media frase -> JSON invalido -> default_blueprint, que colapsa a una Table
        # generica). 768 da margen; el prompt ya prohibe el contenido, esto es la red.
        max_tokens=768,
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
            blueprint = default_blueprint(ui_format, shape_hints, scheme)

    # --- Post-validation: ensure a verification block exists ---------------
    blueprint = _ensure_verification(blueprint, ui_format, target_bloom)
    # Impone el plan de evaluacion sin importar lo que el LLM decidiera: es lo que
    # garantiza la variedad en vez de dejarla al capricho del modelo.
    if assessment is not None:
        blueprint = _apply_assessment(blueprint, assessment, target_bloom, ui_format)
    return blueprint


def _apply_assessment(
    blueprint: Blueprint,
    assessment: AssessmentPlan,
    target_bloom: str,
    ui_format: str,
) -> Blueprint:
    """Force the closing verification block to match the deterministic plan.

    Rewrites the LAST QuizItem/DragOrder block to the planned type. ``_ensure_verification``
    guarantees at least one exists, so the ``else`` branch only fires defensively.

    Una regla de contenido por encima del plan: si la pantalla explica un PROCEDIMIENTO
    (el blueprint eligio una StepSequence) se verifica ordenandolo con ``DragOrder``, aunque
    el detector de ``shape.py`` no marcase el procedimiento en la fuente. Es lo que hace que
    un nodo procedimental sea interactivo de verdad en vez de una pregunta mas.
    """
    blocks = list(blueprint.blocks)
    has_step_sequence = any(b.type == "StepSequence" for b in blocks)
    if has_step_sequence and ui_format != "chart":
        assessment = AssessmentPlan(block="DragOrder", item_type=None)
    idx = next(
        (
            i
            for i in range(len(blocks) - 1, -1, -1)
            if blocks[i].type in ("QuizItem", "DragOrder")
        ),
        None,
    )
    if assessment.block == "DragOrder":
        new_block = BlueprintBlock(
            id=blocks[idx].id if idx is not None else "ejercicio",
            type="DragOrder",
            intent="verificar",
            bloom=(blocks[idx].bloom if idx is not None else None) or target_bloom,
        )
    else:
        new_block = BlueprintBlock(
            id=blocks[idx].id if idx is not None else "q1",
            type="QuizItem",
            intent="verificar",
            item_type=assessment.item_type or "test",
            bloom=(blocks[idx].bloom if idx is not None else None) or target_bloom,
        )
    if idx is not None:
        blocks[idx] = new_block
    else:
        blocks.append(new_block)
    return Blueprint(blocks=blocks)


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
