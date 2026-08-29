---
title: "Modelo de datos"
order: 4
section: "core"
---

# Modelo de datos

> **Estado: v1.** PostgreSQL + pgvector. Autoalojado, una instancia por empresa.

---

## Visión general

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

Todas las tablas están delimitadas por `org_id` (directamente o a través de una FK padre). Una única organización por despliegue.

---

## Esquema

### Organizations

Una fila por despliegue. Existe para delimitar los datos y prepararse para el futuro.

```sql
CREATE TYPE workspace_mode AS ENUM ('organization', 'individual');

CREATE TABLE organizations (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           text NOT NULL,
    slug           text NOT NULL UNIQUE,
    workspace_mode workspace_mode NOT NULL DEFAULT 'organization',
    settings       jsonb NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
```

`workspace_mode` (migración 0017) es el modo de audiencia del despliegue — ver
`docs/design/audience-modes.md`. Es una capacidad estable por despliegue, fijada
una vez cuando se crea la fila de organización (a partir de `WORKSPACE_MODE`, por defecto
`organization`), nunca inferida a partir del número de usuarios. En `organization` la
fila representa una empresa/equipo/clase; en `individual` es el espacio personal de
una persona. Los despliegues existentes se actualizan a `organization`, así que nada cambia para
ellos. Los endpoints colectivos, exclusivos de organización (empleados, talento, stats,
asignación de cursos, skills) devuelven 404 en un espacio de trabajo `individual`.

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

`accessibility` almacena flags que el empleado activa voluntariamente durante el onboarding:

```json
{"tea": false, "tdah": true, "dislexia": false}
```

El frontend lee estos valores para adaptar el renderizado. El backend nunca los usa para lógica.

### Documents (material fuente subido)

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

### Document chunks (RAG con pgvector)

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

`metadata` guarda información de posición del documento fuente:

```json
{"page": 3, "section": "Devoluciones", "heading": "Plazo"}
```

**Dimensión del embedding:** 384 para `multilingual-e5-small`. Cámbialo a 1024 si usas `multilingual-e5-large`. La declaración `vector(N)` y el índice deben coincidir con el modelo.

**`lists` de IVFFlat:** la regla general es `sqrt(num_filas)`. Empieza con 10, auméntalo a medida que el número de chunks crezca por encima de unos pocos miles.

### Taxonomía de skills

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

Ejemplo de taxonomía:

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

`outcome` es lo que el empleado será capaz de hacer tras completar el curso. Obligatorio antes de publicar.

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

El jsonb `content` varía según el tipo:

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

Vincula la finalización de un módulo con cambios en el nivel de skill. Cuando un empleado completa un módulo, su nivel de skill se actualiza automáticamente.

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

Ejemplo: el curso "Devoluciones" enseña la skill "devoluciones":
- Completar el módulo 3 -> nivel = medium
- Completar el módulo 5 -> nivel = high

### Manuals (material de referencia)

Siempre se genera junto a un curso. También puede existir de forma independiente.

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

Regla: un curso siempre tiene un manual. Un manual puede existir sin curso.

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

Se permiten múltiples intentos por ejercicio. El intento más reciente es el estado actual.

### User skills (el grafo de skills)

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

`source`: `'checkpoint'` (el sistema lo fijó al completar un módulo) o `'manual'` (el admin lo asignó directamente).

El nivel nunca baja por los checkpoints. El admin puede anularlo a cualquier nivel.

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

Algoritmo:
- Vida media inicial: 7 días
- Respuesta correcta: `half_life *= 2`
- Respuesta incorrecta: `half_life /= 2`
- Repaso programado cuando: `P(olvido) = 1 - exp(-tiempo_transcurrido / half_life) > 0.3`

### Generation jobs

Sigue el pipeline de generación de contenido multipaso. El admin ve el progreso en tiempo real.

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

Encuesta posterior al curso: 3 preguntas que generan un informe de revisión para el creador del curso.

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

### User sessions (tokens de autenticación)

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

## Consultas clave

### Matriz de skills (vista de admin)

```sql
SELECT u.full_name, s.name AS skill, us.level
FROM user_skills us
JOIN users u ON u.id = us.user_id
JOIN skills s ON s.id = us.skill_id
WHERE u.org_id = $1
ORDER BY u.full_name, s.name;
```

### "Lo que toca hoy" (dashboard del empleado)

```sql
-- Repasos de repetición espaciada pendientes
SELECT e.id, e.content, sr.next_review_at
FROM spaced_repetition sr
JOIN exercises e ON e.id = sr.exercise_id
WHERE sr.user_id = $1
  AND sr.next_review_at <= now()
ORDER BY sr.next_review_at
LIMIT 3;

-- Inscripciones activas con la fecha límite más cercana
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

### Búsqueda semántica (RAG)

```sql
SELECT dc.content, dc.metadata,
       1 - (dc.embedding <=> $2) AS similarity
FROM document_chunks dc
JOIN documents d ON d.id = dc.document_id
WHERE d.org_id = $1
ORDER BY dc.embedding <=> $2
LIMIT 5;
```

`$2` es el vector de embedding de la pregunta del usuario.

### Emparejamiento de mentores

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

## Índices

Además del índice pgvector en `document_chunks.embedding`:

```sql
-- Búsquedas por org
CREATE INDEX idx_users_org ON users(org_id);
CREATE INDEX idx_documents_org ON documents(org_id);
CREATE INDEX idx_courses_org ON courses(org_id);
CREATE INDEX idx_skills_org ON skills(org_id);

-- Búsquedas de inscripciones
CREATE INDEX idx_enrollments_user ON enrollments(user_id);
CREATE INDEX idx_enrollments_course ON enrollments(course_id);

-- Intentos de ejercicio para el seguimiento del progreso
CREATE INDEX idx_attempts_user ON exercise_attempts(user_id);
CREATE INDEX idx_attempts_exercise ON exercise_attempts(exercise_id);

-- Programación de la repetición espaciada
CREATE INDEX idx_sr_next_review ON spaced_repetition(user_id, next_review_at);

-- User skills para las consultas de la matriz
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

-- Chat sessions y messages
CREATE INDEX idx_chat_sessions_user ON chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_org ON chat_sessions(org_id);
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);

-- API keys
CREATE INDEX idx_api_keys_org ON api_keys(org_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);

-- Webhooks y deliveries
CREATE INDEX idx_webhooks_org ON webhooks(org_id);
CREATE INDEX idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);
CREATE INDEX idx_webhook_deliveries_status ON webhook_deliveries(status);
```

### LLM usage log

Registro operativo para el seguimiento de uso de tokens y el análisis de costes. No es una tabla del dominio central — existe para observabilidad.

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

## Extensiones necesarias

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector
```

---

## Notas

- **27 tablas en total** repartidas entre el dominio central, el seguimiento del aprendizaje, la generación de contenido, el chat y la infraestructura de la plataforma. Ver el diagrama de visión general para la jerarquía completa.
- **Claves primarias UUID** en todas partes. Sin enteros autoincrementales. Limpio para sistemas distribuidos y exposición por API.
- **`org_id` en todas las tablas de primer nivel.** Incluso con un despliegue de un solo tenant, esto mantiene las consultas explícitas y hace posible el multi-tenancy futuro sin cambios de esquema.
- **`jsonb` para campos flexibles.** Contenido de ejercicio, flags de accesibilidad, ajustes de organización, metadatos de chunk de documento. Evita cambios de esquema al añadir nuevos tipos de ejercicio u opciones de configuración.
- **El borrado suave no está implementado.** Para el MVP, borrados definitivos con CASCADE. Si más adelante se necesita un rastro de auditoría, se añaden columnas `deleted_at`.
- **Los timestamps son `timestamptz`.** Siempre UTC en la base de datos, convertidos a hora local en el frontend. Una excepción sobrevivió hasta la migración `0006`: `user_skills.last_assessed_at` venía de `0003` como `timestamp without time zone`, mientras que ambos escritores le pasan datetimes con zona horaria. asyncpg rechaza esa combinación, así que *elevar* una fila de skill existente fallaba. `0006` la convierte con `AT TIME ZONE 'UTC'`. Las otras columnas ingenuas de `0003` solo se rellenan en el servidor mediante `now()`/`onupdate` y se dejaron deliberadamente sin tocar.

---

## Apéndice: el esquema v2 (cursos dinámicos)

**Este documento describe el esquema v1 y no se reescribe aquí.** Todo lo de abajo sigue siendo
correcto y sigue siendo sobre lo que corre en producción un curso v1 (cualquier curso que no esté en la ruta
`dynamic`+`validated`).

v2 (cursos dinámicos) añade una cantidad considerable de esquema encima, y su documento de diseño de referencia es
**[`v2-dynamic-courses.md`](/docs/dynamic-courses) §3**, no este fichero. Ve allí para el detalle a
nivel de columna, la composición de `cache_key`, las reglas de retención y el razonamiento.

La forma de la adición, para que sepas si necesitas mirarlo:

- La migración **`0005`** crea **13 tablas y 8 enums**, añade **6 columnas** a `courses`
  (incluyendo `delivery_mode`, `schema_status`, `schema_version` e `intent_density`) y añade 2
  valores al enum `generation_step`. Está escrita a mano, no autogenerada, y el orden de creación
  importa — hay dos referencias hacia adelante en el esquema v2.
- Las tablas nuevas cubren: el grafo de curso (`course_nodes`, `course_node_prerequisites`), las
  pantallas generadas y quién las vio (`node_renders`, `node_render_views`), el estado por aprendiz
  (`learner_profiles`, `learner_node_states`, `node_probes`, `node_attempts`), feedback y
  telemetría (`node_feedback`, `learning_events`, `llm_usage_log`, `term_explanations`) y
  `audit_log`.
  **`node_feedback` se borró el 2026-08-29 con la migración `0036`**, vacía: su único escritor
  era `POST /nodes/{id}/feedback` y ningún cliente llegó a llamarlo. Ver
  `docs/design/future-lesson-feedback.md`.
- **Nada en v1 cambia de forma.** Las columnas v2 en `courses` tienen todas valores por defecto
  que reproducen el comportamiento v1, que es lo que permite que el flag esté desactivado por
  defecto.
- Dos propiedades que conviene conocer antes de consultar cualquiera de esto: `node_renders` **no
  tiene `user_id`** (la caché se comparte por bucket, y el rastro de lectura por usuario vive en
  `node_render_views`), y `answer_key` es una **columna separada** que ningún esquema de respuesta
  incluye.

`downgrade()` en `0005` elimina las 13 tablas, las 6 columnas y los 8 enums, pero deja
`schema_proposing` y `schema_proposed` huérfanos en `generation_step` — PostgreSQL no puede
eliminar un valor de un enum. Eso está documentado en lugar de arreglado, y lo verifica
`tests/integration/test_migration_0005.py`.

### Preferencias de aprendizaje y revisión de personalización

La migración **`0011_learner_preferences`** añade la primera preferencia declarada que puede
modificar un render dinámico:

- `learner_profiles.learning_preferences`: JSONB cerrado y versionado con presentación
  (`balanced|visual|textual|interactive`), detalle (`concise|standard|detailed`) e imágenes
  (`when_useful|prefer|avoid`);
- `learner_profiles.personalization_revision`: revisión monotónica que cambia cuando cambia
  realmente el bundle;
- `learner_node_states.pinned_personalization_revision`: revisión con la que se fijó el render.

La preferencia declarada no se mezcla con `format_vector` (evidencia inferida) ni con
`users.accessibility` (necesidades funcionales). Antes de influir en los prompts se normaliza a un
bucket canónico no identificativo que forma parte de `cache_key`. Al guardar un bundle diferente se
incrementa la revisión y se despejan los pins de ese aprendiz sin borrar el historial compartido.
El guard al fijar impide que una generación iniciada con una revisión antigua vuelva a convertirse
en el render vigente después de un cambio concurrente.

### Dossiers pedagógicos preparados

La migración **`0012_node_knowledge_packs`** añade `node_knowledge_packs`, una tabla de snapshots
inmutables por `(node_id, source_fingerprint, generator_version)`. Cada fila pertenece a una
organización, curso y nodo, y registra `schema_version`, estado
(`pending|ready|review_required|stale|failed`),
Markdown revisable, contrato JSON completo (`pack_payload`), vista compacta de átomos, procedencia,
hashes, tokens, duración y error.

`source_fingerprint` incluye los campos pedagógicamente relevantes del nodo y el hash del contexto
de fuente. Un snapshot nuevo marca los anteriores como `stale`; un worker solo puede completar la
fila que sigue `pending` con el fingerprint que reclamó. El Markdown no se reimporta: para selección,
auditoría y caché la autoridad es `pack_payload` + `pack_hash`. `review_required` conserva el
payload y el Markdown para inspección, pero solo `ready` puede alimentar OpenUI.

**Estados del pack y el criterio de `ready` (fundamentado).** El enum persistido `PackStatus`
(`knowledge_pack/contracts.py`) es `DRAFT`, `READY`, `REVIEW_REQUIRED`, `REJECTED`; `stale`
y `failed` son **resultados del runner**, no estados de fila (`knowledge_pack/runner.py`
`_RETRYABLE_OUTCOMES = {"failed", "stale", "review_required"}`). Un pack se vuelve `ready` solo
cuando `generator.py::_build_pack` encuentra los tres: al menos un átomo `must_preserve`, al menos
un `evidence_spec` `required`, y **ninguna** brecha de falta de datos que bloquee
(`usable = bool(must_preserve) and has_required_evidence and not blocking_gap`). Las unidades de
fuente no cubiertas se registran de forma no bloqueante; un pack que no es `usable` se almacena como
`REVIEW_REQUIRED` con su payload y Markdown conservados para inspección.

### Learning note (personalización en texto libre)

La migración **`0018_learner_learning_note`** añade `learner_profiles.learning_note`, una columna
`Text` anulable que guarda la nota de texto libre del aprendiz *"cómo me gusta aprender"*. Guía
**la forma de una explicación, nunca los hechos** (ver [`personalization.md`](/docs/personalization)). Está
limitada en longitud en la capa Pydantic (`LEARNING_NOTE_MAX_CHARS = 500`,
`src/personalization/learning_note.py`), normalizada al escribirse, y su huella sha1 de 12
caracteres `learning_note_fingerprint` particiona la clave de la caché de render
(`node_render_service.build_render_key`): una nota vacía deja intacta cualquier clave existente;
dos aprendices con la misma nota comparten render. Escribirla fija `personalization_changed`,
eliminando los pins de render de ese aprendiz.

### Artefactos multimedia

Dos tablas delimitadas por org respaldan los medios generados (ver [`media-artifacts.md`](/docs/media-artifacts)).

- **`media_artifacts`** (`src/models/media_artifact.py`) — un asset multimedia generado.
  Enum `kind`, `MediaKind`: `podcast, slides, infographic, video, mindmap, report, cover_image`.
  Enum `status`, `MediaArtifactStatus`: `pending -> running -> done | error` (el estado de fallo
  es `error`, no "failed"). Columnas: `org_id`, `course_id`, `node_id` (anulable), `kind`,
  `status`, `spec_json` (JSONB, guarda el `scope` — `node|course|standalone` — la `note` de
  personalización, las citas y las referencias a sub-assets), `asset_path` (anulable),
  `content_hash` (clave de deduplicación sha256), `error`. **No hay columna `scope`**: el scope
  vive dentro de `spec_json`. Delimitado por org, no por usuario.
- **`course_artifact_generators`** (`src/models/course_artifact_generator.py`) — PK compuesta
  `(course_id, user_id)`. Registra quién, además de los admins, puede generar medios a nivel de
  curso.
