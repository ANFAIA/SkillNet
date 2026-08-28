"""Stateless AI endpoints: schema proposal without persistence.

The ``/ai/`` namespace groups endpoints that call the LLM and return the result
directly, without creating database rows. The admin uses them during the
interactive design phase, before committing a course.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

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
from src.llm.client import LLMService
from src.llm.parsing import parse_json_response
from src.llm.prompts import THEME_EXTRACTOR_SYSTEM, build_extraction_prompt
from src.llm.prompts.schema import SCHEMA_DESIGNER_SYSTEM, build_schema_prompt
from src.schemas.ai import ProposedNode, SchemaProposalRequest, SchemaProposalResponse

logger = get_logger(__name__)

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)

# ── SSE headers (same as nodes.py) ─────────────────────────────

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def _format_sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ── Phase 1 (structure) prompt ─────────────────────────────────

_STRUCTURE_SYSTEM = """\
You are an instructional designer. Teach the subject on its own terms; reach
for a workplace framing only when the subject itself calls for one. Given a course
title, optional description, and a density level, propose ONLY the skeleton:
node titles, criticality, prerequisites, and a short list of observable skills.

Each node is ONE concrete thing the learner will be able to DO after it. The title
names that thing: "Identificar un neurotransmisor por su funcion", "Plazo de
devolucion", "Regla PAS". Chapter titles are the wrong unit: "Conceptos basicos",
"Introduccion", "Tipos de...", "Importancia de...", "Vision general".

Do not write summaries or outcomes here. Keep it fast: the tree and the skills.

For each node return:
- title: short, concrete name (max 80 characters)
- criticality: one of [critical, recommended, contextual]
- prerequisites: list of INDICES (0-based) of other nodes in this list

Reserve "critical" for competencies where doing it WRONG causes real
safety, legal, or serious financial/operational harm (a safety rule, a
regulated procedure, an irreversible action). A node that is merely
important, foundational, or a prerequisite is "recommended", NOT "critical".
Plain knowledge, facts, recognition, or classification are NEVER "critical" —
knowing them is checked by an assessment, not guarded as a safety rule. Most
courses have ZERO critical nodes; that is fine and expected.

Rules:
1. prerequisites uses INDICES of the list you are returning (0 = the first
   node), never identifiers or titles. A node cannot be a prerequisite of
   itself and the graph must be acyclic.
2. Mark a node "critical" ONLY if it meets the safety/consequence bar above.
   Do not force a critical node: if none qualifies, none is critical.
3. Order nodes from foundational to advanced. A prerequisite must appear
   BEFORE the node that needs it.
4. Write title in the SAME LANGUAGE as the course title.
5. Return 2-6 course-level skills. Each skill must describe an observable
   capability with an action verb (for example, "Configurar una taquilla"),
   never a broad topic (for example, "Taquilla"). Do not repeat node titles.
6. Write skills in the SAME LANGUAGE as the course title.
7. Density is a ceiling. Prefer fewer nodes if the brief only names a few
   actions. One action from the brief = one node.

Respond with valid JSON only, no surrounding text:
{"nodes": [{"title": str, "criticality": str, "prerequisites": [int]}],
 "skills": [str]}
"""

_DENSITY_GUIDANCE: dict[int, str] = {
    1: "Ceiling 5 nodes. Only the actions named in the brief.",
    2: "Ceiling 7 nodes. One action per node.",
    3: "Ceiling 10 nodes. One action per node.",
    4: "Ceiling 14 nodes. Contextual nodes only if they are a distinct action.",
    5: "Ceiling 18 nodes. Split procedures; each node is still one action.",
}


def _build_structure_prompt(
    title: str, description: str, density: int
) -> str:
    guidance = _DENSITY_GUIDANCE.get(density, _DENSITY_GUIDANCE[3])
    desc_line = f"\nDescription: {description}" if description else ""
    return (
        f"Propose the node skeleton for this course.\n\n"
        f"Title: {title}{desc_line}\n\n"
        f"Density (intent_density={density}): {guidance}"
    )


def _skill_names_from_response(parsed: object) -> list[str]:
    """Return a small, stable list of editable course-level skill suggestions.

    The suggestions are presentation data until the administrator confirms the
    schema.  Keeping normalization here prevents an enthusiastic model from
    turning one proposal into an unbounded organization taxonomy.
    """

    if not isinstance(parsed, dict) or not isinstance(parsed.get("skills"), list):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for value in parsed["skills"]:
        if not isinstance(value, str):
            continue
        name = " ".join(value.split()).strip()[:120]
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) == 6:
            break
    return names


# ── Phase 2 (enrichment) prompt ────────────────────────────────

_ENRICH_SYSTEM = """\
You are an instructional designer. You are given one node from a course schema
and the course title. Fill in the details for this single node.

Return valid JSON only, no surrounding text:
{"summary": str, "outcome": str, "default_ui_format": str}

Rules:
- summary: 1-2 sentences with the ONE fact, case or procedure this screen
  teaches. A shop-floor sentence, not a syllabus line.
  Example: "Si el aceite frio un rebozado con harina, la fritura no es apta
  para un celiaco."
- outcome: what the employee will do on the job after this screen, one sentence.
- default_ui_format: one of [explanation, exercise, chart, mixed].
  Use chart when the teaching material is numbers; mixed when it is a procedure
  the employee will then practise; explanation when it is one rule or case.
- Write in the SAME LANGUAGE as the node title.
"""


def _build_enrich_prompt(node_title: str, course_title: str) -> str:
    return (
        f'Course: "{course_title}"\n'
        f'Node title: "{node_title}"\n\n'
        f"Fill in the details for this node."
    )


# ── Streaming endpoint ─────────────────────────────────────────


async def _enrich_node(
    llm: LLMService,
    index: int,
    node_title: str,
    course_title: str,
) -> dict:
    """Run a single Phase 2 enrichment call for one node."""
    try:
        response = await llm.complete(
            _ENRICH_SYSTEM,
            _build_enrich_prompt(node_title, course_title),
            temperature=0.3,
            max_tokens=512,
            json_mode=True,
        )
        detail = parse_json_response(response)
        if not isinstance(detail, dict):
            detail = {}
        return {"index": index, "detail": detail}
    except Exception as exc:
        logger.warning("Enrichment failed for node %d (%s): %s", index, node_title, exc)
        return {
            "index": index,
            "detail": {
                "summary": "",
                "outcome": None,
                "default_ui_format": "explanation",
            },
            "error": str(exc),
        }


@router.post("/schema-propose-stream")
async def schema_propose_stream(
    body: SchemaProposalRequest,
    _admin: AdminUser,
    llm: LLMDep,
) -> StreamingResponse:
    """Two-phase streaming schema proposal.

    Phase 1: A fast LLM call that returns just node titles, criticality, and
    prerequisites. Sent as ``event: structure``.

    Phase 2: Parallel LLM calls (one per node) to fill in summary, outcome,
    estimated minutes, and format. Each result is sent as ``event: node_detail``.

    Final ``event: done`` when all enrichments complete; ``event: error`` on failure.
    """

    async def event_stream() -> AsyncIterator[str]:
        try:
            # --- Phase 1: Structure ---
            prompt = _build_structure_prompt(
                body.title,
                body.description or "",
                body.intent_density,
            )
            structure_response = await llm.complete(
                _STRUCTURE_SYSTEM,
                prompt,
                temperature=0.2,
                max_tokens=2048,
                json_mode=True,
            )
            parsed = parse_json_response(structure_response)
            raw_nodes = _nodes_from_response(parsed)
            proposed_skills = _skill_names_from_response(parsed)

            if len(raw_nodes) > MAX_PROPOSED_NODES:
                raw_nodes = raw_nodes[:MAX_PROPOSED_NODES]

            # Build structure-only nodes
            structure_nodes = []
            for idx, node in enumerate(raw_nodes):
                title = str(node.get("title", "")).strip()[:300]
                if not title:
                    continue
                structure_nodes.append({
                    "title": title,
                    "criticality": str(node.get("criticality", "recommended")),
                    "prerequisites": _safe_prerequisites(
                        node.get("prerequisites"), idx
                    ),
                })

            yield _format_sse(
                "structure",
                {"nodes": structure_nodes, "skills": proposed_skills},
            )

            # --- Phase 2: Enrich each node in parallel ---
            tasks = [
                _enrich_node(llm, idx, node["title"], body.title)
                for idx, node in enumerate(structure_nodes)
            ]
            # Fire all in parallel; yield each as it completes
            for coro in asyncio.as_completed(tasks):
                result = await coro
                yield _format_sse("node_detail", result)

            yield _format_sse("done", {})

        except Exception as exc:
            logger.error("schema-propose-stream failed: %s", exc, exc_info=True)
            yield _format_sse("error", {"message": str(exc)[:500]})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ── Original non-streaming endpoint (unchanged) ────────────────


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
            source_headings=[],
            prerequisites=_safe_prerequisites(node.get("prerequisites"), idx),
        )
        for idx, node in enumerate(proposed)
        if str(node.get("title") or "").strip()
        and str(node.get("summary") or "").strip()
    ]

    return SchemaProposalResponse(nodes=nodes)


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
