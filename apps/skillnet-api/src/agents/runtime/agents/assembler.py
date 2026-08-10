"""Assembler agent — combines Content Writer + Interaction Designer outputs into a
complete OpenUI Lang program.  Pure Python, no LLM calls."""

from __future__ import annotations

import json
import re

from src.agents.runtime.agents.types import Blueprint, ContentOutput, InteractionOutput
from src.core.logging import get_logger
from src.llm.prompts.runtime import ANSWER_KEY_SENTINEL
from src.render.spec import MAX_ROOT_CHILDREN

logger = get_logger(__name__)


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
    #     `warn` Callout carrying a critical rule vanished from a Ticketrona node).
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

    # 5. Reconstruct raw_dsl (program + sentinel + key)
    raw_dsl = program
    if answer_key:
        raw_dsl += f"\n{ANSWER_KEY_SENTINEL}\n" + json.dumps(
            answer_key, ensure_ascii=False
        )

    return raw_dsl, answer_key
