---
title: "v1 scope"
order: 12
section: "v2"
---

# v1 Scope & Decisions

> **This document defines the v1 product and takes PRIORITY over the other docs in design/
> on v1 matters.** The other docs were written for the complete product (v1 + v2 + future).
>
> **What it no longer does:** decide the scope of the entire project. v2 is implemented
> (2026-07-27) and its design document —[`v2-dynamic-courses.md`](v2-dynamic-courses.md)— is
> the one that governs everything related to v2. If this file and that one contradict each
> other about v2, that one wins.

---

## v1 vs v2

- **v1 (implemented, and what serves production):** Static course generation. The admin
  uploads a document, the AI generates a course in Markdown, it's saved in the DB, and it's
  rendered with react-markdown. The chatbot is dynamic (RAG). There is no per-user
  personalization.
- **v2 (implemented, chosen per course):** Dynamic generation. The AI generates the
  personalized screen for each learner on the fly (profile, level, pace). The v1 MD remains
  the raw material / seed, and it also acts as the `fallback_seed` when generation fails.

  There is no global flag: `src/services/course_delivery.py::resolve_delivery` is the only
  decision point, and it serves v2 only when the course has `delivery_mode='dynamic'` **and**
  `schema_status='validated'`. Any other course —including any created before v2— continues
  to be served by v1 unchanged.

  **v1 regression with the flag off is the project's invariant**
  (`tests/integration/test_v1_regression.py`). Therefore: everything this document says about
  v1 still holds, word for word. The only thing that has expired is the "DO NOT implement".

---

## Closed decisions

### Content and format

- **Markdown as the only content format.** The AI generates courses in MD. Never JSON for
  narrative content.
- **Exercises in a separate table.** The MD carries only narrative content. Exercises live in
  the `exercises` table with structured data (type, question, options, correct answer,
  explanation). The frontend renders the MD with react-markdown and mounts exercise
  components from the DB.
- **No SNML.** The SNML spec (`snml-spec.md`) was an exploration. It is not used in v1 or v2.
  Ignore it.
- **RAG never touches the PDF.** The PDF is parsed and structured first. RAG operates on
  clean text, not on the original PDF.

### Course generation

- **LangGraph YES, since v1.** The generation pipeline uses LangGraph with specialized agents.
- **No human-in-the-loop in v1.** The admin triggers generation and the pipeline is
  autonomous. There are no pauses for intermediate review. The admin reviews the final result.
- **Pipeline:** prepare_context → extract_themes → design_structure → generate_modules
  (parallel) → review_quality → refine (up to 2 cycles on failure) → publish.
- **Agents:** Extractor (themes), Architect (structure), Module Generator (per-module MD
  content), Quality Reviewer (review), Refiner (correction).
- **Ingestion modes:** from documents (PDF), from catalog (pre-built), mixed, from scratch
  (topic only).

### Chatbot

- **Simple RAG + conversational memory.** No LangGraph for chat in v1.
- **Functionality:** the employee asks, relevant chunks are retrieved with RAG, conversation
  history is included, and it answers.
- **No tools, no multi-step reasoning.** Just: history + RAG context + system prompt → LLM →
  answer.

### LLM and providers

- **litellm** for provider abstraction. Supports OpenAI, Anthropic, DeepSeek, Ollama, Google,
  Mistral, etc.
- **Model configurable via env vars.** No service knows which provider is behind it.
- **Embeddings are equally configurable** via env vars.

### Infrastructure

- **Auth:** Session cookies with CookieTransport (fastapi-users). No JWT.
- **Docker:** 3 services (db: pgvector:pg16, api: FastAPI, web: React + nginx).
- **No Redis, no Celery.** PostgreSQL for everything.

---

## Contradictions with other docs

| Doc | Says | v1 |
|-----|------|-----|
| `content-generation.md` | 2 human-in-the-loop checkpoints | **No human-in-the-loop.** Autonomous pipeline |
| `snml-spec.md` | SNML format for content | **Ignore.** SNML dropped |
| `backend-api.md` | direct openai SDK | **Use litellm** |
| `llm-integration.md` | openai SDK, provider-specific | **Use litellm** |
| `data-model.md` | 27 tables | **~14 for v1** (see scope below) |
| `backend-api.md` | 73 endpoints | **~30 for v1** |
| `chat-agents.md` | Chat with tools and LangGraph | **Simple chat:** RAG + memory, no LangGraph |
| Various | Exercises in MD (`:::` blocks) | **Exercises in the `exercises` table**, MD narrative only |

---

## v1 scope: what gets implemented

- Organizations, users, auth (login/logout/session)
- Document upload, PDF-to-text parsing
- Chunking + embeddings for RAG (pgvector)
- Generation pipeline with LangGraph (specialized agents)
- Courses: CRUD, modules, lessons (MD), exercises (table)
- Enrollments: assign courses to employees
- Exercises: submit answer, deterministic grading
- Chatbot: RAG + conversational memory + SSE streaming
- Docker Compose: db + api + web
- Frontend: replace mock data with the real API, react-markdown for content

## v1 scope: what is NOT implemented

- Skills, skill categories, skill checkpoints
- Manuals as a separate format
- Spaced repetition
- Webhooks, API keys, audit log
- SNML
- Human-in-the-loop generation
- On-the-fly personalization (v2)
- External MCP server
