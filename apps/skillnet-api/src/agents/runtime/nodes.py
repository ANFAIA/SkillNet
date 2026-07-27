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

import time
import uuid
from typing import Any

from sqlalchemy import select

from src.agents.content.helpers import (
    FULL_TEXT_PAGE_THRESHOLD,
    assemble_chunk_text,
    estimate_pages,
)
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
    build_format_prompt,
    build_repair_prompt,
    build_ui_prompt,
    clip_source,
    signal_actions_for_node,
    ui_generator_system,
    ui_max_tokens,
    ui_repair_system,
)
from src.models import (
    Course,
    CourseNode,
    Document,
    Lesson,
    NodeRenderStatus,
    Organization,
    User,
)
from src.render.backends import get_render_backend
from src.render.errors import RenderError
from src.render.gate import canonicalize
from src.render.prompt import catalog_version, library_version
from src.render.spec import Component, UISpec, parse_spec
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.llm_usage_repo import log_usage
from src.repositories.node_render_repo import NodeRenderRepository
from src.services.learner_profile_service import is_calibrating
from src.services.mastery_service import MASTERED, target_bloom, threshold_for
from src.services.node_render_service import NodeRenderService, build_render_key

logger = get_logger(__name__)

#: Chunks retrieved for the ``chunked`` branch of ``load_context`` (§4.2).
RETRIEVAL_TOP_K = 8

#: A ``Markdown`` fallback block is capped well below ``MAX_LINE_BYTES`` (4096) because the
#: whole seed lesson lives on **one** line once it is serialized — escaped newlines and all.
FALLBACK_BLOCK_CHARS = 2800
#: Root fan-out is capped at 5 (rule 4) and the lead block takes one of them.
FALLBACK_MAX_BLOCKS = 4

STEP_MESSAGES: dict[str, str] = {
    "load_context": "Preparando el nodo...",
    "probe_gate": "Comprobando lo que ya dominas...",
    "decide_formato": "Eligiendo la forma de la leccion...",
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

    if estimate_pages(document) <= FULL_TEXT_PAGE_THRESHOLD and document.full_text:
        return clip_source(document.full_text)

    repo = DocumentChunkRepository(db)
    embedder = maybe_fixture_embedder(resolve_embedding_config(await _org_settings(db, org_id)))
    query = f"{node.title}\n{node.summary}"
    embedding = await embedder.embed_query(query)
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
    problems: list[str] = []
    for component in spec.components:
        if component.type != "QuizItem":
            continue
        item_id = str(component.props.get("item_id") or component.id)
        entry = answer_key.get(item_id)
        if not isinstance(entry, dict) or not _has_solution(entry):
            problems.append(
                f"QuizItem {item_id!r} tiene enunciado pero no llega su solucion en el "
                f"bloque {ANSWER_KEY_SENTINEL}"
            )
    return problems


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
        user = await db.get(User, user_id)
        profile = await LearnerProfileRepository(db).get_by_user(user_id)
        node_state = await LearnerNodeStateRepository(db).get_by_user_and_node(
            user_id, node_id
        )
        org_settings = await _org_settings(db, org_id)
        source_context = await load_source_context(db, node, org_id)

        key = build_render_key(
            node=node,
            course=course,
            profile=profile,
            node_state=node_state,
            accessibility=dict(getattr(user, "accessibility", None) or {}),
            model_key=runtime_model_key(org_settings),
            is_preview=bool(state.get("is_preview")),
            # The service already salted the preview key; reuse it verbatim so the row it
            # claimed and the row this graph writes are the same row.
            preview_salt=None,
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
            "title": node.title,
            "summary": node.summary,
            "outcome": node.outcome,
            "criticality": _plain(node.criticality),
            "default_ui_format": default_format,
            "mastery_threshold": float(node.mastery_threshold or 0.8),
            "seed_lesson_id": str(node.seed_lesson_id) if node.seed_lesson_id else None,
            "source_headings": list(node.source_headings or []),
        }
        profile_payload = {
            # `goal` is deliberately absent: it never reaches the LLM (§3.3).
            "role_title": getattr(profile, "role_title", None),
            "sector": getattr(profile, "sector", None),
            "experience_level": _plain(getattr(profile, "experience_level", "unknown")),
            "preset": _plain(getattr(profile, "preset", "standard")),
            "nodes_completed": int(getattr(profile, "nodes_completed", 0) or 0),
            "vector_bucket": key.vector_bucket,
            "tutor_signals": list(
                signal_actions_for_node(getattr(profile, "tutor_notes", None), node.id)
            ),
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
        "node_state": state_payload,
        "source_context": source_context,
        "backend": str(state.get("backend") or "openui"),
        "effective_density": key.effective_density,
        "scaffold_band": key.scaffold_band,
        "cache_key": cache_key,
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


# --------------------------------------------------------------------------- #
# Node 2: probe_gate
# --------------------------------------------------------------------------- #
@runtime_node_error_wrapper("probe_gate")
async def probe_gate(state: NodeRuntimeState) -> dict:
    """Skip the node when the learner already mastered it. Zero tokens (§2, §7.3)."""
    node_state = state.get("node_state") or {}
    mastered = str(node_state.get("state")) == MASTERED
    await publish_step(
        str(state["request_id"]), "probe_gate", STEP_MESSAGES["probe_gate"]
    )
    return {"mastered": mastered, "current_step": "probe_gate"}


# --------------------------------------------------------------------------- #
# Node 3: decide_formato
# --------------------------------------------------------------------------- #
@runtime_node_error_wrapper("decide_formato")
async def decide_formato(state: NodeRuntimeState) -> dict:
    """Pick ``ui_format``, then the tier (§4.3).

    **The calibration period of §6.4 is a hard rule, and it short-circuits this node
    entirely:** with ``nodes_completed < 3`` there is no LLM call at all and the format is
    ``node.default_ui_format``. Not "the model is asked and ignored" — asked and ignored
    would still cost a call, and the reason for the rule is pedagogical, not economic: the
    learner has to build a mental map before the interface starts moving (the lesson of
    Office 2000's adaptive menus).
    """
    request_id = str(state["request_id"])
    node = state.get("node") or {}
    profile = state.get("profile") or {}
    node_state = state.get("node_state") or {}
    default_format = coerce_ui_format(node.get("default_ui_format"))
    #: Empty during calibration: no call was made, so there is nothing to account for.
    decide_tokens: dict[str, int] = {}

    if is_calibrating(int(profile.get("nodes_completed") or 0)):
        ui_format = default_format
        tier = select_tier(ui_format)
        rationale = "calibracion: se usa el formato por defecto del nodo (§6.4)"
    else:
        org_id = _uuid(state["org_id"])
        llm = await _make_llm(org_id, "fast")
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
            scaffold_band=str(state.get("scaffold_band") or "neutral"),
            vector_bucket=str(profile.get("vector_bucket") or ""),
            mastery=float(node_state.get("mastery") or 0.0),
            consecutive_failed=int(node_state.get("consecutive_failed") or 0),
            last_error_kind=node_state.get("last_error_kind"),
            source_has_numbers=_source_has_numbers(str(state.get("source_context") or "")),
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

    await publish_step(request_id, "decide_formato", STEP_MESSAGES["decide_formato"])
    await sse.publish(
        node_channel(request_id), "ui_format", {"format": ui_format, "tier": tier}
    )
    return {
        "ui_format": ui_format,
        "tier": tier,
        "format_rationale": rationale,
        "current_step": "decide_formato",
        # Carried so `node_renders.tokens_*` is the cost of the *render*, not of one of the
        # two calls that produced it. `genera_ui` adds its own on top, retries included.
        **decide_tokens,
    }


# --------------------------------------------------------------------------- #
# Node 4: genera_ui
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

    if retry:
        system = ui_repair_system()
        user_prompt = build_repair_prompt(
            previous=str(state.get("raw_dsl") or ""),
            errors=list(state.get("validation_errors") or []),
            ui_format=ui_format,
        )
    else:
        system = ui_generator_system()
        user_prompt = build_ui_prompt(
            title=str(node.get("title") or ""),
            summary=str(node.get("summary") or ""),
            outcome=node.get("outcome"),
            criticality=str(node.get("criticality") or "recommended"),
            ui_format=ui_format,
            effective_density=int(state.get("effective_density") or 3),
            scaffold_band=str(state.get("scaffold_band") or "neutral"),
            role_title=profile.get("role_title"),
            sector=profile.get("sector"),
            experience_level=str(profile.get("experience_level") or "unknown"),
            preset=str(profile.get("preset") or "standard"),
            target_bloom=target_bloom(mastery, threshold),
            last_error_kind=node_state.get("last_error_kind"),
            consecutive_failed=int(node_state.get("consecutive_failed") or 0),
            consecutive_correct=int(node_state.get("consecutive_correct") or 0),
            tutor_signals=tuple(profile.get("tutor_signals") or ()),
            source_context=str(state.get("source_context") or ""),
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
    return {
        "raw_dsl": raw,
        "model": getattr(llm, "model", "unknown"),
        "duration_ms": duration_ms + int(state.get("duration_ms") or 0),
        "tokens_in": _accumulate(state.get("tokens_in"), tokens_in),
        "tokens_out": _accumulate(state.get("tokens_out"), tokens_out),
        "current_step": "genera_ui",
    }


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

    async with async_session_factory() as db:
        repo = NodeRenderRepository(db)
        render = await repo.get_by_id(_uuid(render_id))
        if render is None:
            raise ValueError(f"node_renders row {render_id} disappeared")
        await repo.mark_ready(
            render,
            ui_format=ui_format,
            ui_spec=dict(spec),
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
    "build_fallback_spec",
    "decide_formato",
    "fallback_seed",
    "genera_ui",
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
