"""Graph nodes for the runtime render pipeline (§4.2).

```
load_context -> probe_gate --(mastered)--------------------------> skip_node -> END
                    | needs_content
                    v
              decide_formato -> genera_ui -> validate_ui --(ok)---> persist_render -> END
                                     ^            |
                                     +--(invalid, retry<1)
                                                  |
                                                  +--(fail)------> fallback_seed -> END
```

Every node opens its **own** session with ``async_session_factory``, exactly like v1 and the
schema graph: a node is a unit of work with its own transaction, and a render that fails
half way must not leave a partially written row behind somebody else's commit.

Three things in here are the security contract of §5.1 and are not negotiable:

* The model's own bytes (``raw_dsl``) are never persisted as servable text and never sent
  to a browser. ``validate_ui`` runs them through ``gate.canonicalize``, which parses to a
  ``UISpec`` and **re-serializes**; ``persist_render`` stores that re-serialization.
* ``answer_key`` is split off before the program is parsed and lands in its own column.
* No tool, no ``toolProvider``, no reactive syntax is taught or accepted anywhere.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from sqlalchemy import select

from src.agents.content.helpers import (
    CHARS_PER_PAGE,
    FULL_TEXT_PAGE_THRESHOLD,
    assemble_chunk_text,
    estimate_pages,
)
from src.agents.runtime.assessment import AssessmentPlan, plan_assessment
from src.agents.runtime.classify import classify_function
from src.agents.runtime.screen_scheme import ScreenScheme, plan_screen_scheme
from src.agents.runtime.errors import (
    node_channel,
    publish_error,
    publish_step,
    runtime_node_error_wrapper,
)
from src.agents.runtime.router import (
    coerce_ui_format,
    purpose_for,
    runtime_model_key,
    select_tier,
    tier_config,
    tier_llm,
)
from src.agents.runtime.shape import (
    ShapePlan,
    ShapeSignal,
    analyze_shape,
    focus_on_headings,
    refine_format,
)
from src.agents.runtime.state import NodeRuntimeState
from src.core import sse
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.llm.embedding import resolve_embedding_config
from src.llm.fixtures import maybe_fixture_embedder
from src.llm.parsing import parse_json_response
from src.llm.prompts.runtime import (
    ANSWER_KEY_SENTINEL,
    DECIDE_MAX_TOKENS,
    DECIDE_TEMPERATURE,
    DECIDE_USE_CASE,
    FORMAT_DECIDER_SYSTEM,
    UI_TEMPERATURE,
    UI_USE_CASE,
    EPISODE_PROMPT_VERSION,
    build_episode_repair_prompt,
    build_episode_ui_prompt,
    build_format_prompt,
    build_repair_prompt,
    build_ui_prompt,
    clip_source,
    episode_ui_generator_system,
    episode_ui_repair_system,
    signal_actions_for_node,
    ui_generator_system,
    ui_max_tokens,
    ui_repair_system,
)
from src.models import (
    ActivityDefinition,
    Course,
    CourseNode,
    Document,
    ExperienceIntent,
    ExperienceVariant,
    ImplementationBinding,
    Lesson,
    NodeRenderStatus,
    Organization,
    User,
)
from src.personalization.preferences import normalize_learning_preferences
from src.personalization.projection import (
    longitudinal_projection_from_mapping,
    project_longitudinal_history,
)
from src.render.backends import get_render_backend
from src.render.errors import RenderError
from src.render.gate import canonicalize
from src.render.kit import ContentFunction
from src.render.prompt import catalog_version, library_version
from src.render.prompt_slice import resolve_runtime_prompt
from src.render.spec import Component, UISpec, parse_spec
from src.repositories.activity_definition_repo import (
    ActivityDefinitionRepository,
    ActivityStateRepository,
)
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.llm_usage_repo import log_usage
from src.repositories.node_knowledge_pack_repo import NodeKnowledgePackRepository
from src.repositories.node_render_repo import NodeRenderRepository
from src.services.activity_authoring import (
    authoring_draft_with_server_refs,
    build_activity_authoring_prompts,
    materialize_authored_activity,
)
from src.services.activity_definitions import ActivityDefinitionService
from src.services.learner_profile_service import is_calibrating
from src.services.mastery_service import target_bloom, threshold_for
from src.services.node_render_service import NodeRenderService, build_render_key

logger = get_logger(__name__)

#: Chunks retrieved for the ``chunked`` branch of ``load_context`` (§4.2).
RETRIEVAL_TOP_K = 8

#: Fallback is a safety net, not a document viewer. Keep it within a compact viewport even
#: when the source lesson is long: one lead plus at most two short Markdown blocks.
FALLBACK_BLOCK_CHARS = 300
FALLBACK_MAX_BLOCKS = 2

# Closed renderer-safe scope for unscored support. Assessment wrappers and neutral
# experience references are deliberately absent: they require server materialization.
_SUPPORT_PROMPT_COMPONENT_IDS = frozenset(
    {
        "BeforeAfter",
        "Chart",
        "DidactGlossary",
        "DidactTimeline",
        "DidactWorkedExample",
        "Flashcard",
        "HintReveal",
        "StepByStepReveal",
        "StepSequence",
        "Table",
        "Tabs",
    }
)

STEP_MESSAGES: dict[str, str] = {
    "load_context": "Preparando el nodo...",
    "probe_gate": "Comprobando lo que ya dominas...",
    "direct_episode": "Preparando una experiencia adaptada...",
    "decide_formato": "Eligiendo la forma de la leccion...",
    "author_activity": "Preparando la actividad interactiva...",
    "genera_ui": "Escribiendo la leccion...",
    "validate_ui": "Revisando la leccion...",
    "persist_render": "Guardando la leccion...",
    "fallback_seed": "Sirviendo la version de respaldo...",
    "skip_node": "Ya dominas este nodo.",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def _org_settings(db: Any, org_id: uuid.UUID) -> dict[str, Any]:
    """Provider overrides of the organization; falls back to the single row."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
    return dict(org.settings) if org and org.settings else {}


async def _make_llm(org_id: uuid.UUID, tier: str) -> Any:
    """The tier's ``LLMService``, through the one fixture branch point (§12.1)."""
    async with async_session_factory() as db:
        org_settings = await _org_settings(db, org_id)
    return tier_llm(org_settings, tier)


async def load_source_context(db: Any, node: CourseNode, org_id: uuid.UUID) -> str:
    """The two explicit branches of §4.2.

    * A document of **<= 5 pages** goes in whole (``full_text``). No embeddings needed, and
      this is the branch the fixture tests exercise end to end.
    * Anything bigger goes through ``similarity_search_by_headings(headings=node.source_headings)``.
      Headings survive re-ingestion, chunk ids do not. If the heading filter returns nothing
      the search is retried **without** it and a warning is logged — an empty source would
      otherwise hand the learner plausible content with no documentary basis, silently.
    """
    if node.source_document_id is None:
        return ""
    document = await db.get(Document, node.source_document_id)
    if document is None:
        return ""

    # A document whose full_text fits in the prompt window goes in whole. The threshold
    # uses character count as a secondary signal: a 10-slide PDF may report 10 "pages"
    # but carry fewer characters than a dense 3-page manual. When the text is small
    # enough to fit comfortably, the full-text path is more reliable and avoids an
    # embedding call that may not be available.
    full_text_chars = len(document.full_text or "")
    pages = estimate_pages(document)
    use_full_text = (
        document.full_text
        and (pages <= FULL_TEXT_PAGE_THRESHOLD or full_text_chars <= CHARS_PER_PAGE * FULL_TEXT_PAGE_THRESHOLD)
    )
    if use_full_text:
        # Scoped to the node's own headings, exactly like the chunked branch below.
        # The asymmetry was invisible and expensive: a document of <= 5 pages went in
        # WHOLE, so all three nodes of the seeded ``Alergenos`` course were handed the
        # same text and the node about cross-contamination was asked to teach from the
        # fourteen allergens as well. It also costs tokens where they are scarcest —
        # ``genera_ui`` averages ~5 250 input tokens against a 6 000/min free-tier
        # ceiling, and the whole document is most of that.
        return clip_source(_scoped_full_text(document.full_text, node.source_headings))

    repo = DocumentChunkRepository(db)
    try:
        embedder = maybe_fixture_embedder(resolve_embedding_config(await _org_settings(db, org_id)))
        query = f"{node.title}\n{node.summary}"
        embedding = await embedder.embed_query(query)
    except Exception:
        logger.warning(
            "Embedding failed for node %s; falling back to full_text", node.id
        )
        if document.full_text:
            return clip_source(_scoped_full_text(document.full_text, node.source_headings))
        return ""
    headings = list(node.source_headings or [])
    rows = await repo.similarity_search_by_headings(
        org_id=org_id,
        query_embedding=embedding,
        top_k=RETRIEVAL_TOP_K,
        document_ids=[document.id],
        headings=headings,
    )
    if not rows and headings:
        logger.warning(
            "No chunk matched headings %s for node %s; retrying without the filter",
            headings,
            node.id,
        )
        rows = await repo.similarity_search_by_headings(
            org_id=org_id,
            query_embedding=embedding,
            top_k=RETRIEVAL_TOP_K,
            document_ids=[document.id],
            headings=None,
        )
    if not rows and document.full_text:
        return clip_source(document.full_text)

    class _Chunk:
        def __init__(self, content: str) -> None:
            self.content = content

    return clip_source(assemble_chunk_text([_Chunk(row["content"]) for row in rows]))


#: A scoped section shorter than this is treated as a bad match and the whole document is
#: kept. Narrowing to two sentences would starve the generator of the material it has to
#: teach from, and ``SkillNet 13`` then leaves it nothing to say — a worse failure than
#: carrying a few hundred tokens too many.
MIN_SCOPED_SOURCE_CHARS = 200


def _scoped_full_text(full_text: str, headings: Any) -> str:
    """The node's own sections of a short document, or all of it when that is not safe."""
    scoped = focus_on_headings(full_text, list(headings or ()))
    if len(scoped.strip()) < MIN_SCOPED_SOURCE_CHARS:
        return full_text
    return scoped


def split_answer_key(raw: str) -> tuple[str, dict]:
    """Split ``<program>`` from ``<answer key JSON>`` on :data:`ANSWER_KEY_SENTINEL`.

    Done **before** the gate sees anything, which is why the JSON braces never trip
    ``check_static_only``. A missing or unparseable key is not an error here: ``validate_ui``
    decides, because "is a key required" depends on whether the spec has a ``QuizItem``.
    """
    if ANSWER_KEY_SENTINEL not in raw:
        return raw, {}
    program, _, tail = raw.partition(ANSWER_KEY_SENTINEL)
    try:
        parsed = parse_json_response(tail)
    except Exception:  # noqa: BLE001 - a broken key is a validation problem, not a crash
        return program, {}
    return program, parsed if isinstance(parsed, dict) else {}


def missing_answer_keys(spec: UISpec, answer_key: dict) -> list[str]:
    """Item ids of ``QuizItem`` blocks with no usable entry in the key.

    A quiz whose key is missing would grade every answer 0.0 (``content_for`` returns a
    content dict with no solution), so the learner could never pass the node. That is a
    validation failure worth spending the single repair attempt on, not something to serve.
    """
    wanted = [
        str(component.props.get("item_id") or component.id)
        for component in spec.components
        if component.type == "QuizItem"
    ]
    missing = [
        item_id
        for item_id in wanted
        if not isinstance(answer_key.get(item_id), dict)
        or not _has_solution(answer_key[item_id])
    ]
    if not missing:
        return []

    # What the model has to change depends on what it actually sent, and the repair loop
    # replays this string verbatim, so the two cases are told apart here rather than left
    # to the model to guess. Measured (2026-07-27): the key was *absent* on
    # `higiene-alimentaria` and `alergenos-hosteleria`, and *present but indexed by the
    # question text* on `atencion-reclamaciones`. The old message — "no llega su solucion"
    # for both — is the same complaint for two different mistakes.
    if answer_key:
        received = ", ".join(repr(key) for key in list(answer_key)[:4])
        remedy = (
            f"La clave que has enviado indexa por {received}. Se indexa por el item_id "
            "del QuizItem, que es su PRIMER argumento, no por el enunciado ni por el id "
            "del bloque."
        )
    else:
        example = missing[0]
        remedy = (
            f"No has escrito el bloque. Despues del programa, una linea con exactamente "
            f"{ANSWER_KEY_SENTINEL} y debajo un unico JSON: "
            f'{{"{example}": {{"correct": 0, "explanation": "Por que esa."}}}}. '
            "La clave nunca es una declaracion del programa."
        )
    return [
        f"QuizItem {item_id!r} tiene enunciado pero no llega su solucion en el bloque "
        f"{ANSWER_KEY_SENTINEL}. {remedy}"
        for item_id in missing
    ]


def _has_solution(entry: dict) -> bool:
    return any(
        entry.get(field) is not None
        for field in ("correct", "correct_order", "blanks", "rubric")
    )


def prune_answer_key(spec: UISpec, answer_key: dict) -> dict:
    """Keep only entries for ``QuizItem`` ids that really exist in the spec.

    The model is capable of inventing an entry for an item it did not emit; storing it would
    put un-referenced answers in a column whose whole purpose is to be minimal.
    """
    wanted = {
        str(component.props.get("item_id") or component.id)
        for component in spec.components
        if component.type == "QuizItem"
    }
    return {
        item_id: entry
        for item_id, entry in answer_key.items()
        if item_id in wanted and isinstance(entry, dict)
    }


def _source_has_numbers(text: str) -> bool:
    """Whether the source carries digits at all — the honest input to the ``chart`` rule.

    ``decide_formato`` may not pick ``chart`` for a source with no figures, because rule 13
    of the generator prompt forbids inventing any. Better to tell it than to hope.
    """
    return any(char.isdigit() for char in text)


# --------------------------------------------------------------------------- #
# Node 1: load_context
# --------------------------------------------------------------------------- #
@runtime_node_error_wrapper("load_context")
async def load_context(state: NodeRuntimeState) -> dict:
    """Load node, profile, learner state and source; compute the key; claim the row.

    Claiming ``node_renders`` here (``status='generating'``) rather than at the end is what
    gives the error wrapper something to mark ``failed``, and what makes a second request
    for the same key adopt the row instead of racing it.
    """
    request_id = str(state["request_id"])
    node_id = _uuid(state["node_id"])
    user_id = _uuid(state["user_id"])
    org_id = _uuid(state["org_id"])

    async with async_session_factory() as db:
        node = await db.get(CourseNode, node_id)
        if node is None:
            raise ValueError(f"Course node {node_id} not found")
        course = await db.get(Course, node.course_id)
        if course is None:
            raise ValueError(f"Course {node.course_id} not found")
        # Lo que cubren las OTRAS pantallas del curso. Sin esto cada nodo se genera a
        # ciegas, y con un documento corto los seis extraen la misma idea principal:
        # medido el 2026-08-09 sobre el manual real del partner, la misma frase de
        # apertura salio en cuatro de seis pantallas y practicamente la misma pregunta en
        # las seis. Es propiedad del esquema, no del aprendiz, asi que no toca el
        # `cache_key` (ya lleva `schema_version`) ni el periodo de calibracion de §6.4.
        siblings_rows = (
            (
                await db.execute(
                    select(CourseNode)
                    .where(
                        CourseNode.course_id == node.course_id,
                        CourseNode.id != node_id,
                        CourseNode.archived.is_(False),
                    )
                    .order_by(CourseNode.position)
                )
            )
            .scalars()
            .all()
        )
        siblings = [
            f"{row.position}. {row.title}"
            + (f" — {row.summary.strip()}" if (row.summary or "").strip() else "")
            for row in siblings_rows
        ]

        user = await db.get(User, user_id)
        profile = await LearnerProfileRepository(db).get_by_user(user_id)
        node_state = await LearnerNodeStateRepository(db).get_by_user_and_node(
            user_id, node_id
        )
        org_settings = await _org_settings(db, org_id)
        source_context = await load_source_context(db, node, org_id)
        accessibility_payload = dict(getattr(user, "accessibility", None) or {})
        history_payload = state.get("longitudinal_history")
        history = (
            longitudinal_projection_from_mapping(history_payload)
            if isinstance(history_payload, dict)
            else project_longitudinal_history(
                [],
                nodes_completed=int(getattr(profile, "nodes_completed", 0) or 0),
            )
        )
        expected_history_digest = str(
            state.get("longitudinal_decision_digest") or ""
        )
        if (
            expected_history_digest
            and history.decision_digest != expected_history_digest
        ):
            raise RuntimeError(
                "Longitudinal decision changed between cache lookup and generation; retry"
            )

        from src.knowledge_pack.runtime_selection import load_runtime_knowledge

        pack_selection = await load_runtime_knowledge(
            db,
            node=node,
            course=course,
            profile=profile,
            node_state=node_state,
            accessibility=accessibility_payload,
        )
        expected_pack_key = str(state.get("knowledge_pack_key") or "")
        if expected_pack_key:
            if pack_selection is None or pack_selection.cache_fragment != expected_pack_key:
                raise RuntimeError(
                    "Knowledge pack changed between cache lookup and generation; retry"
                )
            source_context = pack_selection.source_context
        else:
            # A pack may finish after the pre-graph cache lookup. This render remains on
            # raw source under its already-frozen key; the next request gets the pack key.
            pack_selection = None

        key = build_render_key(
            node=node,
            course=course,
            profile=profile,
            node_state=node_state,
            accessibility=accessibility_payload,
            model_key=runtime_model_key(org_settings),
            is_preview=bool(state.get("is_preview")),
            # The service already salted the preview key; reuse it verbatim so the row it
            # claimed and the row this graph writes are the same row.
            preview_salt=None,
            knowledge_pack_key=expected_pack_key,
            longitudinal_history=history,
        )
        cache_key = str(state.get("cache_key") or key.cache_key)

        # The tier is not known until decide_formato has run, so the row is claimed with the
        # node's declared default. persist_render rewrites both columns with what was used.
        default_format = coerce_ui_format(node.default_ui_format)
        claim_tier = select_tier(default_format)
        render = await NodeRenderRepository(db).claim(
            org_id=org_id,
            node_id=node_id,
            cache_key=cache_key,
            backend=str(state.get("backend") or "openui"),
            model=tier_config(org_settings, claim_tier).model,
            tier=claim_tier,
            ui_format=default_format,
            generated_by=user_id,
            is_preview=bool(state.get("is_preview")),
        )
        render_id = str(render.id)
        already_served = render.status in (
            NodeRenderStatus.READY,
            NodeRenderStatus.FALLBACK,
        )
        node_payload = {
            "id": str(node.id),
            "position": int(node.position),
            "title": node.title,
            "summary": node.summary,
            "outcome": node.outcome,
            "criticality": _plain(node.criticality),
            "default_ui_format": default_format,
            "mastery_threshold": float(node.mastery_threshold or 0.8),
            "seed_lesson_id": str(node.seed_lesson_id) if node.seed_lesson_id else None,
            "source_headings": list(node.source_headings or []),
            "domain": str(
                getattr(node, "domain", None) or getattr(course, "title", "") or ""
            ),
            # Optional server-owned oracle declarations. They are consumed only by the
            # episode adapter and never serialized into a model prompt.
            "evidence_contracts": dict(
                getattr(node, "evidence_contracts", None) or {}
            ),
        }
        profile_payload = {
            # `goal` is deliberately absent: it never reaches the LLM (§3.3).
            "role_title": getattr(profile, "role_title", None),
            "sector": getattr(profile, "sector", None),
            "experience_level": _plain(getattr(profile, "experience_level", "unknown")),
            "preset": _plain(getattr(profile, "preset", "standard")),
            "nodes_completed": int(getattr(profile, "nodes_completed", 0) or 0),
            "vector_bucket": key.vector_bucket,
            # Structured shadow-planner inputs only. Neither field is injected into a
            # prompt or used to select the live OpenUI output here.
            "format_vector": dict(getattr(profile, "format_vector", None) or {}),
            "learning_preferences": dict(
                getattr(profile, "learning_preferences", None) or {}
            ),
            "tutor_signals": list(
                signal_actions_for_node(getattr(profile, "tutor_notes", None), node.id)
            ),
            # The learner's narrative memory, trimmed, made available to the render context.
            # It is DELIBERATELY not fed into the generation prompt here: the render is cached
            # under a `cache_key` that (correctly) excludes `user_id`, so injecting one
            # learner's prose into the shared prompt would leak their personalization into a
            # row served to everyone in the same bucket. Activating generator personalization
            # needs a coarse, non-identifying memory bucket in the cache_key — see
            # docs/learner-memory.md ("CONFIRMAR con Jose"). Exposed now so the plumbing is in
            # place; read today only by the tutor, whose turn is per-user and uncached.
            "memory_md": _render_memory_for_prompt(getattr(profile, "memory_md", None)),
            "longitudinal_history": {
                "evaluated_attempts": history.evaluated_attempts,
                "error_attempts": history.error_attempts,
                "supported_error_attempts": history.supported_error_attempts,
                "mechanic_exposure": list(history.mechanic_exposure),
                "support_level": history.support_level.value,
                "applied": history.applied,
                "evidence_policy": history.evidence_policy,
                "semantic_error_mapping": history.semantic_error_mapping,
            },
        }
        state_payload = {
            "state": _plain(getattr(node_state, "state", "not_started")),
            "mastery": float(getattr(node_state, "mastery", 0.0) or 0.0),
            "consecutive_correct": int(getattr(node_state, "consecutive_correct", 0) or 0),
            "consecutive_failed": int(getattr(node_state, "consecutive_failed", 0) or 0),
            "last_error_kind": _plain_or_none(getattr(node_state, "last_error_kind", None)),
            "scaffold_band": key.scaffold_band,
        }
        await db.commit()

    await publish_step(request_id, "load_context", STEP_MESSAGES["load_context"])
    if already_served:
        # Another request finished this exact key between the service's cache check and this
        # claim. The graph keeps going and ``persist_render`` will rewrite the row with an
        # equivalent render (same key means the same inputs), which is wasteful but not
        # wrong. Logged rather than short-circuited: the cheap fix is the service's check.
        logger.info(
            "Render %s for key %s was already served; regenerating an equivalent one",
            render_id,
            cache_key,
        )

    return {
        "node": node_payload,
        "profile": profile_payload,
        "accessibility": accessibility_payload,
        "personalization_revision": int(
            getattr(profile, "personalization_revision", 0) or 0
        ),
        "node_state": state_payload,
        "source_context": source_context,
        "knowledge_pack_key": expected_pack_key,
        "knowledge_pack_hash": pack_selection.pack_hash if pack_selection else "",
        "knowledge_selection_hash": (
            pack_selection.selection_hash if pack_selection else ""
        ),
        "knowledge_atom_ids": list(pack_selection.atom_ids) if pack_selection else [],
        "knowledge_evidence_ids": (
            list(pack_selection.evidence_ids) if pack_selection else []
        ),
        "knowledge_pack_payload": (
            dict(pack_selection.pack_payload) if pack_selection else {}
        ),
        "knowledge_source_refs": (
            [item.model_dump(mode="json") for item in pack_selection.source_refs]
            if pack_selection
            else []
        ),
        "siblings": siblings,
        "backend": str(state.get("backend") or "openui"),
        "effective_density": key.effective_density,
        "scaffold_band": key.scaffold_band,
        "longitudinal_decision_digest": history.decision_digest,
        "longitudinal_history": profile_payload["longitudinal_history"],
        "cache_key": cache_key,
        "generation_policy_key": key.generation_policy_key,
        "render_id": render_id,
        "schema_version": int(state.get("schema_version") or 1),
        "current_step": "load_context",
    }


def _plain(value: object) -> str:
    return getattr(value, "value", value) if value is not None else ""  # type: ignore[return-value]


def _plain_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _history_support_level(state: NodeRuntimeState | dict) -> str:
    history = state.get("longitudinal_history")
    if not isinstance(history, dict) or not bool(history.get("applied")):
        return "base"
    value = str(history.get("support_level") or "base")
    return value if value in {"base", "hints", "worked-example"} else "base"


def _effective_scaffold_band(state: NodeRuntimeState | dict) -> str:
    """Escalate support for the next render without mutating node mastery state."""

    band = str(state.get("scaffold_band") or "neutral")
    support = _history_support_level(state)
    if support == "worked-example":
        return "novice"
    if support == "hints" and band == "advanced":
        return "neutral"
    return band


#: Ceiling on the learner-memory slice carried in the render context (chars). Small: it is
#: not fed into the (cached) generation prompt today — see the note in ``load_context``.
_MEMORY_CONTEXT_MAX_CHARS = 800


def _render_memory_for_prompt(memory_md: str | None) -> str:
    """The learner's narrative memory trimmed for the render context; ``""`` when empty."""
    from src.services.learner_memory import render_for_prompt

    return render_for_prompt(memory_md, max_chars=_MEMORY_CONTEXT_MAX_CHARS)


# --------------------------------------------------------------------------- #
# Node 2: probe_gate
# --------------------------------------------------------------------------- #
@runtime_node_error_wrapper("probe_gate")
async def probe_gate(state: NodeRuntimeState) -> dict:
    """Skip the node when the learner already mastered it. Zero tokens (§2, §7.3).

    **Currently bypassed** (``b9a06c3``, 2026-07-28): the gate always routes to content
    generation, so the "a mastered node costs zero tokens" guarantee of §2/§7.3 is not in
    force. The frontend bypasses the probe phase in the same commit, so re-enabling this
    is a product decision that has to be taken on both sides at once.
    """
    # BYPASS: pre-assessment gate disabled — always route to content generation.
    # To re-enable, restore the original two lines (and the `MASTERED` import from
    # `src.services.mastery_service`, dropped because nothing else here uses it):
    #   node_state = state.get("node_state") or {}
    #   mastered = str(node_state.get("state")) == MASTERED
    mastered = False
    await publish_step(
        str(state["request_id"]), "probe_gate", STEP_MESSAGES["probe_gate"]
    )
    return {"mastered": mastered, "current_step": "probe_gate"}


# --------------------------------------------------------------------------- #
# Adaptive rollout: pure contract projection, fail-open to the legacy router
# --------------------------------------------------------------------------- #
def _declined_episode(
    state: NodeRuntimeState,
    reason: str,
    *,
    refs: tuple[str, ...] = (),
) -> dict:
    trace = dict(state.get("plan_trace") or {})
    trace["episode"] = {
        "status": "declined",
        "reason": reason,
        "refs": list(refs),
        "prompt_version": EPISODE_PROMPT_VERSION,
    }
    return {
        "episode_brief": None,
        "episode_status": "declined",
        "episode_decline_reason": reason,
        "episode_prompt_version": EPISODE_PROMPT_VERSION,
        "plan_trace": trace,
        "current_step": "direct_episode",
    }


async def direct_episode(state: NodeRuntimeState) -> dict:
    """Build one grounded episode or decline to the unchanged legacy path.

    The selection frozen into the render key is reconstructed exactly; knowledge is never
    selected twice.  This node only certifies the component boundary.  ``author_activity``
    may materialize that certified definition later in the same runtime request; no
    experience artifact is prepared with the course.
    """

    from src.agents.runtime.shadow_plan import build_grounded_episode_plan_trace
    from src.knowledge_pack.contracts import NodeKnowledgePack, SourceRef
    from src.knowledge_pack.runtime_selection import RuntimeKnowledgeSelection
    from src.services.episode_inputs import (
        EpisodeInputDeclined,
        episode_inputs_from_selection,
    )
    from src.services.episode_policy import (
        build_episode_brief,
        build_support_episode_brief,
    )
    from src.services.evidence_contract_policy import (
        EvidencePolicyDeclined,
        evidence_contracts_for_pack,
    )

    payload = state.get("knowledge_pack_payload")
    if not isinstance(payload, dict) or not payload:
        return _declined_episode(state, "missing_knowledge_pack")
    try:
        pack = NodeKnowledgePack.model_validate(payload)
        source_refs = tuple(
            SourceRef.model_validate(item)
            for item in state.get("knowledge_source_refs") or ()
        )
        selection = RuntimeKnowledgeSelection(
            pack_hash=str(state.get("knowledge_pack_hash") or ""),
            selection_hash=str(state.get("knowledge_selection_hash") or ""),
            cache_fragment=str(state.get("knowledge_pack_key") or ""),
            source_context=str(state.get("source_context") or ""),
            atom_ids=tuple(state.get("knowledge_atom_ids") or ()),
            evidence_ids=tuple(state.get("knowledge_evidence_ids") or ()),
            source_refs=source_refs,
            pack_payload=payload,
        )
        node_view = dict(state.get("node") or {})
        evidence_policy = evidence_contracts_for_pack(
            pack,
            criticality=node_view.get("criticality"),
        )
        support_reasons = {
            "critical_oracle_unavailable",
            "execution_oracle_unavailable",
            "rubric_oracle_unavailable",
            "required_evidence_unsupported",
        }
        support_only = isinstance(evidence_policy, EvidencePolicyDeclined)
        if support_only:
            decline_reason = evidence_policy.reason.value
            if decline_reason not in support_reasons:
                return _declined_episode(
                    state,
                    f"evidence_policy:{decline_reason}",
                    refs=evidence_policy.evidence_ids,
                )
            # These explicit unavailable markers let the grounding adapter retain the
            # competency's required evidence constitution. The support brief activates
            # none of the gates and never exposes these internal refs to the prompt.
            node_view["evidence_contracts"] = {
                spec.evidence_id: {
                    "evidence_type": "unscored-required-evidence",
                    "oracle_ref": f"unavailable:{decline_reason}:{spec.evidence_id}",
                }
                for spec in pack.evidence_specs
                if spec.required
            }
        else:
            decline_reason = ""
            node_view["evidence_contracts"] = {
                key: dict(value)
                for key, value in evidence_policy.evidence_contracts.items()
            }
        inputs = episode_inputs_from_selection(
            pack,
            selection,
            node=node_view,
            profile_bucket=state.get("profile") or {},
            node_state=state.get("node_state") or {},
        )
        if isinstance(inputs, EpisodeInputDeclined):
            return _declined_episode(
                state, inputs.reason.value, refs=inputs.refs
            )
        brief = (
            build_support_episode_brief(
                inputs.competency,
                inputs.source_map,
                inputs.belief,
                decline_reason=f"evidence_policy:{decline_reason}",
            )
            if support_only
            else build_episode_brief(
                inputs.competency,
                inputs.source_map,
                inputs.belief,
            )
        )
        trace = build_grounded_episode_plan_trace(pack.objective, dict(state))
        certified_ids = (
            ()
            if support_only
            else tuple(
                dict.fromkeys(
                    component_id
                    for contract in evidence_policy.evidence_contracts.values()
                    for component_id in contract.get("supported_component_ids", ())
                )
            )
        )
        prompt_ids = list(trace.get("prompt_component_ids") or ())
        if support_only:
            prompt_ids = [
                value for value in prompt_ids if value in _SUPPORT_PROMPT_COMPONENT_IDS
            ]
            trace["renderer_selection"] = (
                "planner-unscored" if prompt_ids else "base-shell"
            )
        elif certified_ids and "DidactActivity" not in prompt_ids:
            prompt_ids.append("DidactActivity")
            if trace.get("status") != "planned":
                trace["renderer_selection"] = "evidence-certified"
        if not support_only and not prompt_ids:
            return _declined_episode(state, "renderer_shortlist_declined")
    except (TypeError, ValueError, KeyError) as exc:
        return _declined_episode(state, f"invalid_episode_inputs:{type(exc).__name__}")

    ui_format = "exercise" if brief.assessment_mode != "none" else "explanation"
    tier = select_tier(ui_format)
    trace["prompt_component_ids"] = prompt_ids
    trace["episode"] = {
        "status": "support_only" if support_only else "ready",
        "episode_id": str(brief.episode_id),
        "strategy": brief.policy_trace.get("strategy"),
        "prompt_version": EPISODE_PROMPT_VERSION,
        "pack_hash": selection.pack_hash,
        "selection_hash": selection.selection_hash,
        "evidence_policy": evidence_policy.policy_version,
        "evidence_blocked": support_only,
        "mastery_blocked": support_only,
    }
    request_id = str(state["request_id"])
    await publish_step(request_id, "direct_episode", STEP_MESSAGES["direct_episode"])
    await sse.publish(
        node_channel(request_id), "ui_format", {"format": ui_format, "tier": tier}
    )
    return {
        "episode_brief": brief.model_dump(mode="json"),
        "episode_status": "support_only" if support_only else "ready",
        "episode_decline_reason": (
            f"evidence_policy:{decline_reason}" if support_only else None
        ),
        "episode_prompt_version": EPISODE_PROMPT_VERSION,
        "ui_format": ui_format,
        "tier": tier,
        "format_rationale": "adaptive_episode_contract",
        "shell_mode": "episode",
        "plan_trace": trace,
        "prompt_component_ids": prompt_ids,
        "assessment_block": "" if support_only else "DidactActivity",
        "assessment_item_type": None if support_only else certified_ids[0],
        "assessment_hint": (
            "" if support_only else "Use the exact server-certified evidence activity."
        ),
        "episode_certified_component_ids": list(certified_ids),
        "current_step": "direct_episode",
    }


# --------------------------------------------------------------------------- #
# Node 3: decide_formato
# --------------------------------------------------------------------------- #
#: ``ContentFunction`` -> el ``kind`` que ``ShapeSignal.instruction()`` sabe redactar.
_ROUTED_KINDS = {
    ContentFunction.CONTRASTAR: "contrast",
    ContentFunction.VARIAR: "variants",
    ContentFunction.EXPLORAR: "explore",
}


async def _route_function(state: NodeRuntimeState, node: dict, plan: ShapePlan) -> ShapePlan:
    """Antepone al plan la funcion que el router semantico reconozca (fases 3/4).

    Devuelve el plan intacto si la flag esta apagada, si el router no ve nada claro o si
    falla. **Se antepone y no se anade** porque ``MAX_HINTS`` corta a dos: una funcion
    reconocida por significado es mas especifica que "aqui hay una lista", asi que si
    compiten por la plaza gana la semantica. Esa es justamente la hipotesis que este
    prototipo esta midiendo.
    """
    # Import local, como en ``graph.py``: la flag se lee en cada llamada para que un test
    # pueda encenderla con monkeypatch sin reimportar el modulo.
    from src.config import settings

    if not settings.SEMANTIC_ROUTER:
        return plan
    source = str(state.get("source_context") or "")
    llm = await _make_llm(_uuid(state["org_id"]), "fast")
    function, _usage = await classify_function(
        title=str(node.get("title") or ""),
        summary=str(node.get("summary") or ""),
        source=source,
        llm=llm,
    )
    if function is None:
        return plan
    signal = ShapeSignal(kind=_ROUTED_KINDS[function], count=0, function=function)
    logger.info(
        "router semantico: nodo %s -> %s (%s)",
        node.get("id"),
        function.value,
        signal.block or "sin componente",
    )
    return ShapePlan(signals=(signal, *plan.signals), has_numbers=plan.has_numbers)


@runtime_node_error_wrapper("decide_formato")
async def decide_formato(state: NodeRuntimeState) -> dict:
    """Pick ``ui_format``, then the tier (§4.3).

    **The calibration period of §6.4 is a hard rule, and it short-circuits this node
    entirely:** with ``nodes_completed < 3`` there is no LLM call at all and the format is
    ``node.default_ui_format``. Not "the model is asked and ignored" — asked and ignored
    would still cost a call, and the reason for the rule is pedagogical, not economic: the
    learner has to build a mental map before the interface starts moving (the lesson of
    Office 2000's adaptive menus).

    **The shape of the material is read on every path, calibrating or not** (§4.2, defect
    of 2026-07-28). Until then the calibration branch chose the screen with *zero*
    knowledge of the content: ``default_ui_format`` is written by the schema agent when the
    course is created and never looked at again. Measured on the seeded courses, that is
    not a theoretical gap — ``Coordinacion con cocina y tiempos`` is declared ``chart`` and
    its section writes every figure as a word ("doce minutos", "dieciocho"), so there is
    not one digit for a chart to plot and the generator could only have invented them.

    Reading the source here does not weaken the calibration rule, and it is worth being
    precise about why: §6.4 freezes adaptation **to the learner**. A shape derived from the
    node's own material is the same for every learner and on every visit, so the interface
    still does not move under anyone. It also costs no call, which matters more than it
    looks — the free tier's ceiling is tokens per minute, and a second call to pick a shape
    would spend the quota the generation itself needs.
    """
    request_id = str(state["request_id"])
    node = state.get("node") or {}
    profile = state.get("profile") or {}
    node_state = state.get("node_state") or {}
    default_format = coerce_ui_format(node.get("default_ui_format"))
    #: Empty during calibration: no call was made, so there is nothing to account for.
    decide_tokens: dict[str, int] = {}

    plan = analyze_shape(
        source_context=str(state.get("source_context") or ""),
        summary=str(node.get("summary") or ""),
        headings=list(node.get("source_headings") or ()),
    )
    plan = await _route_function(state, node, plan)

    if is_calibrating(int(profile.get("nodes_completed") or 0)):
        ui_format, correction = refine_format(
            default_format,
            plan,
            criticality=str(node.get("criticality") or "recommended"),
        )
        tier = select_tier(ui_format)
        rationale = "calibracion: se usa el formato por defecto del nodo (§6.4)"
        if correction:
            rationale = f"calibracion, corregido: {correction}"
            logger.info(
                "Node %s declares default_ui_format=%r but %s; serving %r instead",
                node.get("id"),
                default_format,
                correction,
                ui_format,
            )
    else:
        org_id = _uuid(state["org_id"])
        llm = await _make_llm(org_id, "fast")
        preferences = normalize_learning_preferences(profile.get("learning_preferences"))
        prompt = build_format_prompt(
            title=str(node.get("title") or ""),
            summary=str(node.get("summary") or ""),
            outcome=node.get("outcome"),
            criticality=str(node.get("criticality") or "recommended"),
            default_ui_format=default_format,
            role_title=profile.get("role_title"),
            sector=profile.get("sector"),
            experience_level=str(profile.get("experience_level") or "unknown"),
            preset=str(profile.get("preset") or "standard"),
            effective_density=int(state.get("effective_density") or 3),
            scaffold_band=_effective_scaffold_band(state),
            vector_bucket=str(profile.get("vector_bucket") or ""),
            mastery=float(node_state.get("mastery") or 0.0),
            consecutive_failed=int(node_state.get("consecutive_failed") or 0),
            last_error_kind=node_state.get("last_error_kind"),
            source_has_numbers=_source_has_numbers(str(state.get("source_context") or "")),
            shape_summary=plan.summary if plan else "",
            presentation_preference=preferences.presentation.value,
            detail_preference=preferences.detail.value,
            image_preference=preferences.images.value,
        )
        started = time.monotonic()
        raw, usage = await llm.complete_with_usage(
            FORMAT_DECIDER_SYSTEM,
            prompt,
            temperature=DECIDE_TEMPERATURE,
            max_tokens=DECIDE_MAX_TOKENS,
            json_mode=True,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        payload = parse_json_response(raw)
        decided = payload.get("ui_format") if isinstance(payload, dict) else None
        rationale = str(payload.get("rationale") or "") if isinstance(payload, dict) else ""
        ui_format = coerce_ui_format(decided, default_format)
        tier = select_tier(ui_format)
        await log_usage(
            async_session_factory,
            org_id=org_id,
            user_id=state.get("user_id"),
            use_case=DECIDE_USE_CASE,
            purpose=purpose_for("fast"),
            model=getattr(llm, "model", "unknown"),
            tier="fast",
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            duration_ms=duration_ms,
        )
        if usage.reason:
            # An explicit, greppable gap. `llm_usage_log` with NULL tokens and no
            # explanation reads like an accounting bug months later; this says which
            # provider (or which fixture run) is the one that reported nothing.
            logger.info(
                "No token accounting for decide_formato on %s: %s",
                getattr(llm, "model", "unknown"),
                usage.reason,
            )
        decide_tokens = {
            name: value
            for name, value in (
                ("tokens_in", usage.tokens_in),
                ("tokens_out", usage.tokens_out),
            )
            if value is not None
        }

    # Resolve execution before assessment: live Didact shortlist must not inject QuizItem.
    from src.agents.runtime.shadow_plan import build_shadow_plan_trace
    from src.config import settings
    from src.personalization.selection_policy import (
        SelectionExecution,
        runtime_execution,
    )

    requested_execution = (
        state.get("selection_execution")
        or (
            settings.RUNTIME_SELECTION_EXECUTION
            if settings.RUNTIME_COMPONENT_SHORTLIST
            else SelectionExecution.OFF
        )
    )
    requested_strategy = (
        state.get("selection_strategy") or settings.RUNTIME_SELECTION_STRATEGY
    )
    effective_execution = runtime_execution(
        requested_execution, requested_strategy
    )
    didact_live = (
        settings.RUNTIME_COMPONENT_SHORTLIST
        and effective_execution is SelectionExecution.LIVE
    )

    # Cómo se verifica el nodo: determinista, propiedad del nodo (no del aprendiz), estable
    # en cada visita. En live Didact la rotación apunta a actividades, no a QuizItem.
    assessment = plan_assessment(
        plan,
        ui_format=ui_format,
        node_id=str(node.get("id") or ""),
        didact=didact_live,
        course_id=str(state.get("course_id") or ""),
        position=node.get("position"),
    )
    scheme = plan_screen_scheme(plan, assessment, ui_format=ui_format)
    shape_functions = list(
        dict.fromkeys(signal.function.value for signal in plan.signals)
    )

    shadow_state = dict(state)
    shadow_state.update(
        {
            "ui_format": ui_format,
            "tier": tier,
            "shape_functions": shape_functions,
            "shape_summary": plan.summary,
            "assessment_block": assessment.block,
            "assessment_item_type": assessment.item_type,
            "concept_block": scheme.concept_block,
        }
    )
    plan_trace = build_shadow_plan_trace(
        shadow_state,
        mode=effective_execution.value,
        selection_strategy=requested_strategy,
        selection_execution=requested_execution,
    )
    prompt_component_ids = (
        list(plan_trace.get("prompt_component_ids") or ())
        if effective_execution is SelectionExecution.LIVE
        else []
    )

    await publish_step(request_id, "decide_formato", STEP_MESSAGES["decide_formato"])
    await sse.publish(
        node_channel(request_id), "ui_format", {"format": ui_format, "tier": tier}
    )
    return {
        "ui_format": ui_format,
        "tier": tier,
        "format_rationale": rationale,
        "assessment_block": assessment.block,
        "assessment_item_type": assessment.item_type,
        "assessment_hint": assessment.instruction(),
        "concept_block": scheme.concept_block,
        "screen_scheme": scheme.instruction(),
        # Computed once here and carried, so `genera_ui` and its one repair attempt read
        # the same analysis. Re-deriving it in the retry would re-scan the source for a
        # result that cannot have changed.
        "shape_hints": list(plan.hints(ui_format)),
        "shape_summary": plan.summary,
        "shape_functions": shape_functions,
        "plan_trace": plan_trace,
        "prompt_component_ids": prompt_component_ids,
        "current_step": "decide_formato",
        # Carried so `node_renders.tokens_*` is the cost of the *render*, not of one of the
        # two calls that produced it. `genera_ui` adds its own on top, retries included.
        **decide_tokens,
    }


# --------------------------------------------------------------------------- #
# Node 4: author_activity (optional, fail-open)
# --------------------------------------------------------------------------- #
def _activity_candidates(state: NodeRuntimeState) -> tuple[str, ...]:
    """Didact ids selected by the planner whose renderer is the generic activity host."""

    from src.personalization.didact_catalog import load_didact_catalog

    trace = state.get("plan_trace") or {}
    shadow = trace.get("shadow") if isinstance(trace, dict) else None
    ranked = shadow.get("component_candidates") if isinstance(shadow, dict) else None
    selection = trace.get("selection") if isinstance(trace, dict) else None
    policy_trace = (
        selection.get("policy_trace") if isinstance(selection, dict) else None
    )
    selected_ids = (
        tuple(policy_trace.get("selected_ids") or ())
        if isinstance(policy_trace, dict)
        and selection.get("effective_execution") == "live"
        else ()
    )
    if selected_ids:
        by_id = {
            item.get("component_id"): item
            for item in ranked or ()
            if isinstance(item, dict)
        }
        ranked = tuple(
            by_id[candidate_id]
            for candidate_id in selected_ids
            if candidate_id in by_id
        )
    catalog = load_didact_catalog().by_type_id
    selected: list[str] = []
    for item in ranked or ():
        component_id = item.get("component_id") if isinstance(item, dict) else None
        component = catalog.get(component_id) if isinstance(component_id, str) else None
        if component is None or component.renderer_symbol != "DidactActivity":
            continue
        if not component.llm_emittable:
            continue
        selected.append(component.type_id)
        if len(selected) >= 5:
            break
    preferred = state.get("assessment_item_type")
    if isinstance(preferred, str):
        component = catalog.get(preferred)
        if (
            component is not None
            and component.renderer_symbol == "DidactActivity"
            and component.llm_emittable
        ):
            selected = [preferred, *[item for item in selected if item != preferred]]
    return tuple(dict.fromkeys(selected))


_LEGACY_ASSESSMENT_BLOCKS = frozenset({"QuizItem", "DragOrder"})
_DIRECT_DIDACT_CLOSERS = (
    "Flashcard",
    "HintReveal",
    "DidactGlossary",
    "DidactTimeline",
    "DidactWorkedExample",
)


def _prompt_assessment_required(state: NodeRuntimeState) -> tuple[str, ...]:
    """Components the scoped prompt must include so verification can close the screen.

    Prepared activities cross the neutral ``LearningExperience`` boundary. If optional
    authoring declines, a concrete-case ``QuizItem`` remains evaluable without inventing
    an activity id or exposing a reveal card.
    """

    block = str(state.get("assessment_block") or "")
    if block == "DidactActivity":
        if isinstance(state.get("authored_activity"), dict):
            return ("LearningExperience",)
        return ("QuizItem",)
    if block in _DIRECT_DIDACT_CLOSERS:
        return (block,)
    if block in _LEGACY_ASSESSMENT_BLOCKS:
        return (block,)
    return ()


def _effective_assessment_hint(state: NodeRuntimeState, required: tuple[str, ...]) -> str:
    """Keep the user prompt aligned with the closer that will actually be in scope."""

    hint = str(state.get("assessment_hint") or "")
    block = str(state.get("assessment_block") or "")
    if block != "DidactActivity" and block not in _DIRECT_DIDACT_CLOSERS:
        return hint
    if isinstance(state.get("authored_activity"), dict):
        return (
            "VERIFICA con LearningExperience usando exactamente la referencia neutral "
            "preparada por el servidor; no inventes ids ni definiciones."
        )
    closer = required[0] if required else "QuizItem"
    if closer == "QuizItem":
        return AssessmentPlan(block="QuizItem", item_type="test").instruction()
    return (
        f"VERIFICA con {closer}. El concepto ensena con un caso o una grafica; "
        f"{closer} es otro encargo del puesto."
    )


def _effective_screen_scheme(
    state: NodeRuntimeState, required: tuple[str, ...]
) -> str:
    """Rebuild the scheme if authoring declined and the closer changed."""

    concept = str(state.get("concept_block") or "")
    if not concept:
        return str(state.get("screen_scheme") or "")
    stored_practice = str(state.get("assessment_block") or "")
    closer = stored_practice
    item_type = state.get("assessment_item_type")
    if stored_practice == "DidactActivity":
        if isinstance(state.get("authored_activity"), dict):
            closer = "LearningExperience"
        else:
            closer = required[0] if required else "QuizItem"
            item_type = "test" if closer == "QuizItem" else None
    return ScreenScheme(
        concept_block=concept,
        practice_block=closer,
        practice_item_type=item_type,
    ).instruction()


async def author_activity(state: NodeRuntimeState) -> dict:
    """Materialise a rich activity before OpenUI sees it; decline safely.

    This node intentionally does not use ``runtime_node_error_wrapper``. Activity
    authoring is an optional enrichment: a malformed fixture, provider error or stale
    pack removes DidactActivity from the scoped prompt. The screen then falls back to a
    concrete-case ``QuizItem`` rather than a reveal-only pseudo-assessment.
    """

    episode_payload = state.get("episode_brief")
    if isinstance(episode_payload, dict):
        certified = tuple(state.get("episode_certified_component_ids") or ())
        # The evidence contract is the server-owned authority for adaptive episodes.
        # Legacy planning may prefer a different Didact exercise shape, but it cannot
        # veto or replace the component whose scorer was actually certified.
        candidates = certified[:1]
    else:
        candidates = _activity_candidates(state)[:1]
    if not candidates or "DidactActivity" not in (state.get("prompt_component_ids") or ()):
        if isinstance(episode_payload, dict):
            return {
                "authored_activity": None,
                "activity_authoring_status": "declined:not_certified",
                "episode_brief": None,
                "episode_status": "declined",
                "episode_decline_reason": "activity_authoring:not_certified",
            }
        return {"authored_activity": None, "activity_authoring_status": "not_requested"}

    # Prefer immutable work prepared while the course was validated. The first producer
    # currently approved for this assessment seam is the validated single-choice probe.
    prepared = None
    org_id = _uuid(state["org_id"])
    node_id = _uuid(state["node_id"])
    if not isinstance(episode_payload, dict) and candidates[0] == "didact.quiz.single-choice":
        try:
            async with async_session_factory() as db:
                prepared = (
                    await db.execute(
                        select(
                            ImplementationBinding,
                            ExperienceVariant,
                            ExperienceIntent,
                            ActivityDefinition,
                        )
                        .join(
                            ExperienceVariant,
                            ExperienceVariant.id == ImplementationBinding.variant_id,
                        )
                        .join(
                            ExperienceIntent,
                            ExperienceIntent.id == ExperienceVariant.intent_id,
                        )
                        .join(
                            ActivityDefinition,
                            ActivityDefinition.id
                            == ImplementationBinding.activity_definition_id,
                        )
                        .where(
                            ImplementationBinding.org_id == org_id,
                            ExperienceIntent.org_id == org_id,
                            ExperienceIntent.node_id == node_id,
                            ExperienceIntent.intent.in_(
                                ("knowledge_check", "guided_practice")
                            ),
                            ActivityDefinition.enabled.is_(True),
                        )
                        .order_by(
                            ExperienceIntent.intent.desc(),
                            ImplementationBinding.is_fallback.asc(),
                            ImplementationBinding.binding_key.asc(),
                        )
                        .limit(1)
                    )
                ).first()
        except Exception:
            # Legacy/unit environments may not have migration 0016 yet. Preserve the
            # existing authoring fallback until migration rollout is complete.
            logger.info("prepared_experience_unavailable", exc_info=True)
    if prepared is not None:
        binding, _variant, intent, activity = prepared
        return {
            "authored_activity": {
                "activity_id": str(activity.id),
                "component_id": activity.component_id,
                "binding_id": str(binding.id),
                "experience_id": str(binding.id),
                "implementation_ref": (
                    f"{binding.implementation_id}@{binding.implementation_version}"
                ),
                "definition_ref": binding.definition_ref,
                "intent_id": str(intent.id),
            },
            "activity_authoring_status": "prepared",
            "prompt_component_ids": [
                "LearningExperience" if value == "DidactActivity" else value
                for value in state.get("prompt_component_ids") or ()
            ],
        }

    # Legacy migration fallback: the authoring prompt carries one validator-owned schema.
    # Keep selection and the server-side allow-list identical so a completion cannot switch
    # to a candidate whose contract it was never shown.
    request_id = str(state["request_id"])
    await publish_step(request_id, "author_activity", STEP_MESSAGES["author_activity"])
    usage = None
    started = time.monotonic()
    try:
        course_id = _uuid(state["course_id"])
        render_id = _uuid(state["render_id"])
        atom_ids = tuple(str(value) for value in state.get("knowledge_atom_ids") or ())
        evidence_ids = tuple(str(value) for value in state.get("knowledge_evidence_ids") or ())
        allowed_refs = (*atom_ids, *evidence_ids)
        if not allowed_refs:
            if isinstance(episode_payload, dict):
                from src.schemas.episode_contracts import EpisodeBrief
                from src.services.episode_policy import degrade_episode_brief_to_support

                support = degrade_episode_brief_to_support(
                    EpisodeBrief.model_validate(episode_payload),
                    decline_reason="grounded_authoring_refs_unavailable",
                )
                support_prompt_ids = [
                    value
                    for value in state.get("prompt_component_ids") or ()
                    if value in _SUPPORT_PROMPT_COMPONENT_IDS
                ]
                plan_trace = dict(state.get("plan_trace") or {})
                plan_trace["prompt_component_ids"] = support_prompt_ids
                plan_trace["renderer_selection"] = (
                    "planner-unscored" if support_prompt_ids else "base-shell"
                )
                return {
                    "authored_activity": None,
                    "activity_authoring_status": "support_only:empty_source_refs",
                    "episode_brief": support.model_dump(mode="json"),
                    "episode_status": "support_only",
                    "episode_decline_reason": "grounded_authoring_refs_unavailable",
                    "shell_mode": "episode",
                    "ui_format": "explanation",
                    "tier": select_tier("explanation"),
                    "assessment_block": "",
                    "assessment_item_type": None,
                    "assessment_hint": "",
                    "prompt_component_ids": support_prompt_ids,
                    "episode_certified_component_ids": [],
                    "plan_trace": plan_trace,
                }
            return {
                "authored_activity": None,
                "activity_authoring_status": "declined:empty_source_refs",
                "prompt_component_ids": [
                    value
                    for value in state.get("prompt_component_ids") or ()
                    if value != "DidactActivity"
                ],
            }
        system, user = build_activity_authoring_prompts(
            candidates=candidates,
            title=str((state.get("node") or {}).get("title") or ""),
            outcome=(state.get("node") or {}).get("outcome"),
            source_context=str(state.get("source_context") or ""),
            allowed_source_refs=allowed_refs,
        )
        # Activity definition is small structured work; it always uses the fast tier even
        # when the eventual screen needs the heavy presentation tier.
        llm = await _make_llm(org_id, "fast")
        raw, usage = await llm.complete_with_usage(
            system,
            user,
            temperature=0.2,
            max_tokens=1600,
            json_mode=True,
        )
        await log_usage(
            async_session_factory,
            org_id=org_id,
            user_id=state.get("user_id"),
            use_case="runtime_activity_authoring",
            purpose=purpose_for("fast"),
            model=getattr(llm, "model", "unknown"),
            tier="fast",
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        parsed_draft = parse_json_response(raw)
        if not isinstance(parsed_draft, dict):
            raise ValueError("activity authoring response must be an object")
        draft = authoring_draft_with_server_refs(
            parsed_draft,
            allowed_source_refs=allowed_refs,
        )
        async with async_session_factory() as db:
            pack = None
            pack_hash = str(state.get("knowledge_pack_hash") or "")
            if pack_hash:
                pack = await NodeKnowledgePackRepository(db).find_by_hash(
                    node_id=node_id, pack_hash=pack_hash
                )
            materialized = await materialize_authored_activity(
                ActivityDefinitionService(
                    ActivityDefinitionRepository(db), ActivityStateRepository(db)
                ),
                org_id=org_id,
                course_id=course_id,
                node_id=node_id,
                render_id=render_id,
                knowledge_pack_id=pack.id if pack is not None else None,
                pack_hash=pack_hash,
                draft=draft,
                allowed_component_ids=candidates,
                allowed_source_refs=allowed_refs,
            )
            await db.commit()
        return {
            "authored_activity": materialized.model_dump(mode="json"),
            "activity_authoring_status": "ready",
            "prompt_component_ids": [
                "LearningExperience" if value == "DidactActivity" else value
                for value in state.get("prompt_component_ids") or ()
            ],
            # Keep node_renders and the evaluation harness honest: authoring is part of
            # the on-the-fly render cost, not an invisible preliminary call.
            "tokens_in": (
                int(state.get("tokens_in") or 0) + int(usage.tokens_in or 0)
                if state.get("tokens_in") is not None or usage.tokens_in is not None
                else None
            ),
            "tokens_out": (
                int(state.get("tokens_out") or 0) + int(usage.tokens_out or 0)
                if state.get("tokens_out") is not None or usage.tokens_out is not None
                else None
            ),
            "duration_ms": int(state.get("duration_ms") or 0)
            + int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        logger.warning("activity_authoring_declined %s", type(exc).__name__, exc_info=True)
        accounting: dict[str, Any] = {}
        if usage is not None:
            accounting = {
                "tokens_in": (
                    int(state.get("tokens_in") or 0) + int(usage.tokens_in or 0)
                    if state.get("tokens_in") is not None or usage.tokens_in is not None
                    else None
                ),
                "tokens_out": (
                    int(state.get("tokens_out") or 0) + int(usage.tokens_out or 0)
                    if state.get("tokens_out") is not None or usage.tokens_out is not None
                    else None
                ),
                "duration_ms": int(state.get("duration_ms") or 0)
                + int((time.monotonic() - started) * 1000),
            }
        return {
            "authored_activity": None,
            "activity_authoring_status": f"declined:{type(exc).__name__}",
            "episode_brief": None if isinstance(episode_payload, dict) else episode_payload,
            "episode_status": (
                "declined" if isinstance(episode_payload, dict) else state.get("episode_status")
            ),
            "episode_decline_reason": (
                f"activity_authoring:{type(exc).__name__}"
                if isinstance(episode_payload, dict)
                else state.get("episode_decline_reason")
            ),
            "prompt_component_ids": [
                value
                for value in state.get("prompt_component_ids") or ()
                if value != "DidactActivity"
            ],
            **accounting,
        }


def _source_with_authored_activity(state: NodeRuntimeState) -> str:
    """Add only the opaque id and public projection to the UI-generation context."""

    source = str(state.get("source_context") or "")
    activity = state.get("authored_activity")
    if not isinstance(activity, dict):
        return source
    instruction = {
        "experience_id": activity.get("experience_id") or activity.get("activity_id"),
        "implementation_ref": activity.get("implementation_ref")
        or f"{activity.get('component_id')}@1",
        "definition_ref": activity.get("definition_ref") or activity.get("activity_id"),
    }
    return (
        source.rstrip()
        + "\n\n## Experiencia preparada por el servidor\n"
        + "Incluye exactamente LearningExperience(experience_id, implementation_ref, "
        + "definition_ref) usando estos valores; no inventes otro id: "
        + json.dumps(instruction, ensure_ascii=False, sort_keys=True)
        + "\n"
    )


# --------------------------------------------------------------------------- #
# Node 5: genera_ui
# --------------------------------------------------------------------------- #
@runtime_node_error_wrapper("genera_ui")
async def genera_ui(state: NodeRuntimeState) -> dict:
    """Ask the active backend's dialect from the tier's model, streaming.

    The system prompt is the **generated** artefact (``library.prompt()``) plus the answer-key
    protocol; see ``src/llm/prompts/runtime.py``. On a retry it is the repair prompt, and the
    user turn carries the validator's own messages, because "line 4: expected ')'" is
    actionable and "invalid program" is not.

    Streaming is not decoration: §9.2 promises a ``ui_block`` event per completed component,
    which is what lets the browser replace the skeleton progressively. ``parse_partial`` is
    only run when the accumulated text has gained a line break — one declaration per line is
    the frozen grammar, so a component cannot complete anywhere else, and this keeps the
    per-chunk cost off the hot path.
    """
    request_id = str(state["request_id"])
    org_id = _uuid(state["org_id"])
    node = state.get("node") or {}
    profile = state.get("profile") or {}
    node_state = state.get("node_state") or {}
    tier = str(state.get("tier") or "fast")
    ui_format = coerce_ui_format(state.get("ui_format"))
    retry = int(state.get("retry_count") or 0)

    llm = await _make_llm(org_id, tier)
    mastery = float(node_state.get("mastery") or 0.0)
    threshold = threshold_for(
        node.get("criticality") or "recommended", node.get("mastery_threshold")
    )

    shape_hints = list(state.get("shape_hints") or ())

    from src.config import settings

    episode_payload = state.get("episode_brief")
    adaptive_episode = isinstance(episode_payload, dict)
    assessment_required = _prompt_assessment_required(state)
    scoped_prompt, scope = resolve_runtime_prompt(
        state.get("prompt_component_ids") or (),
        additional_required=assessment_required,
        enabled=settings.RUNTIME_COMPONENT_SHORTLIST or adaptive_episode,
    )
    assessment_block = str(state.get("assessment_block") or "")
    didact_verification = (
        "LearningExperience" in assessment_required
        or assessment_block in _DIRECT_DIDACT_CLOSERS
    )

    if retry and adaptive_episode:
        system = episode_ui_repair_system(scoped_prompt)
        user_prompt = build_episode_repair_prompt(
            episode=episode_payload,
            source_context=_source_with_authored_activity(state),
            previous=str(state.get("raw_dsl") or ""),
            errors=list(state.get("validation_errors") or []),
        )
    elif retry:
        system = ui_repair_system(scoped_prompt, didact_verification=didact_verification)
        user_prompt = build_repair_prompt(
            previous=str(state.get("raw_dsl") or ""),
            errors=list(state.get("validation_errors") or []),
            ui_format=ui_format,
            shape_hints=shape_hints,
            screen_scheme=_effective_screen_scheme(state, assessment_required),
        )
    elif adaptive_episode:
        system = episode_ui_generator_system(scoped_prompt)
        user_prompt = build_episode_ui_prompt(
            episode=episode_payload,
            source_context=_source_with_authored_activity(state),
        )
    else:
        system = ui_generator_system(
            scoped_prompt, didact_verification=didact_verification
        )
        preferences = normalize_learning_preferences(profile.get("learning_preferences"))
        user_prompt = build_ui_prompt(
            title=str(node.get("title") or ""),
            summary=str(node.get("summary") or ""),
            outcome=node.get("outcome"),
            criticality=str(node.get("criticality") or "recommended"),
            ui_format=ui_format,
            effective_density=int(state.get("effective_density") or 3),
            scaffold_band=_effective_scaffold_band(state),
            role_title=profile.get("role_title"),
            sector=profile.get("sector"),
            experience_level=str(profile.get("experience_level") or "unknown"),
            preset=str(profile.get("preset") or "standard"),
            target_bloom=target_bloom(mastery, threshold),
            last_error_kind=node_state.get("last_error_kind"),
            consecutive_failed=int(node_state.get("consecutive_failed") or 0),
            consecutive_correct=int(node_state.get("consecutive_correct") or 0),
            tutor_signals=tuple(profile.get("tutor_signals") or ()),
            source_context=_source_with_authored_activity(state),
            shape_hints=shape_hints,
            assessment_hint=_effective_assessment_hint(state, assessment_required),
            screen_scheme=_effective_screen_scheme(state, assessment_required),
            presentation_preference=preferences.presentation.value,
            detail_preference=preferences.detail.value,
            image_preference=preferences.images.value,
            longitudinal_support_level=_history_support_level(state),
        )

    await publish_step(request_id, "genera_ui", STEP_MESSAGES["genera_ui"])
    started = time.monotonic()
    usage_out: dict[str, Any] = {}
    raw = await _stream_program(
        llm,
        system,
        user_prompt,
        request_id=request_id,
        ui_format=ui_format,
        tier=tier,
        backend_name=str(state.get("backend") or "openui"),
        usage_out=usage_out,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    tokens_in = usage_out.get("tokens_in")
    tokens_out = usage_out.get("tokens_out")

    await log_usage(
        async_session_factory,
        org_id=org_id,
        user_id=state.get("user_id"),
        use_case=UI_USE_CASE,
        purpose=purpose_for(tier),
        model=getattr(llm, "model", "unknown"),
        tier=tier,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        duration_ms=duration_ms,
    )
    if tokens_in is None and tokens_out is None:
        # The expensive half of the render is the one that streams, so a provider that
        # cannot report usage on a stream is the difference between a measured cost model
        # and an estimated one. Named here rather than left as two NULLs (§9.3).
        logger.info(
            "No token accounting for genera_ui on %s: %s",
            getattr(llm, "model", "unknown"),
            usage_out.get("reason") or "unknown",
        )
    result = {
        "raw_dsl": raw,
        "model": getattr(llm, "model", "unknown"),
        "duration_ms": duration_ms + int(state.get("duration_ms") or 0),
        "tokens_in": _accumulate(state.get("tokens_in"), tokens_in),
        "tokens_out": _accumulate(state.get("tokens_out"), tokens_out),
        "current_step": "genera_ui",
    }
    if scope is not None:
        plan_trace = dict(state.get("plan_trace") or {})
        plan_trace["prompt_scope"] = {
            "version": scope.version,
            "digest": scope.digest,
            "prompt_sha256": scope.prompt_sha256,
            "included_component_ids": list(scope.included_component_ids),
        }
        result["plan_trace"] = plan_trace
    return result


def _accumulate(previous: int | None, addition: int | None) -> int | None:
    """Sum two token counts, keeping ``None`` when nothing was ever measured.

    ``0`` and ``None`` are different answers: ``0`` claims the call was free, ``None``
    says nobody counted. Coalescing to ``0`` would make the §9.3 ratio look measured.
    """
    if previous is None and addition is None:
        return None
    return int(previous or 0) + int(addition or 0)


async def _stream_program(
    llm: Any,
    system: str,
    user_prompt: str,
    *,
    request_id: str,
    ui_format: str,
    tier: str,
    backend_name: str,
    usage_out: dict[str, Any] | None = None,
) -> str:
    """Collect the completion, publishing ``ui_block`` as components complete (§9.2)."""
    backend = get_render_backend(backend_name)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    chunks: list[str] = []
    announced: set[str] = set()
    async for delta in llm.stream(
        messages,
        temperature=UI_TEMPERATURE,
        max_tokens=ui_max_tokens(tier),
        usage_out=usage_out,
    ):
        chunks.append(delta)
        if "\n" not in delta:
            continue
        program_so_far, _ = split_answer_key("".join(chunks))
        try:
            partial = backend.parse_partial(program_so_far, ui_format=ui_format)
        except Exception:  # noqa: BLE001 - parse_partial promises not to raise; belt anyway
            continue
        for component in partial.components:
            if component.id in announced:
                continue
            announced.add(component.id)
            await sse.publish(
                node_channel(request_id),
                "ui_block",
                {"component": component.model_dump()},
            )
    return "".join(chunks)


@runtime_node_error_wrapper("genera_ui")
async def genera_ui_multi(state: NodeRuntimeState) -> dict:
    """Multi-agent version of genera_ui. Same signature, same output.

    Four agents: Blueprint -> Content Writer + Interaction Designer (parallel) -> Assembler.
    On retry, falls back to the monolithic genera_ui (the repair prompt is optimized for it).

    The retry calls ``genera_ui.__wrapped__`` (the un-decorated function) to avoid double
    error-wrapping: this function already has ``@runtime_node_error_wrapper("genera_ui")``,
    and calling the decorated ``genera_ui`` would mark the render ``failed`` and publish an
    error SSE event before the graph's own fallback has a chance to run.
    """
    from src.agents.runtime.agents.assembler import assemble
    from src.agents.runtime.agents.blueprint import run_blueprint
    from src.agents.runtime.agents.content_writer import run_content_writer
    from src.agents.runtime.agents.interaction_designer import run_interaction_designer
    from src.agents.runtime.screen_scheme import ScreenScheme

    request_id = str(state["request_id"])
    org_id = _uuid(state["org_id"])
    node = state.get("node") or {}
    profile = state.get("profile") or {}
    node_state = state.get("node_state") or {}
    tier = str(state.get("tier") or "fast")
    ui_format = coerce_ui_format(state.get("ui_format"))
    retry = int(state.get("retry_count") or 0)

    # On retry, fall back to the monolithic genera_ui (repair prompt is optimized for it).
    # __wrapped__ bypasses the inner error decorator — this function's own wrapper handles it.
    if retry:
        return await genera_ui.__wrapped__(state)  # type: ignore[attr-defined]

    llm = await _make_llm(org_id, tier)
    mastery = float(node_state.get("mastery") or 0.0)
    threshold = threshold_for(
        node.get("criticality") or "recommended", node.get("mastery_threshold")
    )

    await publish_step(request_id, "genera_ui", "Disenando la estructura...")
    started = time.monotonic()

    # El plan de evaluacion (decidido en decide_formato) se reconstruye aqui para imponerlo
    # en el blueprint. Reconstruir desde el estado en vez de recalcular mantiene una sola
    # fuente de verdad: la rotacion ya quedo fijada por node_id.
    assessment = None
    if state.get("assessment_block"):
        assessment = AssessmentPlan(
            block=str(state["assessment_block"]),
            item_type=state.get("assessment_item_type"),
        )
    scheme = None
    if state.get("concept_block") and assessment is not None:
        scheme = ScreenScheme(
            concept_block=str(state["concept_block"]),
            practice_block=assessment.block,
            practice_item_type=assessment.item_type,
        )

    # --- Agent 1: Blueprint ---
    preferences = normalize_learning_preferences(profile.get("learning_preferences"))
    blueprint = await run_blueprint(
        title=str(node.get("title") or ""),
        summary=str(node.get("summary") or ""),
        outcome=node.get("outcome"),
        criticality=str(node.get("criticality") or "recommended"),
        ui_format=ui_format,
        effective_density=int(state.get("effective_density") or 3),
        scaffold_band=_effective_scaffold_band(state),
        role_title=profile.get("role_title"),
        sector=profile.get("sector"),
        experience_level=str(profile.get("experience_level") or "unknown"),
        target_bloom=target_bloom(mastery, threshold),
        shape_hints=list(state.get("shape_hints") or ()),
        siblings=list(state.get("siblings") or ()),
        llm=llm,
        assessment=assessment,
        scheme=scheme,
        presentation_preference=preferences.presentation.value,
        detail_preference=preferences.detail.value,
        image_preference=preferences.images.value,
    )

    await publish_step(request_id, "genera_ui", "Escribiendo el contenido...")

    # --- Agents 2+3: Content Writer + Interaction Designer (PARALLEL) ---
    content_coro = run_content_writer(
        blueprint=blueprint,
        title=str(node.get("title") or ""),
        summary=str(node.get("summary") or ""),
        source_context=str(state.get("source_context") or ""),
        role_title=profile.get("role_title"),
        sector=profile.get("sector"),
        scaffold_band=_effective_scaffold_band(state),
        criticality=str(node.get("criticality") or "recommended"),
        siblings=list(state.get("siblings") or ()),
        llm=llm,
    )

    interaction_coro = None
    interaction_blocks = [b for b in blueprint.blocks if b.type in ("QuizItem", "DragOrder")]
    if interaction_blocks:
        interaction_coro = run_interaction_designer(
            blueprint=blueprint,
            content_declarations="",  # parallel: content not ready yet
            title=str(node.get("title") or ""),
            summary=str(node.get("summary") or ""),
            source_context=str(state.get("source_context") or ""),
            role_title=profile.get("role_title"),
            sector=profile.get("sector"),
            target_bloom=target_bloom(mastery, threshold),
            scaffold_band=_effective_scaffold_band(state),
            siblings=list(state.get("siblings") or ()),
            llm=llm,
        )

    # Execute in parallel
    if interaction_coro:
        content_output, interaction_output = await asyncio.gather(
            content_coro, interaction_coro
        )
    else:
        content_output = await content_coro
        interaction_output = None

    # --- Agent 4: Assembler (no LLM) ---
    raw_dsl, _answer_key = assemble(
        blueprint=blueprint,
        content_output=content_output,
        interaction_output=interaction_output,
        ui_format=ui_format,
    )

    duration_ms = int((time.monotonic() - started) * 1000)

    # Token accounting: the agents discard individual usage (the fixture system
    # reports None), so tokens_in/out stay at whatever decide_formato set.
    # When a real provider reports usage, the individual agents should propagate it.
    return {
        "raw_dsl": raw_dsl,
        "model": getattr(llm, "model", "unknown"),
        "duration_ms": duration_ms + int(state.get("duration_ms") or 0),
        "tokens_in": state.get("tokens_in"),
        "tokens_out": state.get("tokens_out"),
        "current_step": "genera_ui",
    }


# --------------------------------------------------------------------------- #
# Node 5: validate_ui
# --------------------------------------------------------------------------- #
@runtime_node_error_wrapper("validate_ui")
async def validate_ui(state: NodeRuntimeState) -> dict:
    """The gate: split the key, canonicalize, and refuse anything that does not hold.

    ``gate.canonicalize`` does size caps -> reactivity rejection -> ``backend.parse`` (the
    frozen grammar and the 7 contract rules of §5.2) -> ``serialize``. The second element it
    returns is the **only** text a browser may receive.

    A failure here is not an exception: it is a ``validation_errors`` list plus
    ``retry_count + 1``, which the router turns into either one repair attempt or the seed
    fallback. Failing loudly to the wrapper would skip the repair loop entirely.
    """
    raw = str(state.get("raw_dsl") or "")
    ui_format = coerce_ui_format(state.get("ui_format"))
    backend_name = str(state.get("backend") or "openui")
    await publish_step(
        str(state["request_id"]), "validate_ui", STEP_MESSAGES["validate_ui"]
    )

    program_text, answer_key = split_answer_key(raw)
    try:
        spec, program = canonicalize(
            program_text,
            ui_format=ui_format,
            backend=get_render_backend(backend_name),
        )
    except RenderError as exc:
        errors = list(getattr(exc, "errors", None) or [str(exc)])
        return {
            "ui_spec": None,
            "validation_errors": errors,
            "retry_count": int(state.get("retry_count") or 0) + 1,
            "current_step": "validate_ui",
        }

    assessment_block = str(state.get("assessment_block") or "")
    if (
        assessment_block == "DidactActivity"
        or assessment_block in _DIRECT_DIDACT_CLOSERS
    ):
        forbidden = sorted(
            {
                component.type
                for component in spec.components
                if component.type in {"QuizItem", "DragOrder"}
            }
        )
        if forbidden:
            return {
                "ui_spec": None,
                "validation_errors": [
                    "En modo Didact esta prohibido "
                    + " y ".join(forbidden)
                    + ": usa LearningExperience o un bloque Didact directo."
                ],
                "retry_count": int(state.get("retry_count") or 0) + 1,
                "current_step": "validate_ui",
            }

    key_problems = missing_answer_keys(spec, answer_key)
    if key_problems:
        return {
            "ui_spec": None,
            "validation_errors": key_problems,
            "retry_count": int(state.get("retry_count") or 0) + 1,
            "current_step": "validate_ui",
        }

    return {
        "ui_spec": spec.model_dump(),
        "program": program,
        "answer_key": prune_answer_key(spec, answer_key),
        "validation_errors": [],
        "current_step": "validate_ui",
    }


# --------------------------------------------------------------------------- #
# Node 6: persist_render
# --------------------------------------------------------------------------- #
@runtime_node_error_wrapper("persist_render")
async def persist_render(state: NodeRuntimeState) -> dict:
    """Write ``status='ready'`` with the canonical program and its provenance (§3.4)."""
    return await _persist(state, status=NodeRenderStatus.READY, step="persist_render")


# --------------------------------------------------------------------------- #
# Node 7: fallback_seed
# --------------------------------------------------------------------------- #
@runtime_node_error_wrapper("fallback_seed")
async def fallback_seed(state: NodeRuntimeState) -> dict:
    """The final safety net: the v1 seed lesson, rendered as ``Markdown`` (§9.3 level 4).

    Two deliberate departures from the one-line sketch in §4.2 ("un ``ui_spec`` de un solo
    bloque ``Markdown``"), both forced by rules this batch does not get to bend:

    * **A lead block comes first.** Contract rule 7 (§5.2) requires the first child of the
      root of an ``explanation`` spec to be a ``TextContent variant="lead"`` or a ``Callout``.
      A lone ``Markdown`` component is therefore not a valid ``explanation`` spec at all, and
      the node summary is exactly the "esto te sirve para X" slot that rule protects.
    * **The seed is split into up to four blocks.** One component is one line of dialect and
      ``MAX_LINE_BYTES`` is 4096, so a real lesson does not fit on one line. Splitting at
      paragraph boundaries keeps the whole gate applicable instead of special-casing it.
    """
    request_id = str(state["request_id"])
    node = state.get("node") or {}
    if not state.get("render_id"):
        # ``load_context`` failed before claiming a row, so there is no row to write and
        # nothing to serve. Say so **once**, with ``fallback: false``: telling the client to
        # re-request a render that cannot exist would loop it against a blank screen.
        await publish_error(
            request_id,
            "fallback_seed",
            "No se pudo preparar el nodo, asi que no hay nada que servir.",
            fallback=False,
        )
        return {"current_step": "failed"}

    seed_lesson_id = node.get("seed_lesson_id")
    content = ""

    if seed_lesson_id:
        async with async_session_factory() as db:
            lesson = await db.get(Lesson, _uuid(seed_lesson_id))
            content = (lesson.content or "") if lesson is not None else ""
    if not content.strip():
        content = str(state.get("source_context") or "").strip()
    if not content.strip():
        content = str(node.get("summary") or "")

    spec = build_fallback_spec(
        summary=str(node.get("summary") or node.get("title") or ""),
        content=content,
    )
    backend = get_render_backend(str(state.get("backend") or "openui"))
    program = backend.serialize(spec)

    await publish_step(request_id, "fallback_seed", STEP_MESSAGES["fallback_seed"])
    return await _persist(
        {
            **state,
            "ui_spec": spec.model_dump(),
            "program": program,
            "answer_key": {},
            "ui_format": "explanation",
        },
        status=NodeRenderStatus.FALLBACK,
        step="fallback_seed",
    )


def build_fallback_spec(*, summary: str, content: str) -> UISpec:
    """``Stack([lead, md1..mdN])`` — a valid ``explanation`` spec built by the server.

    ``Markdown`` is the one kit component the model may **not** emit (``llm_emittable`` is
    false) and that ``parse`` refuses: the asymmetry is the point, and this is the only
    author of it.
    """
    blocks = _split_markdown(content)
    components = [
        Component(
            id="lead",
            type="TextContent",
            props={"text": summary or "Contenido de respaldo.", "variant": "lead"},
        )
    ]
    child_ids = ["lead"]
    for index, block in enumerate(blocks, start=1):
        block_id = f"md{index}"
        components.append(
            Component(id=block_id, type="Markdown", props={"content": block})
        )
        child_ids.append(block_id)
    components.insert(
        0,
        Component(id="root", type="Stack", props={"gap": "md"}, children=child_ids),
    )
    return parse_spec(
        {
            "version": UISpec.VERSION,
            "format": "explanation",
            "root": "root",
            "components": [component.model_dump() for component in components],
        }
    )


def _split_markdown(content: str) -> list[str]:
    """Cut the seed into at most :data:`FALLBACK_MAX_BLOCKS` blocks at blank lines."""
    text = content.strip() or "Sin contenido de respaldo."
    blocks: list[str] = []
    remaining = text
    while remaining and len(blocks) < FALLBACK_MAX_BLOCKS:
        if len(remaining) <= FALLBACK_BLOCK_CHARS:
            blocks.append(remaining.strip())
            remaining = ""
            break
        head = remaining[:FALLBACK_BLOCK_CHARS]
        cut = head.rfind("\n\n")
        if cut < FALLBACK_BLOCK_CHARS // 3:
            cut = head.rfind("\n")
        if cut < FALLBACK_BLOCK_CHARS // 3:
            cut = head.rfind(" ")
        if cut <= 0:
            cut = FALLBACK_BLOCK_CHARS
        blocks.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        blocks[-1] = (blocks[-1] + "\n\n[...]").strip()
    return [block for block in blocks if block] or ["Sin contenido de respaldo."]


async def _persist(
    state: NodeRuntimeState | dict, *, status: NodeRenderStatus, step: str
) -> dict:
    """Shared tail of ``persist_render`` and ``fallback_seed``."""
    request_id = str(state["request_id"])
    render_id = state.get("render_id")
    if not render_id:
        raise ValueError("No node_renders row was claimed for this request")

    ui_format = coerce_ui_format(state.get("ui_format"))
    tier = str(state.get("tier") or select_tier(ui_format))
    spec = state.get("ui_spec") or {}
    program = str(state.get("program") or "")
    persisted_spec = dict(spec)
    from src.services.node_render_service import generation_provenance_for_state

    persisted_spec["generation"] = generation_provenance_for_state(
        state, fallback=step == "fallback_seed"
    )

    async with async_session_factory() as db:
        repo = NodeRenderRepository(db)
        render = await repo.get_by_id(_uuid(render_id))
        if render is None:
            raise ValueError(f"node_renders row {render_id} disappeared")
        await repo.mark_ready(
            render,
            ui_format=ui_format,
            ui_spec=persisted_spec,
            answer_key=dict(state.get("answer_key") or {}),
            dialect=program,
            catalog_version=catalog_version(),
            library_version=library_version(),
            model=str(state.get("model") or render.model),
            tier=tier,
            tokens_in=state.get("tokens_in"),
            tokens_out=state.get("tokens_out"),
            duration_ms=state.get("duration_ms"),
            status=status,
        )
        if not state.get("is_preview"):
            # Pin what was just written (§3.3 "Vision A"). Nothing else can, and that is
            # not an optimisation detail: ``NodeRenderService`` pins only on a *cache hit*
            # and ``GET /nodes/{id}/render`` recomputes nothing on purpose, so without this
            # the learner whose request paid for the generation would poll ``202`` forever
            # while everybody who arrived after them got the render for free. It is also
            # what makes ``POST /render {"force": true}`` visible: the refreshed row is
            # written under a salted key nobody will ever look up, so the pin is the only
            # way back to it.
            await NodeRenderService(db).pin(
                user_id=_uuid(str(state["user_id"])),
                node_id=_uuid(str(state["node_id"])),
                render=render,
                personalization_revision=int(
                    state.get("personalization_revision") or 0
                ),
            )
        await db.commit()

    if step == "persist_render":
        await publish_step(request_id, step, STEP_MESSAGES[step])
    await sse.publish(
        node_channel(request_id),
        "ui_done",
        {
            "render_id": str(render_id),
            "format": ui_format,
            "status": status.value,
        },
    )
    return {
        "render_id": str(render_id),
        "ui_format": ui_format,
        "catalog_version": catalog_version(),
        "library_version": library_version(),
        "current_step": step,
    }


# --------------------------------------------------------------------------- #
# Node 8: skip_node
# --------------------------------------------------------------------------- #
@runtime_node_error_wrapper("skip_node")
async def skip_node(state: NodeRuntimeState) -> dict:
    """The node was already mastered: announce it and spend nothing (§2).

    Nothing is written: ``learner_node_states.state`` is *already* ``mastered`` (that is what
    the gate read), and re-stamping it would move ``mastered_at`` for a visit that taught
    nothing.
    """
    request_id = str(state["request_id"])
    render_id = state.get("render_id")
    if render_id:
        # Hand the claimed cache_key back. Leaving it in `generating` would read like a
        # crashed worker for the cheapest outcome the pipeline has.
        async with async_session_factory() as db:
            repo = NodeRenderRepository(db)
            render = await repo.get_by_id(_uuid(render_id))
            if render is not None and render.status is NodeRenderStatus.GENERATING:
                await repo.release(render, "skipped: the node was already mastered")
            await db.commit()

    await sse.publish(
        node_channel(request_id), "node_skipped", {"reason": "mastered"}
    )
    return {"current_step": "skip_node"}


__all__ = [
    "FALLBACK_BLOCK_CHARS",
    "FALLBACK_MAX_BLOCKS",
    "RETRIEVAL_TOP_K",
    "STEP_MESSAGES",
    "author_activity",
    "build_fallback_spec",
    "decide_formato",
    "direct_episode",
    "fallback_seed",
    "genera_ui",
    "genera_ui_multi",
    "load_context",
    "load_source_context",
    "missing_answer_keys",
    "persist_render",
    "probe_gate",
    "prune_answer_key",
    "skip_node",
    "split_answer_key",
    "validate_ui",
]
