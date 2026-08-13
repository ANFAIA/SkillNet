"""Cómo se EXPLICA un nodo, decidido de forma determinista antes de gastar un token.

Por qué existe este módulo
==========================

``assessment.py`` ya fija el cierre. El hueco que quedaba suelto era el **concepto**:
el generador inventaba una definición en prosa y luego preguntaba la misma frase.
Eso no es un fallo de redacción; es que la didáctica de la pantalla no estaba
planeada. Este módulo es el gemelo de la evaluación para la enseñanza: lee la
forma del material y el plan de verificación, y devuelve el esquema de la
pantalla — lead, concepto, práctica — estable por nodo.

Qué NO hace
===========

* **No escribe el contenido.** Solo nombra los tres huecos y el bloque de cada uno.
  El LLM rellena filas, pasos o cifras; no elige la forma.
* **No persiste el esquema en el nodo.** Se deriva de la fuente y del closer, igual
  que ``shape_hints``. El día que el diseñador lo fije a mano, este plan es el
  valor por defecto.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.runtime.assessment import AssessmentPlan
from src.agents.runtime.shape import ShapePlan

#: Bloques que pueden ocupar el hueco de concepto. TextContent no está: el
#: concepto es material (filas, pasos, barras, bien/mal), no una definición.
CONCEPT_BLOCKS = frozenset({"Table", "Chart", "StepSequence", "BeforeAfter"})

_CONCEPT_FILL = {
    "Table": "filas de un caso o lista del puesto, no un parrafo que define el titulo",
    "Chart": "cifras de la fuente, sin inventar ninguna",
    "StepSequence": "pasos concretos del procedimiento, en orden",
    "BeforeAfter": "un estado mal y el mismo bien, del puesto",
}

_KIND_TO_CONCEPT = {
    "enumeration": "Table",
    "labelled_list": "Table",
    "procedure": "StepSequence",
    "numeric_series": "Chart",
    "contrast": "BeforeAfter",
    "variants": "Table",
    "explore": "Table",
}


@dataclass(frozen=True)
class ScreenScheme:
    """Los tres huecos de la pantalla, ya decididos para este nodo."""

    concept_block: str
    practice_block: str
    practice_item_type: str | None = None

    def instruction(self) -> str:
        """El bloque de prompt: nombra los huecos. El modelo solo rellena."""
        fill = _CONCEPT_FILL.get(self.concept_block, "el material de este nodo")
        practice = self.practice_block
        if self.practice_item_type:
            practice = f"{self.practice_block} ({self.practice_item_type})"
        return (
            "ESQUEMA DE ESTA PANTALLA (ya decidido para este nodo)\n"
            "1. lead = TextContent(..., \"lead\") — una situacion del puesto\n"
            f"2. concepto = {self.concept_block}(...) — {fill}\n"
            f"3. practica = {practice} — otro encargo del puesto, distinto del lead\n"
            "Rellena estos tres huecos. El concepto no es una definicion."
        )


def plan_screen_scheme(
    plan: ShapePlan | None,
    assessment: AssessmentPlan,
    *,
    ui_format: str,
) -> ScreenScheme:
    """El esquema didáctico de un nodo.

    * La **forma del material** elige el concepto (lista → Table, pasos →
      StepSequence, cifras → Chart, bien/mal → BeforeAfter).
    * Un nodo ``chart`` con cifras usa Chart; sin cifras no inventa ejes.
    * Sin forma detectada, el closer procedimental pide StepSequence; el resto,
      Table (un caso con filas). Nunca un párrafo de definición.
    * La **práctica** es el closer que ya decidió ``assessment.py``.
    """
    return ScreenScheme(
        concept_block=_concept_block(plan, assessment, ui_format),
        practice_block=assessment.block,
        practice_item_type=assessment.item_type,
    )


def _concept_block(
    plan: ShapePlan | None,
    assessment: AssessmentPlan,
    ui_format: str,
) -> str:
    if ui_format == "chart" and (plan is None or plan.has_numbers):
        return "Chart"
    if plan is not None:
        for signal in plan.signals:
            mapped = _KIND_TO_CONCEPT.get(signal.kind)
            if mapped in CONCEPT_BLOCKS:
                if ui_format == "chart" and signal.chart_block in CONCEPT_BLOCKS:
                    return signal.chart_block
                return mapped
            if signal.block in CONCEPT_BLOCKS:
                return signal.block
    if _is_procedure_closer(assessment) and ui_format != "chart":
        return "StepSequence"
    return "Table"


def _is_procedure_closer(assessment: AssessmentPlan) -> bool:
    if assessment.block == "DragOrder":
        return True
    return assessment.item_type == "didact.sort"


__all__ = [
    "CONCEPT_BLOCKS",
    "ScreenScheme",
    "plan_screen_scheme",
]
