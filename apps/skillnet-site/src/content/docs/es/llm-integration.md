---
title: "Capa de integración con LLM"
order: 7
section: "core"
---

# Capa de integración con LLM

> **Estado: v1.** Arquitectura completa de integración con LLM para SkillNet. Cubre la abstracción de proveedor, la integración con LangGraph, la gestión de prompts, el streaming, la gestión de coste/tokens, el manejo de errores y el soporte de LLM local. Alineado con [architecture.md](/docs/architecture), [backend-api.md](/docs/backend-api) y [rag-retrieval.md](/docs/rag-retrieval).

---

## 1. Abstracción de proveedor

SkillNet no depende de ningún proveedor de LLM concreto. El backend habla con una única interfaz -- base URL + clave de API + nombre de modelo -- usando el SDK de Python `openai`. Cualquier API compatible con OpenAI funciona sin más (OpenAI, DeepSeek, Groq, Together, Mistral, local vía Ollama/LM Studio, etc.). No hay código específico de proveedor en la lógica de negocio.

### 1.1 Variables de entorno

Dos grupos: uno para modelos de chat/completion, otro para modelos de embeddings. Las sobrescrituras de modelo por caso de uso permiten ejecutar modelos distintos para tareas distintas (por ejemplo, un modelo barato para tutoría y uno más potente para generación).

#### Chat / Completion

| Variable | Valor por defecto | Descripción |
|----------|---------|-------------|
| `LLM_BASE_URL` | `https://api.openai.com/v1` | URL base para la API compatible con OpenAI |
| `LLM_API_KEY` | `""` | Clave de API para autenticación |
| `LLM_MODEL` | `gpt-4o-mini` | Modelo por defecto para todos los casos de uso |
| `LLM_GENERATION_MODEL` | (recae en `LLM_MODEL`) | Modelo para generación de curso/manual (puede interesar más capacidad de razonamiento) |
| `LLM_TUTOR_MODEL` | (recae en `LLM_MODEL`) | Modelo para el chat del tutor (puede interesar más rapidez/economía) |
| `LLM_EVAL_MODEL` | (recae en `LLM_MODEL`) | Modelo para evaluación de ejercicios (puede interesar más fiabilidad de salida estructurada) |

#### Embeddings

| Variable | Valor por defecto | Descripción |
|----------|---------|-------------|
| `EMBEDDING_BASE_URL` | (recae en `LLM_BASE_URL`) | URL base separada para embeddings (proveedor distinto o local) |
| `EMBEDDING_API_KEY` | (recae en `LLM_API_KEY`) | Clave de API separada para el proveedor de embeddings |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Nombre del modelo de embeddings |
| `EMBEDDING_DIMENSIONS` | `384` | Dimensiones de embedding esperadas. Debe coincidir con el ancho de la columna de pgvector |

> **Requisito de prefijo E5:** El modelo `intfloat/multilingual-e5-small` (y toda la familia E5) requiere prefijos específicos en el texto de entrada: anteponer `"query: "` para las consultas de búsqueda y `"passage: "` para los documentos que se indexan. Ver los ayudantes `LLMClient.embed_query()` y `LLMClient.embed_passages()` en la sección 1.3.

La separación entre la configuración de chat y la de embeddings existe porque las organizaciones suelen usar proveedores distintos para cada cosa: una API en la nube para chat (OpenAI, DeepSeek) y un modelo local para embeddings (multilingual-e5-small vía Ollama), o al revés.

### 1.2 Configuración de LLMSettings

Clase de Pydantic Settings que lee las variables de entorno, ofrece cadenas de respaldo y resuelve el modelo correcto para cada caso de uso.

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

**Por qué Pydantic Settings:** Coherente con el resto del patrón de configuración de SkillNet (ver `src/config.py` en [backend-api.md](/docs/backend-api)). Valida tipos en el arranque, lee ficheros `.env` y ofrece acceso tipado sin parsear strings a mano.

### 1.3 LLMClient

Una envoltura fina sobre `AsyncOpenAI` que ofrece tres métodos: `chat()`, `chat_stream()` y `embed()`. La envoltura existe para centralizar la resolución de modelo, los parámetros por defecto y el manejo de errores. Los servicios nunca instancian `AsyncOpenAI` directamente.

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

**Por qué no usar `AsyncOpenAI` directamente en los servicios:** Tres razones. Primero, la resolución de modelo por caso de uso quedaría dispersa en cada punto de llamada. Segundo, la lógica de reintentos y la traducción de errores (sección 6) envuelven al cliente. Tercero, la testabilidad -- los servicios dependen de `LLMClient`, que se puede sustituir por un doble en los tests.

### 1.4 Inyección de dependencias

El `LLMClient` se inyecta en los manejadores de ruta a través del sistema `Depends()` de FastAPI, coherente con el patrón existente para sesiones de base de datos y autenticación.

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

Uso en rutas:

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

## 2. Integración con LangGraph

LangGraph gestiona las máquinas de estados de los agentes. Cada tipo de agente (tutor, generador de contenido, evaluador) es un grafo con nodos y aristas definidos. Los nodos del grafo llaman a métodos de `LLMClient` -- no instancian sus propias conexiones LLM.

### 2.1 Dataclasses de estado

Cada tipo de agente tiene un estado tipado que fluye por el grafo. Los estados son dataclasses (no diccionarios) por seguridad de tipos y soporte del IDE.

Las definiciones de estado están en sus documentos de agente respectivos: ver [content-generation.md](/docs/content-generation) (`GenerationState`) y [chat-agents.md](/docs/chat-agents) (`TutorState`).

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

### 2.2 Patrón de nodo de grafo

Los nodos del grafo son funciones async que reciben el estado, llaman a `LLMClient` y devuelven actualizaciones de estado. Las dependencias (`LLMClient`, sesión de base de datos) se inyectan mediante closures al construir el grafo -- no a través de `config["configurable"]` ni a través del estado (que debe seguir siendo serializable).

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

### 2.3 Streaming de LangGraph a SSE

Para el chat orientado al usuario, el grafo del tutor usa `chat_stream()` en lugar de `chat()`. El generador async fluye desde LangGraph, a través de `StreamingResponse` de FastAPI, hasta el cliente como Server-Sent Events.

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

## 3. Gestión de prompts

### 3.1 Decisiones de diseño

| Decisión | Justificación |
|----------|-----------|
| **Prompts en ficheros Python, no en base de datos** | Control de versiones con git. Revisión de código en los cambios de prompt. No hace falta migración para actualizar un prompt. Rollback = git revert. |
| **f-strings para plantillas** | Sin dependencia adicional de motor de plantillas. Los f-strings de Python son legibles y comprobables por tipos. Jinja2 añadiría complejidad sin beneficio a esta escala. |
| **Un directorio por tipo de agente** | Propiedad clara. Un desarrollador que busque el prompt de sistema del tutor va a `agents/prompts/tutor.py`. |
| **Módulo compartido para instrucciones transversales** | Las salvaguardas de seguridad, el formato de citación y la detección de idioma son iguales en todos los agentes. DRY. |

### 3.2 Estructura de directorios

```
src/agents/prompts/
    __init__.py
    tutor.py          # Tutor system prompt, follow-up prompts
    generator.py      # Course generation: outline, module, lesson, exercise
    evaluator.py      # Exercise grading: practical_case, dialogue
    admin.py          # Admin assistant system prompt
    shared.py         # Safety guardrails, citation instructions, language detection
```

### 3.3 Plantillas de prompt

#### Instrucciones compartidas de seguridad y citación

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

# SUSTITUIDA el 2026-07-27 para el tutor: la segunda regla ("di exactamente: No tengo
# informacion...") es la que hacia que el tutor rechazara todas las preguntas en la demo.
# Los prompts vivos estan en src/llm/prompts/tutor.py, donde la persona se mantiene a
# traves de tres estados de fundamentacion y el ultimo responde con conocimiento general
# y lo dice. Las otras cinco reglas sobreviven ahi, reformuladas. Ver docs/design/chat-agents.md.

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

#### Prompt de sistema del tutor

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

#### Prompts del generador

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

#### Prompts del evaluador

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

#### Prompt del asistente administrativo

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

### 3.4 Resumen de temperatura y formato

| Agente | Caso de uso | Temperatura | Formato de salida |
|-------|----------|-------------|---------------|
| Tutor | Respuesta de chat | 0.3 | Texto plano + citas |
| Tutor | Sugerencia de seguimiento | 0.8 | Texto plano |
| Generador | Esquema de curso | 0.3 | JSON |
| Generador | Contenido de lección | 0.3 | Markdown |
| Generador | Creación de ejercicios | 0.3 | JSON |
| Evaluador | Corrección de caso práctico | 0.2 | JSON |
| Evaluador | Evaluación de diálogo | 0.2 | JSON |
| Admin | Respuesta del asistente | 0.5 | Texto plano |
| Ingesta | Resumen de documento | 0.2 | Texto plano |

### 3.5 Pruebas de prompts

Los prompts se pueden probar de forma aislada sin levantar la aplicación completa. Cada función de prompt devuelve un string -- sin efectos secundarios, sin E/S.

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

## 4. Arquitectura de streaming

### 4.1 Flujo de extremo a extremo

Streaming token a token del LLM al navegador:

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

### 4.2 Tipos de eventos SSE

Tres tipos de eventos, mantenidos al mínimo:

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

| Evento | Cuándo | Payload |
|-------|------|---------|
| `token` | Cada token del LLM | `{"content": "<texto del token>"}` |
| `done` | El LLM terminó de generar | `{"message_id": "<uuid>", "citations": [...]}` |
| `error` | Cualquier error durante el streaming | `{"message": "<mensaje orientado al usuario>"}` |

### 4.3 Implementación en el servidor

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

### 4.4 Implementación en el cliente

El frontend de React usa `ReadableStream` (no `EventSource`) porque la petición inicial es un POST con cuerpo, algo que `EventSource` no soporta.

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

### 4.5 Detección de desconexión del cliente

Si el usuario navega fuera o cierra la pestaña mientras el LLM sigue generando, el servidor lo detecta y detiene el stream. Esto evita malgastar tokens de LLM en peticiones abandonadas.

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

La llamada `request.is_disconnected()` es barata (comprueba el estado de la conexión ASGI). No añade latencia relevante al stream.

### 4.6 Cuándo NO usar streaming

El streaming se usa solo para la salida conversacional orientada al usuario. Para la salida JSON estructurada, se necesita la respuesta completa antes de procesarla:

| Endpoint | ¿Streaming? | Por qué |
|----------|-----------|-----|
| Chat del tutor | Sí | El usuario ve los tokens según llegan |
| Chat del admin | Sí | Misma justificación |
| Evaluación de ejercicios | No | La respuesta debe ser JSON válido, parseado como un todo |
| Generación de cursos | No | Cada paso produce datos estructurados para el siguiente paso |
| Resumen de documentos | No | El resumen lo consume el sistema, no se muestra de forma incremental |

---

## 5. Gestión de coste y tokens

### 5.1 Conteo de tokens

SkillNet usa `tiktoken` con la codificación `cl100k_base` como aproximación universal para contar tokens. Esta codificación es suficientemente cercana para los modelos de OpenAI y sirve como estimación razonable para otros proveedores (DeepSeek, Groq, etc.). El recuento exacto de tokens es específico de cada proveedor, pero la aproximación es suficiente para la gestión de presupuesto y las decisiones de truncamiento.

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

### 5.2 Gestión de la ventana de contexto

El uso más crítico del conteo de tokens es encajar los mensajes en la ventana de contexto del modelo. La función `fit_messages_to_context` garantiza que el prompt de sistema nunca se trunca, mientras que el historial de conversación se recorta empezando por los mensajes más antiguos.

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

### 5.3 Seguimiento de uso

El uso del LLM se registra en una tabla de base de datos para monitorización y análisis de coste. No es facturación en tiempo real -- es una herramienta de observabilidad para el administrador.

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

### 5.4 Estimación de coste para trabajos de generación

Antes de iniciar un trabajo de generación de curso, el sistema estima el coste total en tokens para que el administrador pueda tomar una decisión informada.

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

## 6. Manejo de errores

### 6.1 Estrategia de reintentos

Las llamadas a la API del LLM son intrínsecamente poco fiables (problemas de red, límites de tasa, caídas del proveedor). SkillNet usa la librería `tenacity` para la lógica de reintentos con backoff exponencial.

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

Aplicado a los métodos de `LLMClient`:

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

### 6.2 Manejo de límites de tasa

Cuando el proveedor de LLM devuelve 429 (rate limited), la cabecera `Retry-After` indica cuánto esperar. El SDK de `openai` lo maneja automáticamente vía `RateLimitError`, y el backoff exponencial de `tenacity` cubre el timing de reintento. Para los casos en los que la cabecera `Retry-After` especifica una espera más larga:

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

### 6.3 Traducción de errores

Los errores del LLM se traducen a la jerarquía `AppError` de SkillNet (ver [backend-api.md](/docs/backend-api) sección 4.4). El usuario nunca ve errores en bruto del proveedor.

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

### 6.4 Degradación elegante

Cuando el LLM no está disponible, SkillNet no se cae. Las funcionalidades que no dependen del LLM siguen funcionando con normalidad:

| Funcionalidad | Cuando el LLM está caído |
|---------|------------------|
| Login, navegación, ajustes | Funcionan con normalidad |
| Listado de cursos, matriculación | Funcionan con normalidad |
| Ejercicios deterministas (test, verdadero/falso, rellenar huecos) | Se corrigen con normalidad (no necesitan LLM) |
| Seguimiento de progreso, planificación de repetición espaciada | Funcionan con normalidad |
| Matriz de habilidades, informes | Funcionan con normalidad |
| Chat del tutor | Devuelve error: "El tutor no esta disponible en este momento" |
| Evaluación de casos prácticos | Devuelve error: "La evaluacion no esta disponible" |
| Generación de cursos | Falla de forma controlada: estado del trabajo = "failed", se notifica al admin |
| Procesamiento de documentos | Falla el paso de embedding, estado = "error", el admin puede reintentar |

El principio: **502/503 (fallo aguas arriba), nunca 500 (fallo nuestro).** El cliente recibe un mensaje de error claro y sabe que el problema es del proveedor de LLM, no de SkillNet.

---

## 7. Soporte de LLM local

El diseño agnóstico de proveedor de SkillNet implica que los LLM locales funcionan con la misma interfaz -- se cambia la URL, se mantiene el código.

### 7.1 Configuración

| Proveedor | `LLM_BASE_URL` | Ejemplo de modelo | Notas |
|----------|----------------|---------------|-------|
| **Ollama** | `http://localhost:11434/v1` | `llama3.1`, `qwen2.5`, `mistral` | Ollama expone un endpoint `/v1` compatible con OpenAI. No hace falta clave de API (poner `LLM_API_KEY=ollama`). |
| **LM Studio** | `http://localhost:1234/v1` | `lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF` | El servidor local de LM Studio es compatible con OpenAI de fábrica. No hace falta clave de API (poner `LLM_API_KEY=lm-studio`). |
| **vLLM** | `http://localhost:8000/v1` | `meta-llama/Meta-Llama-3.1-8B-Instruct` | vLLM para servir localmente en producción con batching. |
| **text-generation-webui** | `http://localhost:5000/v1` | (modelo cargado) | La web UI de Oobabooga también expone un endpoint compatible con OpenAI de fábrica. |

Ejemplo de `.env` para una configuración totalmente local:

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

### 7.2 Consideraciones sobre el modelo

Los modelos locales tienen características distintas a las API en la nube. La capa de integración con el LLM gestiona estas diferencias:

#### Ventana de contexto

Los modelos locales suelen tener ventanas de contexto más pequeñas (4K-8K para modelos GGUF cuantizados, aunque algunos soportan 32K-128K). La función `fit_messages_to_context` (sección 5.2) lo gestiona automáticamente -- si el modelo configurado tiene una ventana conocida menor, el historial se trunca de forma más agresiva.

Para modelos locales desconocidos, se usa el valor conservador por defecto de 8.192 tokens. El administrador puede sobrescribirlo añadiendo el modelo a `CONTEXT_WINDOWS` en la configuración.

#### Fiabilidad de la salida JSON

Las API en la nube (OpenAI, DeepSeek) soportan modos de salida estructurada (`response_format={"type": "json_object"}`). Los modelos locales pueden no soportar este parámetro, o pueden producir JSON malformado.

SkillNet lo gestiona con una función de extracción de JSON de respaldo:

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

#### Validación de la dimensión de embedding

Al usar modelos de embedding locales, el `EMBEDDING_DIMENSIONS` configurado debe coincidir con lo que el modelo produce realmente. Un desajuste provoca fallos de inserción en pgvector (vector dimension mismatch). SkillNet lo valida en el arranque:

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

Integración con el lifespan de FastAPI:

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

### 7.3 Comparativa de rendimiento

Rendimiento aproximado para una respuesta de chat del tutor (una pregunta, 5 fragmentos en el contexto, prompt de ~2000 tokens, respuesta de ~500 tokens):

| Configuración | Tiempo hasta el primer token | Respuesta completa | Coste por consulta |
|-------|-------------------|---------------|----------------|
| **API en la nube (GPT-4o-mini)** | ~300ms | ~2s | ~$0.001 |
| **API en la nube (DeepSeek-chat)** | ~500ms | ~3s | ~$0.0003 |
| **GPU local (RTX 3060, Llama 3.1 8B)** | ~200ms | ~4s | $0.00 |
| **GPU local (RTX 4090, Llama 3.1 8B)** | ~100ms | ~2s | $0.00 |
| **CPU local (16GB RAM, Llama 3.1 8B Q4)** | ~2s | ~30s | $0.00 |
| **CPU local (32GB RAM, Qwen 2.5 7B Q4)** | ~1.5s | ~25s | $0.00 |

**Recomendación:**
- **Desarrollo / pruebas:** Local vía Ollama en CPU. Lento pero gratuito y sin conexión.
- **Despliegue pequeño (< 10 usuarios concurrentes):** DeepSeek o local con una GPU de gama media.
- **Despliegue en producción:** API en la nube (GPT-4o-mini o DeepSeek) por fiabilidad y velocidad. GPU local para organizaciones que no pueden enviar datos al exterior.

Los LLM locales solo con CPU son viables para pruebas y despliegues de bajo tráfico. Para usuarios concurrentes, se recomienda encarecidamente una GPU o una API en la nube.

---

## 8. Organización de ficheros

Todo el código de integración con el LLM vive bajo `src/llm/`. Las definiciones de agente (grafos de LangGraph) viven bajo `src/agents/`. Los prompts se anidan dentro de agents porque son específicos de cada agente.

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

### Responsabilidades de los módulos

| Módulo | Responsabilidad | Dependencias |
|--------|---------------|--------------|
| `llm/config.py` | Leer variables de entorno, resolver el modelo por caso de uso | pydantic-settings |
| `llm/client.py` | Envoltura del SDK de OpenAI, 3 métodos | openai, config |
| `llm/tokens.py` | Conteo de tokens | tiktoken |
| `llm/context.py` | Encajar mensajes en la ventana de contexto | tokens |
| `llm/cost.py` | Estimar el coste de un trabajo de generación | tokens, usage |
| `llm/usage.py` | Registrar uso en base de datos, estimar coste | sqlalchemy |
| `llm/resilience.py` | Decorador de reintento, estrategia de backoff | tenacity, errores de openai |
| `llm/errors.py` | Traducir errores de openai a AppError | openai, core.exceptions |
| `llm/parsing.py` | Extraer JSON de salidas desordenadas del LLM | json, re |
| `llm/startup.py` | Validar la configuración de embedding en el arranque | client, config |

---

## Qué está decidido vs qué está pospuesto

| Decidido | Pospuesto |
|---------|----------|
| SDK compatible con OpenAI para todos los proveedores | Soporte de fine-tuning / LoRA |
| Sobrescrituras de modelo por caso de uso vía variables de entorno | UI de admin para seleccionar modelo (por ahora solo variables de entorno) |
| tiktoken cl100k_base para el conteo de tokens | Integración de tokenizador específico de proveedor |
| Prompts en ficheros Python (control de versiones) | Framework de pruebas A/B de prompts |
| Streaming SSE para chat, sin streaming para salida estructurada | Alternativa por WebSocket para SSE |
| Reintento con backoff exponencial (tenacity) | Patrón de circuit breaker |
| 502/503 para fallos del LLM, no 500 | Failover multi-proveedor (probar el proveedor B si A está caído) |
| Validación de la dimensión de embedding en el arranque | Detección automática de dimensión desde la columna de pgvector |
| Registro de uso en PostgreSQL | Panel de uso en la UI de admin |
| Estimación de coste para trabajos de generación | Límites de presupuesto / topes de gasto |
| Soporte de LLM local vía la misma interfaz compatible con OpenAI | Detección de GPU / selección automática de modelo |
</content>
</invoke>
