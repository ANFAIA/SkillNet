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


@dataclass(frozen=True)
class AssessmentPlan:
    """El bloque de verificación que cierra la pantalla, y su tipo si es un ``QuizItem``."""

    #: ``"QuizItem"`` | ``"DragOrder"``.
    block: str
    #: El ``item_type`` cuando ``block == "QuizItem"``; ``None`` para ``DragOrder``.
    item_type: str | None

    @property
    def is_quiz(self) -> bool:
        return self.block == "QuizItem"

    def instruction(self) -> str:
        """La línea de prompt: nombra el bloque y cómo escribirlo, sin ambigüedad."""
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

    Estable: la misma pantalla en cada visita (no se mueve bajo el aprendiz). Repartido:
    ``position`` no vale porque cursos distintos comparten posiciones y sesgarían el
    reparto; un hash del id descorrelaciona la rotación del orden del temario.
    """
    digest = hashlib.sha1(str(node_id).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _has_procedure(plan: ShapePlan | None) -> bool:
    if plan is None:
        return False
    return any(signal.kind == "procedure" for signal in plan.signals)


def plan_assessment(
    plan: ShapePlan | None, *, ui_format: str, node_id: str
) -> AssessmentPlan:
    """El plan de verificación de un nodo.

    * Un **procedimiento** se verifica ordenándolo → ``DragOrder`` (salvo en ``chart``,
      donde la pantalla es una cifra y ordenar pasos no viene a cuento).
    * En cualquier otro caso, rota de forma determinista y estable por ``node_id`` entre
      ``test``, ``true_false`` y ``fill_blank`` para que los nodos hermanos no caigan todos
      en la opción múltiple.
    """
    if _has_procedure(plan) and ui_format != "chart":
        return AssessmentPlan(block="DragOrder", item_type=None)
    item_type = QUIZ_ROTATION[_node_seed(node_id) % len(QUIZ_ROTATION)]
    return AssessmentPlan(block="QuizItem", item_type=item_type)


__all__ = ["QUIZ_ROTATION", "AssessmentPlan", "plan_assessment"]
