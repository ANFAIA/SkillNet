"""Graph state for the runtime node pipeline (§4.2).

``total=False`` so every node returns a partial dict of updates that LangGraph merges,
exactly like ``SchemaState`` and the v1 ``GenerationState``.

There is **no ``job_id``** and no ``generation_jobs`` row: a node render is a per-learner,
per-request unit of work keyed on ``request_id``, which is also the SSE channel
(``node:{request_id}``). That is the whole reason ``src/agents/runtime/errors.py`` exists
instead of reusing the v1 wrapper.

Fields beyond the list in §4.2 are marked below; each is data the graph already had to
carry and that the spec's sketch left implicit.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class NodeRuntimeState(TypedDict, total=False):
    # --- Identity ---
    request_id: str
    org_id: str
    user_id: str
    course_id: str
    node_id: str

    # --- Loaded context ---
    node: dict  # title, summary, outcome, criticality, source_headings, seed_lesson_id
    profile: dict  # role_title, sector, experience_level, preset, format_vector,
    # nodes_completed, tutor_notes  (never `goal`: it does not reach the LLM)
    node_state: dict  # mastery, state, consecutive_*, last_error_kind, scaffold_band
    source_context: str  # source text (RAG or full_text), already clipped
    #: Titulo y resumen de las OTRAS pantallas del curso, en orden de posicion. Lo que
    #: evita que seis nodos generados por separado abran con la misma frase y hagan la
    #: misma pregunta. Propiedad del esquema, identica para todos los aprendices.
    siblings: list[str]

    # --- Gate ---
    mastered: bool

    # --- Router ---
    ui_format: Literal["explanation", "simulation", "exercise", "chart", "mixed"]
    tier: Literal["fast", "heavy"]
    format_rationale: str
    #: What ``src/agents/runtime/shape.py`` found in *this node's* section of the source:
    #: one instruction per structure, already naming the kit block that renders it. Written
    #: by ``decide_formato`` and read by ``genera_ui``; it is a property of the node, never
    #: of the learner, which is what makes it safe during the calibration period (§6.4).
    shape_hints: list[str]
    #: One line of evidence for the log and the rationale — never for a prompt.
    shape_summary: str

    # --- Generation ---
    backend: str  # "openui" (the only dialect in this PR)
    effective_density: int  # course.intent_density, capped by short_blocks (§3.1)
    scaffold_band: str  # novice|neutral|advanced, frozen when the probe closed
    raw_dsl: str
    ui_spec: dict | None
    answer_key: dict
    validation_errors: list[str]
    retry_count: int

    # --- Output ---
    cache_key: str
    render_id: str | None
    tokens_in: int
    tokens_out: int

    # --- Control ---
    error: str | None
    current_step: str

    # --- Beyond §4.2's sketch, and why ---
    #: ``true`` for ``POST /render {"preview": true}``. Excluded from the cache (§3.4) and
    #: never pinned onto ``learner_node_states``.
    is_preview: bool
    #: ``courses.schema_version``. Part of the ``cache_key``, so editing the schema
    #: invalidates derived renders without deleting a row.
    schema_version: int
    #: The **canonical** program, re-serialized from the validated spec by
    #: ``backend.serialize``. This is what ``node_renders.dialect`` stores and the only
    #: text a client may receive — never ``raw_dsl``.
    program: str
    #: Resolved model id of the tier that generated, for ``node_renders.model``.
    model: str
    #: Wall-clock of the generation, for ``node_renders.duration_ms`` and ``llm_usage_log``.
    duration_ms: int
    #: Provenance columns of §3.4, read from the build-step artefacts.
    catalog_version: str
    library_version: str


__all__ = ["NodeRuntimeState"]
