## 4. Backend API Architecture

> **Status: v1.** Complete backend structure for `apps/skillnet-api/`. Aligns with [data-model.md](data-model.md), [screens.md](screens.md), and [architecture.md](architecture.md).

---

### 4.1 Project Layout

```
apps/skillnet-api/
├── pyproject.toml                  # uv project, dependencies
├── alembic.ini                     # DB migrations config
├── alembic/
│   ├── env.py
│   └── versions/                   # Migration files
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app factory, lifespan, middleware
│   ├── config.py                   # Pydantic Settings (env vars)
│   │
│   ├── auth/                       # Authentication (fastapi-users)
│   │   ├── __init__.py
│   │   ├── backend.py              # CookieTransport + session strategy
│   │   ├── manager.py              # UserManager (create, verify, etc.)
│   │   ├── schemas.py              # UserRead, UserCreate, UserUpdate
│   │   └── router.py               # /auth/login, /auth/logout, /auth/me
│   │
│   ├── models/                     # SQLAlchemy ORM models (1 file per table)
│   │   ├── __init__.py             # Re-exports all models
│   │   ├── base.py                 # DeclarativeBase, common mixins (TimestampMixin, UUIDMixin)
│   │   ├── organization.py
│   │   ├── user.py                 # Extends fastapi-users SQLAlchemy model
│   │   ├── document.py
│   │   ├── document_chunk.py
│   │   ├── skill.py
│   │   ├── skill_category.py
│   │   ├── course.py
│   │   ├── module.py
│   │   ├── lesson.py
│   │   ├── exercise.py
│   │   ├── skill_checkpoint.py
│   │   ├── manual.py
│   │   ├── enrollment.py
│   │   ├── exercise_attempt.py
│   │   ├── user_skill.py
│   │   ├── spaced_repetition.py
│   │   ├── generation_job.py
│   │   ├── course_feedback.py
│   │   ├── chat_session.py
│   │   ├── chat_message.py
│   │   ├── background_job.py
│   │   ├── user_session.py
│   │   ├── audit_log.py
│   │   ├── api_key.py
│   │   ├── webhook.py
│   │   └── webhook_delivery.py
│   │
│   ├── repositories/               # Data access layer (async SQLAlchemy queries)
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseRepository[T] — generic CRUD
│   │   ├── user_repo.py
│   │   ├── document_repo.py
│   │   ├── course_repo.py          # Includes nested module/lesson/exercise loading
│   │   ├── enrollment_repo.py
│   │   ├── exercise_attempt_repo.py
│   │   ├── skill_repo.py           # Skills + categories + user_skills + matrix query
│   │   ├── manual_repo.py
│   │   ├── spaced_repetition_repo.py
│   │   ├── generation_job_repo.py
│   │   ├── course_feedback_repo.py
│   │   ├── document_chunk_repo.py  # Vector similarity search
│   │   ├── chat_session_repo.py
│   │   ├── chat_message_repo.py
│   │   ├── background_job_repo.py
│   │   ├── user_session_repo.py
│   │   ├── audit_log_repo.py
│   │   ├── api_key_repo.py
│   │   ├── webhook_repo.py
│   │   └── webhook_delivery_repo.py
│   │
│   ├── services/                   # Business logic (no DB or HTTP awareness)
│   │   ├── __init__.py
│   │   ├── user_service.py         # Invite, bulk invite, deactivate
│   │   ├── document_service.py     # Upload to disk, trigger processing
│   │   ├── course_service.py       # CRUD, publish/archive lifecycle
│   │   ├── enrollment_service.py   # Assign, progress calc, complete
│   │   ├── exercise_service.py     # Grade attempt, auto-check, AI-graded
│   │   ├── skill_service.py        # Matrix, mentorship suggestions, verify_skill
│   │   ├── manual_service.py       # CRUD, linked to course
│   │   ├── spaced_repetition_service.py  # HLR algorithm, due reviews, submit review
│   │   ├── generation_service.py   # Orchestrate generation pipeline
│   │   ├── chat_service.py         # Tutor + admin chat (RAG + streaming)
│   │   ├── alert_service.py        # Compute alerts from progress data
│   │   ├── stats_service.py        # Dashboard aggregations
│   │   └── feedback_service.py     # Submit + revision report generation
│   │
│   ├── routes/                     # FastAPI routers (thin — validate, call service, return)
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── documents.py
│   │   ├── courses.py              # Includes /generate, /publish, /archive actions
│   │   ├── modules.py              # Nested under courses
│   │   ├── lessons.py              # Nested under modules
│   │   ├── exercises.py            # Includes /attempt action
│   │   ├── enrollments.py
│   │   ├── skills.py               # Categories, skills, matrix, mentorship
│   │   ├── manuals.py
│   │   ├── chat.py                 # SSE endpoints (tutor + admin)
│   │   ├── spaced_repetition.py
│   │   ├── generation_jobs.py
│   │   ├── stats.py                # /stats, /alerts
│   │   ├── settings.py             # Org settings, LLM config
│   │   └── feedback.py
│   │
│   ├── schemas/                    # Pydantic models for request/response
│   │   ├── __init__.py
│   │   ├── common.py               # Pagination, ErrorResponse, SuccessMessage
│   │   ├── user.py
│   │   ├── document.py
│   │   ├── course.py               # Includes nested module/lesson/exercise schemas
│   │   ├── enrollment.py
│   │   ├── exercise.py             # AttemptRequest, AttemptResponse, by exercise type
│   │   ├── skill.py                # SkillMatrix, MentorshipSuggestion
│   │   ├── manual.py
│   │   ├── chat.py                 # ChatMessage, ChatEvent (SSE)
│   │   ├── spaced_repetition.py
│   │   ├── generation_job.py
│   │   ├── stats.py                # DashboardStats, Alert
│   │   ├── settings.py
│   │   └── feedback.py
│   │
│   ├── deps/                       # FastAPI dependency injection
│   │   ├── __init__.py
│   │   ├── db.py                   # get_async_session
│   │   ├── auth.py                 # current_user, current_active_user, require_admin
│   │   ├── llm.py                  # get_llm_client
│   │   └── embedding.py            # get_embedding_service
│   │
│   ├── llm/                        # LLM integration (provider-agnostic)
│   │   ├── __init__.py
│   │   ├── client.py               # AsyncOpenAI wrapper, reads env vars
│   │   ├── prompts/                # Prompt templates as .py or .txt
│   │   │   ├── tutor_system.py
│   │   │   ├── admin_system.py
│   │   │   ├── grading.py          # Exercise evaluation prompts
│   │   │   └── generation.py       # Course/manual generation prompts
│   │   └── embedding.py            # Embedding service (API or local model)
│   │
│   ├── agents/                     # LangGraph agent definitions (deferred — Phase 2+)
│   │   ├── __init__.py
│   │   ├── content_agent.py        # Multi-step generation pipeline
│   │   └── tutor_agent.py          # Conversational RAG tutor
│   │
│   └── core/                       # Shared utilities
│       ├── __init__.py
│       ├── exceptions.py           # App-specific exception classes
│       ├── security.py             # Password hashing, cookie config
│       └── pagination.py           # Offset pagination helper
│
├── tests/
│   ├── conftest.py                 # Fixtures: async client, test DB, test user
│   ├── factories.py                # Factory Boy factories for test data
│   ├── test_auth.py
│   ├── test_users.py
│   ├── test_courses.py
│   ├── test_enrollments.py
│   ├── test_exercises.py
│   ├── test_skills.py
│   ├── test_chat.py
│   └── test_spaced_repetition.py
│
├── uploads/                        # Uploaded documents (Docker volume mount)
└── Dockerfile
```

**Layer responsibilities:**

| Layer | What it does | What it does NOT do |
|-------|-------------|---------------------|
| **routes/** | Parse HTTP, validate input (Pydantic), call service, return response | Business logic, DB queries |
| **services/** | Business rules, orchestration, algorithm logic | SQL, HTTP concerns |
| **repositories/** | SQL queries via SQLAlchemy, return model instances | Business logic, HTTP |
| **models/** | ORM table mapping, relationships | Business logic, validation |
| **schemas/** | Request/response validation, serialization | DB awareness |
| **deps/** | Inject shared resources into route handlers | Business logic |

**Data flow:** `HTTP request -> route -> service -> repository -> database` and back. Each layer only talks to its immediate neighbor.

---

### 4.2 API Endpoints

All endpoints prefixed with `/api/v1`. Authentication via session cookie on every request (except login).

#### Auth

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/auth/login` | public | Email + password. Sets httpOnly session cookie (7-day expiry). Returns user data + role |
| `POST` | `/auth/logout` | authenticated | Deletes session. Clears cookie |
| `GET` | `/auth/me` | authenticated | Returns current user (id, email, full_name, role, learning_profile, accessibility) plus the deployment's `workspace_mode` |

Login response redirects by role: employee -> `/dashboard`, admin -> `/admin`. The frontend reads the role from `/auth/me` on page load.

**Workspace mode.** `/auth/me` (and `/settings`) also carry `workspace_mode`
(`organization` \| `individual`; see [audience-modes.md](audience-modes.md)). In an
`individual` deployment the collective, organization-only endpoints — employees
(list/create/reset), talent, `/stats`, course assignment (`POST`/`DELETE
/enrollments`, folder assign) and the skills catalogue — return **404** via the
`require_organization_workspace` dependency: those concepts do not exist in a
personal workspace. This is server-side enforcement; the SPA additionally hides
the sections as UX.

#### Users

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/users` | admin | List all users in org. Supports `?search=`, `?role=`, `?is_active=`. Returns summary stats (active courses count, skill coverage %) |
| `GET` | `/users/{id}` | admin | Single user detail with skills, enrollments, activity |
| `POST` | `/users/invite` | admin | Create employee account. Body: `{email, full_name}`. Generates temp password or invite link |
| `POST` | `/users/invite/bulk` | admin | CSV upload (name, email columns). Returns created count + errors |
| `PUT` | `/users/{id}` | admin | Update user (name, role, is_active). Admin can deactivate |
| `GET` | `/users/me` | authenticated | Current user profile |
| `PUT` | `/users/me` | authenticated | Update own profile (full_name, learning_profile, accessibility). Cannot change role or email |
| `PUT` | `/users/me/password` | authenticated | Change own password. Body: `{current_password, new_password}` |
| `GET` | `/users/me/today` | employee | "What's due today": spaced repetition reviews, next course action, recommendation. Max 3 items |
| `GET` | `/users/me/skills` | employee | Own skill levels grouped by category |
| `GET` | `/users/me/activity` | employee | Recent activity (exercise attempts, lessons completed). Paginated, default last 20 |

#### Learner profile (personalization)

Router `src/routes/learner_profile.py`, prefix `/users/me/learner-profile`. See
[`personalization.md`](personalization.md).

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/users/me/learner-profile` | authenticated | Read the learner profile, incl. `learning_note` and `learning_preferences` |
| `PATCH` | `/users/me/learner-profile` | authenticated | Update editable fields incl. the free-text `learning_note` (max 500 chars, normalized; steers form not facts). Writing it drops that learner's render pins |
| `DELETE` | `/users/me/learner-profile` | authenticated | Clear the profile |

#### Media artifacts

Router `src/routes/media.py`, prefix `/media`. See [`media-artifacts.md`](media-artifacts.md).

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/media/artifacts` | generator | Enqueue one media job. Body `MediaArtifactCreate` incl. `kind`, `scope` (`node\|course\|standalone`) and a personalization `note`. Returns `202 {artifact_id, status}`. Permission via `can_generate_artifacts` |
| `GET` | `/media/artifacts` | authenticated | List artefacts. Query `course_id` (required), `node_id`, `include_nodes`. Three shapes: one node / all course / course-level only |
| `GET` | `/media/artifacts/{id}` | authenticated | Single artefact |
| `GET` | `/media/artifacts/{id}/stream` | authenticated | SSE on channel `media:{id}`: `media_step` events then terminal `media_done`/`media_error` |
| `GET` | `/media/artifacts/{id}/asset` | authenticated | Rendered asset bytes, or 404 |
| `GET` | `/media/artifacts/{id}/asset/{ref}` | authenticated | One sub-asset by content-hash (`ref` must be a sha256 the spec lists) |

#### Course schema (create flow)

Router `src/routes/course_schema.py`. Admin course-schema lifecycle: propose -> PUT (spawn
packs) -> review -> validate -> prewarm. See [`create-course-flow`](create-course-flow.html)
and [`learning-experience-architecture.md`](learning-experience-architecture.md).

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/courses/{course_id}/schema/propose` | admin | `202` + `job_id`. Propose a schema draft |
| `PUT` | `/courses/{course_id}/schema` | admin | Persist the edited schema; spawns knowledge packs (bounded retry `max_attempts=3`); bumping `schema_version` supersedes any in-flight run for an earlier version |
| `POST` | `/courses/{course_id}/schema/review` | admin | Bulk-mark every non-archived node human-reviewed (the wizard calls it right before validate) |
| `POST` | `/courses/{course_id}/schema/nodes/{node_id}/review` | admin | Mark one node reviewed. `reviewed_at` is a serving precondition; render returns `409 node_not_reviewed` otherwise |
| `POST` | `/courses/{course_id}/schema/validate` | admin | Validate the schema; on commit spawns background prewarm of the first nodes' shared renders |

#### Documents

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/documents` | admin | List uploaded documents. Supports `?status=` filter |
| `POST` | `/documents` | admin | Upload file (multipart/form-data). Saves to disk, creates DB record with status=`pending` |
| `GET` | `/documents/{id}` | admin | Document metadata + processing status |
| `DELETE` | `/documents/{id}` | admin | Delete document and its chunks (CASCADE) |
| `POST` | `/documents/{id}/process` | admin | Trigger ingestion pipeline: parse, chunk, embed. Updates status through `processing` -> `ready` or `error` |

#### Courses

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/courses` | admin | List all courses. Supports `?status=draft,published,archived` |
| `POST` | `/courses` | admin | Create empty course shell. Body: `{title, description, outcome, source_document_id?}` |
| `GET` | `/courses/{id}` | authenticated | Full course with modules, lessons, exercises (nested). Employee sees only if enrolled |
| `PUT` | `/courses/{id}` | admin | Update course metadata (title, description, outcome) |
| `DELETE` | `/courses/{id}` | admin | Delete course (only if status=`draft` and no enrollments) |
| `POST` | `/courses/{id}/generate` | admin | Trigger AI generation from source document. Creates generation_job. Returns job_id for polling |
| `POST` | `/courses/{id}/publish` | admin | Set status=`published`. Validates: title, outcome, at least 1 module with 1 lesson |
| `POST` | `/courses/{id}/archive` | admin | Set status=`archived`. Active enrollments marked completed |

#### Modules

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/courses/{course_id}/modules` | authenticated | List modules for course, ordered by position |
| `POST` | `/courses/{course_id}/modules` | admin | Create module. Body: `{title, summary, position}` |
| `PUT` | `/courses/{course_id}/modules/{id}` | admin | Update module (title, summary, position) |
| `DELETE` | `/courses/{course_id}/modules/{id}` | admin | Delete module (CASCADE deletes lessons + exercises) |
| `PUT` | `/courses/{course_id}/modules/reorder` | admin | Batch reorder. Body: `{module_ids: [uuid, uuid, ...]}` |

#### Lessons

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/courses/{course_id}/modules/{module_id}/lessons` | authenticated | List lessons in module, ordered by position |
| `POST` | `/courses/{course_id}/modules/{module_id}/lessons` | admin | Create lesson. Body: `{title, content, position}` |
| `PUT` | `/courses/{course_id}/modules/{module_id}/lessons/{id}` | admin | Update lesson |
| `DELETE` | `/courses/{course_id}/modules/{module_id}/lessons/{id}` | admin | Delete lesson (CASCADE deletes exercises) |

#### Exercises

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/courses/{cid}/modules/{mid}/lessons/{lid}/exercises` | authenticated | List exercises in lesson |
| `POST` | `/courses/{cid}/modules/{mid}/lessons/{lid}/exercises` | admin | Create exercise. Body: `{type, content, position}` |
| `PUT` | `/exercises/{id}` | admin | Update exercise content or type |
| `DELETE` | `/exercises/{id}` | admin | Delete exercise |
| `POST` | `/exercises/{id}/attempt` | employee | Submit answer. Body varies by type (see below). Returns `{score, passed, feedback, explanation}` |
| `GET` | `/exercises/{id}/attempts` | authenticated | Attempt history for this exercise by current user. Admin can add `?user_id=` to see any user |

**Attempt request body by exercise type:**

```
test:           { "selected": 1 }
true_false:     { "answer": true }
fill_blank:     { "answers": ["unused", "tags"] }
order_steps:    { "order": [0, 2, 1, 3] }
practical_case: { "response": "I would explain the 30-day policy..." }
dialogue:       { "messages": [{"role": "user", "content": "..."}] }
```

For `test`, `true_false`, `fill_blank`, `order_steps`: server grades deterministically (compare against correct answer in exercise content).

For `practical_case`: server sends response + rubric to LLM for evaluation. Returns score + per-criteria feedback.

For `dialogue`: server runs multi-turn conversation via LLM with the system_prompt from exercise content. Evaluation after `max_turns` reached.

#### Enrollments

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/enrollments` | authenticated | Employee: own enrollments. Admin: all enrollments. Supports `?status=`, `?user_id=` (admin), `?course_id=` |
| `POST` | `/enrollments` | admin | Assign course to user(s). Body: `{user_ids: [uuid], course_id, deadline?}` |
| `GET` | `/enrollments/{id}` | authenticated | Enrollment detail with progress: modules completed, current position, score |
| `DELETE` | `/enrollments/{id}` | admin | Remove enrollment (only if status=`assigned`, not started) |
| `POST` | `/enrollments/{id}/complete` | system | Mark enrollment completed. Auto-triggered when all modules done. Updates score, completed_at |

Progress calculation: `completed_modules / total_modules`. A module is complete when all its lessons' exercises have at least one passing attempt.

#### Skills

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/skills/categories` | admin | List skill categories with skills |
| `POST` | `/skills/categories` | admin | Create category. Body: `{name, position}` |
| `PUT` | `/skills/categories/{id}` | admin | Update category (name, position) |
| `DELETE` | `/skills/categories/{id}` | admin | Delete category (only if no skills assigned) |
| `GET` | `/skills` | admin | List all skills. Supports `?category_id=` |
| `POST` | `/skills` | admin | Create skill. Body: `{name, description, category_id?}` |
| `PUT` | `/skills/{id}` | admin | Update skill |
| `DELETE` | `/skills/{id}` | admin | Delete skill (only if no user_skills or checkpoints reference it) |
| `GET` | `/skills/matrix` | admin | Full skills matrix: rows=employees, columns=skills, cells=level. Supports `?category_id=` filter |
| `GET` | `/skills/mentorship-suggestions` | admin | Auto-detected pairs: user with high level + user with low level on same skill |
| `POST` | `/skills/verify` | admin | Manually verify a skill. Body: `{user_id, skill_id, level, verifier_id?}`. Sets source=`manual` |
| `GET` | `/skills/{id}/users` | admin | Users who have this skill and their levels |
| `GET` | `/skills/gaps` | admin | Skills where no one (or too few) has high level. Body: `?threshold=` for minimum coverage |

#### Skill Checkpoints

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/courses/{course_id}/checkpoints` | admin | List skill checkpoints for course |
| `POST` | `/courses/{course_id}/checkpoints` | admin | Create checkpoint. Body: `{skill_id, module_id, target_level}` |
| `PUT` | `/courses/{course_id}/checkpoints/{id}` | admin | Update checkpoint |
| `DELETE` | `/courses/{course_id}/checkpoints/{id}` | admin | Delete checkpoint |

When a module is completed, the system checks for checkpoints and updates `user_skills` accordingly. Level never decreases from checkpoints (only admin override can lower it).

#### Chat (SSE)

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/chat` | employee | Send message to tutor. Body: `{message, context?: {course_id?, lesson_id?}}`. Returns SSE stream |
| `POST` | `/chat/admin` | admin | Send message to admin assistant. Body: `{message}`. Returns SSE stream |
| `GET` | `/chat/sessions` | authenticated | List current user's chat sessions. Paginated. Returns `{id, title, created_at, last_message_at}` |
| `GET` | `/chat/sessions/{id}/messages` | authenticated | Get messages for a session. Paginated. Returns `[{role, content, created_at, citations?}]` |
| `DELETE` | `/chat/sessions/{id}` | authenticated | Delete a chat session and its messages |

**SSE protocol:**

1. Client sends `POST /chat` with message body
2. Server returns `Content-Type: text/event-stream`
3. Server streams events:

```
event: token
data: {"content": "The"}

event: token
data: {"content": " return"}

event: citations
data: {"citations": [{"document": "Manual_Devoluciones.pdf", "section": "Plazos", "page": 3}]}

event: suggestions
data: {"prompts": ["What is the return window?", "How do I process a refund?"]}

event: done
data: {"message_id": "uuid"}

event: error
data: {"message": "Model unavailable"}
```

The tutor chat uses RAG: query is embedded, top-k chunks retrieved from `document_chunks`, included in the LLM context alongside the employee's current course/lesson context.

The admin chat has access to organization-wide data (employees, skills, enrollments) for operational queries.

#### Manuals

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/manuals` | authenticated | Employee: manuals from enrolled courses + standalone published manuals. Admin: all manuals |
| `POST` | `/manuals` | admin | Create manual. Body: `{title, content, source_document_id?, course_id?}` |
| `GET` | `/manuals/{id}` | authenticated | Full manual content. Employee must have access (enrolled in linked course or manual is standalone + published) |
| `PUT` | `/manuals/{id}` | admin | Update manual content |
| `DELETE` | `/manuals/{id}` | admin | Delete manual (only if status=`draft`) |
| `POST` | `/manuals/{id}/publish` | admin | Publish manual |
| `GET` | `/manuals/{id}/search` | authenticated | Search within manual content. Query param: `?q=` |

#### Spaced Repetition

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/spaced-repetition/due` | employee | Exercises due for review. Returns max 5, ordered by urgency (most overdue first) |
| `POST` | `/spaced-repetition/review` | employee | Submit review answer. Body: `{exercise_id, answer}`. Grades answer, updates half-life, schedules next review |
| `GET` | `/spaced-repetition/stats` | employee | Review stats: total reviews, streak, next review date |

The HLR algorithm runs on submit:
- Correct: `half_life *= 2`, `review_count += 1`
- Incorrect: `half_life /= 2`, `review_count += 1`
- `next_review_at` = now + time until `P(forget) > 0.3`

#### Generation Jobs

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/generation-jobs` | admin | List generation jobs. Supports `?status=` |
| `GET` | `/generation-jobs/{id}` | admin | Job detail with current step, timestamps, error message if failed |
| `POST` | `/generation-jobs/{id}/retry` | admin | Retry failed job from last successful step |
| `DELETE` | `/generation-jobs/{id}` | admin | Cancel pending/running job |
| `GET` | `/generation-jobs/{id}/review` | admin | Get pending review data (generated content awaiting approval) |
| `POST` | `/generation-jobs/{id}/review` | admin | Submit review decision. Body: `{action: "approve"|"reject", feedback?}` |
| `GET` | `/generation-jobs/{id}/progress` | admin | SSE stream of real-time generation progress events |
| `PUT` | `/generation-jobs/{id}/content` | admin | Inline content editing. Body: `{modules: [...]}`. Updates generated content before approval |
| `POST` | `/generation-jobs/{id}/regenerate-module/{idx}` | admin | Regenerate a single module by index. Body: `{feedback?}` |

**Generation pipeline steps:** `pending` -> `extracting` -> `structuring` -> `generating` -> `reviewing` -> `published` or `failed`.

Each step updates the job status. The frontend polls `GET /generation-jobs/{id}` to show progress.

#### Course Feedback

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/courses/{id}/feedback` | employee | Submit post-course feedback. Body: `{hardest_section, free_text, difficulty: "easy"|"ok"|"hard"}`. One per user per course |
| `GET` | `/courses/{id}/feedback` | admin | All feedback for course. Returns individual responses + aggregated report |
| `GET` | `/courses/{id}/feedback/report` | admin | AI-generated revision report: problematic sections, user quotes, difficulty stats, suggested changes |

#### Stats & Alerts

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/stats` | admin | Dashboard summary: total employees, active courses, critical gaps count, employees needing attention |
| `GET` | `/alerts` | admin | Active alerts (max 10). Types: deadline approaching with 0% progress, consecutive failures (3+), certificate expiring, new employee with no courses, skill decay |

Each alert includes:
```json
{
  "type": "deadline_risk",
  "severity": "high",
  "message": "Carlos has 0% progress on 'Returns' — deadline in 3 days",
  "action_url": "/admin/users/{user_id}",
  "related_ids": {"user_id": "...", "enrollment_id": "..."}
}
```

Alerts are computed on request (not stored). The service queries enrollments, attempts, and spaced_repetition to detect conditions.

#### Organization Settings

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/settings` | admin | Current org settings (name, self-registration flag, LLM config status) |
| `PUT` | `/settings` | admin | Update org settings. Body: `{name?, self_registration_enabled?}` |
| `PUT` | `/settings/llm` | admin | Update LLM config. Body: `{base_url, api_key, model}`. Validates connection before saving |
| `POST` | `/settings/llm/test` | admin | Test LLM connection without saving. Returns success/error |

#### Users — Invitations

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/users/invitations` | admin | List pending invitations. Supports `?status=pending,accepted,expired` |

#### Health

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/health` | public | System health check. Returns `{status: "ok", version, database: "connected"|"error"}` |

#### Admin — Background Jobs

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/admin/jobs` | admin | List background jobs. Supports `?status=`, `?type=`. Returns `{id, type, status, started_at, completed_at, error?}` |

LLM settings are stored in `organizations.settings` jsonb. Env vars (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`) are the defaults; org-level settings override them.

---

### 4.3 Dependency Injection

FastAPI's `Depends()` system provides shared resources to route handlers. All dependencies are defined in `src/deps/`.

#### Database Session

```python
# src/deps/db.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from src.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session

# Type alias for route signatures
DBSession = Annotated[AsyncSession, Depends(get_async_session)]
```

#### Current User (from session cookie)

fastapi-users provides the session cookie backend. The dependency chain extracts the user from the cookie automatically.

```python
# src/deps/auth.py
from fastapi_users import FastAPIUsers
from src.auth.backend import auth_backend
from src.auth.manager import get_user_manager
from src.models.user import User

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# Base dependencies (provided by fastapi-users)
current_user = fastapi_users.current_user(active=True)
current_optional_user = fastapi_users.current_user(active=True, optional=True)

# Type aliases
CurrentUser = Annotated[User, Depends(current_user)]
```

#### Role-Based Access

```python
# src/deps/auth.py (continued)
from fastapi import HTTPException, status

def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user

def require_employee(user: CurrentUser) -> User:
    if user.role != "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee access required",
        )
    return user

# Type aliases for route signatures
AdminUser = Annotated[User, Depends(require_admin)]
EmployeeUser = Annotated[User, Depends(require_employee)]
```

Usage in routes:

```python
# src/routes/courses.py
@router.get("/courses")
async def list_courses(user: AdminUser, db: DBSession):
    ...

@router.post("/exercises/{id}/attempt")
async def attempt_exercise(user: EmployeeUser, db: DBSession, ...):
    ...

@router.get("/courses/{id}")
async def get_course(user: CurrentUser, db: DBSession, ...):
    # Both roles can access, but employee sees only if enrolled
    ...
```

#### LLM Client

```python
# src/deps/llm.py
from openai import AsyncOpenAI
from src.config import settings

async def get_llm_client(db: DBSession) -> AsyncOpenAI:
    """Returns an AsyncOpenAI client configured from org settings or env vars."""
    # Check org-level override first
    org = await db.execute(select(Organization).limit(1))
    org_settings = org.scalar_one().settings

    base_url = org_settings.get("llm_base_url") or settings.LLM_BASE_URL
    api_key = org_settings.get("llm_api_key") or settings.LLM_API_KEY

    return AsyncOpenAI(base_url=base_url, api_key=api_key)

LLMClient = Annotated[AsyncOpenAI, Depends(get_llm_client)]
```

The `AsyncOpenAI` client works with any OpenAI-compatible API. The model name is resolved similarly (org setting > env var) and passed per-call, not at client creation.

#### Embedding Service

```python
# src/deps/embedding.py
from src.llm.embedding import EmbeddingService

async def get_embedding_service(db: DBSession) -> EmbeddingService:
    """Returns embedding service (API-based or local model)."""
    org = await db.execute(select(Organization).limit(1))
    org_settings = org.scalar_one().settings

    return EmbeddingService(
        base_url=org_settings.get("embedding_base_url") or settings.EMBEDDING_BASE_URL,
        api_key=org_settings.get("embedding_api_key") or settings.EMBEDDING_API_KEY,
        model=org_settings.get("embedding_model") or settings.EMBEDDING_MODEL,
    )

EmbeddingSvc = Annotated[EmbeddingService, Depends(get_embedding_service)]
```

#### Dependency Composition Example

A route handler composes what it needs:

```python
@router.post("/chat")
async def tutor_chat(
    user: EmployeeUser,
    db: DBSession,
    llm: LLMClient,
    embeddings: EmbeddingSvc,
    body: ChatMessageRequest,
):
    service = ChatService(db, llm, embeddings)
    return StreamingResponse(
        service.tutor_stream(user, body.message, body.context),
        media_type="text/event-stream",
    )
```

Services receive their dependencies through constructor injection (from the route handler), not through global state.

---

### 4.4 Error Handling

#### Error Response Format

Every error returns the same JSON shape:

```json
{
  "detail": "Course not found",
  "code": "NOT_FOUND",
  "field": null
}
```

For validation errors (422):

```json
{
  "detail": "Validation failed",
  "code": "VALIDATION_ERROR",
  "errors": [
    {"field": "email", "message": "Invalid email format"},
    {"field": "full_name", "message": "Required field"}
  ]
}
```

#### Application Exceptions

```python
# src/core/exceptions.py
class AppError(Exception):
    """Base application error."""
    def __init__(self, message: str, code: str, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code

class NotFoundError(AppError):
    def __init__(self, resource: str, id: str):
        super().__init__(f"{resource} not found", "NOT_FOUND", 404)

class ForbiddenError(AppError):
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, "FORBIDDEN", 403)

class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(message, "CONFLICT", 409)

class LLMError(AppError):
    def __init__(self, message: str = "LLM service unavailable"):
        super().__init__(message, "LLM_ERROR", 502)
```

#### Global Exception Handler

```python
# src/main.py
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, "field": None},
    )

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({"field": field, "message": error["msg"]})
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation failed", "code": "VALIDATION_ERROR", "errors": errors},
    )
```

#### HTTP Status Code Usage

| Status | When |
|--------|------|
| `200` | Success with response body |
| `201` | Resource created (POST that creates) |
| `204` | Success, no body (DELETE) |
| `400` | Bad request (business rule violation: "Cannot delete published course") |
| `401` | Not authenticated (no cookie or expired session) |
| `403` | Authenticated but wrong role |
| `404` | Resource not found |
| `409` | Conflict (duplicate email, enrollment already exists) |
| `413` | File too large (document upload) |
| `422` | Validation error (Pydantic) |
| `429` | Rate limited (future, for LLM endpoints) |
| `502` | LLM provider error (upstream failure) |

#### Validation Approach

1. **Pydantic schemas** validate request shape and types at the route layer
2. **Service layer** validates business rules (e.g., "course must have at least 1 module to publish")
3. **Database constraints** are the last line of defense (unique, FK, check constraints)

Services raise `AppError` subclasses. Routes never catch exceptions — the global handler does.

---

### 4.5 Database Access Layer

#### Engine and Session Setup

```python
# src/deps/db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(
    settings.DATABASE_URL,      # "postgresql+asyncpg://..."
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,     # Avoid lazy-load issues after commit
)
```

#### Base Model

```python
# src/models/base.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import text
from datetime import datetime
import uuid

class Base(DeclarativeBase):
    pass

class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
        onupdate=text("now()"),
    )
```

#### Model Example

```python
# src/models/course.py
from sqlalchemy import ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, UUIDMixin, TimestampMixin
import uuid
import enum

class ContentStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"

class Course(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "courses"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    title: Mapped[str]
    description: Mapped[str | None]
    outcome: Mapped[str | None]
    status: Mapped[ContentStatus] = mapped_column(
        SAEnum(ContentStatus, name="content_status"),
        default=ContentStatus.DRAFT,
    )

    # Relationships
    modules: Mapped[list["Module"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Module.position",
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="course")
    manual: Mapped["Manual | None"] = relationship(back_populates="course", uselist=False)
    checkpoints: Mapped[list["SkillCheckpoint"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )
```

#### Repository Pattern

```python
# src/repositories/base.py
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.base import Base
from typing import TypeVar, Generic, Sequence

T = TypeVar("T", bound=Base)

class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: uuid.UUID) -> T | None:
        return await self.session.get(self.model, id)

    async def get_or_404(self, id: uuid.UUID) -> T:
        obj = await self.get_by_id(id)
        if not obj:
            raise NotFoundError(self.model.__tablename__, str(id))
        return obj

    async def list(
        self,
        *,
        filters: list | None = None,
        order_by=None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[T], int]:
        query = select(self.model)
        count_query = select(func.count()).select_from(self.model)

        if filters:
            for f in filters:
                query = query.where(f)
                count_query = count_query.where(f)

        if order_by is not None:
            query = query.order_by(order_by)

        total = (await self.session.execute(count_query)).scalar_one()
        result = await self.session.execute(query.offset(offset).limit(limit))
        return result.scalars().all(), total

    async def create(self, **kwargs) -> T:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj: T, **kwargs) -> T:
        for key, value in kwargs.items():
            setattr(obj, key, value)
        await self.session.flush()
        return obj

    async def delete(self, obj: T) -> None:
        await self.session.delete(obj)
        await self.session.flush()
```

#### Specialized Repository Example

```python
# src/repositories/skill_repo.py
class SkillRepository(BaseRepository[Skill]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Skill)

    async def get_matrix(self, org_id: uuid.UUID, category_id: uuid.UUID | None = None):
        """Returns the full skills matrix: [{user, skill, level}, ...]"""
        query = (
            select(
                User.id.label("user_id"),
                User.full_name,
                Skill.id.label("skill_id"),
                Skill.name.label("skill_name"),
                UserSkill.level,
            )
            .select_from(User)
            .outerjoin(UserSkill, User.id == UserSkill.user_id)
            .outerjoin(Skill, UserSkill.skill_id == Skill.id)
            .where(User.org_id == org_id, User.is_active == True)
        )
        if category_id:
            query = query.where(Skill.category_id == category_id)

        result = await self.session.execute(query.order_by(User.full_name, Skill.name))
        return result.all()

    async def get_mentorship_suggestions(self, org_id: uuid.UUID):
        """Finds high-low skill pairs for mentorship."""
        query = (
            select(
                User.full_name.label("mentor_name"),
                User.id.label("mentor_id"),
                func.array_agg(
                    func.json_build_object(
                        "mentee_name", mentee.full_name,
                        "mentee_id", mentee.id,
                        "skill", Skill.name,
                    )
                ).label("matches"),
            )
            .select_from(UserSkill)
            .join(User, User.id == UserSkill.user_id)
            .join(
                us_low := aliased(UserSkill),
                and_(
                    us_low.skill_id == UserSkill.skill_id,
                    us_low.level == "low",
                    us_low.user_id != UserSkill.user_id,
                ),
            )
            .join(mentee := aliased(User), mentee.id == us_low.user_id)
            .join(Skill, Skill.id == UserSkill.skill_id)
            .where(UserSkill.level == "high", User.org_id == org_id)
            .group_by(User.id, User.full_name)
        )
        result = await self.session.execute(query)
        return result.all()
```

#### Vector Search (Document Chunks)

```python
# src/repositories/document_chunk_repo.py
from pgvector.sqlalchemy import Vector

class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, DocumentChunk)

    async def similarity_search(
        self,
        org_id: uuid.UUID,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Semantic search across all org documents."""
        query = (
            select(
                DocumentChunk.content,
                DocumentChunk.metadata,
                (1 - DocumentChunk.embedding.cosine_distance(query_embedding)).label("similarity"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.org_id == org_id)
            .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
        result = await self.session.execute(query)
        return [
            {"content": row.content, "metadata": row.metadata, "similarity": row.similarity}
            for row in result.all()
        ]
```

#### Session Management in Routes

Routes get a session from `Depends`, instantiate repositories and services, and the session auto-commits or rolls back:

```python
# src/routes/courses.py
@router.post("/courses", status_code=201)
async def create_course(user: AdminUser, db: DBSession, body: CourseCreate):
    repo = CourseRepository(db)
    service = CourseService(repo)
    course = await service.create(
        org_id=user.org_id,
        created_by=user.id,
        **body.model_dump(),
    )
    await db.commit()
    return CourseRead.model_validate(course)
```

The `commit()` call is in the route handler, not in the repository or service. This keeps the transaction boundary visible and explicit. If anything raises before commit, the session rolls back automatically when the context manager exits.

#### Model-to-Table Mapping Summary

| Model class | Table | Key relationships |
|-------------|-------|-------------------|
| `Organization` | `organizations` | Has many: users, documents, skills, courses |
| `User` | `users` | Belongs to: organization. Has many: enrollments, attempts, user_skills |
| `Document` | `documents` | Belongs to: organization, uploaded_by user. Has many: chunks |
| `DocumentChunk` | `document_chunks` | Belongs to: document. Has: embedding vector(384) |
| `SkillCategory` | `skill_categories` | Belongs to: organization. Has many: skills |
| `Skill` | `skills` | Belongs to: organization, category. Has many: user_skills, checkpoints |
| `Course` | `courses` | Belongs to: organization, created_by user, source document. Has many: modules, enrollments, checkpoints. Has one: manual |
| `Module` | `modules` | Belongs to: course. Has many: lessons |
| `Lesson` | `lessons` | Belongs to: module. Has many: exercises |
| `Exercise` | `exercises` | Belongs to: lesson. Has many: attempts, spaced_repetition entries |
| `SkillCheckpoint` | `skill_checkpoints` | Belongs to: course, skill, module |
| `Manual` | `manuals` | Belongs to: organization, created_by user, source document, course (optional) |
| `Enrollment` | `enrollments` | Belongs to: user, course, assigned_by user |
| `ExerciseAttempt` | `exercise_attempts` | Belongs to: user, exercise |
| `UserSkill` | `user_skills` | Belongs to: user, skill |
| `SpacedRepetition` | `spaced_repetition` | Belongs to: user, exercise |
| `GenerationJob` | `generation_jobs` | Belongs to: organization, triggered_by user, source document. Links to: result course, result manual |
| `CourseFeedback` | `course_feedback` | Belongs to: user, course |
| `ChatSession` | `chat_sessions` | Belongs to: user. Has many: chat_messages |
| `ChatMessage` | `chat_messages` | Belongs to: chat_session |
| `BackgroundJob` | `background_jobs` | Belongs to: organization. Tracks async task execution |
| `UserSession` | `user_sessions` | Belongs to: user. Tracks active auth sessions |
| `AuditLog` | `audit_logs` | Belongs to: user, organization. Records admin actions |
| `ApiKey` | `api_keys` | Belongs to: organization. API key management |
| `Webhook` | `webhooks` | Belongs to: organization. Has many: webhook_deliveries |
| `WebhookDelivery` | `webhook_deliveries` | Belongs to: webhook. Tracks delivery attempts |

#### Migrations

Alembic with async support. One migration per schema change.

```bash
# Generate migration from model changes
uv run alembic revision --autogenerate -m "add_courses_table"

# Apply migrations
uv run alembic upgrade head

# Rollback
uv run alembic downgrade -1
```

The initial migration creates all 27 tables + enums + indexes + extensions (`pgcrypto`, `vector`).

---

### 4.6 Configuration

```python
# src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://skillnet:skillnet@localhost:5432/skillnet"

    # Auth
    SECRET_KEY: str                       # Required, no default
    SESSION_LIFETIME_SECONDS: int = 604800    # 7 days
    COOKIE_NAME: str = "skillnet_session"
    COOKIE_SECURE: bool = True                # Set False for local dev without HTTPS

    # LLM (defaults, overridable per org)
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    # Embeddings
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "multilingual-e5-small"
    EMBEDDING_DIMENSIONS: int = 384

    # File uploads
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # App
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

---

### 4.7 Application Factory

```python
# src/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create upload dir, verify DB connection
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown: dispose engine
    await engine.dispose()

def create_app() -> FastAPI:
    app = FastAPI(
        title="SkillNet API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,        # Required for cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    # Mount routers under /api/v1
    from src.routes import (
        auth, users, documents, courses, modules, lessons,
        exercises, enrollments, skills, chat, manuals,
        spaced_repetition, generation_jobs, stats, settings as settings_routes,
        feedback,
    )
    prefix = "/api/v1"
    app.include_router(auth.router, prefix=prefix, tags=["Auth"])
    app.include_router(users.router, prefix=prefix, tags=["Users"])
    app.include_router(documents.router, prefix=prefix, tags=["Documents"])
    app.include_router(courses.router, prefix=prefix, tags=["Courses"])
    app.include_router(modules.router, prefix=prefix, tags=["Modules"])
    app.include_router(lessons.router, prefix=prefix, tags=["Lessons"])
    app.include_router(exercises.router, prefix=prefix, tags=["Exercises"])
    app.include_router(enrollments.router, prefix=prefix, tags=["Enrollments"])
    app.include_router(skills.router, prefix=prefix, tags=["Skills"])
    app.include_router(chat.router, prefix=prefix, tags=["Chat"])
    app.include_router(manuals.router, prefix=prefix, tags=["Manuals"])
    app.include_router(spaced_repetition.router, prefix=prefix, tags=["Spaced Repetition"])
    app.include_router(generation_jobs.router, prefix=prefix, tags=["Generation Jobs"])
    app.include_router(stats.router, prefix=prefix, tags=["Stats"])
    app.include_router(settings_routes.router, prefix=prefix, tags=["Settings"])
    app.include_router(feedback.router, prefix=prefix, tags=["Feedback"])

    return app

app = create_app()
```

---

### 4.8 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Repository per domain, not per table** | `SkillRepository` handles `skills`, `skill_categories`, `user_skills`, and matrix queries. Avoids 23 tiny repos |
| **No unit of work abstraction** | `db.commit()` in route handler is explicit enough for this scale. Adding UoW adds indirection without benefit |
| **Services receive deps via constructor** | Route handler creates `CourseService(repo)` — no service locator, no global state. Easy to test with fakes |
| **Commit in route, not in service** | Transaction boundary is visible. Service methods are composable (one route can call multiple service methods in one transaction) |
| **No background task queue for MVP** | Generation jobs run in-process with `asyncio.create_task()`. If a request triggers generation, it starts the task and returns the job_id immediately. The client polls for status. Celery/Dramatiq deferred to when needed |
| **Alerts computed on request** | No alert table, no cron. `AlertService.get_alerts()` runs queries against enrollment/attempt/spaced_repetition data. At MVP scale (dozens of employees), this is instant |
| **Flat route files, not nested routers** | `modules.py` handles `/courses/{cid}/modules/...` directly. The nesting is in the URL, not in the code structure. Keeps imports simple |
| **SSE over WebSocket** | Unidirectional streaming is all we need. SSE reconnects automatically, works with proxies, needs zero client-side library |
| **Pydantic schemas separate from ORM models** | ORM models map to tables. Schemas define API contracts. They look similar but evolve independently (e.g., `CourseRead` excludes internal fields, adds computed `module_count`) |
