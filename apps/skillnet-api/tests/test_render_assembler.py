"""Assembler agent (multi-agent render): stitching declarations into a program.

The regression these lock down: an agent may declare a block that the blueprint
never listed. A *helper* nested inside another block (referenced from a children
array) must stay out of root; a true *orphan* (declared, valid, unreachable) must
be wired INTO root instead of silently dropped — measured on a Ticketrona node
where a `warn` Callout with a critical rule vanished because it was orphaned.
"""

from __future__ import annotations

import re

from src.agents.runtime.agents.assembler import assemble
from src.agents.runtime.agents.types import (
    Blueprint,
    BlueprintBlock,
    ContentOutput,
    InteractionOutput,
)


def _root_children(program: str) -> list[str]:
    """The ids inside `root = Stack([...], "gap")`, in order."""
    first = program.splitlines()[0]
    inside = re.search(r"\[([^\]]*)\]", first).group(1)
    return [tok.strip() for tok in inside.split(",") if tok.strip()]


def _bp(*blocks: tuple[str, str, str]) -> Blueprint:
    return Blueprint(blocks=[BlueprintBlock(id=i, type=t, intent=n) for i, t, n in blocks])  # type: ignore[arg-type]


def test_orphan_gets_wired_into_root_before_the_exercise() -> None:
    blueprint = _bp(("intro", "TextContent", "enganchar"), ("q1", "QuizItem", "verificar"))
    content = ContentOutput(
        declarations=(
            'intro = TextContent("Un cliente dice que no ha recibido su entrada.", "lead")\n'
            'aviso = Callout("warn", "Nunca des por cerrado un caso solo con el reenvio.")'
        )
    )
    interaction = InteractionOutput(
        declarations='q1 = QuizItem("q1", "test", "understand", "Que haces primero?", ["a", "b"])',
        answer_key={"q1": {"correct": 1}},
    )

    program, _ = assemble(
        blueprint=blueprint, content_output=content, interaction_output=interaction, ui_format="explanation"
    )
    children = _root_children(program)

    assert "aviso" in children, "the orphan Callout must reach the learner"
    # placed before the last child (the exercise), not after it
    assert children == ["intro", "aviso", "q1"]


def test_nested_helper_is_not_wired_into_root() -> None:
    blueprint = _bp(("card", "Card", "concepto"))
    content = ContentOutput(
        declarations=(
            'card = Card("Caso practico", [helper])\n'
            'helper = TextContent("Detalle del caso.", "body")'
        )
    )
    program, _ = assemble(
        blueprint=blueprint, content_output=content, interaction_output=None, ui_format="explanation"
    )
    children = _root_children(program)

    assert children == ["card"], "a helper referenced by another block stays out of root"
    assert "helper = TextContent" in program, "but its declaration is still emitted"


def test_verification_orphan_lands_last_not_before_a_content_block() -> None:
    """A DragOrder that arrives under an id the blueprint did not list must still close
    the screen — never sit before the StepSequence whose steps are its own answer.

    The seeded ``Cobro y cierre`` node produced exactly this: the blueprint verify block
    was forced to DragOrder, the interaction designer emitted it as ``ejercicio`` (an
    orphan), and the old before-last wiring left ``[lead, callout, ejercicio, pasos]`` —
    the drag exercise ahead of the step list that reveals the correct order.
    """
    blueprint = _bp(
        ("lead", "TextContent", "enganchar"),
        ("callout", "Callout", "refuerzo"),
        ("pasos", "StepSequence", "concepto"),
        ("drag_order", "DragOrder", "verificar"),  # never declared under this id
    )
    content = ContentOutput(
        declarations=(
            'lead = TextContent("Un cierre mal hecho descuadra el arqueo.", "lead")\n'
            'callout = Callout("warn", "Entrega el ticket antes de cerrar la mesa.")\n'
            'pasos = StepSequence("Cobro", ["Pedir la cuenta", "Cobrar", "Cerrar mesa"])'
        )
    )
    interaction = InteractionOutput(
        declarations=(
            'ejercicio = DragOrder("Ordena los pasos:", '
            '["Pedir la cuenta", "Cobrar", "Cerrar mesa"], '
            '["Pedir la cuenta", "Cobrar", "Cerrar mesa"])'
        ),
        answer_key={},
    )

    program, _ = assemble(
        blueprint=blueprint, content_output=content, interaction_output=interaction, ui_format="exercise"
    )
    children = _root_children(program)

    assert children[-1] == "ejercicio", "the exercise must be the last block on the screen"
    assert children == ["lead", "callout", "pasos", "ejercicio"]


def test_orphans_beyond_the_root_cap_are_dropped_not_overflowed() -> None:
    # Five blueprint blocks already fill the root fan-out cap (MAX_ROOT_CHILDREN=5).
    blueprint = _bp(
        ("b1", "TextContent", "enganchar"),
        ("b2", "Table", "concepto"),
        ("b3", "Callout", "concepto"),
        ("b4", "StepSequence", "concepto"),
        ("b5", "QuizItem", "verificar"),
    )
    lines = [
        'b1 = TextContent("uno", "lead")',
        'b2 = Table(["A"], [["1"]])',
        'b3 = Callout("info", "dos")',
        'b4 = StepSequence("Pasos", ["p1", "p2"])',
        'extra = Callout("warn", "huerfano que no cabe")',
    ]
    content = ContentOutput(declarations="\n".join(lines))
    interaction = InteractionOutput(
        declarations='b5 = QuizItem("b5", "test", "understand", "Q?", ["a", "b"])',
        answer_key={"b5": {"correct": 0}},
    )
    program, _ = assemble(
        blueprint=blueprint, content_output=content, interaction_output=interaction, ui_format="exercise"
    )
    children = _root_children(program)

    assert len(children) == 5, "root fan-out cap is respected"
    assert "extra" not in children
