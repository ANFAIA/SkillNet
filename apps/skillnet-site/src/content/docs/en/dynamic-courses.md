---
title: "Dynamic courses (v2)"
order: 11
section: "v2"
---

# v2 — Dynamic courses

> **Status: implemented.** The design on this page was merged into `main`; the working
> branch `feat/dynamic-courses` was deleted on 2026-08-04. v2 is chosen per course
> (`delivery_mode='dynamic'` with `schema_status='validated'`).
>
> Document priority: `v1-scope.md` remains the source of truth **for the v1 path**. This document
> defines the v2 path and **only** applies when the feature flag is active. Where this document
> contradicts `architecture.md`, `content-generation.md`, or `screens.md`, this document wins
> for the v2 path; the v1 path is untouched.
>
> Hard requirement: **v1's static path must keep working** for any course that has not opted
> into v2. No change in this document may alter the behavior of `GET /api/v1/courses/{id}`, of
> the `build_content_graph()` pipeline, or of the existing markdown render for a course whose
> `delivery_mode` is not `dynamic` (see §10).
>
> **Current episodic architecture:** the separation between the course's persisted constitution,
> the on-the-fly generated `EpisodeBrief`, neutral capability selection, `LearningExperience`, and
> server-owned evidence is specified in
> [`learning-experience-architecture.md`](/en/docs/learning-experience-architecture). This document still
> describes v2 runtime persistence, delivery, and compatibility. Sections that prescribe
> `ScreenScheme`, a fixed screen formula, or step grouping apply only to the `legacy_stepper`
> fallback; they do not constrain the `episode` path. `shell_mode` is decided by the server. The
> migration keeps `src.services.course_delivery.resolve_delivery` as the single v1/v2 selector.

---

## 1. Goal and scope

### 1.1 The change

Today a course is generated "in one shot": the admin uploads a document, a 7-node LangGraph
graph writes the entire course in Markdown, and every employee reads exactly the same text.

v2 splits generation into two stages:

| Stage | Who | What it produces | When |
|--------|-------|-------------|--------|
| **Design-time** | Admin/creator | A **schema**: title, outcome, and a list of **nodes** (competencies) with criticality, prerequisites, and an associated source. **Zero content.** | When the course is created |
| **Runtime** | System, per employee | For each NOT-mastered node: a **UI spec** generated on the fly from the node + the learner's profile + the source | When the employee opens the node |

Between the two stages there is a **blocking human gate**: the creator validates the schema.
Without `schema_status = 'validated'`, nothing is generated for any employee.

### 1.2 In scope for this PR (complete vertical slice)

1. **Course schema** — a node table with criticality and prerequisites, LLM-proposed schema
   generation, creator editing, blocking validation.
2. **Onboarding** — 4 questions + 1 optional, ≤90 s, that seed the learner's profile.
3. **Learner profile** — declared profile (role, goal, experience, preset), implicit format
   vector, per-node state (mastery, streaks, type of last error).
4. **Per-node pre-assessment** — 2 items + tiebreaker, with a computable mastery rule and a
   threshold per criticality.
5. **On-the-fly per-node generation** — a new LangGraph graph (`decide_formato` → `genera_ui` →
   `validate_ui` → `persist_render`), with a two-tier model router.
6. **Adapter render layer** — a canonical IR (`ui_spec` jsonb) + **one** dialect backend,
   **OpenUI Lang**, behind a `Protocol` with a registry. The adapter seam goes in; the second
   dialect does **not** (see §1.3 and §5.4).
7. **Profile adjustment** — a deterministic service that updates mastery, vector, and tutor
   notes after every answer.
8. **Click-to-explain (Curio)** — any word or selection inside a node opens an inline contextual
   explanation, with server-side caching.
9. **Latency** — skeleton, productive wait overlapped with the pre-assessment, SSE block
   streaming, cache per profile bucket.
10. **Alembic migrations** (`0005`), tests with recorded fixtures, and this documentation.

### 1.3 NOT in scope (explicit backlog, not "TBD")

| Out | Reason |
|-------|--------|
| `SandboxHTML` / free-form LLM-generated HTML | A direct XSS vector, and 12-65% of generated code has vulnerabilities. The pattern is `prompt → typed IR → native render`. To be reevaluated once an audited iframe sandbox exists |
| `Simulation` component (adjustable parameters) | Requires data-binding and a lifecycle the IR doesn't have. The `simulation` value exists in the reserved `ui_format` enum, but `decide_formato` does not emit it (the `ALLOWED_UI_FORMATS` constant) |
| Spaced repetition (HLR or FSRS) | **Premise correction:** it does not exist today. `spaced_repetition`/HLR appears in `data-model.md`, `product.md`, and `background-processing.md`, but **there is no table or module in the repo** (verified: 20 tables, no `half_life`/`next_review` in `src/`). This PR does not introduce it. Direct consequence: the `needs_review` state is **not** produced by any scheduler — its only producer in this PR is the hint cap (§7.4) |
| Second dialect backend (`a2tl`) | The `UIDL/1` format of `packages/a2tl-web` is a **flat list of sections with no ids or `children`** (`parser.ts:11-21`) and has no primitive for `QuizItem`, `Stack`, `Card`, or `Callout`. It cannot represent the `UISpec` from §5.2, so round-tripping and cross-retry are impossible for any spec with an exercise or nested containers. The `Protocol` + registry (the seam) goes in, not the second dialect. Backlog: if needed, it will be a dialect **native to SkillNet**, not that package's |
| `background_jobs` table / purge worker | Does not exist (verified). Purging `learning_events` and `term_explanations` is a **CLI script** (`python -m src.scripts.purge_learning_data`), documented and runnable by hand or via a host cron job. Backlog: turn it into a real job |
| QLoRA fine-tuning of the DSL | Backlog |
| Parallel router decomposition (8B skeleton + concurrent 120B fills) | The router is implemented **at the full-UI level**. Per-component decomposition only makes sense with `SandboxHTML`, which is out of scope |
| Destructive migration of `modules`/`lessons`/`exercises` | They coexist. v1 lessons are the **seed** (`course_nodes.seed_lesson_id`) and the degraded mode |
| Click-to-locate editing (diff-based editing over the DSL) | Backlog |
| Multi-turn chat/tutor inside the node | v1 chat stays as is. The node only has click-to-explain |

### 1.4 Decisions this document closes

These contradictions were left open during research. They are closed as follows, and are not
reopened within this PR:

| Question | Decision |
|----------|----------|
| LLM output format | **Typed IR** (`ui_spec` jsonb, flat list of components). The LLM emits the active backend's **dialect**; the adapter parses it into the IR. Never HTML |
| Nodes vs. modules/lessons | **They coexist.** `course_nodes` is the v2 unit; `modules`/`lessons` are the v1 path and the seed |
| Where generated content lives | New `node_renders` table, cached by `cache_key`. **It is persisted** (cost). The audit trail does **not** live there: it lives in `node_render_views` (§3.4) |
| Render stability within a node | **View A: the render is pinned.** `learner_node_states.active_render_id` anchors the spec from when the node is opened until the user explicitly requests a regeneration. A browser refresh or a TanStack Query refetch returns **the same** spec. Adaptation happens **between** nodes and sessions, never within an open screen. View B (continuous regeneration) is out of scope: it requires layout locking, a change explanation, and "view the previous version," none of which fit in this PR |
| Declared experience: per course or per person? | **Per person and about their own job**, not about a specific course (the question doesn't name any course). Per-competency adjustment is contributed by `user_skills` via `course_nodes.skill_id` as a prior for the probe (§7.1), not the declaration |
| Raw event log | `learning_events` **is persisted**, reversing the earlier idea of storing only the aggregated vector. Concrete reason: the decay in §3.3 needs `created_at` per event, and the aggregated vector cannot be recomputed if weights change. Cost: a 90-day retention window and a purge script |
| `format_vector` dimensions | **Only the ones the kit can produce**: `text`, `exercise`, `code`, `data`. `diagram`, `audio`, and `resource` are removed — no component emits them, so they would be structurally dead dimensions |
| Neurotypes in `screens.md` | `screens.md` §Employee Settings ("optional: TEA, TDAH, dyslexia flags", line 213) **is deprecated** by the decision not to store neurotype. Fixed in the same routes `chore` (§14.2 #8), along with `design-system.md` §Skeleton, which documents `animate-pulse` while `motion-system.md:437,636` prohibits it |
| Primary mastery scale | **Real `mastery` 0..1** per `(user, node)`, plus a derived `node_state` enum. Shu-Ha-Ri and Bloom are derivations, not primary state |
| Rating scale | The existing one: real `score` 0..1 (same as `exercise_attempts`). No 1-4 Rating |
| Modality preference | The user can explicitly request image, audio, video, or text when the kit supports them. The declared preference wins; `format_vector` remains a secondary inferred signal. See [`adaptive-learning.md`](/en/docs/adaptive-learning) |
| Neurodivergence | **No neurotype label is stored** (health data, GDPR art. 9). Only neutral, opt-in reading adjustments in `users.accessibility` |
| Nature of creator validation | **Blocking gate** via DB state (`schema_status`), not a LangGraph `interrupt()` — survives process restarts |
| LLM provider | litellm, provider-agnostic. The router's two tiers are **purposes** (`runtime_fast`, `runtime_heavy`), not providers. Groq is a possible env var value, not a dependency |
| Frontend routes | Follows the convention **already implemented** in `App.tsx` (Spanish). Fixing `screens.md` is a separate `chore` |
| Presentation adaptation | Does not adapt until 3 nodes are completed (calibration period). It adapts **what** appears, not **where** |

---

## 2. v2 architecture — full flow

```
                              ══════════ DESIGN-TIME (admin) ══════════

  ┌───────────┐   POST /documents          ┌──────────────────┐
  │ document  │ ─────────────────────────► │  v1 ingestion    │  (unchanged)
  │ PDF/DOCX  │   POST /documents/{id}/    │  parse → chunk   │
  └───────────┘        process             │  → embeddings    │
                                           └────────┬─────────┘
                                                    │ documents.status='ready'
                                                    ▼
                     POST /courses/{id}/schema/propose (202 → job_id)
                                                    │
                        ┌───────────────────────────┴───────────────────────────┐
                        │  build_schema_graph()   [src/agents/schema/graph.py]  │
                        │                                                       │
                        │  load_source ─► extract_themes_schema ─► design_schema │
                        │   (NEW, uses     (NEW, uses helpers       (NEW, LLM)  │
                        │    helpers)       + v1 prompt)              │         │
                        │                                             ▼         │
                        │                                     persist_schema    │
                        │                                       (NEW)           │
                        └───────────────────────────┬───────────────────────────┘
                                                    │ SSE: schema_step / schema_ready
                                                    │ channel generation:{job_id}
                                                    ▼
                                       courses.schema_status = 'proposed'
                                       course_nodes + course_node_prerequisites
                                       ⚠ ZERO content generated
                                                    │
                       GET /courses/{id}/schema     │      PUT /courses/{id}/schema
                       (the creator reads it) ◄─────┼───────► (the creator edits it)
                                                    │
                                                    ▼
                    ╔═══════════════════════════════════════════════════════╗
                    ║  BLOCKING GATE                                        ║
                    ║  POST /courses/{id}/schema/validate                   ║
                    ║  validates: acyclic DAG · ≥1 critical node ·          ║
                    ║          every node has a summary and a source ·      ║
                    ║          prereqs with no orphans                      ║
                    ║  ⇒ schema_status='validated', delivery_mode='dynamic' ║
                    ╚═══════════════════════════════╤═══════════════════════╝
                                                    │
                                    POST /enrollments (assignment, unchanged)
                                                    │
                              ══════════ RUNTIME (employee) ══════════
                                                    │
                                                    ▼
     first login ──►    ┌────────────────────────────────────────────┐
                       │  ONBOARDING  (5 screens, ≤90 s)            │
                       │  GET /onboarding · POST /onboarding        │
                       │  role · goal · experience · preset ·       │
                       │  reading settings (optional)                │
                       └────────────────────┬───────────────────────┘
                                            │ seeds
                                            ▼
                       learner_profiles (role_title, goal,
                       experience_level, preset, format_vector=0)
                                            │
                                            ▼
                       GET /courses/{id}/nodes   (list + state + prereq lock)
                                            │
                                            ▼
        ┌──────────────────── for each unlocked node ─────────────────────────┐
        │                                                                      │
        │   POST /nodes/{node_id}/probe        ┌─────────────────────────┐     │
        │   ──────────────────────────────────►│  PRE-ASSESSMENT         │     │
        │                                      │  item A (apply)         │     │
        │   POST /nodes/{node_id}/probe/answer │  item B (understand)    │     │
        │   ──────────────────────────────────►│  [+ tiebreaker if unsure]│     │
        │                                      └───────────┬─────────────┘     │
        │                                                  │                   │
        │      ┌───────────────────────────────────────────┴───────┐           │
        │      │ mastery ≥ threshold(criticality)?                 │           │
        │      └────────┬──────────────────────────────┬───────────┘           │
        │           YES │                              │ NO                    │
        │               ▼                              ▼                       │
        │      node_state='mastered'      ╔═══════════════════════════════════╗│
        │      (skipped, 0 tokens)        ║ build_node_graph()                ║│
        │               │                 ║ [src/agents/runtime/graph.py]     ║│
        │               │                 ║                                   ║│
        │               │                 ║  load_context                     ║│
        │               │                 ║    (node + profile + state +      ║│
        │               │                 ║     source via RAG/seed)          ║│
        │               │                 ║        │                          ║│
        │               │                 ║        ▼                          ║│
        │               │                 ║  probe_gate ──(mastered)──► skip  ║│
        │               │                 ║        │ needs_content            ║│
        │               │                 ║        ▼                          ║│
        │               │                 ║  decide_formato    ◄── ROUTER     ║│
        │               │                 ║   (LLM tier=fast)      fast│heavy ║│
        │               │                 ║   → explanation|exercise|         ║│
        │               │                 ║     chart|mixed                   ║│
        │               │                 ║        │                          ║│
        │               │                 ║        ▼                          ║│
        │               │                 ║  genera_ui  (LLM tier from router)║│
        │               │                 ║   → active backend's dialect      ║│
        │               │                 ║        │                          ║│
        │               │                 ║        ▼                          ║│
        │               │                 ║  validate_ui                      ║│
        │               │                 ║   adapter.parse() → UISpec        ║│
        │               │                 ║   ├ ok ──────────► persist_render ║│
        │               │                 ║   ├ invalid & retry<1 ─► genera_ui║│
        │               │                 ║   └ fails ──────► fallback_seed   ║│
        │               │                 ║                    (v1 markdown)  ║│
        │               │                 ╚═══════════════╤═══════════════════╝│
        │               │                                 │ node_renders       │
        │               │                                 ▼ (ui_spec+answer_key)│
        │               │              GET /nodes/{id}/render        (cache hit)│
        │               │              GET /nodes/{id}/render/stream (SSE)      │
        │               │                                 │                     │
        │               │                                 ▼                     │
        │               │                 ┌───────────────────────────────────┐ │
        │               │                 │  RENDER (frontend)                │ │
        │               │                 │  UiSpecRenderer → blocks/*        │ │
        │               │                 │  wrapped in ClickableSurface      │ │
        │               │                 │                                   │ │
        │               │                 │  click on word/selection ────────►│ │
        │               │                 │  POST /explain (SSE) ─► popover   │ │
        │               │                 └───────────────┬───────────────────┘ │
        │               │                                 │                     │
        │               │            POST /nodes/{id}/answer                    │
        │               │            POST /nodes/{id}/feedback                  │
        │               │                                 │                     │
        │               │                                 ▼                     │
        │               │                 ┌───────────────────────────────────┐ │
        │               │                 │  PROFILE ADJUSTMENT (deterministic)│ │
        │               │                 │  [src/services/learner_profile_   │ │
        │               │                 │   service.py]                     │ │
        │               │                 │  · mastery ← EWMA(score)          │ │
        │               │                 │  · consecutive_correct/failed     │ │
        │               │                 │  · last_error_kind                │ │
        │               │                 │  · format_vector ← learning_events│ │
        │               │                 │  · tutor_notes (controlled vocab) │ │
        │               │                 └───────────────┬───────────────────┘ │
        │               │                                 │                     │
        │               └─────────────────────────────────┤                     │
        │                                                 ▼                     │
        │                                  next unlocked node                  │
        └──────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                       enrollments.status='completed' when all
                       critical nodes are 'mastered'
```

### 2.1 What is persisted vs. what is generated

The asynchronous pedagogical preparation stage sitting between the index and OpenUI is specified in
[`node-knowledge-packs.md`](/en/docs/node-knowledge-packs). After the index commit it generates a
structured contract and a derived Markdown per node. Only `ready` packs feed runtime knowledge
selection; their hash and the selection's hash are part of the cache key. The `review_required`,
`failed`, `stale` states, and the absence of a pack keep the previous raw flow as fallback. Creating
or editing the schema automatically enqueues preparation; opening the screen does not start work.
Each node exposes its state inside its own disclosure on the schema screen; the technical details
do not occupy a global section.

| Persisted (design-time, stable) | Generated on the fly (runtime, per user) |
|------------------------------------|-------------------------------------------|
| Course title and outcome | Each node's UI (`ui_spec`) |
| Nodes, summaries, criticality, prerequisites | The adapted explanatory text |
| Source document + associated headings | Examples contextualized to the role |
| Constitution: competency, grounding, evidence gates, and critical errors | `EpisodeBrief`: mission, dominant action, support, boundaries, and continuation |
| Learner profile | Exercise and pre-assessment items |
| Per-node state (mastery, streaks) | Click-to-explain explanations |
| The **already generated** `ui_spec` (content, shared per bucket) | — |
| Who saw which render and when (`node_render_views`) | — |

The constitution and the packs are not a pre-built presentation. They do not fix the course's
sequence, modality, component, or speculative artifacts; they bound episodic generation and make it
auditable. Audio and video, when eligible, are embedded in the mission: they do not create modality
tabs.

**Cache and audit are two tables, not one.** `node_renders` is **org-scoped content**: it stores
the canonical `dialect` that was served (re-serialized from the `UISpec`, **never** the model's raw
text), the validated `ui_spec`, the model used, and provenance (`catalog_version`,
`library_version`), and the same row is shared by every employee in the same profile bucket. So it
**cannot** say who saw what: on a cache hit (the ~80% that makes the cost sustainable), the row has
nothing to do with the employee currently reading it.

What does say that is `node_render_views(user_id, render_id, first_seen_at)`: a thin row written on
each user's first `GET /nodes/{id}/render`. A certificate is justified by joining
`node_attempts` → `node_render_views` → `node_renders`, and it survives the deletion of any other
user because `node_renders.generated_by` is `NULL`-able with `ON DELETE SET NULL` (§3.4).

---

## 3. Data model

Everything new goes into **one** migration: `alembic/versions/0005_dynamic_courses.py`, with
`revision = "0005"` and `down_revision = "0004"` (current head verified: linear chain
`0001→0002→0003→0004`, no branches).

**What "downgrade tested" exactly means** — and what it doesn't: PostgreSQL **cannot remove a value
from an enum**. `downgrade()` drops the 13 new tables, the 6 `courses` columns, and the 8 new
enums, but **leaves `schema_proposing` and `schema_proposed` orphaned in the `generation_step`
type**. This is harmless (no row references them after the downgrade, because schema jobs are
deleted along with the new tables… and if one remained, `generation_service` already falls back to
a known value) and is exactly what `tests/integration/test_migration_0005.py` asserts: not a
byte-for-byte identical schema, but "all new tables and columns gone, the two enum values still
there." A truly clean downgrade would require recreating the type and rewriting
`generation_jobs.status`; that is not done, and this line is the documented reason.

Conventions honored from `data-model.md`: PK `uuid DEFAULT gen_random_uuid()`, `timestamptz`,
`jsonb` for flexible data, `org_id` on **top-level** tables (children inherit the parent's scoping;
see §15.4), enums named in snake_case.

**Enrollment tenant isolation.** An enrollment has two ends — the learner and the course — and both
must live in the same organization. Creation (`EnrollmentService.assign` /
`assign_courses`) now validates that **all** `user_ids` belong to the admin's org, not just the
course; enrolling a learner from another org returns `403`. The "My courses" listing
(`EnrollmentRepository.list_enrollments`) filters by `User.org_id` **and** `Course.org_id`, so a
preexisting cross-org row no longer appears — previously its title showed up and then the detail
view responded `404` ("Course not found"). The defense applies on both read and write without
deleting rows: an inconsistent enrollment is hidden, not removed. The course detail view already
filtered by the caller's org and that is kept.

> **Creation order in `0005`** — the SQL blocks below are grouped by topic, not in executable
> order. There are two forward references: `course_nodes.default_ui_format` needs the `ui_format`
> enum, and `learner_node_states.active_render_id` needs the `node_renders` table. Actual order:
> **all `CREATE TYPE` first**, then `course_nodes` → `course_node_prerequisites` →
> `node_renders` → `learner_node_states` → the rest → `node_render_views` (which references
> `node_renders` and `course_nodes`).

### 3.1 Changes to existing tables

All with `DEFAULT`, all additive. No existing column is renamed or dropped.

```sql
CREATE TYPE course_delivery_mode AS ENUM ('static', 'dynamic');
CREATE TYPE course_schema_status AS ENUM ('draft', 'proposed', 'validated', 'archived');

ALTER TABLE courses
    ADD COLUMN delivery_mode        course_delivery_mode NOT NULL DEFAULT 'static',
    ADD COLUMN schema_status        course_schema_status NOT NULL DEFAULT 'draft',
    ADD COLUMN schema_validated_by  uuid REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN schema_validated_at  timestamptz,
    ADD COLUMN schema_version       int NOT NULL DEFAULT 1,
    ADD COLUMN intent_density       smallint NOT NULL DEFAULT 3
                                    CHECK (intent_density BETWEEN 1 AND 5);
```

- `delivery_mode`: `'static'` = v1 path intact. `'dynamic'` = v2 path. Only
  `POST /courses/{id}/schema/validate` sets it.
- `schema_version`: incremented on every `PUT /courses/{id}/schema` that changes nodes. It goes
  into the `cache_key`, so editing the schema invalidates derived renders without deleting rows.
- `intent_density`: the "intent slider" condensed(1) ↔ expanded(5). It goes into the `genera_ui`
  prompt as a length budget, not as a format decision.

```sql
-- The 'schema' step of the design-time pipeline
ALTER TYPE generation_step ADD VALUE IF NOT EXISTS 'schema_proposing' BEFORE 'extracting';
ALTER TYPE generation_step ADD VALUE IF NOT EXISTS 'schema_proposed'  AFTER 'reviewing';
```

> **Implementation note, corrected twice.** The deployment is **pg16**
> (`docker-compose.yml`: `pgvector/pgvector:pg16`), where `ALTER TYPE … ADD VALUE` **does** work
> inside a transaction since pg12. The only thing forbidden is **using** the new value in the same
> transaction — and the earlier version of this note claimed `0005` didn't. **That was false**:
> step 16 uses `schema_proposing`/`schema_proposed` in the predicate of the partial index
> `uq_generation_jobs_schema_in_flight`, so the run dies with
> `UnsafeNewEnumValueUsageError`. This was discovered by the first real run of the integration
> suites; until then nobody had done an `alembic upgrade head` from scratch.
>
> Fix applied in the file: the two `ALTER TYPE … ADD VALUE` statements run inside
> `op.get_context().autocommit_block()`, and it is the **only** one in the migration. The cost of
> that block is exactly what the earlier note wanted to avoid, and it must be accepted with eyes
> open: `alembic/env.py` wraps **the entire** run in a `context.begin_transaction()` without
> `transaction_per_migration`, and `src/main.py` calls `run_migrations()` in the lifespan, so the
> block commits `0001..0004` early. If a later step of `0005` fails, the database is left at
> `0004` without `0005` stamped, and the half-created v2 objects must be dropped by hand before
> retrying. This is documented in the migration's docstring and asserted by
> `tests/integration/test_migration_0005.py`.
>
> Second lesson from the same run, applicable to any future migration in this repo:
> **`sa.Enum(..., create_type=False)` doesn't work**. `sa.Enum` loses that flag when adapting to
> the postgres dialect, so `CREATE TYPE` is emitted anyway and blows up the second time. You must
> use `postgresql.ENUM(..., create_type=False)`. This was the real reason
> `alembic upgrade head` from scratch had never worked (it was already broken in `0003`).
>
> Third: a JSONB default value built with `sa.text()` interprets `:` as bind parameters. Left
> unescaped, the DDL in `0005` and in `src/models/learner_profile.py` came out as
> `{"texto"NULL,...}`. You have to write `\:`.
>
> Also add the members to the Python `GenerationStep` enum in `src/models/generation_job.py`
> (`SCHEMA_PROPOSING = "schema_proposing"`, `SCHEMA_PROPOSED = "schema_proposed"`).

> **`generation_jobs.output_type`:** it is `NOT NULL` on an enum with only
> `course_and_manual|manual_only` (`src/models/generation_job.py:15-17`), and a schema-proposal job
> is neither. **Decision:** the schema job writes `output_type='course_and_manual'` as a
> **meaningless placeholder** and no consumer interprets it (schema clients go by `status`). A
> third enum value is not added, to avoid growing the downgrade's orphan-enum problem for a field
> nobody reads.

`generation_jobs.progress` (jsonb) and `langgraph_thread_id`, never written today, **start being
written** in the schema graph: `progress` receives `{"step": ..., "nodes_proposed": N}` at each
node, so a client that subscribes late to the SSE can reconstruct state via REST.

`users.accessibility` (jsonb, already exists) now gets a defined shape — **neutral settings,
never diagnoses**:

```json
{"reduce_motion": false, "short_blocks": true,
 "high_contrast": false, "extra_time": false}
```

**`audio_first` is removed** from the shape and from question 5: there is no TTS anywhere in this
PR, nor an audio component in the frozen kit (§5.3). Offering an accommodation the pipeline cannot
deliver is worse than not offering it.

**How `short_blocks` is honored without `accessibility` reaching the LLM** (the rule that it never
does is kept): the frontend cannot shorten prose written by the model, so the signal is
translated **on the server** into a dimension that already travels to the prompt. In
`load_context`:

```python
effective_density = min(course.intent_density, 2) if user.accessibility.get("short_blocks") else course.intent_density
```

`effective_density` is what goes into the prompt and into the `cache_key`. The LLM receives a
length-budget number, never the flag or its origin.

### 3.2 The course schema

```sql
CREATE TYPE node_criticality AS ENUM ('critical', 'recommended', 'contextual');

CREATE TABLE course_nodes (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    course_id           uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    skill_id            uuid REFERENCES skills(id) ON DELETE SET NULL,
    seed_lesson_id      uuid REFERENCES lessons(id) ON DELETE SET NULL,
    title               text NOT NULL,
    summary             text NOT NULL,
    outcome             text,
    criticality         node_criticality NOT NULL DEFAULT 'recommended',
    position            int NOT NULL,
    source_document_id  uuid REFERENCES documents(id) ON DELETE SET NULL,
    source_headings     text[] NOT NULL DEFAULT '{}',
    mastery_threshold   real NOT NULL DEFAULT 0.80
                        CHECK (mastery_threshold > 0 AND mastery_threshold <= 1),
    default_ui_format   ui_format NOT NULL DEFAULT 'explanation',
    probe_items         jsonb NOT NULL DEFAULT '[]',
    probe_answer_key    jsonb NOT NULL DEFAULT '{}',
    estimated_minutes   int,
    reviewed_at         timestamptz,
    reviewed_by         uuid REFERENCES users(id) ON DELETE SET NULL,
    archived            boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_course_nodes_position UNIQUE (course_id, position)
        DEFERRABLE INITIALLY IMMEDIATE
);

CREATE INDEX idx_course_nodes_course ON course_nodes(course_id, position);
CREATE INDEX idx_course_nodes_skill  ON course_nodes(skill_id);

CREATE TABLE course_node_prerequisites (
    node_id               uuid NOT NULL REFERENCES course_nodes(id) ON DELETE CASCADE,
    prerequisite_node_id  uuid NOT NULL REFERENCES course_nodes(id) ON DELETE CASCADE,
    PRIMARY KEY (node_id, prerequisite_node_id),
    CHECK (node_id <> prerequisite_node_id)
);

CREATE INDEX idx_node_prereq_node ON course_node_prerequisites(node_id);
```

Design notes, each with its reason:

- **`summary` is `NOT NULL`.** Without a summary, the tutor's PageIndex pattern (read the summary
  tree → decide which node is relevant → load only that one) does not work. It's a validation
  requirement, not decoration.
- **`source_headings text[]`, not `chunk_id`.** Chunks are destroyed when the document is
  re-ingested; headings survive. The node references `(source_document_id, source_headings)`.
- **`seed_lesson_id`** points to the equivalent v1 lesson if the course comes from v1. This is the
  degraded mode: if `genera_ui` fails twice or no LLM is available, `lessons.content` is served
  rendered as markdown. This resolves v2's incompatibility with offline/catalog mode.
- **`mastery_threshold` per node**, with a default derived from criticality when the schema is
  created: `critical → 0.90`, `recommended → 0.80`, `contextual → 0.70`. The creator can override
  it.
- **`default_ui_format`** exists because §6.4 mandates falling back to "the node's canonical
  default format" during calibration, and without this column that instruction had nowhere to
  read from. It's proposed by `design_schema` and edited by the creator in B10. Default
  `explanation`.
- **`probe_items` / `probe_answer_key`** store the pre-assessment **pre-generated at validation
  time**, not per user. Items depend only on `(node, source)`, so they are generated once per node
  and served instantly to everyone: this solves the probe's cold start (§9.1), where otherwise the
  "productive wait" would face its own wait on an LLM call against a blank screen. `node_probes`
  becomes just the per-user record of an attempt.
- **`reviewed_at` / `reviewed_by` per node.** The validation in §11.1 proves the graph is
  well-formed, not that a human read the pedagogy. A node without `reviewed_at` **cannot be
  served**: `resolve_delivery` still looks at the course, but `GET /nodes/{id}/render` returns
  `409 node_not_reviewed` if the node hasn't been reviewed. That closes the §11.1 bypass (adding
  new nodes to an already-validated course) by construction, not by trust.
- **`archived`** instead of deletion: a node with `learner_node_states.attempts_count > 0`
  **cannot be deleted** (`422 node_has_progress`), it gets archived. Deleting it would cascade
  into `learner_node_states` and `node_renders`, discarding mastery and the audit trail of people
  who had already worked on it.
- **`UNIQUE (course_id, position)` is `DEFERRABLE INITIALLY IMMEDIATE`**, and the `PUT` in §11.1
  defers it (`SET CONSTRAINTS uq_course_nodes_position DEFERRED`) within its transaction. Without
  that, any reordering violates the constraint mid-statement. Mandatory test: swap positions 1 and
  2 in a single `PUT`.
- **Acyclicity**: cannot be expressed in a CHECK. It's validated in
  `CourseSchemaService.validate()` with a topological order (Kahn) before moving to `'validated'`,
  and there is a unit test for the cycle detector. A cycle returns `422`.

### 3.3 The learner profile

Three independent sources, three distinct places: declared (`learner_profiles`), inferred
(`learning_events` → `format_vector`), and per-competency (`learner_node_states`).

```sql
CREATE TYPE learner_experience AS ENUM ('unknown', 'none', 'some', 'experienced');

CREATE TABLE learner_profiles (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                   uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id                  uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    role_title               text,
    sector                   text,
    goal                     text,
    experience_level         learner_experience NOT NULL DEFAULT 'unknown',
    preset                   learning_profile NOT NULL DEFAULT 'standard',
    format_vector            jsonb NOT NULL DEFAULT
                             '{"texto":0,"ejercicio":0,"codigo":0,"dato":0}',
    format_vector_updated_at timestamptz,
    nodes_completed          int NOT NULL DEFAULT 0,
    tutor_notes              jsonb NOT NULL DEFAULT '{}',
    onboarding_completed_at  timestamptz,
    onboarding_skipped       boolean NOT NULL DEFAULT false,
    onboarding_version       smallint NOT NULL DEFAULT 1,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now()
);
```

- **`preset` reuses the existing `learning_profile` enum** (`standard|focus|fast`). No new enum is
  created. `users.learning_profile` remains the source of truth for the v1 frontend;
  `learner_profiles.preset` is kept in sync in the same onboarding transaction.
- **`experience_level` starts at `'unknown'`, not `'none'`.** `'none'` means "declares no
  experience" and triggers novice scaffolding (worked examples), which is exactly what **hurts**
  the expert. Using `'none'` as "I don't know" would make **everyone who skips onboarding**
  silently receive novice scaffolding. `'unknown'` maps to **neutral** scaffolding: neither extra
  worked examples nor scaffolding suppression; the first node's probe corrects this in 2 items.
- **`format_vector` is jsonb, not 4 columns.** Adding a dimension should not be a migration.
  The dimensions are **exactly the ones the frozen kit in §5.3 can produce**:
  `texto` (`TextContent`, `Callout`, `StepSequence`, `Card`), `ejercicio` (`QuizItem`),
  `codigo` (`CodeBlock`), `dato` (`Chart`, `Table`). `diagrama`, `audio`, and `recurso` are
  removed: no component emits them, so they would be dimensions that can never receive signal and
  would bias the dominant bucket toward `texto` by construction.
  Sums to ~1.0 after L1 normalization; for a new user they're all 0 and **it isn't used for
  anything** (see calibration period, §6.4).
- **`nodes_completed`** is the counter that governs the calibration period. Denormalized on
  purpose: it's read on every `decide_formato` and we don't want a `COUNT(*)` per render.
  **Increment rule, fixed:** `+1` only on the `learning → mastered` transition, i.e. only when the
  node has actually been *worked on*. A node skipped by the probe (`probing → mastered`) does
  **not** increment `nodes_completed`, precisely because it generated no interaction event:
  counting it would take the user out of calibration with an empty `format_vector`.
- **`tutor_notes`** is the "tutor's notebook" (Notarius). **Controlled vocabulary**, not free
  prose, so it is auditable and erasable:

```json
{
  "version": 1,
  "context": {"sector": "retail", "role": "dependiente", "prior": ["caja", "inventario"]},
  "signals": [
    {"node_id": "…", "action": "reforzar_con_ejemplo", "at": "2026-07-25T10:00:00Z"},
    {"node_id": "…", "action": "reducir_longitud_modulo", "at": "…"}
  ]
}
```

Allowed actions (validated via Pydantic, `Literal`) and **the exact condition that writes them**.
Without this table `tutor_notes` was a free, unspecified entry into a prompt, i.e. neither
implementable nor testable; and `sugerir_formato_audio` is removed because there is neither an
audio component (§5.3) nor a signal that could produce it. All writes happen in
`LearnerProfileService.apply_signals()`, called after every `answer`/`feedback`, **never** from an
LLM:

| Action | Exact condition that emits it | Test |
|---|---|---|
| `reforzar_con_ejemplo` (reinforce with example) | `consecutive_failed >= 2` on the node | `test_profile_service.py::test_signal_reinforce` |
| `bajar_dificultad` (lower difficulty) | `node_feedback.difficulty == 'hard'` on the node | `…::test_signal_lower` |
| `subir_dificultad` (raise difficulty) | `node_feedback.difficulty == 'easy'` **and** `consecutive_correct >= 3` | `…::test_signal_raise` |
| `reducir_longitud_modulo` (shorten module) | 3 consecutive `scroll_fast` events on the same node | `…::test_signal_shorten` |
| `revisar_prerrequisito` (review prerequisite) | `last_error_kind == 'conceptual'` **and** the node has ≥1 prerequisite with `state != 'mastered'` | `…::test_signal_prereq` |

`signals` is capped at the 20 most recent (pruned in the service), and the same `(node_id,
action)` is never duplicated: the `at` is updated instead. This is a **deliberate
simplification** of the earlier Notarius exploration, which proposed deriving signals from
conversation with the tutor and from audio/dwell behavior: since §1.3 removes chat inside the
node and there is no audio, those sources don't exist here, and the closed vocabulary is the only
thing that can be fed.

```sql
CREATE TYPE node_state AS ENUM
    ('not_started', 'probing', 'learning', 'mastered', 'needs_review');
CREATE TYPE error_kind AS ENUM ('detail', 'procedural', 'conceptual');

CREATE TABLE learner_node_states (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    node_id              uuid NOT NULL REFERENCES course_nodes(id) ON DELETE CASCADE,
    state                node_state NOT NULL DEFAULT 'not_started',
    mastery              real NOT NULL DEFAULT 0 CHECK (mastery >= 0 AND mastery <= 1),
    probe_score          real CHECK (probe_score IS NULL OR (probe_score >= 0 AND probe_score <= 1)),
    consecutive_correct  smallint NOT NULL DEFAULT 0,
    consecutive_failed   smallint NOT NULL DEFAULT 0,
    hints_used           smallint NOT NULL DEFAULT 0,
    attempts_count       int NOT NULL DEFAULT 0,
    last_error_kind      error_kind,
    active_render_id     uuid REFERENCES node_renders(id) ON DELETE SET NULL,
    render_pinned        boolean NOT NULL DEFAULT true,
    scaffold_band        text NOT NULL DEFAULT 'neutral'
                         CHECK (scaffold_band IN ('novice','neutral','advanced')),
    waived_by            uuid REFERENCES users(id) ON DELETE SET NULL,
    waived_at            timestamptz,
    first_seen_at        timestamptz,
    mastered_at          timestamptz,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, node_id)
);

CREATE INDEX idx_lns_user  ON learner_node_states(user_id);
CREATE INDEX idx_lns_state ON learner_node_states(user_id, state);
```

- **`active_render_id` + `render_pinned`** implement View A from §1.4: the render is pinned when
  the node is opened. `GET /nodes/{id}/render` returns the `active_render_id` spec while
  `render_pinned` is `true`, **without recomputing the `cache_key`**. Without this, content would
  mutate mid-node: with perfect answers mastery travels 0 → 0.40 → 0.64 → 0.784 → 0.87, and with
  `mastery_band` in the key that's four distinct keys within a single `critical` node, so a simple
  browser refresh would return different blocks in a different order — breaking §5.5's own spatial
  stability zones.
- **`scaffold_band`** replaces `mastery_band` in the `cache_key` (§3.4). It's computed **once**,
  when the probe closes: `novice` if `experience_level='none'` or the probe came out `learning`
  with `score_a == 0`; `advanced` if the probe came out `tiebreak` or
  `experience_level='experienced'`; `neutral` otherwise. It's stable for the whole node by
  construction, not by convention.
- **`waived_by` / `waived_at`**: the human escape hatch from §7.4 (`POST /nodes/{id}/waive`).

`mastery` is the **only** primary mastery scale. The others are derived views, computed in code,
never persisted redundantly:

| Derivation | Rule |
|------------|-------|
| Shu-Ha-Ri phase (scaffolding) | `mastery < 0.5 → shu`; `0.5 ≤ mastery < threshold → ha`; `≥ threshold → ri` |
| `skill_level` (`low/medium/high` from `user_skills`) | `< 0.5 → low`; `< 0.85 → medium`; `≥ 0.85 → high`. Applied only upward, as `_assign_course_skills` already does |
| Target Bloom level for the next item | `shu → understand`; `ha → apply`; `ri → analyze` |

```sql
CREATE TABLE learning_events (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    node_id     uuid REFERENCES course_nodes(id) ON DELETE SET NULL,
    type        text NOT NULL,
    element     text,
    weight      real NOT NULL DEFAULT 0,
    metadata    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_learning_events_user ON learning_events(user_id, created_at DESC);
```

Append-only. Fixed weights, defined as a constant in
`src/services/learner_profile_service.py::EVENT_WEIGHTS`:

| `type` | weight | | `type` | weight |
|---|---|---|---|---|
| `explain_click` | +0.30 | | `quiz_correct` | +0.20 |
| `expand` | +0.15 | | `quiz_wrong` | +0.10 |
| `scroll_slow` (>3 s) | +0.10 | | `view` | +0.05 |
| | | | `scroll_fast` (<1 s) | −0.05 |

`element` ∈ `{texto, ejercicio, codigo, dato}` — the four dimensions of `format_vector`.

**`resource_opened` is removed** (it was the second-highest weight): the frozen kit in §5.3 has no
link or resource component, so no render can emit an element on which to open a resource. An event
that no render can fire isn't a signal, it's dead weight that distorts L1 normalization.

**Privacy, decided and corrected:** `learning_events.metadata` **never** stores user text or
copied content. Only `{"element_id": "...", "ms": 1234}`. Text derived from the user lands in
**two** places, not one — an earlier version of this document said "a single place" and
contradicted §3.4:

1. `node_feedback.unclear` — free text the user writes.
2. `term_explanations.term` / `term_normalized` — the selection the user clicked. It's text
   *chosen* by the user, and that's why §8.4 caps what's cacheable at **≤60 characters and ≤4
   tokens**; above that the explanation is served but **not persisted**.

Retention and deletion, all via the same script (`python -m src.scripts.purge_learning_data`, see
§1.3 — there is no `background_jobs` table): `learning_events` at **90 days**; `term_explanations`
at **180 days from `last_used_at`**. Deletion on data-subject request:
`DELETE /users/me/learner-profile` (§11.2) deletes the user's **seven** personal tables —
`node_render_views`, `node_feedback`, `node_attempts`, `node_probes`, `learner_node_states`,
`learning_events`, and `learner_profiles` — and anonymizes `node_renders.generated_by` to `NULL`.
`node_attempts` and `node_probes` hold the answers the employee wrote, so a deletion that left them
behind would return `204` for a promise it hadn't kept; the order follows the FKs from `0005`
(`node_attempts` before `node_probes`, because `node_attempts.probe_id` is `ON DELETE SET NULL`).
The retention script does **not** cover this, nor should it: its job is the two windows above, not
art. 17 erasure.

The vector is computed over a 30-day window with decay:

```
weight_effective = weight * GREATEST(0.2, 1.0 - (age_seconds / (30*86400)) * 0.8)
format_vector[e] = SUM(weight_effective) / SUM(all)      -- L1 normalized
```

**Visibility:** `learner_profiles` and `learner_node_states` are private to the employee. The admin
sees only aggregates with **k ≥ 5** (if the group has fewer than 5 people, the metric isn't shown).
`role_title` and `sector` do travel to the LLM. **`goal` no longer travels to the LLM** (see §3.4
and §6.2): it's consumed deterministically in the frontend for the opening line "this helps you
with X." That reduces the personal data sent to a third party **and** makes question 2's promise
real instead of depending on the model remembering to write it. `users.accessibility` **never**
goes to the LLM (§3.1 explains how `short_blocks` is honored without sending it).

**Notice at the point of collection (GDPR, art. 13):** the onboarding's question-1 screen shows, with
the same visual weight as the question, a fixed line:
*"Your job title and sector are sent to the AI provider to adapt the examples. You can delete them
anytime from Settings."* It isn't optional copy: it's a requirement and lives in `OnboardingRead`
(`notice`), not hardcoded on the client.

### 3.4 Content generated at runtime

```sql
CREATE TYPE ui_format AS ENUM ('explanation', 'simulation', 'exercise', 'chart', 'mixed');
CREATE TYPE node_render_status AS ENUM ('pending', 'generating', 'ready', 'failed', 'fallback');

CREATE TABLE node_renders (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    generated_by   uuid REFERENCES users(id) ON DELETE SET NULL,
    is_preview     boolean NOT NULL DEFAULT false,
    node_id        uuid NOT NULL REFERENCES course_nodes(id) ON DELETE CASCADE,
    cache_key      text NOT NULL,
    ui_format      ui_format NOT NULL,
    ui_spec        jsonb NOT NULL DEFAULT '{}',   -- validated IR; audit only, NOT served
    answer_key     jsonb NOT NULL DEFAULT '{}',   -- never serialized to the client
    dialect        text,                          -- the canonical program the browser painted
    catalog_version text,                         -- "skillnet-ui/1+<digest12>"
    library_version text,                         -- "@openuidev/lang-core@0.2.10; ..."
    backend        text NOT NULL,
    model          text NOT NULL,
    tier           text NOT NULL CHECK (tier IN ('fast', 'heavy')),
    status         node_render_status NOT NULL DEFAULT 'pending',
    tokens_in      int,
    tokens_out     int,
    duration_ms    int,
    error_message  text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    -- Compliance traceability: a row someone viewed says WHAT they saw and against which
    -- catalog. 'pending'/'generating'/'failed' have nothing to show.
    CONSTRAINT ck_node_renders_served_provenance CHECK (
      status NOT IN ('ready', 'fallback')
      OR (dialect IS NOT NULL AND catalog_version IS NOT NULL AND library_version IS NOT NULL)
    ),
    UNIQUE (cache_key)
);

CREATE INDEX idx_node_renders_node   ON node_renders(node_id, created_at DESC);
CREATE INDEX idx_node_renders_status ON node_renders(status);

CREATE TABLE node_render_views (
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    render_id      uuid NOT NULL REFERENCES node_renders(id) ON DELETE CASCADE,
    node_id        uuid NOT NULL REFERENCES course_nodes(id) ON DELETE CASCADE,
    first_seen_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, render_id)
);

CREATE INDEX idx_node_render_views_user ON node_render_views(user_id, node_id, first_seen_at DESC);
```

- **`answer_key` is a column separate from `ui_spec`** and is **never** serialized to the API. It
  is the structural equivalent of v1's `strip_answers()`, but by construction rather than by
  filtering: you can't badly filter what isn't in the same field.
- **`node_renders` has no `user_id`.** It used to have one, `NOT NULL … ON DELETE CASCADE`,
  alongside a global `UNIQUE (cache_key)`, and the two together were incoherent in three ways:
  a per-user lookup never found the shared row (0 hit rate, which is the pillar of the cost
  model); the row only recorded **whoever generated it first**, so §2.1's audit promise was false
  for every cache hit; and offboarding that first employee **destroyed the render everyone else
  was seeing**, and with it the evidence for their certificates. Now: `org_id` for scoping,
  `generated_by` nullable with `SET NULL` for generation traceability, and `node_render_views` for
  the read audit trail (§2.1).
- **The cache lookup is strictly `WHERE cache_key = :key AND status='ready' AND NOT
  is_preview`.** No `user_id` in the `WHERE`, ever.
- **`is_preview`**: renders from `?preview=1` in `shadow` mode are persisted so they can be
  reviewed, but **stay out of the cache**. Without this, a preview generated by an admin
  **before** validating the schema could literally be served to an employee in the same bucket —
  unapproved content reaching a learner through the back door.
- **`cache_key` is globally `UNIQUE`**: two users with the same profile bucket share a render.
  That's deliberate, and it's what makes the cost sustainable.

```
cache_key = sha256(
    f"{node_id}|{course.schema_version}|{preset}|{experience_level}|{role_bucket}"
    f"|{scaffold_band}|{vector_bucket}|{effective_density}|{backend}|{model}|{PROMPT_VERSION}"
)
role_bucket    = slug(role_title or sector or "")[:24]     # "" if there was no onboarding
scaffold_band  = learner_node_states.scaffold_band          # novice|neutral|advanced, fixed per node
vector_bucket  = f"{dominant}:{round(p_dominant,1)}"        # "" during calibration
```

Two corrections relative to the previous version of this formula, both mandatory:

1. **`role_bucket` comes in.** `role_title` is the only thing §6.2 declares travels *literally* to
   the `genera_ui` prompt, and it was the only adaptation with strong evidence — yet it wasn't in
   the key. Result: a sales associate and a shift supervisor with the same preset shared a row, and
   the second one got examples framed for the first one's role, silently erasing the
   personalization onboarding promises. `slug(role_title)` lowers the hit rate; that's accepted,
   because a cache that serves content with the wrong role framing isn't a hit, it's a cheap
   failure.
2. **`mastery_band` is out, `scaffold_band` is in.** `floor(mastery*5)/5` changes with every
   answer: four different keys within a single `critical` node. `scaffold_band` freezes when the
   probe closes (§3.3) and doesn't move until the node closes.

`PROMPT_VERSION` is a constant in `src/llm/prompts/runtime.py`; bumping it invalidates every
render without touching the DB.

**On the cache experiment citation, honestly:** the internal measurement of ~80% hits with 0 stale
deliveries corresponds to a **per-user** key (`user+course+module+bucket`), and the 0% staleness is
a *property of that key*, not a transferable result. This design's **cross-user** key is an
**unmeasured** regime. That's why the first number measured in §14.2 #3 isn't just the hit rate:
it's the pair (hit rate, staleness rate) of the shared key.

```sql
CREATE TABLE node_probes (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    node_id        uuid NOT NULL REFERENCES course_nodes(id) ON DELETE CASCADE,
    schema_version int NOT NULL,
    attempt_no     smallint NOT NULL DEFAULT 1,
    items          jsonb NOT NULL,
    answer_key     jsonb NOT NULL DEFAULT '{}',
    answers        jsonb NOT NULL DEFAULT '[]',
    score          real CHECK (score IS NULL OR (score >= 0 AND score <= 1)),
    mastered       boolean,
    tiebreak_used  boolean NOT NULL DEFAULT false,
    scored         boolean NOT NULL DEFAULT true,
    model          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    completed_at   timestamptz
);

CREATE UNIQUE INDEX uq_node_probes_user_node_version
    ON node_probes(user_id, node_id, schema_version) WHERE scored;
CREATE INDEX idx_node_probes_user_node ON node_probes(user_id, node_id, created_at DESC);

CREATE TABLE node_attempts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    node_id       uuid NOT NULL REFERENCES course_nodes(id) ON DELETE CASCADE,
    render_id     uuid REFERENCES node_renders(id) ON DELETE SET NULL,
    probe_id      uuid REFERENCES node_probes(id) ON DELETE SET NULL,
    item_id       text NOT NULL,
    item_type     exercise_type NOT NULL,
    bloom_level   text CHECK (bloom_level IN
                  ('remember','understand','apply','analyze','evaluate','create')),
    answer        jsonb NOT NULL,
    score         real NOT NULL CHECK (score >= 0 AND score <= 1),
    passed        boolean NOT NULL,
    hints_used    smallint NOT NULL DEFAULT 0,
    feedback      text,
    latency_ms    int,
    attempted_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_node_attempts_user_node ON node_attempts(user_id, node_id, attempted_at DESC);
```

**The partial `UNIQUE` on `node_probes` is the anti-retry rule**, and it's what kept mastery from
being *gameable*: a perfect probe (2/2) returns `mastered`, skips the node, and counts toward
`enrollments.status='completed'` and toward `user_skills`; with two 4-option items, chance succeeds
1 time in 16, so with no attempt limit it took only ~16 re-entries to skip any node — including a
safety-`critical` one — without having seen a single line of content. Concrete rules:

- **One probe scored per `(user_id, node_id, schema_version)`.** Re-entering the node serves the
  stored verdict; no new one is generated.
- **Re-probe only from `needs_review`**, and at least **7 days** after `completed_at`. It's
  inserted with `attempt_no + 1` (the previous row becomes `scored = false`, which is what the
  partial index allows).
- **In a `critical` node the `mastered` verdict can never come purely from selected-response
  items**: the constructed-response tiebreak is **mandatory** (§7.2).
- **`scored = false`** is also used for the declared novice's diagnostic probe (§7.1): it's shown,
  doesn't score, doesn't persist failures, and doesn't consume the single attempt.

`node_attempts` exists instead of reusing `exercise_attempts` because the latter has
`exercise_id uuid NOT NULL REFERENCES exercises(id)`, and items generated on the fly aren't rows in
`exercises`. It does **reuse the `exercise_type` enum** and reuse the existing deterministic
grading, but with an exact name and shape that the previous version of this document got wrong:

- The function is **`grade(exercise_type, content, answer)`, module-level and already pure**, in
  `src/services/exercise_service.py:73` ("Pure and importable without any DB or LLM dependency").
  It is **not** `ExerciseService.grade()` (`ExerciseService` is the class at line 100), and there's
  **no need** to extract it anywhere: it's imported as-is.
- **An adapter is actually needed**, so it's not "zero new logic": `grade()` reads the correct
  answer from a `content` dict shaped like v1 (`correct`, `blanks`, `correct_order`,
  `explanation`), while v2 has the prompts in `QuizItem.props` and the solutions in `answer_key`.
  The adapter is `src/services/node_grading.py::content_for(item_props, answer_key_entry) -> dict`,
  with its own test for each of the 4 deterministic types.
- **The four deterministic types score 0.0 or 1.0**, no partial credit — including `fill_blank`,
  which returns 0.0 if **even one** blank fails (`_grade_fill_blank`, lines 34-43). This is
  load-bearing for the arithmetic in §7.2 and must be kept in mind before "making continuous" any
  item.
- For `practical_case`/`dialogue`, `grade_open_answer()` is used (purpose `eval`), built with
  `get_optional_llm_service`. That factory **also** has to go through `_maybe_fixture` (§12.1) or
  the fixtures flow attempts a real network call.

```sql
CREATE TABLE node_feedback (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    node_id     uuid NOT NULL REFERENCES course_nodes(id) ON DELETE CASCADE,
    difficulty  text NOT NULL CHECK (difficulty IN ('easy', 'ok', 'hard')),
    unclear     text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, node_id)
);

CREATE TABLE term_explanations (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    node_id          uuid REFERENCES course_nodes(id) ON DELETE SET NULL,
    term             text NOT NULL,
    term_normalized  text NOT NULL,
    context_hash     text NOT NULL,
    language         text NOT NULL DEFAULT 'es',
    explanation      text NOT NULL,
    model            text NOT NULL,
    hit_count        int NOT NULL DEFAULT 0,
    created_at       timestamptz NOT NULL DEFAULT now(),
    last_used_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, term_normalized, context_hash, language)
);

CREATE INDEX idx_term_expl_lookup ON term_explanations(org_id, term_normalized, context_hash);
CREATE INDEX idx_term_expl_purge  ON term_explanations(last_used_at);
```

It is only persisted if the term is **≤60 characters and ≤4 tokens** (§8.4). A 140-character
selection is a phrase the user chose, not a term, and storing it indefinitely in a row **without
`user_id`** would also make it impossible to honor an erasure request. Above 60 characters (up to
the hard limit of 140) the explanation is generated and served, but **not written**.
`idx_term_expl_purge` backs the 180-day-from-`last_used_at` deletion.

`context_hash = sha256(normalized_block_text)[:16]`. **Including the context in the key is not
optional**: it's the central argument of the function. "Mercury" in a chemistry node and "Mercury"
next to "planet" must give different explanations. Curio's reference implementation omits the
context from the key, and that's its design bug; it isn't replicated here.

### 3.5 The two instrumentation tables the design takes for granted

These two **don't exist in the repo** (verified: 20 tables, no `llm_usage_log` or `audit_log` in
`src/` or in `0001..0004`), and yet three mitigations in §14.1 and open decision #1 in
§14.2 depend on them. They are created in `0005` instead of continuing to just cite them:

```sql
CREATE TABLE llm_usage_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    use_case    text NOT NULL,          -- decide_formato|runtime_activity_authoring|genera_ui|explain|probe_generate|schema_design
    purpose     text NOT NULL,          -- runtime_fast|runtime_heavy|generation|eval|tutor
    model       text NOT NULL,
    tier        text CHECK (tier IS NULL OR tier IN ('fast','heavy')),
    tokens_in   int,
    tokens_out  int,
    duration_ms int,
    ok          boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_llm_usage_case ON llm_usage_log(org_id, use_case, created_at DESC);

CREATE TABLE audit_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    actor_id    uuid REFERENCES users(id) ON DELETE SET NULL,
    action      text NOT NULL,          -- course_schema_validated|course_schema_unvalidated|node_waived
    subject     text NOT NULL,          -- "course:{uuid}" | "node:{uuid}"
    detail      jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_subject ON audit_log(org_id, subject, created_at DESC);
```

`llm_usage_log` is small and load-bearing: it is the only way to decide §14.2 #1 (real
fast/heavy ratio) with data instead of the 90/10 hypothesis. It is written from **a single
place**, a `log_usage()` wrapper around the calls made by the new nodes; v1 nodes are not
instrumented in this PR. `audit_log.detail` on `course_schema_validated` stores the
**proposed→validated diff** (nodes added, deleted, fields edited): this makes it possible to
measure whether creators actually edit what the LLM proposes, which is the "High" risk from
§14.1 that no structural validation covers.

### 3.6 Delta summary

**13 tablas nuevas:** `course_nodes`, `course_node_prerequisites`, `learner_profiles`,
`learner_node_states`, `learning_events`, `node_renders`, `node_render_views`, `node_probes`,
`node_attempts`, `node_feedback`, `term_explanations`, `llm_usage_log`, `audit_log`.
**8 enums nuevos:** `course_delivery_mode`, `course_schema_status`, `node_criticality`,
`learner_experience`, `node_state`, `error_kind`, `ui_format`, `node_render_status`.
**1 tabla alterada:** `courses` (+6 columnas). **1 enum extendido:** `generation_step` (+2 valores).

> `node_state` keeps the `needs_review` member, but its **only producer in this PR** is the
> hint cap in §7.4. There is no spaced-repetition scheduler (§1.3), so the
> `mastered → needs_review` transition **does not occur** and does not appear in the §7.3 table.

---

## 4. LangGraph pipeline

Two new graphs. The v1 graph (`src/agents/content/`) **does not change behavior**, but it does
get **an extraction refactor with no functional change** (see below). The previous version of
this document claimed that `prepare_context` and `extract_themes` "do not write to the DB" and
could be imported as-is — that was **false**, and two pieces of the design fell with it:

- `nodes.py:177-178` does `await _set_job(job_id, status=GenerationStep.EXTRACTING)` and
  `await _publish_step(job_id, "extracting", …)`; `nodes.py:215-216` does the same with
  `STRUCTURING`. Importing them into `build_schema_graph()` would put the schema job in
  `'extracting'`/`'structuring'` — never in the `'schema_proposing'`/`'schema_proposed'` states
  added by the migration — and would emit generic `step` events.
- The channel is hardcoded in `src/agents/content/errors.py:26-27`
  (`return f"generation:{job_id}"`), so those events would go to `generation:{job_id}`, which no
  schema client would be listening to.

**One single decision:** the **pure** parts are extracted to `src/agents/content/helpers.py`
(`estimate_pages`, `assemble_chunk_text`, `themes_list`) and `src/agents/content/nodes.py`
imports them from there. It is a pure code move with no behavior change, covered by
`tests/test_generation_pipeline.py`, which already exists. The schema graph's nodes are **new**
and live in `src/agents/schema/nodes.py`: they reuse those helpers, `THEME_EXTRACTOR_SYSTEM` and
`build_extraction_prompt`, and write **their own** states and events. No importing of v1 nodes.
`src/agents/content/helpers.py` and `nodes.py` are on the **B2** file list.

### 4.1 Design-time: `build_schema_graph()`

`src/agents/schema/{state.py,nodes.py,graph.py,runner.py,errors.py}`

```
load_source ──► extract_themes_schema ──► design_schema ──► persist_schema ──► END
 (NUEVO, usa       (NUEVO, usa                (NUEVO, LLM)      (NUEVO, DB)
  helpers puros)    helpers + prompt v1)
       └──────────────── on error ────────────────► handle_error ──► END
```

```python
class SchemaState(TypedDict, total=False):
    # Identity
    job_id: str
    org_id: str
    triggered_by: str
    # Inputs
    source_document_ids: list[str]
    course_id: str
    intent_density: int
    # Derived from the source (same shape as v1, computed by the new nodes)
    rag_mode: Literal["full_text", "chunked"]
    full_texts: dict
    extracted_themes: list[dict]
    source_metadata: dict
    available_headings: list[str]   # closed list of real headings from the document
    # New
    proposed_nodes: list[dict]      # title, summary, outcome, criticality,
                                   # prerequisites (indices), source_headings
    schema_warnings: list[str]
    # Control
    error: str | None
    current_step: str
```

`design_schema` makes **one** LLM call (`SCHEMA_DESIGNER_SYSTEM`, `json_mode=True`,
`temperature=0.2`, purpose `generation`) and returns nodes with prerequisites expressed as
**indices** into the list itself, not as uuids — the LLM cannot invent uuids. `persist_schema`
translates them to FKs, runs a topological sort, prunes edges that would create cycles (adding
a warning to `schema_warnings` instead of failing) and writes with `schema_status = 'proposed'`.

**`source_headings` is chosen from a closed list, not invented.** `load_source` collects the
real headings (distinct `chunk_metadata->>'heading'` values from the document, which
`src/services/chunker.py` stores as a string per chunk) into `available_headings`, and the
`design_schema` prompt forces choosing **only from that list**; `persist_schema` discards any
heading outside it and notes it in `schema_warnings`. Without this, a heading invented by the
LLM would not match any chunk and `load_context` (§4.2) would hand an empty source to
`genera_ui` — a silent failure that produces plausible content with no documentary basis.

Checkpointer: `MemorySaver`, same as v1. The job is short and its real state lives in
`generation_jobs` + `course_nodes`. **`langgraph-checkpoint-postgres` is not introduced** in
this PR (a new dependency, and the human gate is already a DB state, not an `interrupt`).

**SSE channel: `f"generation:{job_id}"`, the same one v1 uses** — not `schema:{job_id}`.
Concrete reason: the endpoint being reused has the channel **hardcoded**
(`src/routes/generation_jobs.py:42`, `async for event in subscribe(f"generation:{job_id}")`),
so a dedicated channel would not reach any client without rewriting the endpoint to subscribe
to two channels. Events are already namespaced by type, so sharing the channel does not
collide: `schema_step`, `schema_progress`, `schema_ready`, `error`. The only thing that changes
in the routes file is `_TERMINAL_EVENTS = {"completed", "error", "schema_ready"}` (line 18).

### 4.2 Runtime: `build_node_graph()`

`src/agents/runtime/{state.py,nodes.py,graph.py,router.py,runner.py}`

```
load_context
    │
    ▼
probe_gate ──(mastered)──────────────────────────────────► skip_node ──► END
    │ needs_content
    ▼
decide_formato ──► genera_ui ──► validate_ui ──┬─(ok)─────► persist_render ──► END
                       ▲                       │
                       └──(invalid, retry<1)───┤
                                               └─(fail)──► fallback_seed ──► END
```

```python
class NodeRuntimeState(TypedDict, total=False):
    # Identity
    request_id: str
    org_id: str
    user_id: str
    course_id: str
    node_id: str
    # Loaded context
    node: dict                 # title, summary, outcome, criticality, source_headings
    profile: dict              # role_title, sector, goal, experience_level, preset,
                               # format_vector, nodes_completed, tutor_notes
    node_state: dict           # mastery, state, consecutive_*, last_error_kind
    source_context: str        # source text (RAG or full_text), already trimmed
    # Gate
    mastered: bool
    # Router
    ui_format: Literal["explanation", "simulation", "exercise", "chart", "mixed"]
    tier: Literal["fast", "heavy"]
    format_rationale: str
    # Generation
    backend: str               # "openui" (only dialect in this PR)
    effective_density: int     # course intent_density, bounded by short_blocks (§3.1)
    scaffold_band: str         # novice|neutral|advanced, fixed when the probe closes
    raw_dsl: str
    ui_spec: dict | None
    answer_key: dict
    validation_errors: list[str]
    retry_count: int
    # Output
    cache_key: str
    render_id: str | None
    tokens_in: int
    tokens_out: int
    # Control
    error: str | None
    current_step: str
```

Each node is wrapped by its **own, new** wrapper, `src/agents/runtime/errors.py::
runtime_node_error_wrapper`. The v1 one is **not** adapted: `src/agents/content/errors.py:47-66`
is hard-coupled to `state["job_id"]` and to marking a `generation_jobs` row as `failed`, and
`NodeRuntimeState` has no `job_id` or job row. With an empty `job_id` the v1 wrapper skips
**both the bookkeeping and the `sse.publish`**, so the `error {fallback: true}` contract the
frontend expects in §9.2 would **never be emitted** on a node failure. The new wrapper:

```python
# src/agents/runtime/errors.py
def runtime_node_error_wrapper(name: str):          # keyed on request_id, not job_id
    # on exception:  node_renders.status = 'failed' + error_message
    #                sse.publish(f"node:{request_id}", "error",
    #                            {"step": name, "message": …, "fallback": True})
    #                return {"error": …, "current_step": "failed"}
```

Each node opens its own session with `async_session_factory`, same as v1.

| Node | What it does | LLM |
|------|----------|-----|
| `load_context` | Loads node, profile, state, and the source (see note below). Computes `effective_density` and `cache_key`. **On a hit in `node_renders` with `status='ready'` and `NOT is_preview`, it short-circuits before entering the graph** (checked by the service, not the graph) | — |
| `probe_gate` | Reads `learner_node_states.state`. If `'mastered'` → skip | — |
| `decide_formato` | Decides `ui_format` and calls the router for the tier | Yes, tier `fast` |
| `genera_ui` | Asks the model for the **active backend's dialect**, using `src.render.prompt.render_prompt()` (the artifact generated by `library.prompt()`) as part of the system prompt | Yes, router's tier |
| `validate_ui` | `gate.canonicalize(raw_dsl)`: size caps and reactivity rejection → `backend.parse()` → `UISpec` (the 7 rules) → `serialize()` → the canonical `dialect`. Splits off `answer_key` | — |
| `persist_render` | Writes `node_renders` (`status='ready'`) with `dialect`, `catalog_version` and `library_version`, publishes `ui_done` | — |
| `fallback_seed` | Builds a single-block `Markdown` `ui_spec` from `lessons.content` of the `seed_lesson_id` (or the trimmed `source_context`). `status='fallback'` | — |
| `skip_node` | Marks the node as skipped and publishes `node_skipped` | — |

**The source in `load_context`, with a real implementation path.** The previous version said
"`similarity_search(top_k=8)` … filtering by `source_headings`", and that filter **does not
exist**: `src/repositories/document_chunk_repo.py:73-97` only accepts
`org_id / query_embedding / top_k / document_ids`. **B1** adds a new method to the repository
(the existing one, used by v1 routes, is left untouched):

```python
async def similarity_search_by_headings(
    self, *, org_id, query_embedding, top_k=8,
    document_ids=None, headings: Sequence[str] | None = None,
) -> list[dict]:
    """Same as similarity_search, with
    AND (chunk_metadata->>'heading') = ANY(:headings) when headings is not empty."""
```

Branches, explicit:

- Document with **≤5 pages** → `full_text`. This branch **needs no embeddings**, and is the one
  covered by the fixture tests (§12.1).
- Larger document → `similarity_search_by_headings(headings=node.source_headings)`. It needs a
  real query embedding **and** chunks with a non-null `embedding`
  (`DocumentChunk.embedding` is `Vector(...)` `nullable=False`), so it only works with an
  embedder available. If `headings` returns nothing, it retries without the headings filter and
  logs a warning in the structured log.

**Budgets:** `decide_formato` `max_tokens=256`, `temperature=0.0`, `json_mode=True`.
`genera_ui` `max_tokens=1200` (tier fast) / `2400` (tier heavy), `temperature=0.4`. `MAX_UI_RETRIES = 1`.
Global runtime generation concurrency: `asyncio.Semaphore(6)` in the runner, so that an employee
spike doesn't take down the process.

### 4.3 El router de dos niveles

`src/agents/runtime/router.py`

```python
HEAVY_FORMATS = frozenset({"chart", "mixed", "simulation"})
ALLOWED_UI_FORMATS = frozenset({"explanation", "exercise", "chart", "mixed"})  # simulation OFF
# There is no FAST_FORMATS: select_tier only consults HEAVY_FORMATS, so a second
# constant would be dead code that could go out of sync.

def select_tier(ui_format: str) -> Literal["fast", "heavy"]:
    return "heavy" if ui_format in HEAVY_FORMATS else "fast"

def purpose_for(tier: str) -> str:
    return "runtime_heavy" if tier == "heavy" else "runtime_fast"
```

Routing **at the level of the whole UI**, not per component. It plugs into the purposes
mechanism that already exists in `resolve_llm_config(org_settings, purpose=...)`, so only two
env vars and two org settings keys need to be added:

```python
# src/config.py — Settings
LLM_RUNTIME_FAST_MODEL: str | None = None    # e.g. "groq/llama-3.1-8b-instant"
LLM_RUNTIME_HEAVY_MODEL: str | None = None   # e.g. "groq/openai/gpt-oss-120b"
```

Precedence (the one `resolve_llm_config` already implements, untouched):
`org_settings["llm_runtime_fast_model"]` → `org_settings["llm_model"]` →
`LLM_RUNTIME_FAST_MODEL` → `LLM_MODEL`. If nothing is configured, **both tiers fall back to
`LLM_MODEL`** and everything keeps working with a single model. No specific provider is required.

Every call is logged in `llm_usage_log` (table created in `0005`, §3.5) with `use_case` ∈
`{decide_formato, runtime_activity_authoring, genera_ui, explain, probe_generate,
schema_design}` in order to measure the real
fast/heavy ratio (the 90/10 estimate is a hypothesis, not a data point).

**Single-tenancy: documented here, not fixed here.** `src/deps/llm.py:22-25::_org_settings` and
`SettingsService._get_org` do `select(Organization).limit(1)`. Fixing it properly means
threading a `CurrentUser` into `LLMDep`/`TutorLLMDep`/`EmbeddingDep`/`OptionalLLMDep`, which are
consumed by v1 routes (`src/routes/chat.py:30,47`, `src/routes/exercises.py:61`) **with not a
single test covering them today** (`tests/` has `test_chunking`, `test_generation_pipeline`,
`test_grading`, `test_retrieval_assembly`, `test_skill_service`). Changing v1 route dependency
signatures with no safety net, inside a batch presented as "parallel and safe", is exactly the
kind of silent regression this PR promises not to introduce.

**Decision:** it moves out of B1 and becomes its own `chore` PR (with route tests for chat and
exercise correction as part of it). It is safe to defer because the bootstrap keeps the
**single organization** invariant (`ensure_organization` in the lifespan), so today
`limit(1)` resolves the correct org by construction. The two new purposes do not depend on that
fix: `resolve_llm_config` resolves them via `getattr(settings, f"LLM_{purpose.upper()}_MODEL")`
(`src/llm/client.py:61-67`) regardless of how the org settings were loaded. This is noted in
§14.2 #11, dated.

---

## 5. Render layer

### 5.1 Principle

> **CORRECTED on 2026-07-26** (product decision: full adoption of OpenUI —
> `docs/design/openui-adoption.md`). The sentence that used to be here, *"the browser **never**
> receives generated markup"*, **is no longer true** in the part that matters: the browser receives
> **dialect** and interprets it with `<Renderer>` from `@openuidev/react-lang` over the components we
> register. What remains literally true is the rest: **the LLM never produces HTML** and **the browser
> never receives the text the model wrote**.

```
node + profile + source ──► LLM ──► DIALECT (raw text, NEVER SERVED)
        │
        ├─► gate.check_program()   size caps; no $state, Query, Mutation, @builtins
        ├─► backend.parse()        frozen grammar + the 7 rules from §5.2 (Pydantic)
        ├─► UISpec (jsonb)         audit record, server-only
        └─► backend.serialize()  ──► node_renders.dialect ──► <Renderer> in the browser
                                     (+ catalog_version, library_version)
```

**The three properties that hold this up**, none of which is a style promise:

1. **The browser only ever sees the canonical re-serialization of an already-validated `UISpec`.**
   Never `raw_dsl`. The column is no longer called that (`node_renders.dialect`), precisely so no one
   serves it by accident. A `UISpec` cannot represent state or a tool call, so the property is
   **structural**, not a check.
2. **The server is still the one that validates.** OpenUI's client-side parser paints; ours decides.
   Its parser silently accepts made-up enums, wrong types, duplicate ids, `<script>` and
   `Mutation("delete_all_users", {...})` with `meta.errors=[]`; ours cannot even represent them.
3. **`answer_key` is never serialized.** Same as before: rule 5 of §5.2, a separate column, and no
   response schema mentions it.

**New surface this opens, said out loud: mutations.** The real language has state (`$var`), queries
(`Query`), mutations (`Mutation`), actions (`Action`, `@OpenUrl`, `@ToAssistant`, `@Set`) and 13
builtins. A poisoned PDF can try to emit them. Mitigation, in four stacked, measured controls
(`SEGURIDAD-MUTACIONES.md`):

| Control | How | Measured effect |
|---|---|---|
| Never serve raw text | `serialize()` from the validated `UISpec` | The 10 re-serialized fixtures parse with 0 violations |
| `toolProvider` **absent** from `<Renderer>` | by omitting the prop | `createQueryManager(null)`: zero network, both queries **and** mutations cut off |
| `onAction` and `onStateUpdate` **absent** | by omitting the props | `@OpenUrl`/`@ToAssistant` are no-ops; `@Set` is not persisted. And with no component calling `useTriggerAction()`, an `ActionPlan` isn't even reachable |
| Gate on both sides | `src/render/gate.py` + `parse()` on the server; `assertStaticOnly(parseResult)` in `onParseResult` on the client | 15/15 payloads rejected, 0 false positives across the 10 valid fixtures |

And the cheapest one of all: **the prompt does not teach reactivity**. Without `tools` and without
`markReactive()`, `library.prompt()` never mentions `$var`, `Query(`, `Mutation(`, `@Run` or `@Set`.
It's defense in depth, not a wall: if the model emits it from memory, the gate is what rejects it.
`RENDER_ALLOW_REACTIVE=false` is the switch, and the conditions for touching it are in
`docs/design/openui-adoption.md` §6.

Switching dialects by flipping an env var still works; the pipeline, the IR and the DB don't notice.
The **frontend now would** notice: it receives dialect, not IR.

### 5.2 The canonical IR: `UISpec`

**Flat** list of components with references by id (LLMs generate flat lists better than nested
trees, and this makes incremental parsing trivial).

```json
{
  "version": "skillnet-ui/1",
  "format": "explanation",
  "root": "b0",
  "components": [
    {"id": "b0", "type": "Stack",    "props": {"gap": "md"},
     "children": ["b1", "b2", "b3"]},
    {"id": "b1", "type": "TextContent",
     "props": {"text": "Returns are accepted within 30 calendar days.",
               "variant": "body"}},
    {"id": "b2", "type": "StepSequence",
     "props": {"title": "Return process",
               "steps": ["Check the product", "Scan the receipt",
                         "Log it in the system", "Issue the refund"]}},
    {"id": "b3", "type": "QuizItem",
     "props": {"item_id": "q1", "item_type": "test", "bloom_level": "apply",
               "question": "A customer returns an item on day 32. What do you do?",
               "options": ["Accept the return", "Offer the manufacturer's warranty",
                           "Reject it outright", "Call the manager"]}}
  ]
}
```

Contract rules, validated by Pydantic in `src/render/spec.py`:

1. `root` must exist in `components` and be a container type (`Stack` or `Card`).
2. Every reference in `children` must exist. Forward references allowed.
3. No cycles in the `children` tree.
4. Maximum **12** components per spec and **5 elements** at the root level of the `Stack`. This isn't
   aesthetics: working memory processes 4-7 elements, and a "cognitive screen" is 3-5 related
   elements. A spec with 30 blocks is a generation failure, not rich content.
5. `QuizItem` **does not carry** the correct answer or an explanation. That goes in `answer_key`.
   **Corollary, demonstrated (2026-07-26):** 100% client-side correction is **incompatible with this
   rule by construction** — writing the verdict as `$chosen == 1` requires serializing the answer to
   the browser. This isn't a flaw in OpenUI Lang, it's arithmetic. The path that does respect it is
   `Mutation("grade_answer", {item_id, choice})` with a round trip to the server, and it's turned off
   (§5.1).
6. `props.text` is plain text or inline markdown (`**`, `*`, `` ` ``, links). Never HTML.
7. **The first child of `root` in the `explanation` and `mixed` formats must be a `TextContent`
   (`variant: "lead"`) or a `Callout`.** It's a validation error, not a warning, and it's the slot
   where the frontend injects the "this helps you with X" line derived from `goal` (§6.2 Q2). Without
   this rule, question 2's promise had nowhere to materialize.

**Quality heuristic (not a contract rule):** two sibling components with token similarity > 0.8 say
the same thing twice (redundancy effect). `validate_ui` logs it in the structured log and in
`node_renders.error_message` as a warning, **and does not reject the spec**. It's deliberately left
out of the contract because measuring "saying the same thing in two formats" with token similarity
has obvious false positives (a table summarizing the steps the text just listed is good
redundancy). If the §14.2 data shows this happening often with real harm, it gets promoted to an
error; until then it isn't presented as a fulfilled contract.

`answer_key`, stored separately and never serialized to the client:

```json
{"q1": {"item_type": "test", "correct": 1,
        "explanation": "Manual p.3: after 30 days the manufacturer's warranty applies",
        "bloom_level": "apply"}}
```

### 5.3 The SkillNet UI Kit — frozen list

**Updated on 2026-07-26.** Where each thing lives since the adoption:

* `apps/skillnet-web/src/components/courses/kit/` — **the catalog, in zod + `defineComponent`**. This
  is where the prompt comes from: `scripts/generate-openui-prompt.mjs` calls `library.prompt()` and
  writes `apps/skillnet-api/src/render/openui_prompt.txt` + `openui_catalog.json`. A single place
  where the list is declared.
* `src/render/kit.py` — **source of truth for validation** (types, enums, positional order, the 7
  rules via `src/render/spec.py`). It **no longer** generates the prompt.
  `tests/test_render_prompt_artifact.py` recomputes the catalog digest from here and fails if the
  artifact doesn't match: it's the drift alarm between the two sides, the one that will warn the day
  its API changes.
* `apps/skillnet-web/src/components/courses/blocks/` — the React implementation, now registered in
  OpenUI's library instead of dispatched via `switch`.

The browser library registers **ten** components and the prompt catalog advertises **nine**:
`Markdown` is written by the server for `fallback_seed` and the model cannot emit it. Since the
browser now receives dialect, the fallback also needs a dialect form, so `serialize()` covers all
ten and `parse()` still rejects `Markdown`. The asymmetry didn't disappear: it moved.

| Component | Props (**positional** order for the OpenUI dialect) | What it's for |
|---|---|---|
| `Stack` | `children: string[]`, `gap: "sm"\|"md"\|"lg"` | Vertical container |
| `TextContent` | `text: string`, `variant: "body"\|"lead"\|"caption"` | Prose |
| `Card` | `title: string`, `children: string[]` | Grouping |
| `Callout` | `tone: "info"\|"warn"\|"success"`, `text: string` | Critical rule, exception |
| `StepSequence` | `title: string`, `steps: string[]` | Procedure (2-7 steps) |
| `Table` | `headers: string[]`, `rows: string[][]` | Compare concepts |
| `CodeBlock` | `language: string`, `code: string` | Code example |
| `Chart` | `kind: "bar"\|"line"`, `title: string`, `labels: string[]`, `values: number[]` | Quantitative data |
| `QuizItem` | `item_id: string`, `item_type: exercise_type`, `bloom_level: string`, `question: string`, `options: string[]` | Exercise |
| `Markdown` | `content: string` | **Only** for `fallback_seed`. The LLM cannot emit it |

Naming decisions, closed: `StepSequence` (not `StepList`); `Chart` unified with `kind` (not
`BarChart`/`LineChart`); `Callout` is included because procedural exceptions are 80% of compliance
content; `Timeline`, `ImageCard`, `DragDrop`, `Simulation` and `SandboxHTML` **are not included**.

The 6 values of `item_type` are exactly those of the existing `exercise_type` enum.

**`QuizItemBlock` is self-contained; it is not a bridge to v1's `ExerciseRenderer`.** The earlier
claim ("reused as-is, only swapping the submission hook") was false: each of the six exercise
components builds **its own** mutations and relies on the id of a real row in `exercises` — e.g.
`TestExercise.tsx:3` imports `useSubmitAttempt`/`useCorrectExercise`, calls them on lines 10-11, does
`correctMut.mutate(exercise.id)` and uses `name={exercise.id}` for the radio group. Turning them into
controlled components would require refactoring all six to accept injected handlers: v1 surface no
batch budgets for. **Decision:** B6 writes `QuizItemBlock.tsx` with its own state and its own
submission against `POST /nodes/{id}/answer` (2 internal subcomponents for single-choice and text),
and **does not touch `src/components/exercises/`**. The duplication of ~120 lines of UI is accepted
in exchange for not touching v1.

### 5.4 The adapter interface

`src/render/backends/base.py`

```python
class RenderBackend(Protocol):
    name: str                                    # "openui" (the registry allows more)

    # prompt_fragment() WAS REMOVED on 2026-07-26: the prompt is now generated by
    # library.prompt() in the build step and read by src/render/prompt.py. A backend
    # validates a dialect and re-writes it; it no longer teaches it.

    def parse(self, raw: str, *, ui_format: str | None = None) -> UISpec:
        """Parses the complete dialect. Raises RenderParseError."""

    def parse_partial(self, raw: str, *, ui_format: str | None = None) -> UISpec:
        """Tolerant parsing of incomplete output (streaming). Discards the last
        line if it's mid-way through. Never raises. Still needed on the server
        even though the browser also parses: what gets sent during streaming is
        the canonical re-serialization of the prefix, never the model's bytes."""

    def serialize(self, spec: UISpec) -> str:
        """Spec -> canonical text. The ONLY thing the client can receive."""
```

```python
# src/render/backends/__init__.py
_BACKENDS = {"openui": OpenUiLangBackend()}      # a single dialect in this PR

def get_render_backend(name: str | None = None) -> RenderBackend:
    return _BACKENDS[(name or settings.RENDER_BACKEND)]
```

**Validation parsing is Python, in the backend; painting parsing is JavaScript, in the browser.**
Of the three consequences this paragraph used to claim, (b) still holds — the fixtures cover the
parser without a browser — and the other two changed on 2026-07-26: (a) npm dependencies **do**
enter now (`@openuidev/react-lang@0.2.9`, `@openuidev/lang-core@0.2.10`, `zod@4.4.3`, exact
versions), and (c) **the browser no longer receives JSON**, it receives dialect. What takes the place
of (c) are the three properties and four controls from §5.1.

**Backend 1 — `openui` (DEFAULT).** `src/render/backends/openui.py`. Line-by-line dialect, one
declaration per line, **positional** arguments in the kit table's order, references by array:

```
root = Stack([intro, steps, quiz], "md")
intro = TextContent("Returns are accepted within 30 calendar days.", "body")
steps = StepSequence("Return process", ["Check the product", "Scan the receipt", "Log it in the system", "Issue the refund"])
quiz = QuizItem("q1", "test", "apply", "A customer returns an item on day 32. What do you do?", ["Accept the return", "Offer the manufacturer's warranty", "Reject it outright", "Call the manager"])
```

Chosen as default for token density (≈50% less than equivalent JSON) and because the line-by-line
format makes `parse_partial` trivial: every `\n` completes a component. The variable name is the
component's `id` in the IR.

**Frozen grammar.** Lives in the docstring of `src/render/backends/openui.py` and is **no longer** a
`GRAMMAR` constant pasted into the prompt: `library.prompt()` puts the syntax block in. It's still
the gate's specification, and it's what makes reactivity **inexpressible** rather than being on a
blocklist. An "obvious" dialect with one example and no rules is what an 8B model breaks on day one;
these three are exactly the ones it breaks, and they go into the prompt via `additionalRules`:

```ebnf
program    = { line } ;
line       = ident "=" call newline ;
ident      = ("a".."z" | "A".."Z" | "_") { "a".."z" | "A".."Z" | "0".."9" | "_" } ;
call       = comp_name "(" [ arg { "," arg } ] ")" ;
comp_name  = "Stack" | "TextContent" | "Card" | "Callout" | "StepSequence"
           | "Table" | "CodeBlock" | "Chart" | "QuizItem" ;
arg        = string | number | array | ident | call ;
array      = "[" [ arg { "," arg } ] "]" ;
string     = '"' { char | escape } '"' ;
escape     = "\" ( '"' | "\" | "n" ) ;
char       = <any character except '"', '\' and newline> ;
number     = [ "-" ] digit { digit } [ "." digit { digit } ] ;
```

**`arg = … | call` is from 2026-07-27** (`docs/design/openui-adoption.md` §4 bis). An inline nested
call, `root = Stack([TextContent("Hi.", "lead")], "md")`, is valid OpenUI Lang and the signature
block that `library.prompt()` generates offers it; rejecting it was a subset of our own making, not
a rule of the standard, and it cost a 7B model the entire repair loop. `parse` **flattens** it into
the `UISpec`'s flat list with deterministic synthetic ids (`root_1`, `root_1_1`, …), so rule 4 of
§5.2 is counted after flattening; it only makes sense where the kit declares a `ref[]`
(`Stack.children`, `Card.children`) and in any other position it's a named error; and per-line depth
is capped (16) so recursion isn't a crash vector. `serialize` still emits **only** the referenced
form: it's the canonical form, the one its prompt recommends for streaming, and the only one that
gives each block a real `statementId` in the browser.

The three rules the prompt repeats imperatively and that the malformed fixtures cover one by one:

1. **Double quote inside a string: `\"`.** Never unescaped.
2. **Nested arrays allowed and required in `Table.rows`** (`string[][]`):
   `Table("t", ["A","B"], [["1","2"],["3","4"]])`.
3. **No literal newline inside a string** — write `\n` instead. This is a hard restriction, not
   stylistic: `parse_partial`'s whole premise is that every `\n` closes a component, so a literal
   break inside a quote breaks incremental parsing, not just the complete one. `parse()` rejects an
   unclosed string at end of line; `parse_partial()` discards that line.

**There is no second backend in this PR.** The seam does go in (the `Protocol` and the registry), the
second dialect does not — see §1.3 for the reason (`UIDL/1` cannot represent the `UISpec`). Concrete
consequences, all applied further below: `RENDER_BACKEND_FALLBACK` disappears from §10.2; the
"cross retry" disappears from §14.1; and `tests/test_render_a2tl.py` doesn't exist.

**What takes its place as a second attempt** (which was the real value of the cross retry): in the
single retry (`MAX_UI_RETRIES = 1`) the prompt is not the same one. `UI_REPAIR_SYSTEM` is sent,
which includes the failed `raw_dsl`, the parser's exact `validation_errors`, and the instruction to
return the corrected program and nothing else, with `temperature=0.0`. Repairing with the error in
hand is more effective than retrying blind or switching dialects. If that also fails:
`fallback_seed`. The "never a red screen" safety net is provided by `fallback_seed`, not by a second
dialect.

### 5.5 Frontend side

> **CORRECTED on 2026-07-26.** The `switch`-based dispatch over a `UiSpec` is replaced by
> `<Renderer>` from `@openuidev/react-lang` over the library at
> `src/components/courses/kit/`: the same ten block components, now registered instead of
> dispatched, with streaming carried by `isStreaming`. The props that are **not** passed are part of
> the security contract (§5.1): no `toolProvider`, no `onAction`, no `onStateUpdate`. The block below
> describes the earlier shape and is kept because the spatial stability zones, the pinning of
> `active_render_id`, and the two control affordances **do not change**.

`apps/skillnet-web/src/components/courses/UiSpecRenderer.tsx` — same dispatch pattern as
`ExerciseRenderer`:

```tsx
export function UiSpecRenderer({ spec, nodeId }: { spec: UiSpec; nodeId: string }) { … }
// switch (component.type) → blocks/StackBlock, TextContentBlock, CardBlock,
//   CalloutBlock, StepSequenceBlock, TableBlock, CodeBlockBlock, ChartBlock,
//   QuizItemBlock, MarkdownBlock
```

`ChartBlock` is drawn with inline SVG (no Chart.js or Recharts added). `MarkdownBlock` reuses
`LessonContent`, which is kept intact and also becomes the fallback. A component of unknown type
renders `null` and logs a warning — it never breaks the page.

**Spatial stability zones**, mandatory in `NodeView.tsx`:

| Zone | Content | Can it change |
|------|-----------|---------------|
| Frozen | Header, node title, `ProgressBar`, previous/next buttons, chat access | Never |
| Stable | Order and content of the blocks **while the node is open** | Only if the user asks for it |
| Adaptive | Which examples, which format, which depth, which difficulty, **between** nodes and sessions | Freely |

**How the "Stable" row is guaranteed** (previously a promise with no mechanism):
`GET /nodes/{id}/render` serves `learner_node_states.active_render_id` while `render_pinned` is
`true`. It doesn't recompute the key, so answering an item cannot change the screen, and a TanStack
Query refetch on window refocus returns byte-for-byte the same thing.

**User control, two minimal affordances** (not optional; they're the counterpart to adapting
nothing):

1. **"Update this lesson"** — a button in the node footer that does
   `POST /nodes/{id}/render {"force": true}` and repaints `active_render_id`. It's the **only** way
   an open node's content changes.
2. **"See the previous version"** — when regenerating, a line reading "this lesson has been adapted
   to your latest answers" is shown with a link to the previous render. The rows already exist in
   `node_renders` and `node_render_views` (ordered by `first_seen_at DESC`), so it's a query, not a
   new table.

**On revisiting an already-seen node, the latest render for that `(user, node)` is served**, not a
new one, even if the profile has changed. Regenerating requires the button.

---

## 6. Onboarding

### 6.1 Shape

5 screens, **one question per screen**, at most 3 visible elements per screen, target
**≤90 seconds**. Skippable at any point with "I'll do it later". Asked **once**: skipping writes
`onboarding_completed_at` and `onboarding_skipped = true`, and it isn't asked again (it can be redone
from settings). The 5-screen and 3-element limits come from the documented attention adaptations
(5-question-max tests, 3 bullets per screen).

**Skipping writes `experience_level = 'unknown'`, not `'none'`** (§3.3): `'none'` means "declares
being a beginner" and forces beginner scaffolding, which is the case that hurts the expert. Someone
who skips hasn't declared anything.

**Gate in `ProtectedRoute`, with the details that matter.** `ProtectedRoute` today only has
`useAuth()` (`user`, `isLoading`), and it **also** wraps every admin page, so:

```
redirects to /onboarding  ⇔  features.dynamic_courses === 'on'
                           ∧  user.role === 'employee'
                           ∧  profile loaded with onboarding_completed_at == null
```

- The flag is read from `GET /health` once at startup (see §10.1 — **not** from `/auth/me`).
- The profile query is **conditioned** on `role === 'employee' && flag === 'on'`, so an admin never
  triggers it.
- A **404** from the profile endpoint means "don't redirect", not "not onboarded". If it meant the
  latter, turning the flag off mid-session (routes become 404) would drop the user into a redirect
  loop toward a route that no longer exists.
- While the query is in flight, `AppSkeleton` is painted, never a redirect.

### 6.2 The questions

| # | Question (en) | Type | Field | Why this one and not another |
|---|---------------|------|-------|------------------------|
| 1 | "What's your role?" | free text + 6 org-sector suggestions | `learner_profiles.role_title`, `sector` | The role goes **literally** into `genera_ui`'s system prompt to contextualize the examples. It's **content** adaptation, the one with strong evidence |
| 2 | "What do you want to use SkillNet for right now?" | 3 options + "other" | `goal` | Andragogy principle: adults need to know the WHY before investing time. **It never travels to the LLM.** It's rendered as a deterministic opening line in the `lead` block that rule 7 of §5.2 requires to exist (templated by `goal` value, on the client). This way the promise is always fulfilled, not only when the model remembers |
| 3 | "How much experience do you have in your current role?" | None / Some / Plenty | `experience_level` | Prior knowledge is the **only** dimension with a large effect: it reverses instructional design (worked examples help the novice and **hurt** the expert). **The question does not name any course**: the field is one per person (`UNIQUE (user_id)`) and enters the `cache_key` of *all* their courses, so asking about "Customer service" and then applying it to "Fire prevention" would be incoherent. Per-competency granularity is provided by `user_skills` via `course_nodes.skill_id` (§7.1), not by the declaration |
| 4 | "How do you prefer to study?" | Standard / Focus / Fast pace, each with a one-line description | `preset` (+ mirrored in `users.learning_profile`) | It's **presentation**, not modality. Gives real autonomy and is reversible without restrictions |
| 5 | "Want to turn on any reading settings? (optional)" | checkboxes: short blocks · fewer animations · more contrast · no time limit | `users.accessibility` | No diagnosis, no label. **"Read aloud" is removed**: there's no TTS in this PR nor an audio component in the kit, and offering a nonexistent accommodation is worse than not offering it. "Shorter blocks" is real: it translates to `effective_density ≤ 2` on the server (§3.1) |

### 6.3 What is not forced during this onboarding

- **Initial level via test.** The system adjusts by performance; the per-node pre-assessment already
  does that job, and better, because it's per competency, not global.
- **Preferred format** (video, text, audio?). It isn't forced as an initial question nor turned into
  a "learning style" label. However, any later explicit choice is respected and overrides the
  `format_vector`. The requested modality can combine different pedagogical strategies — retrieval,
  self-explanation, contrast, or scenario — without replacing the user's choice. See
  [`adaptive-learning.md`](/en/docs/adaptive-learning).
- **Neurodivergence diagnoses.** A diagnosis is health data (special category, GDPR art. 9) and isn't
  needed: the concrete settings from question 5 produce the same functional result without the legal
  risk. Question 5 asks about **needs**, not conditions.

### 6.4 Calibration period

For a new user the `format_vector` is all zeros: there's no signal. Hard rule, implemented in
`decide_formato`:

```
if profile["nodes_completed"] < 3:
    vector_bucket = ""                          # doesn't enter the cache_key
    ui_format = node.default_ui_format          # real column, §3.2 — decide_formato isn't called
    # the prompt receives ONLY: role_title, sector, experience_level, preset,
    # effective_density and scaffold_band
```

**What exactly "doesn't adapt" means, with the boundary drawn** — the earlier version said "the
presentation doesn't adapt" while §4.2 fed the full `node_state` into the prompt from node 1, which
contradicted it:

| Dimension | Does it act during calibration? |
|---|---|
| **Format** (`ui_format`: explanation vs exercise vs table) | **No.** `node.default_ui_format` is used |
| **Implicit vector bucket** (`vector_bucket` in the key and the prompt) | **No.** Events accumulate and are not used |
| **Content** (role, sector, source) | **Yes**, from the first node |
| **Scaffolding** (`scaffold_band`, `last_error_kind`, `consecutive_failed`) | **Yes.** It's difficulty and support, not spatial layout: responding to the learner's error doesn't move the interface around |

The reason for the first row is the lesson from the failure of Office 2000-2003's adaptive menus: the
user must form their mental map before the interface starts moving.

**Expected node distribution and its uncomfortable consequence.** A typical compliance course has
**3-6 nodes**; process courses, 6-12. With a 3-node course and a single enrollment, the
`format_vector` subsystem (events endpoint, decay, L1 normalization, `vector_bucket`, 90-day purge)
**does not influence a single render**: the user finishes the course still in calibration. This is
accepted knowingly — the vector is infrastructure for the second and third course, not the first —
and that's why nodes skipped by the probe do **not** increment `nodes_completed` (§3.3): if they did,
someone could leave calibration with zero interaction events and the vector would be applied over
noise.

---

## 7. Pre-assessment and mastery rule

### 7.1 The items

When a node is opened, `POST /nodes/{node_id}/probe` returns **2 items** (3 for `critical` nodes):

- **Item A — `bloom_level = "apply"`**, of type `test` with exactly **4 options**. A case, not a
  definition. It's the deciding one.
- **Item B — `bloom_level = "understand"`**, of type `test` with exactly **4 options**.
  **`true_false` is no longer allowed**: with true/false the chance floor rises from 6.25% to 12.5%,
  and the number §7.2 uses to justify the doubt band would stop being true.
- **Item C (tiebreak)** — **constructed** response: `fill_blank` or a short `practical_case`. In a
  `critical` node it's **always mandatory**; in others only if the verdict falls in the doubt band.

Item source, in order of preference:

1. **Pre-generated at schema validation** and stored in `course_nodes.probe_items` /
   `probe_answer_key` (§3.2). This is the normal case: **zero tokens and zero wait**. Items depend
   only on `(node, source)`, so one generation per node serves the whole organization.
2. If the node has a `seed_lesson_id` and there are no pre-generated items, existing exercises from
   that lesson are sampled at the requested Bloom levels. **Zero tokens.**
3. Last resort: an LLM call (purpose `runtime_fast`, `json_mode`, `max_tokens=500`) from
   `node.summary` + `source_context`, written into `course_nodes.probe_items` so the next employee
   doesn't pay for it.

The attempt is recorded in `node_probes` with a separate `answer_key`, **a single scored row per
`(user_id, node_id, schema_version)`** — see §3.4 for the full anti-retry rule, which is what
prevents skipping a node by re-entering until you get it right by chance.

**Prior from `user_skills`, instead of starting everyone at 0.** `course_nodes.skill_id` exists and
`user_skills.skill_level` already carries a verified level (including peer/manager verification).
When `learner_node_states` is created, it is seeded with:

```python
mastery_prior = {"high": 0.85, "medium": 0.55, "low": 0.25}.get(user_skill_level, 0.0)
```

It's only the EWMA's and `scaffold_band`'s starting point; it does **not** skip the node by itself
(that's decided by the probe). Until now §7 only wrote to `user_skills` and never read it, wasting
the only prior-mastery signal the product already had.

**Diagnostic probe for the declared beginner.** If `experience_level == 'none'` and
`nodes_completed == 0`, the first node's probe is served with `scored = false`: it's presented as
"let's see what you already know", it **does not persist failures**, doesn't score mastery, and
doesn't consume the single attempt. Without this, the first product experience for someone who has
just declared themselves a beginner is N×2 guaranteed failures before seeing a single line of
content.

### 7.2 The rule, made computable

**Honest starting point:** the four deterministic types score **0.0 or 1.0**, with no partial credit
(verified in `exercise_service.py:25-57`, `fill_blank` included). With two binary items,
`0.6a + 0.4b` can only take the values `{0.0, 0.4, 0.6, 1.0}`. Consequence of the previous version of
this rule: the three thresholds (0.90 / 0.80 / 0.70) **behaved identically** — 1.0 mastered in all
three, 0.6 fell into tiebreak in all three, 0.4 and 0.0 stayed in learning in all three — and the
`0.5a+0.2b+0.3c` tiebreak capped out at **0.80**, below `critical`'s 0.90, so on a critical node it
was dead code: an LLM call and an extra question that couldn't change the verdict.

```python
# src/services/mastery_service.py

THRESHOLDS = {"critical": 0.90, "recommended": 0.80, "contextual": 0.70}
DOUBT_BAND_FLOOR = 0.55
W_APPLY, W_UNDERSTAND = 0.6, 0.4
# Renormalized tiebreak: a perfect third item reaches 1.0, so
# ALL thresholds are reachable and none is unreachable.
W3_APPLY, W3_UNDERSTAND, W3_CONSTRUCTED = 0.45, 0.15, 0.40
FADING_STREAK = 3             # N
REGRESS_STREAK = 2

def probe_estimate(score_a: float, score_b: float) -> float:
    return W_APPLY * score_a + W_UNDERSTAND * score_b

def probe_verdict(score_a, score_b, criticality, threshold=None):
    """Verdict with ONLY the two selected-response items."""
    est = probe_estimate(score_a, score_b)
    if score_a < 0.5:                       # fails apply → never masters
        return "learning", est
    if est >= 1.0:
        # Everything correct. On a critical node this is NOT enough: chance here is 1/16.
        if criticality == "critical":
            return "tiebreak", est
        return "mastered", est
    if est >= DOUBT_BAND_FLOOR:             # 0.6 → doubt
        return "tiebreak", est
    return "learning", est

def tiebreak_mastery(score_a, score_b, score_c) -> float:
    return W3_APPLY * score_a + W3_UNDERSTAND * score_b + W3_CONSTRUCTED * score_c

def tiebreak_verdict(score_a, score_b, score_c, criticality, threshold=None):
    m = tiebreak_mastery(score_a, score_b, score_c)
    thr = threshold if threshold is not None else THRESHOLDS[criticality]
    return ("mastered" if m >= thr else "learning"), m
```

Resulting arithmetic, verified (`tests/test_mastery.py` asserts it case by case):

| a | b | c | `tiebreak_mastery` | critical 0.90 | recommended 0.80 | contextual 0.70 |
|---|---|---|---|---|---|---|
| 1 | 1 | 1 | **1.00** | masters | masters | masters |
| 1 | 0 | 1 | **0.85** | learns | masters | masters |
| 1 | 1 | 0 | **0.60** | learns | learns | learns |
| 1 | 0 | 0 | **0.45** | learns | learns | learns |

The thresholds now **actually discriminate** and none is unreachable. Four rules that make this
defensible:

1. **You cannot master while failing the apply item** (`score_a < 0.5` → `learning`, no exceptions).
2. **In a two-selected-item probe, the honest verdict is "all correct = candidate".** It's phrased
   this way instead of pretending a continuous threshold discriminates over four possible values.
   The per-criticality threshold does its real work in two places: deciding whether constructed
   confirmation is needed, and in the `learning → mastered` transition in §7.3.
3. **On a `critical` node, `mastered` never comes purely from selected response.** The constructed
   tiebreak is mandatory. Combined chance: 1/16 × ~0 ≈ 0. Together with the single probe per schema
   version (§3.4), skipping a safety node by luck stops being a strategy.
4. **The threshold depends on criticality**, not on the person.

### 7.3 Mastery during the node

After every `POST /nodes/{node_id}/answer`:

```python
ALPHA = 0.4      # weight of new evidence (EWMA)

mastery_new = (1 - ALPHA) * mastery_old + ALPHA * score
if passed:
    consecutive_correct += 1; consecutive_failed = 0
    # MASTERY CEILING: without this the EWMA converges to the average of the
    # scores, so someone sustaining 0.85 asymptotes at 0.85 and NEVER reaches
    # a critical node's 0.90 -> course impossible to complete.
    if consecutive_correct >= FADING_STREAK:
        mastery_new = max(mastery_new, node.mastery_threshold)
else:
    consecutive_failed += 1; consecutive_correct = 0
    mastery_new = min(mastery_new, mastery_old)     # a failure never raises mastery
```

The ceiling corrects a real arithmetic flaw: `mastery_new = 0.6·old + 0.4·score` has a fixed point at
`score`, so the competent-but-imperfect learner (sustained 0.85) would stay 0.05 short of the
threshold forever, and since `enrollments.status='completed'` requires **all** `critical` nodes to be
`mastered`, the course would remain permanently incomplete with no way out. With the ceiling, three
consecutive correct answers *are* sufficient evidence: it's the same streak already required, now
also applied to the magnitude and not just the counter.

`node_state` transitions, deterministic and **complete** (the 8 covered by
`tests/test_mastery.py`):

| # | From | Condition | To | Effects |
|---|-------|-----------|-------|---------|
| 1 | `not_started` | probe is requested | `probing` | `first_seen_at`, `mastery` = prior from `user_skills` (§7.1) |
| 2 | `probing` | `probe_verdict == "mastered"` | `mastered` | `probe_score = est`; `mastery = max(prior, est)`; `mastered_at`; **`nodes_completed` is NOT incremented** |
| 3 | `probing` | `probe_verdict == "tiebreak"` | `probing` | `tiebreak_used = true`; item C is served; `probe_score` not yet written |
| 4 | `probing` | `tiebreak_verdict == "mastered"` | `mastered` | `probe_score = m`; `mastery = max(prior, m)`; `mastered_at` |
| 5 | `probing` | `probe_verdict`/`tiebreak_verdict == "learning"` | `learning` | `probe_score` written; **`mastery` is NOT touched** (prior remains); `scaffold_band` frozen |
| 6 | `learning` | `mastery >= threshold` **and** `consecutive_correct >= 3` | `mastered` | `mastered_at`; `nodes_completed += 1` |
| 7 | `learning` | `consecutive_failed >= 2` | `learning` | lowers difficulty, no state change; `reforzar_con_ejemplo` signal |
| 8 | `learning` | 4th failure on the same item after 3 hints (§7.4) | `needs_review` | worked solution shown; the node enters the practice queue |

Two ambiguities that used to be open and affect certificates, closed above: **`mastery` after a
probe** is written only if the verdict masters (`max(prior, estimate)`), and if the verdict is
`learning` the prior is kept — so `probe_score` and `mastery` don't step on each other; and
**`nodes_completed`** is incremented only in transition 6. Without pinning both down,
`enrollments.score` (average of `mastery` over `critical` nodes) varied by implementation detail,
and that ends up printed on a certificate.

**`mastered → needs_review` does not exist in this PR**: it would require the spaced-repetition
scheduler, which isn't in the repo (§1.3). The only producer of `needs_review` is transition 8.

**`FADING_STREAK = 3` and `REGRESS_STREAK = 2`**, fixed, the same for every criticality. The value
that already appears in the research is chosen (3 correct answers raise, 2 failures lower) and it
isn't parameterized per skill until there's real data.

Requiring both `mastery >= threshold` **and** a streak of 3 avoids the central problem of
*cognitive offloading*: with AI-generated content the learner reports less cognitive load but
produces weaker answers — the "illusion of mastery". A streak requires repeated production, not a
lucky spike.

### 7.4 Scaffolding escalation

Hard rules in `genera_ui`'s prompt and in the service, not suggestions:

- **`attempt-before-hint`**: no hint is offered until at least one attempt is recorded in
  `node_attempts` for that `item_id`. **A click-to-explain inside an unanswered `QuizItem` counts as
  a hint** and consumes the quota — see §8.5, where it used to be an escape hatch that didn't touch
  `hints_used`.
- **Hint cap: 3, with a defined exit.** On the fourth failure the full worked solution is shown and
  the node moves to **`state = 'needs_review'`** (not `'learning'`), which gives it three things it
  didn't have before — the earlier version said "the node is passed over" without defining **any**
  way back:
  1. **Visibility**: `NodeListRead` exposes `needs_practice: true` and the node appears in a
     "to practice" section, instead of disappearing.
  2. **Re-entry**: it can be retried at any time (`POST /nodes/{id}/render {force:true}` regenerates
     with `last_error_kind` in the prompt) and **re-probed** after 7 days (§3.4).
  3. **Human path**: `POST /nodes/{node_id}/waive` (admin or manager role) sets `mastered` with
     `waived_by`/`waived_at` and a row in `audit_log` (`action='node_waived'`). It's consistent with
     the product's "if you know it, you know it" principle: a human who has seen the person work can
     certify them, and who did it is recorded.
  While a `critical` node is in `needs_review`, `enrollments.status` **stays at `active`** and
  `NodeListRead.can_complete` is `false` with the node listed in `blocked_by`. The course neither
  completes silently nor blocks silently: you can see why.
- **Error classification** → `last_error_kind`, which enters the next `genera_ui` call:
  `detail` (typo/format) → correct and continue; `procedural` → point at the exact step and repeat;
  `conceptual` → a single Socratic question about the mistaken part.
- **Don't intervene by default.** If `consecutive_correct >= 1` and there's no overload signal, the
  next render doesn't add scaffolding or extra explanations. Silence is the default.
- **No time limit** on any item. Time pressure increases extraneous cognitive load.

### 7.5 Course closure

`enrollments.status = 'completed'` when **all non-archived `critical` nodes of the course are
`mastered`** (via mastery, probe, or `waive`). `recommended` and `contextual` nodes don't block it.
`enrollments.score` = average of `learner_node_states.mastery` over those `critical` nodes.
`_assign_course_skills` still grants `user_skills` with the `mastery → skill_level` translation from
§3.3, and never downgrades.

**Mandatory recalculation on schema change.** `PUT /courses/{id}/schema` changes the set of
`critical` nodes, which is precisely what governs the closure condition. In the same transaction as
the `PUT` (and the `validate`), the condition is recalculated for **all** active enrollments of the
course: an already-completed course can go back to `active` if the creator adds a new `critical`
node, and a blocked one can complete if the missing node is archived. It's recorded in `audit_log`.
Without this, enrollment state would be a function of a schema that no longer exists.

---

## 8. Click-to-explain (Curio)

### 8.1 What is ported and what is not

| Ported | Destination | Note |
|---|---|---|
| `tokenize()` + `TOKEN_RE` + `Token` | `apps/skillnet-web/src/lib/tokenize.ts` | Pure function, no dependencies. Copied with its regex `/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*|[^\p{L}\p{N}]+/gu` |
| `toClickable()` | `src/components/courses/ClickableText.tsx` | Wraps each clickable token in a `<span className="entity">` |
| `clickify()` pattern over already-rendered text nodes | `ClickableText` + `LessonContent` | **The key to the port**: raw markdown is never tokenized, only the `typeof child === 'string'` children of the already-built tree. That's why the structure doesn't break |
| `ClickableSurface` (a single listener with `onClick` + `onMouseUp`) | `src/components/courses/ClickableSurface.tsx` | With the `justDragged` ref and its `setTimeout(…, 0)` |
| `expandRangeToWords()` | `src/components/courses/ClickableSurface.tsx` | Snap to full word on selections |
| `cleanDescription()` | `src/llm/prompts/explain.py` (**Python**) | Cleanup happens on the server, before caching |
| Description prompt | `src/llm/prompts/explain.py` | No uppercase tags (small models tend to repeat them) |
| `useGenerative` is **NOT** ported | — | Triggers 4 LLM generations per click. Only the quick-glance behavior is wanted |
| `@floating-ui/react` is **NOT** ported | — | New dependency. Manual positioning in the style of the extension's `Overlay.tsx`, with `framer-motion`, which is already present |
| Hover is **NOT** ported | — | Click and selection only. Debounced hover is promised in Curio's docs but never implemented, and it would trigger cost without user intent |

### 8.2 Mandatory corrections relative to the original

These three are acknowledged bugs in the original and are **not** replicated:

1. **`STOPWORDS` in Spanish and English.** The original list is English-only, so in a
   Spanish text `de`, `la`, `que` would be clickable and `the`, `of` would not. It defines
   `STOPWORDS_ES` (~120 function words) ∪ `STOPWORDS_EN`.
2. **The cache key includes the context.** `(org_id, term_normalized, context_hash, language)`
   — see §3.4. Without `context_hash` the function would contradict its own premise.
3. **Keyboard accessibility.** Words don't carry `tabindex` (it would flood the tab order of a
   long node). **Roving tabindex over the block** is implemented instead: each text block is
   `tabindex="0"` with `role="group"`, and inside it the ←/→ arrows move a logical cursor between
   clickable words, Enter/Space opens the explanation. The active `<span>` gets
   `aria-expanded="true"` and there's a real `:focus-visible` rule. A
   `@media (prefers-reduced-motion: reduce)` rule is added to the popover's animations, which is
   also missing in the original.

### 8.3 The context that gets sent

- **Block context**: it climbs to the closest block using
  `BLOCK_SELECTOR = 'p,li,h1,h2,h3,h4,h5,h6,blockquote,td,th,dd,dt'`, normalizes whitespace
  (`.replace(/\s+/g,' ').trim()`) and trims to **600 characters centered on the term**, not the
  first 600. Fixed relative to the original: in a long block, the clicked term could fall outside
  the context sent to the model, which is exactly the worst possible failure.
- **Node context**: `node_id` (the server adds `node.title` and `node.summary`). Replaces Curio's
  `messageId`/last user turn, which doesn't apply here.

### 8.4 How it is served

`POST /api/v1/explain` with `Accept: text/event-stream`.

1. The term is normalized (`trim().toLowerCase()`) and `context_hash` is computed.
2. **Hit in `term_explanations`** → a single `token` event is emitted with the full text and
   `done`; `hit_count` and `last_used_at` are incremented. Latency ~10 ms, cost 0.
3. **Miss** → `LLMService.stream()` with purpose `runtime_fast`, `temperature=0.2`,
   `max_tokens=80`. It accumulates, passes through `clean_explanation()` on each delta and emits
   `token`. It's persisted once finished.
4. Rate limit: 30 explanations per user per minute, in process memory. Above that, `429` and the
   popover shows "Too many requests in a row."
5. **Two limits, not one**: more than **140 characters** → `422` (an accidental selection of half a
   paragraph is not a term). Between **61 and 140** characters → it's explained but **not
   persisted** (`term_explanations` only caches ≤60 characters **and** ≤4 tokens, §3.4). Storing
   phrases chosen by the user in a row with no `user_id`, no retention window, and no delete
   endpoint would contradict §3.3's own privacy promise.

Prompt (`EXPLAIN_SYSTEM`, in `src/llm/prompts/explain.py`): **exactly one short sentence**, no
markdown, no preamble, no repeating the instruction, **in the language of the text**, explaining
the term in its concrete usage — not translating it. No uppercase tags like `TERM:`.

The popover is **not** recursively clickable (its content is rendered as plain text). This avoids
generation loops and adds nothing. It **does** carry one action: **"I don't understand"**, which
opens the existing v1 chat seeded with the term, the block text, and the `node_id`. It's the exit
for someone who doesn't understand the single sentence, who otherwise had no next step: the chat
lives on another route and doesn't know the node's context.

### 8.5 Where it mounts and which clicks do NOT count

`NodeView.tsx` wraps `<UiSpecRenderer>` in `<ClickableSurface nodeId={nodeId}>`.
`ClickableText` is applied inside `TextContentBlock`, `CalloutBlock`, `StepSequenceBlock`,
`TableBlock`, `CardBlock` (titles included).

**Explicit hit-test rule.** `ClickableSurface` is a **single** listener over the whole subtree, and
that subtree is no longer chat prose: it contains buttons, radios and inputs. Curio's original
pattern never had to distinguish "click on a word" from "click on a control," and `justDragged`
only separates drag from click. Without a rule, answering a quiz option would **also** trigger the
explanation. First line of the handler:

```ts
if ((e.target as HTMLElement).closest(
      'button, a, input, textarea, select, label, [role="radio"], [role="button"], [data-no-explain]'
    )) return;
```

- **The entire `QuizItemBlock` carries `data-no-explain`**: statement **and** options. The previous
  version only excluded the statement, and the **options** are exactly the part that leaks the
  answer — clicking a word inside the correct option returns a contextual explanation of it.
- **`CodeBlockBlock`** and links remain excluded.
- **Inside an unanswered `QuizItem`**, if explain were ever enabled there, **each explain would
  count as a hint** (`hints_used += 1`, subject to the cap of 3 and to `attempt-before-hint`).
  Today it's simply disabled, which is the safe version of the same rule: a free explain was an
  uncounted hint that also fed the vector's highest weight (+0.30).
- Mandatory test in `ClickableSurface.test.tsx`: **clicking an option's button produces no request
  to `/explain`**.

---

## 9. Latency strategy

Three layers, in this order.

### 9.1 The pre-assessment IS the productive wait

The contradiction "the pre-assessment and the waiting screen occupy the same first seconds" is
resolved by merging them:

**Prerequisite, without which this doesn't work:** the probe items are **pre-generated** in
`course_nodes.probe_items` at schema validation time (§3.2, §7.1). If the probe had to be generated
with an LLM call when the node is opened, the "productive wait" would have its own wait in front of
it against a blank screen — a wait can't cover for a wait. In the residual case where they have to
be generated (a node without pre-generation), `node.summary` plus the opening line derived from
`goal` are shown while they generate.

```
t=0     POST /nodes/{id}/probe            → 2 items (pre-generated: instant)
t≈0     the user reads and answers item A
t=A     POST /nodes/{id}/probe/answer (A) ─┬─► if the verdict can no longer be "mastered",
                                           │   POST /nodes/{id}/render fires IN BACKGROUND
                                           └─► the user answers item B
t=B     POST /nodes/{id}/probe/answer (B)  → final verdict
t=B+ε   GET /nodes/{id}/render/stream      → normalmente ya hay bloques listos
```

Answering item B costs 10-20 s of human attention, which is the same order of magnitude as
`decide_formato` + `genera_ui`. The wait disappears because it overlaps with pedagogically useful
work (the pre-question effect has a notable effect size on its own). If the final verdict comes
out `mastered`, the in-flight render is cancelled (`asyncio.Task.cancel()`) and discarded — cost
accepted in exchange for zero latency in the frequent case.

### 9.2 Skeleton and streaming

- **Skeleton**: `NodeSkeleton.tsx` paints the canonical shape (title + 3 text bars + 1 block)
  with a shimmer based on `transform`/`opacity`, not `animate-pulse` (`motion-system.md:437,636`
  forbids it; a `shimmer` preset is added to `src/lib/motion.ts`). **It's implemented as a new
  component `ShimmerSkeleton.tsx`, and `src/components/ui/Skeleton.tsx` is NOT touched**: that
  file uses `animate-pulse` and is re-exported as `SkeletonText`/`SkeletonCard`/`SkeletonRow` in v1
  pages (plus its story), so changing it would be a visible v1 change **with the flag off**,
  contradicting §10.1. `design-system.md` §Skeleton, which documents `animate-pulse` as the
  canonical pattern, is the stale doc and gets fixed in the `chore` of §14.2 #8.
- **Streaming**: `GET /nodes/{node_id}/render/stream` is SSE with these events:

| Event | Payload | When |
|--------|---------|--------|
| `render_step` | `{step, message}` | On entering each graph node |
| `ui_format` | `{format, tier}` | After `decide_formato` — allows swapping the skeleton for one of the correct shape |
| `ui_block` | `{component}` | Each time `parse_partial` completes a new component |
| `ui_done` | `{render_id, format}` | On persisting |
| `node_skipped` | `{reason: "mastered"}` | If the gate skips the node |
| `error` | `{step, message, fallback: bool}` | Failure; if `fallback` is true, the client requests the render again and gets the seed |

The channel is `f"node:{request_id}"`. `src/core/sse.py` is kept with its known limitation
(in-memory, single worker, loses events prior to subscription) and **two functions are added to
it**, because "reused as-is" was incompatible with the mitigation: subscribers live in the private
dict `_registry` (lines 11-37) and **there's no accessor**, so waiting "until there's a subscriber"
couldn't be scheduled. In **B5**, and `src/core/sse.py` goes in its file list:

```python
def subscriber_count(channel: str) -> int:
    return len(_registry.get(channel, ()))

async def wait_for_subscriber(channel: str, timeout: float = 0.5) -> bool:
    """True if a subscriber appears before the timeout. Polls every 25 ms."""
```

With that: `POST /nodes/{id}/render` returns `202 {request_id}`, the client subscribes, and the
runner does `await wait_for_subscriber(f"node:{request_id}", 0.5)` before starting the real work.
Migrating to `LISTEN/NOTIFY` is backlog, and is only needed with more than one uvicorn worker
(today `docker/api.Dockerfile` starts with `--workers 1`, which is consistent).

### 9.3 Cache

Four levels:

1. **`node_renders` by `cache_key`** (§3.4). A hit is a SQL query: ~5 ms, 0 tokens. This is the
   level that makes it so the second employee with the same profile doesn't pay for generation.
   The lookup is by `cache_key` **alone**, never by `user_id`, or the hit rate would be 0.
2. **`active_render_id` by `(user, node)`** (§5.5). Inside an open node and on a revisit, not even
   the cache is queried: the already-pinned render is served. This is the cheapest level of all and
   also the one that guarantees spatial stability.
3. **`course_nodes.probe_items`** (§7.1). Pre-assessment items are generated **once per node** at
   validation time and serve the whole organization. It's the only pre-generation in this PR, and
   it's justified because it doesn't depend on the user: N employees, one generation.
4. **`term_explanations`** for click-to-explain (§8.4), and the **v1 seed** as the final safety
   net: `fallback_seed` serves `lessons.content`. This also answers offline-catalog compatibility:
   with no LLM available, the course **keeps working** in degraded v1 mode instead of breaking.

### 9.4 Anticipated render window

Generation remains on-the-fly: the representation is not folded into the course when it's
validated, nor is the full path produced. What changes is when the runtime work starts, so the
model's latency doesn't turn into visible latency:

- opening the course requests the **first two available lessons**;
- once the current lesson is served, `NodeView` requests the **next three**;
- as the learner advances, that window of three shifts along;
- `POST /nodes/{id}/render {force:false}` is idempotent and reuses a ready render or an in-flight
  task;
- each render keeps the same pins, policy keys, versions, and invalidation rules as if it had been
  requested by entering the node directly.

The anticipation follows the likely path and is bounded; it does not generate full branches or
every possible component. So "pre-generated" here means **runtime render started ahead of time
during the session**, not a pedagogical artifact persisted inside the course definition. Authority
and implications for future branching episodes are in
[`learning-experience-architecture.md`](/en/docs/learning-experience-architecture) §2.1.

---

## 10. Path selection: no global flag

> This section originally described a three-value `DYNAMIC_COURSES_MODE` flag
> (`off`/`shadow`/`on`) as a progressive rollout mechanism. That flag never made it to
> production: the mechanism that actually got implemented, and the one that exists today in
> `main`, is simpler — the choice is **per course**, with no environment variable involved.

`src/services/course_delivery.py::resolve_delivery(course)` is the single decision point:

```python
def resolve_delivery(course) -> Literal["static", "dynamic"]:
    if course.delivery_mode != CourseDeliveryMode.DYNAMIC:
        return "static"
    if course.schema_status != CourseSchemaStatus.VALIDATED:
        return "static"
    return "dynamic"
```

A course goes through v2 only if it has `delivery_mode='dynamic'` **and**
`schema_status='validated'`. Any other course — including any created before v2 existed — keeps
going through v1 on the same instance, with no gate or special environment. `GET /api/v1/health`
does not expose feature flags; it returns DB and embedding status (`src/routes/health.py`).
Querying `course.delivery_mode`/`schema_status` for this decision anywhere other than this function
is forbidden.

### 10.1 Secondary flags

| Env var | Values | Default | What it does |
|---------|---------|---------|----------|
| `RENDER_BACKEND` | `openui` | `openui` | Dialect requested from the LLM and the parser used. A single valid value in this PR; the env var exists so that adding a dialect isn't a call-site code change |
| `LLM_RUNTIME_FAST_MODEL` | litellm model id | empty → `LLM_MODEL` | Fast tier of the router |
| `LLM_RUNTIME_HEAVY_MODEL` | litellm model id | empty → `LLM_MODEL` | Heavy tier of the router |
| `LLM_FIXTURE_DIR` | path | `src/llm/fixture_data` | Where it looks up/records fixtures (§12) |
| `LLM_FIXTURE_MODE` | `replay` \| `record` | `replay` | `record` records (prompt, response) pairs with a real key |

**`RENDER_BACKEND_FALLBACK` does not exist** — it's removed along with the second dialect (§1.3,
§5.4). The single retry uses `UI_REPAIR_SYSTEM` with the same dialect.

**`LLM_FIXTURE_DIR` points inside the package, not at `tests/`.** The previous default
(`./tests/fixtures/llm`) made the `fixtures` profile of `docker-compose.yml` **impossible**: the
runtime image copies only `.venv`, `src`, `alembic`, `alembic.ini` and `pyproject.toml`
(`docker/api.Dockerfile:34-38`), so `tests/` isn't inside the container and every lookup would
fail — exactly the "the whole flow can be demoed locally with no key" promise. Fixtures live in
**`src/llm/fixture_data/`**, ship in the image with `src`, and there's no need to touch the
Dockerfile. Tests point at the same directory.

All of these are documented in [`configuration.md`](/en/docs/configuration), which also says
which of them actually reach the container: `LLM_FIXTURE_DIR` and `LLM_FIXTURE_MODE` are no
longer in `.env.example`, because there is no reason to touch them.

---

## 11. API

Prefix `/api/v1`. Auth via session cookie, like everything else. Role and flag guards are
implemented as dependencies: `require_dynamic_courses(mode_min="shadow")`.

### 11.1 Course schema (admin)

| Method | Route | Request | Response |
|---|---|---|---|
| `POST` | `/courses/{course_id}/schema/propose` | `{"source_document_id": uuid \| null, "intent_density": 1..5}` | `202 {"job_id": str}` — **idempotent while the job is in flight**: if the course already has a job in a non-terminal state (`pending`/`schema_proposing`, no `cancelled_at`), **that same `job_id`** is returned instead of launching another designer. Two clicks don't buy two runs or leave two runners writing the same set of nodes. The read is done by `CourseSchemaService.propose`; the actual race is closed by the partial unique index `uq_generation_jobs_schema_in_flight` from `0005`. `intent_density` is **not** rewritten on reuse (the in-flight job already read it) |
| `GET` | `/courses/{course_id}/schema` | — | `200 CourseSchemaRead` |
| `PUT` | `/courses/{course_id}/schema` | `CourseSchemaUpdate` | `200 CourseSchemaRead` |
| `POST` | `/courses/{course_id}/schema/validate` | — | `200 CourseSchemaRead` · `422 SchemaValidationError` |
| `POST` | `/courses/{course_id}/schema/unvalidate` | — | `200 CourseSchemaRead` |

```jsonc
// CourseSchemaRead
{
  "course_id": "…", "schema_status": "proposed", "schema_version": 3,
  "delivery_mode": "static", "intent_density": 3,
  "validated_by": null, "validated_at": null,
  "warnings": ["Removed a cyclic prerequisite between 'Exceptions' and 'Deadlines'"],
  "nodes": [{
    "id": "…", "title": "Return deadline", "summary": "…", "outcome": "…",
    "criticality": "critical", "position": 1,
    "mastery_threshold": 0.90, "estimated_minutes": 6,
    "skill_id": "…", "seed_lesson_id": null,
    "source_document_id": "…", "source_headings": ["Returns", "Deadline"],
    "prerequisite_node_ids": []
  }]
}

// CourseSchemaUpdate — full replacement (not a partial PATCH: order and graph
// must be validated as a whole). Nodes without "id" are created; nodes that are
// absent are ARCHIVED if they have progress, deleted if they don't.
{ "intent_density": 4, "nodes": [ { /* same fields, "id" optional */ } ] }

// 422 SchemaValidationError
{ "detail": { "code": "schema_invalid",
              "errors": [{"code": "cycle", "node_ids": ["…","…"]},
                         {"code": "missing_summary", "node_ids": ["…"]},
                         {"code": "no_critical_node"}] } }

// 422 when editing an already-validated schema
{ "detail": { "code": "schema_locked",
              "message": "This schema is validated. Use /schema/unvalidate before editing it." } }
```

**The gate can't be skipped by editing after validation.** Previously, `PUT …/schema` was a full
replacement that bumped `schema_version` **without** touching `schema_status` or `delivery_mode`:
on a live, validated course, a creator could add new, never-reviewed nodes and employees would
immediately get content generated for them — exactly what §1.1 promises can't happen. Three rules,
all blocking:

1. **`PUT …/schema` on `schema_status='validated'` returns `422 schema_locked`.** You have to call
   `POST …/unvalidate`, which sets `schema_status='proposed'` **and** `delivery_mode='static'` in
   the same transaction and writes to `audit_log` (`course_schema_unvalidated`). In other words:
   editing a live course pulls it out of v2 until it's validated again. Explicit and visible, not
   implicit.
2. **`reviewed_at` per node** (§3.2). `POST …/validate` only reviews the graph; a node without
   `reviewed_at` is never served (`409 node_not_reviewed`). B10's panel marks each node as
   reviewed when it's opened and edited, and `PUT` **clears `reviewed_at`** on any node whose
   `title`, `summary`, `criticality`, or `source_headings` changed.
3. **A node with `attempts_count > 0` can't be deleted**: `422 node_has_progress`, or it's archived
   (`archived = true`). Deleting it would cascade to `learner_node_states` and `node_renders`,
   destroying mastery and the audit trail of people who already worked on it, and also changing
   the set of `critical` nodes that governs enrollment closure.

`POST …/validate` validation rules, all blocking: acyclic DAG · at least one `critical` node ·
every node with a non-empty `summary` · every node with a `source_document_id` or
`seed_lesson_id` (inherited rule: no source, no course) · no orphan prerequisites ·
`position` contiguous starting from 1 · every node with `reviewed_at`. On validation:
`schema_status='validated'`, `delivery_mode='dynamic'`, `schema_validated_by/at`,
**pre-generation of probes** for all nodes (§7.1), recalculation of closure for active enrollments
(§7.5), and a row in `audit_log` with `action='course_schema_validated'` and the
proposed→validated diff in `detail`.

The `PUT` runs `SET CONSTRAINTS uq_course_nodes_position DEFERRED` at the start of its transaction
(§3.2), without which any reordering would violate the `UNIQUE (course_id, position)` constraint
mid-statement.

### 11.2 Onboarding and profile (employee)

| Method | Route | Request | Response |
|---|---|---|---|
| `GET` | `/onboarding` | — | `200 OnboardingRead` |
| `POST` | `/onboarding` | `OnboardingSubmit` | `200 LearnerProfileRead` |
| `POST` | `/onboarding/skip` | — | `200 LearnerProfileRead` |
| `GET` | `/users/me/learner-profile` | — | `200 LearnerProfileRead` · `404` if it doesn't exist |
| `PATCH` | `/users/me/learner-profile` | `{"preset"?, "role_title"?, "sector"?, "goal"?}` | `200 LearnerProfileRead` |
| `DELETE` | `/users/me/learner-profile` | — | `204` — deletes the user's **seven** personal tables in this order: `node_render_views`, `node_feedback`, `node_attempts`, `node_probes`, `learner_node_states`, `learning_events`, `learner_profiles`; and sets `node_renders.generated_by = NULL`. `node_attempts` before `node_probes` because `node_attempts.probe_id` is `ON DELETE SET NULL` (§3.3). It's the GDPR art. 17 erasure path that §3.3 promised and had no endpoint for |

```jsonc
// OnboardingRead — the server sends the questions so the copy lives in one place
{ "version": 1, "completed": false,
  "notice": "Your job title and sector are sent to the AI provider to tailor examples. You can delete them anytime from Settings.",
  "questions": [
    {"id": "role_title", "kind": "text_suggest", "prompt": "What is your job title?",
     "suggestions": ["Sales assistant", "Cashier", "Shift supervisor", "…"]},
    {"id": "goal", "kind": "single_choice", "prompt": "What do you want to use SkillNet for right now?",
     "options": [{"value":"onboarding","label":"I just joined and want to get up to speed"},
                 {"value":"specific_gap","label":"There's something specific I need to master"},
                 {"value":"assigned","label":"I've been assigned training"}], "allow_other": true},
    {"id": "experience_level", "kind": "single_choice",
     "prompt": "How much experience do you have in your current role?",
     "options": [{"value":"none","label":"None"},{"value":"some","label":"Some"},
                 {"value":"experienced","label":"A lot"}]},
    {"id": "preset", "kind": "single_choice", "prompt": "How do you prefer to study?",
     "options": [{"value":"standard","label":"Standard","hint":"10-15 min blocks"},
                 {"value":"focus","label":"Focus","hint":"Step by step, no distractions"},
                 {"value":"fast","label":"Fast pace","hint":"3-5 min micro-blocks"}]},
    {"id": "accessibility", "kind": "multi_choice", "optional": true,
     "prompt": "Do you want to turn on any reading settings?",
     "options": [{"value":"short_blocks","label":"Shorter blocks"},
                 {"value":"reduce_motion","label":"Less animation"},
                 {"value":"high_contrast","label":"More contrast"},
                 {"value":"extra_time","label":"No time limit"}]}
  ]}

// OnboardingSubmit
{ "role_title": "Sales assistant", "sector": "retail", "goal": "onboarding",
  "experience_level": "some", "preset": "focus",
  "accessibility": {"short_blocks": true, "reduce_motion": false,
                    "high_contrast": false, "extra_time": false} }

// LearnerProfileRead — format_vector and tutor_notes are NOT exposed to the client
{ "role_title": "Sales assistant", "sector": "retail", "goal": "onboarding",
  "experience_level": "some", "preset": "focus", "nodes_completed": 0,
  "onboarding_completed_at": "2026-07-25T09:12:00Z", "onboarding_skipped": false,
  "calibrating": true }
```

`POST /onboarding` writes `learner_profiles` **and** `users.learning_profile` **and**
`users.accessibility` in a single transaction.

### 11.3 Runtime (employee)

| Method | Route | Request | Response |
|---|---|---|---|
| `GET` | `/courses/{course_id}/nodes` | — | `200 NodeListRead` |
| `POST` | `/nodes/{node_id}/probe` | — | `200 ProbeRead` |
| `POST` | `/nodes/{node_id}/probe/answer` | `{"probe_id", "item_id", "answer"}` | `200 ProbeAnswerResult` |
| `POST` | `/nodes/{node_id}/render` | `{"force": false, "preview": false}` | `202 {"request_id", "cached": bool}` · `409 node_not_reviewed` |
| `GET` | `/nodes/{node_id}/render` | — | `200 NodeRenderRead` (the pinned render, see below) · `202 {"status":"generating","request_id"}` · `409 node_not_reviewed` |
| `GET` | `/nodes/{node_id}/renders` | — | `200 {"renders": [{render_id, created_at, ui_format}]}` — history for "view the previous version" (§5.5) |
| `POST` | `/nodes/{node_id}/waive` | `{"reason"?}` | `200 NodeStateRead` — admin/manager only; §7.4 |
| `GET` | `/nodes/{node_id}/render/stream?request_id=…` | — | `200 text/event-stream` |
| `POST` | `/nodes/{node_id}/answer` | `{"render_id", "item_id", "answer", "hints_used", "latency_ms"}` | `200 NodeAttemptResult` — **the body's `hints_used` is informational and the server must NOT trust it** (B5): it's the value that decides whether `NodeAttemptResult.correct_answer` is revealed, and a field the client fills in can't govern that reveal (`hints_used: 3` would be a free answer key). The valid count is derived server-side from `node_attempts.hints_used` for `(user_id, node_id, item_id)`, which only `POST /nodes/{id}/hint` increments. `QuizItemBlock` (B6) grants no hints and always sends `0` |
| `POST` | `/nodes/{node_id}/hint` | `{"render_id", "item_id"}` | `200 {"hint", "hints_used"}` · `409` if there's no prior attempt |
| `POST` | `/nodes/{node_id}/feedback` | `{"difficulty", "unclear"?}` | `204` |
| `POST` | `/nodes/{node_id}/events` | `{"events": [{"type","element","node_id"?,"ms"?}]}` | `204` |
| `POST` | `/explain` | `{"term", "context", "node_id"?, "language"?}` | `200 text/event-stream` |
| `GET` | `/render-kit` | — | `200 UIKitRead` |

```jsonc
// NodeListRead
{ "course_id": "…", "delivery_mode": "dynamic", "schema_version": 3,
  "nodes": [{ "id": "…", "title": "Return deadline", "summary": "…",
              "criticality": "critical", "position": 1,
              "state": "not_started", "mastery": 0.0,
              "locked": false, "locked_by": [],
              "needs_practice": false,          // state == 'needs_review' (§7.4)
              "estimated_minutes": 6 }],
  "can_complete": false, "blocked_by": ["…"], "progress_percent": 0 }

// ProbeRead — no correct answers
{ "probe_id": "…", "node_id": "…",
  "items": [{ "item_id": "a", "item_type": "test", "bloom_level": "apply",
              "question": "…", "options": ["…","…","…","…"] },
            { "item_id": "b", "item_type": "true_false", "bloom_level": "understand",
              "question": "…" }] }

// ProbeAnswerResult
{ "item_id": "a", "score": 1.0, "passed": true,
  "verdict": null,                       // null until all items are answered
  "estimate": 0.6, "next_item_id": "b",
  "render_hint": "prefetch" }            // "prefetch" | "skip" | null → the client
                                         // triggers POST /render in the background

// NodeRenderRead — answer_key NEVER appears here
{ "render_id": "…", "node_id": "…", "ui_format": "explanation",
  "status": "ready", "backend": "openui", "cached": true,
  "spec": { "version": "skillnet-ui/1", "root": "b0", "format": "explanation",
            "components": [ /* … */ ] } }

// NodeAttemptResult
{ "score": 0.0, "passed": false, "feedback": "…",
  "correct_answer": null,                // only when hints_used >= 3 or passed
  "mastery": 0.34, "state": "learning",
  "consecutive_correct": 0, "consecutive_failed": 1,
  "next": "retry" }                      // "retry" | "next_item" | "next_node"
```

`GET /courses/{course_id}` **does not change shape**. When the course is dynamic it adds
`"delivery_mode": "dynamic"` and returns `modules: []`; the frontend uses that to decide which view
to go to. No existing field changes type — v1's `CourseView` keeps compiling and working.

**`GET /nodes/{node_id}/render` recalculates nothing.** It returns the `ui_spec` of
`learner_node_states.active_render_id` while `render_pinned` is `true` (§5.5), and writes a row to
`node_render_views` the first time that user sees that render (§2.1). Only
`POST …/render {"force": true}` recalculates the `cache_key` and repins. Without this separation, a
simple refetch would change the screen mid-node.

`POST /nodes/{node_id}/render` with `"preview": true` can only be called by an admin, generates
with the admin's profile, doesn't write `learner_node_states`, and persists with
**`is_preview = true`**, which excludes it from the cache (§3.4). Without that flag, a preview
generated **before** validation could literally be served to an employee in the same bucket. This
is what makes `shadow` mode possible without leaking unapproved content.

---

## 12. Test strategy and fixtures

**Central constraint: there are no API keys.** Everything must be verifiable without network
access. The solution is not to mock every test, but an alternative `LLMService` implementation
selected by configuration.

### 12.1 `FixtureLLMService`

`src/llm/fixtures.py`

```python
FIXTURE_PREFIX = "fixture/"

class FixtureLLMService(LLMService):
    """Serves recorded responses. Activates when the resolved model starts with
    'fixture/'. No network calls."""

    def _key(self, system_prompt: str, user_prompt: str) -> str:
        return sha256(f"{system_prompt}\x00{user_prompt}".encode()).hexdigest()[:16]


class FixtureEmbeddingService(EmbeddingService):
    """Deterministic vectors hashed from the text, dimension = config.dimensions.
    No network calls. Not semantic: they let the pipeline run and support shape
    assertions, not relevance measurement."""
```

**It branches at ALL construction points, with a single helper.** The earlier version said
"a single branch, in the factory" and patched two sites out of five, under the wrong name. The
actual points are:

| File | Line | What it builds |
|---|---|---|
| `src/deps/llm.py` | 29 | `get_llm_service` |
| `src/deps/llm.py` | 33 | `get_tutor_llm_service` |
| `src/deps/llm.py` | 37 | `get_embedding_service` |
| `src/deps/llm.py` | 43 | `get_optional_llm_service` (purpose `eval` — **the one `grade_open_answer` uses**) |
| `src/agents/content/nodes.py` | 82 | `_make_llm` (**not** `_build_llm`, as this document used to say) |
| `src/agents/content/nodes.py` | 88 | `_make_embedder` |
| `src/services/settings_service.py` | 72 | settings connection test |
| `src/services/ingestion.py` | 53 | ingestion embedder |

```python
# src/llm/fixtures.py
def maybe_fixture_llm(config) -> LLMService:
    return FixtureLLMService(config) if config.model.startswith(FIXTURE_PREFIX) else LLMService(config)

def maybe_fixture_embedder(config) -> EmbeddingService:
    return FixtureEmbeddingService(config) if config.model.startswith(FIXTURE_PREFIX) else EmbeddingService(config)
```

The eight sites call one of the two. Without `get_optional_llm_service` patched, correcting a
`practical_case`/`dialogue` from a probe or a tiebreak would attempt a real network call (§3.4).
Without `FixtureEmbeddingService`, `load_context` in its `chunked` branch has no query embedding and,
moreover, there would be no chunk to search at all: `DocumentChunk.embedding` is `Vector(...)`
`nullable=False` (`src/models/document_chunk.py:35-37`), so without an embedder not a single row gets
created (`src/services/ingestion.py:76-81` swallows the failure and saves only `full_text`).

**Honest scope of the flow without keys:** with `FixtureEmbeddingService` the fixture tests cover
**both** branches of `load_context`. The `chunked` branch is exercised with deterministic vectors, so
it tests **the wiring** (that the query arrives, that heading filtering applies, that the context gets
trimmed), **not semantic relevance**. Retrieval quality can only be judged with
`@pytest.mark.integration` and real keys, and it is labeled as such.

Fixture layout (**inside the package**, see §10.2 — if they lived under `tests/` the Docker
`fixtures` profile would not find them):

```
src/llm/fixture_data/
├── index.json                       # {sha16: file, prompt_preview, use_case}
├── schema_design/returns_policy.json
├── decide_formato/{explanation,exercise,chart}.json
├── genera_ui/openui_explanation.txt        # raw dialect, exactly as the model would emit it
├── genera_ui/openui_exercise.txt
├── genera_ui/openui_table_nested.txt       # Table.rows as string[][]  (rule 2 of §5.4)
├── genera_ui/malformed_unclosed_array.txt  # retry path
├── genera_ui/malformed_unescaped_quote.txt # rule 1 of §5.4
├── genera_ui/malformed_literal_newline.txt # rule 3 of §5.4 — breaks parse_partial
├── genera_ui/invalid_unknown_component.txt # fallback path
├── genera_ui/repaired_after_retry.txt      # response to UI_REPAIR_SYSTEM
├── probe_generate/plazo_devolucion.json
└── explain/{mercurio_quimica,mercurio_planeta}.json   # tests context_hash
```

The three `malformed_*` fixtures correspond **one to one** to the three rules of the frozen grammar
in §5.4: they are the failures an 8B model makes on day one, not invented malformations.

Recording mode, for whenever someone has a key: `LLM_FIXTURE_MODE=record` makes the real
`LLMService` write each (prompt, response) pair to `LLM_FIXTURE_DIR` and update `index.json`. That
way fixtures are real, not hand-invented. If a fixture is missing in replay mode, the test fails
with the sha and a preview of the prompt, not an opaque `KeyError`.

`docker-compose.yml` has a `fixtures` profile with `LLM_MODEL=fixture/local` and
`EMBEDDING_MODEL=fixture/local`, so the whole flow can be demoed locally with no keys at all (the
v2 path is enabled per course, not by env var — see §10). It works in the production compose file
because fixtures travel inside `src/` (§10.2); `docker/compose/dev.yml`, which bind-mounts
`./apps/skillnet-api:/app`, works the same way.

### 12.2 What is tested and how

| Level | File | What it checks | Needs |
|---|---|---|---|
| Unit | `tests/test_render_openui.py` | `parse()` of 8 valid dialects → golden JSON; 6 malformed → `RenderParseError`, including the 3 grammar rules (§5.4); `parse_partial` over truncations at **every** position via a `@pytest.mark.parametrize` over `range(len(raw))` — **not** with `hypothesis`, which would be a new dev dependency, and the dependency limit in `AGENTS.md` requires justifying it for anything a loop already covers | nothing |
| Unit | `tests/test_render_roundtrip.py` | `parse(serialize(spec)) == spec` for the `openui` backend over 11 golden specs (the 10 here plus `inline_nested`, which pins the synthetic ids of inline nesting), **including** specs with `QuizItem`, nested `Stack`, and `Table` with nested `rows` | nothing |
| Unit | `tests/test_render_kit.py` | The frozen catalog (10 names, positional prop-by-prop order, the 6 `item_type` values of the existing enum) and the 7 rules: `UISpec` rejects >12 components, cycles, dangling refs, `QuizItem` with `correct`, and `explanation`/`mixed` without an initial `lead` block | nothing |
| Unit | `tests/test_render_prompt_artifact.py` | **The drift alarm** between `src/render/kit.py` and the artifact `library.prompt()` generates: normalized catalog digest, `prompt_sha256`, that the prompt announces the 9 signatures and no more, that it **does not** teach reactive syntax, and that the `@openuidev` versions are the audited ones | nothing |
| Unit | `tests/test_render_gate.py` | 15 reactive payloads (loose `Mutation`, self-triggering `Query`, `refreshInterval`, `@OpenUrl` with `javascript:`, `@ToAssistant`, `$state`, ternary, builtins…) rejected, and 6 legitimate contents accepted — including prose that mentions `Query()` and `$300`, which is the measured false positive of a keyword grep; size caps; `canonicalize()` returns the re-serialization, not the input | nothing |
| Unit | `tests/test_mastery.py` | Truth table of `probe_verdict` (25 cases), including "B perfect and A at zero" → **no** mastery; `critical` with 2/2 selected gives `tiebreak`, not `mastered`; `tiebreak_mastery` **reaches each of the 3 thresholds** (the §7.2 table case by case); the mastery ceiling (a sustained 0.85 **does** reach `mastered` on a `critical` node); EWMA; the **8** `node_state` transitions of §7.3 | nothing |
| Unit | `tests/test_probe_reuse.py` | The second `POST /probe` for the same `(user, node, schema_version)` returns the stored verdict and **does not** generate items; re-probe rejected if `state != 'needs_review'` or fewer than 7 days have passed; diagnostic probe (`scored=false`) does not consume the attempt | nothing |
| Unit | `tests/test_node_grading.py` | `content_for()` for the 4 deterministic types: recombines `answer_key` + props and `grade()` scores the same as v1 given the same input | nothing |
| Unit | `tests/test_schema_validation.py` | Cycle detection (self-edge, 2-cycle, 5-cycle, large valid DAG), orphans, `no_critical_node`, cycle pruning in `persist_schema` | nothing |
| Unit | `tests/test_runtime_router.py` | `select_tier` for the 5 formats; `purpose_for`; `resolve_llm_config` precedence with `runtime_fast`/`runtime_heavy` and fallback to `LLM_MODEL` | nothing |
| Unit | `tests/test_profile_service.py` | Vector with decay (event fixture with fixed `created_at`), L1 normalization, `vector_bucket`, calibration with `nodes_completed < 3`, pruning `tutor_notes` to 20 | nothing |
| Unit | `tests/test_cache_key.py` | The key changes with `schema_version`, `preset`, `role_bucket`, `scaffold_band`, `effective_density`, `PROMPT_VERSION`; it does **not** change with `user_id` or with `mastery` within the same `scaffold_band`; two profiles with different `role_title` do **not** share a key | nothing |
| Unit | `tests/test_schema_gate.py` | `PUT` on `validated` → `422 schema_locked`; `unvalidate` sets `proposed` + `static`; deleting a node with `attempts_count > 0` → `422`; editing `summary` clears `reviewed_at`; a node without `reviewed_at` → `409` when requesting a render | nothing |
| Unit | `tests/test_delivery_resolution.py` | The 12 cases of `resolve_delivery` | nothing |
| Graph | `tests/test_runtime_graph.py` | `build_node_graph()` compiles; full run with `FixtureLLMService` and fake repos: happy path, `mastered`→skip, malformed→retry, invalid→`fallback_seed` | fixtures |
| Graph | `tests/test_schema_graph.py` | Full `propose` run with fixtures → N nodes with expected criticality and prereqs | fixtures |
| Integration | `tests/integration/test_dynamic_flow.py` (`@pytest.mark.integration`) | e2e over real Postgres: propose → validate → onboarding → probe → render → answer → mastery → completed | docker db + fixtures |
| Integration | `tests/integration/test_v1_regression.py` (`@pytest.mark.integration`) | The full v1 flow stays identical for a `static` course, and a course with the new columns set to `dynamic` but without a validated schema still gets served by v1 (`resolve_delivery`) | docker db |
| Migration | `tests/integration/test_migration_0005.py` | `upgrade` from `0004` and `downgrade` back, with v1 data present. Exact asserts: the 13 tables and the 6 `courses` columns disappear; the 8 new enums disappear; **`generation_step` retains `schema_proposing` and `schema_proposed`** (orphans by design, §3); no v1 row altered; reordering positions 1↔2 in a `PUT` does not violate the deferred `UNIQUE` constraint | docker db |

**On `aiosqlite`:** DB tests cannot run on SQLite (`jsonb`, `text[]`, native enums,
`pgvector`). Decision: service tests use fake in-memory repositories (protocols, since services
receive repos by injection) and anything that touches real SQL is marked `@pytest.mark.integration`
and runs against the `docker-compose` Postgres. `pytest -m "not integration"` stays green with no
Docker and no network — that is what runs in CI by default.

### 12.3 Frontend

| File | What |
|---|---|
| `src/lib/tokenize.test.ts` | Spanish tokenization with accents, apostrophes, hyphens, punctuation, emoji; ES and EN stopwords; verbatim re-render (`tokens.join('') === input`) |
| `src/components/courses/UiSpecRenderer.test.tsx` | Renders the 10 golden specs (shared with the backend via `src/test/fixtures/ui-specs/*.json`); unknown type → `null` with no crash; dangling refs → no crash |
| `src/components/courses/ClickableSurface.test.tsx` | Click on a word → correct term; partial selection → whole word; `justDragged`; click on `CodeBlock` → nothing; **click on a `QuizItemBlock` option button → no request to `/explain`**; click on the quiz statement → nothing |
| `src/api/nodes.test.ts` | SSE parsing with `fetch` stubbed (same pattern as `client.test.ts`), including incremental `ui_block` and `error` with `fallback` |
| Stories | `UiSpecRenderer`, each block, `NodeSkeleton`, explanation popover, onboarding wizard — with the addon's `a11y` set to `error` (not `todo`) for the new ones |

The golden specs are **the same JSON file** on backend and frontend (copied by a script in
`pretest`, not hand-duplicated). If the contract breaks, both sides break at once.

---

## 13. Batch work plan

Rule: each batch is a commit (or a few), compiles, passes `pytest -m "not integration"` and `pnpm
lint`, and **leaves the flag at `off`** until batch B12. No intermediate batch may break v1.

**The six and only v1 surfaces touched, declared** (everything else is a new file). None changes
behavior with the flag off, and all six are covered by existing or new v1 tests:

| v1 file | Batch | Change | Why it's safe |
|---|---|---|---|
| `src/agents/content/{nodes,helpers}.py` | B2 | Move 3 pure functions to `helpers.py` and import them | No behavior change; already covered by `tests/test_generation_pipeline.py` |
| `src/routes/generation_jobs.py` | B2 | `_TERMINAL_EVENTS` += `schema_ready` (1 line) | An event type v1 never emits |
| `src/core/sse.py` | B5 | +`subscriber_count`, +`wait_for_subscriber` | Additive only; `publish`/`subscribe` untouched |
| `src/repositories/document_chunk_repo.py` | B1 | +`similarity_search_by_headings` | New method; the existing one untouched |
| `apps/skillnet-web/src/pages/employee/CourseView.tsx` | B9 | `if (delivery_mode === 'dynamic')` | With the flag off, the API never returns `dynamic` |
| `apps/skillnet-web/src/pages/admin/CreateCourse.tsx` | B10 | Extract `StepIndicator` + optional step | Pure refactor + branch behind the flag |

`src/components/ui/Skeleton.tsx` **is no longer on the list**: B6 creates a separate
`ShimmerSkeleton.tsx` (§9.2).

```
B0 ──┬── B1 ──┬── B5 ──┬── B9 ── B12
     ├── B2 ──┴─ B10 ──┤
     ├── B3 ──── B8 ───┤
     ├── B4 ───────────┤
     ├── B6 ───────────┤
     └── B7 ───────────┘
```

### B0 — Base: migration, models, config *(blocking for everything)*

- `alembic/versions/0005_dynamic_courses.py` (new, `down_revision="0004"`, `downgrade` with the
  exact scope of §3: no `op.execute("COMMIT")`, leaving the 2 orphan enum values)
- `src/models/{course_node.py, course_node_prerequisite.py, learner_profile.py, learner_node_state.py, learning_event.py, node_render.py, node_render_view.py, node_probe.py, node_attempt.py, node_feedback.py, term_explanation.py, llm_usage_log.py, audit_log.py}` (new — 13)
- `src/models/course.py` (+6 columns, 2 enums), `src/models/generation_job.py` (+2 members), `src/models/__init__.py`
- `src/config.py` (`RENDER_BACKEND`, `LLM_RUNTIME_FAST_MODEL`, `LLM_RUNTIME_HEAVY_MODEL`, `LLM_FIXTURE_DIR`, `LLM_FIXTURE_MODE`)
- `src/llm/fixtures.py` (new: `FixtureLLMService`, `FixtureEmbeddingService`, `maybe_fixture_llm`, `maybe_fixture_embedder`), `src/llm/fixture_data/` (fixture directory, inside the package)
- **The 8 construction points from §12.1** go through the helpers: `src/deps/llm.py` (4), `src/agents/content/nodes.py` (2), `src/services/settings_service.py` (1), `src/services/ingestion.py` (1)
- `src/services/course_delivery.py` (new, `resolve_delivery`)
- `src/deps/features.py` (new, `require_dynamic_courses`)
- `src/routes/health.py` (+`features`), `src/scripts/purge_learning_data.py` (new)
- `tests/test_delivery_resolution.py`, `tests/integration/test_migration_0005.py`
- `.env.example`, `docker-compose.yml` (`fixtures` profile with fixture `LLM_MODEL` and `EMBEDDING_MODEL`)

### B1 — Render adapter and UI Kit (Python) *(parallel with B2, B3, B4, B6, B7)*

- `src/render/{__init__.py, spec.py, kit.py, errors.py}` (new)
- `src/render/backends/{__init__.py, base.py, openui.py}` (new — **without `a2tl.py`**, §1.3)
- `src/repositories/document_chunk_repo.py` (+`similarity_search_by_headings`, new method; the existing one untouched)
- `tests/test_render_openui.py`, `test_render_roundtrip.py`, `test_render_kit.py`
- `tests/fixtures/dsl/*.openui`, `tests/fixtures/ui-specs/*.json`
- **Does NOT** touch the `org_id` scoping of `src/deps/llm.py` or `settings_service.py`: it goes out
  as its own `chore` PR with route tests for chat and exercises (§4.3, §14.2 #11)

### B2 — Design-time: schema graph + endpoints *(parallel with B1, B3, B4, B6, B7)*

- `src/agents/schema/{__init__.py, state.py, nodes.py, graph.py, runner.py, errors.py}` (new — **new** nodes, not imported from v1, §4)
- `src/agents/content/helpers.py` (new: `estimate_pages`, `assemble_chunk_text`, `themes_list` **moved** from `nodes.py`) + `src/agents/content/nodes.py` (imports from there; no behavior change)
- `src/llm/prompts/schema.py` (new: `SCHEMA_DESIGNER_SYSTEM`, `build_schema_prompt` with `available_headings` as a closed list)
- `src/repositories/course_node_repo.py` (new)
- `src/services/course_schema_service.py` (new: propose, update, validate, unvalidate, cycles, versioning, `schema_locked` gate, `reviewed_at`, archiving, probe pre-generation, enrollment recalculation)
- `src/repositories/audit_log_repo.py` (new)
- `src/schemas/course_schema.py` (new)
- `src/routes/course_schema.py` (new), `src/main.py` (registration), `src/routes/generation_jobs.py` (`_TERMINAL_EVENTS` += `schema_ready`, 1 line — the channel is still `generation:{job_id}`)
- `tests/test_schema_validation.py`, `tests/test_schema_gate.py`, `tests/test_schema_graph.py`, `src/llm/fixture_data/schema_design/*.json`

### B3 — Learner profile and onboarding (API) *(parallel with B1, B2, B4, B6, B7)*

- `src/repositories/{learner_profile_repo.py, learning_event_repo.py}` (new)
- `src/services/learner_profile_service.py` (new: `EVENT_WEIGHTS` for 7 types, 4-dimension vector with decay, `vector_bucket`, calibration, `apply_signals()` with the **5 trigger rules** of §3.3)
- `src/schemas/{onboarding.py, learner_profile.py}` (new; `OnboardingRead.notice` included)
- `src/routes/{onboarding.py, learner_profile.py}` (new, including `DELETE /users/me/learner-profile`), `src/main.py`
- `tests/test_profile_service.py` (one test per `tutor_notes` rule), `tests/test_cache_key.py`

### B4 — Pre-assessment and mastery *(parallel with B1, B2, B3, B6, B7)*

- `src/services/mastery_service.py` (new: `probe_verdict`, `tiebreak_mastery`/`tiebreak_verdict`, EWMA with ceiling, the 8 transitions, `THRESHOLDS`, prior from `user_skills`)
- `src/services/probe_service.py` (new: reading `course_nodes.probe_items`, sampling from the seed, LLM generation as last resort, grading, single attempt per version, diagnostic probe)
- `src/services/node_grading.py` (new: `content_for()` — `answer_key` + props → v1 dict adapter; **imports** `grade()` from `exercise_service`, does not move it)
- `src/repositories/{node_probe_repo.py, node_attempt_repo.py, learner_node_state_repo.py}` (new)
- `src/llm/prompts/probe.py` (new)
- `tests/test_mastery.py`, `tests/test_probe_reuse.py`, `tests/test_node_grading.py`, `src/llm/fixture_data/probe_generate/*.json`

### B5 — Runtime: per-node graph + endpoints *(depends on B1 and B4)*

- `src/agents/runtime/{__init__.py, state.py, nodes.py, graph.py, router.py, runner.py, errors.py}` (new; `errors.py` contains `runtime_node_error_wrapper`, independent from v1's — §4.2)
- `src/llm/prompts/runtime.py` (new: `FORMAT_DECIDER_SYSTEM`, `UI_GENERATOR_SYSTEM`, `UI_REPAIR_SYSTEM`, `PROMPT_VERSION`, `build_*`)
- `src/services/node_render_service.py` (new: `cache_key` with `role_bucket`/`scaffold_band`, hit/miss by `cache_key` **without `user_id`**, pinning `active_render_id`, writing `node_render_views`, cancellation, fallback)
- `src/repositories/{node_render_repo.py, node_render_view_repo.py, llm_usage_repo.py}` (new)
- `src/core/sse.py` (+`subscriber_count`, +`wait_for_subscriber` — §9.2; additive only)
- `src/schemas/node.py` (new), `src/routes/nodes.py` (new, including `/waive` and `/renders`), `src/main.py`
- `src/services/exercise_service.py`: **untouched.** `grade()` is already a pure module-level function (line 73) and is imported as-is; the adapter lives in `node_grading.py` (B4)
- `tests/test_runtime_router.py`, `tests/test_runtime_graph.py`, `src/llm/fixture_data/{decide_formato,genera_ui}/*`

### B6 — Frontend: spec renderer and blocks *(parallel; only needs B1's contract JSON)*

- `src/types/ui-spec.ts` (new), `src/types/index.ts` (`LearningNode`, `NodeRender`, `LearnerProfile`, `ProbeItem`, without touching v1 types)
- `src/components/courses/UiSpecRenderer.tsx` (new)
- `src/components/courses/blocks/{StackBlock,TextContentBlock,CardBlock,CalloutBlock,StepSequenceBlock,TableBlock,CodeBlockBlock,ChartBlock,QuizItemBlock,MarkdownBlock}.tsx` (new). `QuizItemBlock` is **self-contained** (§5.3): its own state and its own submission to `POST /nodes/{id}/answer`, and `src/components/exercises/` is **not** touched
- `src/lib/motion.ts` (+`shimmer` preset), `src/components/ui/ShimmerSkeleton.tsx` (**new**; v1's `Skeleton.tsx` untouched — §9.2)
- Stories + `UiSpecRenderer.test.tsx`, `src/test/fixtures/ui-specs/` (copy from B1)

### B7 — Curio: click-to-explain *(parallel; needs `term_explanations` from B0)*

- Backend: `src/llm/prompts/explain.py`, `src/services/explain_service.py`, `src/schemas/explain.py`, `src/routes/explain.py`, `src/repositories/term_explanation_repo.py` (new) + `src/main.py`
- Frontend: `src/lib/tokenize.ts`, `src/components/courses/{ClickableText,ClickableSurface,ExplainPopover}.tsx`, `src/api/explain.ts` (new). `ClickableSurface` implements the hit-test from §8.5 (`closest(...)`) as the first line of the handler; `ExplainPopover` carries the "I don't understand" action → seeded v1 chat
- `src/index.css` (`.entity`, `.entity-open`, `.phrase-rect`, `:focus-visible`, `prefers-reduced-motion`)
- `tests`: `tokenize.test.ts`, `ClickableSurface.test.tsx` (including the "click on option → no explain" case), `src/llm/fixture_data/explain/*.json`

### B8 — Frontend: onboarding wizard *(depends on B3)*

- `src/components/ui/StepIndicator.tsx` (**extracted** from `CreateCourse.tsx`; `CreateCourse.tsx` now imports it — refactor with no functional change)
- `src/pages/onboarding/Onboarding.tsx`, `src/components/onboarding/{RoleStep,GoalStep,ExperienceStep,PresetStep,AccessibilityStep}.tsx` (new)
- `src/api/onboarding.ts` (new), `src/api/users.ts` (`useUpdateProfile` accepts `accessibility`)
- `src/types/index.ts`: **fix** `learning_profile?: Record<string, unknown> | null` → `learning_profile?: 'standard' | 'focus' | 'fast'`. The backend column is the `learning_profile` enum (`src/models/user.py`), so the wizard has to send a plain string and the current type blocks that
- `src/App.tsx` (`/onboarding` route, outside `AppLayout`), `src/components/layout/ProtectedRoute.tsx` (gate with the 4 rules from §6.1: flag from `/health`, query conditioned on `role === 'employee'`, 404 ⇒ do not redirect, skeleton while loading)

### B9 — Frontend: node view *(depends on B5 and B6)*

- `src/pages/employee/NodeView.tsx`, `src/components/courses/{NodeList,NodeSkeleton,ProbeRunner,NodeFeedback,RenderControls}.tsx` (new). `RenderControls` is the node footer with "Update this lesson" and "View previous version" (§5.5) — it is not optional
- `src/api/nodes.ts` (new: `useCourseNodes`, `useProbe`, `useSubmitProbeAnswer`, `useNodeRender`, `useNodeRenderStream`, `useSubmitNodeAnswer`, `useNodeEvents`, `useNodeRenderHistory`). `useNodeRender` runs with `refetchOnWindowFocus: false` — belt-and-suspenders, since the backend already serves the pinned render
- `src/pages/employee/CourseView.tsx` (**only** modification: if `delivery_mode === 'dynamic'` renders `NodeList`; otherwise the v1 tree stays intact)
- `src/App.tsx` (`/empleado/curso/:id/nodo/:nodeId`)

### B10 — Admin frontend: schema *(depends on B2)*

- `src/pages/admin/CourseSchema.tsx`, `src/components/schema/{NodeEditor,PrerequisitePicker,CriticalityBadge,IntentDensitySlider,SchemaValidationPanel,ReviewChecklist}.tsx` (new). `NodeEditor` exposes `default_ui_format`; `ReviewChecklist` marks `reviewed_at` per node and blocks the validate button until all are reviewed
- `src/api/schema.ts` (new, including `unvalidate` and the `schema_locked` warning), `src/pages/admin/CreateCourse.tsx` (step 1 → "define schema" when the flag allows it; the v1 path stays available), `src/App.tsx` (`/admin/curso/:id/esquema`)

### B11 — Integration and regression *(depends on B5, B8, B9, B10)*

- `tests/integration/test_dynamic_flow.py`, `tests/integration/test_v1_regression.py`
- `src/services/enrollment_service.py` (completion via unarchived `critical` nodes, **only** on the dynamic branch; recalculation when the schema changes, §7.5)
- `src/services/skill_service.py` (`mastery → skill_level` translation, **and reading** `user_skills` for the probe prior, §7.1)

### B12 — Docs, flag, and PR

- `docs/design/v2-dynamic-courses.md` (this file, updated with lessons learned)
- `AGENTS.md` (§"Current phase" → v2 with the flag; **and fix the package list**: it mentions
  `packages/mcp-ui-renderer`, which does not exist — `packages/` contains `a2tl-video`, `a2tl-web`,
  `mcp-md-reader`), `CLAUDE.md` (`fixtures` profile commands)
- **`chore` for obsolete docs** (§14.2 #8), in this same batch: `screens.md` (routes in Spanish;
  §Employee Settings line 213, remove "TEA, TDAH, dislexia flags" and describe `users.accessibility`
  as neutral settings), `design-system.md` (§Skeleton: `animate-pulse` → `ShimmerSkeleton`)
- `docs/design/data-model.md` (v2 appendix pointing here; the v1 body is not rewritten)
- `README.md` (flag section), final `.env.example`
- Flag set to `shadow` in the development `docker-compose.yml`, `off` in production
- PR to `main` with `resolve_delivery`'s truth table and the v1 regression test evidence

**Critical path:** B0 → B1 → B5 → B9 → B11 → B12. Everything else hangs in parallel. With two
people, the split is: one does B0/B1/B5 (adapter + runtime), the other B2/B3/B4 (schema + profile +
mastery), and then B6-B10 can overlap.

---

## 14. Risks and open decisions

### 14.1 Risks with a decided mitigation

| Risk | Probability | Mitigation in this design |
|---|---|---|
| A small model (8B) frequently generates a malformed dialect | High | Frozen EBNF grammar + 3 escape rules in the prompt (§5.4) · tolerant `parse_partial` · 1 retry with `UI_REPAIR_SYSTEM` (the exact error in the prompt) · `fallback_seed` to v1 markdown. **The user never sees a red screen** — and that is guaranteed by `fallback_seed`, not a second dialect |
| The generated content is pedagogically worse than the static one and no one reviews it | High | `shadow` mode (previews with `is_preview`, kept out of the cache) · **`reviewed_at` mandatory per node**: a node no one has opened does not get served · proposed→validated diff in `audit_log`, to *measure* whether creators edit · `node_feedback` with a trigger: 3+ users mark `hard` on the same node → notice to the creator. **The creator decides, the system never rewrites on its own** |
| LLM cost spikes | Medium | Cache shared per bucket (not per user) · probes pre-generated per node, not per user · pre-assessment avoids generating what's already known · `llm_usage_log` with `use_case`, **table created in `0005`** (§3.5) · explicit `max_tokens` budgets |
| The cross-user cache hit rate is much worse than measured | **High** | The cross-user regime **is not measured** (§3.4) and `role_bucket` deliberately makes it worse. It's the first thing measured (§14.2 #3), and the rollback lever is one line: drop `role_bucket` or `vector_bucket` from the key and bump `PROMPT_VERSION` |
| The in-memory SSE loses events or breaks with >1 worker | Medium | `202 {request_id}` + subscription before the work + 500 ms wait · fallback to polling `GET /nodes/{id}/render` (a pattern the frontend already uses for generation) · documented: **a single uvicorn worker until migrating to LISTEN/NOTIFY** |
| The correct answer leaks to the client | Medium | `answer_key` in a separate column that no response Pydantic schema includes · `ProbeSession.probe` typed as `ProbeRow` (a protocol **without** `answer_key`) and projected by `ProbeSessionRead.from_session` (`extra="forbid"`, fields enumerated by hand) — the service no longer returns the whole ORM row to its caller · a test that dumps the response model and asserts that neither the key nor its values appear (`tests/test_probe_answer_key_privacy.py`) · `NodeRenderRead` already exists (`src/schemas/node.py:115`, arrived with B5) with `extra="forbid"` and the field list enumerated by hand in `NodeRenderRead.of`, which is the whole contract; **still pending** is the equivalent test that dumps *that* model and asserts the absence of the key, like the one for `ProbeSessionRead` · the client's `hints_used` is informational and cannot govern the reveal (§11.3) |
| Prompt injection from client-supplied text | Medium | `POST /explain` interpolates two client values (`term`, `context`, and the context is not checked against the node's real text). **Neither goes between quotes**: they're sanitized (control characters, `<`/`>`, quote runs, length caps of 140/600) and fenced in `<<<name:token>>>` markers whose token no sanitized payload can contain — closing the fence would require characters already stripped. The `system` prompt declares that whatever sits between markers is data, never instruction. Token derived from content (not random) so fixtures stay reproducible. Hijack tests in `tests/test_explain_service.py` |
| The mastery rule lets someone who doesn't know through | Medium | `score_a >= 0.5` clause · a constructed-response tiebreak **mandatory on every `critical` node** · **a single scored probe per schema version** (unique index), which is what prevents re-entering until getting it right by chance · a streak of 3 in addition to the threshold |
| The mastery rule locks out someone who does know | Medium | Mastery ceiling: 3 consecutive hits raise `mastery` to the threshold (§7.3), because the EWMA converges to the mean and left a sustained 0.85 at 0.05 short of 0.90 forever · human override `POST /nodes/{id}/waive` logged to `audit_log` · a node in `needs_review` stays visible and retriable, never disappeared |
| Content shifts under the user's feet | Medium | `active_render_id` pins the render while the node is open · `scaffold_band` (stable) replaces `mastery_band` (changed with every answer) in the key · regeneration only via an explicit button, with "view previous version" |
| Silent regression in v1 | Medium | `test_v1_regression.py` with the flag at `off` · `resolve_delivery` as the single decision point · default `off` |
| Contract drift between backend and frontend | Medium | Shared golden specs, copied by a script in `pretest`. Both sides break at once |
| XSS via generated content | Low (by design) | Never HTML: typed IR + native render. `SandboxHTML` out of scope. `props.text` is inline text/markdown, rendered by `react-markdown` without `rehype-raw` |
| GDPR with sensitive data | Medium | No neurotype labels · `learning_events` carries no user text, purged at 90 days by `src/scripts/purge_learning_data.py` (there is no `background_jobs` table, §1.3) · `term_explanations` only caches ≤60 characters and purges at 180 days · `goal` no longer travels to the LLM · notice at the collection point (`OnboardingRead.notice`) · `DELETE /users/me/learner-profile` for Art. 17, which deletes the **seven** personal tables (including `node_attempts` and `node_probes`, the ones holding what the employee wrote) and proves it table by table in `tests/test_gdpr_erasure.py` · `accessibility` never goes to the LLM · admin aggregates with k≥5 · `audit_log` (table created in `0005`) on schema validation |
| Audit evidence gets destroyed when an employee is offboarded | Medium | `node_renders` has no `user_id`, and `generated_by` uses `ON DELETE SET NULL`; the read trail lives in `node_render_views`, per user · a node with progress gets archived, not deleted |

### 14.2 Open decisions (with a decision date, not "TBD")

1. **Real fast/heavy ratio.** The 90/10 estimate is a hypothesis. It's decided with
   `llm_usage_log` data after 2 weeks in `shadow` mode. If heavy exceeds 25%, the `decide_formato`
   prompt needs review — it's probably choosing `chart` when `explanation` would do.
2. **Real `genera_ui` latency. ~~Open~~ CLOSED (2026-07-27, measured).** Internal sources gave
   incompatible figures (1-2 s vs 22.9 s vs 60-120 s), all for full HTML generation and not for the
   IR. Measured with `scripts/quality_bench.py` against real Groq
   (`groq/llama-3.1-8b-instant` as the fast tier, `groq/openai/gpt-oss-120b` as heavy):
   **under one second to ~3 s per render, at ~0.0008 USD per render**, with token accounting
   already populated. **The "20-30 seconds" problem the research assumed does not exist in this
   stack**: the 60-150 s figures were from a 7B model on local CPU.

   Consequences, and these are the ones that matter: the productive wait is more than enough,
   **no pre-generation is needed**, and no extra layer of waiting gets added. The latency budget
   stops being a design constraint, so the dials get spent on *correctness*, not speed
   (`docs/design/tuning.md`). The only real operational constraint is that **Groq's free tier
   returns 429 easily**: any measurement run needs exponential backoff, and the bench already has
   it built in and accounts for the wait separately so a 429 can never score as a quality failure.
3. **Cross-user cache hit rate **and staleness** rate.** Both get measured, because the ~80%/0%
   figure quoted was measured with a **per-user** key, and this key is shared: it's a regime with
   no data (§3.4). Query: hits per `cache_key` over `node_renders` + `node_render_views`, and
   "stale" = a served render whose `role_bucket`/`scaffold_band` no longer matches the reader's
   profile. If hits fall below 50%, `vector_bucket` gets dropped; if there is also perceptible
   staleness, `role_bucket` gets dropped too and less personalized content is accepted. A one-line
   change plus a `PROMPT_VERSION` bump.
4. **FSRS vs HLR.** HLR is kept (it's already in the data model). The decision to migrate to
   FSRS-6 is made in the spaced-repetition PR, not here, and requires first pinning down: number
   of weights (sources say 17, 19, and 21), `difficulty` range, and the `py-fsrs` version with its
   API (`Scheduler.review_card` vs `FSRS.repeat`).
5. **Retention alert thresholds.** There are three incompatible sets in the research
   (0.85/0.70/0.50 vs 0.50/0.70 vs 85/70/50 + critical). A single canonical table gets defined in
   the spaced-repetition PR.
6. **Interleaving between nodes.** Mixing nodes from different courses in a session improves
   transfer but overloads beginners. Decided once real `mastery` data exists: the candidate rule is
   to enable it only for nodes with `mastery >= 0.5` (phase `ha` or above).
7. **Stateful `Simulation`?** Requires the IR to grow with data-binding, a structural change to the
   contract. Decided only if `node_feedback` shows that `explanation` + `exercise` isn't enough for
   procedural nodes.
8. **Spanish vs English routes.** The code uses Spanish, the docs English. The code is followed and
   `screens.md` is corrected in a separate `chore`. If the opposite is decided, it's a mechanical
   rename of `App.tsx` and the `Link`s, with no effect on the API.
9. **Per-employee weight personalization threshold.** Not applicable until FSRS exists. Once it
   applies, choose between >50 and >200 reviews (sources give both) and document it.
10. **Multi-worker.** The design assumes a single uvicorn worker because of the in-memory SSE
    (consistent with `docker/api.Dockerfile`, which starts with `--workers 1`). If deployment needs
    more, the decision is Postgres `LISTEN/NOTIFY` (no Redis, consistent with "no Redis, no
    Celery"), and only `src/core/sse.py` needs touching.
11. **`org_id` scoping of org settings.** `select(Organization).limit(1)` in
    `src/deps/llm.py:22-25` and `SettingsService._get_org`. It leaves this PR for its own `chore`
    (§4.3) because fixing it properly requires threading `CurrentUser` through four dependencies
    that untested v1 routes consume. **Decided before admitting a second organization on an
    instance**; today the single-org invariant makes it harmless. The `chore` includes route tests
    for `chat.py` and `exercises.py`.
12. **Second render dialect.** Out of scope for this PR (§1.3). Decided **if** the retry with
    `UI_REPAIR_SYSTEM` leaves a parse failure rate >5% measured over `node_renders.status`. If
    needed, it will be a SkillNet-owned dialect capable of expressing the full `UISpec`, not
    `UIDL/1`.
13. **Course navigation: flat list vs semantic-zoom canvas.** `NodeListRead` is an ordered list,
    which is a **deliberate downgrade** from the canvas exploration with a persistent status rail
    that the Keyhole research recommends. Reason: the canvas is its own frontend project and this
    PR already ships a new renderer. Re-evaluated once real courses with >10 nodes exist; noted
    here rather than omitted.
14. **Promoting the redundancy rule (§5.2) from warning to error.** Decided from the warnings
    accumulated in `node_renders.error_message` after 2 weeks in `shadow`: if it appears in <5% of
    renders, it's promoted to a validation error; if it appears often due to table-summary-after-text
    (good redundancy), the heuristic gets retired.

### 14.3 What the first real run of the integration suites found (2026-07-27)

The `tests/integration/` suites were written in B11 but **had never been run against a live
PostgreSQL**. The first time they ran, they found seven things. They're noted here because five of
them contradict something this document or the code claimed, and because two are **v1** bugs that
had been there since before v2.

**Migrations (none of this was theoretical: `alembic upgrade head` from scratch had never worked).**

1. `0003` used `sa.Enum(..., create_type=False)`. `sa.Enum` **loses that flag** when adapting to
   the postgres dialect, so `CREATE TYPE skill_level` was emitted twice and the run died. Fixed to
   `postgresql.ENUM`. This was the underlying reason no one had ever been able to bring up the
   database from scratch.
2. `0005` and `src/models/learner_profile.py` built a JSONB default with `sa.text()` carrying an
   unescaped `:`. SQLAlchemy read them as bind parameters and the DDL came out as
   `{"text"NULL,...}`. Fixed by escaping `\:`.
3. `0005` used a new `generation_step` value **in the same transaction that added it** (the
   `uq_generation_jobs_schema_in_flight` partial index) → `UnsafeNewEnumValueUsageError`. The two
   `ALTER TYPE … ADD VALUE` statements now sit inside `op.get_context().autocommit_block()`. The
   opposite claim in `0005`'s docstring and in the §3 note **was false** and is corrected in both
   places.
4. New migration **`0006`**: `user_skills.last_assessed_at` was `timestamp without time zone` while
   its two writers (`SkillService.record_mastery` and `EnrollmentService._grant_course_skills`)
   pass it *aware* values. asyncpg rejects the mix, so **leveling up** a skill that already existed
   blew up the request. It survived until now because it only affects the UPDATE branch.

**v1 product bugs, discovered by the regression suite and not by v2.**

5. Four sites auto-complete an enrollment on reaching progress 1.0, and **none of them granted the
   course's skills**. `POST /enrollments/{id}/complete` found the enrollment already completed,
   took its early return, and `user_skills` stayed empty: an employee would finish a course and get
   no credit at all. Fixed in `EnrollmentService.complete()`.
6. `PUT /lessons/{id}` was a **guaranteed 500** (`MissingGreenlet`): it read `lesson.exercises`
   from a loader that never eagerly loaded them. No test covered that route.

**Environment.**

7. `docker/compose/dev.yml` mounted the host repo over `/app`, so `uv run` inside the container saw
   a virtualenv with binaries from another OS, decided it was broken, and **deleted the host's
   `.venv`** to rebuild it. Fixed with an anonymous volume over `/app/.venv`.

The cross-cutting lesson, and the one that applies to the rest of the project: **a suite that has
never run is not coverage.** The two broken v1 routes (5 and 6) had sat in the repo for months with
green unit tests around them.

---

## 15. Review: objections dismissed

Two adversarial audits reviewed this document. **All blockers from both were verified against the
code and all of them turned out to be correct**, and are fixed above. What follows are the
**parts** of objections that were not applied, with the evidence for why.

### 15.1 "Force `fill_blank` on item A so `score_a` is continuous"

**Dismissed: the proposed fix doesn't work.** The diagnosis was indeed correct (with two binary
items, all three thresholds behave the same, and the tiebreak capped at 0.80 < 0.90), and it's fixed
in §7.2. But the suggested route — making `score_a` continuous via `fill_blank` — doesn't exist:
`_grade_fill_blank` (`src/services/exercise_service.py:34-43`) returns **0.0 as soon as a single
blank fails**, same as `_grade_test`, `_grade_true_false`, and `_grade_order_steps`. All four
deterministic types are all-or-nothing. Making it continuous would require changing v1's grading,
which is used in production for real `exercises`, and that is out of scope.

What was applied instead: renormalizing the tiebreak to `0.45a + 0.15b + 0.40c` (it reaches 1.0, so
every threshold is reachable), requiring item B to be a 4-option `test` (so the cited 6.25% is
accurate), and making the constructed tiebreak **mandatory** on every `critical` node. The
thresholds discriminate without needing partial credit (table in §7.2).

### 15.2 "Add a `schema_only` value to `generation_output`"

**Dismissed on cost/benefit, not on correctness.** The observation is valid:
`generation_jobs.output_type` is `NOT NULL` over a two-value enum, and a schema job is neither. But
adding a third value widens the same problem §3 documents — a Postgres enum can't lose values, so
the `downgrade` would leave **three** orphans instead of two — for a field that **no schema consumer
reads**: clients go by `status`, and `generation_service` already falls back to
`COURSE_AND_MANUAL` on any unknown value. It's documented as an explicit placeholder in §3.1 instead
of creating migration debt.

### 15.3 "Generate the role block with a `fast` call per user (~40 tokens)"

**Dismissed in favor of the same reviewer's other option.** The problem — the role wasn't in the
`cache_key` and per-role personalization got lost on every cache hit — is real and is fixed. Of the
two proposed routes, the first is taken (`role_bucket` inside the key), not the separately generated
block, for two concrete reasons: an extra LLM call **per user and per node** is exactly the cost the
cache exists to avoid (and it would be 100% of users, not the 20% of cache misses); and a block
generated outside the `ui_spec` would live outside `node_renders`, i.e. outside the audit trail and
outside the built-in `answer_key`. The "this helps you with X" line does get implemented, but
**deterministic and on the client** from `goal` (§6.2 Q2), with no tokens.

### 15.4 "Add `org_id` to the ten new tables"

**Applied partially, by design.** The **top-level** tables carry `org_id`, which is what
`data-model.md`'s convention requires: `course_nodes`, `learner_profiles`, `node_renders`,
`term_explanations`, `llm_usage_log`, `audit_log`. The child tables whose scoping derives
unambiguously from their parent and which are only queried by `user_id` or `node_id` do **not**
carry it: `course_node_prerequisites`, `learner_node_states`, `learning_events`, `node_probes`,
`node_attempts`, `node_feedback`, `node_render_views`. Adding `org_id` there would be one more
denormalized column to keep consistent on every write with no query that ever uses it. The
inconsistency the objection flagged — claiming multi-tenancy with a single org-scoped table — is
resolved by the six above.

### 15.5 Verifications that confirmed the document (no change required)

> **TWO OF THESE VERIFICATIONS ARE VOIDED on 2026-07-26** (product decision: full OpenUI adoption —
> `docs/design/openui-adoption.md`). This section reads as *"this is already checked, don't audit it
> again"*, so the two expired statements are struck through below instead of deleted, and what
> remains true is kept separate from what no longer is.
>
> 1. **The "no new npm dependency" promise no longer holds.** Three come in, with exact versions
>    and no `^`: `@openuidev/react-lang@0.2.9`, `@openuidev/lang-core@0.2.10`, and `zod@4.4.3`
>    (`apps/skillnet-web/package.json`, resolved in `pnpm-lock.yaml`). The versions are pinned
>    because none of the security properties the adoption relies on is a public contract of the
>    package; `tests/test_render_prompt_artifact.py::test_the_pinned_openui_versions_are_the_audited_ones`
>    is the alarm that fires when they get bumped.
> 2. **The browser parser is NO longer the Python one.** The Python one is kept, but as a
>    **validator** on the server (`src/render/gate.py` + `src/render/spec.py`): it validates before
>    persisting and re-serializes the `UISpec` to the canonical dialect. The rendering is done by
>    `<Renderer>` from `@openuidev/react-lang` over the components we register (§5.1, §5.3, §5.4).
>
> **What still holds from the original statement, and is verified:** the XSS mitigation.
> `react-markdown` 10 is still present **without** `rehype-raw`, there is no
> `dangerouslySetInnerHTML` anywhere in `apps/skillnet-web/src/`, and `framer-motion` is still
> present. That half doesn't depend on the adoption: the OpenUI packages don't interpret HTML, they
> map the language to our own React components.

Listed so no one audits them again: the Alembic chain is linear `0001→0004`, so
`down_revision="0004"` is correct and there are no conflicting heads · no new route from §11
collides with the ~40 existing ones · `resolve_llm_config`'s precedence works exactly as §4.3
describes for `runtime_fast`/`runtime_heavy` (`src/llm/client.py:61-67`) · `GenerationJobRead.status`
is `str`, so the two new enum members don't break it · the `integration` marker is already in the
pytest configuration · `react-markdown` 10 is present **without** `rehype-raw` and `framer-motion`
is present, so ~~both the XSS mitigation and the "no new npm dependency" promise hold~~ **the XSS
mitigation holds** (the "no new npm dependency" promise does not: see the notice above) ·
`docker/api.Dockerfile` starts with `--workers 1`, consistent with the SSE assumption.

On the npm package `openui`: ~~whether it exists or not is irrelevant, because §5.4 implements the
parser in **Python** and adds no frontend dependency~~. **Corrected on 2026-07-26:** the real
package is `@openuidev/*`, it exists, and it **does** come in as a frontend dependency; the Python
parser is kept as a server-side validator, not as the browser parser. What was a real risk —
presenting "OpenUI Lang" as an external dialect with one example and no grammar — is closed twice:
with the frozen EBNF and the three escape rules of §5.4 (plus one malformed fixture per rule), and,
since the adoption, with the dialect's own reference implementation.
