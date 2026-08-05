"""Stateless AI endpoints: schema proposal without persistence.

The ``/ai/`` namespace groups endpoints that call the LLM and return the result
directly, without creating database rows. The admin uses them during the
interactive design phase, before committing a course.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.agents.content.helpers import themes_list
from src.agents.schema.nodes import (
    EXTRACT_MAX_TOKENS,
    EXTRACT_TEMPERATURE,
    MAX_PROPOSED_NODES,
    SCHEMA_MAX_TOKENS,
    SCHEMA_TEMPERATURE,
    _nodes_from_response,
)
from src.core.logging import get_logger
from src.deps.auth import AdminUser
from src.deps.llm import LLMDep
from src.llm.parsing import parse_json_response
from src.llm.prompts import THEME_EXTRACTOR_SYSTEM, build_extraction_prompt
from src.llm.prompts.schema import SCHEMA_DESIGNER_SYSTEM, build_schema_prompt
from src.schemas.ai import ProposedNode, SchemaProposalRequest, SchemaProposalResponse

logger = get_logger(__name__)

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)


@router.post("/schema-propose", response_model=SchemaProposalResponse)
async def schema_propose(
    body: SchemaProposalRequest,
    _admin: AdminUser,
    llm: LLMDep,
) -> SchemaProposalResponse:
    """Propose a course schema from a title, description, and density.

    Stateless: nothing is persisted. The admin reviews the proposal in the UI
    and commits it explicitly.
    """
    # Build context from the title and description (no document).
    parts = [body.title]
    if body.description:
        parts.append(body.description)
    context = "\n\n".join(parts)

    # Step 1: extract themes.
    theme_response = await llm.complete(
        THEME_EXTRACTOR_SYSTEM,
        build_extraction_prompt(context),
        temperature=EXTRACT_TEMPERATURE,
        max_tokens=EXTRACT_MAX_TOKENS,
        json_mode=True,
    )
    extracted_themes = themes_list(parse_json_response(theme_response))

    # Step 2: design the schema.
    source_metadata = {
        "total_pages": 0,
        "doc_count": 0,
        "doc_titles": [body.title],
    }
    prompt = build_schema_prompt(
        extracted_themes,
        source_metadata,
        [],
        intent_density=body.intent_density,
        course_title=body.title,
        course_outcome=None,
    )
    design_response = await llm.complete(
        SCHEMA_DESIGNER_SYSTEM,
        prompt,
        temperature=SCHEMA_TEMPERATURE,
        max_tokens=SCHEMA_MAX_TOKENS,
        json_mode=True,
    )
    proposed = _nodes_from_response(parse_json_response(design_response))

    if len(proposed) > MAX_PROPOSED_NODES:
        proposed = proposed[:MAX_PROPOSED_NODES]

    nodes = [
        ProposedNode(
            title=str(node.get("title", "")).strip()[:300],
            summary=str(node.get("summary", "")).strip(),
            outcome=node.get("outcome"),
            criticality=str(node.get("criticality", "recommended")),
            default_ui_format=str(node.get("default_ui_format", "explanation")),
            estimated_minutes=_as_minutes(node.get("estimated_minutes")),
            source_headings=[],
            prerequisites=_safe_prerequisites(node.get("prerequisites"), idx),
        )
        for idx, node in enumerate(proposed)
        if str(node.get("title") or "").strip()
        and str(node.get("summary") or "").strip()
    ]

    return SchemaProposalResponse(nodes=nodes)


def _as_minutes(value: object) -> int:
    """Clamp to a sensible range, defaulting to 10."""
    try:
        minutes = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 10
    return max(1, min(minutes, 240))


def _safe_prerequisites(raw: object, own_index: int) -> list[int]:
    """Keep only valid integer prerequisites that do not self-reference."""
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for item in raw:
        try:
            idx = int(item)
        except (TypeError, ValueError):
            continue
        if idx != own_index and idx >= 0:
            out.append(idx)
    return out
