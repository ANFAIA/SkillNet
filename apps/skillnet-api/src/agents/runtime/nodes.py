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
import functools
import json
import re
import time
import unicodedata
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from src.agents.content.helpers import (
    CHARS_PER_PAGE,
    FULL_TEXT_PAGE_THRESHOLD,
    assemble_chunk_text,
    estimate_pages,
)
from src.agents.runtime.assessment import (
    QUIZ_ROTATION,
    AssessmentPlan,
    _closer_index,
    plan_assessment,
)
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
    SCOPE_HEADINGS_MISSING,
    SCOPE_HEADINGS_UNMATCHED,
    SCOPE_OK,
    SCOPE_SLICE_TOO_SHORT,
    ShapePlan,
    ShapeSignal,
    analyze_shape,
    refine_format,
    scope_to_headings,
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
from src.personalization.learning_note import (
    learning_note_fingerprint,
    normalize_learning_note,
)
from src.personalization.preferences import normalize_learning_preferences
from src.personalization.projection import (
    longitudinal_projection_from_mapping,
    project_longitudinal_history,
)
from src.render.backends import get_render_backend
from src.render.errors import RenderError, RenderValidationError
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
    assert_grounded_activity_draft,
    authoring_draft_with_server_refs,
    build_activity_authoring_prompts,
    materialize_authored_activity,
)
from src.services.activity_definitions import ActivityDefinitionService
from src.services.learner_profile_service import is_calibrating
from src.services.mastery_service import target_bloom, threshold_for
from src.services.node_render_service import (
    NodeRenderService,
    build_render_key,
    current_prompt_version,
)

logger = get_logger(__name__)

#: Chunks retrieved for the ``chunked`` branch of ``load_context`` (§4.2).
RETRIEVAL_TOP_K = 8

#: Fallback is a safety net, not a document viewer. Keep it within a compact viewport even
#: when the source lesson is long: one lead plus at most two short Markdown blocks.
FALLBACK_BLOCK_CHARS = 300
FALLBACK_MAX_BLOCKS = 2


# --------------------------------------------------------------------------- #
# Leaked server scaffolding — the one thing a screen may never contain
# --------------------------------------------------------------------------- #
# ``state["source_context"]`` is the **server prompt**, not lesson content. When the node
# has a validated knowledge pack, ``knowledge_pack.runtime_selection._render_context``
# renders it as a dossier: a title, internal section headings (``## Invariantes``,
# ``## Material adaptable``) and one program-minted reference per point
# (``must.atom:10``, installed by ``knowledge_pack.generator._namespace_atom_ids``). Its
# whole purpose is to tell the model what it may teach and what it may not invent; not one
# word of it was written for a learner to read.
#
# Until 2026-08-27 ``_serve_fallback`` used it as the fallback body whenever the node had
# no v1 seed lesson — which is *every* node of a course authored natively in v2 — so
# learners read the prompt on screen, atom ids and all. ``source_context`` is therefore no
# longer a content source anywhere in this module, and the patterns below are the second
# line of defence for the other way the markers can escape: the model copying them back
# out of its own prompt.
#
# The patterns are deliberately **structural**, never a bare word, and every one of them
# is a shape only the *server* writes. "Invariantes" is legitimate prose in a course on
# mathematics or programming, so a lone word never trips the check; and neither does a
# citation, which is the mistake this check made until 2026-08-27: matching any
# ``[letters:digits]`` flagged ``[ISO:9001]``, ``[cap:3]`` and ``[RFC:2606]`` — a lesson
# quoting a standard, a chapter or an RFC — and cost that screen both repair attempts. What
# trips it now is a namespaced reference (``must.``/``selectable.``), the dossier's own
# ``(ref …)`` marker, a bracketed *namespaced* id ending in ``:N``, the exact multi-word
# server jargon, or a section heading in markdown heading form.
#
# The literal wording is read from the module that EMITS it (see ``_scaffold_wording``), so
# the detector cannot drift from the dossier the day someone renames a section.

#: A program-minted atom reference: ``must.`` / ``selectable.`` plus the identifier
#: alphabet of ``knowledge_pack.contracts._IDENTIFIER``. The two prefixes are installed by
#: the server, never proposed by the model, so this form cannot be a coincidence of prose;
#: requiring an alphanumeric immediately after the dot keeps "you must. Then..." out.
_SCAFFOLD_REF_RE = re.compile(r"\b(?:must|selectable)\.[A-Za-z0-9][A-Za-z0-9._:/@-]*")

#: The marker ``runtime_selection._point`` actually writes today: the point's prose, then
#: its reference in parentheses behind the ``ref`` keyword — ``(ref must.atom:1)``,
#: ``(ref safety.allergen)``, ``(ref correo_reenviado)``. That keyword is the server's own
#: jargon, which is what makes this form safe to match for the ids that carry **no**
#: ``must.``/``selectable.`` namespace (evidence specs and generable slots): the bare id is
#: indistinguishable from a lesson's own citation, ``(ref <id>)`` is not. A purely numeric
#: reference is excluded, because "(ref 2)" is a citation a human might write.
#: ``tests/test_knowledge_pack.py`` runs the real emitter through the detector, so this
#: cannot silently drift away from the wording it mirrors.
_SCAFFOLD_POINT_REF_RE = re.compile(
    r"\(ref\s+(?![0-9]+\))[A-Za-z0-9][A-Za-z0-9._:/@-]*\)", re.IGNORECASE
)

#: A bracketed dossier reference, the shape the dossier used **before** 2026-08-27 (``-
#: [must.atom:1] texto``) and the one a seed or summary generated back then can still
#: carry. A **namespace** is required — a dot with a letter on either side — and not merely
#: "letters, colon, digits": ``[ISO:9001]``, ``[RFC:2606]``, ``[cap:3]`` and ``[art:5]`` are
#: a lesson citing a standard or an article, and rejecting those cost the screen its two
#: repair attempts and then, if the node's own summary carried one, its fallback body too.
#: ``[1:30]`` and ``[Juan 3:16]`` are excluded for the same reason as before: no dotted
#: namespace, and the alphabet excludes the space.
_SCAFFOLD_BRACKET_REF_RE = re.compile(
    r"\[[A-Za-z][A-Za-z0-9_-]*\.[A-Za-z][A-Za-z0-9._:/@-]*:\d+\]"
)


def _fold(text: str) -> str:
    """Lowercase and strip combining marks, so an unaccented copy still matches.

    The dossier is written with accents; a model paraphrasing it often drops them, and the
    OpenUI parser folds accents in identifiers anyway. Comparing folded text costs nothing
    and closes the "Dossier pedagogico seleccionado" spelling.
    """
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    ).lower()


@functools.cache
def _scaffold_wording() -> tuple[
    tuple[str, ...], tuple[tuple[str, re.Pattern[str]], ...]
]:
    """The dossier's literal wording, in the two strengths the check applies it.

    * **Phrases**, matched anywhere: server jargon no course would write. A heading earns a
      place here only when it is unmistakable on its own.
    * **Headings**, matched only in the dossier's own markdown heading form: their words
      are plausible lesson content, so ``## Invariantes`` is the server's while "los
      invariantes de un bucle" is a lesson's. A copied *title* with no reference beside it
      cannot be told apart from real content and is deliberately allowed through.

    The import is deferred and the result cached because
    ``knowledge_pack.runtime_selection`` reaches this module back through
    ``configured_generator`` -> ``agents.runtime.shape`` -> ``agents/runtime/__init__``: at
    module level it is a real cycle. ``load_context`` defers the same import for the same
    reason.
    """
    from src.knowledge_pack.runtime_selection import (
        DOSSIER_SECTION_HEADINGS,
        DOSSIER_TITLE,
    )

    phrases = (
        DOSSIER_TITLE,
        DOSSIER_SECTION_HEADINGS[2],  # "Evidencia que debe obtenerse"
        DOSSIER_SECTION_HEADINGS[3],  # "Espacios generables permitidos"
    )
    headings = (
        DOSSIER_SECTION_HEADINGS[0],  # "Invariantes"
        DOSSIER_SECTION_HEADINGS[1],  # "Material adaptable"
    )
    heading_res = tuple(
        (
            heading,
            re.compile(
                rf"^[ \t]*#{{1,6}}[ \t]*{re.escape(_fold(heading))}[ \t]*:?[ \t]*$",
                re.MULTILINE,
            ),
        )
        for heading in headings
    )
    return phrases, heading_res


def leaked_scaffolding_markers(text: str) -> list[str]:
    """Internal-scaffolding markers found in text that is about to face a learner.

    An empty list means clean. The returned strings are what was matched, so they can go
    straight into a log line and into the repair prompt — the model is told *which* marker
    it copied, not merely that something was wrong.
    """
    if not text:
        return []
    found: list[str] = []
    found.extend(_SCAFFOLD_REF_RE.findall(text))
    # Delimiters stripped so ``[must.atom:1]``, ``(ref must.atom:1)`` and ``must.atom:1``
    # collapse into one entry instead of reporting the same leak two or three times.
    found.extend(
        match.strip("[]") for match in _SCAFFOLD_BRACKET_REF_RE.findall(text)
    )
    found.extend(
        match[1:-1].split(None, 1)[1].strip()
        for match in _SCAFFOLD_POINT_REF_RE.findall(text)
    )
    phrases, heading_res = _scaffold_wording()
    folded = _fold(text)
    for phrase in phrases:
        if _fold(phrase) in folded:
            found.append(phrase)
    for heading, pattern in heading_res:
        if pattern.search(folded):
            found.append(f"## {heading}")
    return sorted(dict.fromkeys(found))


def _collect_strings(value: Any, into: list[str]) -> None:
    """Every string reachable inside a props payload, at any depth."""
    if isinstance(value, str):
        into.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, into)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_strings(item, into)


def spec_scaffolding_markers(spec: UISpec) -> list[str]:
    """The same check over a parsed spec: only ``props``, which is all the learner reads.

    Component ids and types are server-controlled vocabularies (``[A-Za-z_][A-Za-z0-9_]*``
    and the closed kit), so they cannot carry a dossier reference and are not scanned.
    """
    texts: list[str] = []
    for component in spec.components:
        _collect_strings(component.props, texts)
    return leaked_scaffolding_markers("\n".join(texts))


# Closed renderer-safe scope for unscored support. Assessment wrappers and neutral
# experience references are deliberately absent: they require server materialization.
#: Reveal-only blocks (``DidactWorkedExample``, ``HintReveal``, ``StepByStepReveal``) were
#: removed on 2026-08-17: a support screen still must not hand information to the learner
#: behind a click. The learner reads full content or acts; nothing is reveal-gated.
#: ``DidactGlossary`` removed on 2026-08-17: the platform already has "Curio" (click any
#: word for its meaning), so an in-lesson glossary block is redundant and never generated.
#: ``Flashcard`` removed on 2026-08-18: even in a support-only episode a Flashcard is a
#: reveal (front → back), so if it were the last block on the screen the learner "closes" the
#: node by flipping a card instead of acting — which the bench flags as ``flashcard_as_closer``
#: and the owner banned outright. Support screens still teach and rehearse, but with blocks the
#: learner reads or acts on (``DragOrder`` for active recall/ordering), never a reveal-gated card.
_SUPPORT_PROMPT_COMPONENT_IDS = frozenset(
    {
        "BeforeAfter",
        "Chart",
        "DidactTimeline",
        "DragOrder",
        "StepSequence",
        "Table",
        "Tabs",
    }
)

#: The interactive (non-mastery) blocks a support-only episode may use. ``support_only``
#: means "we do not CERTIFY mastery here", not "passive info only": the screen must still
#: offer a self-check / rehearsal built from the source. When the planner shortlist for a
#: support episode contains none of these, one is appended so the episode stays interactive.
#: ``Flashcard`` is deliberately absent (see above): a support interaction is a real act, not
#: a reveal.
_SUPPORT_INTERACTIVE_IDS = frozenset({"DragOrder", "BeforeAfter"})
#: Preferred order when forcing an interaction into a support shortlist that lacks one.
#: ``DragOrder`` first: active recall by ordering/sorting, always groundable from the source,
#: an act the learner performs — never a Flashcard reveal.
_SUPPORT_INTERACTIVE_FALLBACK: tuple[str, ...] = (
    "DragOrder",
    "BeforeAfter",
)


def _ensure_support_interaction(prompt_ids: list[str]) -> list[str]:
    """Keep a support-only shortlist interactive without certifying mastery."""

    if any(value in _SUPPORT_INTERACTIVE_IDS for value in prompt_ids):
        return prompt_ids
    return [*prompt_ids, _SUPPORT_INTERACTIVE_FALLBACK[0]]

STEP_MESSAGES: dict[str, str] = {
    "load_context": "Preparando el nodo...",
    "probe_gate": "Comprobando lo que ya dominas...",
    "direct_episode": "Preparando una experiencia adaptada...",
    "decide_formato": "Eligiendo la forma de la leccion...",
    "author_activity": "Preparando la actividad interactiva...",
    "genera_ui": "Escribiendo la leccion...",
    "validate_ui": "Revisando la leccion...",
    "critic_episode": "Afinando la pedagogia...",
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


async def load_source_context(
    db: Any,
    node: CourseNode,
    org_id: uuid.UUID,
    *,
    scope_out: dict[str, Any] | None = None,
) -> str:
    """The two explicit branches of §4.2.

    * A document of **<= 5 pages** goes in whole (``full_text``). No embeddings needed, and
      this is the branch the fixture tests exercise end to end.
    * Anything bigger goes through ``similarity_search_by_headings(headings=node.source_headings)``.
      Headings survive re-ingestion, chunk ids do not. If the heading filter returns nothing
      the search is retried **without** it and a warning is logged — an empty source would
      otherwise hand the learner plausible content with no documentary basis, silently.

    ``scope_out`` is an optional diagnostic sink, the same shape of out-parameter
    ``LLMService.stream`` uses for ``usage_out``: it is filled with ``{"widened": bool,
    "reason": str}`` saying whether the text handed back is really this node's or the whole
    document. The return type is deliberately untouched — ``knowledge_pack.runner`` types
    this function as its ``SourceLoader`` and ``routes.nodes`` calls it directly, so
    widening the signature by return value would be a breaking change for a diagnostic.

    Four fallbacks widen the scope, all deliberate and all previously silent: no headings on
    the node, headings that match nothing, a scoped slice under
    :data:`MIN_SCOPED_SOURCE_CHARS`, and the chunk search retried with the heading filter
    dropped. Each keeps the node from starving, and each also hands it material that belongs
    to a sibling node — which is what a learner reports as being asked about something never
    explained. See :func:`_with_source_scope` for what the caller does with this.
    """

    def _record(reason: str) -> None:
        if scope_out is not None:
            scope_out.clear()
            scope_out.update({"widened": reason != SCOPE_OK, "reason": reason})

    _record(SCOPE_OK)
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
        scoped, reason = _scoped_full_text(document.full_text, node.source_headings)
        _record(reason)
        return clip_source(scoped)

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
            scoped, reason = _scoped_full_text(document.full_text, node.source_headings)
            _record(reason)
            return clip_source(scoped)
        return ""
    headings = list(node.source_headings or [])
    if not headings:
        _record(SCOPE_HEADINGS_MISSING)
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
        _record(SCOPE_CHUNKS_UNFILTERED)
        rows = await repo.similarity_search_by_headings(
            org_id=org_id,
            query_embedding=embedding,
            top_k=RETRIEVAL_TOP_K,
            document_ids=[document.id],
            headings=None,
        )
    if not rows and document.full_text:
        # The widest fallback of the four: no chunk matched at all, so the node is handed
        # the entire document with no scoping of any kind. Logged like its sibling above —
        # until 2026-08-28 this branch was the only silent one.
        logger.warning(
            "No chunk matched at all for node %s; falling back to the whole document",
            node.id,
        )
        _record(SCOPE_CHUNKS_EMPTY)
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

#: The two scope-widening reasons that belong to the chunked branch; the other two come
#: from :mod:`src.agents.runtime.shape` so the names cannot drift from the code that
#: decides them.
SCOPE_CHUNKS_UNFILTERED = "chunks_unfiltered"
SCOPE_CHUNKS_EMPTY = "chunks_empty"

#: What each widening reason means for the generator, in its own language. Closed
#: vocabulary, like ``_SIGNAL_RULES`` in the prompt module: a reason can never turn into
#: free-form prose injected into a prompt.
_SCOPE_WIDENED_REASONS: dict[str, str] = {
    SCOPE_HEADINGS_MISSING: (
        "este nodo no declara que parte del documento le toca, asi que abajo tienes el "
        "documento entero"
    ),
    SCOPE_HEADINGS_UNMATCHED: (
        "las secciones que este nodo declara no aparecen en el documento, asi que abajo "
        "tienes el documento entero"
    ),
    SCOPE_SLICE_TOO_SHORT: (
        "la seccion propia de este nodo era demasiado corta para ensenar con ella, asi "
        "que abajo tienes el documento entero"
    ),
    SCOPE_CHUNKS_UNFILTERED: (
        "no se encontro ningun pasaje bajo las secciones de este nodo, asi que abajo "
        "tienes pasajes de todo el documento"
    ),
    SCOPE_CHUNKS_EMPTY: (
        "no se encontro ningun pasaje relevante, asi que abajo tienes el documento entero"
    ),
}


def _scoped_full_text(full_text: str, headings: Any) -> tuple[str, str]:
    """The node's own sections of a short document, or all of it when that is not safe.

    Returns the text **and** why, so the caller can tell the generator it is holding more
    than its own material. See :func:`load_source_context`.
    """
    scoped, reason = scope_to_headings(full_text, list(headings or ()))
    if len(scoped.strip()) < MIN_SCOPED_SOURCE_CHARS:
        return full_text, SCOPE_SLICE_TOO_SHORT if reason == SCOPE_OK else reason
    return scoped, reason


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


def unusable_answer_keys(spec: UISpec, answer_key: dict) -> list[str]:
    """Entries that are PRESENT but cannot grade the item they belong to.

    :func:`missing_answer_keys` asks "did the model send a solution at all". This asks the
    next question, which nothing asked until 2026-08-28: "is the solution the right SHAPE
    for this ``item_type``". ``src.services.probe_service.validate_probe_items`` has always
    asked it for the pre-test — ``correct`` must be an ``int`` in range — and the render
    path never did, an asymmetry no comment ever justified.

    What the gap serves, read off ``src.services.exercise_service``:

    * ``"correct": "1"`` on a ``test`` — ``_grade_test`` compares ``selected == correct``,
      so ``1 == "1"`` is ``False`` and **no answer can ever score**.
    * ``"correct": 4`` with four options — same outcome by a different route.
    * ``"correct": "false"`` on a ``true_false`` — ``_grade_true_false`` compares
      ``bool(given) == bool(correct)``, and ``bool("false")`` is ``True``, so the grading is
      **inverted**: the learner picks Falso, which is right, and is told it was Verdadero.

    The last one is the shape the testers reported on 2026-08-28 ("la respuesta no es esa"),
    and the frontend hides its cause: ``revealedCorrectIndex``
    (``apps/skillnet-web/src/components/courses/blocks/QuizItemBlock.tsx``) only reveals a
    ``boolean``/``number``, so a string key marks nothing green and the screen just says
    wrong. A key like this is not a degraded screen, it is an unpassable one, so it is worth
    the single repair attempt exactly like an absent key.

    Returns one message per broken item, each naming the offending value **and** the shape
    to write instead: the repair loop replays these verbatim and a vague one burns the
    only retry.
    """
    problems: list[str] = []
    for component in spec.components:
        if component.type != "QuizItem":
            continue
        item_id = str(component.props.get("item_id") or component.id)
        entry = answer_key.get(item_id)
        if not isinstance(entry, dict):
            continue  # absent: missing_answer_keys owns that message
        item_type = str(component.props.get("item_type") or "")
        options = component.props.get("options")
        option_count = len(options) if isinstance(options, list) else 0
        problem = _answer_key_problem(item_type, entry, item_id, option_count)
        if problem:
            problems.append(problem)
    return problems


def _true_false_int(correct: object) -> bool:
    """Whether ``correct`` is the 0/1 spelling of a ``true_false`` answer.

    ``isinstance(True, int)`` is True in Python, so the ``bool`` exclusion is what keeps
    this from claiming every real boolean as an int.
    """
    return isinstance(correct, int) and not isinstance(correct, bool) and correct in (0, 1)


def _answer_key_problem(
    item_type: str, entry: dict, item_id: str, option_count: int
) -> str | None:
    """The one thing wrong with this entry, phrased as an order the model can execute."""
    correct = entry.get("correct")

    if item_type == "test":
        # bool is a subclass of int, and `True` would grade as option 1 — the same silent
        # off-by-one the whole check exists to stop. Excluded explicitly, as the probe does.
        if not isinstance(correct, int) or isinstance(correct, bool):
            return (
                f"QuizItem {item_id!r} es de tipo \"test\" y su clave trae "
                f"correct={correct!r}, que no es un numero. En \"test\" correct es el "
                f"INDICE de la opcion correcta, un entero sin comillas, contando desde 0: "
                f'{{"{item_id}": {{"correct": 0, "explanation": "..."}}}}. Con comillas la '
                "comparacion nunca acierta y el aprendiz no puede aprobar."
            )
        if option_count and not 0 <= correct < option_count:
            return (
                f"QuizItem {item_id!r} tiene {option_count} opciones, asi que correct solo "
                f"puede ir de 0 a {option_count - 1}, y has escrito {correct}. Cuenta desde "
                "0: la primera opcion es 0 y la ultima es "
                f"{option_count - 1}. Corrige el indice para que apunte a la opcion que de "
                "verdad responde al enunciado."
            )
        return None

    if item_type == "true_false":
        # 0 and 1 are ACCEPTED, not rejected, and the difference is not pedantry: the
        # front sends `{answer: selected === 0}` and `_grade_true_false` compares
        # `bool(given) == bool(correct)`, so an int already grades right. Refusing it
        # would spend the single repair attempt — and possibly drop the node to a flat
        # seed lesson — over a key that works. `prune_answer_key` normalizes it to a real
        # bool on the way to storage so `revealedCorrectIndex` can still paint the correct
        # option green. A string is a different animal and stays refused: `bool("false")`
        # is True, which inverts the grade silently.
        if not isinstance(correct, bool) and not _true_false_int(correct):
            return (
                f"QuizItem {item_id!r} es de tipo \"true_false\" y su clave trae "
                f"correct={correct!r}. Ahi correct es true o false en JSON, sin comillas y "
                f'sin indices: {{"{item_id}": {{"correct": true, "explanation": "..."}}}}. '
                'Escrito como texto, "false" se lee como verdadero y la correccion sale al '
                "reves: se le dice que fallo a quien acerto."
            )
        return None

    if item_type == "fill_blank":
        blanks = entry.get("blanks")
        if not isinstance(blanks, list) or not blanks:
            return (
                f"QuizItem {item_id!r} es de tipo \"fill_blank\" y su clave no trae la "
                f'lista "blanks". Escribe {{"{item_id}": {{"blanks": ["<texto exacto del '
                'hueco>"], "explanation": "..."}}}}: sin ella no hay con que comparar la '
                "respuesta y el hueco es incorregible."
            )
        if any(not isinstance(blank, str) or not blank.strip() for blank in blanks):
            return (
                f"QuizItem {item_id!r} tiene un hueco vacio o no textual en \"blanks\" "
                f"({blanks!r}). Cada entrada es el texto EXACTO que se espera en ese hueco, "
                "tal y como aparece en la fuente."
            )
        return None

    if item_type == "order_steps":
        # A QuizItem of this type is unanswerable, and that is a frontend fact, not a
        # preference: `QuizItemBlock.buildAnswer` only builds a choice payload for `test`
        # and `true_false`, so an `order_steps` item renders as a free-text box and posts
        # `{response: "..."}`. `_grade_order_steps` then compares that string against a
        # list of indices and scores 0.0 forever. Ordering has a working block — DragOrder,
        # which carries its own solution as its third argument — so the repair is a swap,
        # not a better key. (v1 exercises are unaffected: they have their own renderer,
        # `apps/skillnet-web/src/components/exercises/OrderStepsExercise.tsx`.)
        return (
            f"QuizItem {item_id!r} usa item_type \"order_steps\", que esta pantalla no sabe "
            "responder: se dibuja como una caja de texto y ninguna respuesta puede acertar. "
            "Para ordenar usa DragOrder(\"instruccion\", [\"item1\", \"item2\", \"item3\"], "
            "[\"orden\", \"correcto\", \"aqui\"]), que lleva su solucion dentro y no necesita "
            "entrada en la clave."
        )

    # `practical_case` and `dialogue` are open types graded by an eval LLM (or waved
    # through at 0.5); their keys are rubrics, not solutions, and nothing here can check a
    # rubric. Leaving them alone is deliberate, not an oversight.
    return None


def answer_key_problems(spec: UISpec, answer_key: dict) -> list[str]:
    """Every reason this key cannot grade this spec, absent entries first.

    Absent beats malformed: telling the model its ``correct`` is out of range for an entry
    it never wrote would send the one repair attempt after the wrong mistake.
    """
    missing = missing_answer_keys(spec, answer_key)
    return missing or unusable_answer_keys(spec, answer_key)


def prune_answer_key(spec: UISpec, answer_key: dict) -> dict:
    """Keep only entries for ``QuizItem`` ids that really exist in the spec, normalized.

    The model is capable of inventing an entry for an item it did not emit; storing it would
    put un-referenced answers in a column whose whole purpose is to be minimal.

    It also settles the one spelling ``_answer_key_problem`` deliberately lets through: a
    ``true_false`` whose ``correct`` is 0 or 1 instead of a JSON boolean. It already grades
    right, so refusing it would burn the single repair attempt over a working key — but
    stored as an int it reaches ``revealedCorrectIndex``, which requires ``typeof
    'boolean'`` and therefore highlights nothing, leaving the learner told they failed
    without being shown the right answer. Normalizing here, at the one seam that builds the
    stored key, keeps both ends honest.
    """
    wanted = {
        str(component.props.get("item_id") or component.id)
        for component in spec.components
        if component.type == "QuizItem"
    }
    item_types = {
        str(component.props.get("item_id") or component.id): str(
            component.props.get("item_type") or ""
        )
        for component in spec.components
        if component.type == "QuizItem"
    }
    pruned: dict = {}
    for item_id, entry in answer_key.items():
        if item_id not in wanted or not isinstance(entry, dict):
            continue
        if item_types.get(item_id) == "true_false" and _true_false_int(
            entry.get("correct")
        ):
            entry = {**entry, "correct": bool(entry["correct"])}
        pruned[item_id] = entry
    return pruned


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
        # Diagnostic sink: says whether the text below is really this node's slice or a
        # widened fallback. Carried into the prompt by `_with_source_scope` so the screen
        # can teach from borrowed material without evaluating on it.
        source_scope: dict[str, Any] = {}
        source_context = await load_source_context(
            db, node, org_id, scope_out=source_scope
        )
        if source_scope.get("widened"):
            logger.warning(
                "source_scope_widened node=%s course=%s reason=%s",
                node.id,
                node.course_id,
                source_scope.get("reason"),
            )
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

        # The media broker: offer this node's READY podcast/infographic artefacts to the
        # generator, gated by the learner's modality preference. Kept in state for the
        # generation/critic nodes, and its fingerprint partitions the render cache key.
        from src.agents.runtime.media_broker import (
            gate_offers,
            offers_fingerprint,
            ready_media_for_node,
        )

        ready_media = await ready_media_for_node(db, node_id=node_id, org_id=org_id)
        media_offers = gate_offers(
            ready_media, getattr(profile, "learning_preferences", None)
        )

        # The source-image broker: what this course does with the pictures that were
        # already inside its source document. Diagrams get rebuilt (their description
        # steers the prompt, no image is placed), screenshots get kept — unless the
        # course's `image_source_policy` overrides the rule. Deliberately NOT routed
        # through `gate_offers`: a source image is content, not a modality, and that gate
        # only fires for a learner who declared audio or visual.
        from src.agents.runtime.source_image_broker import (
            SOURCE_IMAGE_COMPONENT,
            decide_source_images,
            decision_fingerprint,
            source_images_for_node,
            suppress_competing_media,
        )

        image_decision = decide_source_images(
            await source_images_for_node(db, node=node, org_id=org_id),
            policy=getattr(course, "image_source_policy", None),
            preferences=getattr(profile, "learning_preferences", None),
        )
        # A real picture from the customer's own manual and one a model invented must not
        # share a lesson; the real one wins. A podcast is untouched — different sense.
        media_offers = suppress_competing_media(image_decision, media_offers)

        media_offers_payload = [
            {
                "kind": offer.kind,
                "component": offer.component,
                "artifact_id": offer.artifact_id,
                "title": offer.title,
            }
            for offer in media_offers
        ]
        source_image_offers_payload = [
            {
                "component": SOURCE_IMAGE_COMPONENT,
                "image_id": offer.image_id,
                "alt": offer.alt,
                "caption": offer.caption,
                # The asset route is document-scoped, so the client needs both ids.
                "document_id": offer.document_id,
            }
            for offer in image_decision.kept
        ]
        source_image_rebuilds_payload = [
            {
                "image_id": item.image_id,
                "description": item.description,
                "caption": item.caption,
            }
            for item in image_decision.rebuilt
        ]

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
            media_offer_fingerprint=offers_fingerprint(media_offers),
            # The course's image policy plus the chosen originals. Empty when the node
            # matched no source image, so no pre-existing render key moves.
            source_image_fingerprint=decision_fingerprint(image_decision),
            # The learner's free-text note partitions the render cache: two learners with
            # different notes get different renders, and changing your note re-renders.
            # Mirrors the pre-graph key in NodeRenderService.render_key_for exactly.
            learning_note_fingerprint=learning_note_fingerprint(
                getattr(profile, "learning_note", None)
            ),
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
            # Same string that went into `cache_key`, kept readable in a column so a
            # later PROMPT_VERSION bump can be told from a row it evicted
            # (src/services/render_retention.py).
            prompt_version=current_prompt_version(),
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
            # The learner's own "how I like to learn" note. Unlike memory_md, this DOES steer
            # the (cached) generation prompt — the render is partitioned by its fingerprint
            # (see build_render_key), so no cross-learner leak. It changes only HOW the same
            # content is explained, never WHAT is taught.
            "learning_note": normalize_learning_note(
                getattr(profile, "learning_note", None)
            ),
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
        "source_scope": dict(source_scope),
        # Broker-offered media components for this node (already gated by preference).
        "media_offers": media_offers_payload,
        # Originals from the source document this lesson places, and the ones it rebuilds.
        "source_image_offers": source_image_offers_payload,
        "source_image_rebuilds": source_image_rebuilds_payload,
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
        # The evidence policy certifies a FAMILY of deterministically-scored components; the
        # authoring node picks certified_ids[0]. Rotate the family by node so sibling nodes
        # do not all land on the same activity (matching/categorize/sort/word-bank/quiz),
        # which is exactly the variety the owner asked for. Stable per node (never shifts
        # under a returning learner) via the assessment rotation helper.
        if certified_ids:
            from src.agents.runtime.assessment import _closer_index

            offset = _closer_index(
                node_id=str(state["node_id"]),
                course_id=str(state.get("course_id") or ""),
                position=(state.get("node") or {}).get("position"),
                size=len(certified_ids),
            )
            certified_ids = certified_ids[offset:] + certified_ids[:offset]
        prompt_ids = list(trace.get("prompt_component_ids") or ())
        if support_only:
            prompt_ids = [
                value for value in prompt_ids if value in _SUPPORT_PROMPT_COMPONENT_IDS
            ]
            # support_only never certifies mastery, but the screen must still be
            # interactive: guarantee at least one non-mastery self-check block.
            prompt_ids = _ensure_support_interaction(prompt_ids)
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
#: No direct Didact block is ever the node's TEST. Emptied on 2026-08-17: ``Flashcard`` is a
#: CONTENT resource (active recall), ``DidactGlossary`` was dropped platform-wide (Curio
#: replaces it) and ``DidactTimeline`` is content too — none of them "evaluate", so none may
#: stand in as the assessment/closer. The real check is a ``DidactActivity`` (matching,
#: categorize, sort, word-bank, quiz variants) or, when none can be materialized, a real
#: varied ``QuizItem``. Kept as a name so the (now always-false) closer checks stay readable.
_DIRECT_DIDACT_CLOSERS: tuple[str, ...] = ()


def _didact_activity_fallback_item_type(state: NodeRuntimeState) -> str:
    """A real, node-varied QuizItem type when a certified activity cannot be materialized.

    Never a Flashcard: the closer is the node's TEST and must actually check the learner.
    Rotating the ``QuizItem`` type by node keeps sibling fallbacks from all being the same
    "test" (single-choice/true-false/fill-in-the-blank), the variety the owner asked for.
    """

    index = _closer_index(
        node_id=str(state.get("node_id") or ""),
        course_id=str(state.get("course_id") or ""),
        position=(state.get("node") or {}).get("position"),
        size=len(QUIZ_ROTATION),
    )
    return QUIZ_ROTATION[index]


def _didact_activity_fallback_block(state: NodeRuntimeState) -> str:
    """Deterministic interactive fallback when authoring an activity declines: a real test."""

    return "QuizItem"


def _pinned_experience_refs(state: NodeRuntimeState) -> tuple[str, str, str] | None:
    """The server-owned experience triple for THIS node, or ``None`` if there is none.

    **The one predicate for "a prepared experience exists".** Everything that branches on
    it — the prompt's required closer, the screen scheme, the assessment hint, the
    assembler, the gate's pinning step and the closer policy below — reads this, because
    ``authored_activity`` being a dict is *not* the same question. A ``MaterializedActivity``
    with an empty ``component_id``, or a payload whose ``implementation_ref`` carries no
    ``@version``, is a dict from which no full triple can be derived: the server has nothing
    to pin, so a ``LearningExperience`` on that screen would reference ids the model
    invented. Asking the dict-shaped question in one place and the derivable question in
    another is what let the repair message recommend the very closer the next rule refused
    (see :func:`_forbidden_closers`).
    """

    authored = state.get("authored_activity")
    if not isinstance(authored, dict):
        return None
    return _authored_experience_refs(authored)


def _has_prepared_experience(state: NodeRuntimeState) -> bool:
    """Whether the server has a pinnable ``LearningExperience`` for this node."""

    return _pinned_experience_refs(state) is not None


def _prompt_assessment_required(state: NodeRuntimeState) -> tuple[str, ...]:
    """Components the scoped prompt must include so verification can close the screen.

    Prepared activities cross the neutral ``LearningExperience`` boundary. If optional
    authoring declines, the screen still closes with a genuine interaction: a real
    ``QuizItem`` variant (see ``_didact_activity_fallback_block``), never a reveal-only
    Flashcard. ``_DIRECT_DIDACT_CLOSERS`` is empty, so no direct Didact block stands in as
    the test.
    """

    block = str(state.get("assessment_block") or "")
    if block == "DidactActivity":
        if _has_prepared_experience(state):
            return ("LearningExperience",)
        return (_didact_activity_fallback_block(state),)
    if block in _DIRECT_DIDACT_CLOSERS:
        return (block,)
    if block in _LEGACY_ASSESSMENT_BLOCKS:
        return (block,)
    return ()


#: The two interactions the learner actually *executes* and the gate keys and corrects.
#: Neither reveals an answer for free, so either one satisfies the closing rule that bans a
#: Flashcard as the last block.
_REAL_CLOSERS: frozenset[str] = frozenset({"QuizItem", "DragOrder"})


def _allowed_closers(state: NodeRuntimeState) -> set[str]:
    """Closers this screen may legitimately end on. One source of truth.

    In Didact mode the point of the prohibition is that verification crosses the neutral
    ``LearningExperience`` boundary and is corrected **by the server**: the model must not
    quietly substitute a quiz it invented for the prepared, tracked experience. That intent
    holds only while an experience actually exists.

    When authoring **declines** there is no prepared experience, so the prohibition has
    nothing left to defend — yet it kept refusing ``DragOrder`` while ``screen_scheme``
    was instructing the model to "cierra con DragOrder" for an ordered procedure. Measured in
    the quality bench on 2026-08-27: the prompt ordered the exact closer the gate forbade, so
    an obedient model could not win and the node fell back to a flat Markdown seed with no
    interaction at all — strictly worse, on the very axis the rule exists to protect, than the
    ``DragOrder`` it refused. A ``DragOrder`` is a real answer-keyed interaction, not a reveal.

    So the rule keeps its full teeth where a prepared experience exists (the screen must close
    on it) and stops firing where it has nothing to guard. That is narrowing an over-broad
    rule to its own rationale, not lowering the pedagogical bar: a screen still may never
    close by merely revealing information.
    """

    required = set(_prompt_assessment_required(state))
    if _has_prepared_experience(state):
        return required
    return required | set(_REAL_CLOSERS)


def _forbidden_closers(state: NodeRuntimeState) -> frozenset[str]:
    """Real closers the gate refuses on THIS screen. The prohibition's single derivation.

    Two things are folded in here on purpose, because keeping them apart is what produced
    contradictions:

    * **The scope.** The Didact prohibition only applies to a Didact screen, so anywhere
      else nothing is forbidden. Computed here rather than at the call site, so a reader of
      ``_offerable_closers`` cannot get the scope wrong while the gate gets it right.
    * **The complement.** ``_REAL_CLOSERS - _allowed_closers(state)`` is the exact set the
      gate rejects, and :func:`_offerable_closers` builds its recommendation by *subtracting*
      this set. The invariant "a repair never proposes what the next rule rejects" is then
      structural instead of a fact two functions have to keep agreeing on.
    """

    block = str(state.get("assessment_block") or "")
    if block != "DidactActivity" and block not in _DIRECT_DIDACT_CLOSERS:
        return frozenset()
    return frozenset(_REAL_CLOSERS) - _allowed_closers(state)


def _offerable_closers(state: NodeRuntimeState) -> tuple[str, ...]:
    """Interactions a repair message may name as the closer for THIS screen.

    Derived by subtracting :func:`_forbidden_closers`, so a repair message can never propose
    a component the same gate refuses one rule later. Naming "un QuizItem o un DragOrder"
    unconditionally used to point the model straight at an option it was about to be
    rejected for using.

    ``LearningExperience`` is offerable only when the server has a **pinnable** experience,
    which is precisely when both real closers are forbidden. That is not a coincidence to be
    maintained by hand: both facts come from :func:`_has_prepared_experience` through
    :func:`_allowed_closers`. Until 2026-08-27 they did not, and the message on the
    "no pinnable experience" branch of ``validate_ui`` contradicted itself in one sentence —
    "NO uses LearningExperience ... cierra con un LearningExperience" — while the prohibition
    below it forbade both real closers, leaving no repair the gate would accept.
    """

    forbidden = _forbidden_closers(state)
    offerable = tuple(
        name for name in ("QuizItem", "DragOrder") if name not in forbidden
    )
    if offerable:
        return offerable
    # Every real closer is out, which happens only while a prepared experience exists: name
    # it rather than a QuizItem the prohibition is about to refuse.
    return tuple(sorted(_allowed_closers(state) - set(_REAL_CLOSERS))) or ("QuizItem",)


def _effective_assessment_hint(state: NodeRuntimeState, required: tuple[str, ...]) -> str:
    """Keep the user prompt aligned with the closer that will actually be in scope."""

    hint = str(state.get("assessment_hint") or "")
    block = str(state.get("assessment_block") or "")
    if block != "DidactActivity" and block not in _DIRECT_DIDACT_CLOSERS:
        return hint
    if _has_prepared_experience(state):
        return (
            "VERIFICA con LearningExperience usando exactamente la referencia neutral "
            "preparada por el servidor; no inventes ids ni definiciones."
        )
    closer = required[0] if required else "QuizItem"
    if closer == "QuizItem":
        item_type = _didact_activity_fallback_item_type(state)
        return AssessmentPlan(block="QuizItem", item_type=item_type).instruction()
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
        if _has_prepared_experience(state):
            closer = "LearningExperience"
        else:
            closer = required[0] if required else "QuizItem"
            item_type = (
                _didact_activity_fallback_item_type(state)
                if closer == "QuizItem"
                else None
            )
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
                # Carried so the prepared path reaches `genera_ui` as informative as the
                # legacy `MaterializedActivity` one: `_source_with_authored_activity` shows
                # the generator what its closer will ask so it teaches that first. Without
                # it this branch would keep writing screens blind to their own evaluation.
                "public_definition": dict(
                    getattr(activity, "public_definition", None) or {}
                ),
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
                support_prompt_ids = _ensure_support_interaction(
                    [
                        value
                        for value in state.get("prompt_component_ids") or ()
                        if value in _SUPPORT_PROMPT_COMPONENT_IDS
                    ]
                )
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
        # A small model at low temperature sometimes echoes the contract example placeholders
        # instead of grounding in the source. That is nonsense for the topic, so the grounding
        # gate rejects it; one retry with a firmer reminder recovers the rich activity often
        # enough to be worth a single extra fast-tier call before declining to a QuizItem.
        draft = None
        for attempt in range(2):
            attempt_user = user if attempt == 0 else (
                user
                + "\n\nEl intento anterior copio los valores de EJEMPLO del contrato sin "
                "cambiarlos. Cada item, opcion, par o categoria DEBE reescribirse con un "
                "hecho concreto del dossier (por ejemplo un tipo de golpe, un criterio, un "
                "paso real). No devuelvas 'Concepto A', 'Ejemplo B', 'termino A' ni ningun "
                "marcador generico."
            )
            raw, usage = await llm.complete_with_usage(
                system,
                attempt_user,
                temperature=0.2 if attempt == 0 else 0.4,
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
            # A parse/shape/empty-definition failure is a deliberate decline (the prompt asks
            # for an empty definition when the source is insufficient), so it is NOT retried.
            candidate_draft = authoring_draft_with_server_refs(
                parsed_draft,
                allowed_source_refs=allowed_refs,
            )
            # Grounding gate: a draft that copied the contract's example placeholders instead
            # of authoring from the source is nonsense for the topic. ONLY this failure is
            # worth one retry with a firmer reminder before declining to a grounded fallback.
            try:
                assert_grounded_activity_draft(candidate_draft)
            except ValueError:
                if attempt == 0:
                    continue
                raise
            draft = candidate_draft
            break
        assert draft is not None  # loop either sets draft, continues once, or raises
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


def _authored_experience_refs(authored: dict[str, Any]) -> tuple[str, str, str] | None:
    """The server-authoritative ``(experience_id, implementation_ref@version, definition_ref)``.

    The two authoring paths both land in ``authored_activity`` but with different shapes.
    The prepared path (migration 0016) carries the three refs explicitly. The legacy
    LLM-authoring path stores a ``MaterializedActivity``, whose model is ``extra="forbid"``
    with only ``activity_id``, ``component_id`` and ``public_definition`` — so the three refs
    are simply absent and have to be derived.

    Deriving them here, once, is the point: the prompt builder and the gate's pinning step
    used to read the same dict with *different* fallbacks. On the legacy path the prompt
    showed the model a correctly pinned ``component_id@1`` while
    ``_pin_authored_experience_refs`` read a bare ``implementation_ref``, found nothing, and
    silently no-opped. The model then had to copy an opaque versioned id by hand, dropped the
    ``@version`` (``"impl_ref"``, then ``"impl_ref_v1"`` on repair), and every screen carrying
    a ``LearningExperience`` burned the whole repair loop and fell back to a flat seed —
    measured as 11 of 13 gate rejections on 2026-08-27. One derivation, no drift.

    Returns ``None`` when no full, version-pinned triple can be formed, which is the signal
    that the server has no experience to pin and the screen must close some other way.
    """

    activity_id = str(authored.get("activity_id") or "")
    component_id = str(authored.get("component_id") or "")
    experience_id = str(authored.get("experience_id") or "") or activity_id
    implementation_ref = str(authored.get("implementation_ref") or "") or (
        f"{component_id}@1" if component_id else ""
    )
    definition_ref = str(authored.get("definition_ref") or "") or activity_id
    if not (experience_id and "@" in implementation_ref and definition_ref):
        return None
    return experience_id, implementation_ref, definition_ref


def _episode_node_context(state: NodeRuntimeState) -> dict[str, Any]:
    """The node's own identity and what the REST of the course covers, for the episode path.

    ``load_context`` has computed ``siblings`` since 2026-08-09, when six screens built from
    one short manual opened with the same sentence four times and asked practically the same
    question in all six. The fix never reached the path that runs today: ``siblings`` was
    read only by ``genera_ui_multi``, and ``build_node_graph`` swaps that generator out
    whenever ``ADAPTIVE_EPISODES`` is on. The episode brief carries the mission but not the
    node's title, its summary or its neighbours, so every adaptive render re-ran the exact
    failure the sibling list was written to stop — including asking about material that
    belongs to a different node, which reads to the learner as "nobody explained this".

    Returned as kwargs rather than three positional reads so the three episode builders
    (generate, repair, revise) cannot drift apart on which half of the context they pass.
    """

    node = state.get("node") or {}
    return {
        "node_title": str(node.get("title") or ""),
        "node_summary": str(node.get("summary") or ""),
        "siblings": list(state.get("siblings") or ()),
    }


#: How much of the activity's visible task travels with the generation prompt.
#:
#: ``genera_ui`` averages ~5 250 input tokens against a 6 000/min free-tier ceiling (see
#: ``load_source_context``), so the preview has to be a reminder, not a second source. The
#: publics it summarizes are small by contract — a title plus four to six short items — and
#: this cap only bites on a pathological one.
ACTIVITY_PREVIEW_MAX_CHARS = 700

#: Keys of a public activity definition that carry the learner-visible *task*.
_ACTIVITY_TASK_KEYS = ("title", "question", "prompt", "instruction")

#: Keys that carry one visible *piece* of the activity inside its item lists.
_ACTIVITY_PIECE_KEYS = ("content", "text", "label", "prompt", "before", "after")


def _activity_visible_pieces(value: Any, into: list[str]) -> None:
    """Collect the learner-visible strings of a public definition, ids excluded.

    Ids (``source-1``, ``gap-2``) are how the server correlates an answer, and they mean
    nothing to whoever writes the explanation. Dropping them keeps the preview short and,
    more importantly, keeps a machine token out of a prompt whose output is grepped for
    exactly that kind of copied server scaffolding (:func:`spec_scaffolding_markers`).
    """
    if isinstance(value, Mapping):
        for key in _ACTIVITY_PIECE_KEYS:
            piece = value.get(key)
            if isinstance(piece, str) and piece.strip():
                into.append(piece.strip())
        for child in value.values():
            if isinstance(child, (Mapping, list)):
                _activity_visible_pieces(child, into)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, str) and child.strip():
                into.append(child.strip())
            else:
                _activity_visible_pieces(child, into)


def _activity_task_preview(public_definition: Mapping[str, Any]) -> str:
    """One line of task plus the material it will ask about, or ``""`` if there is none."""

    task = ""
    for key in _ACTIVITY_TASK_KEYS:
        candidate = public_definition.get(key)
        if isinstance(candidate, str) and candidate.strip():
            task = candidate.strip()
            break

    pieces: list[str] = []
    for key, child in public_definition.items():
        if key in _ACTIVITY_TASK_KEYS or not isinstance(child, (Mapping, list)):
            continue
        _activity_visible_pieces(child, pieces)

    # Order-preserving dedup: matching repeats a term across sources and targets often
    # enough that the raw list reads like padding.
    unique = list(dict.fromkeys(pieces))
    lines = [line for line in (task, "; ".join(unique)) if line]
    preview = "\n".join(lines)
    if len(preview) > ACTIVITY_PREVIEW_MAX_CHARS:
        preview = preview[:ACTIVITY_PREVIEW_MAX_CHARS].rstrip() + "..."
    return preview


def _source_with_authored_activity(state: NodeRuntimeState) -> str:
    """Add the opaque id **and** the public projection to the UI-generation context.

    The docstring promised both since the seam was written; the code passed only the three
    ids, and that omission is the structural half of the mismatch the testers reported on
    2026-08-28 ("las preguntas no van con lo explicado"). ``author_activity`` runs *before*
    ``genera_ui`` — see ``build_node_graph`` — so the evaluation exists first and the
    explanation is written second, blind: with nothing but an opaque id in hand, the model
    writing the screen could not know what its own closer was about to ask. Whether the two
    lined up was luck.

    ``MaterializedActivity.public_definition`` is the answer-free half of the split
    (:func:`~src.services.activity_authoring.split_public_private` moves ``evaluation``,
    ``correct*``, ``answer*``, ``solution*`` and ``expected*`` to the private side, and
    ``validate_evaluation_definition`` re-asserts that the solution lives there). It is the
    same payload the learner's browser already receives, so showing it to the generator
    reveals nothing new — it only stops the generator from teaching around it.
    """

    source = str(state.get("source_context") or "")
    refs = _pinned_experience_refs(state)
    if refs is None:
        return source
    experience_id, implementation_ref, definition_ref = refs
    instruction = {
        "experience_id": experience_id,
        "implementation_ref": implementation_ref,
        "definition_ref": definition_ref,
    }
    block = (
        "\n\n## Experiencia preparada por el servidor\n"
        + "Incluye exactamente LearningExperience(experience_id, implementation_ref, "
        + "definition_ref) usando estos valores; no inventes otro id: "
        + json.dumps(instruction, ensure_ascii=False, sort_keys=True)
        + "\n"
    )

    authored = state.get("authored_activity")
    public_definition = (
        authored.get("public_definition") if isinstance(authored, dict) else None
    )
    preview = (
        _activity_task_preview(public_definition)
        if isinstance(public_definition, Mapping)
        else ""
    )
    if preview:
        block += (
            "\nESTA es la comprobacion que cerrara la pantalla, y el aprendiz la resolvera "
            "DESPUES de leerte:\n"
            + preview
            + "\nAsegurate de haber ENSENADO antes, en las pantallas de contenido, lo que "
            "hace falta para resolverla: si aparece un termino, una relacion o un dato en "
            "esa comprobacion, explicalo antes. No la copies ni la resumas en pantalla, y "
            "no reveles cual es la respuesta: solo prepara al aprendiz para ella.\n"
        )
    return source.rstrip() + block


def _with_source_scope(scoped_prompt: str, state: NodeRuntimeState) -> str:
    """Warn the generator when the source below is wider than this node's own material.

    Pure over ``state``: reads what ``load_context`` recorded and, when the scope widened,
    appends one bounded paragraph. No widening -> the prompt is returned unchanged, so a
    correctly scoped node never sees the block.

    The instruction it adds is deliberately asymmetric — **explain broadly, evaluate
    narrowly**. The four fallbacks in ``load_source_context`` exist so a node is never left
    with nothing to teach from, and that is still the right trade; what was wrong is that
    the generator could not tell borrowed material from its own, so it would happily close
    a screen by testing a fact that belongs three nodes further on. To the learner that is
    indistinguishable from never having been taught it, which is exactly what the testers
    reported on 2026-08-28.

    The reason is rendered from a closed vocabulary (:data:`_SCOPE_WIDENED_REASONS`), the
    same discipline ``_SIGNAL_RULES`` follows in the prompt module: a diagnostic string can
    never become free-form prose injected into a prompt.
    """
    scope = state.get("source_scope") or {}
    if not isinstance(scope, Mapping) or not scope.get("widened"):
        return scoped_prompt
    explanation = _SCOPE_WIDENED_REASONS.get(str(scope.get("reason") or ""))
    if not explanation:
        return scoped_prompt

    node = state.get("node") or {}
    title = str(node.get("title") or "").strip()
    focus = f'"{title}"' if title else "el titulo y el resumen de este nodo"
    return (
        scoped_prompt
        + "\n\n## Alcance de la fuente\n"
        + f"Aviso: {explanation}. Parte de ese material pertenece a OTROS nodos del curso.\n"
        + f"Ensena solo lo que corresponde a {focus}. Puedes apoyarte en el resto para dar "
        + "contexto, pero la comprobacion final SOLO puede preguntar por lo que hayas "
        + "explicado en esta pantalla: no evalues un dato que este en la fuente y no en tu "
        + "explicacion, porque el aprendiz no lo habra visto nunca.\n"
    )


def _with_media_offers(scoped_prompt: str, state: NodeRuntimeState) -> str:
    """Append the media broker's grounded whitelist addendum when offers exist for the node.

    Pure over ``state``: reads the ``media_offers`` computed (and preference-gated) in
    ``load_context`` and, if any, widens the prompt with the id-pinned PodcastPlayer /
    InfographicImage offer. No offers -> the prompt is returned unchanged, so a node with no
    ready artefact never sees the block and can never emit the component.
    """
    payload = state.get("media_offers") or ()
    if not payload:
        return scoped_prompt
    from src.agents.runtime.media_broker import MediaOffer, offers_prompt_addendum

    offers = [
        MediaOffer(
            kind=str(item.get("kind")),
            component=str(item.get("component")),
            artifact_id=str(item.get("artifact_id")),
            title=str(item.get("title") or ""),
        )
        for item in payload
        if item.get("artifact_id")
    ]
    addendum = offers_prompt_addendum(offers)
    return f"{scoped_prompt}\n{addendum}" if addendum else scoped_prompt


def _with_source_images(scoped_prompt: str, state: NodeRuntimeState) -> str:
    """Append the source-image broker's block: place these originals, re-express those.

    Pure over ``state``: reads what ``load_context`` already decided (course policy x
    image ``kind`` x the learner's ``images`` preference) and widens the scoped prompt
    with the id-pinned ``SourceImage`` whitelist, the rebuild instructions, or both.
    Neither -> the prompt is returned unchanged, so a node with no source images never
    sees the block and can never emit the component.
    """
    kept = state.get("source_image_offers") or ()
    rebuilds = state.get("source_image_rebuilds") or ()
    if not kept and not rebuilds:
        return scoped_prompt
    from src.agents.runtime.source_image_broker import (
        SourceImageDecision,
        SourceImageOffer,
        SourceImageRebuild,
        decision_prompt_addendum,
    )

    decision = SourceImageDecision(
        kept=tuple(
            SourceImageOffer(
                image_id=str(item.get("image_id")),
                alt=str(item.get("alt") or ""),
                caption=str(item.get("caption") or ""),
                document_id=str(item.get("document_id") or ""),
            )
            for item in kept
            if item.get("image_id")
        ),
        rebuilt=tuple(
            SourceImageRebuild(
                image_id=str(item.get("image_id")),
                description=str(item.get("description") or ""),
                caption=str(item.get("caption") or ""),
            )
            for item in rebuilds
            if item.get("description")
        ),
        considered=len(kept) + len(rebuilds),
    )
    addendum = decision_prompt_addendum(decision)
    if not addendum:
        return scoped_prompt
    return scoped_prompt + "\n" + addendum


def _guarantee_media_offers(
    spec_dict: dict, program: str, state: NodeRuntimeState | dict
) -> tuple[dict, str]:
    """Deterministically place any preference-gated media offer the model did not emit.

    The broker widens the prompt so the model *may* embed a ready PodcastPlayer/
    InfographicImage — or a ``SourceImage``, an original picture from the course's own
    source document — but a plan-driven episode (or the critic) routinely drops the
    optional reference, so a learner the offer was gated *for* would not reliably see it.
    This is the guarantee: after a program has already validated, if a gated offer for
    this node is not already referenced, append the id-pinned broker component to the root
    and re-serialize from the spec. Nothing here can crash a render — on any error the
    original (already valid) spec and program are returned untouched, honouring the
    gate-valid-program rule.

    Rebuilt source images are deliberately absent: they place no component at all, they
    only steer the prompt, so there is nothing here to guarantee.
    """
    offers = [*(state.get("media_offers") or ()), *(state.get("source_image_offers") or ())]
    if not offers:
        return spec_dict, program
    try:
        spec = UISpec.model_validate(spec_dict)
        present = {
            str(component.props.get(key))
            for component in spec.components
            for key in ("artifact_id", "image_id")
            if component.props.get(key)
        }
        components = list(spec.components)
        root = next((c for c in components if c.id == spec.root), None)
        if root is None:
            return spec_dict, program

        added_ids: list[str] = []
        for index, offer in enumerate(offers):
            component_type = str(offer.get("component") or "")
            # A source image is addressed by ``image_id``, a media artefact by
            # ``artifact_id``; both are the real row id and neither is ever invented.
            offered_id = str(offer.get("artifact_id") or offer.get("image_id") or "")
            if not offered_id or offered_id in present:
                continue
            if component_type == "PodcastPlayer":
                props = {"artifact_id": offered_id, "title": str(offer.get("title") or "Audio overview")}
            elif component_type == "InfographicImage":
                props = {"artifact_id": offered_id, "alt": str(offer.get("title") or "Infografia")}
            elif component_type == "SourceImage":
                # Prop order matters and `document_id` is last: see `SourceImageOffer`.
                props = {
                    "image_id": offered_id,
                    "alt": str(offer.get("alt") or "Imagen del documento de origen"),
                    "caption": str(offer.get("caption") or ""),
                    "document_id": str(offer.get("document_id") or ""),
                }
            else:
                continue
            new_id = f"brokerMedia{index + 1}"
            components.append(Component(id=new_id, type=component_type, props=props))
            added_ids.append(new_id)
            present.add(offered_id)

        if not added_ids:
            return spec_dict, program

        new_root = root.model_copy(
            update={"children": [*root.children, *added_ids]}
        )
        components = [new_root if c.id == root.id else c for c in components]
        new_spec = spec.model_copy(update={"components": components})
        backend = get_render_backend(str(state.get("backend") or "openui"))
        new_program = backend.serialize(new_spec)
        return new_spec.model_dump(), new_program
    except Exception as exc:  # noqa: BLE001 - a media guarantee must never break a render
        logger.warning("Could not inject broker media offer into render: %s", exc)
        return spec_dict, program


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
    # Broker addendum: when a READY media artefact exists for this node and the learner's
    # modality preference allows it, widen the closed scope with a grounded, id-pinned
    # PodcastPlayer/InfographicImage offer. A misused offer still fails the gate -> fallback.
    scoped_prompt = _with_media_offers(scoped_prompt, state)
    scoped_prompt = _with_source_images(scoped_prompt, state)
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
            learning_note=str(profile.get("learning_note") or ""),
            **_episode_node_context(state),
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
            learning_note=str(profile.get("learning_note") or ""),
            **_episode_node_context(state),
        )
        # The episode brief in the user turn is what the model treats as authoritative, so a
        # media offer folded only into the system grammar (which makes the component valid but
        # unplanned) is reliably dropped. Repeat the id-pinned directive here so a
        # preference-matching learner actually gets the artefact placed into the episode.
        user_prompt = _with_media_offers(user_prompt, state)
        user_prompt = _with_source_images(user_prompt, state)
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
            learning_note=str(profile.get("learning_note") or ""),
        )

    # After every branch, repairs included: the user turn is what the model treats as
    # authoritative, and a node reading a widened source must be told so on all four paths
    # or the one that misses it keeps evaluating on a sibling's material. No-op unless
    # `load_context` recorded a widening.
    user_prompt = _with_source_scope(user_prompt, state)

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

    # The scope warning travels on the source itself here, because the source is the only
    # channel these two agents share with the caller — they build their own prompts. Kept in
    # sync with `genera_ui` deliberately: this generator is unreachable while
    # ADAPTIVE_EPISODES is on, so the day someone turns that flag off is exactly the day the
    # widening fix would go missing with no error to notice it by.
    #
    # `_source_with_authored_activity` is NOT applied: on this path the assembler emits the
    # `LearningExperience` deterministically from `authored_activity`, so telling the writers
    # to emit one too would produce it twice.
    multi_source = _with_source_scope(str(state.get("source_context") or ""), state)

    # --- Agents 2+3: Content Writer + Interaction Designer (PARALLEL) ---
    content_coro = run_content_writer(
        blueprint=blueprint,
        title=str(node.get("title") or ""),
        summary=str(node.get("summary") or ""),
        source_context=multi_source,
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
            source_context=multi_source,
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
        # A server-authored Didact activity owns the closer: the assembler emits the neutral
        # LearningExperience deterministically so the rich interactive activities surface.
        # Only when the triple is derivable: with a dict the server cannot pin, the
        # assembler would emit a LearningExperience referencing ids nobody can resolve.
        authored_activity=state.get("authored_activity")
        if _has_prepared_experience(state)
        else None,
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


_LEARNING_EXPERIENCE_CALL = re.compile(
    r'LearningExperience\(\s*"(?:[^"\\]|\\.)*"\s*,\s*"(?:[^"\\]|\\.)*"\s*,'
    r'\s*"(?:[^"\\]|\\.)*"\s*\)'
)


def _pin_authored_experience_refs(program_text: str, state: NodeRuntimeState) -> str:
    """Rewrite ``LearningExperience`` refs with the server-authoritative ones.

    The three refs (``experience_id``, ``implementation_ref@version``, ``definition_ref``)
    are server-owned identity: ``author_activity`` resolves them from the published plan and
    injects them into the prompt for the model to copy verbatim. Models routinely drop the
    ``@version`` suffix or invent semantic-looking ids ("impl_memoria_fases"), which the gate
    then rejects (`implementation_ref must pin a version`), and the whole personalized episode
    falls back to a flat Markdown seed. Rewriting the call from ``authored_activity`` makes
    that class of copy-fidelity failures impossible instead of asking an 8B model to copy an
    opaque versioned id perfectly. No-op unless authoring prepared a full, version-pinned ref.

    The refs come from :func:`_pinned_experience_refs`, the same derivation the prompt
    builder, the assembler and the closer policy use. Reading ``authored_activity`` directly
    here is what broke the net on the legacy authoring path: see
    :func:`_authored_experience_refs`.
    """
    refs = _pinned_experience_refs(state)
    if refs is None:
        return program_text
    experience_id, implementation_ref, definition_ref = refs
    replacement = (
        f'LearningExperience("{experience_id}", '
        f'"{implementation_ref}", "{definition_ref}")'
    )
    return _LEARNING_EXPERIENCE_CALL.sub(replacement, program_text)


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
    if _has_prepared_experience(state):
        program_text = _pin_authored_experience_refs(program_text, state)
    elif "LearningExperience(" in program_text:
        # No *pinnable* experience for this node — authoring declined, or it produced a
        # payload no full triple can be derived from — so a ``LearningExperience`` here
        # references nothing real: the model invented its ids and the gate would reject it
        # with the opaque "must pin a version", which sends the repair attempts chasing a
        # version suffix instead of the real fix. Fail with an actionable message instead,
        # naming only a closer this screen is actually allowed to emit.
        closers = _offerable_closers(state)
        return {
            "ui_spec": None,
            "validation_errors": [
                "No hay ninguna experiencia preparada por el servidor para este nodo, asi "
                "que NO uses LearningExperience (inventarias ids que no existen). Cierra la "
                "pantalla con una interaccion REAL anclada en la fuente: "
                + " o ".join(f"un {name}" for name in closers)
                + "."
            ],
            "retry_count": int(state.get("retry_count") or 0) + 1,
            "current_step": "validate_ui",
        }
    try:
        spec, program = canonicalize(
            program_text,
            ui_format=ui_format,
            backend=get_render_backend(backend_name),
        )
    except RenderError as exc:
        errors = list(getattr(exc, "errors", None) or [str(exc)])
        logger.warning(
            "validate_ui_rejected node=%s retry=%s shell=%s errors=%s raw=%r",
            state.get("node_id"),
            state.get("retry_count"),
            state.get("shell_mode"),
            errors,
            program_text[:1500],
        )
        return {
            "ui_spec": None,
            "validation_errors": errors,
            "retry_count": int(state.get("retry_count") or 0) + 1,
            "current_step": "validate_ui",
        }

    # Defence in depth against the leak of 2026-08-27. The prompt shows the model the
    # dossier's internal references next to the text of every point, so a model that
    # paraphrases badly (or copies) can carry ``must.atom:10`` or ``## Invariantes`` into a
    # prop. This is **rejected into the repair loop**, not scrubbed: the token is only the
    # visible symptom of a screen that transcribed the server's scaffolding instead of
    # teaching from it, so deleting the marker would leave a mutilated sentence that was
    # never written for a learner either. Rejecting gives the model the one repair attempt
    # it already has, and after that ``fallback_seed`` serves the node summary — a screen,
    # never the dossier. Same return shape as the other content-level refusals below.
    leaked = spec_scaffolding_markers(spec)
    if leaked:
        logger.warning(
            "validate_ui_leaked_scaffolding node=%s retry=%s markers=%s",
            state.get("node_id"),
            state.get("retry_count"),
            leaked,
        )
        return {
            "ui_spec": None,
            "validation_errors": [
                "El texto copia andamiaje interno del servidor: "
                + ", ".join(leaked[:6])
                + ". Los titulos del dossier y sus referencias (must.*, selectable.*, "
                "(ref ...)) son instrucciones para ti, no contenido. Reescribe cada bloque "
                "con prosa que el aprendiz pueda leer, explicando el hecho con tus "
                "palabras y sin ninguna referencia ni titulo del dossier."
            ],
            "retry_count": int(state.get("retry_count") or 0) + 1,
            "current_step": "validate_ui",
        }

    # The required closer can fall back from LearningExperience to a real interaction when
    # no prepared experience can be pinned (see _allowed_closers) — genera_ui's prompt and
    # screen_scheme follow that same fallback, so the prohibition must too, or a correctly
    # obedient model gets rejected for writing exactly the closer it was told to. That
    # mismatch was a measured deadlock, not a hypothetical. ``_forbidden_closers`` carries
    # both the scope (Didact screens only) and the complement, and every repair message
    # subtracts it, so nothing recommended here can be refused there.
    refused = _forbidden_closers(state)
    forbidden = sorted({c.type for c in spec.components if c.type in refused})
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

    # Hard guard: the screen must never CLOSE on a Flashcard. The shortlist only steers the
    # model, so on a support screen it sometimes ends with a Flashcard (a reveal) as the last
    # block — exactly the ``flashcard_as_closer`` the owner banned. Reject it so the repair
    # loop re-ends the screen with a real interaction (DragOrder / QuizItem). A Flashcard is
    # still allowed as CONTENT anywhere earlier on the screen.
    non_container = [
        component
        for component in spec.components
        if component.type not in {"Stack", "Card"}
    ]
    if non_container and non_container[-1].type == "Flashcard":
        # Name only closers this screen may actually emit: in Didact mode the prohibition
        # above rejects a DragOrder, so the old unconditional "DragOrder, o un QuizItem"
        # could send the repair at a forbidden component. See ``_offerable_closers``.
        closers = _offerable_closers(state)
        return {
            "ui_spec": None,
            "validation_errors": [
                "La ULTIMA interaccion de la pantalla es una Flashcard, que solo REVELA "
                "informacion y no evalua. Cierra la pantalla con una interaccion REAL que "
                "el aprendiz ejecuta ("
                + " o ".join(f"un {name}" for name in closers)
                + "). La Flashcard puede quedarse antes como contenido de apoyo, nunca "
                "como cierre."
            ],
            "retry_count": int(state.get("retry_count") or 0) + 1,
            "current_step": "validate_ui",
        }

    key_problems = answer_key_problems(spec, answer_key)
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
# Node 5b: critic_episode (optional, fail-open) — one review + one revision
# --------------------------------------------------------------------------- #
def _root_child_count(spec_payload: Any) -> int:
    """How many screens the paginated episode currently has (root's direct children)."""

    if not isinstance(spec_payload, dict):
        return 0
    root_id = spec_payload.get("root")
    for component in spec_payload.get("components") or ():
        if isinstance(component, dict) and component.get("id") == root_id:
            children = component.get("children")
            return len(children) if isinstance(children, list) else 0
    return 0


async def critic_episode(state: NodeRuntimeState) -> dict:
    """Review the pedagogy of a valid episode and revise ONCE (``MAX_UI_RETRIES`` unused).

    Lean by construction: it runs only for episode-shell renders when ``MULTI_AGENT_RENDER``
    is on, calls a single critic from a different perspective, and applies at most one
    revision. A revision that fails validation is discarded — the already-valid episode is
    never regressed to fallback, which is the Phase-1 gate-safety promise.
    """

    from src.config import settings

    episode_payload = state.get("episode_brief")
    spec_payload = state.get("ui_spec")
    if (
        not settings.MULTI_AGENT_RENDER
        or not isinstance(episode_payload, dict)
        or not isinstance(spec_payload, dict)
        or not spec_payload
    ):
        return {"current_step": "critic_episode"}

    from src.agents.runtime.agents.episode_critic import run_episode_critic
    from src.llm.prompts.runtime import (
        build_episode_revise_prompt,
        episode_ui_revise_system,
    )

    request_id = str(state["request_id"])
    org_id = _uuid(state["org_id"])
    node = state.get("node") or {}
    ui_format = coerce_ui_format(state.get("ui_format"))
    backend_name = str(state.get("backend") or "openui")
    screen_count = _root_child_count(spec_payload)
    program = str(state.get("program") or "")
    assessment_mode = "none" if not state.get("assessment_block") else "evidence"

    await publish_step(request_id, "critic_episode", STEP_MESSAGES["critic_episode"])

    trace = dict(state.get("plan_trace") or {})
    started = time.monotonic()
    try:
        llm = await _make_llm(org_id, "fast")
        verdict = await run_episode_critic(
            title=str(node.get("title") or ""),
            summary=str(node.get("summary") or ""),
            domain=str(node.get("domain") or ""),
            program=program,
            screen_count=screen_count,
            assessment_mode=assessment_mode,
            llm=llm,
        )
    except Exception:  # noqa: BLE001 - critic is optional
        logger.info("critic_episode_unavailable", exc_info=True)
        return {"current_step": "critic_episode"}

    trace["critic"] = {
        "revise": verdict.revise,
        "notes": list(verdict.notes),
        "screens_before": screen_count,
        "applied": False,
    }
    if not verdict.actionable:
        return {"plan_trace": trace, "current_step": "critic_episode"}

    # One revision. Reuse the episode dialect and re-run the same gate. If anything is off,
    # keep the original valid episode.
    try:
        scoped_prompt, _scope = resolve_runtime_prompt(
            state.get("prompt_component_ids") or (),
            additional_required=_prompt_assessment_required(state),
            enabled=True,
        )
        scoped_prompt = _with_media_offers(scoped_prompt, state)
        scoped_prompt = _with_source_images(scoped_prompt, state)
        system = episode_ui_revise_system(scoped_prompt)
        user_prompt = build_episode_revise_prompt(
            episode=episode_payload,
            source_context=_source_with_authored_activity(state),
            previous=program,
            notes=verdict.notes,
            learning_note=str((state.get("profile") or {}).get("learning_note") or ""),
            **_episode_node_context(state),
        )
        # The revision is a FULL regeneration, not a patch, so it needs the same warning
        # `genera_ui` gets on all four of its paths — and needs it more: the critic's own
        # grounding note makes "you evaluated what you never taught" the likeliest reason
        # to be here, and this path cannot retry. Without it the rewrite loses "explain
        # broadly, evaluate narrowly" and can re-introduce the very question that
        # triggered the revision. No-op unless `load_context` recorded a widening.
        user_prompt = _with_source_scope(user_prompt, state)
        raw, usage = await llm.complete_with_usage(
            system,
            user_prompt,
            temperature=UI_TEMPERATURE,
            max_tokens=ui_max_tokens(str(state.get("tier") or "fast")),
            json_mode=False,
        )
        program_text, answer_key = split_answer_key(raw)
        # The revision is a fresh generation, so it re-invents LearningExperience refs just
        # like the first pass. Re-apply the same server authority as validate_ui, or the
        # critic silently reintroduces the hallucinated refs it can't be trusted to copy —
        # and unlike validate_ui there is no repair loop here, so a bad ref would be served.
        if _has_prepared_experience(state):
            program_text = _pin_authored_experience_refs(program_text, state)
        elif "LearningExperience(" in program_text:
            # No prepared activity: a LearningExperience here references nothing real and
            # would 404 at serve time ("no se pudo cargar la actividad"). Discard the
            # revision and keep the original valid episode validate_ui already pinned.
            raise ValueError("revised episode invented an unbacked LearningExperience")
        spec, revised_program = canonicalize(
            program_text,
            ui_format=ui_format,
            backend=get_render_backend(backend_name),
        )
        if answer_key_problems(spec, answer_key):
            # The full check, not just presence: this path has NO repair loop, so a
            # malformed key here is served. A revision that comes back with
            # `{"correct": "false"}` on a true_false would grade every answer backwards —
            # `bool("false")` is True — and `missing_answer_keys` waves it through because
            # the entry exists. Same for an out-of-range index and for `order_steps`.
            # Discarding keeps the episode `validate_ui` already cleared, which is the
            # rule every other refusal in this block follows.
            raise ValueError("revised episode has an unusable answer key")
        leaked = spec_scaffolding_markers(spec)
        if leaked:
            # The revision is a fresh generation from the same prompt, so it can copy the
            # dossier's own references and headings exactly as ``genera_ui`` can — and here
            # there is no repair loop, so a leak would be served. Discard the revision and
            # keep the episode ``validate_ui`` already cleared.
            raise ValueError(f"revised episode copied internal scaffolding: {leaked}")
    except Exception as exc:  # noqa: BLE001 - keep the original valid episode
        logger.info("critic_revision_discarded %s", type(exc).__name__, exc_info=True)
        await log_usage(
            async_session_factory,
            org_id=org_id,
            user_id=state.get("user_id"),
            use_case="runtime_episode_critic",
            purpose=purpose_for("fast"),
            model=getattr(llm, "model", "unknown"),
            tier="fast",
            tokens_in=None,
            tokens_out=None,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return {"plan_trace": trace, "current_step": "critic_episode"}

    await log_usage(
        async_session_factory,
        org_id=org_id,
        user_id=state.get("user_id"),
        use_case="runtime_episode_critic",
        purpose=purpose_for("fast"),
        model=getattr(llm, "model", "unknown"),
        tier="fast",
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    trace["critic"]["applied"] = True
    trace["critic"]["screens_after"] = _root_child_count(spec.model_dump())
    logger.info(
        "critic_revision_applied node=%s screens %s->%s notes=%s",
        state.get("node_id"),
        screen_count,
        trace["critic"]["screens_after"],
        list(verdict.notes),
    )
    return {
        "ui_spec": spec.model_dump(),
        "program": revised_program,
        "raw_dsl": raw,
        "answer_key": prune_answer_key(spec, answer_key),
        "plan_trace": trace,
        "tokens_in": _accumulate(state.get("tokens_in"), usage.tokens_in),
        "tokens_out": _accumulate(state.get("tokens_out"), usage.tokens_out),
        "duration_ms": int(state.get("duration_ms") or 0)
        + int((time.monotonic() - started) * 1000),
        "current_step": "critic_episode",
    }


# --------------------------------------------------------------------------- #
# Node 6: persist_render
# --------------------------------------------------------------------------- #
#: Root must keep at least this many children after a phantom experience is dropped for
#: the render to be worth serving as content. A lead-only screen (1 child) is effectively
#: empty, so we fall back rather than serve it.
_MIN_ROOT_CHILDREN_AFTER_DROP = 2


async def _definition_ref_resolves(
    db: Any, definition_ref: Any, org_id: uuid.UUID
) -> bool:
    """Whether ``definition_ref`` is a REAL ``activity_definitions`` row in this org.

    Mirrors exactly how the serve-time route resolves it: ``ActivityDefinitionService.get``
    -> ``ActivityDefinitionRepository.get_scoped(activity_id, org_id)``. A hallucinated ref
    (``def_memoria_almacenes``) is not even a UUID, so it fails the parse; a well-formed but
    non-existent UUID fails the scoped lookup. Either way the frontend would 404 and show
    "esta actividad no esta disponible", so we treat both as unresolvable.
    """
    try:
        activity_id = uuid.UUID(str(definition_ref))
    except (ValueError, AttributeError, TypeError):
        return False
    row = await ActivityDefinitionRepository(db).get_scoped(activity_id, org_id)
    return row is not None


async def _phantom_experience_ids(
    spec_payload: dict[str, Any], org_id: uuid.UUID, db: Any
) -> set[str]:
    """Component ids of ``LearningExperience`` blocks whose ``definition_ref`` is phantom."""
    phantom: set[str] = set()
    for component in spec_payload.get("components") or ():
        if not isinstance(component, dict) or component.get("type") != "LearningExperience":
            continue
        props = component.get("props") or {}
        definition_ref = props.get("definition_ref")
        if not await _definition_ref_resolves(db, definition_ref, org_id):
            component_id = component.get("id")
            if isinstance(component_id, str):
                phantom.add(component_id)
    return phantom


def _drop_components(spec_payload: dict[str, Any], drop_ids: set[str]) -> dict[str, Any]:
    """Remove ``drop_ids`` from the flat list and from every ``children`` array."""
    components: list[dict[str, Any]] = []
    for component in spec_payload.get("components") or ():
        if not isinstance(component, dict) or component.get("id") in drop_ids:
            continue
        cloned = dict(component)
        cloned["children"] = [
            child
            for child in (component.get("children") or [])
            if child not in drop_ids
        ]
        components.append(cloned)
    pruned = {**spec_payload, "components": components}
    # ``generation`` is server-only provenance added by ``_persist`` after the contract
    # passes; it is excluded from ordinary dumps, so a re-validation here must not carry it.
    pruned.pop("generation", None)
    return pruned


@runtime_node_error_wrapper("persist_render")
async def persist_render(state: NodeRuntimeState) -> dict:
    """Write ``status='ready'`` with the canonical program and its provenance (§3.4).

    Before anything is stored, a deterministic serve-time guard closes the phantom
    ``LearningExperience`` class end to end (§5.1). A rendered episode can carry a
    ``LearningExperience(experience_id, implementation_ref, definition_ref)`` whose refs the
    model invented (``def_memoria_almacenes``) instead of copying the real activity-definition
    UUID; earlier pins in ``validate_ui`` / the critic reduced but did not eliminate it, and a
    cached render could still ship one. At serve time the frontend fetches
    ``GET /activities/{definition_ref}/definition`` and gets a 404 -> "esta actividad no esta
    disponible". Here every ``LearningExperience`` is resolved against ``activity_definitions``
    in the node's org exactly as the route does; any that does not resolve is DROPPED (its id
    also pulled from every ``children`` array) and the spec is re-canonicalized. If dropping
    leaves a servable screen (>= a lead plus real content) it is served; otherwise this render
    falls back to the seed lesson rather than serve a broken activity.
    """
    spec_payload = state.get("ui_spec")
    if isinstance(spec_payload, dict) and spec_payload:
        org_id = _uuid(state["org_id"])
        async with async_session_factory() as db:
            phantom = await _phantom_experience_ids(spec_payload, org_id, db)
        if phantom:
            logger.warning(
                "persist_render dropping %d phantom LearningExperience component(s) "
                "node=%s render=%s ids=%s",
                len(phantom),
                state.get("node_id"),
                state.get("render_id"),
                sorted(phantom),
            )
            pruned = _drop_components(spec_payload, phantom)
            backend = get_render_backend(str(state.get("backend") or "openui"))
            try:
                spec = parse_spec(pruned)
                root = spec.component(spec.root)
                if root is None or len(root.children) < _MIN_ROOT_CHILDREN_AFTER_DROP:
                    raise RenderValidationError(
                        ["dropping the phantom experience left no servable content"]
                    )
                program = backend.serialize(spec)
            except RenderError as exc:
                logger.warning(
                    "persist_render could not salvage spec after dropping phantom "
                    "experience(s) node=%s render=%s: %s; serving fallback",
                    state.get("node_id"),
                    state.get("render_id"),
                    exc,
                )
                return await _serve_fallback(state)
            # A dropped closer carries no client-side answer key of its own; the surviving
            # QuizItem entries (if any) are re-pruned against the reduced spec.
            state = {
                **state,
                "ui_spec": spec.model_dump(),
                "program": program,
                "answer_key": prune_answer_key(spec, dict(state.get("answer_key") or {})),
            }
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

    # Reaching this node means generation really failed for this node, and the row alone
    # does not say why: ``node_renders`` records the *fallback*, and the wrapper's traceback
    # (when there was one) is a separate line with no render_id in it. One structured line
    # here is what makes "why is this course serving fallbacks?" answerable from the logs
    # without a debugger: which branch of the graph arrived, with which validator
    # complaints, at which retry, and whether there was any seed lesson to fall back on.
    logger.warning("fallback_seed reached %s", _fallback_diagnostics(state))
    await publish_step(request_id, "fallback_seed", STEP_MESSAGES["fallback_seed"])
    return await _serve_fallback(state, step="fallback_seed")


def _fallback_diagnostics(state: NodeRuntimeState | dict) -> dict[str, Any]:
    """Everything the log needs to explain *why* this render fell back.

    ``cause`` distinguishes the three ways in (see ``agents/runtime/graph.py``): an
    exception in any node (short-circuited by ``runtime_node_error_wrapper``, whose message
    already carries the failing step), the repair loop running out of attempts, and the
    serve-time guards of ``persist_render``. Everything else is context that turns a cause
    into a diagnosis.
    """
    node = state.get("node") or {}
    error = str(state.get("error") or "")
    validation_errors = list(state.get("validation_errors") or [])
    if error:
        cause = "node_error"
    elif validation_errors:
        cause = "validation_exhausted"
    else:
        cause = "unknown"
    return {
        "cause": cause,
        "node_id": str(state.get("node_id") or ""),
        "render_id": str(state.get("render_id") or ""),
        "course_id": str(state.get("course_id") or ""),
        "step": str(state.get("current_step") or ""),
        # The wrapper's message is ``[step] Type: text``, so this names the failing node.
        "error": error[:300],
        "retry_count": int(state.get("retry_count") or 0),
        "validation_errors": [str(item)[:200] for item in validation_errors[:4]],
        "ui_format": str(state.get("ui_format") or ""),
        "shell_mode": str(state.get("shell_mode") or ""),
        "episode_status": str(state.get("episode_status") or ""),
        "episode_decline_reason": str(state.get("episode_decline_reason") or ""),
        "activity_authoring_status": str(state.get("activity_authoring_status") or ""),
        "knowledge_pack_hash": str(state.get("knowledge_pack_hash") or ""),
        "has_seed_lesson": bool(node.get("seed_lesson_id")),
        "has_summary": bool(str(node.get("summary") or "").strip()),
        "source_context_chars": len(str(state.get("source_context") or "")),
    }


#: The last link of the fallback content chain: what the learner is told when the node has
#: no human-written text at all to fall back on. It is *served*, as a one-block ``fallback``
#: screen, not merely announced on the SSE channel — a request that serves nothing leaves
#: the pin empty, and an empty pin is a ``202 pending`` the client polls for ever and pays an
#: LLM generation for each time (see :func:`_serve_fallback`). Dumping ``source_context``
#: instead is what put the server's own prompt on a learner's screen.
NOTHING_SERVABLE_MESSAGE = (
    "No hemos podido preparar este nodo. Vuelve a intentarlo en un momento."
)


async def _serve_fallback(
    state: NodeRuntimeState | dict, *, step: str = "persist_render"
) -> dict:
    """Build the fallback spec from human-written text and persist it as ``'fallback'``.

    Shared by ``fallback_seed`` (the graph's safety net) and ``persist_render`` (the
    serve-time phantom-experience guard, when dropping the bad activity leaves nothing
    servable). The body is the v1 seed lesson, or failing that the node's summary — the only
    two texts reachable from this state that a human wrote **for a learner to read** — and
    with neither, :data:`NOTHING_SERVABLE_MESSAGE`, which says so.

    That last link is what makes the chain terminate. Until 2026-08-27 this branch served
    **nothing**: the row was marked ``failed`` and no render was pinned, so
    ``GET /nodes/{id}/render`` answered ``202 pending`` for ever — a spinner the learner
    could never get past — and the client kept re-arming ``POST /render`` because nothing
    was served. With no pin there was no *fallback* pin either, which is the only thing
    ``request_render`` used to charge the retry budget for, and ``find_cached`` cannot see a
    ``failed`` row: every single poll therefore bought a fresh LLM generation, without
    limit. A one-sentence screen ends both. It is a ``fallback`` row like any other, which
    is exactly the status that is **not** retained: ``pinned_render`` swaps the pin for a
    ``ready`` render as soon as one exists, and the retry budget spends at most
    ``FALLBACK_RETRY_MAX_ATTEMPTS`` generations on the key while trying to produce one.

    ``state["source_context"]`` sat between those two until 2026-08-27 and must never go
    back. It is the **server prompt**, not content: with a validated knowledge pack it is
    the dossier rendered by
    ``knowledge_pack.runtime_selection._render_context`` — a ``# Dossier pedagógico
    seleccionado`` title, internal ``## Invariantes`` / ``## Material adaptable`` headings
    and one program-minted reference per point (``must.atom:10``) — and without one it is a
    raw slice of the customer's PDF. A course authored natively in v2 has **no**
    ``seed_lesson_id``, so this was not the exotic branch: it was the normal one, and a
    learner read the server's own instructions to the model as their lesson, atom ids
    included. Whatever is added to this chain has to be prose written for a human.
    """
    node = state.get("node") or {}
    seed_lesson_id = node.get("seed_lesson_id")
    content = ""
    body_source = "seed_lesson"

    if seed_lesson_id:
        async with async_session_factory() as db:
            lesson = await db.get(Lesson, _uuid(seed_lesson_id))
            content = (lesson.content or "") if lesson is not None else ""
    if not content.strip():
        # The common case for a v2-native course: no seed lesson exists at all. The summary
        # is the "esto te sirve para X" sentence the schema designer wrote, so it is short
        # but it is real content, and it is already what rule 7's lead slot is filled with.
        content = str(node.get("summary") or "").strip()
        body_source = "node_summary"
    leaked = leaked_scaffolding_markers(content)
    if leaked:
        # Belt and braces: a seed lesson or summary carrying dossier markers means the leak
        # was already persisted upstream (a seed generated from a dossier, say). Drop it
        # rather than re-serve it, and log loudly — this branch is a bug elsewhere.
        logger.error(
            "fallback body carries internal scaffolding; refusing to serve it "
            "node=%s render=%s body_source=%s markers=%s",
            state.get("node_id"),
            state.get("render_id"),
            body_source,
            leaked,
        )
        content = ""
    if not content.strip():
        logger.error(
            "nothing servable for node=%s render=%s step=%s: no seed lesson (%s) and no "
            "usable summary; serving the honest message instead. source_context is NOT a "
            "fallback body — it is the server prompt.",
            state.get("node_id"),
            state.get("render_id"),
            step,
            node.get("seed_lesson_id"),
        )
        content = NOTHING_SERVABLE_MESSAGE
        body_source = "nothing_servable"

    lead = str(node.get("title") or "")
    if body_source == "seed_lesson":
        # A full lesson as the body: the summary is the lead it was written for. When the
        # body IS the summary, or the summary was just dropped for carrying scaffolding,
        # only the title may lead — printing the same sentence twice, or re-serving the
        # markers in the lead slot, is what this branch exists to avoid.
        lead = str(node.get("summary") or node.get("title") or "")
    if leaked_scaffolding_markers(lead):
        # The lead is on screen too, so it faces the same bar as the body.
        logger.error(
            "fallback lead carries internal scaffolding; dropping it node=%s render=%s",
            state.get("node_id"),
            state.get("render_id"),
        )
        lead = ""
    spec = build_fallback_spec(summary=lead, content=content)
    backend = get_render_backend(str(state.get("backend") or "openui"))
    program = backend.serialize(spec)

    return await _persist(
        {
            **state,
            "ui_spec": spec.model_dump(),
            "program": program,
            "answer_key": {},
            "ui_format": "explanation",
        },
        status=NodeRenderStatus.FALLBACK,
        step=step,
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
    # Guarantee the preference-gated media offer is present before the row is frozen: the
    # model may (and often does) drop the optional broker reference, so this is what makes a
    # matching learner reliably see the podcast/infographic inline. Never fatal.
    if spec:
        persisted_spec, program = _guarantee_media_offers(dict(spec), program, state)
    else:
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
    "NOTHING_SERVABLE_MESSAGE",
    "RETRIEVAL_TOP_K",
    "STEP_MESSAGES",
    "answer_key_problems",
    "author_activity",
    "build_fallback_spec",
    "critic_episode",
    "decide_formato",
    "direct_episode",
    "fallback_seed",
    "genera_ui",
    "genera_ui_multi",
    "leaked_scaffolding_markers",
    "load_context",
    "load_source_context",
    "missing_answer_keys",
    "persist_render",
    "probe_gate",
    "prune_answer_key",
    "skip_node",
    "spec_scaffolding_markers",
    "split_answer_key",
    "unusable_answer_keys",
    "validate_ui",
]
