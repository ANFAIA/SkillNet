---
title: "v1 scope"
order: 12
section: "v2"
---

# v1 Scope & Decisions

> **This document defines the v1 product and has PRIORITY over the other design/ docs on
> v1 matters.** The other docs were written for the complete product (v1 + v2 + future).
>
> **What it no longer does:** decide the scope of the entire project. v2 is implemented
> (2026-07-27) and its design document — [`v2-dynamic-courses.md`](v2-dynamic-courses.md) — is
> the one that governs everything related to v2. If this file and that one contradict each other
> about v2, that one wins.

---

## v1 vs v2

- **v1 (implemented, and what serves production):** Static course generation. The admin uploads a
  document, the AI generates a course in Markdown, it's saved to the DB, and rendered with
  react-markdown. The chatbot is dynamic (RAG). There is no per-user personalization.
- **v2 (implemented, chosen per course):** Dynamic generation. The AI generates the personalized
  screen for each learner on the fly (profile, level, pace). v1's MD remains the raw material /
  seed, and is also the `fallback_seed` when generation fails.

  There is no global flag: `src/services/course_delivery.py::resolve_delivery` is the single
  decision point, and it serves v2 only when the course has `delivery_mode='dynamic'` **and**
  `schema_status='validated'`. Any other course — including any created before v2 — keeps
  running through v1 unchanged.

  **v1's regression with the flag off is the project's invariant**
  (`tests/integration/test_v1_regression.py`). Therefore: everything this document says about
  v1 remains in force, word for word. The only thing that expired is the "do NOT implement".

---

## Closed decisions

### Content and format

- **Markdown as the only content format.** The AI generates courses in MD. Never JSON for
  narrative content.
- **Exercises in a separate table.** The MD carries only narrative content. Exercises go in the
  `exercises` table with structured data (type, question, options, correct answer, explanation).
  The frontend renders the MD with react-markdown and mounts exercise components from the DB.
- **No SNML.** The SNML spec (`snml-spec.md`) was an exploration. It is not used in v1 or v2.
  Ignore it.
- **RAG never touches the PDF.** The PDF is parsed and structured first. RAG operates on clean
  text, not on the original PDF.

### Course generation

- **LangGraph, YES, since v1.** The generation pipeline uses LangGraph with specialized agents.
- **No human-in-the-loop in v1.** The admin triggers generation and the pipeline is autonomous.
  There are no pauses for intermediate review. The admin reviews the final result.
- **Pipeline:** prepare_context → extract_themes → design_structure → generate_modules (parallel)
  → review_quality → refine (if it fails, max 2 cycles) → publish.
- **Agents:** Extractor (themes), Architect (structure), Module Generator (MD content per module),
  Quality Reviewer (review), Refiner (correction).
- **Ingestion modes:** from documents (PDF), from catalog (pre-made), mixed, from scratch (topic
  only).

### Chatbot

- **Simple RAG + conversational memory.** No LangGraph for chat in v1.
- **Functionality:** the employee asks, relevant chunks are retrieved with RAG, conversation
  history is included, an answer is returned.
- **No tools, no multi-step reasoning.** Only: history + RAG context + system prompt → LLM →
  response.

### LLM and providers

- **litellm** for provider abstraction. Supports OpenAI, Anthropic, DeepSeek, Ollama, Google,
  Mistral, etc.
- **Model configurable via env vars.** No service knows which provider is behind it.
- **Embeddings equally configurable** via env vars.

### Infrastructure

- **Auth:** Session cookies with CookieTransport (fastapi-users). No JWT.
- **Docker:** 3 services (db: pgvector:pg16, api: FastAPI, web: React + nginx).
- **No Redis, no Celery.** PostgreSQL for everything.

---

## Contradictions with other docs

| Doc | Says | v1 |
|-----|------|-----|
| `content-generation.md` | 2 human-in-the-loop checkpoints | **No human-in-the-loop.** Autonomous pipeline |
| `snml-spec.md` | SNML format for content | **Ignore.** SNML discarded |
| `backend-api.md` | direct openai SDK | **Use litellm** |
| `llm-integration.md` | openai SDK, provider-specific | **Use litellm** |
| `data-model.md` | 27 tables | **~14 for v1** (see scope below) |
| `backend-api.md` | 73 endpoints | **~30 for v1** |
| `chat-agents.md` | Chat with tools and LangGraph | **Simple chat:** RAG + memory, no LangGraph |
| Various | Exercises in MD (::: blocks) | **Exercises in the `exercises` table**, MD is narrative only |

---

## v1 Scope: what is implemented

- Organizations, users, auth (login/logout/session)
- Document upload, PDF-to-text parsing
- Chunking + embeddings for RAG (pgvector)
- Generation pipeline with LangGraph (specialized agents)
- Courses: CRUD, modules, lessons (MD), exercises (table)
- Enrollments: assigning courses to employees
- Exercises: submitting an answer, deterministic grading
- Chatbot: RAG + conversational memory + SSE streaming
- Docker Compose: db + api + web
- Frontend: replacing mock data with the real API, react-markdown for content

## v1 Scope: what is NOT implemented

- Skills, skill categories, skill checkpoints
- Manuals as a separate format
- Spaced repetition
- Webhooks, API keys, audit log
- SNML
- Human-in-the-loop in generation
- On-the-fly personalization (v2)
- External MCP server
