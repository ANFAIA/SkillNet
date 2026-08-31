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

from src.core.language import Language


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
    accessibility: dict  # closed settings; never prose, memory or identity
    personalization_revision: int  # race guard for repinning generated content
    node_state: dict  # mastery, state, consecutive_*, last_error_kind, scaffold_band
    source_context: str  # source text (RAG or full_text), already clipped
    knowledge_pack_key: str  # pack_hash:selection_hash frozen before graph start
    knowledge_pack_hash: str
    knowledge_selection_hash: str
    knowledge_atom_ids: list[str]
    knowledge_evidence_ids: list[str]
    #: Server-only grounding retained for the adaptive branch. Neither value is serialized
    #: into the model prompt; the episode prompt receives only the authorized source slice.
    knowledge_pack_payload: dict
    knowledge_source_refs: list[dict]
    #: Versioned selection settings frozen with the cache key before graph start.
    selection_strategy: str
    selection_execution: str
    generation_policy_key: str
    #: Closed, bounded projection of scored Didact evidence from earlier nodes.
    longitudinal_history: dict
    #: The same projection digest included in the shared render cache key.
    longitudinal_decision_digest: str
    #: Optional explicit progressive expansion requested by a future caller/gate.
    #: The production service does not set it, so progressive honestly starts at top3.
    selection_progressive_stage: Literal["top3", "top5", "catalog"]
    #: Titulo y resumen de las OTRAS pantallas del curso, en orden de posicion. Lo que
    #: evita que seis nodos generados por separado abran con la misma frase y hagan la
    #: misma pregunta. Propiedad del esquema, identica para todos los aprendices.
    siblings: list[str]
    #: ``{"widened": bool, "reason": str}`` from ``load_source_context``: whether the source
    #: below is this node's own slice or one of the four documented fallbacks that hand it
    #: the whole document (or a sibling's passages). Explains the "nadie me explico esto"
    #: reports of 2026-08-28 — the material WAS taught, in another node.
    source_scope: dict
    # Broker-offered media components for this node, already gated by learner preference:
    # each is {kind, component, artifact_id, title} for a READY MediaArtifact.
    media_offers: list[dict]
    # Originals from the course's own source document that this lesson PLACES: each is
    # {component, image_id, alt, caption, document_id} for a real ``source_images`` row —
    # the prop order the frontend component expects, document_id last. Already gated
    # by the course's ``image_source_policy``, the image's ``kind`` and the learner's
    # ``images`` preference.
    source_image_offers: list[dict]
    # Originals this lesson REBUILDS instead of showing: each is {image_id, description,
    # caption}. No component is placed for these; the description steers the prompt.
    source_image_rebuilds: list[dict]

    # --- Gate ---
    mastered: bool

    # --- Adaptive episode rollout ---
    episode_brief: dict | None
    episode_status: Literal["ready", "support_only", "declined"]
    episode_decline_reason: str | None
    episode_prompt_version: str
    episode_certified_component_ids: list[str]
    shell_mode: Literal["legacy_stepper", "episode"]

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
    #: Semantic/content functions already computed by ``decide_formato``. Observability
    #: only: live prompts continue to consume ``shape_hints``.
    shape_functions: list[str]
    #: Cómo se VERIFICA este nodo, decidido por ``src/agents/runtime/assessment.py`` a
    #: partir de la forma del material y el ``node_id`` (estable, propiedad del nodo). Es
    #: lo que reparte la variedad de evaluación entre los nodos de un curso en vez de
    #: caer siempre en un ``QuizItem`` de tipo ``test``.
    assessment_block: str  # "QuizItem" | "DragOrder" | "DidactActivity"
    assessment_item_type: str | None  # Quiz item_type, or didact.* when DidactActivity
    assessment_hint: str  # la línea de prompt ya redactada
    #: Cómo se EXPLICA este nodo, decidido por ``src.agents.runtime.screen_scheme`` a
    #: partir de la forma del material y del closer. Tres huecos (lead, concepto,
    #: práctica). El generador rellena; no inventa la forma.
    concept_block: str  # Table | Chart | StepSequence | BeforeAfter
    screen_scheme: str  # el bloque de prompt ya redactado

    # --- Generation ---
    #: The language every prompt in this graph writes in. Resolved once by
    #: ``build_render_key`` (course -> org default -> the platform default) and carried,
    #: not re-derived: it is part of the render's cache key, so a node that answered the
    #: question differently would generate content the key does not describe.
    language: Language
    backend: str  # "openui" (the only dialect in this PR)
    effective_density: int  # course.intent_density, capped by short_blocks (§3.1)
    scaffold_band: str  # novice|neutral|advanced, frozen when the probe closed
    raw_dsl: str
    ui_spec: dict | None
    #: Inspectable experience decision. In shortlist mode its renderer-safe component
    #: names steer the prompt; the trace itself is not persisted in ``ui_spec``.
    plan_trace: dict
    #: Renderer-safe OpenUI names selected from the complete planning inventory. The
    #: prompt builder adds its structural shell and the required assessment separately.
    prompt_component_ids: list[str]
    #: Server-materialised activity reference. The UI model receives this real id and
    #: the public projection only; private answers never enter graph state.
    authored_activity: dict | None
    activity_authoring_status: str
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
