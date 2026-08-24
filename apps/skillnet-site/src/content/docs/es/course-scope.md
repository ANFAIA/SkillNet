---
title: "Alcance de v1"
order: 12
section: "v2"
---

# v1 Scope & Decisions

> **Este documento define el producto v1 y tiene PRIORIDAD sobre los demas docs de design/ en
> cuestiones de v1.** Los otros docs fueron escritos para el producto completo (v1 + v2 + futuro).
>
> **Lo que ya no hace:** decidir el alcance del proyecto entero. v2 esta implementado
> (2026-07-27) y su documento de diseno —[`v2-dynamic-courses.md`](v2-dynamic-courses.md)— es
> el que manda en todo lo relativo a v2. Si este fichero y aquel se contradicen sobre v2, gana
> aquel.

---

## v1 vs v2

- **v1 (implementado, y lo que sirve produccion):** Generacion estatica de cursos. El admin sube un documento, la IA genera un curso en Markdown, se guarda en BD, se renderiza con react-markdown. El chatbot es dinamico (RAG). No hay personalizacion por usuario.
- **v2 (implementado, eleccion por curso):** Generacion dinamica. La IA genera la pantalla
  personalizada para cada aprendiz en el momento (perfil, nivel, ritmo). El MD de v1 sigue
  siendo la materia prima / seed, y ademas es el `fallback_seed` cuando la generacion falla.

  No hay flag global: `src/services/course_delivery.py::resolve_delivery` es el unico punto de
  decision, y sirve v2 solo cuando el curso tiene `delivery_mode='dynamic'` **y**
  `schema_status='validated'`. Cualquier otro curso —incluido cualquiera creado antes de v2—
  sigue por v1 sin cambios.

  **La regresion de v1 con el flag apagado es la invariante del proyecto**
  (`tests/integration/test_v1_regression.py`). Por tanto: todo lo que este documento dice sobre
  v1 sigue vigente, palabra por palabra. Lo unico que ha caducado es el "NO implementar".

---

## Decisiones cerradas

### Contenido y formato

- **Markdown como unico formato de contenido.** La IA genera cursos en MD. Nunca JSON para contenido narrativo.
- **Ejercicios en tabla aparte.** El MD lleva solo contenido narrativo. Los ejercicios van en la tabla `exercises` con datos estructurados (tipo, pregunta, opciones, respuesta correcta, explicacion). El frontend renderiza el MD con react-markdown y monta componentes de ejercicio desde la BD.
- **Sin SNML.** La spec de SNML (`snml-spec.md`) fue una exploracion. No se usa en v1 ni v2. Ignorarla.
- **RAG nunca toca el PDF.** El PDF se parsea y se estructura primero. RAG opera sobre texto limpio, no sobre el PDF original.

### Generacion de cursos

- **LangGraph SI, desde v1.** El pipeline de generacion usa LangGraph con agentes especializados.
- **Sin human-in-the-loop en v1.** El admin dispara la generacion y el pipeline es autonomo. No hay pausas para revision intermedia. El admin revisa el resultado final.
- **Pipeline:** prepare_context → extract_themes → design_structure → generate_modules (paralelo) → review_quality → refine (si falla, max 2 ciclos) → publish.
- **Agentes:** Extractor (temas), Architect (estructura), Module Generator (contenido MD por modulo), Quality Reviewer (revision), Refiner (correccion).
- **Modos de ingesta:** desde documentos (PDF), desde catalogo (pre-hechos), mixto, desde cero (solo tema).

### Chatbot

- **RAG simple + memoria conversacional.** No LangGraph para el chat en v1.
- **Funcionalidad:** el empleado pregunta, se buscan chunks relevantes con RAG, se incluye historial de la conversacion, se responde.
- **Sin herramientas, sin razonamiento multi-paso.** Solo: historial + contexto RAG + system prompt → LLM → respuesta.

### LLM y providers

- **litellm** para abstraccion de providers. Soporta OpenAI, Anthropic, DeepSeek, Ollama, Google, Mistral, etc.
- **Modelo configurable por env vars.** Ningun servicio sabe que provider hay detras.
- **Embeddings igualmente configurables** por env vars.

### Infraestructura

- **Auth:** Session cookies con CookieTransport (fastapi-users). No JWT.
- **Docker:** 3 servicios (db: pgvector:pg16, api: FastAPI, web: React + nginx).
- **Sin Redis, sin Celery.** PostgreSQL para todo.

---

## Contradicciones con otros docs

| Doc | Dice | v1 |
|-----|------|-----|
| `content-generation.md` | 2 checkpoints human-in-the-loop | **Sin human-in-the-loop.** Pipeline autonomo |
| `snml-spec.md` | Formato SNML para contenido | **Ignorar.** SNML descartado |
| `backend-api.md` | openai SDK directo | **Usar litellm** |
| `llm-integration.md` | openai SDK, provider-specific | **Usar litellm** |
| `data-model.md` | 27 tablas | **~14 para v1** (ver scope abajo) |
| `backend-api.md` | 73 endpoints | **~30 para v1** |
| `chat-agents.md` | Chat con herramientas y LangGraph | **Chat simple:** RAG + memoria, sin LangGraph |
| Varios | Ejercicios en MD (bloques :::) | **Ejercicios en tabla `exercises`**, MD solo narrativo |

---

## Scope v1: lo que se implementa

- Organizaciones, usuarios, auth (login/logout/session)
- Upload de documentos, parsing de PDF a texto
- Chunking + embeddings para RAG (pgvector)
- Pipeline de generacion con LangGraph (agentes especializados)
- Cursos: CRUD, modulos, lecciones (MD), ejercicios (tabla)
- Enrollments: asignar cursos a empleados
- Ejercicios: enviar respuesta, grading determinista
- Chatbot: RAG + memoria conversacional + streaming SSE
- Docker Compose: db + api + web
- Frontend: reemplazar mock data con API real, react-markdown para contenido

## Scope v1: lo que NO se implementa

- Skills, skill categories, skill checkpoints
- Manuales como formato separado
- Spaced repetition
- Webhooks, API keys, audit log
- SNML
- Human-in-the-loop en generacion
- Personalizacion on-the-fly (v2)
- MCP server externo
</content>
