# SkillNet API — v1 Build Decisions (authoritative)

This file is the single source of truth for the v1 backend. It resolves every
open decision and pins the exact scope. It has priority over the general design
docs (`docs/design/*`) wherever they differ, second only to
`docs/design/v1-scope.md`. Read this before writing any code.

## Stack & tooling

- Python 3.12, managed with `uv` (`pyproject.toml` + `uv.lock`).
- FastAPI (async), SQLAlchemy 2.0 async ORM, asyncpg driver, Alembic (async).
- fastapi-users[sqlalchemy] with **CookieTransport + DatabaseStrategy** (session
  cookies, 7-day expiry). No JWT.
- Pydantic v2 + pydantic-settings.
- LLM: **litellm** (`litellm.acompletion` / `litellm.aembedding`). Never the
  openai SDK directly. Provider chosen entirely by env vars.
- Generation pipeline: **LangGraph** (`langgraph`). In-memory `MemorySaver`
  checkpointer for v1 (no Postgres checkpointer dependency — keeps it simple;
  jobs are short-lived and tracked in our own `generation_jobs` table).
- PDF parsing: `pypdf` (pure-Python, no system libs — Docker-friendly). TXT/MD
  built-in. DOCX best-effort via `python-docx` if present, else unsupported.
- Tokenizing/chunking: `tiktoken` (cl100k_base) for counts.
- Tests: `pytest` + `pytest-asyncio`. Unit tests must NOT require a live DB or
  network. DB/integration tests are marked `@pytest.mark.integration` and skipped
  when `DATABASE_URL` is unreachable.
- Lint/format: `ruff`. Type-check: strict type hints everywhere (mypy-friendly).

## Layering (strict)

`HTTP request -> route -> service -> repository -> model/DB` and back.

- **routes/**: parse HTTP, validate via Pydantic schema, call service, return
  schema. Owns `db.commit()`. No SQL, no business rules.
- **services/**: business rules, orchestration. Receive deps via constructor
  (repos, llm, embeddings). No HTTP, no raw SQL, no `commit()`.
- **repositories/**: SQLAlchemy queries only. Return ORM instances / rows. No
  business logic.
- **models/**: ORM mapping + relationships only.
- **schemas/**: Pydantic request/response. No DB awareness.
- **deps/**: FastAPI dependency providers (db session, current user, llm,
  embeddings). No business logic.
- **core/**: exceptions, security, pagination, logging.

Dependency inversion: services never import global singletons; everything is
injected. Functions pure where possible (grading, chunking, routing).

## Background jobs

No Redis, no Celery. Generation runs via `asyncio.create_task` fired from the
`POST /courses/{id}/generate` route. A module-level `TaskRegistry` keeps strong
references to running tasks so they aren't GC'd. Status is tracked in
`generation_jobs`. Progress streamed via an in-process pub/sub (asyncio.Queue
per job) consumed by the SSE endpoint.

## Error handling

Domain exceptions in `core/exceptions.py` (`AppError` + subclasses
`NotFoundError`, `ForbiddenError`, `ConflictError`, `ValidationError`,
`LLMError`). Global handlers in `main.py` map them to the JSON envelope
`{"detail","code","field"}`. Services raise; routes never `except: pass`.

## Logging & observability

`structlog`-free: stdlib `logging` configured in `core/logging.py`, level from
`LOG_LEVEL`. Each generation node logs step transitions. No llm_usage_log table
in v1 (deferred).

## Data model — v1 tables (13)

Only these tables exist in v1. Everything else in `data-model.md` is deferred.

1. `organizations`
2. `users`  (fastapi-users base + org_id, full_name, role, learning_profile,
   accessibility, hired_at, is_active). PK `id uuid`. Uses fastapi-users column
   names: `email`, `hashed_password`, `is_active`, `is_superuser`, `is_verified`.
   Add domain columns. `role` enum(admin, employee).
3. `documents`
4. `document_chunks` (vector(384), tsvector spanish, ivfflat + gin indexes)
5. `courses`
6. `modules`
7. `lessons`
8. `exercises`
9. `enrollments`
10. `exercise_attempts`
11. `generation_jobs` (result_manual_id kept nullable but unused in v1)
12. `chat_sessions`
13. `chat_messages`

**Dropped from v1** (do not create): skills, skill_categories, user_skills,
skill_checkpoints, spaced_repetition, course_feedback, manuals, background_jobs,
user_sessions (fastapi-users DatabaseStrategy uses its own `accesstoken` table
via fastapi-users-db-sqlalchemy — that's fine), audit_log, api_keys, webhooks,
webhook_deliveries, llm_usage_log.

Note: fastapi-users DatabaseStrategy needs an access-token table
(`AccessTokenTable`). Include it — it replaces the custom `user_sessions` table.

Enums: `user_role`, `learning_profile`, `document_status`, `content_status`,
`exercise_type`, `enrollment_status`, `generation_output`, `generation_step`.
Match `data-model.md` DDL exactly for columns and constraints of included tables.

## Content format

- Lesson narrative content = **Markdown** (`lessons.content text`).
- Exercises = structured rows in `exercises` (`content jsonb`, `type` enum).
  Never embed exercises in the lesson MD.
- Manual generation is **skipped** in v1 (no manuals table). Generation output
  is course-only. `generation_jobs.output_type` is always `course_and_manual`
  in the enum but the pipeline produces only the course; `result_manual_id`
  stays null.

## Generation pipeline (LangGraph) — v1

Autonomous, NO human-in-the-loop. Nodes:

`prepare_context -> extract_themes -> design_structure -> generate_modules
(parallel, bounded semaphore) -> review_quality -> (refine_content if fail,
max 2 cycles, loop back to review_quality) -> publish`

On any node exception -> `handle_error` terminal node (job status=failed).
No `interrupt_before`. No admin checkpoints. Agents: Extractor, Architect,
Module Generator, Quality Reviewer, Refiner. All LLM calls go through the
`LLMService` (litellm) with tenacity retries. JSON parsing via a robust parser
with recovery. `publish` writes course+modules+lessons+exercises with
status=draft; admin publishes separately.

RAG mode inside the pipeline:
- single doc, <=5 pages -> `full_text` (whole text in prompts, no embeddings).
- else -> `chunked` (retrieve from document_chunks; extractor maps themes to
  chunk_ids; module generator uses those + semantic supplement).

## RAG / retrieval — v1

- Ingestion (`POST /documents/{id}/process`): parse -> clean -> decide mode.
  <=3 pages: store `full_text`, status ready, no chunks. >3 pages: semantic
  chunk (512 tok max, 2-sentence overlap, contextual prefix) -> embed (litellm
  aembedding, batched) -> store chunks. status ready/error.
- Embedding dim from `EMBEDDING_DIMENSIONS` (default 384). vector column is
  fixed at 384 in the migration (matches multilingual-e5-small default).
- Chat retrieval: embed query -> `document_chunks` cosine similarity top-k
  (org-scoped) -> assemble context block with citations -> litellm streaming.
- Reranking, hybrid RRF, PageIndex: **deferred** (semantic only in v1).

## Chat — v1

RAG + conversational memory. NO LangGraph, no tools. `POST /chat` body
`{message, session_id?, context?}`. Creates/loads a `chat_sessions` row
(agent_type='tutor'), stores user + assistant `chat_messages`, retrieves RAG
context, builds prompt = system + last N messages + context block + question,
streams tokens via SSE (`token`, `citations`, `done`, `error` events). Admin
chat (`/chat/admin`) deferred/optional — v1 focuses on tutor chat.

## Exercise grading — v1

Deterministic for `test`, `true_false`, `fill_blank`, `order_steps` (compare
against `content` correct answer; score 0/1, passed = score==1). `practical_case`
and `dialogue`: LLM-graded via litellm against the rubric; if no LLM configured,
return a graceful 0.5 "needs review" style result rather than crashing. Store
every attempt in `exercise_attempts`.

## Endpoints — v1 (~34)

Prefix `/api/v1`. Cookie auth on all except login & health.

Auth: `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`
Health: `GET /health`
Users: `GET /users` (admin), `POST /users` (admin, create employee),
  `GET /users/{id}` (admin), `PUT /users/{id}` (admin),
  `GET /users/me`, `PUT /users/me`
Documents: `GET /documents` (admin), `POST /documents` (admin, multipart),
  `GET /documents/{id}` (admin), `DELETE /documents/{id}` (admin),
  `POST /documents/{id}/process` (admin)
Courses: `GET /courses`, `POST /courses` (admin),
  `GET /courses/{id}` (nested modules/lessons/exercises),
  `PUT /courses/{id}` (admin), `DELETE /courses/{id}` (admin),
  `POST /courses/{id}/generate` (admin), `POST /courses/{id}/publish` (admin),
  `POST /courses/{id}/archive` (admin)
Exercises: `POST /exercises/{id}/attempt` (employee),
  `GET /exercises/{id}/attempts`
Enrollments: `GET /enrollments`, `POST /enrollments` (admin),
  `GET /enrollments/{id}`, `DELETE /enrollments/{id}` (admin)
Generation jobs: `GET /generation-jobs/{id}` (admin),
  `GET /generation-jobs/{id}/progress` (admin, SSE)
Chat: `POST /chat` (employee, SSE), `GET /chat/sessions`,
  `GET /chat/sessions/{id}/messages`
Settings: `GET /settings` (admin), `PUT /settings/llm` (admin),
  `POST /settings/llm/test` (admin)

Enrollment/progress: employee sees a course only if enrolled (GET /courses/{id}
enforces). Progress = completed_modules/total_modules; a module is complete when
every exercise in its lessons has a passing attempt by the user.

## Config (env vars) — see config.py

DATABASE_URL, SECRET_KEY (>=32 chars, enforced), SESSION_LIFETIME_SECONDS=604800,
COOKIE_NAME=skillnet_session, COOKIE_SECURE (bool), LLM_BASE_URL, LLM_API_KEY,
LLM_MODEL, LLM_GENERATION_MODEL?, LLM_TUTOR_MODEL?, LLM_EVAL_MODEL?,
EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS=384,
UPLOAD_DIR, MAX_UPLOAD_SIZE_MB=50, DEBUG, CORS_ORIGINS, LOG_LEVEL, ENVIRONMENT,
ADMIN_EMAIL?, ADMIN_PASSWORD?, ORG_NAME?.

LLM/embeddings resolve org-settings override first, then env var default.

## Startup (lifespan)

1. ensure upload dir. 2. run alembic `upgrade head`. 3. ensure single org row
(from ORG_NAME or default). 4. maybe create admin from ADMIN_EMAIL/PASSWORD.
Idempotent. No JobCoordinator process (asyncio tasks per request instead).

## Naming & style

snake_case Python, PascalCase classes, descriptive names, short single-purpose
functions, full type hints, no dead code, no obvious comments, no `Any` without
justification. Every module has a clear single responsibility.
