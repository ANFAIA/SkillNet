---
title: "API de backend"
order: 3
section: "core"
---

## 4. Arquitectura de la API de backend

> **Estado: v1.** Estructura de backend completa para `apps/skillnet-api/`. Alineado con [data-model.md](data-model.md), [screens.md](screens.md) y [architecture.md](architecture.md).

---

### 4.1 Estructura del proyecto

```
apps/skillnet-api/
├── pyproject.toml                  # proyecto uv, dependencias
├── alembic.ini                     # configuración de migraciones de BD
├── alembic/
│   ├── env.py
│   └── versions/                   # Ficheros de migración
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # factoría de la app FastAPI, lifespan, middleware
│   ├── config.py                   # Pydantic Settings (variables de entorno)
│   │
│   ├── auth/                       # Autenticación (fastapi-users)
│   │   ├── __init__.py
│   │   ├── backend.py              # CookieTransport + estrategia de sesión
│   │   ├── manager.py              # UserManager (crear, verificar, etc.)
│   │   ├── schemas.py              # UserRead, UserCreate, UserUpdate
│   │   └── router.py               # /auth/login, /auth/logout, /auth/me
│   │
│   ├── models/                     # Modelos ORM de SQLAlchemy (1 fichero por tabla)
│   │   ├── __init__.py             # Reexporta todos los modelos
│   │   ├── base.py                 # DeclarativeBase, mixins comunes (TimestampMixin, UUIDMixin)
│   │   ├── organization.py
│   │   ├── user.py                 # Extiende el modelo SQLAlchemy de fastapi-users
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
│   ├── repositories/               # Capa de acceso a datos (consultas async de SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseRepository[T] — CRUD genérico
│   │   ├── user_repo.py
│   │   ├── document_repo.py
│   │   ├── course_repo.py          # Incluye la carga anidada de módulo/lección/ejercicio
│   │   ├── enrollment_repo.py
│   │   ├── exercise_attempt_repo.py
│   │   ├── skill_repo.py           # Skills + categorías + user_skills + consulta de la matriz
│   │   ├── manual_repo.py
│   │   ├── spaced_repetition_repo.py
│   │   ├── generation_job_repo.py
│   │   ├── course_feedback_repo.py
│   │   ├── document_chunk_repo.py  # Búsqueda de similitud vectorial
│   │   ├── chat_session_repo.py
│   │   ├── chat_message_repo.py
│   │   ├── background_job_repo.py
│   │   ├── user_session_repo.py
│   │   ├── audit_log_repo.py
│   │   ├── api_key_repo.py
│   │   ├── webhook_repo.py
│   │   └── webhook_delivery_repo.py
│   │
│   ├── services/                   # Lógica de negocio (sin conocimiento de BD ni de HTTP)
│   │   ├── __init__.py
│   │   ├── user_service.py         # Invitar, invitación masiva, desactivar
│   │   ├── document_service.py     # Subida a disco, dispara el procesamiento
│   │   ├── course_service.py       # CRUD, ciclo de vida publicar/archivar
│   │   ├── enrollment_service.py   # Asignar, cálculo de progreso, completar
│   │   ├── exercise_service.py     # Calificar intento, comprobación automática, calificado por IA
│   │   ├── skill_service.py        # Matriz, sugerencias de mentoría, verify_skill
│   │   ├── manual_service.py       # CRUD, vinculado al curso
│   │   ├── spaced_repetition_service.py  # Algoritmo HLR, repasos pendientes, enviar repaso
│   │   ├── generation_service.py   # Orquesta el pipeline de generación
│   │   ├── chat_service.py         # Chat de tutor + admin (RAG + streaming)
│   │   ├── alert_service.py        # Calcula alertas a partir de los datos de progreso
│   │   ├── stats_service.py        # Agregaciones del dashboard
│   │   └── feedback_service.py     # Envío + generación del informe de revisión
│   │
│   ├── routes/                     # Routers de FastAPI (finos — validan, llaman al service, devuelven)
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── documents.py
│   │   ├── courses.py              # Incluye las acciones /generate, /publish, /archive
│   │   ├── modules.py              # Anidado bajo courses
│   │   ├── lessons.py              # Anidado bajo modules
│   │   ├── exercises.py            # Incluye la acción /attempt
│   │   ├── enrollments.py
│   │   ├── skills.py               # Categorías, skills, matriz, mentoría
│   │   ├── manuals.py
│   │   ├── chat.py                 # Endpoints SSE (tutor + admin)
│   │   ├── spaced_repetition.py
│   │   ├── generation_jobs.py
│   │   ├── stats.py                # /stats, /alerts
│   │   ├── settings.py             # Ajustes de la organización, config de LLM
│   │   └── feedback.py
│   │
│   ├── schemas/                    # Modelos Pydantic para petición/respuesta
│   │   ├── __init__.py
│   │   ├── common.py               # Paginación, ErrorResponse, SuccessMessage
│   │   ├── user.py
│   │   ├── document.py
│   │   ├── course.py               # Incluye los esquemas anidados de módulo/lección/ejercicio
│   │   ├── enrollment.py
│   │   ├── exercise.py             # AttemptRequest, AttemptResponse, por tipo de ejercicio
│   │   ├── skill.py                # SkillMatrix, MentorshipSuggestion
│   │   ├── manual.py
│   │   ├── chat.py                 # ChatMessage, ChatEvent (SSE)
│   │   ├── spaced_repetition.py
│   │   ├── generation_job.py
│   │   ├── stats.py                # DashboardStats, Alert
│   │   ├── settings.py
│   │   └── feedback.py
│   │
│   ├── deps/                       # Inyección de dependencias de FastAPI
│   │   ├── __init__.py
│   │   ├── db.py                   # get_async_session
│   │   ├── auth.py                 # current_user, current_active_user, require_admin
│   │   ├── llm.py                  # get_llm_client
│   │   └── embedding.py            # get_embedding_service
│   │
│   ├── llm/                        # Integración de LLM (agnóstica de proveedor)
│   │   ├── __init__.py
│   │   ├── client.py               # wrapper de AsyncOpenAI, lee variables de entorno
│   │   ├── prompts/                # Plantillas de prompt como .py o .txt
│   │   │   ├── tutor_system.py
│   │   │   ├── admin_system.py
│   │   │   ├── grading.py          # Prompts de evaluación de ejercicios
│   │   │   └── generation.py       # Prompts de generación de curso/manual
│   │   └── embedding.py            # Servicio de embeddings (API o modelo local)
│   │
│   ├── agents/                     # Definiciones de agentes LangGraph (diferido — Fase 2+)
│   │   ├── __init__.py
│   │   ├── content_agent.py        # Pipeline de generación multipaso
│   │   └── tutor_agent.py          # Tutor conversacional RAG
│   │
│   └── core/                       # Utilidades compartidas
│       ├── __init__.py
│       ├── exceptions.py           # Clases de excepción propias de la app
│       ├── security.py             # Hash de contraseñas, config de cookies
│       └── pagination.py           # Ayudante de paginación por offset
│
├── tests/
│   ├── conftest.py                 # Fixtures: cliente async, BD de test, usuario de test
│   ├── factories.py                # Factorías de Factory Boy para datos de test
│   ├── test_auth.py
│   ├── test_users.py
│   ├── test_courses.py
│   ├── test_enrollments.py
│   ├── test_exercises.py
│   ├── test_skills.py
│   ├── test_chat.py
│   └── test_spaced_repetition.py
│
├── uploads/                        # Documentos subidos (montaje de volumen Docker)
└── Dockerfile
```

**Responsabilidades por capa:**

| Capa | Qué hace | Qué NO hace |
|-------|-------------|---------------------|
| **routes/** | Parsea HTTP, valida la entrada (Pydantic), llama al service, devuelve la respuesta | Lógica de negocio, consultas a la BD |
| **services/** | Reglas de negocio, orquestación, lógica de algoritmo | SQL, aspectos de HTTP |
| **repositories/** | Consultas SQL vía SQLAlchemy, devuelven instancias de modelo | Lógica de negocio, HTTP |
| **models/** | Mapeo ORM de tablas, relaciones | Lógica de negocio, validación |
| **schemas/** | Validación y serialización de petición/respuesta | Conocimiento de la BD |
| **deps/** | Inyectan recursos compartidos en los manejadores de ruta | Lógica de negocio |

**Flujo de datos:** `petición HTTP -> route -> service -> repository -> base de datos` y de vuelta. Cada capa solo habla con su vecino inmediato.

---

### 4.2 Endpoints de la API

Todos los endpoints con el prefijo `/api/v1`. Autenticación vía cookie de sesión en cada petición (excepto el login).

#### Auth

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `POST` | `/auth/login` | público | Email + contraseña. Establece la cookie de sesión httpOnly (caducidad de 7 días). Devuelve datos del usuario + rol |
| `POST` | `/auth/logout` | autenticado | Borra la sesión. Limpia la cookie |
| `GET` | `/auth/me` | autenticado | Devuelve el usuario actual (id, email, full_name, role, learning_profile, accessibility) más el `workspace_mode` del despliegue |

La respuesta del login redirige según el rol: empleado -> `/dashboard`, admin -> `/admin`. El frontend lee el rol desde `/auth/me` al cargar la página.

**Modo de espacio de trabajo.** `/auth/me` (y `/settings`) también llevan `workspace_mode`
(`organization` \| `individual`; ver [audience-modes.md](audience-modes.md)). En un
despliegue `individual` los endpoints colectivos, exclusivos de organización — empleados
(listar/crear/reiniciar), talento, `/stats`, asignación de cursos (`POST`/`DELETE
/enrollments`, asignación por carpeta) y el catálogo de skills — devuelven **404** vía la
dependencia `require_organization_workspace`: esos conceptos no existen en un
espacio de trabajo personal. Es un cumplimiento del lado del servidor; la SPA además oculta
las secciones como UX.

#### Usuarios

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/users` | admin | Lista todos los usuarios de la org. Admite `?search=`, `?role=`, `?is_active=`. Devuelve estadísticas resumidas (número de cursos activos, % de cobertura de skills) |
| `GET` | `/users/{id}` | admin | Detalle de un usuario con skills, inscripciones, actividad |
| `POST` | `/users/invite` | admin | Crea una cuenta de empleado. Cuerpo: `{email, full_name}`. Genera contraseña temporal o enlace de invitación |
| `POST` | `/users/invite/bulk` | admin | Subida de CSV (columnas name, email). Devuelve el número creado + errores |
| `PUT` | `/users/{id}` | admin | Actualiza el usuario (nombre, rol, is_active). El admin puede desactivar |
| `GET` | `/users/me` | autenticado | Perfil del usuario actual |
| `PUT` | `/users/me` | autenticado | Actualiza el propio perfil (full_name, learning_profile, accessibility). No puede cambiar el rol ni el email |
| `PUT` | `/users/me/password` | autenticado | Cambia la propia contraseña. Cuerpo: `{current_password, new_password}` |
| `GET` | `/users/me/today` | empleado | "Lo que toca hoy": repasos de repetición espaciada, próxima acción de curso, recomendación. Máximo 3 elementos |
| `GET` | `/users/me/skills` | empleado | Los propios niveles de skill agrupados por categoría |
| `GET` | `/users/me/activity` | empleado | Actividad reciente (intentos de ejercicio, lecciones completadas). Paginado, por defecto los últimos 20 |

#### Perfil del aprendiz (personalización)

Router `src/routes/learner_profile.py`, prefijo `/users/me/learner-profile`. Ver
[`personalization.md`](personalization.md).

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/users/me/learner-profile` | autenticado | Lee el perfil del aprendiz, incl. `learning_note` y `learning_preferences` |
| `PATCH` | `/users/me/learner-profile` | autenticado | Actualiza los campos editables incl. la nota libre `learning_note` (máx. 500 caracteres, normalizada; guía la forma, no los hechos). Escribirla elimina los pins de render de ese aprendiz |
| `DELETE` | `/users/me/learner-profile` | autenticado | Borra el perfil |

#### Artefactos multimedia

Router `src/routes/media.py`, prefijo `/media`. Ver [`media-artifacts.md`](media-artifacts.md).

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `POST` | `/media/artifacts` | generador | Encola un trabajo de medios. Cuerpo `MediaArtifactCreate` incl. `kind`, `scope` (`node\|course\|standalone`) y una `note` de personalización. Devuelve `202 {artifact_id, status}`. Permiso vía `can_generate_artifacts` |
| `GET` | `/media/artifacts` | autenticado | Lista artefactos. Query `course_id` (obligatorio), `node_id`, `include_nodes`. Tres formas: un nodo / todo el curso / solo a nivel de curso |
| `GET` | `/media/artifacts/{id}` | autenticado | Un artefacto |
| `GET` | `/media/artifacts/{id}/stream` | autenticado | SSE en el canal `media:{id}`: eventos `media_step` seguidos del terminal `media_done`/`media_error` |
| `GET` | `/media/artifacts/{id}/asset` | autenticado | Bytes del asset renderizado, o 404 |
| `GET` | `/media/artifacts/{id}/asset/{ref}` | autenticado | Un sub-asset por hash de contenido (`ref` debe ser un sha256 que liste la spec) |

#### Esquema de curso (flujo de creación)

Router `src/routes/course_schema.py`. Ciclo de vida del esquema de curso para el admin: proponer -> PUT (genera
packs) -> revisar -> validar -> precalentar. Ver [`create-course-flow`](create-course-flow.html)
y [`learning-experience-architecture.md`](learning-experience-architecture.md).

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `POST` | `/courses/{course_id}/schema/propose` | admin | `202` + `job_id`. Propone un borrador de esquema |
| `PUT` | `/courses/{course_id}/schema` | admin | Persiste el esquema editado; genera los knowledge packs (reintento acotado `max_attempts=3`); subir `schema_version` reemplaza cualquier ejecución en curso de una versión anterior |
| `POST` | `/courses/{course_id}/schema/review` | admin | Marca en bloque todos los nodos no archivados como revisados por humano (el asistente lo llama justo antes de validar) |
| `POST` | `/courses/{course_id}/schema/nodes/{node_id}/review` | admin | Marca un nodo como revisado. `reviewed_at` es una precondición para servir; el render devuelve `409 node_not_reviewed` en caso contrario |
| `POST` | `/courses/{course_id}/schema/validate` | admin | Valida el esquema; al confirmarse genera en segundo plano el precalentamiento de los renders compartidos de los primeros nodos |

#### Documentos

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/documents` | admin | Lista los documentos subidos. Admite el filtro `?status=` |
| `POST` | `/documents` | admin | Sube un fichero (multipart/form-data). Guarda en disco, crea el registro en BD con status=`pending` |
| `GET` | `/documents/{id}` | admin | Metadatos del documento + estado de procesamiento |
| `DELETE` | `/documents/{id}` | admin | Borra el documento y sus chunks (CASCADE) |
| `POST` | `/documents/{id}/process` | admin | Dispara el pipeline de ingesta: parsear, trocear, generar embeddings. Actualiza el estado pasando por `processing` -> `ready` o `error` |

#### Cursos

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/courses` | admin | Lista todos los cursos. Admite `?status=draft,published,archived` |
| `POST` | `/courses` | admin | Crea un armazón de curso vacío. Cuerpo: `{title, description, outcome, source_document_id?}` |
| `GET` | `/courses/{id}` | autenticado | Curso completo con módulos, lecciones, ejercicios (anidados). El empleado solo lo ve si está inscrito |
| `PUT` | `/courses/{id}` | admin | Actualiza los metadatos del curso (título, descripción, outcome) |
| `DELETE` | `/courses/{id}` | admin | Borra el curso (solo si status=`draft` y sin inscripciones) |
| `POST` | `/courses/{id}/generate` | admin | Dispara la generación por IA a partir del documento fuente. Crea un generation_job. Devuelve job_id para hacer polling |
| `POST` | `/courses/{id}/publish` | admin | Fija status=`published`. Valida: título, outcome, al menos 1 módulo con 1 lección |
| `POST` | `/courses/{id}/archive` | admin | Fija status=`archived`. Las inscripciones activas se marcan como completadas |

#### Módulos

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/courses/{course_id}/modules` | autenticado | Lista los módulos del curso, ordenados por posición |
| `POST` | `/courses/{course_id}/modules` | admin | Crea un módulo. Cuerpo: `{title, summary, position}` |
| `PUT` | `/courses/{course_id}/modules/{id}` | admin | Actualiza el módulo (title, summary, position) |
| `DELETE` | `/courses/{course_id}/modules/{id}` | admin | Borra el módulo (CASCADE borra lecciones + ejercicios) |
| `PUT` | `/courses/{course_id}/modules/reorder` | admin | Reordenación en lote. Cuerpo: `{module_ids: [uuid, uuid, ...]}` |

#### Lecciones

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/courses/{course_id}/modules/{module_id}/lessons` | autenticado | Lista las lecciones del módulo, ordenadas por posición |
| `POST` | `/courses/{course_id}/modules/{module_id}/lessons` | admin | Crea una lección. Cuerpo: `{title, content, position}` |
| `PUT` | `/courses/{course_id}/modules/{module_id}/lessons/{id}` | admin | Actualiza la lección |
| `DELETE` | `/courses/{course_id}/modules/{module_id}/lessons/{id}` | admin | Borra la lección (CASCADE borra ejercicios) |

#### Ejercicios

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/courses/{cid}/modules/{mid}/lessons/{lid}/exercises` | autenticado | Lista los ejercicios de la lección |
| `POST` | `/courses/{cid}/modules/{mid}/lessons/{lid}/exercises` | admin | Crea un ejercicio. Cuerpo: `{type, content, position}` |
| `PUT` | `/exercises/{id}` | admin | Actualiza el contenido o tipo del ejercicio |
| `DELETE` | `/exercises/{id}` | admin | Borra el ejercicio |
| `POST` | `/exercises/{id}/attempt` | empleado | Envía la respuesta. El cuerpo varía según el tipo (ver abajo). Devuelve `{score, passed, feedback, explanation}` |
| `GET` | `/exercises/{id}/attempts` | autenticado | Historial de intentos de este ejercicio del usuario actual. El admin puede añadir `?user_id=` para ver el de cualquier usuario |

**Cuerpo de la petición de intento según el tipo de ejercicio:**

```
test:           { "selected": 1 }
true_false:     { "answer": true }
fill_blank:     { "answers": ["unused", "tags"] }
order_steps:    { "order": [0, 2, 1, 3] }
practical_case: { "response": "I would explain the 30-day policy..." }
dialogue:       { "messages": [{"role": "user", "content": "..."}] }
```

Para `test`, `true_false`, `fill_blank`, `order_steps`: el servidor califica de forma determinista (compara contra la respuesta correcta en el contenido del ejercicio).

Para `practical_case`: el servidor envía la respuesta + la rúbrica al LLM para su evaluación. Devuelve una puntuación + feedback por criterio.

Para `dialogue`: el servidor ejecuta una conversación multiturno vía LLM con el system_prompt del contenido del ejercicio. Evaluación al alcanzar `max_turns`.

#### Inscripciones

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/enrollments` | autenticado | Empleado: sus propias inscripciones. Admin: todas las inscripciones. Admite `?status=`, `?user_id=` (admin), `?course_id=` |
| `POST` | `/enrollments` | admin | Asigna el curso a uno o varios usuarios. Cuerpo: `{user_ids: [uuid], course_id, deadline?}` |
| `GET` | `/enrollments/{id}` | autenticado | Detalle de la inscripción con progreso: módulos completados, posición actual, puntuación |
| `DELETE` | `/enrollments/{id}` | admin | Elimina la inscripción (solo si status=`assigned`, sin empezar) |
| `POST` | `/enrollments/{id}/complete` | sistema | Marca la inscripción como completada. Se dispara automáticamente cuando todos los módulos están hechos. Actualiza score, completed_at |

Cálculo del progreso: `módulos_completados / módulos_totales`. Un módulo está completo cuando todos los ejercicios de sus lecciones tienen al menos un intento aprobado.

#### Skills

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/skills/categories` | admin | Lista las categorías de skill con sus skills |
| `POST` | `/skills/categories` | admin | Crea una categoría. Cuerpo: `{name, position}` |
| `PUT` | `/skills/categories/{id}` | admin | Actualiza la categoría (name, position) |
| `DELETE` | `/skills/categories/{id}` | admin | Borra la categoría (solo si no tiene skills asignadas) |
| `GET` | `/skills` | admin | Lista todas las skills. Admite `?category_id=` |
| `POST` | `/skills` | admin | Crea una skill. Cuerpo: `{name, description, category_id?}` |
| `PUT` | `/skills/{id}` | admin | Actualiza la skill |
| `DELETE` | `/skills/{id}` | admin | Borra la skill (solo si ningún user_skill ni checkpoint la referencia) |
| `GET` | `/skills/matrix` | admin | Matriz completa de skills: filas=empleados, columnas=skills, celdas=nivel. Admite el filtro `?category_id=` |
| `GET` | `/skills/mentorship-suggestions` | admin | Pares detectados automáticamente: usuario con nivel alto + usuario con nivel bajo en la misma skill |
| `POST` | `/skills/verify` | admin | Verifica manualmente una skill. Cuerpo: `{user_id, skill_id, level, verifier_id?}`. Fija source=`manual` |
| `GET` | `/skills/{id}/users` | admin | Usuarios que tienen esta skill y sus niveles |
| `GET` | `/skills/gaps` | admin | Skills en las que nadie (o muy pocos) tiene nivel alto. Cuerpo: `?threshold=` para la cobertura mínima |

#### Checkpoints de skill

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/courses/{course_id}/checkpoints` | admin | Lista los checkpoints de skill del curso |
| `POST` | `/courses/{course_id}/checkpoints` | admin | Crea un checkpoint. Cuerpo: `{skill_id, module_id, target_level}` |
| `PUT` | `/courses/{course_id}/checkpoints/{id}` | admin | Actualiza el checkpoint |
| `DELETE` | `/courses/{course_id}/checkpoints/{id}` | admin | Borra el checkpoint |

Cuando se completa un módulo, el sistema comprueba los checkpoints y actualiza `user_skills` en consecuencia. El nivel nunca baja por los checkpoints (solo una anulación manual del admin puede bajarlo).

#### Chat (SSE)

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `POST` | `/chat` | empleado | Envía un mensaje al tutor. Cuerpo: `{message, context?: {course_id?, lesson_id?}}`. Devuelve un stream SSE |
| `POST` | `/chat/admin` | admin | Envía un mensaje al asistente de admin. Cuerpo: `{message}`. Devuelve un stream SSE |
| `GET` | `/chat/sessions` | autenticado | Lista las sesiones de chat del usuario actual. Paginado. Devuelve `{id, title, created_at, last_message_at}` |
| `GET` | `/chat/sessions/{id}/messages` | autenticado | Obtiene los mensajes de una sesión. Paginado. Devuelve `[{role, content, created_at, citations?}]` |
| `DELETE` | `/chat/sessions/{id}` | autenticado | Borra una sesión de chat y sus mensajes |

**Protocolo SSE:**

1. El cliente envía `POST /chat` con el cuerpo del mensaje
2. El servidor devuelve `Content-Type: text/event-stream`
3. El servidor emite eventos:

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

El chat del tutor usa RAG: la consulta se convierte a embedding, se recuperan los top-k chunks de `document_chunks`, y se incluyen en el contexto del LLM junto con el contexto del curso/lección actual del empleado.

El chat de admin tiene acceso a los datos de toda la organización (empleados, skills, inscripciones) para consultas operativas.

#### Manuales

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/manuals` | autenticado | Empleado: manuales de los cursos inscritos + manuales independientes publicados. Admin: todos los manuales |
| `POST` | `/manuals` | admin | Crea un manual. Cuerpo: `{title, content, source_document_id?, course_id?}` |
| `GET` | `/manuals/{id}` | autenticado | Contenido completo del manual. El empleado debe tener acceso (inscrito en el curso vinculado, o el manual es independiente + publicado) |
| `PUT` | `/manuals/{id}` | admin | Actualiza el contenido del manual |
| `DELETE` | `/manuals/{id}` | admin | Borra el manual (solo si status=`draft`) |
| `POST` | `/manuals/{id}/publish` | admin | Publica el manual |
| `GET` | `/manuals/{id}/search` | autenticado | Busca dentro del contenido del manual. Parámetro de query: `?q=` |

#### Repetición espaciada

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/spaced-repetition/due` | empleado | Ejercicios pendientes de repaso. Devuelve un máximo de 5, ordenados por urgencia (los más atrasados primero) |
| `POST` | `/spaced-repetition/review` | empleado | Envía la respuesta del repaso. Cuerpo: `{exercise_id, answer}`. Califica la respuesta, actualiza la vida media, programa el siguiente repaso |
| `GET` | `/spaced-repetition/stats` | empleado | Estadísticas de repaso: total de repasos, racha, próxima fecha de repaso |

El algoritmo HLR se ejecuta al enviar:
- Correcto: `half_life *= 2`, `review_count += 1`
- Incorrecto: `half_life /= 2`, `review_count += 1`
- `next_review_at` = ahora + tiempo hasta que `P(olvido) > 0.3`

#### Trabajos de generación

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/generation-jobs` | admin | Lista los trabajos de generación. Admite `?status=` |
| `GET` | `/generation-jobs/{id}` | admin | Detalle del trabajo con el paso actual, timestamps, mensaje de error si falló |
| `POST` | `/generation-jobs/{id}/retry` | admin | Reintenta un trabajo fallido desde el último paso exitoso |
| `DELETE` | `/generation-jobs/{id}` | admin | Cancela un trabajo pendiente/en ejecución |
| `GET` | `/generation-jobs/{id}/review` | admin | Obtiene los datos de revisión pendientes (contenido generado a la espera de aprobación) |
| `POST` | `/generation-jobs/{id}/review` | admin | Envía la decisión de revisión. Cuerpo: `{action: "approve"|"reject", feedback?}` |
| `GET` | `/generation-jobs/{id}/progress` | admin | Stream SSE de eventos de progreso de generación en tiempo real |
| `PUT` | `/generation-jobs/{id}/content` | admin | Edición de contenido en línea. Cuerpo: `{modules: [...]}`. Actualiza el contenido generado antes de la aprobación |
| `POST` | `/generation-jobs/{id}/regenerate-module/{idx}` | admin | Regenera un solo módulo por índice. Cuerpo: `{feedback?}` |

**Pasos del pipeline de generación:** `pending` -> `extracting` -> `structuring` -> `generating` -> `reviewing` -> `published` o `failed`.

Cada paso actualiza el estado del trabajo. El frontend hace polling a `GET /generation-jobs/{id}` para mostrar el progreso.

#### Feedback de curso

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `POST` | `/courses/{id}/feedback` | empleado | Envía el feedback posterior al curso. Cuerpo: `{hardest_section, free_text, difficulty: "easy"|"ok"|"hard"}`. Uno por usuario y curso |
| `GET` | `/courses/{id}/feedback` | admin | Todo el feedback del curso. Devuelve las respuestas individuales + un informe agregado |
| `GET` | `/courses/{id}/feedback/report` | admin | Informe de revisión generado por IA: secciones problemáticas, citas de usuarios, estadísticas de dificultad, cambios sugeridos |

#### Estadísticas y alertas

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/stats` | admin | Resumen del dashboard: total de empleados, cursos activos, número de brechas críticas, empleados que necesitan atención |
| `GET` | `/alerts` | admin | Alertas activas (máx. 10). Tipos: fecha límite próxima con 0% de progreso, fallos consecutivos (3+), certificado por caducar, nuevo empleado sin cursos, decaimiento de skill |

Cada alerta incluye:
```json
{
  "type": "deadline_risk",
  "severity": "high",
  "message": "Carlos has 0% progress on 'Returns' — deadline in 3 days",
  "action_url": "/admin/users/{user_id}",
  "related_ids": {"user_id": "...", "enrollment_id": "..."}
}
```

Las alertas se calculan por petición (no se almacenan). El servicio consulta las inscripciones, los intentos y la repetición espaciada para detectar las condiciones.

#### Ajustes de la organización

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/settings` | admin | Ajustes actuales de la org (nombre, flag de autorregistro, estado de la config de LLM) |
| `PUT` | `/settings` | admin | Actualiza los ajustes de la org. Cuerpo: `{name?, self_registration_enabled?}` |
| `PUT` | `/settings/llm` | admin | Actualiza la config de LLM. Cuerpo: `{base_url, api_key, model}`. Valida la conexión antes de guardar |
| `POST` | `/settings/llm/test` | admin | Prueba la conexión al LLM sin guardar. Devuelve éxito/error |

#### Usuarios — Invitaciones

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/users/invitations` | admin | Lista las invitaciones pendientes. Admite `?status=pending,accepted,expired` |

#### Health

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/health` | público | Comprobación de salud del sistema. Devuelve `{status: "ok", version, database: "connected"|"error"}` |

#### Admin — Trabajos en segundo plano

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `GET` | `/admin/jobs` | admin | Lista los trabajos en segundo plano. Admite `?status=`, `?type=`. Devuelve `{id, type, status, started_at, completed_at, error?}` |

Los ajustes de LLM se almacenan en el jsonb `organizations.settings`. Las variables de entorno (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`) son los valores por defecto; los ajustes a nivel de organización las sobrescriben.

---

### 4.3 Inyección de dependencias

El sistema `Depends()` de FastAPI proporciona recursos compartidos a los manejadores de ruta. Todas las dependencias se definen en `src/deps/`.

#### Sesión de base de datos

```python
# src/deps/db.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from src.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session

# Alias de tipo para las firmas de las rutas
DBSession = Annotated[AsyncSession, Depends(get_async_session)]
```

#### Usuario actual (a partir de la cookie de sesión)

fastapi-users proporciona el backend de cookie de sesión. La cadena de dependencias extrae el usuario de la cookie automáticamente.

```python
# src/deps/auth.py
from fastapi_users import FastAPIUsers
from src.auth.backend import auth_backend
from src.auth.manager import get_user_manager
from src.models.user import User

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# Dependencias base (proporcionadas por fastapi-users)
current_user = fastapi_users.current_user(active=True)
current_optional_user = fastapi_users.current_user(active=True, optional=True)

# Alias de tipo
CurrentUser = Annotated[User, Depends(current_user)]
```

#### Acceso basado en roles

```python
# src/deps/auth.py (continuación)
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

# Alias de tipo para las firmas de las rutas
AdminUser = Annotated[User, Depends(require_admin)]
EmployeeUser = Annotated[User, Depends(require_employee)]
```

Uso en las rutas:

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
    # Ambos roles pueden acceder, pero el empleado solo lo ve si está inscrito
    ...
```

#### Cliente LLM

```python
# src/deps/llm.py
from openai import AsyncOpenAI
from src.config import settings

async def get_llm_client(db: DBSession) -> AsyncOpenAI:
    """Devuelve un cliente AsyncOpenAI configurado a partir de los ajustes de la org o de las variables de entorno."""
    # Primero comprueba si hay una anulación a nivel de organización
    org = await db.execute(select(Organization).limit(1))
    org_settings = org.scalar_one().settings

    base_url = org_settings.get("llm_base_url") or settings.LLM_BASE_URL
    api_key = org_settings.get("llm_api_key") or settings.LLM_API_KEY

    return AsyncOpenAI(base_url=base_url, api_key=api_key)

LLMClient = Annotated[AsyncOpenAI, Depends(get_llm_client)]
```

El cliente `AsyncOpenAI` funciona con cualquier API compatible con OpenAI. El nombre del modelo se resuelve de forma similar (ajuste de la org > variable de entorno) y se pasa por llamada, no al crear el cliente.

#### Servicio de embeddings

```python
# src/deps/embedding.py
from src.llm.embedding import EmbeddingService

async def get_embedding_service(db: DBSession) -> EmbeddingService:
    """Devuelve el servicio de embeddings (basado en API o modelo local)."""
    org = await db.execute(select(Organization).limit(1))
    org_settings = org.scalar_one().settings

    return EmbeddingService(
        base_url=org_settings.get("embedding_base_url") or settings.EMBEDDING_BASE_URL,
        api_key=org_settings.get("embedding_api_key") or settings.EMBEDDING_API_KEY,
        model=org_settings.get("embedding_model") or settings.EMBEDDING_MODEL,
    )

EmbeddingSvc = Annotated[EmbeddingService, Depends(get_embedding_service)]
```

#### Ejemplo de composición de dependencias

Un manejador de ruta compone lo que necesita:

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

Los services reciben sus dependencias por inyección de constructor (desde el manejador de ruta), no a través de estado global.

---

### 4.4 Manejo de errores

#### Formato de respuesta de error

Cada error devuelve la misma forma JSON:

```json
{
  "detail": "Course not found",
  "code": "NOT_FOUND",
  "field": null
}
```

Para errores de validación (422):

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

#### Excepciones de la aplicación

```python
# src/core/exceptions.py
class AppError(Exception):
    """Error base de la aplicación."""
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

#### Manejador global de excepciones

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

#### Uso de códigos de estado HTTP

| Estado | Cuándo |
|--------|------|
| `200` | Éxito con cuerpo de respuesta |
| `201` | Recurso creado (POST que crea) |
| `204` | Éxito, sin cuerpo (DELETE) |
| `400` | Petición incorrecta (violación de regla de negocio: "Cannot delete published course") |
| `401` | No autenticado (sin cookie o sesión caducada) |
| `403` | Autenticado pero con el rol equivocado |
| `404` | Recurso no encontrado |
| `409` | Conflicto (email duplicado, la inscripción ya existe) |
| `413` | Fichero demasiado grande (subida de documento) |
| `422` | Error de validación (Pydantic) |
| `429` | Limitado por rate limit (futuro, para endpoints de LLM) |
| `502` | Error del proveedor de LLM (fallo aguas arriba) |

#### Enfoque de validación

1. Los **esquemas Pydantic** validan la forma y los tipos de la petición en la capa de ruta
2. La **capa de service** valida las reglas de negocio (p. ej., "el curso debe tener al menos 1 módulo para publicarse")
3. Las **restricciones de la base de datos** son la última línea de defensa (unique, FK, check constraints)

Los services lanzan subclases de `AppError`. Las routes nunca capturan excepciones — lo hace el manejador global.

---

### 4.5 Capa de acceso a la base de datos

#### Configuración del motor y la sesión

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
    expire_on_commit=False,     # Evita problemas de lazy-load tras el commit
)
```

#### Modelo base

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

#### Ejemplo de modelo

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

    # Relaciones
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

#### Patrón repositorio

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

#### Ejemplo de repositorio especializado

```python
# src/repositories/skill_repo.py
class SkillRepository(BaseRepository[Skill]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Skill)

    async def get_matrix(self, org_id: uuid.UUID, category_id: uuid.UUID | None = None):
        """Devuelve la matriz completa de skills: [{user, skill, level}, ...]"""
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
        """Encuentra pares de skill alto-bajo para mentoría."""
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

#### Búsqueda vectorial (chunks de documento)

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
        """Búsqueda semántica en todos los documentos de la org."""
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

#### Gestión de la sesión en las rutas

Las rutas obtienen una sesión de `Depends`, instancian repositories y services, y la sesión hace auto-commit o rollback:

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

La llamada a `commit()` está en el manejador de ruta, no en el repository ni en el service. Esto mantiene la frontera transaccional visible y explícita. Si algo lanza una excepción antes del commit, la sesión hace rollback automáticamente al salir del context manager.

#### Resumen del mapeo modelo-tabla

| Clase de modelo | Tabla | Relaciones clave |
|-------------|-------|-------------------|
| `Organization` | `organizations` | Tiene muchos: users, documents, skills, courses |
| `User` | `users` | Pertenece a: organization. Tiene muchos: enrollments, attempts, user_skills |
| `Document` | `documents` | Pertenece a: organization, usuario uploaded_by. Tiene muchos: chunks |
| `DocumentChunk` | `document_chunks` | Pertenece a: document. Tiene: vector de embedding(384) |
| `SkillCategory` | `skill_categories` | Pertenece a: organization. Tiene muchos: skills |
| `Skill` | `skills` | Pertenece a: organization, category. Tiene muchos: user_skills, checkpoints |
| `Course` | `courses` | Pertenece a: organization, usuario created_by, documento fuente. Tiene muchos: modules, enrollments, checkpoints. Tiene uno: manual |
| `Module` | `modules` | Pertenece a: course. Tiene muchos: lessons |
| `Lesson` | `lessons` | Pertenece a: module. Tiene muchos: exercises |
| `Exercise` | `exercises` | Pertenece a: lesson. Tiene muchos: attempts, entradas de spaced_repetition |
| `SkillCheckpoint` | `skill_checkpoints` | Pertenece a: course, skill, module |
| `Manual` | `manuals` | Pertenece a: organization, usuario created_by, documento fuente, course (opcional) |
| `Enrollment` | `enrollments` | Pertenece a: user, course, usuario assigned_by |
| `ExerciseAttempt` | `exercise_attempts` | Pertenece a: user, exercise |
| `UserSkill` | `user_skills` | Pertenece a: user, skill |
| `SpacedRepetition` | `spaced_repetition` | Pertenece a: user, exercise |
| `GenerationJob` | `generation_jobs` | Pertenece a: organization, usuario triggered_by, documento fuente. Enlaza con: course resultante, manual resultante |
| `CourseFeedback` | `course_feedback` | Pertenece a: user, course |
| `ChatSession` | `chat_sessions` | Pertenece a: user. Tiene muchos: chat_messages |
| `ChatMessage` | `chat_messages` | Pertenece a: chat_session |
| `BackgroundJob` | `background_jobs` | Pertenece a: organization. Registra la ejecución de tareas asíncronas |
| `UserSession` | `user_sessions` | Pertenece a: user. Registra las sesiones de autenticación activas |
| `AuditLog` | `audit_logs` | Pertenece a: user, organization. Registra las acciones de admin |
| `ApiKey` | `api_keys` | Pertenece a: organization. Gestión de claves de API |
| `Webhook` | `webhooks` | Pertenece a: organization. Tiene muchos: webhook_deliveries |
| `WebhookDelivery` | `webhook_deliveries` | Pertenece a: webhook. Registra los intentos de entrega |

#### Migraciones

Alembic con soporte async. Una migración por cambio de esquema.

```bash
# Generar migración a partir de cambios en los modelos
uv run alembic revision --autogenerate -m "add_courses_table"

# Aplicar migraciones
uv run alembic upgrade head

# Deshacer
uv run alembic downgrade -1
```

La migración inicial crea las 27 tablas + enums + índices + extensiones (`pgcrypto`, `vector`).

---

### 4.6 Configuración

```python
# src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Base de datos
    DATABASE_URL: str = "postgresql+asyncpg://skillnet:skillnet@localhost:5432/skillnet"

    # Auth
    SECRET_KEY: str                       # Obligatorio, sin valor por defecto
    SESSION_LIFETIME_SECONDS: int = 604800    # 7 días
    COOKIE_NAME: str = "skillnet_session"
    COOKIE_SECURE: bool = True                # Ponlo a False para desarrollo local sin HTTPS

    # LLM (por defecto, sobrescribible por org)
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    # Embeddings
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "multilingual-e5-small"
    EMBEDDING_DIMENSIONS: int = 384

    # Subidas de ficheros
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # App
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

---

### 4.7 Factoría de la aplicación

```python
# src/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Arranque: crea el directorio de subidas, verifica la conexión a la BD
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    yield
    # Apagado: libera el motor
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
        allow_credentials=True,        # Necesario para las cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registra los manejadores de excepciones
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    # Monta los routers bajo /api/v1
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

### 4.8 Decisiones de diseño clave

| Decisión | Justificación |
|----------|-----------|
| **Un repository por dominio, no por tabla** | `SkillRepository` gestiona `skills`, `skill_categories`, `user_skills`, y las consultas de la matriz. Evita 23 repos diminutos |
| **Sin abstracción de unit of work** | `db.commit()` en el manejador de ruta es suficientemente explícito para esta escala. Añadir UoW suma indirección sin beneficio |
| **Los services reciben sus dependencias por constructor** | El manejador de ruta crea `CourseService(repo)` — sin service locator, sin estado global. Fácil de testear con dobles |
| **El commit va en la ruta, no en el service** | La frontera transaccional es visible. Los métodos de service son componibles (una ruta puede llamar a varios métodos de service en una sola transacción) |
| **Sin cola de tareas en segundo plano para el MVP** | Los trabajos de generación corren en el mismo proceso con `asyncio.create_task()`. Si una petición dispara una generación, arranca la tarea y devuelve el job_id de inmediato. El cliente hace polling del estado. Celery/Dramatiq se difieren hasta que hagan falta |
| **Las alertas se calculan por petición** | Sin tabla de alertas, sin cron. `AlertService.get_alerts()` ejecuta consultas contra los datos de enrollment/attempt/spaced_repetition. A escala de MVP (decenas de empleados), esto es instantáneo |
| **Ficheros de ruta planos, no routers anidados** | `modules.py` gestiona `/courses/{cid}/modules/...` directamente. El anidamiento está en la URL, no en la estructura del código. Mantiene los imports simples |
| **SSE sobre WebSocket** | El streaming unidireccional es todo lo que necesitamos. SSE se reconecta automáticamente, funciona con proxies, no necesita ninguna librería del lado del cliente |
| **Los esquemas Pydantic separados de los modelos ORM** | Los modelos ORM mapean tablas. Los esquemas definen los contratos de la API. Se parecen pero evolucionan de forma independiente (p. ej., `CourseRead` excluye campos internos, añade el `module_count` calculado) |
