# LLM Integration Layer

> **Status: v1.** Complete LLM integration architecture for SkillNet. Covers provider abstraction, LangGraph integration, prompt management, streaming, cost/token management, error handling, and local LLM support. Aligns with [architecture.md](architecture.md), [backend-api.md](backend-api.md), and [rag-retrieval.md](rag-retrieval.md).

---

## 1. Provider Abstraction

SkillNet does not lock into any LLM provider. The backend talks to a single interface -- base URL + API key + model name -- using the `openai` Python SDK. Any OpenAI-compatible API works out of the box (OpenAI, DeepSeek, Groq, Together, Mistral, local via Ollama/LM Studio, etc.). No provider-specific code exists in business logic.

### 1.1 Environment Variables

Two groups: one for chat/completion models, one for embedding models. Per-use-case model overrides allow running different models for different tasks (e.g., a cheap model for tutoring, a stronger model for generation).

#### Chat / Completion

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Base URL for the OpenAI-compatible API |
| `LLM_API_KEY` | `""` | API key for authentication |
| `LLM_MODEL` | `gpt-4o-mini` | Default model for all use cases |
| `LLM_GENERATION_MODEL` | (falls back to `LLM_MODEL`) | Model for course/manual generation (may want stronger reasoning) |
| `LLM_TUTOR_MODEL` | (falls back to `LLM_MODEL`) | Model for tutor chat (may want faster/cheaper) |
| `LLM_EVAL_MODEL` | (falls back to `LLM_MODEL`) | Model for exercise evaluation (may want structured output reliability) |

#### Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_BASE_URL` | (falls back to `LLM_BASE_URL`) | Separate base URL for embeddings (different provider or local) |
| `EMBEDDING_API_KEY` | (falls back to `LLM_API_KEY`) | Separate API key for embedding provider |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Embedding model name |
| `EMBEDDING_DIMENSIONS` | `384` | Expected embedding dimensions. Must match pgvector column width |

> **E5 prefix requirement:** The `intfloat/multilingual-e5-small` model (and all E5-family models) requires specific prefixes on input text: prepend `"query: "` for search queries and `"passage: "` for documents being indexed. See `LLMClient.embed_query()` and `LLMClient.embed_passages()` helpers in section 1.3.

The separation between chat and embedding configuration exists because organizations commonly use different providers for each: a cloud API for chat (OpenAI, DeepSeek) and a local model for embeddings (multilingual-e5-small via Ollama), or vice versa.

### 1.2 LLMSettings Configuration

Pydantic Settings class that reads environment variables, provides fallback chains, and resolves the correct model for each use case.

```python
# src/llm/config.py

from enum import Enum
from pydantic_settings import BaseSettings


class LLMUseCase(str, Enum):
    """Use cases that may have dedicated model overrides."""
    TUTOR = "tutor"
    GENERATION = "generation"
    EVALUATION = "evaluation"
    ADMIN = "admin"          # admin assistant chat
    INGESTION = "ingestion"  # document processing (summarization, extraction)


class LLMSettings(BaseSettings):
    """LLM configuration. Reads from environment variables with LLM_ prefix."""

    # --- Chat / Completion ---
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    # Per-use-case overrides (empty = fall back to LLM_MODEL)
    LLM_GENERATION_MODEL: str = ""
    LLM_TUTOR_MODEL: str = ""
    LLM_EVAL_MODEL: str = ""

    # --- Embeddings ---
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"
    EMBEDDING_DIMENSIONS: int = 384

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def model_for(self, use_case: LLMUseCase) -> str:
        """Resolve the model name for a given use case.

        Priority: per-use-case env var > LLM_MODEL default.
        """
        overrides = {
            LLMUseCase.GENERATION: self.LLM_GENERATION_MODEL,
            LLMUseCase.TUTOR: self.LLM_TUTOR_MODEL,
            LLMUseCase.EVALUATION: self.LLM_EVAL_MODEL,
        }
        override = overrides.get(use_case, "")
        return override if override else self.LLM_MODEL

    @property
    def embed_base_url(self) -> str:
        """Embedding base URL, falls back to chat base URL."""
        return self.EMBEDDING_BASE_URL or self.LLM_BASE_URL

    @property
    def embed_api_key(self) -> str:
        """Embedding API key, falls back to chat API key."""
        return self.EMBEDDING_API_KEY or self.LLM_API_KEY


llm_settings = LLMSettings()
```

**Why Pydantic Settings:** Consistent with the rest of SkillNet's config pattern (see `src/config.py` in [backend-api.md](backend-api.md)). Validates types at startup, reads `.env` files, and provides typed access without parsing strings manually.

### 1.3 LLMClient

A thin wrapper around `AsyncOpenAI` that provides three methods: `chat()`, `chat_stream()`, and `embed()`. The wrapper exists to centralize model resolution, default parameters, and error handling. Services never instantiate `AsyncOpenAI` directly.

```python
# src/llm/client.py

from collections.abc import AsyncGenerator
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from src.llm.config import LLMSettings, LLMUseCase


class LLMClient:
    """Provider-agnostic LLM client.

    Uses the openai Python SDK which works with any OpenAI-compatible API:
    OpenAI, DeepSeek, Groq, Together, Ollama, LM Studio, vLLM, etc.
    """

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings

        # Chat client
        self._client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
        )

        # Embedding client (may point to a different provider)
        self._embed_client = AsyncOpenAI(
            base_url=settings.embed_base_url,
            api_key=settings.embed_api_key,
        )

    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        use_case: LLMUseCase = LLMUseCase.TUTOR,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> str:
        """Single-shot chat completion. Returns the full response text.

        Used for: evaluations, generation steps, admin queries,
        any case where the full response is needed before processing.
        """
        model = self._settings.model_for(use_case)

        kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        use_case: LLMUseCase = LLMUseCase.TUTOR,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion. Yields tokens as they arrive.

        Used for: tutor chat, admin chat -- any user-facing conversational
        endpoint where perceived latency matters.
        """
        model = self._settings.model_for(use_case)

        stream = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Uses the embedding-specific client/model, which may point to a
        different provider than the chat model.

        Returns a list of embedding vectors. Each vector has exactly
        EMBEDDING_DIMENSIONS floats.

        Note: For E5-family models (intfloat/multilingual-e5-*), the caller
        must prepend "query: " or "passage: " to inputs. Use the
        embed_query() and embed_passages() helpers instead of calling
        this method directly.
        """
        response = await self._embed_client.embeddings.create(
            model=self._settings.EMBEDDING_MODEL,
            input=texts,
            dimensions=self._settings.EMBEDDING_DIMENSIONS,
        )

        return [item.embedding for item in response.data]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query with the E5 "query: " prefix."""
        return (await self.embed([f"query: {text}"]))[0]

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Embed documents/passages with the E5 "passage: " prefix."""
        return await self.embed([f"passage: {t}" for t in texts])
```

**Why not use `AsyncOpenAI` directly in services:** Three reasons. First, model resolution per use case would be scattered across every call site. Second, retry logic and error translation (section 6) wrap the client. Third, testability -- services depend on `LLMClient` which can be replaced with a fake in tests.

### 1.4 Dependency Injection

The `LLMClient` is injected into route handlers via FastAPI's `Depends()` system, consistent with the existing pattern for database sessions and auth.

```python
# src/deps/llm.py

from src.llm.client import LLMClient
from src.llm.config import llm_settings

_llm_client: LLMClient | None = None


async def get_llm_client() -> LLMClient:
    """FastAPI dependency that provides the LLM client.

    The client is created once and reused (the underlying AsyncOpenAI
    client manages its own connection pool).
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(llm_settings)
    return _llm_client


# Type alias for route signatures
from typing import Annotated
from fastapi import Depends

LLM = Annotated[LLMClient, Depends(get_llm_client)]
```

Usage in routes:

```python
@router.post("/chat")
async def tutor_chat(user: EmployeeUser, db: DBSession, llm: LLM, body: ChatMessage):
    service = ChatService(db, llm)
    return StreamingResponse(
        service.tutor_stream(user, body.message, body.context),
        media_type="text/event-stream",
    )
```

---

## 2. LangGraph Integration

LangGraph manages agent state machines. Each agent type (tutor, content generator, evaluator) is a graph with defined nodes and edges. Graph nodes call `LLMClient` methods -- they do not instantiate their own LLM connections.

### 2.1 State Dataclasses

Each agent type has a typed state that flows through the graph. States are dataclasses (not dicts) for type safety and IDE support.

State definitions are in their respective agent documents: see [content-generation.md](content-generation.md) (`GenerationState`) and [chat-agents.md](chat-agents.md) (`TutorState`).

```python
# src/agents/states.py

from dataclasses import dataclass, field
from typing import Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


@dataclass
class EvaluationState:
    """State for the exercise evaluation agent."""
    messages: Annotated[list[BaseMessage], add_messages]
    exercise_id: str
    exercise_type: str
    student_answer: dict
    rubric: dict = field(default_factory=dict)
    score: float | None = None
    feedback: str = ""
    criteria_scores: dict = field(default_factory=dict)
```

### 2.2 Graph Node Pattern

Graph nodes are async functions that receive state, call `LLMClient`, and return state updates. Dependencies (`LLMClient`, database session) are injected via closures when building the graph -- not through `config["configurable"]` and not through state (which must remain serializable).

```python
# src/agents/tutor_agent.py

from langgraph.graph import StateGraph, END
from src.agents.states import TutorState
from src.llm.client import LLMClient


async def retrieve_context(state: TutorState, llm: LLMClient, db) -> dict:
    """Node: retrieve relevant chunks from knowledge layer."""
    if not state.should_retrieve:
        return {}

    query = state.messages[-1].content
    query_embedding = await llm.embed_query(query)

    # Semantic search (see rag-retrieval.md section 3.2.2)
    chunks = await similarity_search(db, query_embedding, top_k=5)

    return {
        "retrieved_chunks": chunks,
        "should_retrieve": False,
    }


async def generate_response(state: TutorState, llm: LLMClient) -> dict:
    """Node: generate tutor response from context + history."""
    context_block = assemble_context_block(state.retrieved_chunks)
    system_prompt = build_tutor_system_prompt(state)

    messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": m.type, "content": m.content} for m in state.messages],
    ]

    # Insert context before the latest user message
    if context_block:
        messages.insert(-1, {
            "role": "system",
            "content": f"Contexto relevante:\n\n{context_block}",
        })

    response = await llm.chat(
        messages,
        use_case=LLMUseCase.TUTOR,
        temperature=0.3,
    )

    citations = extract_citations(response, state.retrieved_chunks)

    return {
        "messages": [AIMessage(content=response)],
        "citations": citations,
    }


def build_tutor_graph(llm: LLMClient, db) -> StateGraph:
    """Build the tutor agent graph.

    Dependencies are injected via closures -- each node lambda
    captures llm and db from the enclosing scope.
    """
    graph = StateGraph(TutorState)

    graph.add_node("retrieve", lambda state: retrieve_context(state, llm, db))
    graph.add_node("respond", lambda state: generate_response(state, llm))

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "respond")
    graph.add_edge("respond", END)

    return graph.compile()
```

### 2.3 Streaming from LangGraph to SSE

For user-facing chat, the tutor graph uses `chat_stream()` instead of `chat()`. The async generator flows from LangGraph through FastAPI's `StreamingResponse` to the client as Server-Sent Events.

```python
# src/services/chat_service.py

from fastapi import Request
from src.llm.client import LLMClient, LLMUseCase


class ChatService:
    def __init__(self, db, llm: LLMClient) -> None:
        self._db = db
        self._llm = llm

    async def tutor_stream(
        self,
        user,
        message: str,
        context: dict | None,
        request: Request,
    ):
        """Async generator that yields SSE events for tutor chat.

        Flow: retrieve context -> stream LLM response -> emit citations.
        """
        # 1. Retrieve context (non-streaming, fast)
        chunks = await self._retrieve_context(user, message, context)
        messages = self._build_messages(user, message, chunks)

        # 2. Stream LLM response token by token
        full_response = ""
        try:
            async for token in self._llm.chat_stream(
                messages,
                use_case=LLMUseCase.TUTOR,
                temperature=0.3,
            ):
                # Check if client disconnected
                if await request.is_disconnected():
                    return

                full_response += token
                yield f"event: token\ndata: {json.dumps({'content': token})}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            return

        # 3. Extract citations and emit done event
        citations = extract_citations(full_response, chunks)

        yield f"event: done\ndata: {json.dumps({'message_id': str(uuid4()), 'citations': citations})}\n\n"

        # 4. Save to chat history (fire-and-forget, does not block the stream)
        await self._save_history(user, message, full_response, citations)
```

---

## 3. Prompt Management

### 3.1 Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Prompts in Python files, not database** | Version controlled with git. Code review on prompt changes. No migration needed to update a prompt. Rollback = git revert. |
| **f-strings for templating** | No extra template engine dependency. Python's f-strings are readable and type-checkable. Jinja2 would add complexity without benefit for this scale. |
| **One directory per agent type** | Clear ownership. A developer looking for the tutor's system prompt goes to `agents/prompts/tutor.py`. |
| **Shared module for cross-cutting instructions** | Safety guardrails, citation format, and language detection are the same across all agents. DRY. |

### 3.2 Directory Structure

```
src/agents/prompts/
    __init__.py
    tutor.py          # Tutor system prompt, follow-up prompts
    generator.py      # Course generation: outline, module, lesson, exercise
    evaluator.py      # Exercise grading: practical_case, dialogue
    admin.py          # Admin assistant system prompt
    shared.py         # Safety guardrails, citation instructions, language detection
```

### 3.3 Prompt Templates

#### Shared Safety and Citation Instructions

```python
# src/agents/prompts/shared.py

SAFETY_GUARDRAILS = """
REGLAS DE SEGURIDAD (cumplir SIEMPRE):
- Responde SOLO con informacion del contexto proporcionado.
- Si la informacion no esta en el contexto, di exactamente: "No tengo informacion \
sobre esto en los documentos disponibles."
- NUNCA inventes datos, cifras, plazos o procedimientos.
- NUNCA reveles informacion personal de otros empleados.
- NUNCA menciones condiciones medicas, discapacidades o neurodivergencia.
- NUNCA proporciones consejo legal, medico o financiero.
- Si la pregunta es sobre un tema ajeno al ambito laboral, redirige: \
"Mi funcion es ayudarte con los procesos y conocimientos de la empresa."
"""

CITATION_INSTRUCTIONS = """
INSTRUCCIONES DE CITACION:
- Cita la fuente usando [Fuente N] al final de cada afirmacion basada en el contexto.
- Cada fuente esta etiquetada como [Fuente 1], [Fuente 2], etc.
- Si combinas informacion de varias fuentes, cita todas: [Fuente 1][Fuente 3].
- No cites fuentes para conocimiento general o saludos.
"""

LANGUAGE_DETECTION = """
IDIOMA:
- Responde en el mismo idioma que la pregunta del usuario.
- Si el contexto esta en un idioma diferente al de la pregunta, traduce \
la informacion relevante al idioma de la pregunta.
"""
```

#### Tutor System Prompt

```python
# src/agents/prompts/tutor.py

from src.agents.prompts.shared import (
    SAFETY_GUARDRAILS,
    CITATION_INSTRUCTIONS,
    LANGUAGE_DETECTION,
)


def tutor_system_prompt(
    user_name: str,
    course_title: str | None = None,
    lesson_title: str | None = None,
) -> str:
    """Build the tutor system prompt.

    Temperature: 0.3 (grounded RAG responses need low temperature).
    Format: plain text with [Fuente N] citations.
    """
    context_section = ""
    if course_title:
        context_section += f"El empleado esta en el curso: '{course_title}'."
    if lesson_title:
        context_section += f" Leccion actual: '{lesson_title}'."

    return f"""Eres un tutor de formacion corporativa de SkillNet. Tu nombre es Tutor.
Ayudas a empleados a entender los procesos y conocimientos de su empresa.

EMPLEADO: {user_name}
{context_section}

COMPORTAMIENTO:
- Se claro, directo y profesional.
- Adapta tus explicaciones al nivel del empleado.
- Si el empleado parece confundido, ofrece una explicacion alternativa o un ejemplo.
- Usa listas y estructura cuando la respuesta tiene multiples pasos.
- Mantén las respuestas concisas (maximo 3-4 parrafos) a menos que el empleado \
pida una explicacion detallada.

{SAFETY_GUARDRAILS}

{CITATION_INSTRUCTIONS}

{LANGUAGE_DETECTION}
"""
```

#### Generator Prompts

```python
# src/agents/prompts/generator.py

def outline_prompt(document_summary: str, target_outcome: str) -> str:
    """Prompt for generating a course outline from a document.

    Temperature: 0.3 (structured, deterministic output).
    Format: JSON (response_format={"type": "json_object"}).
    """
    return f"""Eres un disenador instruccional experto. Analiza el siguiente resumen \
de documento y genera una estructura de curso.

DOCUMENTO:
{document_summary}

OBJETIVO DEL CURSO:
{target_outcome}

Genera un JSON con esta estructura exacta:
{{
  "title": "Titulo del curso",
  "modules": [
    {{
      "title": "Titulo del modulo",
      "summary": "Resumen en 1-2 oraciones",
      "lessons": [
        {{
          "title": "Titulo de la leccion",
          "key_concepts": ["concepto1", "concepto2"],
          "estimated_duration_minutes": 15
        }}
      ]
    }}
  ]
}}

REGLAS:
- Maximo 5 modulos, 3-4 lecciones por modulo.
- Cada modulo debe cubrir un tema coherente.
- Ordenar de lo basico a lo avanzado.
- Los conceptos clave deben ser especificos al documento, no genericos.
"""


def lesson_content_prompt(
    lesson_title: str,
    key_concepts: list[str],
    source_chunks: str,
) -> str:
    """Prompt for generating lesson content from source chunks.

    Temperature: 0.3 (faithful to source material).
    Format: Markdown text.
    """
    concepts = ", ".join(key_concepts)
    return f"""Genera el contenido de la leccion "{lesson_title}" basandote \
EXCLUSIVAMENTE en el material fuente proporcionado.

CONCEPTOS CLAVE A CUBRIR: {concepts}

MATERIAL FUENTE:
{source_chunks}

FORMATO DE SALIDA:
- Escribe en Markdown.
- Empieza con una introduccion breve (2-3 oraciones).
- Desarrolla cada concepto con explicaciones claras.
- Incluye ejemplos practicos del contexto del documento.
- Termina con un resumen de puntos clave en lista.
- Extension: 500-1000 palabras.

REGLAS:
- Usa SOLO informacion del material fuente.
- No inventes ejemplos que no esten en el documento.
- Adapta el lenguaje al ambito corporativo.
"""


def exercise_prompt(
    lesson_title: str,
    lesson_content: str,
    exercise_type: str,
) -> str:
    """Prompt for generating exercises for a lesson.

    Temperature: 0.3 (consistent with generation pipeline).
    Format: JSON (response_format={"type": "json_object"}).
    """
    type_instructions = {
        "test": """Genera una pregunta de opcion multiple con 4 opciones.
JSON: {"question": "...", "options": ["a", "b", "c", "d"], "correct": 0, "explanation": "..."}""",
        "true_false": """Genera una afirmacion verdadera o falsa.
JSON: {"statement": "...", "correct": true|false, "explanation": "..."}""",
        "fill_blank": """Genera un texto con huecos a rellenar (marca los huecos con ___).
JSON: {"text_with_blanks": "El plazo de ___ es de ___ dias.", "answers": ["devolucion", "30"], "explanation": "..."}""",
        "order_steps": """Genera una secuencia de pasos a ordenar.
JSON: {"instruction": "Ordena los pasos de...", "steps": ["paso1", "paso2", "paso3", "paso4"], "correct_order": [0, 1, 2, 3], "explanation": "..."}""",
        "practical_case": """Genera un caso practico con rubrica de evaluacion.
JSON: {"scenario": "...", "question": "...", "rubric": {"criterio1": {"description": "...", "max_score": 5}, "criterio2": {"description": "...", "max_score": 5}}, "model_answer": "..."}""",
    }

    instruction = type_instructions.get(exercise_type, type_instructions["test"])

    return f"""Genera un ejercicio de tipo "{exercise_type}" para la leccion "{lesson_title}".

CONTENIDO DE LA LECCION:
{lesson_content}

TIPO DE EJERCICIO:
{instruction}

REGLAS:
- El ejercicio debe evaluar comprension del contenido, no memorizacion.
- Las opciones incorrectas deben ser plausibles.
- La explicacion debe ser educativa.
- Basa todo en el contenido de la leccion.
"""
```

#### Evaluator Prompts

```python
# src/agents/prompts/evaluator.py

def practical_case_eval_prompt(
    scenario: str,
    question: str,
    rubric: dict,
    student_answer: str,
    model_answer: str,
) -> str:
    """Prompt for evaluating a practical case exercise.

    Temperature: 0.2 (consistent evaluation).
    Format: JSON (response_format={"type": "json_object"}).
    """
    rubric_text = "\n".join(
        f"- {name}: {criteria['description']} (max {criteria['max_score']} puntos)"
        for name, criteria in rubric.items()
    )

    return f"""Evalua la respuesta de un empleado a un caso practico.

ESCENARIO:
{scenario}

PREGUNTA:
{question}

RUBRICA:
{rubric_text}

RESPUESTA MODELO (referencia, no la unica respuesta correcta):
{model_answer}

RESPUESTA DEL EMPLEADO:
{student_answer}

Evalua segun la rubrica. Devuelve JSON:
{{
  "total_score": <float>,
  "max_score": <float>,
  "passed": <bool>,
  "criteria": {{
    "<criterio>": {{
      "score": <float>,
      "max_score": <float>,
      "feedback": "Explicacion especifica"
    }}
  }},
  "general_feedback": "Retroalimentacion general constructiva en 2-3 oraciones."
}}

REGLAS:
- Se justo pero exigente. La respuesta no necesita ser identica al modelo.
- Valora la comprension sobre la memorizacion.
- El feedback debe ser constructivo y especifico.
- passed = true si total_score >= 60% de max_score.
"""
```

#### Admin Assistant Prompt

```python
# src/agents/prompts/admin.py

from src.agents.prompts.shared import SAFETY_GUARDRAILS, LANGUAGE_DETECTION


def admin_system_prompt() -> str:
    """Build the admin assistant system prompt.

    Temperature: 0.5 (helpful but precise).
    Format: plain text.
    """
    return f"""Eres un asistente administrativo de SkillNet. Ayudas a administradores \
a gestionar la formacion de su equipo.

CAPACIDADES:
- Responder preguntas sobre el estado de la formacion (progreso, brechas, alertas).
- Sugerir acciones basadas en datos (asignaciones, revisiones, mentoria).
- Explicar metricas y reportes del sistema.
- Guiar en la configuracion del sistema.

DATOS DISPONIBLES:
- Los datos del contexto provienen de la base de datos de la organizacion.
- Incluyen: empleados, cursos, progreso, habilidades, alertas.

COMPORTAMIENTO:
- Se directo y orientado a la accion.
- Cuando sugieras acciones, se especifico ("Asignar el curso X a Carlos").
- Presenta datos en formato tabular cuando haya multiples items.
- Destaca situaciones criticas (deadlines proximos, brechas de habilidad).

{SAFETY_GUARDRAILS}

{LANGUAGE_DETECTION}
"""
```

### 3.4 Temperature and Format Summary

| Agent | Use Case | Temperature | Output Format |
|-------|----------|-------------|---------------|
| Tutor | Chat response | 0.3 | Plain text + citations |
| Tutor | Follow-up suggestion | 0.8 | Plain text |
| Generator | Course outline | 0.3 | JSON |
| Generator | Lesson content | 0.3 | Markdown |
| Generator | Exercise creation | 0.3 | JSON |
| Evaluator | Practical case grading | 0.2 | JSON |
| Evaluator | Dialogue assessment | 0.2 | JSON |
| Admin | Assistant response | 0.5 | Plain text |
| Ingestion | Document summarization | 0.2 | Plain text |

### 3.5 Prompt Testing

Prompts can be tested in isolation without spinning up the full application. Each prompt function returns a string -- no side effects, no I/O.

```python
# tests/test_prompts.py

def test_tutor_prompt_includes_safety():
    prompt = tutor_system_prompt("Maria", "Devoluciones", "Plazos")
    assert "NUNCA inventes" in prompt
    assert "Maria" in prompt
    assert "Devoluciones" in prompt


def test_outline_prompt_produces_valid_instruction():
    prompt = outline_prompt("Manual de devoluciones...", "Dominar el proceso")
    assert "JSON" in prompt
    assert "modules" in prompt


def test_eval_prompt_includes_rubric():
    rubric = {"claridad": {"description": "Respuesta clara", "max_score": 5}}
    prompt = practical_case_eval_prompt(
        "Un cliente...", "Que harias?", rubric, "Yo haria...", "Lo correcto es..."
    )
    assert "claridad" in prompt
    assert "max 5 puntos" in prompt
```

---

## 4. Streaming Architecture

### 4.1 End-to-End Flow

Token-by-token streaming from LLM to browser:

```
LLM Provider
    |  (OpenAI-compatible streaming API)
    v
AsyncOpenAI.chat.completions.create(stream=True)
    |  (async iterator of ChatCompletionChunk)
    v
LLMClient.chat_stream()
    |  (async generator yielding str tokens)
    v
ChatService.tutor_stream()
    |  (async generator yielding SSE-formatted strings)
    v
FastAPI StreamingResponse(media_type="text/event-stream")
    |  (HTTP chunked transfer encoding)
    v
Browser EventSource / ReadableStream
    |  (parsed SSE events)
    v
React state update (append token to message)
```

### 4.2 SSE Event Types

Three event types, kept minimal:

```
event: token
data: {"content": "The"}

event: token
data: {"content": " return"}

event: token
data: {"content": " policy"}

event: done
data: {"message_id": "a1b2c3d4", "citations": [{"document": "Manual_Devoluciones.pdf", "section": "Plazos", "page": 3}]}

event: error
data: {"message": "Model unavailable. Please try again."}
```

| Event | When | Payload |
|-------|------|---------|
| `token` | Each token from the LLM | `{"content": "<token text>"}` |
| `done` | LLM finished generating | `{"message_id": "<uuid>", "citations": [...]}` |
| `error` | Any error during streaming | `{"message": "<user-facing message>"}` |

### 4.3 Server-Side Implementation

```python
# src/routes/chat.py

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.post("/chat")
async def tutor_chat(
    request: Request,
    user: EmployeeUser,
    db: DBSession,
    llm: LLM,
    body: ChatMessageRequest,
):
    """Tutor chat endpoint. Returns SSE stream."""
    service = ChatService(db, llm)

    return StreamingResponse(
        service.tutor_stream(user, body.message, body.context, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
```

### 4.4 Client-Side Implementation

The React frontend uses `ReadableStream` (not `EventSource`) because the initial request is a POST with a body, which `EventSource` does not support.

```typescript
// src/hooks/useTutorChat.ts

interface ChatEvent {
  type: 'token' | 'done' | 'error'
  data: {
    content?: string
    message_id?: string
    citations?: Citation[]
    message?: string
  }
}

async function streamChat(
  message: string,
  context: { course_id?: string; lesson_id?: string },
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/v1/chat', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context }),
    signal,
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    onEvent({ type: 'error', data: { message: err.detail } })
    return
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()!  // Keep incomplete line in buffer

    let eventType = ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7)
      } else if (line.startsWith('data: ') && eventType) {
        const data = JSON.parse(line.slice(6))
        onEvent({ type: eventType as ChatEvent['type'], data })
        eventType = ''
      }
    }
  }
}
```

### 4.5 Client Disconnection Detection

If the user navigates away or closes the tab while the LLM is still generating, the server detects this and stops the stream. This prevents wasting LLM tokens on abandoned requests.

```python
# Inside ChatService.tutor_stream()

async for token in self._llm.chat_stream(messages, use_case=LLMUseCase.TUTOR):
    # Check if client disconnected before yielding each token
    if await request.is_disconnected():
        # Client is gone -- stop generating
        return

    full_response += token
    yield f"event: token\ndata: {json.dumps({'content': token})}\n\n"
```

The `request.is_disconnected()` call is cheap (checks the ASGI connection state). It does not add meaningful latency to the stream.

### 4.6 When NOT to Stream

Streaming is used only for user-facing conversational output. For structured JSON output, the full response is needed before processing:

| Endpoint | Streaming? | Why |
|----------|-----------|-----|
| Tutor chat | Yes | User sees tokens as they arrive |
| Admin chat | Yes | Same rationale |
| Exercise evaluation | No | Response must be valid JSON, parsed as a whole |
| Course generation | No | Each step produces structured data for the next step |
| Document summarization | No | Summary is consumed by the system, not displayed incrementally |

---

## 5. Cost and Token Management

### 5.1 Token Counting

SkillNet uses `tiktoken` with the `cl100k_base` encoding as a universal approximation for token counting. This encoding is close enough for OpenAI models and serves as a reasonable estimate for other providers (DeepSeek, Groq, etc.). Exact token counts are provider-specific, but the approximation is sufficient for budget management and truncation decisions.

```python
# src/llm/tokens.py

import tiktoken

# Singleton encoder -- loaded once, thread-safe
_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding.

    This is an approximation. Different models use different tokenizers,
    but cl100k_base is close enough for:
    - Context window budget checks (off by <5%)
    - Cost estimation (off by <10%)
    - Truncation decisions (safe because we truncate conservatively)
    """
    return len(_encoder.encode(text))


def count_messages_tokens(messages: list[dict]) -> int:
    """Count tokens across a list of chat messages.

    Accounts for the per-message overhead (role, name, delimiters).
    Based on OpenAI's token counting guide.
    """
    tokens = 0
    for message in messages:
        tokens += 4  # every message: <|start|>{role}\n ... \n<|end|>
        for key, value in message.items():
            tokens += count_tokens(str(value))
            if key == "name":
                tokens += -1  # role is omitted when name is present
    tokens += 2  # reply priming: <|start|>assistant
    return tokens
```

### 5.2 Context Window Management

The most critical use of token counting is fitting messages into the model's context window. The `fit_messages_to_context` function ensures that the system prompt is never truncated, while conversation history is trimmed from oldest messages first.

```python
# src/llm/context.py

from src.llm.tokens import count_tokens, count_messages_tokens


# Known context window sizes. Conservative estimates (leave margin).
CONTEXT_WINDOWS = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_385,
    "deepseek-chat": 64_000,
    "deepseek-reasoner": 64_000,
    "llama3.1": 128_000,
    "llama3.2": 128_000,
    "mistral": 32_000,
    "qwen2.5": 32_000,
}

DEFAULT_CONTEXT_WINDOW = 8_192  # Conservative fallback for unknown models
RESPONSE_RESERVE = 2_048  # Tokens reserved for the model's response


def get_context_window(model: str) -> int:
    """Get context window size for a model.

    Checks exact match first, then prefix match (for versioned names
    like 'gpt-4o-2024-08-06'), then falls back to conservative default.
    """
    if model in CONTEXT_WINDOWS:
        return CONTEXT_WINDOWS[model]

    # Prefix match: 'gpt-4o-2024-08-06' matches 'gpt-4o'
    for known_model, window in CONTEXT_WINDOWS.items():
        if model.startswith(known_model):
            return window

    return DEFAULT_CONTEXT_WINDOW


def fit_messages_to_context(
    messages: list[dict],
    model: str,
    response_reserve: int = RESPONSE_RESERVE,
) -> list[dict]:
    """Truncate message history to fit within the model's context window.

    Rules:
    1. The system message (messages[0]) is NEVER truncated.
    2. The most recent user message (messages[-1]) is NEVER truncated.
    3. History messages are removed from OLDEST first.
    4. At minimum, the result contains [system, latest_user_message].

    Returns a new list (does not modify the input).
    """
    max_tokens = get_context_window(model) - response_reserve

    # Check if everything fits
    total = count_messages_tokens(messages)
    if total <= max_tokens:
        return list(messages)

    # System prompt is always first and always kept
    system_msg = messages[0] if messages[0]["role"] == "system" else None
    latest_msg = messages[-1]

    # Calculate fixed cost (system + latest message)
    fixed_messages = []
    if system_msg:
        fixed_messages.append(system_msg)
    fixed_cost = count_messages_tokens(fixed_messages + [latest_msg])

    if fixed_cost >= max_tokens:
        # Even system + latest don't fit. Return them anyway (model will
        # truncate internally, but we preserve the most important context).
        result = []
        if system_msg:
            result.append(system_msg)
        result.append(latest_msg)
        return result

    # Budget for history messages
    history_budget = max_tokens - fixed_cost

    # History: everything between system and latest message
    start = 1 if system_msg else 0
    history = messages[start:-1]

    # Keep as many recent history messages as fit
    kept_history = []
    history_tokens = 0
    for msg in reversed(history):
        msg_tokens = count_messages_tokens([msg])
        if history_tokens + msg_tokens > history_budget:
            break
        kept_history.insert(0, msg)
        history_tokens += msg_tokens

    # Assemble result
    result = []
    if system_msg:
        result.append(system_msg)
    result.extend(kept_history)
    result.append(latest_msg)

    return result
```

### 5.3 Usage Tracking

LLM usage is logged to a database table for monitoring and cost analysis. This is not real-time billing -- it is an observability tool for the admin.

```sql
-- llm_usage_log table
CREATE TABLE llm_usage_log (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id),
    user_id         uuid REFERENCES users(id),
    use_case        text NOT NULL,          -- 'tutor', 'generation', 'evaluation', etc.
    model           text NOT NULL,          -- actual model used
    prompt_tokens   integer NOT NULL,
    completion_tokens integer NOT NULL,
    total_tokens    integer NOT NULL,
    estimated_cost  numeric(10, 6),         -- USD, estimated from token counts
    duration_ms     integer,                -- wall clock time for the API call
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_llm_usage_org ON llm_usage_log (org_id, created_at DESC);
CREATE INDEX idx_llm_usage_case ON llm_usage_log (use_case, created_at DESC);
```

```python
# src/llm/usage.py

from datetime import datetime
from uuid import UUID

# Cost per 1M tokens (approximate, varies by provider)
COST_TABLE = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    "llama3.1": {"input": 0.0, "output": 0.0},  # Local, no API cost
}


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate USD cost for an LLM call.

    Returns 0.0 for unknown models (conservative -- better to
    under-report than over-report for local models).
    """
    rates = COST_TABLE.get(model)
    if not rates:
        return 0.0

    input_cost = (prompt_tokens / 1_000_000) * rates["input"]
    output_cost = (completion_tokens / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


async def log_usage(
    db,
    *,
    org_id: UUID,
    user_id: UUID | None,
    use_case: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: int,
) -> None:
    """Record LLM usage to the database."""
    cost = estimate_cost(model, prompt_tokens, completion_tokens)

    await db.execute(
        text("""
            INSERT INTO llm_usage_log
                (org_id, user_id, use_case, model, prompt_tokens,
                 completion_tokens, total_tokens, estimated_cost, duration_ms)
            VALUES
                (:org_id, :user_id, :use_case, :model, :prompt_tokens,
                 :completion_tokens, :total_tokens, :cost, :duration_ms)
        """),
        {
            "org_id": org_id,
            "user_id": user_id,
            "use_case": use_case,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost": cost,
            "duration_ms": duration_ms,
        },
    )
```

### 5.4 Cost Estimation for Generation Jobs

Before starting a course generation job, the system estimates the total token cost so the admin can make an informed decision.

```python
# src/llm/cost.py

from src.llm.tokens import count_tokens
from src.llm.usage import estimate_cost


def estimate_generation_cost(
    document_text: str,
    model: str,
    num_modules: int = 4,
    lessons_per_module: int = 3,
    exercises_per_lesson: int = 2,
) -> dict:
    """Estimate the token cost of generating a course from a document.

    Returns a breakdown by step so the admin knows where the cost is.
    """
    doc_tokens = count_tokens(document_text)

    # Step 1: Outline generation (reads document summary, outputs JSON)
    outline_input = doc_tokens // 3 + 500  # summary + prompt
    outline_output = 800  # JSON outline

    # Step 2: Lesson content (one call per lesson, reads relevant chunks)
    num_lessons = num_modules * lessons_per_module
    lesson_input = 1500 * num_lessons  # chunks + prompt per lesson
    lesson_output = 1000 * num_lessons  # ~1000 tokens per lesson

    # Step 3: Exercise generation (one call per exercise)
    num_exercises = num_lessons * exercises_per_lesson
    exercise_input = 800 * num_exercises  # lesson content + prompt
    exercise_output = 300 * num_exercises  # JSON per exercise

    total_input = outline_input + lesson_input + exercise_input
    total_output = outline_output + lesson_output + exercise_output
    total_cost = estimate_cost(model, total_input, total_output)

    return {
        "estimated_input_tokens": total_input,
        "estimated_output_tokens": total_output,
        "estimated_total_tokens": total_input + total_output,
        "estimated_cost_usd": total_cost,
        "breakdown": {
            "outline": estimate_cost(model, outline_input, outline_output),
            "lessons": estimate_cost(model, lesson_input, lesson_output),
            "exercises": estimate_cost(model, exercise_input, exercise_output),
        },
        "model": model,
    }
```

---

## 6. Error Handling

### 6.1 Retry Strategy

LLM API calls are inherently unreliable (network issues, rate limits, provider outages). SkillNet uses the `tenacity` library for retry logic with exponential backoff.

```python
# src/llm/resilience.py

import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
)

logger = logging.getLogger("skillnet.llm")


def _is_retryable(exc: BaseException) -> bool:
    """Determine if an exception is worth retrying.

    Retryable:
    - APIConnectionError: network issue, might resolve
    - APITimeoutError: server slow, might recover
    - InternalServerError (500): provider hiccup
    - RateLimitError (429): will resolve after backoff

    Not retryable:
    - AuthenticationError (401): wrong API key, won't fix itself
    - NotFoundError (404): wrong model name, won't fix itself
    - BadRequestError (400): malformed request, won't fix itself
    """
    return isinstance(exc, (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    ))


def with_retry(func):
    """Decorator that adds retry logic to LLM calls.

    Strategy:
    - Max 3 attempts
    - Exponential backoff: 1s, 2s, 4s (multiplier=1, min=1, max=10)
    - Only retries on transient errors
    - Logs each retry attempt
    """
    return retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )(func)
```

Applied to the `LLMClient` methods:

```python
# src/llm/client.py (with retry)

class LLMClient:

    @with_retry
    async def chat(self, messages, *, use_case, temperature, max_tokens, response_format=None):
        ...

    # Note: chat_stream is NOT retried at the method level.
    # If the stream fails mid-way, the error is emitted as an SSE event
    # and the client can retry the full request.
    async def chat_stream(self, messages, **kwargs):
        ...

    @with_retry
    async def embed(self, texts):
        ...
```

### 6.2 Rate Limit Handling

When the LLM provider returns 429 (rate limited), the `Retry-After` header indicates how long to wait. The `openai` SDK handles this automatically via `RateLimitError`, and `tenacity`'s exponential backoff covers the retry timing. For cases where the `Retry-After` header specifies a longer wait:

```python
# src/llm/resilience.py (continued)

from tenacity import wait_exponential, wait_combine, wait_fixed


def _get_retry_after(exc: BaseException) -> float | None:
    """Extract Retry-After from a RateLimitError, if present."""
    if isinstance(exc, RateLimitError):
        retry_after = getattr(exc, "response", None)
        if retry_after and hasattr(retry_after, "headers"):
            header = retry_after.headers.get("Retry-After")
            if header:
                try:
                    return float(header)
                except ValueError:
                    pass
    return None


class WaitRespectRetryAfter(wait_exponential):
    """Custom wait strategy that respects the Retry-After header
    when present, falling back to exponential backoff otherwise."""

    def __call__(self, retry_state):
        exc = retry_state.outcome.exception()
        retry_after = _get_retry_after(exc)
        if retry_after is not None:
            return retry_after
        return super().__call__(retry_state)
```

### 6.3 Error Translation

LLM errors are translated into SkillNet's `AppError` hierarchy (see [backend-api.md](backend-api.md) section 4.4). The user never sees raw provider errors.

```python
# src/llm/errors.py

from openai import (
    AuthenticationError,
    NotFoundError,
    BadRequestError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from src.core.exceptions import AppError


class LLMUnavailableError(AppError):
    """LLM provider is temporarily unavailable."""
    def __init__(self, detail: str = "LLM service is temporarily unavailable"):
        super().__init__(detail, "LLM_UNAVAILABLE", 502)


class LLMConfigError(AppError):
    """LLM configuration is invalid (wrong API key, model not found)."""
    def __init__(self, detail: str = "LLM configuration error"):
        super().__init__(detail, "LLM_CONFIG_ERROR", 503)


class LLMRateLimitError(AppError):
    """LLM provider rate limit exceeded."""
    def __init__(self, retry_after: float | None = None):
        detail = "LLM rate limit exceeded. Please try again shortly."
        super().__init__(detail, "LLM_RATE_LIMITED", 429)
        self.retry_after = retry_after


def translate_llm_error(exc: Exception) -> AppError:
    """Convert an openai SDK exception to a SkillNet AppError.

    This function is used AFTER retries are exhausted. The error
    reaching here is the final failure.

    Key principle: errors are 502/503 (upstream failure), not 500
    (our fault). Non-LLM features continue working.
    """
    if isinstance(exc, AuthenticationError):
        return LLMConfigError(
            "LLM API key is invalid. Check LLM_API_KEY in environment variables."
        )

    if isinstance(exc, NotFoundError):
        return LLMConfigError(
            "LLM model not found. Check LLM_MODEL in environment variables."
        )

    if isinstance(exc, BadRequestError):
        return LLMConfigError(
            f"Invalid request to LLM provider: {exc.message}"
        )

    if isinstance(exc, RateLimitError):
        retry_after = _get_retry_after(exc)
        return LLMRateLimitError(retry_after)

    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return LLMUnavailableError(
            "Cannot connect to LLM provider. Check network and LLM_BASE_URL."
        )

    if isinstance(exc, InternalServerError):
        return LLMUnavailableError(
            "LLM provider returned an internal error. The issue is on their end."
        )

    # Unknown error
    return LLMUnavailableError(f"Unexpected LLM error: {type(exc).__name__}")
```

### 6.4 Graceful Degradation

When the LLM is unavailable, SkillNet does not crash. Non-LLM features continue working normally:

| Feature | When LLM is down |
|---------|------------------|
| Login, navigation, settings | Work normally |
| Course listing, enrollment | Work normally |
| Deterministic exercises (test, true/false, fill blank) | Grade normally (no LLM needed) |
| Progress tracking, spaced repetition scheduling | Work normally |
| Skills matrix, reports | Work normally |
| Tutor chat | Returns error: "El tutor no esta disponible en este momento" |
| Practical case evaluation | Returns error: "La evaluacion no esta disponible" |
| Course generation | Fails gracefully: job status = "failed", admin notified |
| Document processing | Embedding step fails, status = "error", admin can retry |

The principle: **502/503 (upstream failure), never 500 (our bug).** The client receives a clear error message and knows the issue is the LLM provider, not SkillNet.

---

## 7. Local LLM Support

SkillNet's provider-agnostic design means local LLMs work with the same interface -- change the URL, keep the code.

### 7.1 Configuration

| Provider | `LLM_BASE_URL` | Model example | Notes |
|----------|----------------|---------------|-------|
| **Ollama** | `http://localhost:11434/v1` | `llama3.1`, `qwen2.5`, `mistral` | Ollama exposes an OpenAI-compatible `/v1` endpoint. No API key needed (set `LLM_API_KEY=ollama`). |
| **LM Studio** | `http://localhost:1234/v1` | `lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF` | LM Studio's local server is OpenAI-compatible out of the box. No API key needed (set `LLM_API_KEY=lm-studio`). |
| **vLLM** | `http://localhost:8000/v1` | `meta-llama/Meta-Llama-3.1-8B-Instruct` | vLLM for production-grade local serving with batching. |
| **text-generation-webui** | `http://localhost:5000/v1` | (loaded model) | Oobabooga's web UI also exposes an OpenAI-compatible endpoint. |

Example `.env` for a fully local setup:

```bash
# Chat model via Ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.1

# Embeddings via Ollama
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIMENSIONS=384
```

### 7.2 Model Considerations

Local models have different characteristics than cloud APIs. The LLM integration layer handles these differences:

#### Context Window

Local models typically have smaller context windows (4K-8K for GGUF quantized models, though some support 32K-128K). The `fit_messages_to_context` function (section 5.2) handles this automatically -- if the configured model has a known smaller window, history is truncated more aggressively.

For unknown local models, the conservative default of 8,192 tokens is used. The admin can override by adding the model to `CONTEXT_WINDOWS` in the configuration.

#### JSON Output Reliability

Cloud APIs (OpenAI, DeepSeek) support structured output modes (`response_format={"type": "json_object"}`). Local models may not support this parameter, or may produce malformed JSON.

SkillNet handles this with a fallback JSON extraction function:

```python
# src/llm/parsing.py

import json
import re


def extract_json_from_response(text: str) -> dict | list | None:
    """Extract JSON from an LLM response, handling common local model issues.

    Tries, in order:
    1. Direct parse (response is pure JSON)
    2. Extract from markdown code block (```json ... ```)
    3. Find the first { ... } or [ ... ] block in the text
    4. Return None if no valid JSON found

    This function exists because local models (Ollama, LM Studio) may:
    - Wrap JSON in markdown code blocks
    - Add explanatory text before/after the JSON
    - Produce JSON with trailing commas (cleaned up)
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Markdown code block
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Find first JSON object or array
    # Look for balanced braces/brackets
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue

        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == start_char:
                depth += 1
            elif c == end_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    # Clean trailing commas before closing brace/bracket
                    candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    return None
```

#### Embedding Dimension Validation

When using local embedding models, the configured `EMBEDDING_DIMENSIONS` must match what the model actually produces. A mismatch causes pgvector insertion failures (vector dimension mismatch). SkillNet validates this at startup:

```python
# src/llm/startup.py

import logging

from src.llm.client import LLMClient
from src.llm.config import llm_settings

logger = logging.getLogger("skillnet.llm")


async def validate_embedding_config(llm: LLMClient) -> None:
    """Validate that the embedding model produces vectors matching
    the configured EMBEDDING_DIMENSIONS.

    Called during application startup (in the FastAPI lifespan handler).
    Raises RuntimeError if dimensions don't match, preventing the app
    from starting with a misconfigured embedding model.
    """
    try:
        test_embeddings = await llm.embed(["test embedding dimension validation"])
    except Exception as e:
        logger.warning(
            "Could not validate embedding dimensions at startup: %s. "
            "Embedding features may fail at runtime.",
            e,
        )
        return

    actual_dim = len(test_embeddings[0])
    expected_dim = llm_settings.EMBEDDING_DIMENSIONS

    if actual_dim != expected_dim:
        raise RuntimeError(
            f"Embedding dimension mismatch: model '{llm_settings.EMBEDDING_MODEL}' "
            f"produces {actual_dim}-dimensional vectors, but EMBEDDING_DIMENSIONS "
            f"is set to {expected_dim}. Update EMBEDDING_DIMENSIONS={actual_dim} "
            f"in your .env file, and ensure the document_chunks.embedding column "
            f"matches (vector({actual_dim}))."
        )

    logger.info(
        "Embedding config validated: model=%s, dimensions=%d",
        llm_settings.EMBEDDING_MODEL,
        actual_dim,
    )
```

Integration with the FastAPI lifespan:

```python
# src/main.py (lifespan handler addition)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Existing startup...
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    # Validate embedding configuration
    llm = LLMClient(llm_settings)
    await validate_embedding_config(llm)

    yield

    await engine.dispose()
```

### 7.3 Performance Comparison

Approximate performance for a tutor chat response (single question, 5 chunks in context, ~2000 token prompt, ~500 token response):

| Setup | Time to First Token | Full Response | Cost per Query |
|-------|-------------------|---------------|----------------|
| **Cloud API (GPT-4o-mini)** | ~300ms | ~2s | ~$0.001 |
| **Cloud API (DeepSeek-chat)** | ~500ms | ~3s | ~$0.0003 |
| **Local GPU (RTX 3060, Llama 3.1 8B)** | ~200ms | ~4s | $0.00 |
| **Local GPU (RTX 4090, Llama 3.1 8B)** | ~100ms | ~2s | $0.00 |
| **Local CPU (16GB RAM, Llama 3.1 8B Q4)** | ~2s | ~30s | $0.00 |
| **Local CPU (32GB RAM, Qwen 2.5 7B Q4)** | ~1.5s | ~25s | $0.00 |

**Recommendation:**
- **Development / testing:** Local via Ollama on CPU. Slow but free and offline.
- **Small deployment (< 10 concurrent users):** DeepSeek or local with a mid-range GPU.
- **Production deployment:** Cloud API (GPT-4o-mini or DeepSeek) for reliability and speed. Local GPU for organizations that cannot send data externally.

CPU-only local LLMs are viable for testing and low-traffic deployments. For concurrent users, a GPU or cloud API is strongly recommended.

---

## 8. File Layout

All LLM integration code lives under `src/llm/`. Agent definitions (LangGraph graphs) live under `src/agents/`. Prompts are nested under agents because they are agent-specific.

```
src/
├── llm/                          # LLM integration layer
│   ├── __init__.py
│   ├── config.py                 # LLMSettings, LLMUseCase enum
│   ├── client.py                 # LLMClient (chat, chat_stream, embed)
│   ├── tokens.py                 # count_tokens, count_messages_tokens (tiktoken)
│   ├── context.py                # fit_messages_to_context, CONTEXT_WINDOWS
│   ├── cost.py                   # estimate_generation_cost
│   ├── usage.py                  # log_usage, estimate_cost, COST_TABLE
│   ├── resilience.py             # with_retry, WaitRespectRetryAfter
│   ├── errors.py                 # LLMUnavailableError, LLMConfigError, translate_llm_error
│   ├── parsing.py                # extract_json_from_response
│   └── startup.py                # validate_embedding_config
│
├── deps/
│   ├── llm.py                    # get_llm_client FastAPI dependency
│   └── ...
│
├── agents/                       # LangGraph agent definitions
│   ├── __init__.py
│   ├── prompts/                  # All prompts (tutor, generator, evaluator, admin, shared)
│   │   ├── __init__.py
│   │   ├── tutor.py              # tutor_system_prompt()
│   │   ├── generator.py          # outline_prompt(), lesson_content_prompt(), exercise_prompt()
│   │   ├── evaluator.py          # practical_case_eval_prompt(), dialogue_eval_prompt()
│   │   ├── admin.py              # admin_system_prompt()
│   │   └── shared.py             # SAFETY_GUARDRAILS, CITATION_INSTRUCTIONS, LANGUAGE_DETECTION
│   ├── content/                  # Content generation pipeline (graph, nodes, state)
│   ├── tutor/                    # Tutor chat agent
│   └── admin/                    # Admin chat agent
│
├── services/
│   ├── chat_service.py           # Tutor/admin chat (uses LLMClient, yields SSE)
│   ├── generation_service.py     # Course generation (uses LLMClient, updates job status)
│   ├── exercise_service.py       # Exercise grading (uses LLMClient for practical/dialogue)
│   └── ...
│
└── routes/
    ├── chat.py                   # SSE streaming endpoints
    └── ...
```

### Module Responsibilities

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `llm/config.py` | Read env vars, resolve model per use case | pydantic-settings |
| `llm/client.py` | OpenAI SDK wrapper, 3 methods | openai, config |
| `llm/tokens.py` | Token counting | tiktoken |
| `llm/context.py` | Fit messages to context window | tokens |
| `llm/cost.py` | Estimate generation job cost | tokens, usage |
| `llm/usage.py` | Log usage to database, estimate cost | sqlalchemy |
| `llm/resilience.py` | Retry decorator, backoff strategy | tenacity, openai errors |
| `llm/errors.py` | Translate openai errors to AppError | openai, core.exceptions |
| `llm/parsing.py` | Extract JSON from messy LLM output | json, re |
| `llm/startup.py` | Validate embedding config at boot | client, config |

---

## What's decided vs what's deferred

| Decided | Deferred |
|---------|----------|
| OpenAI-compatible SDK for all providers | Fine-tuning / LoRA support |
| Per-use-case model overrides via env vars | Admin UI for model selection (env vars only for now) |
| tiktoken cl100k_base for token counting | Provider-specific tokenizer integration |
| Prompts in Python files (version controlled) | Prompt A/B testing framework |
| SSE streaming for chat, no streaming for structured output | WebSocket fallback for SSE |
| Retry with exponential backoff (tenacity) | Circuit breaker pattern |
| 502/503 for LLM failures, not 500 | Multi-provider failover (try provider B if A is down) |
| Embedding dimension validation at startup | Automatic dimension detection from pgvector column |
| Usage logging to PostgreSQL | Usage dashboard in admin UI |
| Cost estimation for generation jobs | Budget limits / spending caps |
| Local LLM support via same OpenAI-compatible interface | GPU detection / automatic model selection |
