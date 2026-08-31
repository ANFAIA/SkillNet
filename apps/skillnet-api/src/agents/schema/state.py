"""Graph state for the design-time schema proposal pipeline (§4.1).

``total=False`` so every node returns a partial dict of updates that LangGraph
merges into the running state, exactly like the v1 ``GenerationState``.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from src.core.language import Language


class SchemaState(TypedDict, total=False):
    # --- Identity ---
    job_id: str
    org_id: str
    triggered_by: str

    # --- Inputs ---
    source_document_ids: list[str]
    course_id: str
    intent_density: int
    # What the proposed titles, summaries and outcomes have to be written in, or
    # ``None`` for "nobody asked", which leaves the designer's prompt exactly as it
    # was. The generation job carries no language of its own, so ``load_source`` reads
    # it off the course row — the one thing every entry point into this graph shares.
    language: Language | None

    # --- Derived from the source (same shape as v1, computed by the new nodes) ---
    rag_mode: Literal["full_text", "chunked"]
    full_texts: dict
    extracted_themes: list[dict]
    source_metadata: dict
    # Closed list of the document's real headings; the designer may pick only
    # from here (§4.1).
    available_headings: list[str]

    # --- New ---
    # title, summary, outcome, criticality, prerequisites (indices), source_headings
    proposed_nodes: list[dict]
    schema_warnings: list[str]
    # "socratic" | "direct" — auto-detected alongside the node graph, defaults to
    # "socratic" when the designer's response omits or mangles it (course.py's
    # CourseTutorStyle enum is the source of truth for valid values).
    tutor_style: str

    # --- Control / progress ---
    error: str | None
    current_step: str
