# Data Model

> **Status: v1.** PostgreSQL + pgvector. Self-hosted, one instance per company.

---

## Overview

```
organizations ─┬── users ──┬── user_sessions
               │           └── chat_sessions ── chat_messages
               ├── documents ──── document_chunks (pgvector + tsvector)
               ├── skills ────── skill_categories
               ├── courses ──┬── modules ──┬── lessons ── exercises
               │             │             └── skill_checkpoints
               │             └── manuals
               ├── background_jobs
               ├── api_keys
               ├── webhooks ──── webhook_deliveries
               └── audit_log

enrollments ─── exercise_attempts
user_skills
spaced_repetition
generation_jobs
course_feedback
```

All tables are scoped by `org_id` (directly or through parent FK). Single organization per deployment.

---

## Schema

### Organizations

One row per deployment. Exists for data scoping and future-proofing.

```sql
CREATE TABLE organizations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    slug        text NOT NULL UNIQUE,
    settings    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
```

### Users

```sql
CREATE TYPE user_role AS ENUM ('admin', 'employee');
CREATE TYPE learning_profile AS ENUM ('standard', 'focus', 'fast');

CREATE TABLE users (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            uuid NOT NULL REFERENCES organizations(id),
    email             text NOT NULL,
    hashed_password   text NOT NULL,
    full_name         text NOT NULL,
    role              user_role NOT NULL DEFAULT 'employee',
    learning_profile  learning_profile NOT NULL DEFAULT 'standard',
    accessibility     jsonb NOT NULL DEFAULT '{}',
    hired_at          date,
    is_active         boolean NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, email)
);
```

`accessibility` stores flags the employee opts into during onboarding:

```json
{"tea": false, "tdah": true, "dislexia": false}
```

The frontend reads these to adapt rendering. The backend never uses them for logic.

### Documents (uploaded source material)

```sql
CREATE TYPE document_status AS ENUM ('pending', 'processing', 'ready', 'error');

CREATE TABLE documents (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id),
    uploaded_by     uuid REFERENCES users(id) ON DELETE SET NULL,
    title           text NOT NULL,
    storage_path    text NOT NULL,
    file_type       text NOT NULL,
    page_count      int,
    size_bytes      bigint,
    full_text       text,
    embedding_model text,
    embedding_dim   int,
    status          document_status NOT NULL DEFAULT 'pending',
    error_message   text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
```

### Document chunks (RAG with pgvector)

```sql
CREATE TABLE document_chunks (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id    uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content        text NOT NULL,
    embedding      vector(384) NOT NULL,
    chunk_index    int NOT NULL,
    search_vector  tsvector GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED,
    metadata       jsonb NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

CREATE INDEX idx_chunks_search ON document_chunks USING gin(search_vector);
```

`metadata` holds position info from the source document:

```json
{"page": 3, "section": "Devoluciones", "heading": "Plazo"}
```

**Embedding dimension:** 384 for `multilingual-e5-small`. Change to 1024 if using `multilingual-e5-large`. The `vector(N)` declaration and index must match the model.

**IVFFlat `lists`:** rule of thumb is `sqrt(num_rows)`. Start with 10, increase as the chunk count grows past a few thousand.

### Skills taxonomy

```sql
CREATE TABLE skill_categories (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id    uuid NOT NULL REFERENCES organizations(id),
    name      text NOT NULL,
    position  int NOT NULL DEFAULT 0,
    UNIQUE (org_id, name)
);

CREATE TABLE skills (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id),
    category_id   uuid REFERENCES skill_categories(id),
    name          text NOT NULL,
    description   text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, name)
);
```

Example taxonomy:

```
Ventas (category)
  ├── devoluciones (skill)
  ├── atencion_cliente
  └── cierre

Tecnologia (category)
  ├── html_css
  └── excel
```

### Courses

```sql
CREATE TYPE content_status AS ENUM ('draft', 'published', 'archived');

CREATE TABLE courses (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES organizations(id),
    created_by          uuid REFERENCES users(id) ON DELETE SET NULL,
    source_document_id  uuid REFERENCES documents(id),
    title               text NOT NULL,
    description         text,
    outcome             text,
    status              content_status NOT NULL DEFAULT 'draft',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
```

`outcome` is what the employee will be able to do after completing the course. Required before publishing.

### Modules

```sql
CREATE TABLE modules (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id   uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title       text NOT NULL,
    summary     text,
    position    int NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
```

### Lessons

```sql
CREATE TABLE lessons (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    module_id   uuid NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    title       text NOT NULL,
    content     text NOT NULL,
    position    int NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
```

### Exercises

```sql
CREATE TYPE exercise_type AS ENUM (
    'test', 'true_false', 'fill_blank',
    'order_steps', 'practical_case', 'dialogue'
);

CREATE TABLE exercises (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lesson_id   uuid NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    type        exercise_type NOT NULL,
    content     jsonb NOT NULL,
    position    int NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
```

The `content` jsonb varies by type:

```json
// test
{
    "question": "How many days for returns?",
    "options": ["14", "30", "60", "90"],
    "correct": 1,
    "explanation": "Manual, p.3: '30 natural days'"
}

// true_false
{
    "statement": "Bank statement is valid as proof of purchase",
    "correct": true,
    "explanation": "Manual, p.5"
}

// fill_blank
{
    "template": "The product must be ___ and with ___",
    "blanks": ["unused", "tags"],
    "explanation": "..."
}

// order_steps
{
    "instruction": "Order the return process steps",
    "steps": ["Verify product", "Scan", "Register", "Refund"],
    "correct_order": [0, 1, 2, 3],
    "explanation": "..."
}

// practical_case
{
    "context": "Friday 18:45. Customer with a 45-day old coffee maker...",
    "question": "What do you do?",
    "rubric": [
        {"criteria": "Mentions 30-day policy doesn't apply", "required": true},
        {"criteria": "Offers manufacturer warranty", "required": true}
    ],
    "explanation": "..."
}

// dialogue
{
    "context": "Angry customer, third visit this week...",
    "system_prompt": "You are an angry customer...",
    "max_turns": 4,
    "evaluation_criteria": ["friendly tone", "concrete solution"]
}
```

### Skill checkpoints

Maps module completion to skill level changes. When an employee completes a module, their skill level updates automatically.

```sql
CREATE TYPE skill_level AS ENUM ('low', 'medium', 'high');

CREATE TABLE skill_checkpoints (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id     uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    skill_id      uuid NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    module_id     uuid NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    target_level  skill_level NOT NULL,
    UNIQUE (course_id, skill_id, module_id)
);
```

Example: course "Returns" teaches skill "devoluciones":
- Complete module 3 -> level = medium
- Complete module 5 -> level = high

### Manuals (reference material)

Always generated alongside a course. Can also exist standalone.

```sql
CREATE TABLE manuals (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES organizations(id),
    created_by          uuid NOT NULL REFERENCES users(id),
    source_document_id  uuid REFERENCES documents(id),
    course_id           uuid REFERENCES courses(id),
    title               text NOT NULL,
    content             jsonb NOT NULL,
    status              content_status NOT NULL DEFAULT 'draft',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
```

Rule: a course always has a manual. A manual can exist without a course.

### Enrollments

```sql
CREATE TYPE enrollment_status AS ENUM ('assigned', 'in_progress', 'completed');

CREATE TABLE enrollments (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id     uuid NOT NULL REFERENCES courses(id),
    assigned_by   uuid REFERENCES users(id) ON DELETE SET NULL,
    status        enrollment_status NOT NULL DEFAULT 'assigned',
    deadline      date,
    started_at    timestamptz,
    completed_at  timestamptz,
    score         real,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, course_id)
);
```

### Exercise attempts

```sql
CREATE TABLE exercise_attempts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_id   uuid NOT NULL REFERENCES exercises(id),
    answer        jsonb NOT NULL,
    score         real NOT NULL CHECK (score >= 0 AND score <= 1),
    passed        boolean NOT NULL,
    feedback      text,
    attempted_at  timestamptz NOT NULL DEFAULT now()
);
```

Multiple attempts per exercise allowed. The latest attempt is the current state.

### User skills (the skill graph)

```sql
CREATE TABLE user_skills (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id          uuid NOT NULL REFERENCES skills(id),
    level             skill_level NOT NULL DEFAULT 'low',
    source            text NOT NULL DEFAULT 'checkpoint',
    last_assessed_at  timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, skill_id)
);
```

`source`: `'checkpoint'` (system set it via module completion) or `'manual'` (admin assigned it directly).

Level never decreases from checkpoints. Admin can override to any level.

### Spaced repetition (HLR)

```sql
CREATE TABLE spaced_repetition (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_id      uuid NOT NULL REFERENCES exercises(id),
    half_life_days   real NOT NULL DEFAULT 7.0,
    review_count     int NOT NULL DEFAULT 0,
    last_reviewed_at timestamptz,
    next_review_at   timestamptz NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, exercise_id)
);
```

Algorithm:
- Initial half-life: 7 days
- Correct answer: `half_life *= 2`
- Wrong answer: `half_life /= 2`
- Review scheduled when: `P(forget) = 1 - exp(-elapsed / half_life) > 0.3`

### Generation jobs

Tracks the multi-step content generation pipeline. The admin sees progress in real time.

```sql
CREATE TYPE generation_output AS ENUM ('course_and_manual', 'manual_only');
CREATE TYPE generation_step AS ENUM (
    'pending', 'extracting', 'structuring',
    'generating', 'reviewing', 'published', 'failed'
);

CREATE TABLE generation_jobs (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                uuid NOT NULL REFERENCES organizations(id),
    triggered_by          uuid NOT NULL REFERENCES users(id),
    source_document_id    uuid REFERENCES documents(id),
    output_type           generation_output NOT NULL,
    status                generation_step NOT NULL DEFAULT 'pending',
    langgraph_thread_id   text,
    progress              jsonb NOT NULL DEFAULT '{}',
    result_course_id      uuid REFERENCES courses(id),
    result_manual_id      uuid REFERENCES manuals(id),
    error_message         text,
    cancelled_at          timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);
```

### Course feedback

Post-course survey: 3 questions that generate a revision report for the course creator.

```sql
CREATE TABLE course_feedback (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id   uuid NOT NULL REFERENCES courses(id),
    responses   jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, course_id)
);
```

### User sessions (auth tokens)

```sql
CREATE TABLE user_sessions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  text NOT NULL,
    ip_address  text,
    user_agent  text,
    expires_at  timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
```

### Audit log

```sql
CREATE TABLE audit_log (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL REFERENCES organizations(id),
    actor_id     uuid NOT NULL REFERENCES users(id),
    action       text NOT NULL,
    target_type  text,
    target_id    uuid,
    detail       jsonb DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now()
);
```

### Background jobs

```sql
CREATE TABLE background_jobs (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL REFERENCES organizations(id),
    type           text NOT NULL CHECK (type IN (
                       'document_ingestion',
                       'spaced_repetition_recalc',
                       'bulk_user_import',
                       'bulk_course_assign'
                   )),
    status         text NOT NULL DEFAULT 'pending',
    payload        jsonb DEFAULT '{}',
    result         jsonb,
    error_message  text,
    attempt_count  int DEFAULT 0,
    max_attempts   int DEFAULT 3,
    scheduled_at   timestamptz DEFAULT now(),
    started_at     timestamptz,
    completed_at   timestamptz,
    locked_by      text,
    locked_at      timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
```

### Chat sessions

```sql
CREATE TABLE chat_sessions (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id                uuid NOT NULL REFERENCES organizations(id),
    agent_type            text NOT NULL CHECK (agent_type IN ('tutor', 'admin')),
    title                 text,
    summary               text,
    summary_covers_until  int DEFAULT 0,
    course_id             uuid REFERENCES courses(id),
    is_active             boolean DEFAULT true,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);
```

### Chat messages

```sql
CREATE TABLE chat_messages (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        text NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     text NOT NULL,
    metadata    jsonb DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);
```

### API keys

```sql
CREATE TABLE api_keys (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id),
    created_by    uuid NOT NULL REFERENCES users(id),
    name          text NOT NULL,
    key_hash      text NOT NULL,
    scopes        text[] NOT NULL,
    is_active     boolean DEFAULT true,
    last_used_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
```

### Webhooks

```sql
CREATE TABLE webhooks (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL REFERENCES organizations(id),
    url            text NOT NULL,
    events         text[] NOT NULL,
    secret         text NOT NULL,
    is_active      boolean DEFAULT true,
    failure_count  int DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now()
);
```

### Webhook deliveries

```sql
CREATE TABLE webhook_deliveries (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id     uuid NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event          text NOT NULL,
    payload        jsonb NOT NULL,
    status         text NOT NULL DEFAULT 'pending',
    response_code  int,
    attempt_count  int DEFAULT 0,
    next_retry_at  timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now()
);
```

---

## Key queries

### Skills matrix (admin view)

```sql
SELECT u.full_name, s.name AS skill, us.level
FROM user_skills us
JOIN users u ON u.id = us.user_id
JOIN skills s ON s.id = us.skill_id
WHERE u.org_id = $1
ORDER BY u.full_name, s.name;
```

### "What's due today" (employee dashboard)

```sql
-- Spaced repetition reviews due
SELECT e.id, e.content, sr.next_review_at
FROM spaced_repetition sr
JOIN exercises e ON e.id = sr.exercise_id
WHERE sr.user_id = $1
  AND sr.next_review_at <= now()
ORDER BY sr.next_review_at
LIMIT 3;

-- Active enrollments with nearest deadline
SELECT c.title, en.status, en.deadline,
       COUNT(DISTINCT m.id) AS total_modules
FROM enrollments en
JOIN courses c ON c.id = en.course_id
JOIN modules m ON m.course_id = c.id
WHERE en.user_id = $1
  AND en.status != 'completed'
ORDER BY en.deadline NULLS LAST
LIMIT 3;
```

### Semantic search (RAG)

```sql
SELECT dc.content, dc.metadata,
       1 - (dc.embedding <=> $2) AS similarity
FROM document_chunks dc
JOIN documents d ON d.id = dc.document_id
WHERE d.org_id = $1
ORDER BY dc.embedding <=> $2
LIMIT 5;
```

`$2` is the embedding vector of the user's question.

### Mentor matching

```sql
SELECT
    mentor.full_name AS mentor,
    mentee.full_name AS mentee,
    s.name AS skill
FROM user_skills us_high
JOIN users mentor ON mentor.id = us_high.user_id
JOIN user_skills us_low ON us_low.skill_id = us_high.skill_id
    AND us_low.level = 'low'
JOIN users mentee ON mentee.id = us_low.user_id
JOIN skills s ON s.id = us_high.skill_id
WHERE us_high.level = 'high'
  AND mentor.org_id = $1
  AND mentor.id != mentee.id;
```

---

## Indexes

Beyond the pgvector index on `document_chunks.embedding`:

```sql
-- Lookups by org
CREATE INDEX idx_users_org ON users(org_id);
CREATE INDEX idx_documents_org ON documents(org_id);
CREATE INDEX idx_courses_org ON courses(org_id);
CREATE INDEX idx_skills_org ON skills(org_id);

-- Enrollment lookups
CREATE INDEX idx_enrollments_user ON enrollments(user_id);
CREATE INDEX idx_enrollments_course ON enrollments(course_id);

-- Exercise attempts for progress tracking
CREATE INDEX idx_attempts_user ON exercise_attempts(user_id);
CREATE INDEX idx_attempts_exercise ON exercise_attempts(exercise_id);

-- Spaced repetition scheduling
CREATE INDEX idx_sr_next_review ON spaced_repetition(user_id, next_review_at);

-- User skills for matrix queries
CREATE INDEX idx_user_skills_user ON user_skills(user_id);
CREATE INDEX idx_user_skills_skill ON user_skills(skill_id);

-- User sessions
CREATE INDEX idx_user_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_token ON user_sessions(token_hash);
CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);

-- Audit log
CREATE INDEX idx_audit_log_org ON audit_log(org_id);
CREATE INDEX idx_audit_log_actor ON audit_log(actor_id);
CREATE INDEX idx_audit_log_target ON audit_log(target_type, target_id);
CREATE INDEX idx_audit_log_created ON audit_log(created_at);

-- Background jobs
CREATE INDEX idx_background_jobs_org ON background_jobs(org_id);
CREATE INDEX idx_background_jobs_status ON background_jobs(status);
CREATE INDEX idx_background_jobs_scheduled ON background_jobs(scheduled_at);

-- Chat sessions and messages
CREATE INDEX idx_chat_sessions_user ON chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_org ON chat_sessions(org_id);
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);

-- API keys
CREATE INDEX idx_api_keys_org ON api_keys(org_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);

-- Webhooks and deliveries
CREATE INDEX idx_webhooks_org ON webhooks(org_id);
CREATE INDEX idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);
CREATE INDEX idx_webhook_deliveries_status ON webhook_deliveries(status);
```

### LLM usage log

Operational logging for token usage tracking and cost analysis. Not a core domain table — exists for observability.

```sql
CREATE TABLE llm_usage_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id),
    user_id     uuid REFERENCES users(id),
    job_id      uuid REFERENCES generation_jobs(id),
    use_case    text NOT NULL,
    model       text NOT NULL,
    tokens_in   int NOT NULL,
    tokens_out  int NOT NULL,
    duration_ms int NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_llm_usage_log_org ON llm_usage_log(org_id, created_at);
CREATE INDEX idx_llm_usage_log_user ON llm_usage_log(user_id, created_at);
```

---

## Extensions required

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector
```

---

## Notes

- **27 tables total** across core domain, learning tracking, content generation, chat, and platform infrastructure. See the overview diagram for the full hierarchy.
- **UUID primary keys** everywhere. No auto-increment integers. Clean for distributed systems and API exposure.
- **`org_id` on all top-level tables.** Even with single-tenant deployment, this keeps queries explicit and makes future multi-tenancy possible without schema changes.
- **`jsonb` for flexible fields.** Exercise content, accessibility flags, organization settings, document chunk metadata. Avoids schema changes when adding new exercise types or config options.
- **Soft delete not implemented.** For MVP, hard deletes with CASCADE. If audit trail is needed later, add `deleted_at` columns.
- **Timestamps are `timestamptz`.** Always UTC in the database, converted to local time in the frontend.
