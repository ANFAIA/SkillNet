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
from src.agents.content.helpers import (
    FULL_TEXT_PAGE_THRESHOLD,
    assemble_chunk_text as _assemble_chunk_text,
    describe_payload as _describe_payload,
    estimate_pages as _estimate_pages,
    module_payload as _module_payload,
    outline_dict as _outline_dict,
    review_report as _review_report,
    strip_chunk_prefix as _strip_chunk_prefix,
    themes_list as _themes_list,
)
from src.agents.content.state import GenerationState
from src.core import sse
from src.core.exceptions import LLMError
from src.core.language import Language, normalize_language
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.llm.client import LLMService, resolve_llm_config
from src.llm.embedding import EmbeddingService, resolve_embedding_config
from src.llm.fixtures import maybe_fixture_embedder, maybe_fixture_llm
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
from src.llm.prompts.language import with_language
from src.models import (
    Course,
    CourseSkill,
    Document,
    Exercise,
    ExerciseType,
    GenerationStep,
    Lesson,
    Module,
    Organization,
    Skill,
)
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.repositories.generation_job_repo import GenerationJobRepository
from src.repositories.skill_repo import SkillRepository
from src.services.language_policy import language_for_course

logger = get_logger(__name__)

MAX_CONCURRENT_MODULES = 3
GEN_TEMPERATURE = 0.3
REVIEW_TEMPERATURE = 0.1
GEN_MAX_TOKENS = 4096
SEMANTIC_TOP_K = 15


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
    return maybe_fixture_llm(resolve_llm_config(org_settings, purpose="generation"))


async def _make_embeddings(org_id: uuid.UUID) -> EmbeddingService:
    async with async_session_factory() as db:
        org_settings = await _load_org_settings(db, org_id)
    return maybe_fixture_embedder(resolve_embedding_config(org_settings))


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


def _language(state: GenerationState) -> Language | None:
    """The run's output language, re-normalized because state crosses a checkpointer.

    LangGraph persists the state, so what comes back is whatever JSON was written —
    ``normalize_language`` turns a resumed ``"EN"`` or ``"en-GB"`` back into ``"en"``
    and anything unusable into ``None``, which is the value that leaves the prompts
    untouched.
    """
    return normalize_language(state.get("language"))


async def _course_language(course_id: Any) -> Language | None:
    """The language the course row asks for, if there is a course row yet.

    v1 generation creates the course in ``publish``, so on a first run there is
    nothing to read and the answer is ``None`` — the same answer as a Spanish course,
    and the same prompts as before this existed.
    """
    if not course_id:
        return None
    async with async_session_factory() as db:
        course = await db.get(Course, uuid.UUID(str(course_id)))
    return None if course is None else language_for_course(course)


# ``estimate_pages``, ``strip_chunk_prefix``, ``assemble_chunk_text`` and
# ``themes_list`` now live in ``src/agents/content/helpers.py`` (shared with the v2
# schema graph) and are imported above under their original private names.


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

    full_texts: dict[str, str] = {
        str(doc.id): (doc.full_text or "") for doc in documents
    }

    if single and total_pages <= FULL_TEXT_PAGE_THRESHOLD:
        rag_mode = "full_text"
    else:
        rag_mode = "chunked"

    source_metadata = {
        "total_pages": total_pages,
        "doc_count": len(documents),
        "doc_titles": [doc.title for doc in documents],
    }

    await _set_job(job_id, status=GenerationStep.EXTRACTING)
    await _publish_step(job_id, "extracting", "Analizando el material de origen...")

    # Resolved here, once, so the four model-facing nodes downstream read one value
    # instead of each deciding for itself and drifting apart mid-course.
    language = _language(state) or await _course_language(state.get("course_id"))

    return {
        "rag_mode": rag_mode,
        "full_texts": full_texts,
        "source_metadata": source_metadata,
        "language": language,
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

    context = "\n\n".join((state.get("full_texts") or {}).values())
    if not context.strip():
        doc_ids = _uuids(state.get("source_document_ids"))
        async with async_session_factory() as db:
            repo = DocumentChunkRepository(db)
            chunks = list(await repo.list_for_documents_ordered(doc_ids))
        context = _assemble_chunk_text(chunks) if chunks else ""
    prompt = build_extraction_prompt(context)

    response = await llm.complete(
        with_language(THEME_EXTRACTOR_SYSTEM, _language(state)),
        prompt,
        temperature=GEN_TEMPERATURE,
        max_tokens=GEN_MAX_TOKENS,
        json_mode=True,
    )
    parsed = parse_json_response(response, context="extract_themes")
    themes = _themes_list(parsed)
    if not themes:
        # Not fatal — the designer can still build an outline from the source metadata —
        # but it costs the course every skill it would have been linked to, so it must not
        # pass in silence.
        logger.warning(
            "Theme extraction produced no usable themes for job %s; received %s",
            job_id,
            _describe_payload(parsed),
        )

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
        with_language(STRUCTURE_DESIGNER_SYSTEM, _language(state)),
        prompt,
        temperature=GEN_TEMPERATURE,
        max_tokens=GEN_MAX_TOKENS,
        json_mode=True,
    )
    outline = _outline_dict(parse_json_response(response, context="design_structure"))

    await _set_job(job_id, status=GenerationStep.STRUCTURING)
    return {"course_outline": outline, "current_step": "structuring"}


# --------------------------------------------------------------------------- #
# Node 4: generate_modules (parallel fan-out)
# --------------------------------------------------------------------------- #
async def _module_context(
    state: GenerationState, spec: dict, embeddings: EmbeddingService | None
) -> str:
    context = "\n\n".join((state.get("full_texts") or {}).values())
    if context.strip():
        return context

    org_id = uuid.UUID(state["org_id"])
    doc_ids = _uuids(state.get("source_document_ids"))
    items: dict[uuid.UUID, dict] = {}

    async with async_session_factory() as db:
        repo = DocumentChunkRepository(db)
        all_chunks = list(await repo.list_for_documents_ordered(doc_ids))
        for chunk in all_chunks:
            items[chunk.id] = {
                "doc": str(chunk.document_id),
                "idx": chunk.chunk_index,
                "content": chunk.content,
            }

        query_text = f"{spec.get('title', '')} {spec.get('summary', '')}".strip()
        if embeddings is not None and query_text:
            try:
                vector = await embeddings.embed_query(query_text)
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
    return "\n\n".join(_strip_chunk_prefix(it["content"]) for it in ordered)


@node_error_wrapper("generate_modules")
async def generate_modules(state: GenerationState) -> dict:
    job_id = str(state["job_id"])
    org_id = uuid.UUID(state["org_id"])
    outline = state.get("course_outline") or {}
    modules: list[dict] = outline.get("modules") or []
    total = len(modules)

    llm = await _make_llm(org_id)
    language = _language(state)
    has_full_text = any(
        v.strip() for v in (state.get("full_texts") or {}).values()
    )
    embeddings = (
        await _make_embeddings(org_id)
        if not has_full_text
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
                with_language(MODULE_GENERATOR_SYSTEM, language),
                build_module_prompt(spec, context),
                temperature=GEN_TEMPERATURE,
                max_tokens=GEN_MAX_TOKENS,
                json_mode=True,
            )
            payload = _module_payload(
                parse_json_response(response, context="generate_modules")
            )
            module = {
                "module_spec": spec,
                "lessons": payload["lessons"],
                "exercises": payload["exercises"],
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
    full_texts = state.get("full_texts") or {}
    context = "\n\n".join(full_texts.values())
    if context.strip():
        return context
    doc_ids = _uuids(state.get("source_document_ids"))
    async with async_session_factory() as db:
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
    # The reviewer is a quality *gate*, not a producer, and by the time it runs the
    # modules and lessons already exist — four LLM calls of them. Letting a provider
    # failure here reach `node_error_wrapper` sends the graph to `handle_error` and
    # discards all of it, which is how a course generation died on Groq's free tier on
    # 2026-07-27: a 6000 tokens-per-minute limit, and a review call that asks for most of
    # a minute's worth in one go.
    #
    # So a reviewer that cannot run is recorded as *not having run*, and the course goes
    # out unreviewed. It lands as a **draft** either way — an admin still has to press
    # Publish — so the human gate the reviewer feeds into is still there. What must not
    # happen is silence: the report says so, and the SSE event says so.
    #
    # The parse is inside the same `try` for the same reason: a review whose answer
    # cannot be read is a review that did not happen, and it must cost the course no more
    # than a review that never returned. `parse_json_response` puts the raw response in
    # the log, so the unreadable answer is still diagnosable.
    try:
        response = await llm.complete(
            with_language(QUALITY_REVIEWER_SYSTEM, _language(state)),
            build_review_prompt(source, generated),
            temperature=REVIEW_TEMPERATURE,
            max_tokens=GEN_MAX_TOKENS,
            json_mode=True,
        )
        report = _review_report(parse_json_response(response, context="review_quality"))
    except LLMError as exc:
        logger.warning(
            "Quality review could not run for job %s (%s); publishing unreviewed",
            job_id,
            exc,
        )
        report = {
            "passed": False,
            "review_skipped": True,
            "overall_score": 0.0,
            "issues": [],
            "skip_reason": str(exc)[:200],
        }

    await _set_job(job_id, status=GenerationStep.REVIEWING)
    await sse.publish(
        sse_channel(job_id),
        "review_result",
        {
            "passed": bool(report.get("passed")),
            "score": report.get("overall_score", 0.0),
            "issues_count": len(report.get("issues") or []),
            "skipped": bool(report.get("review_skipped")),
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
            with_language(CONTENT_REFINER_SYSTEM, _language(state)),
            build_refine_prompt(
                json.dumps(issues, ensure_ascii=False),
                source,
                json.dumps(module, ensure_ascii=False, default=str),
            ),
            temperature=GEN_TEMPERATURE,
            max_tokens=GEN_MAX_TOKENS,
            json_mode=True,
        )
        # Refinement is best-effort: the module it is editing already exists and is
        # publishable, so an answer that cannot be read keeps the module as it was — but
        # says so, instead of the old silent `if isinstance(data, dict)`, which threw a
        # perfectly good refinement away for arriving without its wrapper.
        #
        # `or` and not `.get(key, default)` below: an empty array is the model saying
        # nothing rather than "delete everything", and a refiner asked to fix two
        # sentences has no business emptying a module.
        try:
            payload = _module_payload(
                parse_json_response(response, context="refine_content")
            )
        except LLMError as exc:
            logger.warning(
                "Refinement of module %d skipped for job %s; keeping the reviewed "
                "version (%s)",
                index,
                job_id,
                exc,
            )
            continue
        modules[index] = {
            "module_spec": module.get("module_spec", {}),
            "lessons": payload["lessons"] or module.get("lessons", []),
            "exercises": payload["exercises"] or module.get("exercises", []),
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
# Helper: auto-create skills from extracted themes
# --------------------------------------------------------------------------- #
async def _auto_create_skills(
    db: Any, org_id: uuid.UUID, state: GenerationState
) -> list[uuid.UUID]:
    """Create Skill records from extracted themes and return their IDs.

    Maps each theme's name to a skill. Themes are the concepts the LLM
    identified in the source document — they naturally correspond to the
    skills the generated course will teach.
    """
    themes = state.get("extracted_themes") or []
    if not themes:
        return []

    repo = SkillRepository(db)
    skill_ids: list[uuid.UUID] = []

    for theme in themes:
        name = theme.get("name") or theme.get("title") or ""
        name = name.strip().lower().replace(" ", "_")[:100]
        if not name:
            continue

        existing = await repo.get_by_name(org_id, name)
        if existing is not None:
            skill_ids.append(existing.id)
            continue

        description = theme.get("description") or theme.get("summary") or ""
        skill = Skill(org_id=org_id, name=name, description=description[:500])
        db.add(skill)
        await db.flush()
        skill_ids.append(skill.id)

    logger.info("Auto-created skills from %d themes for org %s", len(themes), org_id)
    return skill_ids


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

        # Auto-create skills from themes and link them to the course.
        skill_ids = await _auto_create_skills(db, org_id, state)
        for skill_id in skill_ids:
            db.add(CourseSkill(course_id=course.id, skill_id=skill_id))
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
                    title=gen_lesson.get("title", "Lección"),
                    content=gen_lesson.get("content", ""),
                    position=gen_lesson.get("position", position),
                )
                db.add(lesson)
                await db.flush()
                last_lesson = lesson

            if last_lesson is None:
                # A module must own at least one lesson to host its exercises.
                last_lesson = Lesson(
                    module_id=module.id, title=spec.get("title", "Lección"),
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
