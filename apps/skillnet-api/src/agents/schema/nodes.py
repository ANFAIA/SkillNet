"""Graph nodes for the design-time schema proposal pipeline (§4.1).

These nodes are **new**, not imported from ``src/agents/content/nodes.py``. The v1
nodes look reusable and are not: they write v1 job states (``extracting``,
``structuring``) and publish generic ``step`` events, so reusing them would leave a
schema job reporting a status it never has and emitting events no schema client
listens for. What *is* shared is the pure part — ``src/agents/content/helpers.py``,
``THEME_EXTRACTOR_SYSTEM`` and ``build_extraction_prompt``.

Nothing here generates content. The whole point of the design-time phase is that it
produces a schema and stops, so a human can read it before a single token of
learner-facing material exists.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from src.agents.content.helpers import (
    FULL_TEXT_PAGE_THRESHOLD,
    assemble_chunk_text,
    estimate_pages,
    themes_list,
)
from src.agents.schema.errors import schema_node_error_wrapper, sse_channel
from src.agents.schema.state import SchemaState
from src.core import sse
from src.core.logging import get_logger
from src.core.tasks import task_registry
from src.deps.db import async_session_factory
from src.llm.client import LLMService, resolve_llm_config
from src.llm.fixtures import maybe_fixture_llm
from src.llm.parsing import parse_json_response
from src.llm.prompts import THEME_EXTRACTOR_SYSTEM, build_extraction_prompt
from src.llm.prompts.schema import SCHEMA_DESIGNER_SYSTEM, build_schema_prompt
from src.models import (
    Course,
    CourseNode,
    CourseNodePrerequisite,
    CourseSchemaStatus,
    Document,
    DocumentChunk,
    GenerationStep,
    Organization,
)
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.repositories.generation_job_repo import GenerationJobRepository
from src.services.course_schema_service import (
    coerce_criticality,
    coerce_ui_format,
    default_threshold_for,
    prune_cyclic_prerequisites,
    topological_order,
)

logger = get_logger(__name__)

SCHEMA_TEMPERATURE = 0.2
SCHEMA_MAX_TOKENS = 8192
EXTRACT_TEMPERATURE = 0.3
EXTRACT_MAX_TOKENS = 4096
# Hard ceiling on a proposal. A model that returns 300 "nodes" has misunderstood
# the task, and persisting them would make the review panel unusable.
MAX_PROPOSED_NODES = 40


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _org_settings(db: Any, org_id: uuid.UUID) -> dict[str, Any]:
    """Return the organization's provider-override settings (or empty)."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
    return dict(org.settings) if org and org.settings else {}


async def _make_llm(org_id: uuid.UUID) -> LLMService:
    async with async_session_factory() as db:
        org_settings = await _org_settings(db, org_id)
    return maybe_fixture_llm(resolve_llm_config(org_settings, purpose="generation"))


async def _run_knowledge_pack_shadow(
    course_id: uuid.UUID, org_id: uuid.UUID, schema_version: int
) -> None:
    """Prepare reviewed node dossiers after schema persistence, never in its transaction."""

    from src.knowledge_pack.configured_generator import ConfiguredKnowledgePackGenerator
    from src.knowledge_pack.runner import (
        KnowledgePackRunnerDependencies,
        run_packs_for_schema,
    )

    llm = await _make_llm(org_id)
    await run_packs_for_schema(
        course_id,
        org_id,
        schema_version,
        dependencies=KnowledgePackRunnerDependencies(
            generator=ConfiguredKnowledgePackGenerator(llm)
        ),
    )


def _spawn_knowledge_pack_shadow(
    course_id: uuid.UUID, org_id: uuid.UUID, schema_version: int
) -> None:
    """Fail-open handoff: pack generation can never invalidate a usable index."""

    coroutine = _run_knowledge_pack_shadow(course_id, org_id, schema_version)
    try:
        task_registry.spawn(
            coroutine, name=f"knowledge-pack:{course_id}:v{schema_version}"
        )
    except Exception:  # noqa: BLE001 - the schema remains the authoritative result.
        coroutine.close()
        logger.warning(
            "Could not schedule knowledge-pack shadow run course=%s schema=%s",
            course_id,
            schema_version,
            exc_info=True,
        )


async def _set_job(job_id: str, **fields: Any) -> None:
    async with async_session_factory() as db:
        repo = GenerationJobRepository(db)
        job = await repo.get_by_id(uuid.UUID(job_id))
        if job is not None:
            await repo.update(job, **fields)
        await db.commit()


async def _publish_step(job_id: str, step: str, message: str) -> None:
    await sse.publish(
        sse_channel(job_id), "schema_step", {"step": step, "message": message}
    )


def _uuids(values: list[str] | None) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for value in values or []:
        try:
            out.append(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError):
            continue
    return out


def distinct_headings(metadatas: list[dict | None]) -> list[str]:
    """Distinct, order-preserving ``chunk_metadata['heading']`` values.

    The chunker stores one heading string per chunk
    (``src/services/chunker.py``), so the document's real section names are
    recoverable without re-parsing the file. This is the closed list the designer
    prompt is allowed to choose from.
    """
    seen: set[str] = set()
    headings: list[str] = []
    for metadata in metadatas:
        if not isinstance(metadata, dict):
            continue
        raw = metadata.get("heading")
        if not isinstance(raw, str):
            continue
        heading = raw.strip()
        if not heading or heading in seen:
            continue
        seen.add(heading)
        headings.append(heading)
    return headings


def select_headings(
    proposed: list[Any], available: list[str], *, node_title: str
) -> tuple[list[str], list[str]]:
    """Keep only headings that exist verbatim in ``available``.

    An invented heading matches no chunk, so ``load_context`` would hand the
    runtime an empty source and the learner would get plausible content with no
    documentary basis — a silent failure. Dropping it loudly is strictly better.
    """
    if not available:
        return [], []
    allowed = {heading: heading for heading in available}
    # Case/whitespace-insensitive second chance: a model that lowercases a heading
    # meant the right section, and rejecting it would lose real grounding.
    folded = {heading.strip().casefold(): heading for heading in available}

    kept: list[str] = []
    warnings: list[str] = []
    for raw in proposed or []:
        if not isinstance(raw, str):
            continue
        candidate = raw.strip()
        if candidate in allowed:
            match = allowed[candidate]
        else:
            match = folded.get(candidate.casefold())
        if match is None:
            warnings.append(
                f"Se descarto el heading inventado '{candidate}' en '{node_title}'."
            )
            continue
        if match not in kept:
            kept.append(match)
    return kept, warnings


def _nodes_from_response(parsed: Any) -> list[dict]:
    """Accept ``{"nodes": [...]}`` or a bare list, like ``themes_list`` does."""
    if isinstance(parsed, dict):
        raw = parsed.get("nodes") or parsed.get("schema") or []
    elif isinstance(parsed, list):
        raw = parsed
    else:
        raw = []
    return [item for item in raw if isinstance(item, dict)]


# --------------------------------------------------------------------------- #
# Node 1: load_source
# --------------------------------------------------------------------------- #
@schema_node_error_wrapper("load_source")
async def load_source(state: SchemaState) -> dict:
    job_id = str(state["job_id"])
    doc_ids = _uuids(state.get("source_document_ids"))

    async with async_session_factory() as db:
        documents = list(
            (
                await db.execute(select(Document).where(Document.id.in_(doc_ids)))
            )
            .scalars()
            .all()
        )
        metadatas = (
            list(
                (
                    await db.execute(
                        select(DocumentChunk.chunk_metadata)
                        .where(DocumentChunk.document_id.in_(doc_ids))
                        .order_by(
                            DocumentChunk.document_id, DocumentChunk.chunk_index
                        )
                    )
                )
                .scalars()
                .all()
            )
            if doc_ids
            else []
        )

    total_pages = sum(estimate_pages(doc) for doc in documents)
    single = len(documents) == 1
    rag_mode = (
        "full_text" if single and total_pages <= FULL_TEXT_PAGE_THRESHOLD else "chunked"
    )

    await _set_job(job_id, status=GenerationStep.SCHEMA_PROPOSING)
    await _publish_step(job_id, "loading_source", "Leyendo el material de origen...")

    return {
        "rag_mode": rag_mode,
        "full_texts": {str(doc.id): (doc.full_text or "") for doc in documents},
        "source_metadata": {
            "total_pages": total_pages,
            "doc_count": len(documents),
            "doc_titles": [doc.title for doc in documents],
        },
        "available_headings": distinct_headings(metadatas),
        "current_step": "loading_source",
    }


# --------------------------------------------------------------------------- #
# Node 2: extract_themes_schema
# --------------------------------------------------------------------------- #
async def _source_context(state: SchemaState) -> str:
    context = "\n\n".join((state.get("full_texts") or {}).values())
    if context.strip():
        return context
    doc_ids = _uuids(state.get("source_document_ids"))
    async with async_session_factory() as db:
        repo = DocumentChunkRepository(db)
        chunks = list(await repo.list_for_documents_ordered(doc_ids))
    return assemble_chunk_text(chunks) if chunks else ""


@schema_node_error_wrapper("extract_themes_schema")
async def extract_themes_schema(state: SchemaState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])

    context = await _source_context(state)

    if not context.strip():
        # "From topic" course: no source document.  Synthesise themes from the
        # course title and description so the designer has something to work with.
        course_id = state.get("course_id")
        if course_id:
            async with async_session_factory() as db:
                course = await db.get(Course, uuid.UUID(str(course_id)))
                if course is not None:
                    parts = [course.title or ""]
                    if course.description:
                        parts.append(course.description)
                    if course.outcome:
                        parts.append(course.outcome)
                    context = "\n\n".join(p for p in parts if p.strip())

    if context.strip():
        llm = await _make_llm(org_id)
        response = await llm.complete(
            THEME_EXTRACTOR_SYSTEM,
            build_extraction_prompt(context),
            temperature=EXTRACT_TEMPERATURE,
            max_tokens=EXTRACT_MAX_TOKENS,
            json_mode=True,
        )
        themes = themes_list(parse_json_response(response))
    else:
        themes = []

    await _publish_step(job_id, "extracting_themes", "Identificando los temas clave...")
    return {"extracted_themes": themes, "current_step": "extracting_themes"}


# --------------------------------------------------------------------------- #
# Node 3: design_schema (one LLM call)
# --------------------------------------------------------------------------- #
@schema_node_error_wrapper("design_schema")
async def design_schema(state: SchemaState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])
    llm = await _make_llm(org_id)

    course_title: str | None = None
    course_outcome: str | None = None
    course_id = state.get("course_id")
    if course_id:
        async with async_session_factory() as db:
            course = await db.get(Course, uuid.UUID(str(course_id)))
            if course is not None:
                course_title = course.title
                course_outcome = course.outcome

    prompt = build_schema_prompt(
        state.get("extracted_themes") or [],
        state.get("source_metadata") or {},
        state.get("available_headings") or [],
        intent_density=int(state.get("intent_density") or 3),
        course_title=course_title,
        course_outcome=course_outcome,
    )
    response = await llm.complete(
        SCHEMA_DESIGNER_SYSTEM,
        prompt,
        temperature=SCHEMA_TEMPERATURE,
        max_tokens=SCHEMA_MAX_TOKENS,
        json_mode=True,
    )
    proposed = _nodes_from_response(parse_json_response(response))

    warnings: list[str] = []
    if len(proposed) > MAX_PROPOSED_NODES:
        warnings.append(
            f"La propuesta traia {len(proposed)} nodos; se conservaron los primeros "
            f"{MAX_PROPOSED_NODES}."
        )
        proposed = proposed[:MAX_PROPOSED_NODES]

    await _publish_step(
        job_id, "designing_schema", "Disenando el grafo de nodos del curso..."
    )
    return {
        "proposed_nodes": proposed,
        "schema_warnings": list(state.get("schema_warnings") or []) + warnings,
        "current_step": "designing_schema",
    }


# --------------------------------------------------------------------------- #
# Node 4: persist_schema
# --------------------------------------------------------------------------- #
@schema_node_error_wrapper("persist_schema")
async def persist_schema(state: SchemaState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])
    course_id = uuid.UUID(str(state["course_id"]))
    doc_ids = _uuids(state.get("source_document_ids"))
    available = list(state.get("available_headings") or [])
    warnings = list(state.get("schema_warnings") or [])

    # Nodos a conservar y poda de relleno, en un solo paso que REMAPEA los
    # prerequisitos (indices base-0). Dos motivos para dropear:
    #   a) sin titulo o sin summary: el summary es obligatorio para validar.
    #   b) RELLENO: en un curso con documento rico en headings, un nodo que el propio
    #      modelo devuelve SIN source_headings es andamiaje generico inventado (medido:
    #      gpt-4o-mini cuela "Fundamentos de atencion al cliente" pese al prompt). No es
    #      rastreable a la fuente, asi que se poda. En cursos por tema (sin doc) o docs
    #      con pocos headings NO se toca: ahi el vacio es esperado, no una senal.
    # Remapear es imprescindible: podar por el medio sin remapear descoloca las
    # dependencias de los nodos que sobreviven (los prerequisitos se resuelven por
    # indice mas abajo). Guarda: nunca se poda hasta dejar 0 nodos anclados.
    available_clean = [h for h in available if h and h.strip()]
    proposed_all = list(state.get("proposed_nodes") or [])
    with_text = [
        node
        for node in proposed_all
        if str(node.get("title") or "").strip() and str(node.get("summary") or "").strip()
    ]
    dropped_meta = len(proposed_all) - len(with_text)
    grounded = sum(1 for n in with_text if (n.get("source_headings") or []))
    prune_filler = len(available_clean) >= 3 and grounded >= 1

    kept: list[dict] = []
    old_to_new: dict[int, int] = {}
    dropped_filler = 0
    for old_index, node in enumerate(with_text):
        if prune_filler and not (node.get("source_headings") or []):
            dropped_filler += 1
            continue
        old_to_new[old_index] = len(kept)
        kept.append(node)

    raw_nodes: list[dict] = []
    for node in kept:
        remapped: list[int] = []
        for candidate in node.get("prerequisites") or []:
            try:
                prereq = int(candidate)
            except (TypeError, ValueError):
                continue
            if prereq in old_to_new:
                remapped.append(old_to_new[prereq])
        raw_nodes.append({**node, "prerequisites": remapped})

    if dropped_meta:
        warnings.append(
            f"Se descartaron {dropped_meta} nodo(s) sin titulo o sin summary: el summary "
            "es obligatorio para la validacion."
        )
    if dropped_filler:
        warnings.append(
            f"Se podaron {dropped_filler} nodo(s) de relleno sin anclar a la fuente "
            "(source_headings vacio en un documento con headings)."
        )

    # Cycles are pruned, never fatal: one bad arrow must not throw away a whole
    # usable proposal (§4.1).
    pruned, cycle_warnings = prune_cyclic_prerequisites(raw_nodes)
    warnings.extend(cycle_warnings)

    count = len(pruned)
    edges_by_index = {
        index: list(node.get("prerequisites") or []) for index, node in enumerate(pruned)
    }
    order = topological_order(list(range(count)), edges_by_index) or list(range(count))
    position_of = {index: rank + 1 for rank, index in enumerate(order)}

    async with async_session_factory() as db:
        node_repo = CourseNodeRepository(db)
        course = await db.get(Course, course_id)
        if course is None:
            raise ValueError(f"Course {course_id} disappeared before persisting")

        await node_repo.defer_position_constraint()

        # A re-proposal replaces the schema. Nodes somebody already worked on are
        # archived rather than deleted, so mastery and audit trail survive (§3.2).
        previous = list(await node_repo.list_for_course(course_id, include_archived=False))
        if previous:
            counts = await node_repo.attempt_counts([node.id for node in previous])
            for node in previous:
                if counts.get(node.id, 0) > 0:
                    node.archived = True
                    warnings.append(
                        f"'{node.title}' tenia progreso de aprendices: se archivo en "
                        "lugar de borrarse."
                    )
                else:
                    await node_repo.replace_prerequisites(node.id, [])
                    await db.delete(node)
            await db.flush()

        source_document_id = doc_ids[0] if doc_ids else course.source_document_id
        created: dict[int, CourseNode] = {}
        for index in order:
            node = pruned[index]
            criticality = coerce_criticality(node.get("criticality"))
            headings, heading_warnings = select_headings(
                node.get("source_headings") or [],
                available,
                node_title=str(node.get("title")),
            )
            warnings.extend(heading_warnings)
            row = CourseNode(
                org_id=org_id,
                course_id=course_id,
                title=str(node.get("title")).strip()[:300],
                summary=str(node.get("summary")).strip(),
                outcome=node.get("outcome"),
                criticality=criticality,
                position=position_of[index],
                source_document_id=source_document_id,
                source_headings=headings,
                mastery_threshold=default_threshold_for(criticality),
                default_ui_format=coerce_ui_format(node.get("default_ui_format")),
                estimated_minutes=_as_minutes(node.get("estimated_minutes")),
                # No reviewed_at: a proposal is never pre-approved (§11.1 rule 2).
                reviewed_at=None,
                reviewed_by=None,
            )
            db.add(row)
            created[index] = row
        await db.flush()

        for index, node in enumerate(pruned):
            for prereq_index in node.get("prerequisites") or []:
                if prereq_index in created and prereq_index != index:
                    db.add(
                        CourseNodePrerequisite(
                            node_id=created[index].id,
                            prerequisite_node_id=created[prereq_index].id,
                        )
                    )

        course.schema_status = CourseSchemaStatus.PROPOSED
        if state.get("intent_density"):
            course.intent_density = int(state["intent_density"])

        job_repo = GenerationJobRepository(db)
        job = await job_repo.get_by_id(uuid.UUID(job_id))
        if job is not None:
            await job_repo.update(
                job,
                status=GenerationStep.SCHEMA_PROPOSED,
                result_course_id=course_id,
                progress={
                    "node_count": count,
                    "schema_warnings": warnings,
                    # Kept so `validate` can record a real proposed -> validated
                    # diff without a new column (§3.5).
                    "proposed_nodes": [
                        {
                            "title": created[index].title,
                            "summary": created[index].summary,
                            "criticality": created[index].criticality.value,
                            "source_headings": list(created[index].source_headings or []),
                            "position": created[index].position,
                        }
                        for index in order
                    ],
                },
            )
        schema_version = int(course.schema_version or 1)
        await db.commit()

    # The schema is durable before any pack worker is allowed to read it. The worker
    # opens fresh sessions and failures are isolated from the schema_ready event below.
    _spawn_knowledge_pack_shadow(course_id, org_id, schema_version)

    await sse.publish(
        sse_channel(job_id),
        "schema_progress",
        {"step": "persisting", "completed": count, "total": count},
    )
    await sse.publish(
        sse_channel(job_id),
        "schema_ready",
        {
            "course_id": str(course_id),
            "node_count": count,
            "warnings": warnings,
            "message": "Esquema propuesto. Revisalo y validalo para activarlo.",
        },
    )
    return {
        "schema_warnings": warnings,
        "current_step": "schema_proposed",
    }


def _as_minutes(value: object) -> int | None:
    try:
        minutes = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return max(1, min(minutes, 240))


# --------------------------------------------------------------------------- #
# Node 5: handle_error (terminal)
# --------------------------------------------------------------------------- #
async def handle_error(state: SchemaState) -> dict:
    job_id = str(state.get("job_id", ""))
    error_message = state.get("error") or "Unknown error"
    if job_id:
        await _set_job(
            job_id,
            status=GenerationStep.FAILED,
            error_message=error_message[:2000],
        )
        await sse.publish(
            sse_channel(job_id),
            "error",
            {
                "step": state.get("current_step", "failed"),
                "message": error_message[:200],
            },
        )
    return {"current_step": "failed"}
