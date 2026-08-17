"""Assembler agent — combines Content Writer + Interaction Designer outputs into a
complete OpenUI Lang program.  Pure Python, no LLM calls."""

from __future__ import annotations

import json
import re

from collections.abc import Mapping
from typing import Any

from src.agents.runtime.agents.types import Blueprint, ContentOutput, InteractionOutput
from src.core.logging import get_logger
from src.llm.prompts.runtime import ANSWER_KEY_SENTINEL
from src.render.spec import MAX_ROOT_CHILDREN

logger = get_logger(__name__)


def _authored_experience_line(authored_activity: Mapping[str, Any]) -> str | None:
    """The server-owned ``LearningExperience`` closer, or None if refs are incomplete.

    The activity was authored, scored and persisted server-side; the closer is not the LLM's
    to invent. When one exists we emit it deterministically instead of trusting a small model
    to reproduce the opaque ids, which is why the rich interactive Didact activities
    (matching, categorize, sort, word-bank...) reliably reach the multi-agent render.
    """

    experience_id = authored_activity.get("experience_id") or authored_activity.get(
        "activity_id"
    )
    implementation_ref = authored_activity.get("implementation_ref") or (
        f"{authored_activity.get('component_id')}@1"
        if authored_activity.get("component_id")
        else None
    )
    definition_ref = authored_activity.get("definition_ref") or authored_activity.get(
        "activity_id"
    )
    if not (experience_id and implementation_ref and definition_ref):
        return None
    return (
        f'experiencia = LearningExperience("{experience_id}", '
        f'"{implementation_ref}", "{definition_ref}")'
    )


#: A declaration whose right-hand side is a verification component. Matched on the raw
#: line rather than on the blueprint because the id an agent actually emits may not match
#: the blueprint id (the interaction designer's DragOrder example hard-codes ``ejercicio``,
#: so a blueprint verify block named ``q1``/``drag_order`` comes back under a different id
#: and lands as an orphan). The pedagogy — "the exercise is always the last block" — has
#: to hold on the id that got written, not the one the blueprint hoped for.
_VERIFICATION_RE = re.compile(r"=\s*(QuizItem|DragOrder)\s*\(")


def _is_verification_line(line: str) -> bool:
    return bool(_VERIFICATION_RE.search(line))


def _collect_declarations(text: str) -> list[tuple[str, str]]:
    """Parse declaration lines from agent output.

    Returns a list of ``(block_id, line)`` pairs.  Lines that are not
    declarations (prose, comments, blank lines) are silently dropped — an LLM
    that emits preamble before the declarations must not poison the program.
    """
    result: list[tuple[str, str]] = []
    for raw in text.strip().splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        block_id = line.split("=", 1)[0].strip()
        # A valid id is an ASCII identifier; reject lines like `{"key": "val"}`
        if not block_id.isidentifier():
            continue
        result.append((block_id, line))
    return result


def assemble(
    *,
    blueprint: Blueprint,
    content_output: ContentOutput,
    interaction_output: InteractionOutput | None,
    ui_format: str,
    authored_activity: Mapping[str, Any] | None = None,
) -> tuple[str, dict]:
    """Assemble the complete program + answer key. Returns (raw_dsl, answer_key)."""
    # 1. Collect declarations, keyed by block_id (last-write-wins on duplicates)
    declarations: dict[str, str] = {}

    for block_id, line in _collect_declarations(content_output.declarations):
        declarations[block_id] = line

    if interaction_output and interaction_output.declarations.strip():
        for block_id, line in _collect_declarations(interaction_output.declarations):
            if block_id in declarations:
                logger.warning(
                    "Duplicate id %r: interaction designer overwrites content writer",
                    block_id,
                )
            declarations[block_id] = line

    # A server-authored activity owns the closer. Emit the neutral LearningExperience block
    # deterministically and drop any QuizItem/DragOrder the agents wrote for that slot — the
    # small model must never invent the opaque ids, and validate_ui forbids those closers when
    # a DidactActivity was certified. This is the seam that makes matching/categorize/sort/
    # word-bank actually render instead of degrading to a plain quiz.
    experience_line: str | None = None
    if isinstance(authored_activity, dict):
        experience_line = _authored_experience_line(authored_activity)
        if experience_line is not None:
            declarations = {
                block_id: line
                for block_id, line in declarations.items()
                if not _is_verification_line(line)
            }
            declarations["experiencia"] = experience_line

    # 2. Build root line
    # Children are the blueprint ids IN ORDER, filtered by what was actually declared.
    root_children: list[str] = []
    for block in blueprint.blocks:
        if block.id in declarations:
            root_children.append(block.id)
        else:
            logger.warning(
                "Blueprint block %r (%s) was not declared by any agent; omitting",
                block.id,
                block.type,
            )

    # Extra ids not in the blueprint fall into two kinds:
    #   - HELPERS nested inside another block (a Card's child, an item referenced
    #     from a children array). They ARE referenced by another declaration, so
    #     they render through their parent and must NOT be added to root.
    #   - true ORPHANS: declared, valid, but unreachable from root — the learner
    #     would never see them. This silently dropped real content (measured: a
    #     `warn` Callout carrying a critical rule vanished from a generated node).
    # Wire the orphans into root instead of losing them, placed just before the
    # last child (normally the exercise) so an informational block lands with the
    # content it belongs to. Respect the root fan-out cap so re-wiring never makes
    # the whole render fail validation — which would drop even more than the orphan.
    blueprint_ids = {b.id for b in blueprint.blocks}

    def _referenced_elsewhere(target: str) -> bool:
        pattern = re.compile(rf"\b{re.escape(target)}\b")
        for other_id, line in declarations.items():
            if other_id == target:
                continue
            rhs = line.split("=", 1)[1] if "=" in line else line
            if pattern.search(rhs):
                return True
        return False

    orphans = [
        did
        for did in declarations
        if did not in blueprint_ids and not _referenced_elsewhere(did)
    ]
    room = max(0, MAX_ROOT_CHILDREN - len(root_children))
    for did in orphans[room:]:
        logger.warning("Orphan id %r dropped: root fan-out cap reached", did)
    wire = orphans[:room]
    for did in wire:
        logger.warning("Orphan id %r not in blueprint; wiring into root", did)
    if wire:
        if root_children:
            root_children[-1:-1] = wire  # before the last child (the exercise)
        else:
            root_children = list(wire)

    # The verification block is always the last child, no matter how it got into root.
    # Two ways it ends up mislaid: the blueprint verify id was omitted (undeclared) and the
    # real exercise arrived as an orphan wired *before* the last child, or a content block
    # (a StepSequence whose steps ARE the answer) sits after the DragOrder that asks the
    # learner to order them — measured on the seeded "Cobro y cierre" node, where
    # `[lead, callout, ejercicio, step_sequence]` spoiled the drag exercise and left the
    # screen ending on content instead of the exercise. Move the last verification child to
    # the end; §blueprint contract already says a screen ends on QuizItem/DragOrder.
    verify_positions = [
        i for i, cid in enumerate(root_children) if _is_verification_line(declarations[cid])
    ]
    if verify_positions and verify_positions[-1] != len(root_children) - 1:
        root_children.append(root_children.pop(verify_positions[-1]))

    # The server-owned experience is the closer: force it to the last root child. Orphan
    # wiring above inserts it before the last child, so move it explicitly to the end.
    if experience_line is not None:
        if "experiencia" not in root_children:
            room_left = MAX_ROOT_CHILDREN - len(root_children)
            if room_left <= 0 and root_children:
                root_children.pop()  # make space by dropping the trailing content block
            root_children.append("experiencia")
        else:
            root_children.append(root_children.pop(root_children.index("experiencia")))

    gap = "md"
    root_line = f'root = Stack([{", ".join(root_children)}], "{gap}")'

    # 3. Assemble — root first, then declarations in blueprint order, then extras
    ordered_lines = [root_line]
    for block in blueprint.blocks:
        if block.id in declarations:
            ordered_lines.append(declarations[block.id])
    # Append extra declarations not in blueprint (e.g. Card helpers)
    for did, line in declarations.items():
        if did not in blueprint_ids:
            ordered_lines.append(line)

    program = "\n".join(ordered_lines)

    # 4. Answer key
    answer_key = {}
    if interaction_output:
        answer_key = interaction_output.answer_key
    # A server-scored experience carries no client-side answer key; drop any the agents wrote.
    if experience_line is not None:
        answer_key = {}

    # 5. Reconstruct raw_dsl (program + sentinel + key)
    raw_dsl = program
    if answer_key:
        raw_dsl += f"\n{ANSWER_KEY_SENTINEL}\n" + json.dumps(
            answer_key, ensure_ascii=False
        )

    return raw_dsl, answer_key
