"""Cómo se VERIFICA un nodo, decidido de forma determinista antes de gastar un token.

Por qué existe este módulo
==========================

Medido el 2026-08-11 sobre la pila viva (multi-agente, ``gpt-4o-mini``): los seis nodos
de dos cursos distintos terminaban en el **mismo** ``QuizItem`` de tipo ``test``. El kit
ya sabe pintar cuatro interacciones distintas de extremo a extremo y con corrección
determinista —``test``, ``true_false``, ``fill_blank`` y ``DragOrder``— pero nada en el
pipeline convertía una propiedad del nodo en una elección de formato, así que el modelo
tomaba siempre la salida más barata: una pregunta de opción múltiple.

Este módulo es el gemelo de :mod:`src.agents.runtime.shape` para la evaluación: lee
propiedades del **nodo** (su forma y su id), no del aprendiz, y devuelve un plan estable.
Que sea del nodo es lo que lo hace compatible con la calibración de §6.4 —la interfaz no
se mueve bajo un aprendiz que aún construye su mapa mental— y estable por ``node_id`` es
lo que reparte la variedad entre los nodos hermanos de un curso sin volverla aleatoria.

Qué NO hace
===========

* **No usa ``practical_case`` ni ``dialogue``.** Su corrección depende de un LLM de
  evaluación (``LLM_EVAL_MODEL``, por defecto ``None``); sin él un caso abierto no se
  puede puntuar. El planificador se ciñe a los cuatro tipos que funcionan siempre. El
  prompt no los prohíbe, simplemente el plan determinista no los impone.
* **No inventa una ordenación.** ``DragOrder`` solo se propone cuando la forma del
  material ya trae un procedimiento con pasos que ordenar.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.agents.runtime.shape import ShapePlan

#: Los ``item_type`` de ``QuizItem`` que se corrigen de forma determinista (0.0/1.0) y que
#: el front pinta bien sin depender de ningún LLM de evaluación. El orden ES la rotación.
QUIZ_ROTATION: tuple[str, ...] = ("test", "true_false", "fill_blank")

#: Quiz-only subset, kept for tests and diagnostics. Live Didact uses the wider closer
#: list below: three quiz types modulo a UUID hash clustered a 6-node course onto
#: true/false four times.
DIDACT_QUIZ_ROTATION: tuple[str, ...] = (
    "didact.quiz.single-choice",
    "didact.quiz.true-false",
    "didact.quiz.fill-in-the-blank",
)
DIDACT_PROCEDURE = "didact.sort"

#: The ASSESSMENT rotation. Every entry is a REAL, varied check the learner acts on —
#: matching, categorize, single-choice, word-bank, fill-in-the-blank, sort — materialized as
#: a server-scored ``DidactActivity``. This is the node's TEST, so it is never a content
#: block. ``Flashcard`` was removed on 2026-08-17: it is a CONTENT resource (active-recall
#: aid on a teaching screen), not the test — using it as the closer made every node's
#: "assessment" a reveal, which is exactly what the owner banned. Reveal-only blocks
#: (``DidactWorkedExample`` progressive, ``HintReveal``) were already banned for the same
#: reason. When no ``DidactActivity`` can be materialized the fallback is a real ``QuizItem``
#: variant (see ``nodes._didact_activity_fallback_block``), never a Flashcard.
DIDACT_CLOSER_ROTATION: tuple[tuple[str | None, str], ...] = (
    ("didact.matching", "DidactActivity"),
    ("didact.categorize", "DidactActivity"),
    ("didact.quiz.single-choice", "DidactActivity"),
    ("didact.word-bank", "DidactActivity"),
    ("didact.quiz.fill-in-the-blank", "DidactActivity"),
    ("didact.sort", "DidactActivity"),
)
DIRECT_DIDACT_BLOCKS = frozenset(
    block for _type_id, block in DIDACT_CLOSER_ROTATION if block != "DidactActivity"
)


@dataclass(frozen=True)
class AssessmentPlan:
    """El bloque de verificación que cierra la pantalla, y su tipo si es un ``QuizItem``."""

    #: ``"QuizItem"`` | ``"DragOrder"`` | ``"DidactActivity"``.
    block: str
    #: Quiz ``item_type``, or a ``didact.*`` id when ``block == "DidactActivity"``.
    item_type: str | None

    @property
    def is_quiz(self) -> bool:
        return self.block == "QuizItem"

    def instruction(self) -> str:
        """La línea de prompt: nombra el bloque y cómo escribirlo, sin ambigüedad."""
        if self.block == "DidactActivity":
            component_id = self.item_type or "didact.quiz.single-choice"
            return (
                f"VERIFICA con DidactActivity usando component_id {component_id!r}. "
                "Si el servidor ya preparó una actividad, usa exactamente esos "
                "activity_id y component_id. El concepto ensena con un caso o "
                "una grafica; la actividad es otro encargo del puesto."
            )
        if self.block in DIRECT_DIDACT_BLOCKS:
            return (
                f"VERIFICA con {self.block}. El concepto ensena con un caso o "
                f"una grafica; {self.block} es otro encargo del puesto."
            )
        if self.block == "DragOrder":
            return (
                "VERIFICA con un bloque DragOrder: el aprendiz ordena arrastrando los "
                "pasos del procedimiento. 4-6 elementos, acciones concretas, y el tercer "
                "argumento es el orden correcto."
            )
        if self.item_type == "true_false":
            return (
                "VERIFICA con un QuizItem de item_type \"true_false\": una afirmación "
                "concreta sobre la fuente que sea verdadera o falsa de forma inequívoca. "
                "Las opciones son [] y la clave lleva {\"correct\": true|false}."
            )
        if self.item_type == "fill_blank":
            return (
                "VERIFICA con un QuizItem de item_type \"fill_blank\": una frase con UN "
                "solo hueco escrito como ____ que el aprendiz rellena con un término o "
                "cifra clave de la fuente. La clave lleva {\"blanks\": [\"<texto exacto>\"]}."
            )
        return (
            "VERIFICA con un QuizItem de item_type \"test\": 4 opciones sobre un CASO "
            "concreto del puesto, con distractores que son errores reales. La clave lleva "
            "{\"correct\": <índice 0-based>}."
        )


def _node_seed(node_id: str) -> int:
    """Entero estable y bien repartido a partir del ``node_id``.

    Estable: la misma pantalla en cada visita (no se mueve bajo el aprendiz). El hash
    solo se usa cuando no hay ``position`` de curso; dentro de un curso la rotación va
    por posición para que nodos hermanos no colisionen en el mismo closer.
    """
    digest = hashlib.sha1(str(node_id).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _closer_index(
    *,
    node_id: str,
    course_id: str = "",
    position: int | None = None,
    size: int,
) -> int:
    """Spread consecutive nodes; salt by course so every syllabus does not start alike."""

    if size <= 0:
        return 0
    if position is not None and int(position) > 0:
        salt = _node_seed(course_id) if course_id else 0
        return (int(position) - 1 + salt) % size
    return _node_seed(node_id) % size


def _has_procedure(plan: ShapePlan | None) -> bool:
    if plan is None:
        return False
    return any(signal.kind == "procedure" for signal in plan.signals)


def plan_assessment(
    plan: ShapePlan | None,
    *,
    ui_format: str,
    node_id: str,
    didact: bool = False,
    course_id: str = "",
    position: int | None = None,
) -> AssessmentPlan:
    """El plan de verificación de un nodo.

    * Un **procedimiento** se verifica ordenándolo → ``DragOrder`` / ``didact.sort``
      (salvo en ``chart``, donde la pantalla es una cifra y ordenar pasos no viene a cuento).
    * En cualquier otro caso, rota de forma determinista. Con ``position`` de curso, los
      nodos hermanos recorren la rueda; el ``course_id`` solo desplaza el origen.
    * Con ``didact=True`` (shortlist live) la rueda recorre familias Didact, no QuizItem.
    """
    index_kwargs = {
        "node_id": node_id,
        "course_id": course_id,
        "position": position,
    }
    if didact:
        if _has_procedure(plan) and ui_format != "chart":
            return AssessmentPlan(block="DidactActivity", item_type=DIDACT_PROCEDURE)
        component_id, block = DIDACT_CLOSER_ROTATION[
            _closer_index(**index_kwargs, size=len(DIDACT_CLOSER_ROTATION))
        ]
        return AssessmentPlan(block=block, item_type=component_id)
    if _has_procedure(plan) and ui_format != "chart":
        return AssessmentPlan(block="DragOrder", item_type=None)
    item_type = QUIZ_ROTATION[
        _closer_index(**index_kwargs, size=len(QUIZ_ROTATION))
    ]
    return AssessmentPlan(block="QuizItem", item_type=item_type)


__all__ = [
    "DIDACT_CLOSER_ROTATION",
    "DIDACT_PROCEDURE",
    "DIDACT_QUIZ_ROTATION",
    "DIRECT_DIDACT_BLOCKS",
    "QUIZ_ROTATION",
    "AssessmentPlan",
    "plan_assessment",
]
