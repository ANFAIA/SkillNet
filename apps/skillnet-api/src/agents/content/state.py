"""Graph state for the autonomous content generation pipeline.

``total=False`` so every node can return a partial dict of updates that LangGraph
merges into the running state. v1 carries NO human-in-the-loop fields (no admin
review, no manual output).
"""

from __future__ import annotations

from typing import Literal, TypedDict


class GenerationState(TypedDict, total=False):
    # --- Identity ---
    job_id: str
    org_id: str
    triggered_by: str

    # --- Inputs ---
    source_document_ids: list[str]
    course_id: str | None

    # --- RAG decisions ---
    rag_mode: Literal["full_text", "chunked"]
    full_texts: dict

    # --- Extraction ---
    extracted_themes: list[dict]
    source_metadata: dict

    # --- Structure ---
    course_outline: dict

    # --- Generation ---
    generated_modules: list[dict]

    # --- Review ---
    review_report: dict | None
    refinement_count: int

    # --- Output ---
    result_course_id: str | None

    # --- Control / progress ---
    error: str | None
    current_step: str
