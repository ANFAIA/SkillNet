"""Graph nodes for the autonomous content generation pipeline.

One async function per node. Each is wrapped by ``node_error_wrapper`` so that a
raised exception becomes a clean terminal failure. Nodes open their own DB
sessions on demand and build LLM/embedding services from resolved org settings.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from sqlalchemy import select

from src.agents.content.errors import node_error_wrapper, sse_channel
from src.agents.content.state import GenerationState
from src.core import sse
from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.llm.client import LLMService, resolve_llm_config
from src.llm.embedding import EmbeddingService, resolve_embedding_config
from src.llm.parsing import parse_json_response
from src.llm.prompts import (
    CONTENT_REFINER_SYSTEM,
    MODULE_GENERATOR_SYSTEM,
    QUALITY_REVIEWER_SYSTEM,
    STRUCTURE_DESIGNER_SYSTEM,
    THEME_EXTRACTOR_SYSTEM,
    build_extraction_prompt,
    build_module_prompt,
    build_refine_prompt,
    build_review_prompt,
    build_structure_prompt,
)
from src.models import (
    Course,
    Document,
    DocumentChunk,
    Exercise,
    ExerciseType,
    GenerationStep,
    Lesson,
    Module,
    Organization,
)
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.repositories.generation_job_repo import GenerationJobRepository

logger = get_logger(__name__)

MAX_CONCURRENT_MODULES = 3
GEN_TEMPERATURE = 0.3
REVIEW_TEMPERATURE = 0.1
GEN_MAX_TOKENS = 4096
SEMANTIC_TOP_K = 3
FULL_TEXT_PAGE_THRESHOLD = 5
_CHARS_PER_PAGE = 2000


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _load_org_settings(db: Any, org_id: uuid.UUID) -> dict[str, Any]:
    """Return the organization's provider-override settings (or empty)."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
    return dict(org.settings) if org and org.settings else {}


async def _make_llm(org_id: uuid.UUID) -> LLMService:
    async with async_session_factory() as db:
        org_settings = await _load_org_settings(db, org_id)
    return LLMService(resolve_llm_config(org_settings, purpose="generation"))


async def _make_embeddings(org_id: uuid.UUID) -> EmbeddingService:
    async with async_session_factory() as db:
        org_settings = await _load_org_settings(db, org_id)
    return EmbeddingService(resolve_embedding_config(org_settings))


async def _set_job(job_id: str, **fields: Any) -> None:
    async with async_session_factory() as db:
        repo = GenerationJobRepository(db)
        job = await repo.get_by_id(uuid.UUID(job_id))
        if job is not None:
            await repo.update(job, **fields)
        await db.commit()


async def _publish_step(job_id: str, step: str, message: str) -> None:
    await sse.publish(sse_channel(job_id), "step", {"step": step, "message": message})


def _uuids(values: list[str] | None) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for value in values or []:
        try:
            out.append(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError):
            continue
    return out


def _estimate_pages(doc: Document) -> int:
    if doc.page_count:
        return doc.page_count
    return max(1, len(doc.full_text or "") // _CHARS_PER_PAGE)


def _chunk_overview(chunks: list[DocumentChunk]) -> str:
    lines = []
    for chunk in chunks:
        heading = (chunk.chunk_metadata or {}).get("heading", "")
        snippet = (chunk.content or "")[:200].replace("\n", " ")
        lines.append(f"[chunk_id={chunk.id}] {heading}: {snippet}")
    return "\n".join(lines)


def _assemble_chunk_text(chunks: list[DocumentChunk]) -> str:
    return "\n\n".join(chunk.content for chunk in chunks)


def _themes_list(parsed: Any) -> list[dict]:
    if isinstance(parsed, dict):
        return parsed.get("themes") or []
    if isinstance(parsed, list):
        return parsed
    return []


async def _load_chunks_by_ids(db: Any, ids: list[uuid.UUID]) -> list[DocumentChunk]:
    if not ids:
        return []
    query = (
        select(DocumentChunk)
        .where(DocumentChunk.id.in_(ids))
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
    )
    return list((await db.execute(query)).scalars().all())


# --------------------------------------------------------------------------- #
# Node 1: prepare_context
# --------------------------------------------------------------------------- #
@node_error_wrapper("prepare_context")
async def prepare_context(state: GenerationState) -> dict:
    job_id = str(state["job_id"])
    doc_ids = _uuids(state.get("source_document_ids"))

    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.id.in_(doc_ids)))
        documents = list(result.scalars().all())

    total_pages = sum(_estimate_pages(doc) for doc in documents)
    single = len(documents) == 1

    if single and total_pages <= FULL_TEXT_PAGE_THRESHOLD:
        rag_mode = "full_text"
        full_texts: dict[str, str] | None = {
            str(doc.id): (doc.full_text or "") for doc in documents
        }
    else:
        rag_mode = "chunked"
        full_texts = None

    source_metadata = {
        "total_pages": total_pages,
        "doc_count": len(documents),
        "doc_titles": [doc.title for doc in documents],
    }

    await _set_job(job_id, status=GenerationStep.EXTRACTING)
    await _publish_step(job_id, "extracting", "Analizando el material de origen...")

    return {
        "rag_mode": rag_mode,
        "full_texts": full_texts,
        "source_metadata": source_metadata,
        "current_step": "extracting",
    }


# --------------------------------------------------------------------------- #
# Node 2: extract_themes
# --------------------------------------------------------------------------- #
@node_error_wrapper("extract_themes")
async def extract_themes(state: GenerationState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])
    llm = await _make_llm(org_id)

    if state.get("rag_mode") == "full_text":
        context = "\n\n".join((state.get("full_texts") or {}).values())
        prompt = build_extraction_prompt(context, include_chunk_ids=False)
    else:
        doc_ids = _uuids(state.get("source_document_ids"))
        async with async_session_factory() as db:
            repo = DocumentChunkRepository(db)
            chunks = list(await repo.list_for_documents_ordered(doc_ids))
        context = _chunk_overview(chunks)
        prompt = build_extraction_prompt(context, include_chunk_ids=True)

    response = await llm.complete(
        THEME_EXTRACTOR_SYSTEM,
        prompt,
        temperature=GEN_TEMPERATURE,
        max_tokens=GEN_MAX_TOKENS,
        json_mode=True,
    )
    themes = _themes_list(parse_json_response(response))

    await _set_job(job_id, status=GenerationStep.STRUCTURING)
    await _publish_step(job_id, "structuring", "Disenando la estructura del curso...")

    return {"extracted_themes": themes, "current_step": "structuring"}


# --------------------------------------------------------------------------- #
# Node 3: design_structure
# --------------------------------------------------------------------------- #
@node_error_wrapper("design_structure")
async def design_structure(state: GenerationState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])
    llm = await _make_llm(org_id)

    prompt = build_structure_prompt(
        state.get("extracted_themes", []), state.get("source_metadata", {})
    )
    response = await llm.complete(
        STRUCTURE_DESIGNER_SYSTEM,
        prompt,
        temperature=GEN_TEMPERATURE,
        max_tokens=GEN_MAX_TOKENS,
        json_mode=True,
    )
    outline = parse_json_response(response)
    if not isinstance(outline, dict):
        outline = {"title": "Curso", "modules": []}

    await _set_job(job_id, status=GenerationStep.STRUCTURING)
    return {"course_outline": outline, "current_step": "structuring"}


# --------------------------------------------------------------------------- #
# Node 4: generate_modules (parallel fan-out)
# --------------------------------------------------------------------------- #
async def _module_context(
    state: GenerationState, spec: dict, embeddings: EmbeddingService | None
) -> str:
    if state.get("rag_mode") == "full_text":
        return "\n\n".join((state.get("full_texts") or {}).values())

    org_id = uuid.UUID(state["org_id"])
    doc_ids = _uuids(state.get("source_document_ids"))
    items: dict[uuid.UUID, dict] = {}

    async with async_session_factory() as db:
        primary = await _load_chunks_by_ids(db, _uuids(spec.get("chunk_ids")))
        for chunk in primary:
            items[chunk.id] = {
                "doc": str(chunk.document_id),
                "idx": chunk.chunk_index,
                "content": chunk.content,
            }

        query_text = f"{spec.get('title', '')} {spec.get('summary', '')}".strip()
        if embeddings is not None and query_text:
            try:
                vector = await embeddings.embed_query(query_text)
                repo = DocumentChunkRepository(db)
                hits = await repo.similarity_search(
                    org_id=org_id,
                    query_embedding=vector,
                    top_k=SEMANTIC_TOP_K,
                    document_ids=doc_ids,
                )
                for hit in hits:
                    if hit["chunk_id"] not in items:
                        items[hit["chunk_id"]] = {
                            "doc": str(hit["document_id"]),
                            "idx": 10**9,
                            "content": hit["content"],
                        }
            except LLMError:
                logger.warning("Semantic supplement skipped (embedding unavailable)")

    ordered = sorted(items.values(), key=lambda it: (it["doc"], it["idx"]))
    return "\n\n".join(it["content"] for it in ordered)


@node_error_wrapper("generate_modules")
async def generate_modules(state: GenerationState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])
    outline = state.get("course_outline") or {}
    modules: list[dict] = outline.get("modules") or []
    total = len(modules)

    llm = await _make_llm(org_id)
    embeddings = (
        await _make_embeddings(org_id)
        if state.get("rag_mode") == "chunked"
        else None
    )

    await _set_job(job_id, status=GenerationStep.GENERATING)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_MODULES)
    completed = 0

    async def generate_one(index: int, spec: dict) -> tuple[int, dict]:
        nonlocal completed
        async with semaphore:
            await sse.publish(
                sse_channel(job_id),
                "progress",
                {
                    "step": "generating",
                    "completed": completed,
                    "total": total,
                    "current": spec.get("title", ""),
                },
            )
            context = await _module_context(state, spec, embeddings)
            response = await llm.complete(
                MODULE_GENERATOR_SYSTEM,
                build_module_prompt(spec, context),
                temperature=GEN_TEMPERATURE,
                max_tokens=GEN_MAX_TOKENS,
                json_mode=True,
            )
            data = parse_json_response(response)
            module = {
                "module_spec": spec,
                "lessons": (data or {}).get("lessons", []),
                "exercises": (data or {}).get("exercises", []),
            }
            completed += 1
            await sse.publish(
                sse_channel(job_id),
                "progress",
                {
                    "step": "generating",
                    "completed": completed,
                    "total": total,
                    "current": spec.get("title", ""),
                },
            )
            return spec.get("position", index + 1), module

    results = await asyncio.gather(
        *(generate_one(i, spec) for i, spec in enumerate(modules))
    )
    ordered = [module for _, module in sorted(results, key=lambda pair: pair[0])]

    return {"generated_modules": ordered, "current_step": "generating"}


# --------------------------------------------------------------------------- #
# Node 5: review_quality (independent — reloads source from DB)
# --------------------------------------------------------------------------- #
async def _load_source_context(state: GenerationState) -> str:
    doc_ids = _uuids(state.get("source_document_ids"))
    async with async_session_factory() as db:
        if state.get("rag_mode") == "full_text":
            result = await db.execute(
                select(Document).where(Document.id.in_(doc_ids))
            )
            return "\n\n".join((doc.full_text or "") for doc in result.scalars().all())
        repo = DocumentChunkRepository(db)
        chunks = list(await repo.list_for_documents_ordered(doc_ids))
        return _assemble_chunk_text(chunks)


@node_error_wrapper("review_quality")
async def review_quality(state: GenerationState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])
    llm = await _make_llm(org_id)

    source = await _load_source_context(state)
    generated = json.dumps(
        state.get("generated_modules", []), ensure_ascii=False, default=str
    )
    response = await llm.complete(
        QUALITY_REVIEWER_SYSTEM,
        build_review_prompt(source, generated),
        temperature=REVIEW_TEMPERATURE,
        max_tokens=GEN_MAX_TOKENS,
        json_mode=True,
    )
    report = parse_json_response(response)
    if not isinstance(report, dict):
        report = {"passed": False, "overall_score": 0.0, "issues": []}

    await _set_job(job_id, status=GenerationStep.REVIEWING)
    await sse.publish(
        sse_channel(job_id),
        "review_result",
        {
            "passed": bool(report.get("passed")),
            "score": report.get("overall_score", 0.0),
            "issues_count": len(report.get("issues") or []),
        },
    )
    return {"review_report": report, "current_step": "reviewing"}


# --------------------------------------------------------------------------- #
# Node 6: refine_content
# --------------------------------------------------------------------------- #
@node_error_wrapper("refine_content")
async def refine_content(state: GenerationState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])
    llm = await _make_llm(org_id)

    report = state.get("review_report") or {}
    modules = list(state.get("generated_modules", []))
    source = await _load_source_context(state)

    issues_by_module: dict[int, list[dict]] = {}
    for issue in report.get("issues") or []:
        index = issue.get("module_index")
        if isinstance(index, int) and 0 <= index < len(modules):
            issues_by_module.setdefault(index, []).append(issue)

    for index, issues in issues_by_module.items():
        module = modules[index]
        response = await llm.complete(
            CONTENT_REFINER_SYSTEM,
            build_refine_prompt(
                json.dumps(issues, ensure_ascii=False),
                source,
                json.dumps(module, ensure_ascii=False, default=str),
            ),
            temperature=GEN_TEMPERATURE,
            max_tokens=GEN_MAX_TOKENS,
            json_mode=True,
        )
        data = parse_json_response(response)
        if isinstance(data, dict):
            modules[index] = {
                "module_spec": module.get("module_spec", {}),
                "lessons": data.get("lessons", module.get("lessons", [])),
                "exercises": data.get("exercises", module.get("exercises", [])),
            }

    await _set_job(job_id, status=GenerationStep.REVIEWING)
    await sse.publish(
        sse_channel(job_id),
        "refining",
        {"cycle": state.get("refinement_count", 0) + 1, "max_cycles": 2},
    )
    return {
        "generated_modules": modules,
        "refinement_count": state.get("refinement_count", 0) + 1,
        "current_step": "reviewing",
    }


# --------------------------------------------------------------------------- #
# Node 7: publish
# --------------------------------------------------------------------------- #
@node_error_wrapper("publish")
async def publish(state: GenerationState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])
    triggered_by = uuid.UUID(state["triggered_by"])
    outline = state.get("course_outline") or {}
    doc_ids = _uuids(state.get("source_document_ids"))

    async with async_session_factory() as db:
        course_id = state.get("course_id")
        if course_id:
            course = await db.get(Course, uuid.UUID(str(course_id)))
        else:
            course = None

        if course is None:
            course = Course(
                org_id=org_id,
                created_by=triggered_by,
                source_document_id=doc_ids[0] if doc_ids else None,
                title=outline.get("title", "Curso"),
                description=outline.get("description"),
                outcome=outline.get("outcome"),
                status="draft",
            )
            db.add(course)
            await db.flush()
        else:
            course.title = outline.get("title", course.title)
            course.description = outline.get("description")
            course.outcome = outline.get("outcome")
            course.status = "draft"
            await db.flush()

        for mod_position, gen_module in enumerate(
            state.get("generated_modules", []), start=1
        ):
            spec = gen_module.get("module_spec", {})
            module = Module(
                course_id=course.id,
                title=spec.get("title", "Modulo"),
                summary=spec.get("summary"),
                position=spec.get("position", mod_position),
            )
            db.add(module)
            await db.flush()

            last_lesson: Lesson | None = None
            gen_lessons = gen_module.get("lessons", [])
            for position, gen_lesson in enumerate(gen_lessons, start=1):
                lesson = Lesson(
                    module_id=module.id,
                    title=gen_lesson.get("title", "Leccion"),
                    content=gen_lesson.get("content", ""),
                    position=gen_lesson.get("position", position),
                )
                db.add(lesson)
                await db.flush()
                last_lesson = lesson

            if last_lesson is None:
                # A module must own at least one lesson to host its exercises.
                last_lesson = Lesson(
                    module_id=module.id, title=spec.get("title", "Leccion"),
                    content="", position=1,
                )
                db.add(last_lesson)
                await db.flush()

            for position, gen_exercise in enumerate(gen_module.get("exercises", [])):
                try:
                    etype = ExerciseType(gen_exercise.get("type"))
                except ValueError:
                    continue
                db.add(
                    Exercise(
                        lesson_id=last_lesson.id,
                        type=etype,
                        content=gen_exercise.get("content", {}),
                        position=gen_exercise.get("position", position),
                    )
                )

        repo = GenerationJobRepository(db)
        job = await repo.get_by_id(uuid.UUID(job_id))
        if job is not None:
            await repo.update(
                job, status=GenerationStep.PUBLISHED, result_course_id=course.id
            )
        result_course_id = str(course.id)
        await db.commit()

    await sse.publish(
        sse_channel(job_id),
        "completed",
        {"course_id": result_course_id, "message": "Curso generado correctamente"},
    )
    return {"result_course_id": result_course_id, "current_step": "published"}


# --------------------------------------------------------------------------- #
# Node 8: handle_error (terminal)
# --------------------------------------------------------------------------- #
async def handle_error(state: GenerationState) -> dict:
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
            {"step": state.get("current_step", "failed"), "message": error_message[:200]},
        )
    return {"current_step": "failed"}
