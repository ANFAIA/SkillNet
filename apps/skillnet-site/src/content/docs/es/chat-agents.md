---
title: "Chat y agentes"
order: 6
section: "core"
---

# Agentes de Tutoria y Chat

> **Estado: v1.** Arquitectura de agentes LangGraph tanto para el tutor de empleados como para el asistente de administracion. Se apoya en [architecture.md](architecture.md) (equipos de agentes, streaming SSE), [rag-retrieval.md](rag-retrieval.md) (estrategias de recuperacion, PageIndex, ensamblado de contexto), [backend-api.md](backend-api.md) (endpoints de chat, inyeccion de dependencias) y [screens.md](screens.md) (Chat Tutor, Admin Chat).

---

## Vision general

SkillNet tiene dos agentes de chat con propositos distintos, estrategias de recuperacion distintas y conjuntos de herramientas distintos, pero infraestructura compartida.

| Agente | Usuario | Proposito | Recuperacion | Herramientas |
|-------|------|---------|-----------|-------|
| **Tutor de empleados** | empleado | Responder preguntas fundamentadas en el conocimiento de la empresa, guiar el aprendizaje | RAG (PageIndex + semantica + fallback acotado) | Ninguna (solo recuperacion + generacion) |
| **Asistente de administracion** | admin | Consultas operativas, ejecutar acciones de la plataforma mediante lenguaje natural | DB directa via llamadas a herramientas | 13 herramientas (lectura + escritura) |

Ambos agentes son maquinas de estados LangGraph que transmiten respuestas via SSE. Ambos comparten el mismo `LLMClient`, la infraestructura de sesiones de base de datos y las tablas de persistencia de chat.

```
Employee ──→ POST /api/v1/chat ──→ TutorAgent (LangGraph) ──→ SSE stream
Admin    ──→ POST /api/v1/chat/admin ──→ AdminAgent (LangGraph) ──→ SSE stream
```

---

## 1. Agente Tutor de empleados

### 1.1 Arquitectura del grafo

El tutor es un `StateGraph` de LangGraph con cinco nodos y aristas condicionales. Sin llamadas a herramientas — el agente recupera contexto, genera una respuesta y la postprocesa.

```
                    ┌─────────────────┐
                    │ classify_intent │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┬──────────────┐
              │              │              │              │
              v              v              v              v
        ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐
        │ retrieve  │  │ retrieve  │  │ retrieve │  │ (skip    │
        │ _course   │  │ _semantic │  │ _progress│  │  retrieval)│
        │ _context  │  │           │  │          │  │          │
        └─────┬─────┘  └─────┬─────┘  └─────┬────┘  └─────┬────┘
              │              │              │              │
              └──────────────┴──────────────┴──────────────┘
                             │
                             v
                    ┌─────────────────┐
                    │generate_response│
                    │  (streaming)    │
                    └────────┬────────┘
                             │
                             v
                    ┌─────────────────┐
                    │  post_process   │
                    └─────────────────┘
```

### 1.2 TutorState

Todo el estado fluye a traves de un unico `TypedDict`. LangGraph lo pasa entre nodos — cada nodo lee lo que necesita y escribe sus salidas.

```python
# src/agents/tutor_agent.py

from typing import TypedDict, Literal
from uuid import UUID
from dataclasses import dataclass

@dataclass
class Citation:
    """Structured citation extracted from the LLM response."""
    index: int              # [1], [2], etc.
    document_title: str
    section: str
    page: int | None
    source_type: str        # "lesson", "document_chunk", "manual"
    source_id: UUID | None  # lesson_id or chunk_id for linking

@dataclass
class ConversationTurn:
    """A single turn in the conversation history."""
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] | None = None

class TutorState(TypedDict):
    # Input
    user_id: UUID
    org_id: UUID
    message: str
    session_id: UUID

    # Context from the request
    course_id: UUID | None          # Set if user is inside a course
    lesson_id: UUID | None          # Set if user is on a specific lesson
    enrollment_id: UUID | None

    # Classification
    intent: Literal[
        "in_course",     # Question about current course content
        "cross_course",  # Question spanning multiple courses or general knowledge
        "progress",      # Question about own progress, scores, deadlines
        "chitchat",      # Greeting, small talk, off-topic but harmless
        "off_topic",     # Completely unrelated to work/learning
    ]

    # Retrieval results
    retrieved_context: str          # Assembled context block for the prompt
    retrieval_source: str           # "pageindex", "semantic", "scoped_fallback", "db", "none"
    retrieval_chunks: list[dict]    # Raw chunk data for citation extraction

    # Conversation memory
    history: list[ConversationTurn] # Last N turns (raw) + older summary
    history_summary: str | None     # Summary of older turns

    # Generation
    system_prompt: str
    response: str                   # Full generated response
    citations: list[Citation]
    suggestions: list[str]          # Follow-up prompt suggestions

    # Metadata
    tokens_used: int
    retrieval_latency_ms: int
    generation_latency_ms: int
```

### 1.3 Implementacion de los nodos

#### classify_intent

El primer nodo clasifica que esta preguntando el usuario. Esto determina que ruta de recuperacion se sigue. La clasificacion es una unica llamada corta al LLM (~30 tokens de salida).

```python
# src/agents/nodes/classify_intent.py

CLASSIFY_PROMPT = """You are an intent classifier for a corporate learning platform.

The employee is chatting with a tutor. Classify their message into exactly one category:

- in_course: question about the content of the course they are currently taking
- cross_course: question about company knowledge that may span multiple topics
- progress: question about their own progress, scores, deadlines, or skills
- chitchat: greeting, thanks, small talk, or casual conversation
- off_topic: completely unrelated to work or learning (politics, sports, etc.)

Current context:
- Employee is {in_course_status}
- Course: {course_title}
- Current lesson: {lesson_title}

Employee message: "{message}"

Reply with ONLY the category name, nothing else."""

async def classify_intent(state: TutorState, llm: AsyncOpenAI, db: AsyncSession) -> dict:
    # Build context description
    if state["course_id"]:
        course = await db.get(Course, state["course_id"])
        lesson = await db.get(Lesson, state["lesson_id"]) if state["lesson_id"] else None
        in_course_status = "inside a course"
        course_title = course.title if course else "Unknown"
        lesson_title = lesson.title if lesson else "None"
    else:
        in_course_status = "not inside any course (general chat)"
        course_title = "None"
        lesson_title = "None"

    prompt = CLASSIFY_PROMPT.format(
        in_course_status=in_course_status,
        course_title=course_title,
        lesson_title=lesson_title,
        message=state["message"],
    )

    response = await llm.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=20,
        temperature=0,
    )

    raw = response.choices[0].message.content.strip().lower()

    # Validate classification
    valid_intents = {"in_course", "cross_course", "progress", "chitchat", "off_topic"}
    intent = raw if raw in valid_intents else "cross_course"  # Default to cross_course

    # Heuristic overrides (avoid LLM call cost for obvious cases)
    msg_lower = state["message"].strip().lower()
    if msg_lower in {"hola", "hi", "hello", "gracias", "thanks", "adios", "bye"}:
        intent = "chitchat"
    elif any(w in msg_lower for w in ["mi progreso", "my progress", "mi nota", "mi puntaje",
                                       "cuanto llevo", "fecha limite", "deadline"]):
        intent = "progress"

    return {"intent": intent}
```

#### retrieve_course_context (patron PageIndex via SQL)

Cuando la intencion es `in_course`, el agente usa el patron PageIndex: obtiene la estructura del curso (titulos de modulo + resumenes), deja que el LLM seleccione el/los modulo(s) relevante(s), y luego obtiene el contenido completo de la leccion. Dos consultas SQL + una llamada corta al LLM. No hace falta embeddings.

```python
# src/agents/nodes/retrieve_course_context.py

async def retrieve_course_context(state: TutorState, llm: AsyncOpenAI, db: AsyncSession) -> dict:
    """
    PageIndex retrieval for in-course questions.
    
    Step 1: Fetch module titles + summaries (the "index page")
    Step 2: LLM picks which module(s) contain the answer
    Step 3: Fetch full lesson content from selected module(s)
    Step 4: If current lesson is set, always include it as priority context
    """
    import time
    start = time.monotonic()

    course_id = state["course_id"]

    # Step 1: Get the course tree (cheap SQL)
    modules = (await db.execute(
        text("""
            SELECT id, title, summary, position
            FROM modules
            WHERE course_id = :course_id
            ORDER BY position
        """),
        {"course_id": course_id}
    )).fetchall()

    if not modules:
        return {
            "retrieved_context": "",
            "retrieval_source": "pageindex",
            "retrieval_chunks": [],
            "retrieval_latency_ms": int((time.monotonic() - start) * 1000),
        }

    tree = "\n".join(
        f"- Modulo {m.position}: {m.title} — {m.summary or '(sin resumen)'}"
        for m in modules
    )

    # Step 2: LLM selects relevant module(s)
    selection_prompt = f"""Given this course structure:
{tree}

The employee asks: "{state['message']}"

Which module number(s) contain the answer? Reply with ONLY the number(s), comma-separated.
If unsure, reply "all"."""

    selection = await llm.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": selection_prompt}],
        max_tokens=20,
        temperature=0,
    )

    selected_text = selection.choices[0].message.content.strip()
    selected_module_ids = _parse_module_selection(selected_text, modules)

    # Step 3: Fetch lesson content from selected modules
    lessons = (await db.execute(
        text("""
            SELECT l.id, l.title, l.content, m.title AS module_title, m.position AS module_pos
            FROM lessons l
            JOIN modules m ON m.id = l.module_id
            WHERE l.module_id = ANY(:module_ids)
            ORDER BY m.position, l.position
        """),
        {"module_ids": selected_module_ids}
    )).fetchall()

    # Step 4: If current lesson is set, ensure it is included (even if LLM didn't select its module)
    current_lesson_included = False
    if state["lesson_id"]:
        for l in lessons:
            if l.id == state["lesson_id"]:
                current_lesson_included = True
                break

        if not current_lesson_included:
            current = (await db.execute(
                text("SELECT id, title, content FROM lessons WHERE id = :lid"),
                {"lid": state["lesson_id"]}
            )).fetchone()
            if current:
                lessons = [current] + list(lessons)

    # Build context block with citation markers
    chunks = []
    context_parts = []
    for i, lesson in enumerate(lessons, 1):
        module_title = getattr(lesson, "module_title", "")
        citation_label = f"[Fuente {i}: {module_title} > {lesson.title}]"
        context_parts.append(f"{citation_label}\n{lesson.content}")
        chunks.append({
            "index": i,
            "document_title": module_title,
            "section": lesson.title,
            "page": None,
            "source_type": "lesson",
            "source_id": str(lesson.id),
        })

    elapsed = int((time.monotonic() - start) * 1000)

    return {
        "retrieved_context": "\n\n---\n\n".join(context_parts),
        "retrieval_source": "pageindex",
        "retrieval_chunks": chunks,
        "retrieval_latency_ms": elapsed,
    }


def _parse_module_selection(text: str, modules) -> list:
    """Parse LLM output like '1, 3' or 'all' into module IDs."""
    if "all" in text.lower():
        return [m.id for m in modules]

    selected = []
    for part in text.replace(",", " ").split():
        try:
            pos = int(part.strip())
            for m in modules:
                if m.position == pos:
                    selected.append(m.id)
        except ValueError:
            continue

    # Fallback: if nothing parsed, return all
    return selected if selected else [m.id for m in modules]
```

#### retrieve_semantic (similitud coseno con pgvector)

Para la intencion `cross_course` — el usuario pregunta algo que podria abarcar varios cursos o proceder de documentos fuente en lugar de contenido de curso estructurado.

```python
# src/agents/nodes/retrieve_semantic.py

async def retrieve_semantic(state: TutorState, db: AsyncSession, embedder) -> dict:
    """
    Semantic RAG for cross-course or general knowledge questions.
    
    Uses pgvector cosine similarity on document_chunks.
    Over-retrieves (top 10), deduplicates, orders by document position,
    returns top 5 for the prompt.
    """
    import time
    start = time.monotonic()

    # Embed the query
    query_embedding = await embedder.embed_query(state["message"])

    # Semantic search across all org documents
    results = (await db.execute(
        text("""
            SELECT dc.id, dc.content, dc.metadata, d.title AS doc_title,
                   1 - (dc.embedding <=> :embedding) AS similarity
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.org_id = :org_id
              AND 1 - (dc.embedding <=> :embedding) > 0.3
            ORDER BY dc.embedding <=> :embedding
            LIMIT 10
        """),
        {"embedding": query_embedding, "org_id": state["org_id"]}
    )).fetchall()

    if not results:
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "retrieved_context": "",
            "retrieval_source": "semantic",
            "retrieval_chunks": [],
            "retrieval_latency_ms": elapsed,
        }

    # Deduplicate by content overlap
    deduplicated = _deduplicate(results, threshold=0.7)

    # Order by document position (not relevance score)
    ordered = sorted(deduplicated, key=lambda r: (
        str(r.doc_title),
        r.metadata.get("position", 0),
    ))

    # Take top 5 after deduplication
    top = ordered[:5]

    # Build context block
    chunks = []
    context_parts = []
    for i, row in enumerate(top, 1):
        heading = row.metadata.get("heading", "")
        page = row.metadata.get("page_start")
        citation_label = f"[Fuente {i}: {row.doc_title}"
        if heading:
            citation_label += f" > {heading}"
        if page:
            citation_label += f", pag. {page}"
        citation_label += "]"

        context_parts.append(f"{citation_label}\n{row.content}")
        chunks.append({
            "index": i,
            "document_title": row.doc_title,
            "section": heading,
            "page": page,
            "source_type": "document_chunk",
            "source_id": str(row.id),
        })

    elapsed = int((time.monotonic() - start) * 1000)

    return {
        "retrieved_context": "\n\n---\n\n".join(context_parts),
        "retrieval_source": "semantic",
        "retrieval_chunks": chunks,
        "retrieval_latency_ms": elapsed,
    }


def _deduplicate(results, threshold: float = 0.7):
    """Remove near-duplicate chunks by Jaccard word overlap."""
    selected = []
    for row in results:
        words = set(row.content.lower().split())
        is_dup = False
        for existing in selected:
            existing_words = set(existing.content.lower().split())
            if not words or not existing_words:
                continue
            overlap = len(words & existing_words) / len(words | existing_words)
            if overlap > threshold:
                is_dup = True
                break
        if not is_dup:
            selected.append(row)
    return selected
```

#### retrieve_progress (DB directa)

Para la intencion `progress` — el usuario pregunta sobre sus propias notas, plazos o niveles de habilidad. No hace falta RAG. Consultas SQL directas.

```python
# src/agents/nodes/retrieve_progress.py

async def retrieve_progress(state: TutorState, db: AsyncSession) -> dict:
    """
    Fetch user progress data directly from the database.
    No RAG needed — the answer comes from structured data.
    """
    import time
    start = time.monotonic()

    user_id = state["user_id"]

    # Enrollments with progress
    enrollments = (await db.execute(
        text("""
            SELECT c.title, e.status, e.deadline, e.score, e.started_at,
                   COUNT(DISTINCT m.id) AS total_modules,
                   COUNT(DISTINCT CASE WHEN EXISTS (
                       SELECT 1 FROM exercise_attempts ea
                       JOIN exercises ex ON ex.id = ea.exercise_id
                       JOIN lessons l ON l.id = ex.lesson_id
                       WHERE l.module_id = m.id AND ea.user_id = :user_id AND ea.passed = true
                   ) THEN m.id END) AS completed_modules
            FROM enrollments e
            JOIN courses c ON c.id = e.course_id
            LEFT JOIN modules m ON m.course_id = c.id
            WHERE e.user_id = :user_id
            GROUP BY c.title, e.status, e.deadline, e.score, e.started_at
        """),
        {"user_id": user_id}
    )).fetchall()

    # Skill levels
    skills = (await db.execute(
        text("""
            SELECT s.name, us.level, sc.name AS category
            FROM user_skills us
            JOIN skills s ON s.id = us.skill_id
            LEFT JOIN skill_categories sc ON sc.id = s.category_id
            WHERE us.user_id = :user_id
            ORDER BY sc.name, s.name
        """),
        {"user_id": user_id}
    )).fetchall()

    # Spaced repetition stats
    reviews_due = (await db.execute(
        text("""
            SELECT COUNT(*) FROM spaced_repetition
            WHERE user_id = :user_id AND next_review_at <= now()
        """),
        {"user_id": user_id}
    )).scalar_one()

    # Build structured context for the LLM
    context_parts = []

    if enrollments:
        context_parts.append("[Datos: Cursos del empleado]")
        for e in enrollments:
            progress = f"{e.completed_modules}/{e.total_modules} modulos"
            deadline = f", fecha limite: {e.deadline}" if e.deadline else ""
            score = f", nota: {e.score:.0%}" if e.score is not None else ""
            context_parts.append(f"- {e.title}: {e.status} ({progress}{deadline}{score})")

    if skills:
        context_parts.append("\n[Datos: Habilidades del empleado]")
        for s in skills:
            cat = f"({s.category})" if s.category else ""
            context_parts.append(f"- {s.name} {cat}: nivel {s.level}")

    if reviews_due > 0:
        context_parts.append(f"\n[Datos: Repasos pendientes]\n- {reviews_due} ejercicios pendientes de repaso")

    elapsed = int((time.monotonic() - start) * 1000)

    return {
        "retrieved_context": "\n".join(context_parts),
        "retrieval_source": "db",
        "retrieval_chunks": [],  # No document chunks — structured data
        "retrieval_latency_ms": elapsed,
    }
```

#### generate_response (streaming)

El nodo central de generacion. Ensambla el system prompt, el historial de conversacion, el contexto recuperado y el mensaje del usuario. Transmite tokens via SSE.

```python
# src/agents/nodes/generate_response.py

TUTOR_SYSTEM_PROMPT = """You are a corporate tutor for {org_name}. You help employees learn and answer their questions based on company documentation.

Rules:
1. Answer ONLY based on the provided context. If the information is not in the context, say so clearly.
2. Cite your sources using [1], [2], etc. corresponding to the [Fuente N] markers in the context.
3. Be concise but complete. Use bullet points for lists.
4. Speak in the same language as the employee.
5. If the question is about the employee's progress, present the data clearly with encouragement.
6. For chitchat (greetings, thanks), respond briefly and warmly, then suggest a learning-related follow-up.
7. For off-topic questions, politely redirect to learning topics.
8. Never invent information. Never reference documents you were not given."""

async def generate_response(
    state: TutorState,
    llm: AsyncOpenAI,
    sse_queue: asyncio.Queue,
) -> dict:
    """
    Generate the tutor response with streaming.
    
    Tokens are pushed to sse_queue as they arrive.
    The full response is also accumulated for post-processing.
    """
    import time
    start = time.monotonic()

    # Build messages array
    messages = []

    # 1. System prompt
    messages.append({
        "role": "system",
        "content": state["system_prompt"],
    })

    # 2. Conversation history (already trimmed by memory manager)
    if state.get("history_summary"):
        messages.append({
            "role": "system",
            "content": f"Summary of earlier conversation:\n{state['history_summary']}",
        })

    for turn in state.get("history", []):
        messages.append({
            "role": turn.role,
            "content": turn.content,
        })

    # 3. Current message with context
    if state["retrieved_context"]:
        user_content = f"""Context from company documentation (use ONLY this to answer):

{state['retrieved_context']}

---

Employee question: {state['message']}

Instructions:
- Answer based ONLY on the context above.
- Cite sources using [1], [2], etc. matching the [Fuente N] labels.
- If the information is not in the context, say "No tengo informacion sobre esto en los documentos disponibles."
- Respond in the same language as the question."""
    else:
        # No context (chitchat, off-topic, or empty retrieval)
        user_content = state["message"]

    messages.append({"role": "user", "content": user_content})

    # 4. Stream the response
    full_response = []

    stream = await llm.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        max_tokens=2000,
        temperature=0.3,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            full_response.append(delta.content)
            # Push token to SSE queue
            await sse_queue.put({
                "event": "token",
                "data": {"content": delta.content},
            })

    response_text = "".join(full_response)
    elapsed = int((time.monotonic() - start) * 1000)

    # Count tokens (approximate)
    total_input = sum(count_tokens(m["content"]) for m in messages)
    total_output = count_tokens(response_text)

    return {
        "response": response_text,
        "generation_latency_ms": elapsed,
        "tokens_used": total_input + total_output,
    }
```

> **SUSTITUIDO (2026-07-27) — la negativa de arriba ha desaparecido.** La instruccion *"If the
> information is not in the context, say 'No tengo informacion sobre esto en los
> documentos disponibles.'"* se llego a desplegar, y entonces respondia **todas** las preguntas
> en la organizacion de demo: los documentos de la semilla son lo bastante pequenos como para
> guardar su texto entero en `documents.full_text` y no tener ningun `document_chunks`, asi que
> la recuperacion siempre estaba vacia y el tutor siempre se negaba, con la respuesta sentada en
> una columna que nunca leia.
>
> Lo que la sustituye es una **escalera de fundamentacion** en `src/services/retrieval.py` —
> fragmentos recuperados, luego el documento completo de un curso en el que el aprendiz esta
> matriculado, luego conocimiento general — y una persona en `src/llm/prompts/tutor.py` que se
> mantiene en los tres escalones. El peldano lo decide el servidor, se anuncia como un evento SSE
> `grounding` y se persiste en `chat_messages.metadata`: si una respuesta es un pasaje citado, un
> documento entero o el conocimiento propio del modelo es una propiedad del sistema, no una frase
> que se le pidiera escribir al modelo. No existe ningun estado en el que el tutor se niegue; el
> peldano mas bajo responde y dice en voz alta que no es material de la empresa.

#### post_process (citas, sugerencias)

Extrae las citas en linea del texto de la respuesta y las mapea a objetos `Citation` estructurados. Tambien genera sugerencias de seguimiento.

```python
# src/agents/nodes/post_process.py

import re

async def post_process(state: TutorState, sse_queue: asyncio.Queue) -> dict:
    """
    Post-process the generated response:
    1. Extract [1], [2], etc. citations and map to source metadata
    2. Generate follow-up suggestions based on context
    3. Send final SSE events (citations, suggestions, done)
    """
    response = state["response"]
    chunks = state["retrieval_chunks"]

    # 1. Extract citation markers
    citation_pattern = re.compile(r'\[(\d+)\]')
    cited_indices = set(int(m) for m in citation_pattern.findall(response))

    citations = []
    for chunk in chunks:
        if chunk["index"] in cited_indices:
            citations.append(Citation(
                index=chunk["index"],
                document_title=chunk["document_title"],
                section=chunk["section"],
                page=chunk.get("page"),
                source_type=chunk["source_type"],
                source_id=UUID(chunk["source_id"]) if chunk.get("source_id") else None,
            ))

    # 2. Generate follow-up suggestions
    suggestions = _generate_suggestions(state)

    # 3. Send SSE events
    if citations:
        await sse_queue.put({
            "event": "citations",
            "data": {
                "citations": [
                    {
                        "index": c.index,
                        "document": c.document_title,
                        "section": c.section,
                        "page": c.page,
                    }
                    for c in citations
                ]
            },
        })

    if suggestions:
        await sse_queue.put({
            "event": "suggestions",
            "data": {"suggestions": suggestions},
        })

    await sse_queue.put({
        "event": "done",
        "data": {
            "message_id": str(uuid4()),
            "tokens_used": state["tokens_used"],
            "retrieval_source": state["retrieval_source"],
            "retrieval_latency_ms": state["retrieval_latency_ms"],
            "generation_latency_ms": state["generation_latency_ms"],
        },
    })

    return {
        "citations": citations,
        "suggestions": suggestions,
    }


def _generate_suggestions(state: TutorState) -> list[str]:
    """
    Generate follow-up prompt suggestions based on context.
    Heuristic, no LLM call — keeps post-processing fast.
    """
    suggestions = []
    intent = state["intent"]

    if intent == "in_course" and state["course_id"]:
        suggestions.append("Explicame esto con un ejemplo practico")
        suggestions.append("Que ejercicios hay sobre este tema?")

    elif intent == "cross_course":
        suggestions.append("Hay algun curso que cubra este tema?")
        suggestions.append("Donde puedo encontrar mas informacion sobre esto?")

    elif intent == "progress":
        suggestions.append("Que deberia repasar hoy?")
        suggestions.append("Cual es mi siguiente paso?")

    elif intent == "chitchat":
        suggestions.append("Que temas puedo aprender hoy?")
        suggestions.append("Muestrame mi progreso")

    return suggestions[:3]
```

### 1.4 Ensamblado del grafo

```python
# src/agents/tutor_agent.py

from langgraph.graph import StateGraph, END

def build_tutor_graph(llm, db, embedder, sse_queue) -> StateGraph:
    """Build the LangGraph state machine for the employee tutor."""

    graph = StateGraph(TutorState)

    # Bind dependencies to node functions via closures
    graph.add_node("classify_intent",
        lambda state: classify_intent(state, llm, db))

    graph.add_node("retrieve_course_context",
        lambda state: retrieve_course_context(state, llm, db))

    graph.add_node("retrieve_semantic",
        lambda state: retrieve_semantic(state, db, embedder))

    graph.add_node("retrieve_progress",
        lambda state: retrieve_progress(state, db))

    graph.add_node("skip_retrieval",
        lambda state: {
            "retrieved_context": "",
            "retrieval_source": "none",
            "retrieval_chunks": [],
            "retrieval_latency_ms": 0,
        })

    graph.add_node("generate_response",
        lambda state: generate_response(state, llm, sse_queue))

    graph.add_node("post_process",
        lambda state: post_process(state, sse_queue))

    # Entry point
    graph.set_entry_point("classify_intent")

    # Conditional edges based on intent
    graph.add_conditional_edges(
        "classify_intent",
        _route_by_intent,
        {
            "retrieve_course_context": "retrieve_course_context",
            "retrieve_semantic": "retrieve_semantic",
            "retrieve_progress": "retrieve_progress",
            "skip_retrieval": "skip_retrieval",
        },
    )

    # All retrieval paths converge to generation
    graph.add_edge("retrieve_course_context", "generate_response")
    graph.add_edge("retrieve_semantic", "generate_response")
    graph.add_edge("retrieve_progress", "generate_response")
    graph.add_edge("skip_retrieval", "generate_response")

    # Generation -> post-processing -> end
    graph.add_edge("generate_response", "post_process")
    graph.add_edge("post_process", END)

    return graph.compile()


def _route_by_intent(state: TutorState) -> str:
    """Route to the appropriate retrieval node based on classified intent."""
    intent = state["intent"]

    if intent == "in_course" and state["course_id"]:
        return "retrieve_course_context"
    elif intent == "in_course" and not state["course_id"]:
        # User asked an in-course question but isn't in a course — fall back to semantic
        return "retrieve_semantic"
    elif intent == "cross_course":
        return "retrieve_semantic"
    elif intent == "progress":
        return "retrieve_progress"
    else:
        # chitchat, off_topic, or follow-ups that don't need context
        return "skip_retrieval"
```

### 1.5 Fallback de RAG acotado

Cuando la recuperacion PageIndex devuelve contenido insuficiente (lecciones demasiado cortas o la respuesta no esta en los modulos seleccionados), el sistema recurre a busqueda semantica acotada al documento fuente del curso.

```python
# src/agents/nodes/retrieve_course_context.py (extended)

async def retrieve_course_context_with_fallback(
    state: TutorState, llm: AsyncOpenAI, db: AsyncSession, embedder,
) -> dict:
    """
    PageIndex retrieval with scoped RAG fallback.
    
    If lesson content is too thin (< 200 tokens total), fall back to
    semantic search on the course's source document chunks.
    """
    result = await retrieve_course_context(state, llm, db)

    # Check if retrieved context is sufficient
    context_tokens = count_tokens(result["retrieved_context"])

    if context_tokens < 200 and state["course_id"]:
        # Fallback: semantic search scoped to the course's source document
        course = await db.get(Course, state["course_id"])
        if course and course.source_document_id:
            query_embedding = await embedder.embed_query(state["message"])

            fallback_results = (await db.execute(
                text("""
                    SELECT dc.id, dc.content, dc.metadata, d.title AS doc_title,
                           1 - (dc.embedding <=> :embedding) AS similarity
                    FROM document_chunks dc
                    JOIN documents d ON d.id = dc.document_id
                    WHERE dc.document_id = :doc_id
                      AND 1 - (dc.embedding <=> :embedding) > 0.3
                    ORDER BY dc.embedding <=> :embedding
                    LIMIT 5
                """),
                {"embedding": query_embedding, "doc_id": course.source_document_id}
            )).fetchall()

            if fallback_results:
                # Append fallback results to existing context
                existing_count = len(result["retrieval_chunks"])
                for i, row in enumerate(fallback_results, existing_count + 1):
                    heading = row.metadata.get("heading", "")
                    page = row.metadata.get("page_start")
                    label = f"[Fuente {i}: {row.doc_title}"
                    if heading:
                        label += f" > {heading}"
                    if page:
                        label += f", pag. {page}"
                    label += "]"

                    result["retrieved_context"] += f"\n\n---\n\n{label}\n{row.content}"
                    result["retrieval_chunks"].append({
                        "index": i,
                        "document_title": row.doc_title,
                        "section": heading,
                        "page": page,
                        "source_type": "document_chunk",
                        "source_id": str(row.id),
                    })

                result["retrieval_source"] = "scoped_fallback"

    return result
```

---

## 2. Estrategia de recuperacion RAG

### 2.1 Arbol de decision

El agente tutor sigue un arbol de decision para determinar como recuperar el contexto. El arbol se evalua en el nodo `classify_intent` y se enruta mediante aristas condicionales.

```
                        Employee sends message
                                |
                                v
                    ┌───── classify_intent ─────┐
                    |                           |
                    v                           v
            Intent: progress?           Intent: chitchat/off_topic?
                |                               |
                v                               v
          Direct DB query              No retrieval (skip)
          (enrollments, skills,        Generate from system
           spaced_repetition)          prompt only
                                                
            Intent: in_course?
                |
                v
        User has course_id?
           /          \
         Yes           No
          |             |
          v             v
    ┌─ PageIndex ─┐   Semantic RAG
    |             |   (cross_course path)
    | SQL tree    |
    | + LLM pick  |
    | + lessons   |
    └──────┬──────┘
           |
           v
    Context sufficient?
    (>= 200 tokens)
       /        \
     Yes         No
      |           |
      v           v
    Done     Scoped RAG Fallback
             (semantic search on
              course source document)
```

### 2.2 Cinco rutas de recuperacion

| # | Ruta | Disparador | Metodo | Coste |
|---|------|---------|--------|------|
| 1 | **PageIndex** | `in_course` + `course_id` establecido | 2 consultas SQL + 1 llamada corta al LLM (~20 tokens) | Bajo: ~0,0001 $ + 2 idas y vueltas a la BD |
| 2 | **RAG semantico** | `cross_course` o `in_course` sin `course_id` | 1 llamada de embedding + 1 consulta pgvector | Medio: ~0,0002 $ + latencia de embedding |
| 3 | **Fallback RAG acotado** | PageIndex devolvio < 200 tokens | Coste de PageIndex + 1 embedding + 1 consulta pgvector acotada | Medio: PageIndex + semantico |
| 4 | **DB directa** | Intencion `progress` | 3 consultas SQL (matriculas, habilidades, repeticion espaciada) | El mas bajo: SQL puro, sin LLM, sin embeddings |
| 5 | **Sin recuperacion** | `chitchat` u `off_topic` | Ninguno | Coste de recuperacion cero |

### 2.3 Comparativa de coste y latencia

| Ruta | Latencia de recuperacion | Llamadas al LLM | Idas y vueltas a la BD | Llamadas de embedding | Total estimado |
|------|-------------------|-----------|----------------|-----------------|-----------------|
| PageIndex | ~50 ms | 1 (clasificar) + 1 (seleccionar modulos) | 2 | 0 | ~150 ms |
| RAG semantico | ~80 ms | 1 (clasificar) | 1 | 1 (~10 ms local) | ~200 ms |
| Fallback acotado | ~130 ms | 1 + 1 | 2 + 1 | 1 | ~300 ms |
| DB directa | ~20 ms | 1 (clasificar) | 3 | 0 | ~100 ms |
| Sin recuperacion | 0 ms | 1 (clasificar) | 0 | 0 | ~50 ms |

Todos los tiempos excluyen la llamada al LLM de generacion principal (que transmite y tipicamente tarda de 1 a 3 segundos).

### 2.4 Cuando PageIndex supera al RAG semantico

Se prefiere PageIndex para preguntas dentro del curso porque:

1. **Precision:** el contenido del curso ya esta estructurado (modulos > lecciones). El LLM elige de un conjunto pequeno y conocido. Sin ruido de embeddings.
2. **Sin deriva de embeddings:** si el modelo de embeddings cambia o el curso se genero despues de la ingesta, el texto de la leccion puede no coincidir con el espacio de embeddings. PageIndex usa SQL puro sobre el esquema relacional.
3. **Mas barato:** sin llamada de embedding. La llamada al LLM de seleccion de modulo es de ~20 tokens.
4. **Alcance determinista:** el curso en el que el usuario esta matriculado es el limite exacto. La busqueda semantica podria traer contenido de otros cursos.

Se prefiere el RAG semantico cuando:
- El usuario no esta dentro de un curso (sin `course_id`)
- La pregunta abarca temas mas alla de un solo curso
- El contenido del curso es escaso y la respuesta podria estar en los documentos fuente

---

## 3. Gestion de la ventana de contexto

### 3.1 Presupuesto de tokens

El agente tutor opera dentro de un presupuesto de tokens conservador pensado para modelos mas pequenos (contexto ~8K-16K). El presupuesto escala automaticamente si se configura un modelo mas grande.

```
┌──────────────────────────────────────────────────────┐
│                  Context Window                       │
│                                                      │
│  ┌──────────────┐  ~400 tokens                       │
│  │ System Prompt │  Fixed: role, rules, org name      │
│  └──────────────┘                                    │
│                                                      │
│  ┌──────────────┐  ~2000 tokens (variable)           │
│  │ History      │  Last 6 turns raw                   │
│  │              │  + older turns as summary            │
│  └──────────────┘                                    │
│                                                      │
│  ┌──────────────┐  ~3000 tokens (variable)           │
│  │ Retrieved    │  3-5 chunks with citation markers   │
│  │ Context      │  Ordered by document position       │
│  └──────────────┘                                    │
│                                                      │
│  ┌──────────────┐  ~200 tokens                       │
│  │ User Message │  Current question + instructions    │
│  └──────────────┘                                    │
│                                                      │
│  ┌──────────────┐  ~2000 tokens (reserved)           │
│  │ Generation   │  Reserved for response output       │
│  │ Reserve      │  (max_tokens parameter)             │
│  └──────────────┘                                    │
│                                                      │
│  Total: ~7600 tokens (conservative, 8K model)        │
│         Scales up with MODEL_CONTEXT_LIMITS           │
└──────────────────────────────────────────────────────┘
```

```python
# src/agents/memory.py

TOKEN_BUDGET = {
    "system_prompt": 400,
    "history": 2000,
    "retrieved_context": 3000,
    "user_message": 200,
    "generation_reserve": 2000,
}

# Total budget allocated per request
TOTAL_BUDGET = sum(TOKEN_BUDGET.values())  # ~7600

# For larger models, the retrieved_context and history budgets scale up
MODEL_CONTEXT_LIMITS = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "claude-3.5-sonnet": 200_000,
    "deepseek-v3": 64_000,
    "deepseek-chat": 64_000,
    "default": 16_000,
}

def get_budgets(model: str) -> dict:
    """Scale token budgets based on model context window."""
    max_ctx = MODEL_CONTEXT_LIMITS.get(model, MODEL_CONTEXT_LIMITS["default"])

    if max_ctx <= 16_000:
        return TOKEN_BUDGET  # Conservative defaults

    # Scale history and context proportionally (cap at 10x)
    scale = min(10, max_ctx / 16_000)
    return {
        "system_prompt": 400,  # Fixed — does not scale
        "history": int(2000 * scale),
        "retrieved_context": int(3000 * scale),
        "user_message": 200,  # Fixed
        "generation_reserve": int(2000 * min(2, scale)),  # Cap at 4000
    }
```

### 3.2 Memoria de la conversacion

El tutor mantiene memoria de conversacion dentro de una sesion. La estrategia equilibra la calidad del contexto con la eficiencia en tokens.

```
Session Memory Strategy:
                                                          
  Turn 1  ──→ Summarize ──┐                               
  Turn 2  ──→ Summarize ──┤                               
  Turn 3  ──→ Summarize ──┼──→ history_summary (~200-400 tokens)
  Turn 4  ──→ Summarize ──┤     Cached in session table   
  ...     ──→ Summarize ──┘     Regenerated every 6 turns  
                                                          
  Turn N-5 ──→ Raw in history                              
  Turn N-4 ──→ Raw in history                              
  Turn N-3 ──→ Raw in history                              
  Turn N-2 ──→ Raw in history                              
  Turn N-1 ──→ Raw in history                              
  Turn N   ──→ Current message (not in history yet)        
```

**Reglas:**

1. Los **ultimos 6 turnos** se mantienen como mensajes en bruto en el campo `history`.
2. Los **turnos mas antiguos** se resumen en un parrafo. El resumen se regenera cada 6 turnos (cuando un nuevo lote "envejece y sale").
3. El **resumen se cachea** en la tabla `chat_sessions` para evitar volver a resumir en cada peticion.
4. **En una sesion nueva**, el historial empieza vacio. No hay memoria entre sesiones.

```python
# src/agents/memory.py

MAX_RAW_TURNS = 6
SUMMARY_TRIGGER = 6  # Regenerate summary every N turns

async def prepare_history(
    session_id: UUID,
    db: AsyncSession,
    llm: AsyncOpenAI,
) -> tuple[list[ConversationTurn], str | None]:
    """
    Load conversation history for the tutor.
    
    Returns:
        (recent_turns, summary_of_older_turns)
    """
    # Fetch all messages in this session, ordered chronologically
    messages = (await db.execute(
        text("""
            SELECT role, content, metadata
            FROM chat_messages
            WHERE session_id = :sid
            ORDER BY created_at ASC
        """),
        {"sid": session_id}
    )).fetchall()

    total = len(messages)

    if total <= MAX_RAW_TURNS:
        # Everything fits in raw history
        turns = [
            ConversationTurn(role=m.role, content=m.content)
            for m in messages
        ]
        return turns, None

    # Split: older messages need summary, recent ones stay raw
    older = messages[:-MAX_RAW_TURNS]
    recent = messages[-MAX_RAW_TURNS:]

    # Check if we have a cached summary
    session = (await db.execute(
        text("SELECT summary, summary_turn_count FROM chat_sessions WHERE id = :sid"),
        {"sid": session_id}
    )).fetchone()

    cached_summary = session.summary if session else None
    cached_count = session.summary_turn_count if session else 0

    # Regenerate summary if new turns have aged out
    if cached_summary and cached_count == len(older):
        summary = cached_summary
    else:
        summary = await _summarize_turns(older, llm)
        # Cache the summary
        await db.execute(
            text("""
                UPDATE chat_sessions
                SET summary = :summary, summary_turn_count = :count
                WHERE id = :sid
            """),
            {"summary": summary, "count": len(older), "sid": session_id}
        )

    recent_turns = [
        ConversationTurn(role=m.role, content=m.content)
        for m in recent
    ]

    return recent_turns, summary


async def _summarize_turns(turns, llm: AsyncOpenAI) -> str:
    """Summarize a list of conversation turns into a paragraph."""
    conversation_text = "\n".join(
        f"{'Employee' if t.role == 'user' else 'Tutor'}: {t.content}"
        for t in turns
    )

    response = await llm.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{
            "role": "user",
            "content": f"""Summarize this conversation in 2-3 sentences, focusing on the topics discussed and any important answers given:

{conversation_text}

Summary:""",
        }],
        max_tokens=200,
        temperature=0,
    )

    return response.choices[0].message.content.strip()
```

---

## 4. Formato de citas

### 4.1 Flujo de citas

Las citas siguen un pipeline desde la recuperacion, pasando por la generacion, hasta el frontend.

```
Retrieval                 Generation                 Post-process              Frontend
─────────                 ──────────                 ────────────              ────────
                                                                              
[Fuente 1: Manual         LLM writes:                Extract [1],[2]          User sees:
 Devoluciones > Plazos]   "The return period         from response text       "The return period
                          is 30 days [1].                                      is 30 days [1]."
[Fuente 2: Manual         Products must be           Map to Citation          
 Devoluciones > Estado]   unused [2]."               objects                  [1] Manual Devoluciones
                                                                                  > Plazos, pag. 3
                                                     Send SSE event:          [2] Manual Devoluciones
                                                     citations: [...]              > Estado, pag. 5
```

### 4.2 Instruccion de citas en el system prompt

El system prompt instruye al LLM para que cite las fuentes con marcadores numerados. Esta es la seccion relevante anadida a cada system prompt del tutor:

```
When answering:
- Reference your sources using [1], [2], etc. at the end of each claim.
- Each number corresponds to the [Fuente N] labels in the provided context.
- Only cite sources you actually used. Do not cite sources for general knowledge statements.
- If none of the provided sources contain the answer, say so explicitly.
```

### 4.3 Objeto de cita estructurado

```python
@dataclass
class Citation:
    index: int              # [1], [2], etc. — matches the marker in the response text
    document_title: str     # "Manual de Devoluciones"
    section: str            # "Plazos de devolucion"
    page: int | None        # 3 (from document_chunk metadata, None for lessons)
    source_type: str        # "lesson" | "document_chunk" | "manual"
    source_id: UUID | None  # The lesson_id or chunk_id — for frontend linking
```

### 4.4 Protocolo de eventos SSE

El protocolo SSE completo para la respuesta del chat del tutor:

```
# 1. Token events — streamed as generated
event: token
data: {"content": "The "}

event: token
data: {"content": "return "}

event: token
data: {"content": "period "}

event: token
data: {"content": "is "}

event: token
data: {"content": "30 days [1]."}

# ... more tokens ...

# 2. Citations event — sent after generation completes
event: citations
data: {"citations": [
  {"index": 1, "document": "Manual Devoluciones", "section": "Plazos", "page": 3},
  {"index": 2, "document": "Manual Devoluciones", "section": "Estado del producto", "page": 5}
]}

# 3. Suggestions event — follow-up prompts
event: suggestions
data: {"suggestions": [
  "Explicame esto con un ejemplo practico",
  "Que ejercicios hay sobre este tema?"
]}

# 4. Done event — signals stream end with metadata
event: done
data: {
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "tokens_used": 1847,
  "retrieval_source": "pageindex",
  "retrieval_latency_ms": 142,
  "generation_latency_ms": 2340
}

# On error (replaces done)
event: error
data: {"message": "Model unavailable. Please try again later.", "code": "LLM_ERROR"}
```

### 4.5 Renderizado de citas en el frontend

El frontend recibe el evento `citations` y transforma los marcadores en linea `[1]` en referencias clicables. `source_type` y `source_id` determinan la navegacion:

| source_type | Accion al hacer clic |
|-------------|-------------|
| `lesson` | Navegar a `/courses/:id` en la leccion |
| `document_chunk` | Abrir el visor de documentos en la pagina (futuro) |
| `manual` | Navegar a `/manuals/:id` en la seccion |

---

## 5. Agente de Chat de Administracion

### 5.1 Arquitectura

El agente de chat de administracion es un **agente de llamada a herramientas** — fundamentalmente distinto del tutor. En lugar de recuperacion RAG, tiene acceso a herramientas que consultan y modifican la plataforma. El LLM decide que herramientas llamar segun la peticion en lenguaje natural del administrador.

```
Admin message ──→ plan ──→ execute_tools ──→ need confirmation?
                                                /          \
                                              No            Yes
                                              |              |
                                              v              v
                                         synthesize     confirm
                                              |              |
                                              v              v
                                           Done        execute_write
                                                           |
                                                           v
                                                      synthesize ──→ Done
```

### 5.2 AdminState

```python
# src/agents/admin_agent.py

class ToolCall(TypedDict):
    tool_name: str
    arguments: dict
    result: Any | None
    status: Literal["pending", "executed", "confirmed", "rejected"]

class AdminState(TypedDict):
    # Input
    user_id: UUID
    org_id: UUID
    message: str
    session_id: UUID

    # Conversation
    history: list[ConversationTurn]
    history_summary: str | None

    # Planning
    plan: str                           # LLM's reasoning about what tools to call
    tool_calls: list[ToolCall]          # Planned tool invocations

    # Confirmation (for write operations)
    pending_confirmation: ToolCall | None   # Write operation awaiting admin approval
    confirmation_preview: str               # Human-readable preview of the action

    # Output
    response: str
    tokens_used: int
```

### 5.3 Definiciones de herramientas

El agente de administracion tiene 13 herramientas organizadas por tipo: consultas de solo lectura y operaciones de escritura que requieren confirmacion.

```python
# src/agents/admin_tools.py

from dataclasses import dataclass
from typing import Callable

@dataclass
class AdminTool:
    name: str
    description: str
    parameters: dict          # JSON Schema for arguments
    handler: Callable
    requires_confirmation: bool

ADMIN_TOOLS: list[AdminTool] = [
    # ── Read-only tools ──────────────────────────────────────────────
    AdminTool(
        name="list_employees",
        description="List all employees with their status, active courses, and skill coverage. "
                    "Supports optional filters: search (name/email), role, is_active.",
        parameters={
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Search by name or email"},
                "role": {"type": "string", "enum": ["admin", "employee"]},
                "is_active": {"type": "boolean"},
            },
        },
        handler=tool_list_employees,
        requires_confirmation=False,
    ),
    AdminTool(
        name="get_employee_detail",
        description="Get detailed info for a specific employee: skills, enrollments, "
                    "recent activity, and learning profile.",
        parameters={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "format": "uuid"},
                "employee_name": {"type": "string",
                                  "description": "If ID unknown, search by name"},
            },
        },
        handler=tool_get_employee_detail,
        requires_confirmation=False,
    ),
    AdminTool(
        name="get_skills_matrix",
        description="Get the full skills matrix showing all employees and their skill levels. "
                    "Can filter by skill category.",
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by category name"},
            },
        },
        handler=tool_get_skills_matrix,
        requires_confirmation=False,
    ),
    AdminTool(
        name="get_skill_gaps",
        description="Find skills where no employee (or fewer than threshold) has 'high' level. "
                    "Identifies organizational knowledge risks.",
        parameters={
            "type": "object",
            "properties": {
                "threshold": {"type": "integer", "default": 1,
                              "description": "Minimum number of experts needed"},
            },
        },
        handler=tool_get_skill_gaps,
        requires_confirmation=False,
    ),
    AdminTool(
        name="who_knows",
        description="Find employees who have a specific skill at a given level or higher. "
                    "Useful for finding experts or mentors.",
        parameters={
            "type": "object",
            "properties": {
                "skill_name": {"type": "string"},
                "min_level": {"type": "string", "enum": ["low", "medium", "high"],
                              "default": "medium"},
            },
            "required": ["skill_name"],
        },
        handler=tool_who_knows,
        requires_confirmation=False,
    ),
    AdminTool(
        name="list_courses",
        description="List all courses with their status, enrollment count, and average score.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["draft", "published", "archived"]},
            },
        },
        handler=tool_list_courses,
        requires_confirmation=False,
    ),
    AdminTool(
        name="get_course_stats",
        description="Get detailed statistics for a specific course: enrolled count, "
                    "completion rate, average score, problematic exercises.",
        parameters={
            "type": "object",
            "properties": {
                "course_id": {"type": "string", "format": "uuid"},
                "course_title": {"type": "string"},
            },
        },
        handler=tool_get_course_stats,
        requires_confirmation=False,
    ),
    AdminTool(
        name="get_alerts",
        description="Get current platform alerts: deadline risks, consecutive failures, "
                    "employees needing attention.",
        parameters={"type": "object", "properties": {}},
        handler=tool_get_alerts,
        requires_confirmation=False,
    ),
    AdminTool(
        name="get_mentorship_suggestions",
        description="Find mentor-mentee pairs based on skill levels. "
                    "High-level employees paired with low-level ones on the same skill.",
        parameters={"type": "object", "properties": {}},
        handler=tool_get_mentorship_suggestions,
        requires_confirmation=False,
    ),

    # ── Write tools (require confirmation) ───────────────────────────
    AdminTool(
        name="assign_course",
        description="Assign a course to one or more employees. "
                    "Optionally set a deadline.",
        parameters={
            "type": "object",
            "properties": {
                "course_id": {"type": "string", "format": "uuid"},
                "course_title": {"type": "string"},
                "employee_ids": {"type": "array", "items": {"type": "string"}},
                "employee_names": {"type": "array", "items": {"type": "string"},
                                   "description": "If IDs unknown, search by names"},
                "deadline": {"type": "string", "format": "date"},
            },
            "required": ["course_title"],
        },
        handler=tool_assign_course,
        requires_confirmation=True,
    ),
    AdminTool(
        name="verify_skill",
        description="Manually set an employee's skill level. "
                    "Overrides the checkpoint-based level.",
        parameters={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "format": "uuid"},
                "employee_name": {"type": "string"},
                "skill_name": {"type": "string"},
                "level": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["skill_name", "level"],
        },
        handler=tool_verify_skill,
        requires_confirmation=True,
    ),
    AdminTool(
        name="deactivate_employee",
        description="Deactivate an employee account. They will no longer be able to log in. "
                    "Their data is preserved.",
        parameters={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "format": "uuid"},
                "employee_name": {"type": "string"},
            },
        },
        handler=tool_deactivate_employee,
        requires_confirmation=True,
    ),
    AdminTool(
        name="archive_course",
        description="Archive a published course. Active enrollments will be marked as completed.",
        parameters={
            "type": "object",
            "properties": {
                "course_id": {"type": "string", "format": "uuid"},
                "course_title": {"type": "string"},
            },
        },
        handler=tool_archive_course,
        requires_confirmation=True,
    ),
]
```

### 5.4 Ejemplos de manejadores de herramientas

```python
# src/agents/admin_tools.py (handlers)

async def tool_list_employees(args: dict, org_id: UUID, db: AsyncSession) -> dict:
    """List employees with summary stats."""
    query = """
        SELECT u.id, u.full_name, u.email, u.role, u.is_active,
               COUNT(DISTINCT e.id) FILTER (WHERE e.status = 'in_progress') AS active_courses,
               COUNT(DISTINCT us.skill_id) AS skills_count
        FROM users u
        LEFT JOIN enrollments e ON e.user_id = u.id
        LEFT JOIN user_skills us ON us.user_id = u.id
        WHERE u.org_id = :org_id
    """
    params = {"org_id": org_id}

    if args.get("search"):
        query += " AND (u.full_name ILIKE :search OR u.email ILIKE :search)"
        params["search"] = f"%{args['search']}%"
    if args.get("role"):
        query += " AND u.role = :role"
        params["role"] = args["role"]
    if args.get("is_active") is not None:
        query += " AND u.is_active = :active"
        params["active"] = args["is_active"]

    query += " GROUP BY u.id ORDER BY u.full_name"

    results = (await db.execute(text(query), params)).fetchall()

    return {
        "employees": [
            {
                "id": str(r.id),
                "name": r.full_name,
                "email": r.email,
                "role": r.role,
                "is_active": r.is_active,
                "active_courses": r.active_courses,
                "skills_count": r.skills_count,
            }
            for r in results
        ],
        "total": len(results),
    }


async def tool_who_knows(args: dict, org_id: UUID, db: AsyncSession) -> dict:
    """Find employees with a specific skill."""
    skill_name = args["skill_name"]
    min_level = args.get("min_level", "medium")

    # Map levels to numeric for comparison
    level_order = {"low": 1, "medium": 2, "high": 3}
    min_numeric = level_order.get(min_level, 2)

    results = (await db.execute(
        text("""
            SELECT u.full_name, u.email, us.level, us.last_assessed_at
            FROM user_skills us
            JOIN users u ON u.id = us.user_id
            JOIN skills s ON s.id = us.skill_id
            WHERE s.org_id = :org_id
              AND s.name ILIKE :skill_name
              AND u.is_active = true
            ORDER BY
                CASE us.level
                    WHEN 'high' THEN 3
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 1
                END DESC
        """),
        {"org_id": org_id, "skill_name": f"%{skill_name}%"}
    )).fetchall()

    # Filter by minimum level
    filtered = [
        r for r in results
        if level_order.get(r.level, 0) >= min_numeric
    ]

    return {
        "skill": skill_name,
        "min_level": min_level,
        "employees": [
            {
                "name": r.full_name,
                "email": r.email,
                "level": r.level,
                "last_assessed": str(r.last_assessed_at) if r.last_assessed_at else None,
            }
            for r in filtered
        ],
        "total": len(filtered),
    }


async def tool_assign_course(args: dict, org_id: UUID, db: AsyncSession) -> dict:
    """Assign a course to employees. Returns preview for confirmation."""
    # Resolve course
    course = None
    if args.get("course_id"):
        course = await db.get(Course, UUID(args["course_id"]))
    elif args.get("course_title"):
        course = (await db.execute(
            text("SELECT * FROM courses WHERE org_id = :org AND title ILIKE :title LIMIT 1"),
            {"org": org_id, "title": f"%{args['course_title']}%"}
        )).fetchone()

    if not course:
        return {"error": f"Course '{args.get('course_title', args.get('course_id'))}' not found"}

    # Resolve employees
    employees = []
    if args.get("employee_ids"):
        for eid in args["employee_ids"]:
            emp = await db.get(User, UUID(eid))
            if emp:
                employees.append(emp)
    elif args.get("employee_names"):
        for name in args["employee_names"]:
            emp = (await db.execute(
                text("SELECT * FROM users WHERE org_id = :org AND full_name ILIKE :name LIMIT 1"),
                {"org": org_id, "name": f"%{name}%"}
            )).fetchone()
            if emp:
                employees.append(emp)

    if not employees:
        return {"error": "No matching employees found"}

    # For preview (before confirmation)
    return {
        "action": "assign_course",
        "course": {"id": str(course.id), "title": course.title},
        "employees": [{"id": str(e.id), "name": e.full_name} for e in employees],
        "deadline": args.get("deadline"),
        "preview_message": (
            f"Assign '{course.title}' to {len(employees)} employee(s): "
            f"{', '.join(e.full_name for e in employees)}"
            + (f" with deadline {args['deadline']}" if args.get("deadline") else "")
        ),
    }
```

### 5.5 Protocolo de confirmacion

Las operaciones de escritura siguen un protocolo de confirmacion de dos pasos. El agente nunca ejecuta una operacion de escritura sin la aprobacion explicita del administrador.

```
Step 1: Preview
  Admin: "Assign the returns course to Carlos and Laura"
  Agent: "I'll assign 'Politica de Devoluciones' to 2 employees:
          - Carlos Garcia
          - Laura Martinez
          Deadline: none
          
          Do you want me to proceed? (yes/no)"

Step 2: Confirm or Reject
  Admin: "yes" / "si" / "proceed" / "dale"
  Agent: [executes the write operation]
         "Done. Course assigned to Carlos Garcia and Laura Martinez."
  
  Admin: "no" / "cancel" / "wait, add Maria too"
  Agent: [cancels, adjusts plan if needed]
```

```python
# src/agents/nodes/admin_confirm.py

CONFIRMATION_WORDS = {"yes", "si", "proceed", "dale", "ok", "confirmar", "hazlo", "adelante"}
REJECTION_WORDS = {"no", "cancel", "cancelar", "wait", "espera", "stop", "para"}

async def confirm_node(state: AdminState, db: AsyncSession) -> dict:
    """
    Handle the confirmation step for write operations.
    
    Checks if the admin's message is a confirmation or rejection.
    If confirmed, executes the pending write operation.
    If rejected, clears the pending operation and returns to planning.
    """
    msg = state["message"].strip().lower()
    pending = state["pending_confirmation"]

    if not pending:
        return {"pending_confirmation": None}

    # Check for confirmation
    is_confirmed = any(word in msg for word in CONFIRMATION_WORDS)
    is_rejected = any(word in msg for word in REJECTION_WORDS)

    if is_confirmed and not is_rejected:
        # Execute the write operation
        tool = _get_tool(pending["tool_name"])
        result = await tool.handler(
            pending["arguments"],
            state["org_id"],
            db,
            execute=True,  # Actually perform the write
        )
        await db.commit()

        return {
            "tool_calls": [
                {**pending, "result": result, "status": "confirmed"}
            ],
            "pending_confirmation": None,
            "response": f"Done. {result.get('success_message', 'Operation completed.')}",
        }

    else:
        # Rejected or ambiguous
        return {
            "pending_confirmation": None,
            "response": "Operation cancelled." if is_rejected else
                        "I didn't understand. The operation is still pending. Say 'yes' to confirm or 'no' to cancel.",
        }
```

### 5.6 Ensamblado del grafo de administracion

```python
# src/agents/admin_agent.py

from langgraph.graph import StateGraph, END

def build_admin_graph(llm, db, sse_queue) -> StateGraph:
    """Build the LangGraph state machine for the admin assistant."""

    graph = StateGraph(AdminState)

    graph.add_node("check_pending",
        lambda state: check_pending_confirmation(state))

    graph.add_node("plan",
        lambda state: plan_tools(state, llm))

    graph.add_node("execute_tools",
        lambda state: execute_tools(state, db))

    graph.add_node("confirm",
        lambda state: confirm_node(state, db))

    graph.add_node("synthesize",
        lambda state: synthesize_response(state, llm, sse_queue))

    # Entry: check if there's a pending confirmation first
    graph.set_entry_point("check_pending")

    graph.add_conditional_edges(
        "check_pending",
        lambda state: "confirm" if state.get("pending_confirmation") else "plan",
        {
            "confirm": "confirm",
            "plan": "plan",
        },
    )

    # After planning, execute the tools
    graph.add_edge("plan", "execute_tools")

    # After executing, check if any tool requires confirmation
    graph.add_conditional_edges(
        "execute_tools",
        lambda state: "confirm" if state.get("pending_confirmation") else "synthesize",
        {
            "confirm": "synthesize",  # Synthesize the preview message
            "synthesize": "synthesize",
        },
    )

    # After confirmation, synthesize the result
    graph.add_edge("confirm", "synthesize")

    graph.add_edge("synthesize", END)

    return graph.compile()


async def plan_tools(state: AdminState, llm: AsyncOpenAI) -> dict:
    """
    LLM decides which tools to call based on the admin's message.
    
    Uses OpenAI-compatible function calling format.
    """
    # Convert AdminTools to OpenAI function format
    functions = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for tool in ADMIN_TOOLS
    ]

    messages = [
        {"role": "system", "content": ADMIN_SYSTEM_PROMPT},
    ]

    # Add history
    for turn in state.get("history", []):
        messages.append({"role": turn.role, "content": turn.content})

    messages.append({"role": "user", "content": state["message"]})

    response = await llm.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        tools=[{"type": "function", "function": f} for f in functions],
        tool_choice="auto",
    )

    choice = response.choices[0]

    if choice.message.tool_calls:
        tool_calls = [
            ToolCall(
                tool_name=tc.function.name,
                arguments=json.loads(tc.function.arguments),
                result=None,
                status="pending",
            )
            for tc in choice.message.tool_calls
        ]
        return {"tool_calls": tool_calls, "plan": choice.message.content or ""}
    else:
        # No tools needed — direct response
        return {
            "tool_calls": [],
            "plan": "",
            "response": choice.message.content,
        }
```

### 5.7 System prompt del administrador

```python
# src/llm/prompts/admin_system.py

ADMIN_SYSTEM_PROMPT = """You are an administrative assistant for {org_name}'s learning platform (SkillNet).

You help the admin manage employees, courses, skills, and the platform. You have access to tools that query and modify the platform.

Capabilities:
- View and search employees, their skills, enrollments, and activity
- View the skills matrix and identify skill gaps
- Find who knows what (expert lookup)
- Assign courses to employees
- Verify (manually set) skill levels
- Deactivate employee accounts
- Archive courses
- View alerts and mentorship suggestions
- Get course statistics and feedback

Rules:
1. For READ operations (viewing data, searching), execute immediately and present results clearly.
2. For WRITE operations (assigning courses, verifying skills, deactivating employees, archiving courses), ALWAYS preview the action first and ask for confirmation before executing.
3. Present data in clear, structured format. Use tables when showing multiple records.
4. When searching by name, use partial matching (the tools support it).
5. If a request is ambiguous (multiple employees match a name), list the matches and ask for clarification.
6. Speak in the same language as the admin.
7. Never expose internal IDs unless the admin asks for them.
8. If a tool returns an error, explain it in plain language and suggest next steps."""
```

---

## 6. Infraestructura compartida

### 6.1 Nuevas tablas de base de datos

Dos tablas nuevas dan soporte a la persistencia de chat de ambos agentes. Se anaden al modelo de datos existente de 17 tablas.

```sql
-- Chat sessions (one per conversation thread)
CREATE TABLE chat_sessions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id),
    agent_type      text NOT NULL CHECK (agent_type IN ('tutor', 'admin')),
    title           text,               -- Auto-generated from first message
    summary         text,               -- Cached summary of older turns
    summary_turn_count int DEFAULT 0,   -- How many turns the summary covers
    context         jsonb DEFAULT '{}', -- Session context (course_id, lesson_id for tutor)
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_sessions_user ON chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_type ON chat_sessions(user_id, agent_type);

-- Chat messages (individual messages within a session)
CREATE TABLE chat_messages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role            text NOT NULL CHECK (role IN ('user', 'assistant')),
    content         text NOT NULL,
    metadata        jsonb DEFAULT '{}', -- citations, tool_calls, retrieval_source, latency
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_messages_session ON chat_messages(session_id, created_at);
```

El `metadata` JSONB guarda informacion especifica de cada agente:

```json
// Tutor message metadata
{
    "citations": [
        {"index": 1, "document": "Manual Devoluciones", "section": "Plazos", "page": 3}
    ],
    "retrieval_source": "pageindex",
    "retrieval_latency_ms": 142,
    "generation_latency_ms": 2340,
    "tokens_used": 1847
}

// Admin message metadata
{
    "tool_calls": [
        {"tool": "list_employees", "args": {"search": "Carlos"}, "result_count": 2}
    ],
    "tokens_used": 923
}
```

### 6.2 Limitacion de tasa

Cada tipo de agente tiene limites de tasa independientes para prevenir abusos y controlar los costes del LLM.

```python
# src/services/rate_limiter.py

from datetime import datetime, timedelta
from collections import defaultdict

class RateLimiter:
    """In-memory rate limiter. Sufficient for single-instance deployment."""

    def __init__(self):
        self._windows: dict[str, list[datetime]] = defaultdict(list)

    # Per-agent limits
    LIMITS = {
        "tutor": {"requests": 30, "window_seconds": 60},     # 30 req/min
        "admin": {"requests": 20, "window_seconds": 60},     # 20 req/min
    }

    def check(self, user_id: str, agent_type: str) -> bool:
        """Returns True if request is allowed, False if rate limited."""
        key = f"{agent_type}:{user_id}"
        limit = self.LIMITS.get(agent_type, self.LIMITS["tutor"])
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=limit["window_seconds"])

        # Clean old entries
        self._windows[key] = [
            t for t in self._windows[key] if t > window_start
        ]

        if len(self._windows[key]) >= limit["requests"]:
            return False

        self._windows[key].append(now)
        return True

    def time_until_reset(self, user_id: str, agent_type: str) -> int:
        """Seconds until the rate limit resets for this user."""
        key = f"{agent_type}:{user_id}"
        if not self._windows[key]:
            return 0
        oldest = min(self._windows[key])
        limit = self.LIMITS.get(agent_type, self.LIMITS["tutor"])
        reset_at = oldest + timedelta(seconds=limit["window_seconds"])
        return max(0, int((reset_at - datetime.utcnow()).total_seconds()))

# Singleton
rate_limiter = RateLimiter()
```

### 6.3 LLMClient compartido

Ambos agentes usan el mismo cliente `AsyncOpenAI` (configurado desde los ajustes de la organizacion o variables de entorno, ver [backend-api.md](backend-api.md) seccion 4.3). La diferencia esta en el system prompt y las herramientas disponibles.

```python
# src/services/chat_service.py

class ChatService:
    """Orchestrates both tutor and admin chat agents."""

    def __init__(self, db: AsyncSession, llm: AsyncOpenAI, embedder=None):
        self.db = db
        self.llm = llm
        self.embedder = embedder

    async def tutor_stream(
        self,
        user: User,
        message: str,
        context: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Handle a tutor chat message. Returns an SSE stream.
        
        context: {course_id?, lesson_id?, session_id?}
        """
        # Rate limit check
        if not rate_limiter.check(str(user.id), "tutor"):
            yield _sse_event("error", {
                "message": "Too many requests. Please wait a moment.",
                "code": "RATE_LIMITED",
                "retry_after": rate_limiter.time_until_reset(str(user.id), "tutor"),
            })
            return

        # Resolve or create session
        session_id = context.get("session_id") if context else None
        if not session_id:
            session_id = await self._create_session(user.id, "tutor", context)

        # Save user message
        await self._save_message(session_id, "user", message)

        # Load conversation memory
        history, summary = await prepare_history(session_id, self.db, self.llm)

        # Build initial state
        org = await self._get_org(user.org_id)
        state: TutorState = {
            "user_id": user.id,
            "org_id": user.org_id,
            "message": message,
            "session_id": session_id,
            "course_id": UUID(context["course_id"]) if context and context.get("course_id") else None,
            "lesson_id": UUID(context["lesson_id"]) if context and context.get("lesson_id") else None,
            "enrollment_id": None,
            "intent": "cross_course",  # Default, overwritten by classifier
            "retrieved_context": "",
            "retrieval_source": "none",
            "retrieval_chunks": [],
            "history": history,
            "history_summary": summary,
            "system_prompt": TUTOR_SYSTEM_PROMPT.format(org_name=org.name),
            "response": "",
            "citations": [],
            "suggestions": [],
            "tokens_used": 0,
            "retrieval_latency_ms": 0,
            "generation_latency_ms": 0,
        }

        # Run the graph with SSE streaming
        sse_queue = asyncio.Queue()
        graph = build_tutor_graph(self.llm, self.db, self.embedder, sse_queue)

        # Run graph in background, yield SSE events as they arrive
        async def run_graph():
            try:
                await graph.ainvoke(state)
            except Exception as e:
                await sse_queue.put({
                    "event": "error",
                    "data": {"message": str(e), "code": "AGENT_ERROR"},
                })
            finally:
                await sse_queue.put(None)  # Sentinel to stop iteration

        task = asyncio.create_task(run_graph())

        try:
            while True:
                event = await sse_queue.get()
                if event is None:
                    break
                yield _sse_event(event["event"], event["data"])
        finally:
            if not task.done():
                task.cancel()

        # Save assistant response
        final_state = task.result() if task.done() and not task.cancelled() else state
        if final_state.get("response"):
            await self._save_message(
                session_id, "assistant", final_state["response"],
                metadata={
                    "citations": [
                        {"index": c.index, "document": c.document_title,
                         "section": c.section, "page": c.page}
                        for c in final_state.get("citations", [])
                    ],
                    "retrieval_source": final_state.get("retrieval_source"),
                    "tokens_used": final_state.get("tokens_used"),
                },
            )

    async def admin_stream(
        self,
        user: User,
        message: str,
        session_id: UUID | None = None,
    ) -> AsyncGenerator[str, None]:
        """Handle an admin chat message. Returns an SSE stream."""
        if not rate_limiter.check(str(user.id), "admin"):
            yield _sse_event("error", {
                "message": "Too many requests. Please wait a moment.",
                "code": "RATE_LIMITED",
            })
            return

        if not session_id:
            session_id = await self._create_session(user.id, "admin")

        await self._save_message(session_id, "user", message)

        history, summary = await prepare_history(session_id, self.db, self.llm)

        org = await self._get_org(user.org_id)
        state: AdminState = {
            "user_id": user.id,
            "org_id": user.org_id,
            "message": message,
            "session_id": session_id,
            "history": history,
            "history_summary": summary,
            "plan": "",
            "tool_calls": [],
            "pending_confirmation": None,
            "confirmation_preview": "",
            "response": "",
            "tokens_used": 0,
        }

        sse_queue = asyncio.Queue()
        graph = build_admin_graph(self.llm, self.db, sse_queue)

        async def run_graph():
            try:
                await graph.ainvoke(state)
            except Exception as e:
                await sse_queue.put({
                    "event": "error",
                    "data": {"message": str(e), "code": "AGENT_ERROR"},
                })
            finally:
                await sse_queue.put(None)

        task = asyncio.create_task(run_graph())

        try:
            while True:
                event = await sse_queue.get()
                if event is None:
                    break
                yield _sse_event(event["event"], event["data"])
        finally:
            if not task.done():
                task.cancel()

        # Save response
        final_state = task.result() if task.done() and not task.cancelled() else state
        if final_state.get("response"):
            await self._save_message(
                session_id, "assistant", final_state["response"],
                metadata={
                    "tool_calls": [
                        {"tool": tc["tool_name"], "status": tc["status"]}
                        for tc in final_state.get("tool_calls", [])
                    ],
                    "tokens_used": final_state.get("tokens_used"),
                },
            )

    # ── Helper methods ───────────────────────────────────────────

    async def _create_session(
        self, user_id: UUID, agent_type: str, context: dict | None = None,
    ) -> UUID:
        result = await self.db.execute(
            text("""
                INSERT INTO chat_sessions (user_id, agent_type, context)
                VALUES (:uid, :type, :ctx)
                RETURNING id
            """),
            {"uid": user_id, "type": agent_type, "ctx": json.dumps(context or {})},
        )
        await self.db.commit()
        return result.scalar_one()

    async def _save_message(
        self, session_id: UUID, role: str, content: str, metadata: dict | None = None,
    ):
        await self.db.execute(
            text("""
                INSERT INTO chat_messages (session_id, role, content, metadata)
                VALUES (:sid, :role, :content, :meta)
            """),
            {"sid": session_id, "role": role, "content": content,
             "meta": json.dumps(metadata or {})},
        )
        await self.db.commit()

    async def _get_org(self, org_id: UUID):
        return (await self.db.execute(
            text("SELECT * FROM organizations WHERE id = :id"),
            {"id": org_id},
        )).fetchone()


def _sse_event(event: str, data: dict) -> str:
    """Format an SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
```

### 6.4 Rutas de la API

```python
# src/routes/chat.py

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from src.deps.auth import EmployeeUser, AdminUser
from src.deps.db import DBSession
from src.deps.llm import LLMClient
from src.deps.embedding import EmbeddingSvc
from src.schemas.chat import ChatMessageRequest, AdminChatRequest, SessionListResponse
from src.services.chat_service import ChatService

router = APIRouter()

@router.post("/chat")
async def tutor_chat(
    user: EmployeeUser,
    db: DBSession,
    llm: LLMClient,
    embeddings: EmbeddingSvc,
    body: ChatMessageRequest,
):
    """Employee tutor chat. Returns SSE stream."""
    service = ChatService(db, llm, embeddings)
    return StreamingResponse(
        service.tutor_stream(user, body.message, body.context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/chat/admin")
async def admin_chat(
    user: AdminUser,
    db: DBSession,
    llm: LLMClient,
    body: AdminChatRequest,
):
    """Admin assistant chat. Returns SSE stream."""
    service = ChatService(db, llm)
    return StreamingResponse(
        service.admin_stream(user, body.message, body.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/sessions")
async def list_sessions(
    user: CurrentUser,
    db: DBSession,
    agent_type: str | None = None,
):
    """List chat sessions for the current user."""
    query = """
        SELECT id, agent_type, title, is_active, created_at, updated_at
        FROM chat_sessions
        WHERE user_id = :uid
    """
    params = {"uid": user.id}

    if agent_type:
        query += " AND agent_type = :type"
        params["type"] = agent_type

    query += " ORDER BY updated_at DESC LIMIT 50"

    sessions = (await db.execute(text(query), params)).fetchall()
    return {
        "sessions": [
            {
                "id": str(s.id),
                "agent_type": s.agent_type,
                "title": s.title,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.get("/chat/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    user: CurrentUser,
    db: DBSession,
):
    """Get all messages in a chat session."""
    # Verify session belongs to user
    session = (await db.execute(
        text("SELECT * FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
        {"sid": session_id, "uid": user.id},
    )).fetchone()

    if not session:
        raise HTTPException(404, "Session not found")

    messages = (await db.execute(
        text("""
            SELECT id, role, content, metadata, created_at
            FROM chat_messages
            WHERE session_id = :sid
            ORDER BY created_at ASC
        """),
        {"sid": session_id},
    )).fetchall()

    return {
        "session_id": session_id,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "metadata": m.metadata,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.delete("/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: CurrentUser,
    db: DBSession,
):
    """Delete a chat session and all its messages."""
    result = await db.execute(
        text("DELETE FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
        {"sid": session_id, "uid": user.id},
    )
    if result.rowcount == 0:
        raise HTTPException(404, "Session not found")
    await db.commit()
    return {"status": "deleted"}
```

### 6.5 Esquemas de peticion/respuesta

```python
# src/schemas/chat.py

from pydantic import BaseModel
from uuid import UUID

class ChatContext(BaseModel):
    course_id: UUID | None = None
    lesson_id: UUID | None = None
    session_id: UUID | None = None

class ChatMessageRequest(BaseModel):
    message: str
    context: ChatContext | None = None

class AdminChatRequest(BaseModel):
    message: str
    session_id: UUID | None = None

class ChatCitation(BaseModel):
    index: int
    document: str
    section: str
    page: int | None = None

class ChatMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list[ChatCitation] | None = None
    metadata: dict | None = None
    created_at: str

class SessionResponse(BaseModel):
    id: UUID
    agent_type: str
    title: str | None
    is_active: bool
    created_at: str
    updated_at: str

class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
```

---

## 7. Arbol de decision RAG vs sin RAG

Diagrama de flujo de decision completo que combina todas las rutas de recuperacion. Esto es lo que implementan el nodo `classify_intent` y la funcion `_route_by_intent`.

```
                        ┌─────────────────────┐
                        │  Employee sends      │
                        │  a message           │
                        └──────────┬───────────┘
                                   │
                                   v
                        ┌─────────────────────┐
                        │  Is it a progress    │
                        │  question?           │
                        │  (scores, deadlines, │
                        │   skills, "mi nota") │
                        └──────────┬───────────┘
                               /       \
                            Yes         No
                             │           │
                             v           v
                    ┌────────────┐  ┌─────────────────────┐
                    │ PATH 4     │  │  Is it chitchat or   │
                    │ Direct DB  │  │  off-topic?          │
                    │            │  │  (greetings, thanks,  │
                    │ SQL queries│  │   unrelated topics)   │
                    │ on enroll- │  └──────────┬───────────┘
                    │ ments,     │         /       \
                    │ skills,    │      Yes         No
                    │ spaced_rep │       │           │
                    └────────────┘       v           v
                                ┌────────────┐  ┌─────────────────────┐
                                │ PATH 5     │  │  Is user inside     │
                                │ No         │  │  a course?          │
                                │ Retrieval  │  │  (course_id set)    │
                                │            │  └──────────┬───────────┘
                                │ Generate   │         /       \
                                │ from system│      Yes         No
                                │ prompt only│       │           │
                                └────────────┘       v           v
                                            ┌────────────┐  ┌────────────┐
                                            │ PATH 1     │  │ PATH 2     │
                                            │ PageIndex  │  │ Semantic   │
                                            │            │  │ RAG        │
                                            │ SQL tree + │  │            │
                                            │ LLM select │  │ pgvector   │
                                            │ + lessons  │  │ cosine     │
                                            └─────┬──────┘  │ similarity │
                                                  │         └────────────┘
                                                  v
                                        ┌─────────────────────┐
                                        │ Retrieved context    │
                                        │ >= 200 tokens?       │
                                        └──────────┬───────────┘
                                               /       \
                                            Yes         No
                                             │           │
                                             v           v
                                        (continue   ┌────────────┐
                                         to gen)    │ PATH 3     │
                                                    │ Scoped RAG │
                                                    │ Fallback   │
                                                    │            │
                                                    │ Semantic   │
                                                    │ search on  │
                                                    │ course's   │
                                                    │ source doc │
                                                    └────────────┘
```

### Tabla resumen completa de rutas

| Ruta | Nombre | Disparador | Metodo | Embedding? | Llamadas LLM (pre-gen) | Consultas DB | Latencia est. | Coste est. |
|------|------|---------|--------|------------|---------------------|------------|-------------|-----------|
| 1 | PageIndex | `in_course` + `course_id` | Navegacion del arbol SQL + seleccion de modulo por LLM | No | 2 (clasificar + seleccionar) | 2 (modulos, lecciones) | ~150 ms | ~0,0002 $ |
| 2 | RAG semantico | `cross_course` o sin `course_id` | Similitud coseno con pgvector | Si (consulta) | 1 (clasificar) | 1 (busqueda de similitud) | ~200 ms | ~0,0003 $ |
| 3 | Fallback acotado | La ruta 1 devolvio < 200 tokens | PageIndex + pgvector acotado | Si (consulta) | 2 (clasificar + seleccionar) | 3 (modulos, lecciones, fragmentos) | ~300 ms | ~0,0004 $ |
| 4 | DB directa | Intencion `progress` | SQL sobre matriculas, habilidades, repeticion espaciada | No | 1 (clasificar) | 3 | ~100 ms | ~0,0001 $ |
| 5 | Sin recuperacion | `chitchat` u `off_topic` | Ninguno | No | 1 (clasificar) | 0 | ~50 ms | ~0,00005 $ |

**Notas sobre los costes:**
- Los costes asumen precios de `gpt-4o-mini` (~0,15 $/1M tokens de entrada, ~0,60 $/1M tokens de salida).
- La llamada principal de generacion (respuesta en streaming) anade ~0,001-0,003 $ por peticion segun la longitud de la respuesta. Este coste es el mismo independientemente de la ruta de recuperacion.
- Las llamadas de embedding (modelo local `multilingual-e5-small`) son gratuitas en despliegues autoalojados.
