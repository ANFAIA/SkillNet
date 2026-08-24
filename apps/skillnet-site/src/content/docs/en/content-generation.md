---
title: "Content generation"
order: 5
section: "core"
---

# Content Generation Pipeline

> **Status: v1.** Complete architecture for the multi-agent content generation pipeline. Transforms uploaded documents into structured courses and reference manuals via LangGraph orchestration with human-in-the-loop checkpoints.

Depends on: [architecture.md](architecture.md), [data-model.md](data-model.md), [rag-retrieval.md](rag-retrieval.md), [backend-api.md](backend-api.md).

---

## 1. Overview

The content generation pipeline takes one or more ingested documents and produces a complete course (modules, lessons, exercises) and an accompanying reference manual. The pipeline is a LangGraph state machine with 10 nodes, 7 specialized agents, 2 mandatory human-in-the-loop checkpoints, and PostgreSQL-backed checkpointing for durability.

```
Admin uploads document(s)
     |
     v
POST /api/v1/courses/{id}/generate
     |
     v
generation_jobs row created (status: pending)
     |
     v
LangGraph graph invoked (async)
     |
     v
  [prepare_context] --> [extract_themes] --> [design_structure]
                                                    |
                                            ADMIN CHECKPOINT 1
                                        (review/edit structure)
                                                    |
                                                    v
                        [generate_modules] (parallel fan-out)
                                    |
                              [generate_manual]
                                    |
                              [review_quality]
                                    |
                           pass? ---+--- fail?
                            |              |
                            v              v
                    ADMIN CHECKPOINT 2  [refine_content]
                    (final review)      (max 2 cycles)
                            |
                            v
                        [publish]
                            |
                            v
                    Course + Manual in DB
                    (status: published)
```

**Design principles:**

- **Human stays in control.** The admin reviews and can edit the structure before any content is generated, and reviews the final output before publication. Nothing reaches learners without explicit approval.
- **Fail-safe, not fail-fast.** Every node catches its own errors, updates the generation job status, and sends an SSE event. The admin sees what failed and can retry.
- **Compartmented context.** Each agent sees only the data it needs. The quality reviewer loads source documents independently — it never sees the generator's context, enabling genuine independent verification.

---

## 2. LangGraph Graph Definition

### 2.1 GenerationState

The state flows through every node. Each node reads what it needs and writes its outputs. LangGraph handles persistence and resumption via PostgreSQL checkpointing.

```python
# src/agents/content/state.py

from typing import TypedDict, Literal
from uuid import UUID

class ModuleSpec(TypedDict):
    title: str
    summary: str
    position: int
    themes: list[str]                  # Theme keys this module covers
    bloom_level: str                   # Target Bloom level
    chunk_ids: list[UUID]              # Relevant chunk IDs from extraction
    lessons: list["LessonSpec"]

class LessonSpec(TypedDict):
    title: str
    position: int
    content_type: Literal["theory", "example", "exercise", "summary"]

class GeneratedModule(TypedDict):
    module_spec: ModuleSpec
    lessons: list["GeneratedLesson"]
    exercises: list[dict]              # Exercise content dicts (see data-model.md)

class GeneratedLesson(TypedDict):
    title: str
    position: int
    content: str                       # Markdown content
    citations: list[dict]              # [{document_title, section, page}]

class ReviewReport(TypedDict):
    passed: bool
    overall_score: float               # 0.0 - 1.0
    issues: list["ReviewIssue"]

class ReviewIssue(TypedDict):
    severity: Literal["critical", "major", "minor"]
    module_index: int | None           # None = course-level issue
    description: str
    suggestion: str

class AdminReview(TypedDict):
    decision: Literal["approve", "edit", "reject"]
    edits: dict | None                 # Inline edits if decision == "edit"
    notes: str | None

class GenerationState(TypedDict):
    # --- Identity ---
    job_id: UUID
    org_id: UUID
    triggered_by: UUID                 # Admin user ID

    # --- Inputs ---
    source_document_ids: list[UUID]    # One or more source documents
    output_type: Literal["course_and_manual", "manual_only"]
    course_id: UUID | None             # Pre-created course shell (if any)

    # --- RAG decisions ---
    rag_mode: Literal["full_text", "chunked"]
    full_texts: dict[UUID, str] | None         # doc_id -> full text (small docs)
    chunk_summary: dict[UUID, int] | None      # doc_id -> chunk count (large docs)

    # --- Extraction ---
    extracted_themes: list[dict]       # [{key, title, bloom_level, chunk_ids, summary}]
    source_metadata: dict              # {total_pages, doc_titles, languages}

    # --- Structure ---
    course_outline: dict               # {title, description, outcome, modules: [ModuleSpec]}
    admin_review_structure: AdminReview | None

    # --- Generation ---
    generated_modules: list[GeneratedModule]
    generated_manual: dict | None      # {title, content: jsonb sections}
    generation_progress: dict          # {completed: int, total: int, current: str}

    # --- Review ---
    review_report: ReviewReport | None
    refinement_count: int              # Tracks cycles (max 2)
    admin_review_final: AdminReview | None

    # --- Output ---
    result_course_id: UUID | None
    result_manual_id: UUID | None

    # --- Error handling ---
    error: str | None
    current_step: str                  # For SSE progress reporting
```

### 2.2 Graph Construction

```python
# src/agents/content/graph.py

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.agents.content.state import GenerationState
from src.agents.content.nodes import (
    prepare_context,
    extract_themes,
    design_structure,
    generate_modules,
    generate_manual,
    review_quality,
    refine_content,
    publish,
    handle_error,
)

def build_content_graph(db_uri: str) -> StateGraph:
    """Build the content generation LangGraph with PostgreSQL checkpointing."""

    graph = StateGraph(GenerationState)

    # --- Nodes ---
    graph.add_node("prepare_context", prepare_context)
    graph.add_node("extract_themes", extract_themes)
    graph.add_node("design_structure", design_structure)
    graph.add_node("admin_review_structure", lambda s: s)   # Passthrough — human edits state
    graph.add_node("generate_modules", generate_modules)
    graph.add_node("generate_manual", generate_manual)
    graph.add_node("review_quality", review_quality)
    graph.add_node("refine_content", refine_content)
    graph.add_node("admin_review_final", lambda s: s)       # Passthrough — human edits state
    graph.add_node("publish", publish)
    graph.add_node("handle_error", handle_error)

    # --- Edges ---
    graph.set_entry_point("prepare_context")

    graph.add_edge("prepare_context", "extract_themes")
    graph.add_edge("extract_themes", "design_structure")
    graph.add_edge("design_structure", "admin_review_structure")

    # After admin reviews structure
    graph.add_conditional_edges(
        "admin_review_structure",
        route_after_structure_review,
        {
            "generate": "generate_modules",
            "redesign": "design_structure",
            "abort": END,
        },
    )

    graph.add_edge("generate_modules", "generate_manual")
    graph.add_edge("generate_manual", "review_quality")

    # After quality review
    graph.add_conditional_edges(
        "review_quality",
        route_after_quality_review,
        {
            "pass": "admin_review_final",
            "refine": "refine_content",
            "fail": "handle_error",
        },
    )

    graph.add_edge("refine_content", "review_quality")

    # After admin final review
    graph.add_conditional_edges(
        "admin_review_final",
        route_after_final_review,
        {
            "publish": "publish",
            "refine": "refine_content",
            "abort": END,
        },
    )

    graph.add_edge("publish", END)
    graph.add_edge("handle_error", END)

    # --- Human-in-the-loop interrupts ---
    # LangGraph pauses execution BEFORE these nodes, waiting for human input
    compiled = graph.compile(
        checkpointer=AsyncPostgresSaver.from_conn_string(db_uri),
        interrupt_before=["admin_review_structure", "admin_review_final"],
    )

    return compiled
```

### 2.3 Edge Routing Functions

```python
# src/agents/content/routing.py

from src.agents.content.state import GenerationState

MAX_REFINEMENT_CYCLES = 2

def route_after_structure_review(state: GenerationState) -> str:
    """Route after admin reviews the course structure."""
    review = state.get("admin_review_structure")

    if review is None:
        # Should not happen — interrupt_before guarantees human input
        return "abort"

    if review["decision"] == "approve":
        return "generate"

    if review["decision"] == "edit":
        # Admin made inline edits to course_outline — regenerate from
        # the edited structure. The edits are already applied to state
        # by the review API handler before resuming the graph.
        return "generate"

    # decision == "reject"
    return "abort"


def route_after_quality_review(state: GenerationState) -> str:
    """Route based on quality reviewer's assessment."""
    report = state.get("review_report")

    if report is None:
        return "fail"

    if report["passed"]:
        return "pass"

    # Check refinement budget
    if state.get("refinement_count", 0) >= MAX_REFINEMENT_CYCLES:
        # Exhausted refinement cycles — send to admin anyway with the
        # review report attached so they can see remaining issues
        return "pass"

    # Has critical issues that need fixing
    if any(i["severity"] == "critical" for i in report["issues"]):
        return "refine"

    # Only minor issues — acceptable for admin review
    if all(i["severity"] == "minor" for i in report["issues"]):
        return "pass"

    # Major issues — try to refine
    return "refine"


def route_after_final_review(state: GenerationState) -> str:
    """Route after admin's final review of generated content."""
    review = state.get("admin_review_final")

    if review is None:
        return "abort"

    if review["decision"] == "approve":
        return "publish"

    if review["decision"] == "edit":
        # Admin made targeted edits — go through one more quality check
        return "refine"

    # decision == "reject"
    return "abort"
```

### 2.4 Visual Graph Diagram

```
                          START
                            |
                            v
                    +------------------+
                    | prepare_context  |  (no LLM)
                    +------------------+
                            |
                            v
                    +------------------+
                    | extract_themes   |  (LLM)
                    +------------------+
                            |
                            v
                    +------------------+
                    | design_structure |  (LLM)
                    +------------------+
                            |
                            v
               ===========================
               | admin_review_structure  |  <-- HUMAN CHECKPOINT 1
               |  (interrupt_before)     |
               ===========================
                     /      |      \
                    /       |       \
               abort    generate   redesign
                 |          |          |
                 v          v          |
                END  +--------------+  |
                     | generate_    |  |
                     | modules     |<-+
                     | (parallel)  |
                     +--------------+
                            |
                            v
                     +--------------+
                     | generate_    |
                     | manual      |
                     +--------------+
                            |
                            v
                     +--------------+
               +---->| review_      |
               |     | quality     |
               |     +--------------+
               |        /    |    \
               |       /     |     \
               |    pass   refine  fail
               |      |      |       |
               |      |      v       v
               |      |  +--------+ +----------+
               |      |  | refine | | handle_  |
               |      |  | content| | error    |
               |      |  +--------+ +----------+
               |      |      |            |
               |      |      +---->-------+---> END
               |      v
               | ===========================
               | | admin_review_final     |  <-- HUMAN CHECKPOINT 2
               | |  (interrupt_before)    |
               | ===========================
               |      /      |      \
               |     /       |       \
               |  abort   publish   refine
               |    |        |        |
               |    v        v        +------>--+
               |   END  +--------+              |
               |         | publish|              |
               |         +--------+              |
               |              |                  |
               +<-------------+                  |
                             END                 |
                                                 |
               +---------------------------------+
               |
               +---> (back to review_quality via refine_content)
```

### 2.5 PostgreSQL Checkpointing

LangGraph persists graph state to PostgreSQL using `langgraph-checkpoint-postgres`. This enables:

- **Durability:** Server restarts don't lose in-progress generation jobs. The graph resumes from the last completed node.
- **Human-in-the-loop:** When the graph hits `interrupt_before`, it serializes state to PostgreSQL and stops. The admin reviews at their own pace (minutes, hours, or days later). When they submit their review, the API handler updates state and resumes the graph.
- **Observability:** Every checkpoint is queryable. The admin can see exactly what state the pipeline is in.

```python
# src/agents/content/runner.py

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.agents.content.graph import build_content_graph
from src.config import settings

# Checkpointer uses a dedicated connection pool (separate from app DB pool)
# Table: langgraph_checkpoints (auto-created by the library)
CHECKPOINTER_URI = settings.DATABASE_URL.replace("+asyncpg", "")

async def start_generation(state: GenerationState) -> str:
    """Start a new generation run. Returns the thread_id for tracking."""
    graph = build_content_graph(CHECKPOINTER_URI)

    thread_id = str(state["job_id"])
    config = {"configurable": {"thread_id": thread_id}}

    # This runs until the first interrupt_before (admin_review_structure)
    await graph.ainvoke(state, config)

    return thread_id


async def resume_generation(job_id: str, updated_state: dict) -> None:
    """Resume a paused generation after admin review."""
    graph = build_content_graph(CHECKPOINTER_URI)

    config = {"configurable": {"thread_id": job_id}}

    # Update the state with admin's review, then resume
    await graph.aupdate_state(config, updated_state)
    await graph.ainvoke(None, config)
```

**Checkpoint table (auto-managed by langgraph-checkpoint-postgres):**

```sql
-- Created automatically on first use
CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT NOT NULL,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, checkpoint_id)
);
```

---

## 3. Agent Roles

Seven specialized agents, each with a single responsibility. Agents do not share context with each other — they receive inputs and produce outputs through the graph state.

### 3.1 Context Preparator

**Role:** Determine RAG mode and prepare source material. No LLM call — pure logic.

**Node:** `prepare_context`

**Inputs:** `source_document_ids`, `org_id`

**Outputs:** `rag_mode`, `full_texts` or `chunk_summary`, `source_metadata`

**Logic:**

```python
# src/agents/content/nodes/prepare_context.py

from src.agents.content.state import GenerationState

async def prepare_context(state: GenerationState) -> dict:
    """Determine RAG strategy and load source material metadata.

    Rules (from rag-retrieval.md):
    - Single doc, <= 3 pages: full_text mode (no chunking, no embeddings)
    - Single doc, 4-5 pages: configurable (default: full_text)
    - Single doc, > 5 pages OR multiple docs: chunked mode (use embeddings)
    """
    doc_ids = state["source_document_ids"]
    org_id = state["org_id"]

    documents = await load_documents(doc_ids, org_id)

    total_pages = sum(d.page_count or 0 for d in documents)
    is_single_doc = len(documents) == 1

    # Determine RAG mode
    if is_single_doc and total_pages <= 5:
        rag_mode = "full_text"
        full_texts = {d.id: d.full_text for d in documents}
        chunk_summary = None
    else:
        rag_mode = "chunked"
        full_texts = None
        chunk_summary = {}
        for d in documents:
            count = await count_chunks(d.id)
            chunk_summary[d.id] = count

    source_metadata = {
        "total_pages": total_pages,
        "doc_count": len(documents),
        "doc_titles": [d.title for d in documents],
        "languages": list({detect_language(d) for d in documents}),
    }

    return {
        "rag_mode": rag_mode,
        "full_texts": full_texts,
        "chunk_summary": chunk_summary,
        "source_metadata": source_metadata,
        "current_step": "extracting",
    }
```

### 3.2 Theme Extractor

**Role:** Identify the key themes in the source material, classify each by Bloom's taxonomy level, and (for chunked documents) record which chunk IDs map to each theme.

**Node:** `extract_themes`

**Inputs:** `rag_mode`, `full_texts` or `chunk_summary`, `source_document_ids`

**Outputs:** `extracted_themes`

**System prompt:**

```
You are a pedagogical content analyst. Your task is to identify the key themes
in the provided source material and classify each theme by its appropriate
Bloom's taxonomy level for workplace training.

For each theme, provide:
- key: a short snake_case identifier
- title: human-readable theme name
- bloom_level: one of [remember, understand, apply, analyze, evaluate, create]
- summary: 1-2 sentence description of what this theme covers
- chunk_ids: (if provided) the IDs of the text chunks that are most relevant

Guidelines:
- Aim for 4-8 themes per course. More granular topics become lesson-level, not theme-level.
- At least 50% of themes should target "apply" level or higher. Workplace training
  is about doing, not just knowing.
- Order themes from foundational to advanced (learning progression).
- Every factual claim must be traceable to the source material.

Respond in valid JSON.
```

**Retrieval strategy for chunked mode:**

```python
# src/agents/content/nodes/extract_themes.py

async def extract_themes(state: GenerationState) -> dict:
    """Extract themes from source material."""

    if state["rag_mode"] == "full_text":
        # Small doc: send entire text to LLM
        context = "\n\n".join(state["full_texts"].values())
        prompt = build_extraction_prompt(context, include_chunk_ids=False)

    else:
        # Large doc(s): retrieve ALL chunks ordered by position
        # Theme extraction needs the full picture, not a subset
        all_chunks = await load_all_chunks_ordered(
            state["source_document_ids"]
        )
        # Build a condensed representation: heading + first 200 chars per chunk
        # This fits in context even for large documents
        context = build_chunk_overview(all_chunks)
        prompt = build_extraction_prompt(context, include_chunk_ids=True)

    response = await llm_call(
        system_prompt=THEME_EXTRACTOR_SYSTEM_PROMPT,
        user_prompt=prompt,
        response_format="json",
    )

    themes = parse_themes(response)

    return {
        "extracted_themes": themes,
        "current_step": "structuring",
    }
```

### 3.3 Structure Designer

**Role:** Design the pedagogical scaffolding of the course: modules, lessons, exercise types, and learning progression. Ensures at least 50% of exercises target the "apply" Bloom level or higher.

**Node:** `design_structure`

**Inputs:** `extracted_themes`, `source_metadata`, `course_id` (for title context)

**Outputs:** `course_outline`

**System prompt:**

```
You are an instructional designer specializing in workplace training for
small and medium businesses. Design a course structure that turns the
provided themes into an effective learning experience.

Rules:
1. Each module covers 1-3 related themes. Order modules from foundational
   to advanced.
2. Each module contains 2-5 lessons:
   - At least one theory lesson (explains concepts)
   - At least one example lesson (shows real-world application)
   - At least one exercise lesson (learner practices)
   - Optionally a summary lesson
3. Exercise distribution: at least 50% of exercises must be "apply" level
   or higher (practical_case, dialogue, order_steps). Tests and true/false
   are acceptable for foundational knowledge but should not dominate.
4. Write a clear course outcome: "After completing this course, the employee
   will be able to..." — use action verbs.
5. Suggest exercise types from: test, true_false, fill_blank, order_steps,
   practical_case, dialogue.

Respond with a complete course outline in JSON format.
```

**Output example:**

```json
{
  "title": "Politica de Devoluciones",
  "description": "Curso completo sobre el proceso de devolucion...",
  "outcome": "Gestionar devoluciones de principio a fin, incluyendo casos excepcionales y clientes dificiles",
  "modules": [
    {
      "title": "Fundamentos de la Politica",
      "summary": "Plazos, condiciones y documentacion necesaria",
      "position": 1,
      "themes": ["plazos_basicos", "condiciones_devolucion"],
      "bloom_level": "understand",
      "chunk_ids": ["uuid1", "uuid2"],
      "lessons": [
        {"title": "Plazos y condiciones", "position": 1, "content_type": "theory"},
        {"title": "Documentacion necesaria", "position": 2, "content_type": "theory"},
        {"title": "Caso: devolucion estandar", "position": 3, "content_type": "example"},
        {"title": "Practica: identificar devolucion valida", "position": 4, "content_type": "exercise"}
      ]
    }
  ]
}
```

### 3.4 Module Generator

**Role:** Generate the actual content for each module's lessons and exercises. Operates on a single module at a time. Uses compartmented chunks — only sees the chunks relevant to its assigned themes.

**Node:** `generate_modules` (runs in parallel via fan-out)

**Inputs:** One `ModuleSpec` from `course_outline`, relevant chunks/text

**Outputs:** One `GeneratedModule` per invocation

**System prompt:**

```
You are a training content writer creating workplace learning materials.
Write engaging, practical content for the specified module.

Rules:
1. Theory lessons: explain concepts clearly with examples from the source
   material. Use simple language appropriate for employees, not academics.
2. Example lessons: present real scenarios from the source material.
   Use the company's own terminology and procedures.
3. Exercise lessons: create exercises that test practical application.
   Every exercise must include an explanation field citing the source.
4. Content must be factually grounded in the provided source material.
   Do NOT add information that is not in the sources.
5. Include citation markers [Fuente: document_title, seccion, pag. N]
   for every factual claim.
6. Write in the same language as the source material.
7. Format lesson content as Markdown.
8. For exercises, output the content field as specified in the data model
   (see exercise type schemas).
```

**Chunk selection for module generation:**

```python
# src/agents/content/nodes/generate_modules.py

async def get_module_context(
    module_spec: ModuleSpec,
    state: GenerationState,
) -> str:
    """Build compartmented context for a single module.

    Dual retrieval strategy:
    1. Primary: load chunks by ID from theme extraction (these were
       identified as relevant during extraction)
    2. Supplement: semantic search for each theme title to catch
       related content that extraction might have missed
    """
    if state["rag_mode"] == "full_text":
        # Small doc: module gets the full text (it's small enough)
        return "\n\n".join(state["full_texts"].values())

    context_chunks = []

    # 1. Primary: chunks identified during extraction
    primary_chunk_ids = module_spec.get("chunk_ids", [])
    if primary_chunk_ids:
        primary = await load_chunks_by_ids(primary_chunk_ids)
        context_chunks.extend(primary)

    # 2. Supplement: semantic search per theme
    for theme_key in module_spec["themes"]:
        theme = find_theme(state["extracted_themes"], theme_key)
        supplemental = await semantic_search(
            query=theme["title"] + " " + theme["summary"],
            document_ids=state["source_document_ids"],
            top_k=3,
            exclude_ids=[c.id for c in context_chunks],
        )
        context_chunks.extend(supplemental)

    # Deduplicate and order by document position
    context_chunks = deduplicate_chunks(context_chunks)
    context_chunks = order_by_position(context_chunks)

    return assemble_context_block(context_chunks)
```

### 3.5 Manual Generator

**Role:** Generate reference material (the manual). Unlike courses, manuals follow the document's original structure — they are reference material, not a learning progression. Employees consult manuals when they need specific information, not to learn sequentially.

**Node:** `generate_manual`

**Inputs:** `source_document_ids`, `rag_mode`, `full_texts` or chunks, `course_outline` (for alignment)

**Outputs:** `generated_manual`

**System prompt:**

```
You are a technical writer creating a reference manual from source material.

A manual is NOT a course. It is organized for quick lookup, not for learning.

Rules:
1. Preserve the source material's organizational structure (sections,
   subsections) rather than creating a learning progression.
2. Use clear headings that employees can scan quickly.
3. Include a table of contents.
4. For procedural content, use numbered step-by-step instructions.
5. For factual content, use tables and bullet points.
6. Include all relevant details from the source — a manual should be
   comprehensive. Employees use it as their single reference.
7. Cite sources: [Fuente: document_title, pag. N].
8. Write in the same language as the source material.

Output as JSON with sections:
{
  "title": "...",
  "content": {
    "toc": [...],
    "sections": [
      {"heading": "...", "level": 1, "body": "markdown content"},
      ...
    ]
  }
}
```

### 3.6 Quality Reviewer

**Role:** Independent verification of generated content against source material. The reviewer loads source documents separately — it never sees the generator's context window or prompt. This is structural independence (see [architecture.md](architecture.md), agent isolation).

**Node:** `review_quality`

**Inputs:** `generated_modules`, `generated_manual`, `source_document_ids` (loads its own context)

**Outputs:** `review_report`

**System prompt:**

```
You are a quality assurance reviewer for training content. Your job is to
verify that generated content is accurate, complete, and pedagogically sound.

IMPORTANT: You are an independent reviewer. You have been given the original
source documents and the generated content. Check the generated content
AGAINST the sources. Do not assume correctness.

Review criteria:
1. ACCURACY: Every factual claim in the generated content must be
   verifiable in the source material. Flag any claim you cannot verify.
2. COMPLETENESS: Key topics from the source should be covered.
   Flag significant omissions.
3. CITATIONS: Every factual statement must have a citation. Flag
   uncited claims.
4. EXERCISE QUALITY: Exercises must have correct answers that match
   the source. Practical cases must have realistic rubrics. Flag
   exercises with wrong answers or impossible scenarios.
5. BLOOM ALIGNMENT: At least 50% of exercises should be "apply" or
   higher. Flag if the course is too theory-heavy.
6. LANGUAGE: Content should be clear, professional, and in the same
   language as the source material. Flag jargon or unclear passages.
7. CONSISTENCY: Module content should not contradict other modules
   or the manual. Flag contradictions.

For each issue found, specify:
- severity: "critical" (factual error, wrong answer), "major" (significant
  omission, missing citations), or "minor" (style, clarity)
- module_index: which module (null for course-level)
- description: what's wrong
- suggestion: how to fix it

Respond in JSON: {"passed": bool, "overall_score": float, "issues": [...]}
A score >= 0.8 with no critical issues = passed.
```

**Independent context loading:**

```python
# src/agents/content/nodes/review_quality.py

async def review_quality(state: GenerationState) -> dict:
    """Independent quality review. Loads source docs separately."""

    # Load source material independently (NOT from state)
    if state["rag_mode"] == "full_text":
        source_context = await load_full_texts_from_db(
            state["source_document_ids"]
        )
    else:
        # Load ALL chunks for review (reviewer needs full picture)
        all_chunks = await load_all_chunks_ordered(
            state["source_document_ids"]
        )
        source_context = assemble_context_block(all_chunks)

    # Serialize generated content for review
    generated_content = serialize_for_review(
        state["generated_modules"],
        state["generated_manual"],
    )

    response = await llm_call(
        system_prompt=QUALITY_REVIEWER_SYSTEM_PROMPT,
        user_prompt=f"""Source material:
{source_context}

---

Generated content to review:
{generated_content}""",
        response_format="json",
    )

    report = parse_review_report(response)

    return {
        "review_report": report,
        "current_step": "reviewed",
    }
```

### 3.7 Content Refiner

**Role:** Apply targeted fixes based on the quality reviewer's report. Does not regenerate entire modules — fixes only the specific issues identified.

**Node:** `refine_content`

**Inputs:** `review_report` (issues list), `generated_modules`, `generated_manual`

**Outputs:** Updated `generated_modules` and/or `generated_manual`, incremented `refinement_count`

**System prompt:**

```
You are a content editor. You have been given a quality review report with
specific issues found in training content. Fix ONLY the issues listed.
Do not rewrite content that was not flagged.

For each issue:
- Read the description and suggestion
- Make the minimum change needed to resolve it
- Preserve the rest of the content exactly as-is
- If the issue is about a missing citation, add the citation from the
  source material provided
- If the issue is about a factual error, correct it using the source material

Respond with the corrected content in the same format as the input.
Mark each fix with a comment: <!-- FIX: issue description -->
```

```python
# src/agents/content/nodes/refine_content.py

async def refine_content(state: GenerationState) -> dict:
    """Apply targeted fixes from quality review."""
    report = state["review_report"]
    modules = state["generated_modules"]
    manual = state["generated_manual"]

    # Group issues by module
    module_issues = group_issues_by_module(report["issues"])

    # Load source context for corrections
    source_context = await load_source_context(state)

    # Fix each module that has issues
    refined_modules = list(modules)
    for module_idx, issues in module_issues.items():
        if module_idx is None:
            continue  # Course-level issues handled separately

        module_content = serialize_module(modules[module_idx])
        issues_text = serialize_issues(issues)

        response = await llm_call(
            system_prompt=CONTENT_REFINER_SYSTEM_PROMPT,
            user_prompt=f"""Issues to fix:
{issues_text}

Source material for reference:
{source_context}

Module content to fix:
{module_content}""",
        )

        refined_modules[module_idx] = parse_refined_module(response)

    return {
        "generated_modules": refined_modules,
        "refinement_count": state.get("refinement_count", 0) + 1,
        "current_step": "reviewing",
    }
```

---

## 4. RAG Integration

### 4.1 Conditional RAG

The pipeline uses the same conditional RAG strategy defined in [rag-retrieval.md](rag-retrieval.md):

| Document size | RAG mode | What happens |
|---------------|----------|--------------|
| Single doc, <= 3 pages | `full_text` | Entire document text is included in every agent's prompt. No embeddings, no retrieval. |
| Single doc, 4-5 pages | `full_text` (configurable) | Default to full text. Can be overridden to chunked via org settings. |
| Single doc, > 5 pages | `chunked` | Document is chunked and embedded during ingestion. Agents retrieve relevant chunks. |
| Multiple docs (any size) | `chunked` | Always chunked. Cross-document retrieval needed. |

The `prepare_context` node makes this decision once. All downstream agents respect the `rag_mode` field in state.

### 4.2 Theme-Based Chunk Grouping

During theme extraction, the extractor maps each theme to the chunk IDs that are most relevant to it. This creates a **theme-to-chunks index** that the module generator uses for compartmented retrieval.

```
Theme "plazos_basicos" --> [chunk_003, chunk_004, chunk_005]
Theme "excepciones"    --> [chunk_008, chunk_009, chunk_012]
Theme "casos_dificiles"--> [chunk_012, chunk_015, chunk_016]
```

Benefits:
- **Compartmentation:** Each module generator sees only its relevant chunks, not the entire document. This reduces noise and improves generation quality.
- **Traceability:** Every piece of generated content can trace back to specific source chunks via the theme mapping.
- **Overlap handling:** Chunks can appear in multiple themes (e.g., chunk_012 above). This is intentional — some content is relevant to multiple modules.

### 4.3 Dual Retrieval Strategy

Module generation uses two complementary retrieval strategies:

```
1. DETERMINISTIC (chunk IDs from extraction)
   Theme extractor identified specific chunks during analysis.
   These are loaded by ID — no search needed, no relevance guessing.
   
   Pros: Precise, reproducible, already verified during extraction.
   Cons: May miss related content not explicitly tagged.

2. SEMANTIC SUPPLEMENT (search by theme description)
   For each theme, run a semantic search using the theme title +
   summary as the query. Retrieve top 3 chunks not already in
   the deterministic set.
   
   Pros: Catches related content, handles cross-references.
   Cons: May retrieve tangentially related content.

Combined context = deterministic chunks + semantic supplement
                   (deduplicated, ordered by document position)
```

### 4.4 Citation Enforcement

Every agent that generates content is instructed to include citations. The pipeline enforces this at multiple levels:

1. **Prompt-level:** System prompts require `[Fuente: document_title, seccion, pag. N]` markers.
2. **Review-level:** The quality reviewer flags any uncited factual claims as "major" issues.
3. **Refinement-level:** The content refiner adds missing citations using source material.

Citation format matches the convention from [rag-retrieval.md](rag-retrieval.md), section 3.4.5.

---

## 5. Parallel Generation

### 5.1 Fan-Out with Semaphore

Module generation runs in parallel using `asyncio.gather` with a semaphore to limit concurrent LLM API calls. This prevents rate-limiting errors and keeps resource usage predictable.

```python
# src/agents/content/nodes/generate_modules.py

import asyncio
from src.agents.content.state import GenerationState, GeneratedModule

MAX_CONCURRENT_LLM_CALLS = 3

async def generate_modules(state: GenerationState) -> dict:
    """Generate all modules in parallel with bounded concurrency."""

    outline = state["course_outline"]
    modules = outline["modules"]
    total = len(modules)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
    progress = {"completed": 0, "total": total, "current": ""}

    async def generate_single_module(module_spec: dict, index: int) -> GeneratedModule:
        async with semaphore:
            progress["current"] = module_spec["title"]
            await send_sse_progress(state["job_id"], progress)

            context = await get_module_context(module_spec, state)

            result = await llm_call(
                system_prompt=MODULE_GENERATOR_SYSTEM_PROMPT,
                user_prompt=build_module_prompt(module_spec, context),
                response_format="json",
            )

            generated = parse_generated_module(result, module_spec)

            progress["completed"] += 1
            await send_sse_progress(state["job_id"], progress)

            return generated

    # Fan-out: all modules in parallel (bounded by semaphore)
    tasks = [
        generate_single_module(spec, i)
        for i, spec in enumerate(modules)
    ]
    generated_modules = await asyncio.gather(*tasks)

    return {
        "generated_modules": list(generated_modules),
        "generation_progress": progress,
        "current_step": "generating_manual",
    }
```

### 5.2 Per-Module Progress Tracking

The admin sees real-time progress via SSE events:

```
event: progress
data: {"job_id": "uuid", "step": "generating", "detail": {"completed": 0, "total": 5, "current": "Fundamentos de la Politica"}}

event: progress
data: {"job_id": "uuid", "step": "generating", "detail": {"completed": 1, "total": 5, "current": "Condiciones de Devolucion"}}

event: progress
data: {"job_id": "uuid", "step": "generating", "detail": {"completed": 2, "total": 5, "current": "Proceso Paso a Paso"}}
```

SSE events are sent through the same `StreamingResponse` infrastructure used by the tutor chat (see [backend-api.md](backend-api.md), section 4.2, Chat endpoints).

---

## 6. Error Handling

### 6.1 Per-Node Error Wrapper

Every node in the graph is wrapped with error handling. Errors are caught, logged, written to the generation job, and sent as SSE events. The graph transitions to the `handle_error` node.

```python
# src/agents/content/nodes/error_handling.py

import functools
import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from openai import APIError, RateLimitError, APITimeoutError

logger = logging.getLogger(__name__)

def node_error_wrapper(node_name: str):
    """Decorator that wraps a graph node with error handling."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(state: dict) -> dict:
            try:
                return await func(state)
            except Exception as e:
                logger.error(f"Node '{node_name}' failed: {e}", exc_info=True)

                # Update generation job status in DB
                await update_generation_job(
                    job_id=state["job_id"],
                    status="failed",
                    error_message=f"[{node_name}] {type(e).__name__}: {str(e)[:500]}",
                )

                # Send SSE error event
                await send_sse_event(state["job_id"], "error", {
                    "step": node_name,
                    "message": str(e)[:200],
                })

                return {
                    "error": f"[{node_name}] {str(e)[:500]}",
                    "current_step": "failed",
                }

        return wrapper
    return decorator
```

### 6.2 LLM API Error Handling with Retries

LLM calls use tenacity for retry logic with exponential backoff. This handles transient API errors (rate limits, timeouts, server errors) without failing the entire pipeline.

```python
# src/agents/content/llm.py

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from openai import APIError, RateLimitError, APITimeoutError

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIError)),
    before_sleep=lambda retry_state: logger.warning(
        f"LLM call retry {retry_state.attempt_number}/3: "
        f"{retry_state.outcome.exception()}"
    ),
)
async def llm_call(
    system_prompt: str,
    user_prompt: str,
    response_format: str = "text",
    max_tokens: int = 4096,
) -> str:
    """Make an LLM API call with retry logic.

    Retry policy:
    - Max 3 attempts
    - Exponential backoff: 4s, 8s, 16s (capped at 60s)
    - Retries on: RateLimitError, APITimeoutError, generic APIError
    - Does NOT retry on: AuthenticationError, BadRequestError (these are
      configuration errors, not transient failures)
    """
    client = await get_llm_client()
    model = await get_model_name()

    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    }

    if response_format == "json":
        kwargs["response_format"] = {"type": "json_object"}

    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content
```

### 6.3 JSON Parse Error Recovery

LLM responses expected in JSON format may contain malformed JSON. The pipeline uses a two-stage recovery strategy:

```python
# src/agents/content/parsing.py

import json
import re

def parse_json_response(response: str, context: str = "") -> dict:
    """Parse LLM response as JSON with recovery strategies.

    Strategy 1: Direct parse
    Strategy 2: Extract JSON from markdown code block
    Strategy 3: Fix common issues (trailing commas, single quotes)
    Strategy 4: Ask LLM to fix its own output (one retry)
    """
    # Strategy 1: direct parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from markdown code block
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: fix common issues
    cleaned = response.strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # trailing commas
    cleaned = cleaned.replace("'", '"')                 # single quotes
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 4: ask LLM to fix it
    fix_prompt = f"""The following was supposed to be valid JSON but has errors.
Fix it and return ONLY the corrected JSON, nothing else.

Context: {context}

Broken JSON:
{response[:2000]}"""

    fixed = await llm_call(
        system_prompt="You fix malformed JSON. Return ONLY valid JSON.",
        user_prompt=fix_prompt,
        response_format="json",
    )
    return json.loads(fixed)
```

### 6.4 Quality Failure Routing

The quality review can result in three outcomes, routed by `route_after_quality_review`:

| Outcome | Condition | Action |
|---------|-----------|--------|
| **Pass** | `score >= 0.8`, no critical issues | Proceed to admin final review |
| **Refine** | Critical or major issues, `refinement_count < 2` | Send to content refiner, then re-review |
| **Fail** | `refinement_count >= 2` and still critical issues | Go to error handler — admin is notified the generation could not meet quality standards |

After 2 refinement cycles without passing, the pipeline does not loop forever. It sends the content to the admin with the review report attached, letting them decide whether to accept, manually fix, or reject.

### 6.5 Error Handler Node

The terminal error handler updates the generation job in PostgreSQL and sends a final SSE event.

```python
# src/agents/content/nodes/error_handling.py

async def handle_error(state: GenerationState) -> dict:
    """Terminal error handler. Updates generation_jobs and notifies admin."""

    error_msg = state.get("error", "Unknown error")

    # Update generation_jobs table
    await update_generation_job(
        job_id=state["job_id"],
        status="failed",
        error_message=error_msg,
    )

    # Send SSE event
    await send_sse_event(state["job_id"], "error", {
        "step": state.get("current_step", "unknown"),
        "message": error_msg,
        "recoverable": is_recoverable(error_msg),
    })

    return {"current_step": "failed"}
```

---

## 7. Admin Interaction

### 7.1 Two Mandatory Checkpoints

The pipeline has two `interrupt_before` points where it pauses and waits for admin input:

| Checkpoint | When | What admin reviews | What admin can do |
|------------|------|---------------------|-------------------|
| **Structure review** | After `design_structure`, before `generate_modules` | Course outline: title, outcome, module structure, lesson plan | Approve, edit inline, reject |
| **Final review** | After `review_quality` passes, before `publish` | Full generated content + quality report | Approve, edit inline, reject, request refinement |

The graph is designed so that **no content reaches learners without explicit admin approval**. The structure checkpoint prevents wasted generation time on a bad outline. The final checkpoint prevents publishing flawed content.

### 7.2 How Interrupts Work

When LangGraph hits an `interrupt_before` node:

1. Graph state is serialized to PostgreSQL (`langgraph_checkpoints` table).
2. Generation job status is updated (e.g., `structuring` -> `awaiting_review`).
3. SSE event is sent: `{event: "awaiting_review", data: {checkpoint: "structure"}}`.
4. The graph stops. No further nodes execute.
5. The admin reviews at their own pace via the API.
6. When the admin submits their review, the API handler calls `resume_generation()` which updates state and resumes the graph from the interrupted point.

### 7.3 Review API Endpoints

These endpoints are part of the generation jobs API (see [backend-api.md](backend-api.md), section 4.2):

```
GET  /api/v1/generation-jobs/{id}/review
POST /api/v1/generation-jobs/{id}/review
PUT  /api/v1/generation-jobs/{id}/content
POST /api/v1/generation-jobs/{id}/regenerate-module/{module_index}
GET  /api/v1/generation-jobs/{id}/progress (SSE)
```

#### GET /generation-jobs/{id}/review

Returns the current state for review. The response depends on which checkpoint is active:

```python
# Structure checkpoint response
{
    "checkpoint": "structure",
    "course_outline": {
        "title": "Politica de Devoluciones",
        "outcome": "...",
        "modules": [...]
    },
    "source_metadata": {
        "total_pages": 12,
        "doc_titles": ["Manual de Devoluciones v3.pdf"]
    },
    "extracted_themes": [...]
}

# Final checkpoint response
{
    "checkpoint": "final",
    "generated_modules": [...],
    "generated_manual": {...},
    "review_report": {
        "passed": true,
        "overall_score": 0.87,
        "issues": [
            {"severity": "minor", "module_index": 2, "description": "..."}
        ]
    }
}
```

#### POST /generation-jobs/{id}/review

Submit the admin's review decision:

```python
# Approve structure
{
    "decision": "approve",
    "notes": null
}

# Approve with edits
{
    "decision": "edit",
    "edits": {
        "course_outline": {
            "title": "Proceso de Devoluciones (editado)",
            "modules": [...]  # Admin can reorder, rename, add, remove modules
        }
    },
    "notes": "Renamed title, moved module 3 before module 2"
}

# Reject
{
    "decision": "reject",
    "notes": "Source material is insufficient for a full course"
}
```

**Backend handler:**

```python
# src/routes/generation_jobs.py

@router.post("/generation-jobs/{id}/review")
async def submit_review(
    id: UUID,
    user: AdminUser,
    db: DBSession,
    body: ReviewSubmission,
):
    """Submit admin review and resume the generation pipeline."""
    job = await get_job_or_404(id, db)

    # Determine which checkpoint we're at
    checkpoint = determine_active_checkpoint(job)

    if checkpoint == "structure":
        state_update = {"admin_review_structure": body.model_dump()}
        if body.decision == "edit" and body.edits:
            state_update["course_outline"] = body.edits["course_outline"]

    elif checkpoint == "final":
        state_update = {"admin_review_final": body.model_dump()}

    # Resume the graph
    await resume_generation(str(id), state_update)

    return {"status": "resumed", "decision": body.decision}
```

#### PUT /generation-jobs/{id}/content

Inline editing API. The admin can directly modify specific parts of the generated content without going through the full review flow:

```python
# Edit a specific lesson's content
{
    "target": "module.2.lesson.1",
    "field": "content",
    "value": "Updated lesson content with admin corrections..."
}

# Edit an exercise
{
    "target": "module.3.lesson.4.exercise.0",
    "field": "content.correct",
    "value": 2
}

# Edit course metadata
{
    "target": "course",
    "field": "outcome",
    "value": "Updated course outcome..."
}
```

#### POST /generation-jobs/{id}/regenerate-module/{module_index}

Regenerate a single module without re-running the entire pipeline. Useful when the admin is mostly satisfied but one module needs a complete redo.

```python
@router.post("/generation-jobs/{id}/regenerate-module/{module_index}")
async def regenerate_module(
    id: UUID,
    module_index: int,
    user: AdminUser,
    db: DBSession,
    body: RegenerateModuleRequest | None = None,
):
    """Regenerate a single module. Optionally with updated instructions."""
    job = await get_job_or_404(id, db)

    # Load current graph state from checkpoint
    graph_state = await load_checkpoint_state(str(id))

    module_spec = graph_state["course_outline"]["modules"][module_index]

    # Apply any admin instructions
    if body and body.instructions:
        additional_context = body.instructions
    else:
        additional_context = None

    # Generate just this module
    context = await get_module_context(module_spec, graph_state)
    regenerated = await generate_single_module_with_context(
        module_spec, context, additional_context
    )

    # Update the module in state
    graph_state["generated_modules"][module_index] = regenerated

    # Save updated state back to checkpoint
    await save_checkpoint_state(str(id), graph_state)

    return {"status": "regenerated", "module_index": module_index}
```

### 7.4 Progress SSE

The admin sees real-time progress through a dedicated SSE endpoint:

```
GET /api/v1/generation-jobs/{id}/progress
Content-Type: text/event-stream
```

**Event types:**

```
# Pipeline step change
event: step
data: {"step": "extracting", "message": "Analyzing source material..."}

event: step
data: {"step": "structuring", "message": "Designing course structure..."}

# Module generation progress
event: progress
data: {"step": "generating", "completed": 2, "total": 5, "current": "Proceso Paso a Paso"}

# Checkpoint reached — admin action required
event: awaiting_review
data: {"checkpoint": "structure", "message": "Course structure ready for review"}

event: awaiting_review
data: {"checkpoint": "final", "message": "Content generated and reviewed. Ready for final approval."}

# Quality review result
event: review_result
data: {"passed": true, "score": 0.87, "issues_count": 2, "critical_count": 0}

# Refinement cycle
event: refining
data: {"cycle": 1, "max_cycles": 2, "issues_fixing": 3}

# Completion
event: completed
data: {"course_id": "uuid", "manual_id": "uuid", "message": "Course published successfully"}

# Error
event: error
data: {"step": "generate_modules", "message": "LLM API timeout after 3 retries", "recoverable": true}
```

**SSE implementation:**

```python
# src/routes/generation_jobs.py

from fastapi.responses import StreamingResponse
import asyncio

@router.get("/generation-jobs/{id}/progress")
async def generation_progress(
    id: UUID,
    user: AdminUser,
):
    """SSE endpoint for real-time generation progress."""

    async def event_stream():
        pubsub = get_sse_pubsub()
        channel = f"generation:{id}"

        async for event in pubsub.subscribe(channel):
            yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"

            if event["type"] in ("completed", "error"):
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
```

**SSE publishing (used by graph nodes):**

```python
# src/agents/content/sse.py

import json

# In-process pub/sub for SSE events
# For multi-process deployments, replace with PostgreSQL LISTEN/NOTIFY

_subscribers: dict[str, list[asyncio.Queue]] = {}

async def send_sse_event(job_id: UUID, event_type: str, data: dict):
    """Publish an SSE event for a generation job."""
    channel = f"generation:{job_id}"
    event = {"type": event_type, "data": data}

    for queue in _subscribers.get(channel, []):
        await queue.put(event)

async def send_sse_progress(job_id: UUID, progress: dict):
    """Convenience: send a progress event."""
    await send_sse_event(job_id, "progress", {
        "step": "generating",
        **progress,
    })

async def send_sse_step(job_id: UUID, step: str, message: str):
    """Convenience: send a step change event."""
    await send_sse_event(job_id, "step", {
        "step": step,
        "message": message,
    })
```

---

## 8. Publish Node

The final node persists the generated content to the database, creating the actual course, modules, lessons, exercises, and manual rows.

```python
# src/agents/content/nodes/publish.py

async def publish(state: GenerationState) -> dict:
    """Persist generated content to database and update generation job."""

    async with get_db_session() as db:
        # 1. Create or update course
        course_id = state.get("course_id")
        outline = state["course_outline"]

        if course_id:
            course = await db.get(Course, course_id)
            course.title = outline["title"]
            course.description = outline["description"]
            course.outcome = outline["outcome"]
        else:
            course = Course(
                org_id=state["org_id"],
                created_by=state["triggered_by"],
                source_document_id=state["source_document_ids"][0],
                title=outline["title"],
                description=outline["description"],
                outcome=outline["outcome"],
                status="draft",  # Publish action is separate
            )
            db.add(course)
            await db.flush()
            course_id = course.id

        # 2. Create modules, lessons, exercises
        for gen_module in state["generated_modules"]:
            spec = gen_module["module_spec"]
            module = Module(
                course_id=course_id,
                title=spec["title"],
                summary=spec["summary"],
                position=spec["position"],
            )
            db.add(module)
            await db.flush()

            for gen_lesson in gen_module["lessons"]:
                lesson = Lesson(
                    module_id=module.id,
                    title=gen_lesson["title"],
                    content=gen_lesson["content"],
                    position=gen_lesson["position"],
                )
                db.add(lesson)
                await db.flush()

            for gen_exercise in gen_module["exercises"]:
                exercise = Exercise(
                    lesson_id=lesson.id,  # Last lesson in module
                    type=gen_exercise["type"],
                    content=gen_exercise["content"],
                    position=gen_exercise["position"],
                )
                db.add(exercise)

        # 3. Create manual
        if state.get("generated_manual"):
            manual = Manual(
                org_id=state["org_id"],
                created_by=state["triggered_by"],
                source_document_id=state["source_document_ids"][0],
                course_id=course_id,
                title=state["generated_manual"]["title"],
                content=state["generated_manual"]["content"],
                status="draft",
            )
            db.add(manual)
            await db.flush()
            manual_id = manual.id
        else:
            manual_id = None

        # 4. Update generation job
        await update_generation_job(
            job_id=state["job_id"],
            status="published",
            result_course_id=course_id,
            result_manual_id=manual_id,
        )

        await db.commit()

    # 5. Send completion SSE event
    await send_sse_event(state["job_id"], "completed", {
        "course_id": str(course_id),
        "manual_id": str(manual_id) if manual_id else None,
        "message": "Course and manual generated successfully",
    })

    return {
        "result_course_id": course_id,
        "result_manual_id": manual_id,
        "current_step": "published",
    }
```

---

## 9. Generation Job Lifecycle

Integration with the `generation_jobs` table from [data-model.md](data-model.md):

```
Admin triggers POST /courses/{id}/generate
    |
    v
generation_jobs row created:
  status = 'pending'
  triggered_by = admin.id
  source_document_id = doc.id
  output_type = 'course_and_manual'
    |
    v
LangGraph graph starts (asyncio.create_task)
    |
    +-- prepare_context     -> status = 'extracting'
    +-- extract_themes      -> status = 'extracting'
    +-- design_structure    -> status = 'structuring'
    +-- [INTERRUPT]         -> status = 'awaiting_structure_review'
    |                          (admin reviews via API)
    +-- generate_modules    -> status = 'generating'
    +-- generate_manual     -> status = 'generating'
    +-- review_quality      -> status = 'reviewing'
    +-- [refine_content]    -> status = 'reviewing' (if needed)
    +-- [INTERRUPT]         -> status = 'awaiting_final_review'
    |                          (admin reviews via API)
    +-- publish             -> status = 'published'
                               result_course_id = UUID
                               result_manual_id = UUID
```

The `generation_step` enum in the data model maps to these transitions:

| Enum value | Graph state |
|------------|-------------|
| `pending` | Job created, graph not yet started |
| `extracting` | `prepare_context` or `extract_themes` running |
| `structuring` | `design_structure` running or awaiting structure review |
| `generating` | `generate_modules` or `generate_manual` running |
| `reviewing` | `review_quality` or `refine_content` running, or awaiting final review |
| `published` | `publish` completed successfully |
| `failed` | Any node failed after retries, or admin rejected |

---

## 10. Configuration

```python
# src/config.py (additions for content generation)

class ContentGenerationConfig(BaseSettings):
    # Concurrency
    MAX_CONCURRENT_LLM_CALLS: int = 3           # Semaphore limit for parallel module gen
    MAX_REFINEMENT_CYCLES: int = 2              # Quality review retry budget

    # LLM parameters for generation
    GENERATION_MAX_TOKENS: int = 4096           # Per module
    GENERATION_TEMPERATURE: float = 0.3         # Low creativity, high fidelity
    REVIEW_TEMPERATURE: float = 0.1             # Very low — reviewer should be strict

    # Retry policy
    LLM_RETRY_ATTEMPTS: int = 3
    LLM_RETRY_MIN_WAIT: int = 4                 # seconds
    LLM_RETRY_MAX_WAIT: int = 60                # seconds

    # RAG thresholds (from rag-retrieval.md)
    FULL_TEXT_PAGE_THRESHOLD: int = 5            # Docs with <= N pages use full text
    SEMANTIC_SEARCH_TOP_K: int = 3              # Supplemental chunks per theme
    QUALITY_PASS_THRESHOLD: float = 0.8         # Minimum score to pass review
```

---

## 11. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **LangGraph over raw asyncio** | State machine with checkpointing, human-in-the-loop, and edge routing is exactly what LangGraph provides. Building this from scratch would be significant undifferentiated work. |
| **PostgreSQL checkpointing** | The same database for everything (data model, sessions, checkpoints). No Redis dependency. Survives server restarts. |
| **2 human checkpoints, not 0 or 1** | Structure review prevents wasted generation on a bad outline. Final review catches quality issues the automated reviewer missed. Both are mandatory because the admin is accountable for what employees learn. |
| **Semaphore-bounded parallelism** | 3 concurrent calls balances throughput against API rate limits. Configurable per deployment. |
| **Independent quality reviewer** | Reviewer loads source docs independently, never sees the generator's context. Error rates multiply with independent verification (from [architecture.md](architecture.md) research). |
| **Max 2 refinement cycles** | Prevents infinite loops. After 2 failed cycles, the content goes to admin with the review report — a human must decide. |
| **Chunk-based compartmentation** | Module generators see only their relevant chunks. Reduces noise, improves accuracy, enforces need-to-know principle from [architecture.md](architecture.md). |
| **SSE for progress, not polling** | SSE infrastructure already exists for tutor chat. Polling would create unnecessary load on the API. |
| **Publish creates draft, not published** | The `publish` node writes to DB with `status=draft`. The admin publishes the course separately via `POST /courses/{id}/publish` after their final review. This separates "generation complete" from "visible to employees". |
| **Single-module regeneration** | The admin should not have to regenerate an entire course because one module is bad. Targeted regeneration saves time and LLM costs. |
| **Manual generated after course** | The manual uses the course outline for structural alignment but follows the source document's organization. Generating it after the course ensures consistency. |

---

## 12. Adaptive Regeneration (Phase 2+)

The pipeline described above generates content **once**. Phase 2 introduces data-driven regeneration based on real employee performance.

### 12.1 The Problem

A course is generated from documents by agents who have never seen a real employee struggle with the content. The first version is a best guess. After 50+ employees take the course, the system has real data about what works and what doesn't.

### 12.2 Signals

| Signal | Source | Threshold |
|--------|--------|-----------|
| Module pass rate | `exercise_attempts` JOIN `lessons` JOIN `modules` | < 60% pass rate across 10+ attempts |
| Average attempts per exercise | `exercise_attempts` GROUP BY `exercise_id` | > 2.5 attempts average |
| Tutor question volume | `chat_messages` filtered by `course_id` | > 5 questions on same topic in 7 days |
| Completion drop-off | `enrollments` status = 'abandoned' at specific module | > 30% abandon at same module |
| Time to complete | `exercise_attempts.created_at` delta | 2x longer than median for same course |

### 12.3 Regeneration Flow

When thresholds are exceeded:

```
System detects weak module
    |
    v
Flag course for review (admin notification)
    |
    v
Admin reviews: accept regeneration, manual edit, or dismiss
    |
    v
If accepted: trigger regeneration pipeline for that module only
    |
    v
New module replaces old one. Active enrollments continue from where they left off.
```

The regeneration uses the **same pipeline** as initial generation (Section 2), but with additional context:

- The quality report from the failed module (what went wrong)
- Real employee questions from the tutor chat (what confused people)
- Exercise attempt data (which specific questions were missed)

This gives the regeneration agents information the initial generation agents didn't have.

### 12.4 Implementation Notes

- **No schema changes needed.** All signals come from existing tables: `exercise_attempts`, `chat_messages`, `enrollments`, `lessons`, `modules`.
- **Single-module regeneration** already exists (Section 7.3). The adaptive flow reuses it.
- **Version tracking** on modules (add `version` column to `modules` table) lets the system track which version each employee is on.
- **Opt-in for MVP.** Adaptive regeneration is disabled by default. Admins enable it per course when they have enough data.
