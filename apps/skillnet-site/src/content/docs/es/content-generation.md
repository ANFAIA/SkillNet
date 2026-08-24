---
title: "Generación de contenido"
order: 5
section: "core"
---

# Pipeline de generación de contenido

> **Estado: v1.** Arquitectura completa del pipeline multiagente de generación de contenido. Transforma documentos subidos en cursos estructurados y manuales de referencia mediante orquestación con LangGraph con puntos de control humanos.

Depende de: [architecture.md](architecture.md), [data-model.md](data-model.md), [rag-retrieval.md](rag-retrieval.md), [backend-api.md](backend-api.md).

---

## 1. Visión general

El pipeline de generación de contenido toma uno o varios documentos ingeridos y produce un curso completo (módulos, lecciones, ejercicios) y un manual de referencia que lo acompaña. El pipeline es una máquina de estados de LangGraph con 10 nodos, 7 agentes especializados, 2 puntos de control humanos obligatorios y checkpointing respaldado por PostgreSQL para garantizar la durabilidad.

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

**Principios de diseño:**

- **El humano mantiene el control.** El administrador revisa y puede editar la estructura antes de generar cualquier contenido, y revisa el resultado final antes de publicarlo. Nada llega a los aprendices sin aprobación explícita.
- **A prueba de fallos, no rápido para fallar.** Cada nodo captura sus propios errores, actualiza el estado del trabajo de generación y envía un evento SSE. El administrador ve qué ha fallado y puede reintentarlo.
- **Contexto compartimentado.** Cada agente ve solo los datos que necesita. El revisor de calidad carga los documentos fuente de forma independiente — nunca ve el contexto del generador, lo que permite una verificación realmente independiente.

---

## 2. Definición del grafo de LangGraph

### 2.1 GenerationState

El estado fluye por todos los nodos. Cada nodo lee lo que necesita y escribe sus salidas. LangGraph gestiona la persistencia y la reanudación mediante checkpointing en PostgreSQL.

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

### 2.2 Construcción del grafo

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

### 2.3 Funciones de enrutado de aristas

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

### 2.4 Diagrama visual del grafo

```
                          START
                            |
                            v
                    +------------------+
                    | prepare_context  |  (sin LLM)
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
               | admin_review_structure  |  <-- PUNTO DE CONTROL HUMANO 1
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
               | | admin_review_final     |  <-- PUNTO DE CONTROL HUMANO 2
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
               +---> (vuelve a review_quality via refine_content)
```

### 2.5 Checkpointing en PostgreSQL

LangGraph persiste el estado del grafo en PostgreSQL usando `langgraph-checkpoint-postgres`. Esto permite:

- **Durabilidad:** los reinicios del servidor no pierden trabajos de generación en curso. El grafo se reanuda desde el último nodo completado.
- **Humano en el bucle:** cuando el grafo llega a `interrupt_before`, serializa el estado en PostgreSQL y se detiene. El administrador revisa a su propio ritmo (minutos, horas o días después). Cuando envía su revisión, el manejador de la API actualiza el estado y reanuda el grafo.
- **Observabilidad:** cada checkpoint es consultable. El administrador puede ver exactamente en qué estado se encuentra el pipeline.

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

**Tabla de checkpoints (gestionada automáticamente por langgraph-checkpoint-postgres):**

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

## 3. Roles de los agentes

Siete agentes especializados, cada uno con una única responsabilidad. Los agentes no comparten contexto entre sí — reciben entradas y producen salidas a través del estado del grafo.

### 3.1 Preparador de contexto

**Rol:** determinar el modo de RAG y preparar el material fuente. Sin llamada al LLM — lógica pura.

**Nodo:** `prepare_context`

**Entradas:** `source_document_ids`, `org_id`

**Salidas:** `rag_mode`, `full_texts` o `chunk_summary`, `source_metadata`

**Lógica:**

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

### 3.2 Extractor de temas

**Rol:** identificar los temas clave del material fuente, clasificar cada uno según el nivel de la taxonomía de Bloom y (para documentos fragmentados) registrar qué IDs de fragmento corresponden a cada tema.

**Nodo:** `extract_themes`

**Entradas:** `rag_mode`, `full_texts` o `chunk_summary`, `source_document_ids`

**Salidas:** `extracted_themes`

**Prompt de sistema:**

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

**Estrategia de recuperación para el modo fragmentado:**

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

### 3.3 Diseñador de estructura

**Rol:** diseñar el andamiaje pedagógico del curso: módulos, lecciones, tipos de ejercicio y progresión de aprendizaje. Garantiza que al menos el 50% de los ejercicios apunten al nivel "apply" de Bloom o superior.

**Nodo:** `design_structure`

**Entradas:** `extracted_themes`, `source_metadata`, `course_id` (para el contexto del título)

**Salidas:** `course_outline`

**Prompt de sistema:**

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

**Ejemplo de salida:**

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

### 3.4 Generador de módulos

**Rol:** generar el contenido real de las lecciones y ejercicios de cada módulo. Opera sobre un único módulo a la vez. Usa fragmentos compartimentados — solo ve los fragmentos relevantes para los temas que tiene asignados.

**Nodo:** `generate_modules` (se ejecuta en paralelo mediante fan-out)

**Entradas:** un `ModuleSpec` de `course_outline`, fragmentos/texto relevantes

**Salidas:** un `GeneratedModule` por invocación

**Prompt de sistema:**

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

**Selección de fragmentos para la generación de módulos:**

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

### 3.5 Generador de manuales

**Rol:** generar el material de referencia (el manual). A diferencia de los cursos, los manuales siguen la estructura original del documento — son material de referencia, no una progresión de aprendizaje. Los empleados consultan los manuales cuando necesitan información concreta, no para aprender de forma secuencial.

**Nodo:** `generate_manual`

**Entradas:** `source_document_ids`, `rag_mode`, `full_texts` o fragmentos, `course_outline` (para alineación)

**Salidas:** `generated_manual`

**Prompt de sistema:**

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

### 3.6 Revisor de calidad

**Rol:** verificación independiente del contenido generado frente al material fuente. El revisor carga los documentos fuente por separado — nunca ve la ventana de contexto ni el prompt del generador. Se trata de independencia estructural (ver [architecture.md](architecture.md), aislamiento de agentes).

**Nodo:** `review_quality`

**Entradas:** `generated_modules`, `generated_manual`, `source_document_ids` (carga su propio contexto)

**Salidas:** `review_report`

**Prompt de sistema:**

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

**Carga de contexto independiente:**

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

### 3.7 Refinador de contenido

**Rol:** aplicar correcciones puntuales según el informe del revisor de calidad. No regenera módulos enteros — corrige solo los problemas concretos identificados.

**Nodo:** `refine_content`

**Entradas:** `review_report` (lista de problemas), `generated_modules`, `generated_manual`

**Salidas:** `generated_modules` y/o `generated_manual` actualizados, `refinement_count` incrementado

**Prompt de sistema:**

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

## 4. Integración con RAG

### 4.1 RAG condicional

El pipeline usa la misma estrategia de RAG condicional definida en [rag-retrieval.md](rag-retrieval.md):

| Tamaño del documento | Modo RAG | Qué ocurre |
|---------------|----------|--------------|
| Un solo doc, <= 3 páginas | `full_text` | Se incluye el texto completo del documento en el prompt de cada agente. Sin embeddings, sin recuperación. |
| Un solo doc, 4-5 páginas | `full_text` (configurable) | Por defecto, texto completo. Se puede cambiar a fragmentado mediante los ajustes de la organización. |
| Un solo doc, > 5 páginas | `chunked` | El documento se fragmenta y se generan embeddings durante la ingesta. Los agentes recuperan los fragmentos relevantes. |
| Varios docs (cualquier tamaño) | `chunked` | Siempre fragmentado. Se necesita recuperación entre documentos. |

El nodo `prepare_context` toma esta decisión una sola vez. Todos los agentes posteriores respetan el campo `rag_mode` del estado.

### 4.2 Agrupación de fragmentos por tema

Durante la extracción de temas, el extractor asigna a cada tema los IDs de fragmento que le son más relevantes. Esto crea un **índice tema-a-fragmentos** que el generador de módulos usa para la recuperación compartimentada.

```
Theme "plazos_basicos" --> [chunk_003, chunk_004, chunk_005]
Theme "excepciones"    --> [chunk_008, chunk_009, chunk_012]
Theme "casos_dificiles"--> [chunk_012, chunk_015, chunk_016]
```

Ventajas:
- **Compartimentación:** cada generador de módulo ve solo sus fragmentos relevantes, no el documento entero. Esto reduce el ruido y mejora la calidad de la generación.
- **Trazabilidad:** cada pieza de contenido generado puede rastrearse hasta fragmentos fuente concretos mediante el mapeo de temas.
- **Gestión de solapamientos:** los fragmentos pueden aparecer en varios temas (por ejemplo, chunk_012 arriba). Esto es intencionado — parte del contenido es relevante para varios módulos.

### 4.3 Estrategia de recuperación dual

La generación de módulos usa dos estrategias de recuperación complementarias:

```
1. DETERMINISTA (IDs de fragmento de la extracción)
   El extractor de temas identificó fragmentos concretos durante el análisis.
   Se cargan por ID — sin necesidad de búsqueda, sin adivinar relevancia.
   
   Ventajas: precisa, reproducible, ya verificada durante la extracción.
   Inconvenientes: puede pasar por alto contenido relacionado no etiquetado explícitamente.

2. SUPLEMENTO SEMÁNTICO (búsqueda por descripción del tema)
   Para cada tema, se ejecuta una búsqueda semántica usando el título del tema +
   el resumen como consulta. Se recuperan los 3 fragmentos principales que aún no
   estén en el conjunto determinista.
   
   Ventajas: capta contenido relacionado, gestiona referencias cruzadas.
   Inconvenientes: puede recuperar contenido tangencialmente relacionado.

Contexto combinado = fragmentos deterministas + suplemento semántico
                   (deduplicados, ordenados por posición en el documento)
```

### 4.4 Exigencia de citas

Todo agente que genera contenido tiene instrucciones de incluir citas. El pipeline lo exige en varios niveles:

1. **A nivel de prompt:** los prompts de sistema exigen marcadores `[Fuente: document_title, seccion, pag. N]`.
2. **A nivel de revisión:** el revisor de calidad marca cualquier afirmación factual sin cita como problema "major".
3. **A nivel de refinamiento:** el refinador de contenido añade las citas que faltan usando el material fuente.

El formato de citas coincide con la convención de [rag-retrieval.md](rag-retrieval.md), sección 3.4.5.

---

## 5. Generación en paralelo

### 5.1 Fan-out con semáforo

La generación de módulos se ejecuta en paralelo usando `asyncio.gather` con un semáforo que limita las llamadas concurrentes a la API del LLM. Esto evita errores de limitación de tasa y mantiene predecible el uso de recursos.

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

### 5.2 Seguimiento del progreso por módulo

El administrador ve el progreso en tiempo real mediante eventos SSE:

```
event: progress
data: {"job_id": "uuid", "step": "generating", "detail": {"completed": 0, "total": 5, "current": "Fundamentos de la Politica"}}

event: progress
data: {"job_id": "uuid", "step": "generating", "detail": {"completed": 1, "total": 5, "current": "Condiciones de Devolucion"}}

event: progress
data: {"job_id": "uuid", "step": "generating", "detail": {"completed": 2, "total": 5, "current": "Proceso Paso a Paso"}}
```

Los eventos SSE se envían a través de la misma infraestructura `StreamingResponse` que usa el chat del tutor (ver [backend-api.md](backend-api.md), sección 4.2, endpoints de chat).

---

## 6. Gestión de errores

### 6.1 Envoltorio de error por nodo

Cada nodo del grafo está envuelto con gestión de errores. Los errores se capturan, se registran, se escriben en el trabajo de generación y se envían como eventos SSE. El grafo transita al nodo `handle_error`.

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

### 6.2 Gestión de errores de la API del LLM con reintentos

Las llamadas al LLM usan tenacity para la lógica de reintentos con retroceso exponencial. Esto gestiona errores transitorios de la API (límites de tasa, tiempos de espera, errores de servidor) sin hacer fallar todo el pipeline.

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

### 6.3 Recuperación de errores de parseo de JSON

Las respuestas del LLM que se esperan en formato JSON pueden contener JSON malformado. El pipeline usa una estrategia de recuperación en dos etapas:

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

### 6.4 Enrutado de fallos de calidad

La revisión de calidad puede tener tres resultados, enrutados por `route_after_quality_review`:

| Resultado | Condición | Acción |
|---------|-----------|--------|
| **Pass (aprobado)** | `score >= 0.8`, sin problemas críticos | Pasa a la revisión final del administrador |
| **Refine (refinar)** | Problemas críticos o graves, `refinement_count < 2` | Se envía al refinador de contenido, y luego se revisa de nuevo |
| **Fail (fallo)** | `refinement_count >= 2` y aún hay problemas críticos | Pasa al gestor de errores — se notifica al administrador de que la generación no pudo alcanzar los estándares de calidad |

Tras 2 ciclos de refinamiento sin aprobar, el pipeline no entra en bucle infinito. Envía el contenido al administrador con el informe de revisión adjunto, dejando que decida si lo acepta, lo corrige manualmente o lo rechaza.

### 6.5 Nodo gestor de errores

El gestor de errores terminal actualiza el trabajo de generación en PostgreSQL y envía un evento SSE final.

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

## 7. Interacción con el administrador

### 7.1 Dos puntos de control obligatorios

El pipeline tiene dos puntos `interrupt_before` en los que se detiene y espera la entrada del administrador:

| Punto de control | Cuándo | Qué revisa el administrador | Qué puede hacer el administrador |
|------------|------|---------------------|-------------------|
| **Revisión de estructura** | Después de `design_structure`, antes de `generate_modules` | Esquema del curso: título, resultado, estructura de módulos, plan de lecciones | Aprobar, editar en línea, rechazar |
| **Revisión final** | Después de que `review_quality` aprueba, antes de `publish` | Contenido generado completo + informe de calidad | Aprobar, editar en línea, rechazar, pedir refinamiento |

El grafo está diseñado para que **ningún contenido llegue a los aprendices sin la aprobación explícita del administrador**. El punto de control de estructura evita perder tiempo de generación en un esquema deficiente. El punto de control final evita publicar contenido defectuoso.

### 7.2 Cómo funcionan las interrupciones

Cuando LangGraph llega a un nodo `interrupt_before`:

1. El estado del grafo se serializa en PostgreSQL (tabla `langgraph_checkpoints`).
2. Se actualiza el estado del trabajo de generación (por ejemplo, `structuring` -> `awaiting_review`).
3. Se envía un evento SSE: `{event: "awaiting_review", data: {checkpoint: "structure"}}`.
4. El grafo se detiene. No se ejecuta ningún nodo más.
5. El administrador revisa a su propio ritmo a través de la API.
6. Cuando el administrador envía su revisión, el manejador de la API llama a `resume_generation()`, que actualiza el estado y reanuda el grafo desde el punto interrumpido.

### 7.3 Endpoints de la API de revisión

Estos endpoints forman parte de la API de trabajos de generación (ver [backend-api.md](backend-api.md), sección 4.2):

```
GET  /api/v1/generation-jobs/{id}/review
POST /api/v1/generation-jobs/{id}/review
PUT  /api/v1/generation-jobs/{id}/content
POST /api/v1/generation-jobs/{id}/regenerate-module/{module_index}
GET  /api/v1/generation-jobs/{id}/progress (SSE)
```

#### GET /generation-jobs/{id}/review

Devuelve el estado actual para revisión. La respuesta depende de qué punto de control esté activo:

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

Envía la decisión de revisión del administrador:

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

**Manejador del backend:**

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

API de edición en línea. El administrador puede modificar directamente partes concretas del contenido generado sin pasar por el flujo completo de revisión:

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

Regenera un único módulo sin volver a ejecutar todo el pipeline. Útil cuando el administrador está mayormente satisfecho pero un módulo necesita rehacerse por completo.

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

### 7.4 SSE de progreso

El administrador ve el progreso en tiempo real a través de un endpoint SSE dedicado:

```
GET /api/v1/generation-jobs/{id}/progress
Content-Type: text/event-stream
```

**Tipos de evento:**

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

**Implementación de SSE:**

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

**Publicación de SSE (usada por los nodos del grafo):**

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

## 8. Nodo de publicación

El nodo final persiste el contenido generado en la base de datos, creando las filas reales de curso, módulos, lecciones, ejercicios y manual.

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

## 9. Ciclo de vida del trabajo de generación

Integración con la tabla `generation_jobs` de [data-model.md](data-model.md):

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

El enum `generation_step` del modelo de datos se corresponde con estas transiciones:

| Valor del enum | Estado del grafo |
|------------|-------------|
| `pending` | Trabajo creado, grafo aún no iniciado |
| `extracting` | `prepare_context` o `extract_themes` en ejecución |
| `structuring` | `design_structure` en ejecución o esperando revisión de estructura |
| `generating` | `generate_modules` o `generate_manual` en ejecución |
| `reviewing` | `review_quality` o `refine_content` en ejecución, o esperando revisión final |
| `published` | `publish` completado con éxito |
| `failed` | Algún nodo falló tras los reintentos, o el administrador rechazó |

---

## 10. Configuración

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

## 11. Decisiones clave de diseño

| Decisión | Justificación |
|----------|-----------|
| **LangGraph en lugar de asyncio puro** | Una máquina de estados con checkpointing, humano en el bucle y enrutado de aristas es exactamente lo que ofrece LangGraph. Construir esto desde cero supondría un trabajo considerable y no diferenciador. |
| **Checkpointing en PostgreSQL** | La misma base de datos para todo (modelo de datos, sesiones, checkpoints). Sin dependencia de Redis. Sobrevive a los reinicios del servidor. |
| **2 puntos de control humanos, no 0 ni 1** | La revisión de estructura evita malgastar generación en un esquema deficiente. La revisión final detecta problemas de calidad que el revisor automático pasó por alto. Ambos son obligatorios porque el administrador es responsable de lo que aprenden los empleados. |
| **Paralelismo acotado por semáforo** | 3 llamadas concurrentes equilibran el rendimiento con los límites de tasa de la API. Configurable por despliegue. |
| **Revisor de calidad independiente** | El revisor carga los documentos fuente de forma independiente, nunca ve el contexto del generador. Las tasas de error se multiplican con verificación independiente (según la investigación de [architecture.md](architecture.md)). |
| **Máximo 2 ciclos de refinamiento** | Evita bucles infinitos. Tras 2 ciclos fallidos, el contenido pasa al administrador junto con el informe de revisión — una persona debe decidir. |
| **Compartimentación basada en fragmentos** | Los generadores de módulo solo ven sus fragmentos relevantes. Reduce el ruido, mejora la precisión, refuerza el principio de necesidad de conocer de [architecture.md](architecture.md). |
| **SSE para el progreso, no sondeo** | La infraestructura de SSE ya existe para el chat del tutor. El sondeo generaría una carga innecesaria en la API. |
| **La publicación crea un borrador, no lo publica** | El nodo `publish` escribe en la BD con `status=draft`. El administrador publica el curso por separado mediante `POST /courses/{id}/publish` tras su revisión final. Esto separa "generación completada" de "visible para los empleados". |
| **Regeneración de un solo módulo** | El administrador no debería tener que regenerar un curso entero porque un módulo sea deficiente. La regeneración selectiva ahorra tiempo y coste de LLM. |
| **El manual se genera después del curso** | El manual usa el esquema del curso para la alineación estructural pero sigue la organización del documento fuente. Generarlo después del curso garantiza coherencia. |

---

## 12. Regeneración adaptativa (Fase 2+)

El pipeline descrito arriba genera contenido **una sola vez**. La Fase 2 introduce regeneración basada en datos, a partir del rendimiento real de los empleados.

### 12.1 El problema

Un curso se genera a partir de documentos por agentes que nunca han visto a un empleado real batallar con el contenido. La primera versión es una estimación razonada. Después de que 50 o más empleados hagan el curso, el sistema tiene datos reales sobre qué funciona y qué no.

### 12.2 Señales

| Señal | Fuente | Umbral |
|--------|--------|-----------|
| Tasa de aprobados por módulo | `exercise_attempts` JOIN `lessons` JOIN `modules` | < 60% de aprobados en 10+ intentos |
| Intentos medios por ejercicio | `exercise_attempts` GROUP BY `exercise_id` | > 2,5 intentos de media |
| Volumen de preguntas al tutor | `chat_messages` filtrado por `course_id` | > 5 preguntas sobre el mismo tema en 7 días |
| Abandono de finalización | `enrollments` con status = 'abandoned' en un módulo concreto | > 30% abandona en el mismo módulo |
| Tiempo de finalización | delta de `exercise_attempts.created_at` | 2 veces más que la mediana para el mismo curso |

### 12.3 Flujo de regeneración

Cuando se superan los umbrales:

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

La regeneración usa el **mismo pipeline** que la generación inicial (Sección 2), pero con contexto adicional:

- El informe de calidad del módulo que falló (qué salió mal)
- Preguntas reales de empleados en el chat del tutor (qué generó confusión)
- Datos de intentos de ejercicios (qué preguntas concretas se fallaron)

Esto proporciona a los agentes de regeneración información que los agentes de generación inicial no tenían.

### 12.4 Notas de implementación

- **No se necesitan cambios de esquema.** Todas las señales provienen de tablas ya existentes: `exercise_attempts`, `chat_messages`, `enrollments`, `lessons`, `modules`.
- **La regeneración de un solo módulo** ya existe (Sección 7.3). El flujo adaptativo la reutiliza.
- **El seguimiento de versiones** en los módulos (añadir la columna `version` a la tabla `modules`) permite al sistema rastrear en qué versión está cada empleado.
- **Opt-in para el MVP.** La regeneración adaptativa está desactivada por defecto. Los administradores la activan por curso cuando tienen datos suficientes.
