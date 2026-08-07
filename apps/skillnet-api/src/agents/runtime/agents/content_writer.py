"""Content Writer agent — writes educational CONTENT blocks in OpenUI Lang."""

from __future__ import annotations

from functools import cache
from typing import Any

from src.agents.runtime.agents.types import (
    Blueprint,
    ContentOutput,
    criticality_rule,
    scaffold_rule,
)
from src.core.logging import get_logger
from src.llm.prompts.runtime import clip_source
from src.render.prompt import render_prompt

logger = get_logger(__name__)

# ── System prompt (cached) ──────────────────────────────────────────────


@cache
def content_writer_system() -> str:
    return (
        render_prompt().rstrip("\n")
        + """

## SkillNet Content Writer: tu tarea especifica

Escribes los bloques de CONTENIDO en dialecto OpenUI Lang. Recibes un blueprint y una fuente.

Lo que SI haces:
- Escribir TextContent, Table, StepByStepReveal, StepSequence, Callout, BeforeAfter,
  Chart, CodeBlock.
- Una declaracion por linea: id = Componente(args...)
- Usar los ids EXACTOS del blueprint.

Lo que NO haces:
- NO escribir QuizItem ni DragOrder (otro agente).
- NO escribir root = Stack(...).
- NO escribir ---ANSWER-KEY---.
- NO prosa antes ni despues.
- NO usar Tabs, TabItem, Card, Accordion ni AccordionItem.

## EL LEAD (TextContent "lead") — la frase que engancha

UNA SOLA FRASE que haga al aprendiz querer saber mas:
- Un dato sorprendente: "En UFC 1 no habia categorias de peso ni rounds."
- Una situacion real: "Tu primer dia en cocina y alguien te pregunta si el plato lleva gluten."
- Un reto: "Catorce alergenos obligatorios. Sabrias nombrar la mitad?"

PROHIBIDO:
- "Este nodo cubre...", "En esta seccion...", "Se exploraran..."
- Copiar o resumir el resumen del nodo. El resumen es PARA TI, no para el aprendiz.
- Mas de dos frases. Si no cabe en una linea, sobra.

## EL CONCEPTO — el componente que ENSENA

El componente central no es decoracion: ES la leccion. Cada celda, paso o item tiene
contenido ESPECIFICO y SUSTANCIAL.

Table: cada fila aporta un dato concreto y diferente.
  MAL:  Table(["Tecnica"], [["Diversas tecnicas de golpeo"]])
  BIEN: Table(["Tecnica", "Origen", "Ejemplo"], [["Jab", "Boxeo", "Golpe recto con la mano adelantada"], ["Low kick", "Muay Thai", "Patada al muslo exterior"]])

StepByStepReveal: cada paso tiene titulo + explicacion practica.
  MAL:  StepByStepReveal("Pasos", [["Paso 1", "Hacer lo primero"]])
  BIEN: StepByStepReveal("Regla PAS del extintor", [["P - Quitar el pasador", "Tira de la anilla metalica con un gesto seco hacia fuera."], ["A - Apuntar a la base", "A 2-3 metros, apunta a la BASE del fuego, nunca a las llamas."]])

BeforeAfter: los dos lados son CONCRETOS, no genericos.
  MAL:  BeforeAfter("Comparacion", "Mal", "Hacerlo mal", "Bien", "Hacerlo bien")
  BIEN: BeforeAfter("Guardia de boxeo", "MAL", "Manos bajas, menton expuesto, pies juntos.", "BIEN", "Manos a la altura de la sien, menton pegado al pecho, pies al ancho de hombros.")

Ejemplo completo de salida para un blueprint con [intro, tabla, aviso]:
intro = TextContent("Catorce alergenos, uno solo que se cuele y el cliente acaba en urgencias.", "lead")
tabla = Table(["Alergeno", "Donde aparece"], [["Cereales con gluten", "Masa de pizza, empanado"], ["Crustaceos", "Paella, gambas al ajillo"], ["Huevos", "Tortilla, rebozados, mayonesa"], ["Leche", "Bechamel, postres, helados"]])
aviso = Callout("warn", "Si el cliente pregunta y no estas seguro, consulta la ficha tecnica antes de responder. Nunca digas 'creo que no lleva'.")

Si no hay fuente, limitate a lo que dice el resumen del nodo. No inventes cifras, plazos,
nombres de norma ni datos que no esten en el resumen. Se concreto con lo que TIENES, no
inventes lo que no tienes.

Reglas del dialecto: las de arriba, sin excepciones.
- SkillNet 14: ids en ASCII sin tildes.
- SkillNet 15: una lista de N cosas es UN bloque (Table o StepSequence), no N bloques
  separados ni N elementos separados por comas dentro de un TextContent.
- SkillNet 16: Callout solo "info", "warn" o "success".
- SkillNet 17: a la derecha del = va siempre una llamada a bloque.

Responde SOLO con las declaraciones, una por linea. Nada mas.
"""
    )


# ── User prompt builder ─────────────────────────────────────────────────


def build_content_prompt(
    *,
    blueprint: Blueprint,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    scaffold_band: str,
    criticality: str,
) -> str:
    content_blocks = [
        b for b in blueprint.blocks if b.type not in ("QuizItem", "DragOrder")
    ]

    # Blueprint section
    lines: list[str] = ["BLUEPRINT (escribe SOLO estos bloques, con estos ids exactos)"]
    for b in content_blocks:
        parts = [f"intent={b.intent}"]
        if b.variant is not None:
            parts.append(f"variant={b.variant}")
        if b.columns is not None:
            parts.append(f"columns={b.columns}")
        if b.note is not None:
            parts.append(f"nota={b.note}")
        lines.append(f"- {b.id}: {b.type} ({', '.join(parts)})")

    lines.append("")
    lines.append(f"NODO: {title}")
    lines.append(f"RESUMEN: {summary}")

    lines.append(f"- {criticality_rule(criticality)}")
    lines.append(f"- {scaffold_rule(scaffold_band)}")

    if role_title:
        lines.append(
            f"- Los ejemplos son situaciones de un/una {role_title} del sector {sector}."
        )

    lines.append("")
    clipped = clip_source(source_context.strip()) if source_context.strip() else ""
    if clipped:
        lines.append("FUENTE (es la unica verdad; no anadas datos que no esten aqui)")
        lines.append(clipped)
    else:
        lines.append("NO HAY FUENTE. Limitate al resumen del nodo.")

    lines.append("")
    lines.append("Escribe las declaraciones, una por linea. Nada mas.")
    return "\n".join(lines)


# ── Agent entry point ────────────────────────────────────────────────────


async def run_content_writer(
    *,
    blueprint: Blueprint,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    scaffold_band: str,
    criticality: str,
    llm: Any,
) -> ContentOutput:
    """Generate OpenUI Lang declarations for content blocks."""

    content_blocks = [
        b for b in blueprint.blocks if b.type not in ("QuizItem", "DragOrder")
    ]
    if not content_blocks:
        logger.debug("content_writer: no content blocks in blueprint — returning empty")
        return ContentOutput(declarations="")

    system = content_writer_system()
    user = build_content_prompt(
        blueprint=blueprint,
        title=title,
        summary=summary,
        source_context=source_context,
        role_title=role_title,
        sector=sector,
        scaffold_band=scaffold_band,
        criticality=criticality,
    )

    logger.debug("content_writer: calling LLM (%d content blocks)", len(content_blocks))
    text, usage = await llm.complete_with_usage(
        system, user, temperature=0.4, max_tokens=1600
    )
    logger.debug("content_writer: done — %s", usage)

    return ContentOutput(declarations=text)
