# v2 — Cursos dinámicos

> **Estado: spec de implementación. Rama `feat/dynamic-courses`.**
>
> Prioridad documental: `v1-scope.md` sigue siendo la verdad **del camino v1**. Este documento
> define el camino v2 y **sólo** aplica cuando el feature flag está activo. Donde este documento
> contradice a `architecture.md`, `content-generation.md` o `screens.md`, gana este documento
> para el camino v2; el camino v1 no se toca.
>
> Requisito duro: **el camino estático de v1 debe seguir funcionando** para cualquier curso que
> no haya optado por v2. Ningún cambio de este documento puede alterar el comportamiento de
> `GET /api/v1/courses/{id}`, del pipeline `build_content_graph()` ni del render markdown
> existente para un curso cuyo `delivery_mode` no sea `dynamic` (ver §10).
>
> **Arquitectura episódica vigente:** la separación entre constitución persistida del curso,
> `EpisodeBrief` generado on-the-fly, selección neutral de capacidades, `LearningExperience` y
> evidencia server-owned se especifica en
> [`learning-experience-architecture.md`](learning-experience-architecture.md). Este documento sigue
> describiendo persistencia, entrega y compatibilidad del runtime v2. Las secciones que prescriben
> `ScreenScheme`, una fórmula fija de pantalla o agrupación por pasos aplican sólo al fallback
> `legacy_stepper`; no restringen el camino `episode`. `shell_mode` lo decide el servidor. La
> migración conserva `src.services.course_delivery.resolve_delivery` como único selector v1/v2.

---

## 1. Objetivo y alcance

### 1.1 El cambio

Hoy un curso se genera "del tirón": el admin sube un documento, un grafo LangGraph de 7 nodos
escribe todo el curso en Markdown, y todos los empleados leen exactamente el mismo texto.

v2 parte la generación en dos tiempos:

| Tiempo | Quién | Qué produce | Cuándo |
|--------|-------|-------------|--------|
| **Design-time** | Admin/creador | Un **esquema**: título, outcome y una lista de **nodos** (competencias) con criticidad, prerrequisitos y fuente asociada. **Cero contenido.** | Al crear el curso |
| **Runtime** | Sistema, por empleado | Para cada nodo NO dominado: un **UI spec** generado al vuelo desde el nodo + el perfil del aprendiz + la fuente | Cuando el empleado abre el nodo |

Entre los dos tiempos hay un **gate humano bloqueante**: el creador valida el esquema. Sin
`schema_status = 'validated'` no se genera nada para ningún empleado.

### 1.2 Entra en este PR (vertical slice completo)

1. **Esquema de curso** — tabla de nodos con criticidad y prerrequisitos, generación del esquema
   propuesto por LLM, edición por el creador, validación bloqueante.
2. **Onboarding** — 4 preguntas + 1 opcional, ≤90 s, que siembran el perfil del aprendiz.
3. **Perfil del aprendiz** — perfil declarado (rol, objetivo, experiencia, preset), vector implícito
   de formato, estado por nodo (maestría, rachas, tipo de último error).
4. **Pre-assessment por nodo** — 2 ítems + desempate, con una regla de maestría computable y
   umbral por criticidad.
5. **Generación on-the-fly por nodo** — grafo LangGraph nuevo (`decide_formato` → `genera_ui` →
   `validate_ui` → `persist_render`), con router de dos niveles de modelo.
6. **Capa de render con adaptador** — una IR canónica (`ui_spec` jsonb) + **un** backend de dialecto,
   **OpenUI Lang**, detrás de un `Protocol` con registro. El seam del adaptador entra; el segundo
   dialecto **no** (ver §1.3 y §5.4).
7. **Ajuste del perfil** — servicio determinista que actualiza maestría, vector y notas del tutor
   tras cada respuesta.
8. **Clic-para-explicar (Curio)** — cualquier palabra o selección dentro de un nodo abre una
   explicación contextual en línea, con caché de servidor.
9. **Latencia** — skeleton, espera productiva solapada con el pre-assessment, streaming SSE de
   bloques, caché por bucket de perfil.
10. **Migraciones Alembic** (`0005`), tests con fixtures grabadas, y esta documentación.

### 1.3 NO entra (backlog explícito, no "TBD")

| Fuera | Motivo |
|-------|--------|
| `SandboxHTML` / HTML libre generado por el LLM | Vector XSS directo y 12-65 % del código generado con vulnerabilidades. El patrón es `prompt → IR tipada → render nativo`. Se reevalúa cuando exista sandbox de iframe auditado |
| Componente `Simulation` (parámetros ajustables) | Requiere data-binding y ciclo de vida que la IR no tiene. El valor `simulation` existe en el enum `ui_format` reservado, pero `decide_formato` no lo emite (constante `ALLOWED_UI_FORMATS`) |
| Repetición espaciada (HLR o FSRS) | **Corrección de premisa:** no existe hoy. `spaced_repetition`/HLR aparece en `data-model.md`, `product.md` y `background-processing.md`, pero **no hay tabla ni módulo en el repo** (verificado: 20 tablas, ningún `half_life`/`next_review` en `src/`). Este PR no lo introduce. Consecuencia directa: el estado `needs_review` **no** lo produce ningún scheduler — su único productor en este PR es el tope de pistas (§7.4) |
| Segundo backend de dialecto (`a2tl`) | El formato `UIDL/1` de `packages/a2tl-web` es una **lista plana de secciones sin ids ni `children`** (`parser.ts:11-21`) y no tiene primitiva para `QuizItem`, `Stack`, `Card` ni `Callout`. No puede representar la `UISpec` de §5.2, así que el round-trip y el reintento cruzado son imposibles para cualquier spec con ejercicio o contenedores anidados. Entra el `Protocol` + el registro (el seam), no el segundo dialecto. Backlog: si hace falta, será un dialecto **propio de SkillNet**, no el de ese paquete |
| Tabla `background_jobs` / worker de purga | No existe (verificado). La purga de `learning_events` y `term_explanations` es un **script CLI** (`python -m src.scripts.purge_learning_data`), documentado y ejecutable a mano o por cron del host. Backlog: convertirlo en job real |
| Fine-tuning QLoRA del DSL | Backlog |
| Descomposición paralela del router (8B esqueleto + 120B rellenos concurrentes) | Se implementa el router **a nivel de UI completa**. La descomposición por componente sólo tiene sentido con `SandboxHTML`, que está fuera |
| Migración destructiva de `modules`/`lessons`/`exercises` | Conviven. Las lecciones v1 son la **semilla** (`course_nodes.seed_lesson_id`) y el modo degradado |
| Click-to-locate editing (edición por diff sobre el DSL) | Backlog |
| Chat/tutor multi-turno dentro del nodo | El chat v1 sigue como está. El nodo sólo tiene clic-para-explicar |

### 1.4 Decisiones que este documento cierra

Estas contradicciones venían abiertas en la investigación. Se cierran así, y no se reabren dentro
de este PR:

| Cuestión | Decisión |
|----------|----------|
| Formato de salida del LLM | **IR tipada** (`ui_spec` jsonb, lista plana de componentes). El LLM emite el **dialecto** del backend activo; el adaptador lo parsea a la IR. Nunca HTML |
| Nodos vs módulos/lecciones | **Conviven.** `course_nodes` es la unidad de v2; `modules`/`lessons` son el camino v1 y la semilla |
| Dónde vive el contenido generado | Tabla nueva `node_renders`, cacheada por `cache_key`. **Se persiste** (coste). La auditoría **no** vive ahí: vive en `node_render_views` (§3.4) |
| Estabilidad del render dentro de un nodo | **Visión A: el render se fija.** `learner_node_states.active_render_id` ancla el spec desde que se abre el nodo hasta que el usuario pide explícitamente regenerar. Un refresco del navegador o un refetch de TanStack Query devuelve **el mismo** spec. La adaptación ocurre **entre** nodos y sesiones, nunca dentro de una pantalla abierta. Visión B (regeneración continua) queda fuera: exige bloqueo de layout, explicación del cambio y "ver la versión anterior", y nada de eso cabe en este PR |
| Experiencia declarada: ¿por curso o por persona? | **Por persona y sobre su propio puesto**, no sobre un curso concreto (la pregunta no nombra ningún curso). El ajuste por competencia lo aporta `user_skills` vía `course_nodes.skill_id` como prior del probe (§7.1), no la declaración |
| Log de eventos crudo | **Se persiste** `learning_events`, revirtiendo la idea previa de guardar sólo el vector agregado. Razón concreta: el decaimiento de §3.3 necesita `created_at` por evento, y el vector agregado no permite recalcularlo si cambian los pesos. Coste: una ventana de retención de 90 días y un script de purga |
| Dimensiones del `format_vector` | **Sólo las que el kit puede producir**: `texto`, `ejercicio`, `codigo`, `dato`. `diagrama`, `audio` y `recurso` se eliminan — no hay componente que los emita, así que serían dimensiones estructuralmente muertas |
| Neurotipos en `screens.md` | `screens.md` §Employee Settings ("optional: TEA, TDAH, dislexia flags", línea 213) **queda derogado** por la decisión de no almacenar neurotipo. Se corrige en el mismo `chore` de rutas (§14.2 #8), junto con `design-system.md` §Skeleton, que documenta `animate-pulse` mientras `motion-system.md:437,636` lo prohíbe |
| Escala de dominio primaria | **`mastery` real 0..1** por `(user, node)`, más un enum `node_state` derivado. Shu-Ha-Ri y Bloom son derivaciones, no estado primario |
| Escala de rating | La existente: `score` real 0..1 (igual que `exercise_attempts`). Sin Rating 1-4 |
| Preferencia de modalidad | El usuario puede pedir explícitamente imagen, audio, vídeo o texto cuando el kit los soporte. La preferencia declarada prevalece; `format_vector` queda como señal inferida secundaria. Véase [`adaptive-learning.md`](adaptive-learning.md) |
| Neurodivergencia | **No se almacena etiqueta de neurotipo** (dato de salud, art. 9 RGPD). Sólo ajustes de lectura neutros opt-in en `users.accessibility` |
| Naturaleza de la validación del creador | **Gate bloqueante** por estado en BD (`schema_status`), no `interrupt()` de LangGraph — sobrevive a reinicios del proceso |
| Provider LLM | litellm, provider-agnóstico. Los dos niveles del router son **purposes** (`runtime_fast`, `runtime_heavy`), no proveedores. Groq es un valor posible de env var, no una dependencia |
| Rutas del frontend | Se sigue la convención **ya implementada** en `App.tsx` (español). Corregir `screens.md` es un `chore` aparte |
| Adaptación de presentación | No se adapta hasta 3 nodos completados (periodo de calibración). Se adapta **qué** aparece, no **dónde** |

---

## 2. Arquitectura v2 — flujo completo

```
                              ══════════ DESIGN-TIME (admin) ══════════

  ┌───────────┐   POST /documents          ┌──────────────────┐
  │ documento │ ─────────────────────────► │  ingesta v1      │  (sin cambios)
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
                        │   (NUEVO, usa    (NUEVO, usa helpers      (NUEVO, LLM)│
                        │    helpers)       + prompt v1)              │         │
                        │                                             ▼         │
                        │                                     persist_schema    │
                        │                                       (NUEVO)         │
                        └───────────────────────────┬───────────────────────────┘
                                                    │ SSE: schema_step / schema_ready
                                                    │ canal generation:{job_id}
                                                    ▼
                                       courses.schema_status = 'proposed'
                                       course_nodes + course_node_prerequisites
                                       ⚠ CERO contenido generado
                                                    │
                       GET /courses/{id}/schema     │      PUT /courses/{id}/schema
                       (el creador lo lee)  ◄───────┼───────► (el creador lo edita)
                                                    │
                                                    ▼
                    ╔═══════════════════════════════════════════════════════╗
                    ║  GATE BLOQUEANTE                                      ║
                    ║  POST /courses/{id}/schema/validate                   ║
                    ║  valida: DAG acíclico · ≥1 nodo critical ·            ║
                    ║          todo nodo con summary y fuente ·             ║
                    ║          prereqs sin huérfanos                        ║
                    ║  ⇒ schema_status='validated', delivery_mode='dynamic' ║
                    ╚═══════════════════════════════╤═══════════════════════╝
                                                    │
                                    POST /enrollments (asignación, sin cambios)
                                                    │
                              ══════════ RUNTIME (empleado) ══════════
                                                    │
                                                    ▼
     primer login ──►  ┌────────────────────────────────────────────┐
                       │  ONBOARDING  (5 pantallas, ≤90 s)          │
                       │  GET /onboarding · POST /onboarding        │
                       │  rol · objetivo · experiencia · preset ·   │
                       │  ajustes de lectura (opcional)             │
                       └────────────────────┬───────────────────────┘
                                            │ siembra
                                            ▼
                       learner_profiles (role_title, goal,
                       experience_level, preset, format_vector=0)
                                            │
                                            ▼
                       GET /courses/{id}/nodes   (lista + estado + bloqueo por prereqs)
                                            │
                                            ▼
        ┌──────────────────── por cada nodo desbloqueado ─────────────────────┐
        │                                                                      │
        │   POST /nodes/{node_id}/probe        ┌─────────────────────────┐     │
        │   ──────────────────────────────────►│  PRE-ASSESSMENT         │     │
        │                                      │  item A (apply)         │     │
        │   POST /nodes/{node_id}/probe/answer │  item B (understand)    │     │
        │   ──────────────────────────────────►│  [+ desempate si duda]  │     │
        │                                      └───────────┬─────────────┘     │
        │                                                  │                   │
        │      ┌───────────────────────────────────────────┴───────┐           │
        │      │ mastery ≥ umbral(criticality)?                    │           │
        │      └────────┬──────────────────────────────┬───────────┘           │
        │            SÍ │                              │ NO                    │
        │               ▼                              ▼                       │
        │      node_state='mastered'      ╔═══════════════════════════════════╗│
        │      (se salta, 0 tokens)       ║ build_node_graph()                ║│
        │               │                 ║ [src/agents/runtime/graph.py]     ║│
        │               │                 ║                                   ║│
        │               │                 ║  load_context                     ║│
        │               │                 ║    (nodo + perfil + estado +      ║│
        │               │                 ║     fuente vía RAG/seed)          ║│
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
        │               │                 ║  genera_ui  (LLM tier del router) ║│
        │               │                 ║   → dialecto del backend activo   ║│
        │               │                 ║        │                          ║│
        │               │                 ║        ▼                          ║│
        │               │                 ║  validate_ui                      ║│
        │               │                 ║   adapter.parse() → UISpec        ║│
        │               │                 ║   ├ ok ──────────► persist_render ║│
        │               │                 ║   ├ inválido & retry<1 ─► genera_ui║│
        │               │                 ║   └ falla ──────► fallback_seed   ║│
        │               │                 ║                    (markdown v1)  ║│
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
        │               │                 │  envuelto en ClickableSurface     │ │
        │               │                 │                                   │ │
        │               │                 │  clic en palabra/selección ──────►│ │
        │               │                 │  POST /explain (SSE) ─► popover   │ │
        │               │                 └───────────────┬───────────────────┘ │
        │               │                                 │                     │
        │               │            POST /nodes/{id}/answer                    │
        │               │            POST /nodes/{id}/feedback                  │
        │               │                                 │                     │
        │               │                                 ▼                     │
        │               │                 ┌───────────────────────────────────┐ │
        │               │                 │  AJUSTE DE PERFIL (determinista)  │ │
        │               │                 │  [src/services/learner_profile_   │ │
        │               │                 │   service.py]                     │ │
        │               │                 │  · mastery ← EWMA(score)          │ │
        │               │                 │  · consecutive_correct/failed     │ │
        │               │                 │  · last_error_kind                │ │
        │               │                 │  · format_vector ← learning_events│ │
        │               │                 │  · tutor_notes (vocab controlado) │ │
        │               │                 └───────────────┬───────────────────┘ │
        │               │                                 │                     │
        │               └─────────────────────────────────┤                     │
        │                                                 ▼                     │
        │                                  siguiente nodo desbloqueado          │
        └──────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                       enrollments.status='completed' cuando todos los
                       nodos critical están en 'mastered'
```

### 2.1 Qué se persiste vs qué se genera

La preparación pedagógica asíncrona situada entre el índice y OpenUI se especifica en
[`node-knowledge-packs.md`](node-knowledge-packs.md). Tras el commit del índice genera un contrato
estructurado y un Markdown derivado por nodo. Solo los packs `ready` alimentan la selección de
conocimiento del runtime; su hash y el de la selección forman parte de la clave de caché. Los estados
`review_required`, `failed`, `stale` y la ausencia de pack mantienen el flujo raw anterior como
fallback. Crear o modificar el esquema encola automáticamente la preparación; abrir la pantalla no
inicia trabajo. Cada nodo expone su estado dentro de su propio desplegable en la pantalla de esquema;
los detalles técnicos no ocupan una sección global.

| Se persiste (design-time, estable) | Se genera al vuelo (runtime, por usuario) |
|------------------------------------|-------------------------------------------|
| Título y outcome del curso | La UI de cada nodo (`ui_spec`) |
| Nodos, summaries, criticidad, prerrequisitos | El texto explicativo adaptado |
| Documento fuente + headings asociados | Los ejemplos contextualizados al rol |
| Constitución: competencia, grounding, gates de evidencia y errores críticos | `EpisodeBrief`: misión, acción dominante, apoyo, límites y continuación |
| Perfil del aprendiz | Los ítems de ejercicio y del pre-assessment |
| Estado por nodo (maestría, rachas) | Las explicaciones de clic-para-explicar |
| El `ui_spec` **ya generado** (contenido, compartido por bucket) | — |
| Quién vio qué render y cuándo (`node_render_views`) | — |

La constitución y los packs no son una presentación precreada. No fijan secuencia, modalidad,
componente ni artefactos especulativos del curso; acotan la generación episódica y permiten auditarla.
Audio y vídeo, cuando resultan elegibles, se embeben en la misión: no crean pestañas de modalidad.

**Caché y auditoría son dos tablas, no una.** `node_renders` es **contenido org-scoped**: guarda el
`dialect` canónico que se sirvió (re-serializado desde la `UISpec`, **nunca** el texto crudo del
modelo), la `ui_spec` validada, el modelo usado y la procedencia (`catalog_version`,
`library_version`), y una misma fila la
comparten todos los empleados del mismo bucket de perfil. Por tanto **no** puede decir quién vio
qué: en un acierto de caché (el ~80 % que hace sostenible el coste) la fila no tiene nada que ver
con el empleado que la está leyendo.

Lo que sí lo dice es `node_render_views(user_id, render_id, first_seen_at)`: una fila fina escrita
en el primer `GET /nodes/{id}/render` de cada usuario. Un certificado se justifica uniendo
`node_attempts` → `node_render_views` → `node_renders`, y sobrevive al borrado de cualquier otro
usuario porque `node_renders.generated_by` es `NULL`-able con `ON DELETE SET NULL` (§3.4).

---

## 3. Modelo de datos

Todo lo nuevo va en **una** migración: `alembic/versions/0005_dynamic_courses.py`, con
`revision = "0005"` y `down_revision = "0004"` (head actual verificado: cadena lineal
`0001→0002→0003→0004`, sin ramas).

**Qué significa exactamente "downgrade probado"** — y qué no: PostgreSQL **no puede quitar un valor
de un enum**. `downgrade()` borra las 13 tablas nuevas, las 6 columnas de `courses` y los 8 enums
nuevos, pero **deja huérfanos `schema_proposing` y `schema_proposed` en el tipo `generation_step`**.
Es inocuo (ninguna fila los referencia después del downgrade, porque los jobs de esquema se borran
con las tablas nuevas… y si quedara alguno, `generation_service` ya cae a un valor conocido) y es
exactamente lo que asserta `tests/integration/test_migration_0005.py`: no un esquema byte a byte
idéntico, sino "todas las tablas y columnas nuevas fuera, los dos valores de enum dentro". Un
downgrade verdaderamente limpio exigiría recrear el tipo y reescribir `generation_jobs.status`; no
se hace, y esta línea es la razón documentada.

Convenciones respetadas de `data-model.md`: PK `uuid DEFAULT gen_random_uuid()`, `timestamptz`,
`jsonb` para lo flexible, `org_id` en tablas **top-level** (las hijas heredan el scoping del padre;
ver §15.4), enums nombrados en snake_case.

**Aislamiento tenant de matrículas.** Una matrícula tiene dos extremos —el aprendiz y el curso— y
ambos deben vivir en la misma organización. La creación (`EnrollmentService.assign` /
`assign_courses`) valida ahora que **todos** los `user_ids` pertenezcan a la org del admin, no solo el
curso; enrolar a un aprendiz de otra org devuelve `403`. El listado de “Mis cursos”
(`EnrollmentRepository.list_enrollments`) filtra por `User.org_id` **y** `Course.org_id`, de modo que
una fila cruzada preexistente no aparece —antes se mostraba su título y luego el detalle respondía
`404` (“Curso no encontrado”)—. La defensa se aplica en lectura y escritura sin borrar filas: una
matrícula inconsistente queda oculta, no eliminada. El detalle del curso ya filtraba por la org del
llamante y se mantiene.

> **Orden de creación en `0005`** — los bloques SQL de abajo están agrupados por tema, no en orden
> ejecutable. Hay dos referencias hacia adelante: `course_nodes.default_ui_format` necesita el enum
> `ui_format`, y `learner_node_states.active_render_id` necesita la tabla `node_renders`. Orden real:
> **todos los `CREATE TYPE` primero**, luego `course_nodes` → `course_node_prerequisites` →
> `node_renders` → `learner_node_states` → el resto → `node_render_views` (que referencia
> `node_renders` y `course_nodes`).

### 3.1 Cambios a tablas existentes

Todos con `DEFAULT`, todos aditivos. Ninguna columna existente se renombra ni se borra.

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

- `delivery_mode`: `'static'` = camino v1 intacto. `'dynamic'` = camino v2. Sólo lo pone
  `POST /courses/{id}/schema/validate`.
- `schema_version`: se incrementa en cada `PUT /courses/{id}/schema` que cambie nodos. Entra en la
  `cache_key`, así que editar el esquema invalida los renders derivados sin borrar filas.
- `intent_density`: el "slider de intención" condensado(1) ↔ expandido(5). Entra en el prompt de
  `genera_ui` como presupuesto de longitud, no como decisión de formato.

```sql
-- El paso 'schema' del pipeline de design-time
ALTER TYPE generation_step ADD VALUE IF NOT EXISTS 'schema_proposing' BEFORE 'extracting';
ALTER TYPE generation_step ADD VALUE IF NOT EXISTS 'schema_proposed'  AFTER 'reviewing';
```

> **Nota de implementación, corregida dos veces.** El despliegue es **pg16**
> (`docker-compose.yml`: `pgvector/pgvector:pg16`), donde `ALTER TYPE … ADD VALUE` **sí** funciona
> dentro de una transacción desde pg12. Lo único prohibido es **usar** el valor nuevo en la misma
> transacción — y la versión anterior de esta nota afirmaba que `0005` no lo hacía. **Era falso**:
> el paso 16 usa `schema_proposing`/`schema_proposed` en el predicado del índice parcial
> `uq_generation_jobs_schema_in_flight`, así que la tirada muere con
> `UnsafeNewEnumValueUsageError`. Lo descubrió la primera ejecución real de las suites de
> integración; hasta entonces nadie había hecho un `alembic upgrade head` desde cero.
>
> Corrección aplicada en el fichero: los dos `ALTER TYPE … ADD VALUE` se ejecutan dentro de
> `op.get_context().autocommit_block()`, y es el **único** de la migración. El coste de ese
> bloque sigue siendo el que la nota anterior quería evitar y hay que asumirlo con los ojos
> abiertos: `alembic/env.py` envuelve **toda** la tirada en un `context.begin_transaction()` sin
> `transaction_per_migration`, y `src/main.py` llama a `run_migrations()` en el lifespan, así que
> el bloque confirma `0001..0004` antes de tiempo. Si un paso posterior de `0005` falla, la base
> se queda en `0004` sin `0005` estampada y hay que borrar a mano los objetos v2 a medio crear
> antes de reintentar. Está documentado en el docstring de la migración y afirmado por
> `tests/integration/test_migration_0005.py`.
>
> Segunda lección de la misma ejecución, aplicable a cualquier migración futura de este repo:
> **`sa.Enum(..., create_type=False)` no sirve**. `sa.Enum` pierde ese flag al adaptarse al
> dialecto de postgres, así que el `CREATE TYPE` se emite igualmente y la segunda vez revienta.
> Hay que usar `postgresql.ENUM(..., create_type=False)`. Era el motivo real de que
> `alembic upgrade head` desde cero no hubiera funcionado nunca (estaba en `0003`).
>
> Tercera: un valor por defecto JSONB construido con `sa.text()` interpreta los `:` como
> parámetros de bind. Sin escapar, el DDL de `0005` y de `src/models/learner_profile.py` salía
> como `{"texto"NULL,...}`. Hay que escribir `\:`.
>
> Añadir también los miembros al enum Python `GenerationStep` en `src/models/generation_job.py`
> (`SCHEMA_PROPOSING = "schema_proposing"`, `SCHEMA_PROPOSED = "schema_proposed"`).

> **`generation_jobs.output_type`:** es `NOT NULL` sobre un enum con sólo
> `course_and_manual|manual_only` (`src/models/generation_job.py:15-17`), y un job de propuesta de
> esquema no es ninguno de los dos. **Decisión:** el job de esquema escribe
> `output_type='course_and_manual'` como **placeholder sin significado** y ningún consumidor lo
> interpreta (los clientes de esquema se guían por `status`). No se añade un tercer valor al enum
> para no ampliar el problema de enum-huérfano del downgrade por un campo que nadie lee.

`generation_jobs.progress` (jsonb) y `langgraph_thread_id`, hoy nunca escritos, **empiezan a
escribirse** en el grafo de esquema: `progress` recibe `{"step": ..., "nodes_proposed": N}` en cada
nodo, de modo que un cliente que se suscribe tarde al SSE puede reconstruir el estado por REST.

`users.accessibility` (jsonb, ya existe) pasa a tener forma definida — **ajustes neutros, nunca
diagnósticos**:

```json
{"reduce_motion": false, "short_blocks": true,
 "high_contrast": false, "extra_time": false}
```

**`audio_first` se elimina** de la forma y de la pregunta 5: no hay TTS en ningún punto de este PR,
ni componente de audio en el kit congelado (§5.3). Ofrecer una acomodación que el pipeline no puede
entregar es peor que no ofrecerla.

**Cómo se honra `short_blocks` sin que `accessibility` llegue al LLM** (la regla de que nunca llega
se mantiene): el frontend no puede acortar prosa escrita por el modelo, así que la señal se
traduce **en el servidor** a una dimensión que ya viaja al prompt. En `load_context`:

```python
effective_density = min(course.intent_density, 2) if user.accessibility.get("short_blocks") else course.intent_density
```

`effective_density` es lo que entra en el prompt y en la `cache_key`. El LLM recibe un número de
presupuesto de longitud, nunca el flag ni su origen.

### 3.2 El esquema del curso

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

Notas de diseño, cada una con su razón:

- **`summary` es `NOT NULL`.** Sin summary el patrón PageIndex del tutor (leer el árbol de
  summaries → decidir qué nodo es relevante → cargar sólo ése) no funciona. Es requisito de
  validación, no un adorno.
- **`source_headings text[]`, no `chunk_id`.** Los chunks se destruyen al re-ingerir el documento;
  los headings sobreviven. El nodo referencia `(source_document_id, source_headings)`.
- **`seed_lesson_id`** apunta a la lección v1 equivalente si el curso viene de v1. Es el modo
  degradado: si `genera_ui` falla dos veces o no hay LLM disponible, se sirve
  `lessons.content` renderizado con markdown. Esto resuelve la incompatibilidad de v2 con el modo
  offline/catálogo.
- **`mastery_threshold` por nodo**, con default derivado de la criticidad al crear el esquema:
  `critical → 0.90`, `recommended → 0.80`, `contextual → 0.70`. El creador puede sobreescribirlo.
- **`default_ui_format`** existe porque §6.4 manda caer en "el formato canónico por defecto del
  nodo" durante la calibración, y sin esta columna esa instrucción no tenía dónde leerse. Lo propone
  `design_schema` y lo edita el creador en B10. Default `explanation`.
- **`probe_items` / `probe_answer_key`** guardan el pre-assessment **pre-generado en la validación**,
  no por usuario. Los ítems dependen sólo de `(node, source)`, así que se generan una vez por nodo y
  se sirven instantáneamente a todo el mundo: resuelve el arranque en frío del probe (§9.1), donde de
  otro modo la "espera productiva" tendría delante su propia espera de una llamada LLM contra una
  pantalla en blanco. `node_probes` pasa a ser sólo el registro por usuario de un intento.
- **`reviewed_at` / `reviewed_by` por nodo.** La validación de §11.1 prueba que el grafo está bien
  formado, no que un humano leyera la pedagogía. Un nodo sin `reviewed_at` **no se puede servir**:
  `resolve_delivery` sigue mirando el curso, pero `GET /nodes/{id}/render` devuelve `409
  node_not_reviewed` si el nodo no está revisado. Eso cierra el bypass de §11.1 (añadir nodos nuevos
  a un curso ya validado) por construcción, no por confianza.
- **`archived`** en lugar de borrado: un nodo con `learner_node_states.attempts_count > 0` **no se
  puede borrar** (`422 node_has_progress`), se archiva. Borrarlo cascadearía a `learner_node_states`
  y `node_renders`, tirando maestría y rastro de auditoría de gente que ya había trabajado.
- **`UNIQUE (course_id, position)` es `DEFERRABLE INITIALLY IMMEDIATE`** y el `PUT` de §11.1 la
  difiere (`SET CONSTRAINTS uq_course_nodes_position DEFERRED`) dentro de su transacción. Sin eso,
  cualquier reordenación viola la restricción a mitad de la sentencia. Test obligatorio: intercambiar
  las posiciones 1 y 2 en un solo `PUT`.
- **Aciclicidad**: no se puede expresar en un CHECK. Se valida en
  `CourseSchemaService.validate()` con un orden topológico (Kahn) antes de pasar a `'validated'`,
  y hay test unitario del detector de ciclos. Un ciclo devuelve `422`.

### 3.3 El perfil del aprendiz

Tres fuentes independientes, tres sitios distintos: declarado (`learner_profiles`), inferido
(`learning_events` → `format_vector`), y por competencia (`learner_node_states`).

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

- **`preset` reusa el enum `learning_profile`** que ya existe (`standard|focus|fast`). No se crea
  un enum nuevo. `users.learning_profile` sigue siendo la fuente de verdad para el frontend v1;
  `learner_profiles.preset` se mantiene sincronizado en la misma transacción del onboarding.
- **`experience_level` arranca en `'unknown'`, no en `'none'`.** `'none'` significa "declara que no
  tiene experiencia" y dispara andamiaje de novato (ejemplos resueltos), que es exactamente lo que
  **perjudica** al experto. Usar `'none'` como "no lo sé" haría que **todo el que salte el onboarding**
  reciba andamiaje de novato en silencio. `'unknown'` se mapea a andamiaje **neutro**: ni ejemplos
  resueltos extra ni supresión de andamiaje; el probe del primer nodo corrige en 2 ítems.
- **`format_vector` es jsonb, no 4 columnas.** Añadir una dimensión no debe ser una migración.
  Las dimensiones son **exactamente las que el kit congelado de §5.3 puede producir**:
  `texto` (`TextContent`, `Callout`, `StepSequence`, `Card`), `ejercicio` (`QuizItem`),
  `codigo` (`CodeBlock`), `dato` (`Chart`, `Table`). Se eliminan `diagrama`, `audio` y `recurso`:
  ningún componente los emite, así que serían dimensiones que no pueden recibir señal nunca y que
  sesgarían el bucket dominante hacia `texto` por construcción.
  Suma ~1.0 tras normalizar L1; con el usuario nuevo son todos 0 y **no se usa para nada**
  (ver periodo de calibración, §6.4).
- **`nodes_completed`** es el contador que gobierna el periodo de calibración. Denormalizado a
  propósito: se lee en cada `decide_formato` y no queremos un `COUNT(*)` por render.
  **Regla de incremento, fijada:** `+1` sólo en la transición `learning → mastered`, es decir sólo
  cuando el nodo se ha *trabajado*. Un nodo saltado por el probe (`probing → mastered`) **no**
  incrementa `nodes_completed`, precisamente porque no generó ni un evento de interacción: contarlo
  sacaría al usuario de la calibración con un `format_vector` vacío.
- **`tutor_notes`** es el "cuaderno del tutor" (Notarius). **Vocabulario controlado**, no prosa
  libre, para que sea auditable y borrable:

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

Acciones permitidas (validadas por Pydantic, `Literal`) y **la condición exacta que las escribe**.
Sin esta tabla `tutor_notes` era una entrada libre y no especificada a un prompt, es decir no
implementable ni testeable; y `sugerir_formato_audio` se elimina porque ni existe componente de
audio (§5.3) ni hay señal que pueda producirla. Todas las escrituras ocurren en
`LearnerProfileService.apply_signals()`, llamado tras cada `answer`/`feedback`, **nunca** desde un
LLM:

| Acción | Condición exacta que la emite | Test |
|---|---|---|
| `reforzar_con_ejemplo` | `consecutive_failed >= 2` en el nodo | `test_profile_service.py::test_signal_reinforce` |
| `bajar_dificultad` | `node_feedback.difficulty == 'hard'` en el nodo | `…::test_signal_lower` |
| `subir_dificultad` | `node_feedback.difficulty == 'easy'` **y** `consecutive_correct >= 3` | `…::test_signal_raise` |
| `reducir_longitud_modulo` | 3 eventos `scroll_fast` consecutivos en el mismo nodo | `…::test_signal_shorten` |
| `revisar_prerrequisito` | `last_error_kind == 'conceptual'` **y** el nodo tiene ≥1 prerrequisito con `state != 'mastered'` | `…::test_signal_prereq` |

`signals` está capado a las 20 más recientes (poda en el servicio) y una misma `(node_id, action)`
no se duplica: se actualiza el `at`. Esto es una **simplificación deliberada** de la exploración de
Notarius, que proponía derivar señales de la conversación con el tutor y de comportamiento de
audio/dwell: como §1.3 quita el chat dentro del nodo y no hay audio, esas fuentes no existen aquí y
el vocabulario cerrado es lo único alimentable.

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

- **`active_render_id` + `render_pinned`** implementan la Visión A de §1.4: el render se fija al
  abrir el nodo. `GET /nodes/{id}/render` devuelve el spec de `active_render_id` mientras
  `render_pinned` sea `true`, **sin recalcular la `cache_key`**. Sin esto, el contenido mutaba a
  mitad de nodo: con respuestas perfectas la maestría recorre 0 → 0.40 → 0.64 → 0.784 → 0.87, y con
  `mastery_band` en la clave eso son cuatro claves distintas dentro de un mismo nodo `critical`, así
  que un simple refresco del navegador devolvía otros bloques en otro orden — rompiendo la propia
  tabla de zonas de estabilidad de §5.5.
- **`scaffold_band`** sustituye a `mastery_band` en la `cache_key` (§3.4). Se calcula **una vez**, al
  cerrar el probe: `novice` si `experience_level='none'` o el probe salió `learning` con
  `score_a == 0`; `advanced` si el probe salió `tiebreak` o `experience_level='experienced'`;
  `neutral` en el resto. Es estable durante todo el nodo por construcción, no por convención.
- **`waived_by` / `waived_at`**: la vía de escape humana de §7.4 (`POST /nodes/{id}/waive`).

`mastery` es la **única** escala primaria de dominio. Las demás son vistas derivadas, calculadas
en código, nunca persistidas por duplicado:

| Derivación | Regla |
|------------|-------|
| Fase Shu-Ha-Ri (andamiaje) | `mastery < 0.5 → shu`; `0.5 ≤ mastery < threshold → ha`; `≥ threshold → ri` |
| `skill_level` (`low/medium/high` de `user_skills`) | `< 0.5 → low`; `< 0.85 → medium`; `≥ 0.85 → high`. Se aplica sólo al alza, como ya hace `_assign_course_skills` |
| Nivel Bloom objetivo del siguiente ítem | `shu → understand`; `ha → apply`; `ri → analyze` |

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

Append-only. Pesos fijos, definidos como constante en
`src/services/learner_profile_service.py::EVENT_WEIGHTS`:

| `type` | peso | | `type` | peso |
|---|---|---|---|---|
| `explain_click` | +0.30 | | `quiz_correct` | +0.20 |
| `expand` | +0.15 | | `quiz_wrong` | +0.10 |
| `scroll_slow` (>3 s) | +0.10 | | `view` | +0.05 |
| | | | `scroll_fast` (<1 s) | −0.05 |

`element` ∈ `{texto, ejercicio, codigo, dato}` — las cuatro dimensiones del `format_vector`.

**`resource_opened` se elimina** (era el segundo peso más alto): el kit congelado de §5.3 no tiene
componente de enlace o recurso, así que ningún render puede emitir un elemento sobre el que abrir un
recurso. Un evento que ningún render puede disparar no es una señal, es peso muerto que distorsiona
la normalización L1.

**Privacidad, decidida y corregida:** `learning_events.metadata` **nunca** guarda texto del usuario
ni el contenido copiado. Sólo `{"element_id": "...", "ms": 1234}`. El texto derivado del usuario
aterriza en **dos** sitios, no en uno — la versión anterior de este documento decía "un único sitio"
y se contradecía con §3.4:

1. `node_feedback.unclear` — texto libre que el usuario escribe.
2. `term_explanations.term` / `term_normalized` — la selección que el usuario clicó. Es texto
   *elegido* por el usuario, y por eso §8.4 limita lo cacheable a **≤60 caracteres y ≤4 tokens**;
   por encima de eso la explicación se sirve pero **no se persiste**.

Retención y borrado, todo por el mismo script (`python -m src.scripts.purge_learning_data`, ver §1.3
— no existe tabla `background_jobs`): `learning_events` a **90 días**; `term_explanations` a **180
días desde `last_used_at`**. Borrado a petición del interesado:
`DELETE /users/me/learner-profile` (§11.2) borra las **siete** tablas personales del usuario —
`node_render_views`, `node_feedback`, `node_attempts`, `node_probes`, `learner_node_states`,
`learning_events` y `learner_profiles` — y anonimiza `node_renders.generated_by` a `NULL`.
`node_attempts` y `node_probes` guardan las respuestas que el empleado escribió, así que un borrado
que las dejara atrás devolvería `204` por una promesa que no ha cumplido; el orden es el que imponen
las FKs de `0005` (`node_attempts` antes de `node_probes`, porque `node_attempts.probe_id` es
`ON DELETE SET NULL`). El script de retención **no** cubre esto y no debe: su cometido son las dos
ventanas de arriba, no la supresión del art. 17.

El vector se calcula sobre una ventana de 30 días con decaimiento:

```
weight_effective = weight * GREATEST(0.2, 1.0 - (age_seconds / (30*86400)) * 0.8)
format_vector[e] = SUM(weight_effective) / SUM(all)      -- normalizado L1
```

**Visibilidad:** `learner_profiles` y `learner_node_states` son privados del empleado. El admin ve
sólo agregados con **k ≥ 5** (si el grupo tiene menos de 5 personas, no se muestra la métrica).
`role_title` y `sector` sí viajan al LLM. **`goal` ya no viaja al LLM** (ver §3.4 y §6.2): se
consume de forma determinista en el frontend para la línea de apertura "esto te sirve para X". Eso
reduce el dato personal enviado a un tercero **y** hace que la promesa de la pregunta 2 sea real
en lugar de depender de que el modelo se acuerde de escribirla. `users.accessibility` **nunca** va al
LLM (§3.1 explica cómo se honra `short_blocks` sin enviarlo).

**Aviso en el punto de recogida (RGPD, art. 13):** la pantalla de la pregunta 1 del onboarding
muestra, con el mismo peso visual que la pregunta, una línea fija:
*"Tu puesto y tu sector se envían al proveedor de IA para adaptar los ejemplos. Puedes borrarlos
cuando quieras desde Ajustes."* No es copy opcional: es requisito y va en `OnboardingRead`
(`notice`), no hardcodeado en el cliente.

### 3.4 Contenido generado en runtime

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
    ui_spec        jsonb NOT NULL DEFAULT '{}',   -- IR validada; auditoría, NO se sirve
    answer_key     jsonb NOT NULL DEFAULT '{}',   -- nunca se serializa al cliente
    dialect        text,                          -- el programa canónico que pintó el navegador
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
    -- Trazabilidad de cumplimiento: una fila que alguien vio dice QUÉ vio y contra qué
    -- catálogo. 'pending'/'generating'/'failed' no tienen nada que mostrar.
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

- **`answer_key` es columna aparte de `ui_spec`** y **nunca** se serializa a la API. Es el
  equivalente estructural de `strip_answers()` del camino v1, pero por construcción en lugar de por
  filtrado: no se puede filtrar mal lo que no está en el mismo campo.
- **`node_renders` no tiene `user_id`.** Tenía uno `NOT NULL … ON DELETE CASCADE` junto a un
  `UNIQUE (cache_key)` global, y las dos cosas juntas eran incoherentes de tres maneras: la búsqueda
  por usuario no encontraba nunca la fila compartida (hit rate 0, que es el pilar del modelo de
  coste); la fila sólo registraba a **quien la generó primero**, así que la promesa de auditoría de
  §2.1 era falsa para cada acierto de caché; y dar de baja a ese primer empleado **destruía el render
  que veían todos los demás** y, con él, la evidencia de sus certificados. Ahora: `org_id` para el
  scoping, `generated_by` `NULL`-able con `SET NULL` para trazabilidad de generación, y
  `node_render_views` para la auditoría de lectura (§2.1).
- **La búsqueda de caché es estrictamente `WHERE cache_key = :key AND status='ready' AND NOT
  is_preview`.** Nada de `user_id` en el `WHERE`, nunca.
- **`is_preview`**: los renders de `?preview=1` del modo `shadow` se persisten para poder revisarlos,
  pero **quedan fuera de la caché**. Sin esto, un preview generado por un admin **antes** de validar
  el esquema podía servirse literalmente a un empleado del mismo bucket — contenido no aprobado
  llegando a un aprendiz por la puerta de atrás.
- **`cache_key` es `UNIQUE` global**: dos usuarios con el mismo bucket de perfil comparten render.
  Eso es deliberado y es lo que hace el coste sostenible.

```
cache_key = sha256(
    f"{node_id}|{course.schema_version}|{preset}|{experience_level}|{role_bucket}"
    f"|{scaffold_band}|{vector_bucket}|{effective_density}|{backend}|{model}|{PROMPT_VERSION}"
)
role_bucket    = slug(role_title or sector or "")[:24]     # "" si no hay onboarding
scaffold_band  = learner_node_states.scaffold_band          # novice|neutral|advanced, fijo por nodo
vector_bucket  = f"{dominant}:{round(p_dominant,1)}"        # "" durante calibración
```

Dos correcciones respecto a la versión anterior de esta fórmula, ambas obligadas:

1. **Entra `role_bucket`.** `role_title` es lo único que §6.2 declara que viaja *literalmente* al
   prompt de `genera_ui`, y era la única adaptación con evidencia fuerte — pero no estaba en la
   clave. Resultado: un dependiente y un encargado de turno con el mismo preset compartían fila y el
   segundo recibía los ejemplos enmarcados para el rol del primero, borrando en silencio la
   personalización que el onboarding promete. `slug(role_title)` baja el hit rate; se acepta, porque
   una caché que sirve contenido con el marco de rol equivocado no es un acierto, es un fallo barato.
2. **Sale `mastery_band`, entra `scaffold_band`.** `floor(mastery*5)/5` cambia con cada respuesta:
   cuatro claves distintas dentro de un solo nodo `critical`. `scaffold_band` se congela al cerrar el
   probe (§3.3) y no se mueve hasta que el nodo se cierra.

`PROMPT_VERSION` es una constante en `src/llm/prompts/runtime.py`; subirla invalida todos los renders
sin tocar la BD.

**Sobre la cita del experimento de caché, honestamente:** la medición interna de ~80 % de aciertos
con 0 entregas obsoletas corresponde a una clave **por usuario** (`usuario+curso+módulo+bucket`), y
el 0 % de obsoletas es una *propiedad de esa clave*, no un resultado transferible. La clave
**inter-usuario** de este diseño es un régimen **no medido**. Por eso el primer número que se mide en
§14.2 #3 no es sólo el hit rate: es el par (hit rate, tasa de obsoletas) de la clave compartida.

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

**El `UNIQUE` parcial de `node_probes` es la regla anti-reintento**, y es lo que impedía que la
maestría fuera *gameable*: un probe perfecto (2/2) devuelve `mastered`, salta el nodo y cuenta para
`enrollments.status='completed'` y para `user_skills`; con dos ítems de 4 opciones el azar acierta
1 vez de 16, así que sin límite de intentos bastaba reentrar ~16 veces para saltarse cualquier nodo
—incluido uno `critical` de seguridad— sin haber visto una línea de contenido. Reglas, concretas:

- **Un probe puntuado por `(user_id, node_id, schema_version)`.** Al reentrar en el nodo se sirve el
  veredicto almacenado; no se genera otro.
- **Re-probe sólo desde `needs_review`** y con al menos **7 días** desde `completed_at`. Se inserta
  con `attempt_no + 1` (la fila anterior pasa a `scored = false`, así el índice parcial lo permite).
- **En un nodo `critical` el veredicto `mastered` nunca puede salir de ítems de respuesta
  seleccionada**: el desempate de respuesta construida es **obligatorio** (§7.2).
- **`scored = false`** también se usa para el probe diagnóstico del novato (§7.1): se muestra, no
  puntúa, no persiste fallos y no consume el intento único.

`node_attempts` existe en lugar de reusar `exercise_attempts` porque esta última tiene
`exercise_id uuid NOT NULL REFERENCES exercises(id)` y los ítems generados al vuelo no son filas de
`exercises`. Sí **reusa el enum `exercise_type`** y reusa la corrección determinista existente,
pero con un nombre y una forma exactos que la versión anterior de este documento tenía mal:

- La función es **`grade(exercise_type, content, answer)`, módulo-level y ya pura** en
  `src/services/exercise_service.py:73` ("Pure and importable without any DB or LLM dependency").
  **No** es `ExerciseService.grade()` (`ExerciseService` es la clase de la línea 100) y **no** hay que
  extraerla a ningún sitio: se importa tal cual.
- **Sí hace falta un adaptador**, así que no es "cero lógica nueva": `grade()` lee la respuesta
  correcta de un dict `content` con forma v1 (`correct`, `blanks`, `correct_order`, `explanation`),
  mientras que v2 tiene los enunciados en `QuizItem.props` y las soluciones en `answer_key`. El
  adaptador es `src/services/node_grading.py::content_for(item_props, answer_key_entry) -> dict`,
  con test propio por cada uno de los 4 tipos deterministas.
- **Los cuatro tipos deterministas puntúan 0.0 o 1.0**, sin crédito parcial — incluido `fill_blank`,
  que devuelve 0.0 si falla **un solo** hueco (`_grade_fill_blank`, líneas 34-43). Esto es
  load-bearing para la aritmética de §7.2 y hay que tenerlo presente antes de "hacer continuo" ningún
  ítem.
- Para `practical_case`/`dialogue` se usa `grade_open_answer()` (purpose `eval`), que se construye con
  `get_optional_llm_service`. Ese factory **también** tiene que pasar por `_maybe_fixture` (§12.1) o
  el flujo con fixtures intenta una llamada de red real.

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

Sólo se persiste si el término es **≤60 caracteres y ≤4 tokens** (§8.4). Una selección de 140
caracteres es una frase escogida por el usuario, no un término, y guardarla indefinidamente en una
fila **sin `user_id`** la haría además imposible de atender ante una solicitud de supresión. Por
encima de 60 caracteres (hasta el límite duro de 140) la explicación se genera y se sirve, pero
**no se escribe**. `idx_term_expl_purge` da soporte al borrado a 180 días de `last_used_at`.

`context_hash = sha256(normalized_block_text)[:16]`. **Incluir el contexto en la clave no es
opcional**: es el argumento central de la función. "Mercurio" en un nodo de química y "Mercurio"
junto a "planeta" deben dar explicaciones distintas. La implementación de referencia de Curio
omite el contexto de la clave y ése es su bug de diseño; aquí no se replica.

### 3.5 Las dos tablas de instrumentación que el diseño da por hechas

Estas dos **no existen en el repo** (verificado: 20 tablas, ningún `llm_usage_log` ni `audit_log` en
`src/` ni en `0001..0004`), y sin embargo tres mitigaciones de §14.1 y la decisión abierta #1 de
§14.2 dependen de ellas. Se crean en `0005` en lugar de seguir citándolas:

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

`llm_usage_log` es pequeña y load-bearing: es la única forma de decidir §14.2 #1 (ratio real
fast/heavy) con datos en lugar de con la hipótesis 90/10. La escribe **un solo sitio**, un wrapper
`log_usage()` alrededor de las llamadas de los nodos nuevos; los nodos v1 no se instrumentan en este
PR. `audit_log.detail` en `course_schema_validated` guarda el **diff propuesto→validado** (nodos
añadidos, borrados, campos editados): así se puede medir si los creadores editan de verdad lo que
propone el LLM, que es el riesgo "Alta" de §14.1 que ninguna validación estructural cubre.

### 3.6 Resumen del delta

**13 tablas nuevas:** `course_nodes`, `course_node_prerequisites`, `learner_profiles`,
`learner_node_states`, `learning_events`, `node_renders`, `node_render_views`, `node_probes`,
`node_attempts`, `node_feedback`, `term_explanations`, `llm_usage_log`, `audit_log`.
**8 enums nuevos:** `course_delivery_mode`, `course_schema_status`, `node_criticality`,
`learner_experience`, `node_state`, `error_kind`, `ui_format`, `node_render_status`.
**1 tabla alterada:** `courses` (+6 columnas). **1 enum extendido:** `generation_step` (+2 valores).

> `node_state` conserva el miembro `needs_review`, pero su **único productor en este PR** es el tope
> de pistas de §7.4. No hay scheduler de repetición espaciada (§1.3), así que la transición
> `mastered → needs_review` **no ocurre** y no aparece en la tabla de §7.3.

---

## 4. Pipeline LangGraph

Dos grafos nuevos. El grafo v1 (`src/agents/content/`) **no cambia de comportamiento**, pero sí
recibe **un refactor de extracción sin cambio funcional** (ver más abajo). La afirmación de la
versión anterior de este documento — que `prepare_context` y `extract_themes` "no escriben en BD" y
podían importarse tal cual — era **falsa**, y con ella caían dos piezas del diseño:

- `nodes.py:177-178` hace `await _set_job(job_id, status=GenerationStep.EXTRACTING)` y
  `await _publish_step(job_id, "extracting", …)`; `nodes.py:215-216` hace lo mismo con
  `STRUCTURING`. Importarlos en `build_schema_graph()` pondría el job de esquema en
  `'extracting'`/`'structuring'` — nunca en los `'schema_proposing'`/`'schema_proposed'` que añade la
  migración — y emitiría eventos `step` genéricos.
- El canal está fijado en `src/agents/content/errors.py:26-27`
  (`return f"generation:{job_id}"`), así que esos eventos irían a `generation:{job_id}`, que ningún
  cliente de esquema escucharía.

**Decisión, una sola:** se extraen las partes **puras** a `src/agents/content/helpers.py`
(`estimate_pages`, `assemble_chunk_text`, `themes_list`) y `src/agents/content/nodes.py` las importa
desde ahí. Es un movimiento de código sin cambio de comportamiento, cubierto por
`tests/test_generation_pipeline.py`, que ya existe. Los nodos del grafo de esquema son **nuevos** y
viven en `src/agents/schema/nodes.py`: reutilizan esos helpers, `THEME_EXTRACTOR_SYSTEM` y
`build_extraction_prompt`, y escriben **sus propios** estados y eventos. Nada de importar los nodos
v1. `src/agents/content/helpers.py` y `nodes.py` van en la lista de ficheros de **B2**.

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
    available_headings: list[str]   # lista cerrada de headings reales del documento
    # New
    proposed_nodes: list[dict]      # título, summary, outcome, criticality,
                                   # prerequisites (índices), source_headings
    schema_warnings: list[str]
    # Control
    error: str | None
    current_step: str
```

`design_schema` hace **una** llamada LLM (`SCHEMA_DESIGNER_SYSTEM`, `json_mode=True`,
`temperature=0.2`, purpose `generation`) y devuelve nodos con prerrequisitos expresados como
**índices** de la propia lista, no como uuids — el LLM no puede inventar uuids. `persist_schema`
los traduce a FKs, ejecuta un orden topológico, poda las aristas que crearían ciclos (añadiendo
un aviso a `schema_warnings` en lugar de fallar) y escribe con `schema_status = 'proposed'`.

**`source_headings` se elige de una lista cerrada, no se inventa.** `load_source` recoge los
headings reales (`chunk_metadata->>'heading'` distintos del documento, que `src/services/chunker.py`
guarda como un string por chunk) en `available_headings`, y el prompt de `design_schema` obliga a
elegir **sólo de esa lista**; `persist_schema` descarta cualquier heading fuera de ella y lo anota en
`schema_warnings`. Sin esto, un heading inventado por el LLM no coincide con ningún chunk y
`load_context` (§4.2) entrega una fuente vacía a `genera_ui` — un fallo silencioso que produce
contenido plausible sin base documental.

Checkpointer: `MemorySaver`, igual que v1. El job es corto y su estado real vive en
`generation_jobs` + `course_nodes`. **No se introduce `langgraph-checkpoint-postgres`** en este PR
(dependencia nueva, y el gate humano ya es un estado de BD, no un `interrupt`).

**Canal SSE: `f"generation:{job_id}"`, el mismo que v1** — no `schema:{job_id}`. Razón concreta: el
endpoint que se reutiliza tiene el canal **hardcodeado** (`src/routes/generation_jobs.py:42`,
`async for event in subscribe(f"generation:{job_id}")`), así que un canal propio no llegaría a
ningún cliente sin reescribir el endpoint para suscribirse a dos canales. Los eventos ya van
namespaced por tipo, así que compartir canal no colisiona: `schema_step`, `schema_progress`,
`schema_ready`, `error`. Lo único que cambia en el fichero de rutas es
`_TERMINAL_EVENTS = {"completed", "error", "schema_ready"}` (línea 18).

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
    source_context: str        # texto de la fuente (RAG o full_text), ya recortado
    # Gate
    mastered: bool
    # Router
    ui_format: Literal["explanation", "simulation", "exercise", "chart", "mixed"]
    tier: Literal["fast", "heavy"]
    format_rationale: str
    # Generation
    backend: str               # "openui" (único dialecto en este PR)
    effective_density: int     # intent_density del curso, acotado por short_blocks (§3.1)
    scaffold_band: str         # novice|neutral|advanced, fijado al cerrar el probe
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

Cada nodo va envuelto en un wrapper **propio y nuevo**, `src/agents/runtime/errors.py::
runtime_node_error_wrapper`. **No** se adapta el de v1: `src/agents/content/errors.py:47-66` está
duramente acoplado a `state["job_id"]` y a marcar una fila de `generation_jobs` como `failed`, y
`NodeRuntimeState` no tiene `job_id` ni fila de job. Con `job_id` vacío el wrapper v1 se salta **tanto
el bookkeeping como el `sse.publish`**, de modo que el contrato `error {fallback: true}` que el
frontend espera en §9.2 **no se emitiría nunca** ante un fallo de nodo. El wrapper nuevo:

```python
# src/agents/runtime/errors.py
def runtime_node_error_wrapper(name: str):          # keyed on request_id, not job_id
    # on exception:  node_renders.status = 'failed' + error_message
    #                sse.publish(f"node:{request_id}", "error",
    #                            {"step": name, "message": …, "fallback": True})
    #                return {"error": …, "current_step": "failed"}
```

Cada nodo abre su propia sesión con `async_session_factory`, igual que v1.

| Nodo | Qué hace | LLM |
|------|----------|-----|
| `load_context` | Carga nodo, perfil, estado, y la fuente (ver nota de abajo). Calcula `effective_density` y `cache_key`. **Si hay hit en `node_renders` con `status='ready'` y `NOT is_preview`, corta antes de entrar al grafo** (lo comprueba el servicio, no el grafo) | — |
| `probe_gate` | Lee `learner_node_states.state`. Si `'mastered'` → salta | — |
| `decide_formato` | Decide `ui_format` y llama al router para el tier | Sí, tier `fast` |
| `genera_ui` | Pide al modelo el **dialecto del backend activo**, usando `src.render.prompt.render_prompt()` (el artefacto generado por `library.prompt()`) como parte del system prompt | Sí, tier del router |
| `validate_ui` | `gate.canonicalize(raw_dsl)`: topes de tamaño y rechazo de reactividad → `backend.parse()` → `UISpec` (las 7 reglas) → `serialize()` → el `dialect` canónico. Separa `answer_key` | — |
| `persist_render` | Escribe `node_renders` (`status='ready'`) con `dialect`, `catalog_version` y `library_version`, publica `ui_done` | — |
| `fallback_seed` | Construye un `ui_spec` de un solo bloque `Markdown` con `lessons.content` del `seed_lesson_id` (o el `source_context` recortado). `status='fallback'` | — |
| `skip_node` | Marca el nodo como saltado y publica `node_skipped` | — |

**La fuente en `load_context`, con camino de implementación real.** La versión anterior decía
"`similarity_search(top_k=8)` … filtrando por `source_headings`", y ese filtro **no existe**:
`src/repositories/document_chunk_repo.py:73-97` sólo acepta
`org_id / query_embedding / top_k / document_ids`. Se añade en **B1** un método nuevo al repositorio
(no se toca el existente, que lo usan rutas v1):

```python
async def similarity_search_by_headings(
    self, *, org_id, query_embedding, top_k=8,
    document_ids=None, headings: Sequence[str] | None = None,
) -> list[dict]:
    """Igual que similarity_search, con
    AND (chunk_metadata->>'heading') = ANY(:headings) cuando headings no es vacío."""
```

Ramas, explícitas:

- Documento con **≤5 páginas** → `full_text`. Esta rama **no necesita embeddings**, y es la que
  cubren los tests con fixtures (§12.1).
- Documento mayor → `similarity_search_by_headings(headings=node.source_headings)`. Necesita un
  embedding real de la query **y** chunks con `embedding` no nulo
  (`DocumentChunk.embedding` es `Vector(...)` `nullable=False`), así que sólo funciona con embedder
  disponible. Si `headings` no devuelve nada, se reintenta sin el filtro de headings y se anota un
  aviso en el log estructurado.

**Presupuestos:** `decide_formato` `max_tokens=256`, `temperature=0.0`, `json_mode=True`.
`genera_ui` `max_tokens=1200` (tier fast) / `2400` (tier heavy), `temperature=0.4`. `MAX_UI_RETRIES = 2`.
Concurrencia global de generación runtime: `asyncio.Semaphore(6)` en el runner, para que un pico
de empleados no tumbe el proceso.

### 4.3 El router de dos niveles

`src/agents/runtime/router.py`

```python
HEAVY_FORMATS = frozenset({"chart", "mixed", "simulation"})
ALLOWED_UI_FORMATS = frozenset({"explanation", "exercise", "chart", "mixed"})  # simulation OFF
# No hay FAST_FORMATS: select_tier sólo consulta HEAVY_FORMATS, así que una segunda
# constante sería código muerto que puede desincronizarse.

def select_tier(ui_format: str) -> Literal["fast", "heavy"]:
    return "heavy" if ui_format in HEAVY_FORMATS else "fast"

def purpose_for(tier: str) -> str:
    return "runtime_heavy" if tier == "heavy" else "runtime_fast"
```

Enrutamiento **a nivel de UI completa**, no por componente. Se conecta al mecanismo de purposes
que ya existe en `resolve_llm_config(org_settings, purpose=...)`, así que sólo hay que añadir dos
env vars y dos claves de org settings:

```python
# src/config.py — Settings
LLM_RUNTIME_FAST_MODEL: str | None = None    # ej. "groq/llama-3.1-8b-instant"
LLM_RUNTIME_HEAVY_MODEL: str | None = None   # ej. "groq/openai/gpt-oss-120b"
```

Precedencia (la que ya implementa `resolve_llm_config`, sin tocarla):
`org_settings["llm_runtime_fast_model"]` → `org_settings["llm_model"]` →
`LLM_RUNTIME_FAST_MODEL` → `LLM_MODEL`. Si no se configura nada, **ambos tiers caen en
`LLM_MODEL`** y todo sigue funcionando con un solo modelo. Ningún proveedor concreto es requisito.

Se registra cada llamada en `llm_usage_log` (tabla creada en `0005`, §3.5) con `use_case` ∈
`{decide_formato, runtime_activity_authoring, genera_ui, explain, probe_generate,
schema_design}` para medir el ratio real
fast/heavy (la estimación 90/10 es una hipótesis, no un dato).

**Single-tenancy: se documenta, no se arregla aquí.** `src/deps/llm.py:22-25::_org_settings` y
`SettingsService._get_org` hacen `select(Organization).limit(1)`. Arreglarlo de verdad significa meter
un `CurrentUser` en `LLMDep`/`TutorLLMDep`/`EmbeddingDep`/`OptionalLLMDep`, que consumen rutas v1
(`src/routes/chat.py:30,47`, `src/routes/exercises.py:61`) **sin un solo test que las cubra hoy**
(`tests/` tiene `test_chunking`, `test_generation_pipeline`, `test_grading`,
`test_retrieval_assembly`, `test_skill_service`). Cambiar firmas de dependencias de rutas v1 sin red
de seguridad, dentro de un lote presentado como "paralelo y seguro", es exactamente el tipo de
regresión silenciosa que este PR promete no introducir.

**Decisión:** sale de B1 y se convierte en su propio `chore` PR (con tests de ruta para chat y
corrección de ejercicios como parte del mismo). Es seguro diferirlo porque el bootstrap mantiene la
invariante de **una organización** (`ensure_organization` en el lifespan), así que hoy
`limit(1)` resuelve la org correcta por construcción. Los dos purposes nuevos no dependen de ese
arreglo: `resolve_llm_config` los resuelve por `getattr(settings, f"LLM_{purpose.upper()}_MODEL")`
(`src/llm/client.py:61-67`) con independencia de cómo se cargaron los org settings. Queda anotado en
§14.2 #11 con fecha.

---

## 5. Capa de render

### 5.1 Principio

> **CORREGIDO el 2026-07-26** (decisión de producto: adopción completa de OpenUI —
> `docs/design/openui-adoption.md`). La frase que había aquí, *"el navegador **nunca** recibe markup
> generado"*, **ya no es cierta** en la parte que importa: el navegador recibe **dialecto** y lo
> interpreta con `<Renderer>` de `@openuidev/react-lang` sobre los componentes que registramos. Lo que
> sigue siendo literalmente cierto es lo demás: **el LLM nunca produce HTML** y **el navegador nunca
> recibe el texto que escribió el modelo**.

```
nodo + perfil + fuente ──► LLM ──► DIALECTO (texto crudo, NO SE SIRVE NUNCA)
        │
        ├─► gate.check_program()   topes de tamaño; nada de $estado, Query, Mutation, @builtins
        ├─► backend.parse()        gramática congelada + las 7 reglas de §5.2 (Pydantic)
        ├─► UISpec (jsonb)         registro de auditoría, sólo servidor
        └─► backend.serialize()  ──► node_renders.dialect ──► <Renderer> en el navegador
                                     (+ catalog_version, library_version)
```

**Las tres propiedades que sostienen esto**, y ninguna es una promesa de estilo:

1. **El navegador sólo ve la re-serialización canónica de una `UISpec` ya validada.** Nunca
   `raw_dsl`. La columna ya no se llama así (`node_renders.dialect`), precisamente para que nadie la
   sirva por descuido. Una `UISpec` no puede representar estado ni una llamada a tool, así que la
   propiedad es **estructural**, no una comprobación.
2. **El servidor sigue siendo el que valida.** El parser de OpenUI en el cliente pinta; el nuestro
   decide. Su parser acepta en silencio enums inventados, tipos incorrectos, ids duplicados,
   `<script>` y `Mutation("delete_all_users", {...})` con `meta.errors=[]`; el nuestro no puede ni
   representarlos.
3. **`answer_key` nunca se serializa.** Igual que antes: regla 5 de §5.2, columna aparte, y ningún
   esquema de respuesta la menciona.

**Superficie nueva que esto abre, dicha en voz alta: las mutaciones.** El lenguaje real tiene estado
(`$var`), consultas (`Query`), mutaciones (`Mutation`), acciones (`Action`, `@OpenUrl`,
`@ToAssistant`, `@Set`) y 13 builtins. Un PDF envenenado puede intentar emitirlas. Mitigación, en
cuatro controles apilados y medidos (`SEGURIDAD-MUTACIONES.md`):

| Control | Cómo | Efecto medido |
|---|---|---|
| No servir texto crudo | `serialize()` desde la `UISpec` validada | Las 10 fixtures re-serializadas parsean con 0 violaciones |
| `toolProvider` **ausente** en el `<Renderer>` | por omisión de prop | `createQueryManager(null)`: cero red, queries **y** mutaciones cortadas |
| `onAction` y `onStateUpdate` **ausentes** | por omisión de prop | `@OpenUrl`/`@ToAssistant` son no-ops; `@Set` no se persiste. Y sin ningún componente que llame a `useTriggerAction()`, un `ActionPlan` no es ni alcanzable |
| Puerta en los dos lados | `src/render/gate.py` + `parse()` en el servidor; `assertStaticOnly(parseResult)` en `onParseResult` en el cliente | 15/15 payloads rechazados, 0 falsos positivos sobre las 10 fixtures válidas |

Y el más barato de todos: **el prompt no enseña la reactividad**. Sin `tools` y sin `markReactive()`,
`library.prompt()` no menciona `$var`, `Query(`, `Mutation(`, `@Run` ni `@Set`. Es mitigación en
profundidad, no barrera: si el modelo la emite de memoria, quien la rechaza es la puerta.
`RENDER_ALLOW_REACTIVE=false` es el interruptor, y las condiciones para tocarlo están en
`docs/design/openui-adoption.md` §6.

Se sigue cambiando de dialecto cambiando una env var; el pipeline, la IR y la BD no se enteran. El
**frontend sí** se enteraría ahora: recibe dialecto, no IR.

### 5.2 La IR canónica: `UISpec`

Lista **plana** de componentes con referencias por id (los LLMs generan listas planas mejor que
árboles anidados, y así el parseo incremental es trivial).

```json
{
  "version": "skillnet-ui/1",
  "format": "explanation",
  "root": "b0",
  "components": [
    {"id": "b0", "type": "Stack",    "props": {"gap": "md"},
     "children": ["b1", "b2", "b3"]},
    {"id": "b1", "type": "TextContent",
     "props": {"text": "Las devoluciones se aceptan durante 30 días naturales.",
               "variant": "body"}},
    {"id": "b2", "type": "StepSequence",
     "props": {"title": "Proceso de devolución",
               "steps": ["Verificar el producto", "Escanear el ticket",
                         "Registrar en el sistema", "Emitir el reembolso"]}},
    {"id": "b3", "type": "QuizItem",
     "props": {"item_id": "q1", "item_type": "test", "bloom_level": "apply",
               "question": "Un cliente vuelve el día 32. ¿Qué haces?",
               "options": ["Aceptar la devolución", "Ofrecer garantía del fabricante",
                           "Rechazar sin más", "Llamar al encargado"]}}
  ]
}
```

Reglas del contrato, validadas por Pydantic en `src/render/spec.py`:

1. `root` debe existir en `components` y ser de tipo contenedor (`Stack` o `Card`).
2. Toda referencia en `children` debe existir. Referencias adelantadas permitidas.
3. Sin ciclos en el árbol de `children`.
4. Máximo **12** componentes por spec y **5 elementos** en el nivel raíz del `Stack`. No es
   estética: la memoria de trabajo procesa 4-7 elementos, y una "pantalla cognitiva" son 3-5
   elementos relacionados. Un spec con 30 bloques es un fallo de generación, no contenido rico.
5. `QuizItem` **no lleva** respuesta correcta ni explicación. Eso va a `answer_key`.
   **Corolario, demostrado (2026-07-26):** la corrección 100 % en cliente es **incompatible con esta
   regla por construcción** — escribir el veredicto como `$elegida == 1` exige serializar la respuesta
   al navegador. No es un defecto de OpenUI Lang, es aritmética. La vía que sí la respeta es
   `Mutation("grade_answer", {item_id, choice})` con un viaje al servidor, y está apagada (§5.1).
6. `props.text` es texto plano o markdown inline (`**`, `*`, `` ` ``, links). Nunca HTML.
7. **El primer hijo de `root` en los formatos `explanation` y `mixed` debe ser un `TextContent`
   (`variant: "lead"`) o un `Callout`.** Es un error de validación, no un aviso, y es el hueco donde
   el frontend inyecta la línea "esto te sirve para X" derivada de `goal` (§6.2 Q2). Sin esta regla la
   promesa de la pregunta 2 no tenía ningún sitio donde materializarse.

**Heurística de calidad (no regla del contrato):** dos componentes hermanos con similitud de tokens
> 0.8 dicen lo mismo dos veces (efecto de redundancia). `validate_ui` lo anota en el log estructurado
y en `node_renders.error_message` como aviso, **y no rechaza el spec**. Se deja explícitamente
fuera del contrato porque medir "decir lo mismo en dos formatos" con similitud de tokens tiene
falsos positivos obvios (una tabla que resume los pasos que el texto acaba de enumerar es
redundancia buena). Si los datos de §14.2 muestran que ocurre a menudo con daño real, se promueve a
error; hasta entonces no se presenta como contrato cumplido.

`answer_key`, guardado aparte y nunca serializado al cliente:

```json
{"q1": {"item_type": "test", "correct": 1,
        "explanation": "Manual p.3: pasados 30 días aplica la garantía del fabricante",
        "bloom_level": "apply"}}
```

### 5.3 El SkillNet UI Kit — lista congelada

**Actualizado el 2026-07-26.** Dónde vive cada cosa desde la adopción:

* `apps/skillnet-web/src/components/courses/kit/` — **el catálogo, en zod + `defineComponent`**. Es de
  donde sale el prompt: `scripts/generate-openui-prompt.mjs` llama a `library.prompt()` y escribe
  `apps/skillnet-api/src/render/openui_prompt.txt` + `openui_catalog.json`. Un solo sitio donde se
  declara la lista.
* `src/render/kit.py` — **fuente de verdad de la validación** (tipos, enums, orden posicional, las 7
  reglas vía `src/render/spec.py`). Ya **no** genera el prompt. `tests/test_render_prompt_artifact.py`
  recalcula el digest del catálogo desde aquí y falla si el artefacto no coincide: es la alarma de
  deriva entre los dos lados, y la que avisará el día que su API cambie.
* `apps/skillnet-web/src/components/courses/blocks/` — la implementación React, que ahora se registra
  en la librería de OpenUI en vez de despacharse por `switch`.

La librería del navegador registra **diez** componentes y el catálogo del prompt anuncia **nueve**:
`Markdown` lo escribe el servidor para `fallback_seed` y el modelo no puede emitirlo. Como el
navegador ya recibe dialecto, el fallback también necesita forma de dialecto, así que `serialize()`
cubre los diez y `parse()` sigue rechazando `Markdown`. La asimetría no desapareció: cambió de sitio.

| Componente | Props (orden **posicional** para el dialecto OpenUI) | Para qué |
|---|---|---|
| `Stack` | `children: string[]`, `gap: "sm"\|"md"\|"lg"` | Contenedor vertical |
| `TextContent` | `text: string`, `variant: "body"\|"lead"\|"caption"` | Prosa |
| `Card` | `title: string`, `children: string[]` | Agrupar |
| `Callout` | `tone: "info"\|"warn"\|"success"`, `text: string` | Regla crítica, excepción |
| `StepSequence` | `title: string`, `steps: string[]` | Procedimiento (2-7 pasos) |
| `Table` | `headers: string[]`, `rows: string[][]` | Comparar conceptos |
| `CodeBlock` | `language: string`, `code: string` | Ejemplo de código |
| `Chart` | `kind: "bar"\|"line"`, `title: string`, `labels: string[]`, `values: number[]` | Dato cuantitativo |
| `QuizItem` | `item_id: string`, `item_type: exercise_type`, `bloom_level: string`, `question: string`, `options: string[]` | Ejercicio |
| `Markdown` | `content: string` | **Sólo** para `fallback_seed`. El LLM no puede emitirlo |

Decisiones de nomenclatura, cerradas: `StepSequence` (no `StepList`); `Chart` unificado con `kind`
(no `BarChart`/`LineChart`); `Callout` entra porque las excepciones de procedimiento son el 80 % del
contenido de compliance; `Timeline`, `ImageCard`, `DragDrop`, `Simulation` y `SandboxHTML` **no
entran**.

Los 6 valores de `item_type` son exactamente los del enum `exercise_type` existente.

**`QuizItemBlock` es autónomo; no es un puente al `ExerciseRenderer` de v1.** La afirmación anterior
("se reutilizan tal cual, cambiando sólo el hook de envío") era falsa: cada uno de los seis
componentes de ejercicio construye **sus propias** mutaciones y se apoya en el id de una fila real de
`exercises` — p. ej. `TestExercise.tsx:3` importa `useSubmitAttempt`/`useCorrectExercise`, las llama
en las líneas 10-11, hace `correctMut.mutate(exercise.id)` y usa `name={exercise.id}` para el grupo de
radios. Convertirlos en componentes controlados exigiría refactorizar los seis para aceptar handlers
inyectados: superficie v1 que ningún lote presupuesta. **Decisión:** B6 escribe
`QuizItemBlock.tsx` con su propio estado y su propio envío contra `POST /nodes/{id}/answer`
(2 subcomponentes internos para selección única y texto), y **no toca `src/components/exercises/`**.
Se acepta la duplicación de ~120 líneas de UI a cambio de no tocar v1.

### 5.4 La interfaz del adaptador

`src/render/backends/base.py`

```python
class RenderBackend(Protocol):
    name: str                                    # "openui" (el registro admite más)

    # prompt_fragment() SE ELIMINÓ el 2026-07-26: el prompt lo genera library.prompt()
    # en el paso de build y lo lee src/render/prompt.py. Un backend valida un dialecto
    # y lo vuelve a escribir; ya no lo enseña.

    def parse(self, raw: str, *, ui_format: str | None = None) -> UISpec:
        """Parsea el dialecto completo. Lanza RenderParseError."""

    def parse_partial(self, raw: str, *, ui_format: str | None = None) -> UISpec:
        """Parseo tolerante de salida incompleta (streaming). Descarta la última
        línea si está a medias. Nunca lanza. Sigue siendo necesario en el servidor
        aunque el navegador también parsee: lo que se le manda en streaming es la
        re-serialización canónica del prefijo, nunca los bytes del modelo."""

    def serialize(self, spec: UISpec) -> str:
        """Spec -> texto canónico. Lo ÚNICO que el cliente puede recibir."""
```

```python
# src/render/backends/__init__.py
_BACKENDS = {"openui": OpenUiLangBackend()}      # un solo dialecto en este PR

def get_render_backend(name: str | None = None) -> RenderBackend:
    return _BACKENDS[(name or settings.RENDER_BACKEND)]
```

**El parseo de validación es Python, en el backend; el de pintado es JavaScript, en el navegador.**
De las tres consecuencias que este párrafo reclamaba, (b) sigue en pie — las fixtures cubren el parser
sin navegador — y las otras dos cambiaron el 2026-07-26: (a) **sí** entran dependencias npm
(`@openuidev/react-lang@0.2.9`, `@openuidev/lang-core@0.2.10`, `zod@4.4.3`, versiones exactas), y (c)
**el navegador ya no recibe JSON**, recibe dialecto. Lo que ocupa el sitio de (c) son las tres
propiedades y los cuatro controles de §5.1.

**Backend 1 — `openui` (DEFAULT).** `src/render/backends/openui.py`. Dialecto línea a línea, una
declaración por línea, argumentos **posicionales** en el orden de la tabla del kit, referencias por
array:

```
root = Stack([intro, steps, quiz], "md")
intro = TextContent("Las devoluciones se aceptan durante 30 días naturales.", "body")
steps = StepSequence("Proceso de devolución", ["Verificar el producto", "Escanear el ticket", "Registrar en el sistema", "Emitir el reembolso"])
quiz = QuizItem("q1", "test", "apply", "Un cliente vuelve el día 32. ¿Qué haces?", ["Aceptar la devolución", "Ofrecer garantía del fabricante", "Rechazar sin más", "Llamar al encargado"])
```

Elegido como default por densidad de tokens (≈50 % menos que JSON equivalente) y porque el formato
línea a línea permite `parse_partial` trivial: cada `\n` completa un componente. El nombre de la
variable es el `id` del componente en la IR.

**Gramática congelada.** Vive en el docstring de `src/render/backends/openui.py` y ya **no** es una
constante `GRAMMAR` que se pegue en el prompt: el bloque de sintaxis lo pone `library.prompt()`. Sigue
siendo la especificación de la puerta, y es lo que hace que la reactividad sea **inexpresable** en vez
de estar en una lista negra. Un dialecto "obvio" con un ejemplo y sin reglas es lo que un modelo de 8B
rompe el primer día; estas tres son exactamente las que rompe, y van al prompt por
`additionalRules`:

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
char       = <cualquier carácter excepto '"', '\' y newline> ;
number     = [ "-" ] digit { digit } [ "." digit { digit } ] ;
```

**`arg = … | call` es de 2026-07-27** (`docs/design/openui-adoption.md` §4 bis). Una llamada anidada
en línea, `root = Stack([TextContent("Hola.", "lead")], "md")`, es OpenUI Lang válido y el bloque de
firmas que genera `library.prompt()` la ofrece; rechazarla era un subconjunto nuestro, no una regla
del estándar, y le costó el bucle de reparación entero a un modelo de 7B. `parse` la **aplana** a la
lista plana de la `UISpec` con ids sintéticos deterministas (`root_1`, `root_1_1`, …), así que la
regla 4 de §5.2 se cuenta después de aplanar; sólo tiene sentido donde el kit declara un `ref[]`
(`Stack.children`, `Card.children`) y en cualquier otra posición es un error con nombre propio; y la
profundidad por línea está topada (16) para que la recursión no sea un vector de caída. `serialize`
sigue emitiendo **sólo** la forma referenciada: es la forma canónica, es la que su prompt recomienda
para streaming y es la única que da a cada bloque un `statementId` real en el navegador.

Las tres reglas que el prompt repite en imperativo y que las fixtures malformadas cubren una a una:

1. **Comilla doble dentro de un string: `\"`.** Nunca sin escapar.
2. **Arrays anidados permitidos y obligatorios en `Table.rows`** (`string[][]`):
   `Table("t", ["A","B"], [["1","2"],["3","4"]])`.
3. **Ningún salto de línea literal dentro de un string** — se escribe `\n`. Es una restricción
   dura, no estética: toda la premisa de `parse_partial` es que cada `\n` cierra un componente, así
   que un salto literal dentro de una comilla rompe el parseo incremental, no sólo el completo.
   `parse()` rechaza el string sin cerrar al final de línea; `parse_partial()` descarta esa línea.

**No hay segundo backend en este PR.** El seam sí entra (el `Protocol` y el registro), el segundo
dialecto no — ver §1.3 para la razón (`UIDL/1` no puede representar la `UISpec`). Consecuencias
concretas, todas aplicadas más abajo: `RENDER_BACKEND_FALLBACK` desaparece de §10.2; el
"reintento cruzado" desaparece de §14.1; y `tests/test_render_a2tl.py` no existe.

**Qué ocupa su sitio como segundo intento** (que era el valor real del reintento cruzado): en el
reintento (`MAX_UI_RETRIES = 2`) el prompt no es el mismo. Se envía
`UI_REPAIR_SYSTEM`, que incluye el `raw_dsl` fallido, los `validation_errors` exactos del parser y la
instrucción de devolver el programa corregido y nada más, con `temperature=0.0`. Reparar con el error
en mano es más efectivo que reintentar a ciegas o cambiar de dialecto. Si también falla:
`fallback_seed`. La red de seguridad de "nunca una pantalla roja" la da `fallback_seed`, no el
segundo dialecto.

### 5.5 Lado frontend

> **CORREGIDO el 2026-07-26.** El despacho por `switch` sobre una `UiSpec` lo sustituye el
> `<Renderer>` de `@openuidev/react-lang` sobre la librería de
> `src/components/courses/kit/`: los mismos diez componentes de bloque, registrados en vez de
> despachados, y el streaming lo lleva `isStreaming`. Las props que **no** se pasan son parte del
> contrato de seguridad (§5.1): sin `toolProvider`, sin `onAction`, sin `onStateUpdate`. El bloque de
> abajo describe la forma anterior y se conserva porque las zonas de estabilidad espacial, el pinning
> de `active_render_id` y las dos afordancias de control **no cambian**.

`apps/skillnet-web/src/components/courses/UiSpecRenderer.tsx` — mismo patrón de dispatch que
`ExerciseRenderer`:

```tsx
export function UiSpecRenderer({ spec, nodeId }: { spec: UiSpec; nodeId: string }) { … }
// switch (component.type) → blocks/StackBlock, TextContentBlock, CardBlock,
//   CalloutBlock, StepSequenceBlock, TableBlock, CodeBlockBlock, ChartBlock,
//   QuizItemBlock, MarkdownBlock
```

`ChartBlock` se dibuja con SVG inline (no se añade Chart.js ni Recharts). `MarkdownBlock` reutiliza
`LessonContent`, que se conserva intacto y pasa a ser también el fallback. Un componente de tipo
desconocido renderiza `null` y registra un aviso — nunca rompe la página.

**Zonas de estabilidad espacial**, obligatorio en `NodeView.tsx`:

| Zona | Contenido | Puede cambiar |
|------|-----------|---------------|
| Congelada | Header, título del nodo, `ProgressBar`, botones anterior/siguiente, acceso al chat | Nunca |
| Estable | Orden y contenido de los bloques **mientras el nodo está abierto** | Sólo si el usuario lo pide |
| Adaptativa | Qué ejemplos, qué formato, qué profundidad, qué dificultad, **entre** nodos y sesiones | Libremente |

**Cómo se garantiza la fila "Estable"** (antes era una promesa sin mecanismo):
`GET /nodes/{id}/render` sirve `learner_node_states.active_render_id` mientras `render_pinned` sea
`true`. No recalcula la clave, así que responder un ítem no puede cambiar la pantalla, y un refetch de
TanStack Query al recuperar el foco de la ventana devuelve byte a byte lo mismo.

**Control del usuario, dos afordancias mínimas** (no opcionales; son la contrapartida de adaptar
nada):

1. **"Actualizar esta lección"** — un botón en el pie del nodo que hace
   `POST /nodes/{id}/render {"force": true}` y repinta `active_render_id`. Es la **única** vía por la
   que el contenido de un nodo abierto cambia.
2. **"Ver la versión anterior"** — al regenerar, se muestra una línea "esta lección se ha adaptado a
   tus últimas respuestas" con enlace al render previo. Las filas ya existen en `node_renders` y
   `node_render_views` (ordenadas por `first_seen_at DESC`), así que es una consulta, no una tabla
   nueva.

**En una revisita a un nodo ya visto se sirve el último render de ese `(user, node)`**, no uno nuevo,
aunque el perfil haya cambiado. Regenerar requiere el botón.

---

## 6. Onboarding

### 6.1 Forma

5 pantallas, **una pregunta por pantalla**, máximo 3 elementos visibles por pantalla, objetivo
**≤90 segundos**. Saltable en cualquier momento con "Lo hago luego". Se pregunta **una vez**: al
saltar se escribe `onboarding_completed_at` y `onboarding_skipped = true`, y no se vuelve a
preguntar (se puede rehacer desde ajustes). El límite de 5 pantallas y de 3 elementos viene de las
adaptaciones de atención documentadas (tests de 5 preguntas máximo, 3 bullets por pantalla).

**Saltar escribe `experience_level = 'unknown'`, no `'none'`** (§3.3): `'none'` significa "declara ser
novato" y fuerza andamiaje de novato, que es el caso que perjudica al experto. Quien salta no ha
declarado nada.

**Gate en `ProtectedRoute`, con los detalles que importan.** `ProtectedRoute` sólo tiene hoy
`useAuth()` (`user`, `isLoading`), y envuelve **también** todas las páginas de admin, así que:

```
redirige a /onboarding  ⇔  features.dynamic_courses === 'on'
                        ∧  user.role === 'employee'
                        ∧  perfil cargado con onboarding_completed_at == null
```

- El flag se lee de `GET /health` una vez al arrancar (ver §10.1 — **no** de `/auth/me`).
- La query del perfil va **condicionada** a `role === 'employee' && flag === 'on'`, para que un admin
  nunca la dispare.
- Un **404** del endpoint de perfil significa "no redirigir", no "no onboardeado". Si significara lo
  segundo, apagar el flag a mitad de sesión (las rutas pasan a 404) metería al usuario en un bucle de
  redirección hacia una ruta que ya no existe.
- Mientras la query está en vuelo se pinta `AppSkeleton`, nunca se redirige.

### 6.2 Las preguntas

| # | Pregunta (es) | Tipo | Campo | Por qué esta y no otra |
|---|---------------|------|-------|------------------------|
| 1 | "¿Cuál es tu puesto?" | texto libre + 6 sugerencias del sector de la org | `learner_profiles.role_title`, `sector` | El rol entra **literalmente** en el system prompt de `genera_ui` para contextualizar los ejemplos. Es adaptación de **contenido**, la que tiene evidencia fuerte |
| 2 | "¿Para qué quieres usar SkillNet ahora mismo?" | 3 opciones + "otro" | `goal` | Principio de andragogía: el adulto necesita saber el POR QUÉ antes de invertir tiempo. **No viaja al LLM.** Se renderiza como línea de apertura determinista en el bloque `lead` que la regla 7 de §5.2 obliga a que exista (plantilla por valor de `goal`, en el cliente). Así la promesa se cumple siempre, no cuando el modelo se acuerda |
| 3 | "¿Cuánta experiencia tienes en tu puesto actual?" | Ninguna / Algo / Bastante | `experience_level` | El conocimiento previo es la **única** dimensión con efecto grande: invierte el diseño instruccional (los ejemplos resueltos ayudan al novato y **perjudican** al experto). **La pregunta no nombra ningún curso**: el campo es uno por persona (`UNIQUE (user_id)`) y entra en la `cache_key` de *todos* sus cursos, así que preguntar por "Atención al cliente" y luego aplicarlo a "Prevención de incendios" era incoherente. La granularidad por competencia la aporta `user_skills` vía `course_nodes.skill_id` (§7.1), no la declaración |
| 4 | "¿Cómo prefieres estudiar?" | Estándar / Concentración / Ritmo rápido, con una línea de descripción cada uno | `preset` (+ espejo en `users.learning_profile`) | Es **presentación**, no modalidad. Da autonomía real y es reversible sin restricciones |
| 5 | "¿Quieres activar algún ajuste de lectura? (opcional)" | checkboxes: bloques cortos · menos animaciones · más contraste · sin límite de tiempo | `users.accessibility` | Sin diagnóstico, sin etiqueta. **"Leer en voz alta" se elimina**: no hay TTS en este PR ni componente de audio en el kit, y ofrecer una acomodación inexistente es peor que no ofrecerla. "Bloques más cortos" sí es real: se traduce a `effective_density ≤ 2` en el servidor (§3.1) |

### 6.3 Lo que no se fuerza durante este onboarding

- **Nivel inicial mediante test.** El sistema ajusta por rendimiento; el pre-assessment por nodo ya
  hace ese trabajo, y mejor, porque es por competencia y no global.
- **Formato preferido** (¿vídeo, texto, audio?). No se fuerza como pregunta inicial ni se convierte
  en una etiqueta de "estilo de aprendizaje". Sin embargo, cualquier elección explícita posterior
  se respeta y prevalece sobre el `format_vector`. La modalidad pedida puede combinar distintas
  estrategias pedagógicas —recuperación, autoexplicación, contraste o escenario— sin sustituir la
  elección del usuario. Véase [`adaptive-learning.md`](adaptive-learning.md).
- **Diagnósticos de neurodivergencia.** Un diagnóstico es dato de salud (categoría especial,
  art. 9 RGPD) y no hace falta: los ajustes concretos de la pregunta 5 producen el mismo resultado
  funcional sin el riesgo legal. La pregunta 5 pregunta por **necesidades**, no por condiciones.

### 6.4 Periodo de calibración

Con un usuario nuevo el `format_vector` es todo ceros: no hay señal. Regla dura, implementada en
`decide_formato`:

```
if profile["nodes_completed"] < 3:
    vector_bucket = ""                          # no entra en la cache_key
    ui_format = node.default_ui_format          # columna real, §3.2 — no se llama a decide_formato
    # el prompt recibe SOLO: role_title, sector, experience_level, preset,
    # effective_density y scaffold_band
```

**Qué significa exactamente "no se adapta", con la frontera dibujada** — la versión anterior decía "no
se adapta la presentación" mientras §4.2 metía `node_state` completo en el prompt desde el nodo 1, lo
cual se contradecía:

| Dimensión | ¿Actúa durante la calibración? |
|---|---|
| **Formato** (`ui_format`: explicación vs ejercicio vs tabla) | **No.** Se usa `node.default_ui_format` |
| **Bucket de vector implícito** (`vector_bucket` en la clave y en el prompt) | **No.** Los eventos se acumulan y no se usan |
| **Contenido** (rol, sector, fuente) | **Sí**, desde el primer nodo |
| **Andamiaje** (`scaffold_band`, `last_error_kind`, `consecutive_failed`) | **Sí.** Es dificultad y apoyo, no disposición espacial: responder al error del alumno no mueve la interfaz de sitio |

La razón de la primera fila es la lección del fracaso de los menús adaptativos de Office 2000-2003: el
usuario debe formar su mapa mental antes de que la interfaz empiece a moverse.

**Distribución esperada de nodos y su consecuencia incómoda.** Un curso de compliance típico tiene
**3-6 nodos**; los cursos de proceso, 6-12. Con un curso de 3 nodos y una sola asignación, el
subsistema de `format_vector` (endpoint de eventos, decaimiento, normalización L1, `vector_bucket`,
purga a 90 días) **no influye en un solo render**: el usuario acaba el curso todavía en calibración.
Se acepta a sabiendas — el vector es infraestructura para el segundo y tercer curso, no para el
primero — y por eso los nodos saltados por el probe **no** incrementan `nodes_completed` (§3.3): si lo
hicieran, alguien podría salir de la calibración con cero eventos de interacción y el vector se
aplicaría sobre ruido.

---

## 7. Pre-assessment y regla de maestría

### 7.1 Los ítems

Al abrir un nodo, `POST /nodes/{node_id}/probe` devuelve **2 ítems** (3 en nodos `critical`):

- **Ítem A — `bloom_level = "apply"`**, de tipo `test` con exactamente **4 opciones**. Un caso, no
  una definición. Es el que decide.
- **Ítem B — `bloom_level = "understand"`**, de tipo `test` con exactamente **4 opciones**.
  **Ya no se admite `true_false`**: con verdadero/falso el suelo del azar sube de 6.25 % a 12.5 %, y
  el número que §7.2 usa para justificar la banda de duda dejaba de ser cierto.
- **Ítem C (desempate)** — respuesta **construida**: `fill_blank` o `practical_case` corto. En un nodo
  `critical` es **obligatorio siempre**; en el resto sólo si el veredicto cae en la banda de duda.

Origen de los ítems, por orden de preferencia:

1. **Pre-generados en la validación del esquema** y guardados en `course_nodes.probe_items` /
   `probe_answer_key` (§3.2). Es el caso normal: **cero tokens y cero espera**. Los ítems dependen
   sólo de `(node, source)`, así que una generación por nodo sirve a toda la organización.
2. Si el nodo tiene `seed_lesson_id` y no hay pre-generados, se muestrean ejercicios existentes de esa
   lección con los niveles Bloom pedidos. **Cero tokens.**
3. Último recurso: una llamada LLM (purpose `runtime_fast`, `json_mode`, `max_tokens=500`) desde
   `node.summary` + `source_context`, y se escriben en `course_nodes.probe_items` para que el siguiente
   empleado no la pague.

Se registra el intento en `node_probes` con `answer_key` separado, **una sola fila puntuada por
`(user_id, node_id, schema_version)`** — ver §3.4 para la regla anti-reintento completa, que es lo que
impide saltarse un nodo a base de reentrar hasta acertar por azar.

**Prior desde `user_skills`, en vez de arrancar todo el mundo en 0.** `course_nodes.skill_id` existe y
`user_skills.skill_level` ya lleva un nivel verificado (incluida la verificación por par/responsable).
Al crear `learner_node_states` se siembra:

```python
mastery_prior = {"high": 0.85, "medium": 0.55, "low": 0.25}.get(user_skill_level, 0.0)
```

Es sólo el punto de partida del EWMA y del `scaffold_band`; **no** salta el nodo por sí mismo (eso lo
decide el probe). Hasta ahora §7 sólo escribía en `user_skills` y nunca lo leía, desperdiciando la
única señal de dominio previo que el producto ya tenía.

**Probe diagnóstico para el novato declarado.** Si `experience_level == 'none'` y
`nodes_completed == 0`, el probe del primer nodo se sirve con `scored = false`: se presenta como
"vamos a ver qué te suena ya", **no persiste fallos**, no puntúa maestría y no consume el intento
único. Sin esto, la primera experiencia del producto para quien acaba de declararse novato son N×2
fallos garantizados antes de ver una sola línea de contenido.

### 7.2 La regla, computable

**Punto de partida honesto:** los cuatro tipos deterministas puntúan **0.0 o 1.0**, sin crédito
parcial (verificado en `exercise_service.py:25-57`, `fill_blank` incluido). Con dos ítems binarios,
`0.6a + 0.4b` sólo puede valer `{0.0, 0.4, 0.6, 1.0}`. Consecuencia de la versión anterior de esta
regla: los tres umbrales (0.90 / 0.80 / 0.70) **se comportaban idénticamente** — 1.0 dominaba en los
tres, 0.6 caía en desempate en los tres, 0.4 y 0.0 aprendían en los tres — y el desempate
`0.5a+0.2b+0.3c` topaba en **0.80**, por debajo del 0.90 de `critical`, así que en un nodo crítico era
código muerto: una llamada LLM y una pregunta extra que no podían cambiar el veredicto.

```python
# src/services/mastery_service.py

THRESHOLDS = {"critical": 0.90, "recommended": 0.80, "contextual": 0.70}
DOUBT_BAND_FLOOR = 0.55
W_APPLY, W_UNDERSTAND = 0.6, 0.4
# Desempate renormalizado: un tercer ítem perfecto llega a 1.0, así que
# TODOS los umbrales son alcanzables y ninguno es inalcanzable.
W3_APPLY, W3_UNDERSTAND, W3_CONSTRUCTED = 0.45, 0.15, 0.40
FADING_STREAK = 3             # N
REGRESS_STREAK = 2

def probe_estimate(score_a: float, score_b: float) -> float:
    return W_APPLY * score_a + W_UNDERSTAND * score_b

def probe_verdict(score_a, score_b, criticality, threshold=None):
    """Veredicto con SÓLO los dos ítems de respuesta seleccionada."""
    est = probe_estimate(score_a, score_b)
    if score_a < 0.5:                       # falla aplicar → nunca domina
        return "learning", est
    if est >= 1.0:
        # Todo correcto. En un nodo critical NO basta: el azar aquí es 1/16.
        if criticality == "critical":
            return "tiebreak", est
        return "mastered", est
    if est >= DOUBT_BAND_FLOOR:             # 0.6 → duda
        return "tiebreak", est
    return "learning", est

def tiebreak_mastery(score_a, score_b, score_c) -> float:
    return W3_APPLY * score_a + W3_UNDERSTAND * score_b + W3_CONSTRUCTED * score_c

def tiebreak_verdict(score_a, score_b, score_c, criticality, threshold=None):
    m = tiebreak_mastery(score_a, score_b, score_c)
    thr = threshold if threshold is not None else THRESHOLDS[criticality]
    return ("mastered" if m >= thr else "learning"), m
```

Aritmética resultante, comprobada (`tests/test_mastery.py` la asserta caso por caso):

| a | b | c | `tiebreak_mastery` | critical 0.90 | recommended 0.80 | contextual 0.70 |
|---|---|---|---|---|---|---|
| 1 | 1 | 1 | **1.00** | domina | domina | domina |
| 1 | 0 | 1 | **0.85** | aprende | domina | domina |
| 1 | 1 | 0 | **0.60** | aprende | aprende | aprende |
| 1 | 0 | 0 | **0.45** | aprende | aprende | aprende |

Los umbrales ahora **discriminan de verdad** y ninguno es inalcanzable. Cuatro reglas que hacen esto
defendible:

1. **No se puede dominar fallando el ítem de aplicar** (`score_a < 0.5` → `learning`, sin más).
2. **En probe de dos ítems seleccionados, el veredicto honesto es "todo correcto = candidato".** Se
   dice así en lugar de fingir que un umbral continuo discrimina sobre cuatro valores posibles. El
   umbral por criticidad hace su trabajo real en dos sitios: decidiendo si hace falta confirmación
   construida, y en la transición `learning → mastered` de §7.3.
3. **En un nodo `critical`, `mastered` nunca sale de respuesta seleccionada.** El desempate construido
   es obligatorio. Azar combinado: 1/16 × ~0 ≈ 0. Junto con el probe único por versión de esquema
   (§3.4), saltarse un nodo de seguridad por suerte deja de ser una estrategia.
4. **El umbral depende de la criticidad**, no de la persona.

### 7.3 Maestría durante el nodo

Tras cada `POST /nodes/{node_id}/answer`:

```python
ALPHA = 0.4      # peso de la evidencia nueva (EWMA)

mastery_new = (1 - ALPHA) * mastery_old + ALPHA * score
if passed:
    consecutive_correct += 1; consecutive_failed = 0
    # TECHO DE MAESTRÍA: sin esto el EWMA converge a la media de los scores,
    # así que quien puntúa 0.85 de forma sostenida asintota en 0.85 y NUNCA
    # alcanza el 0.90 de un nodo critical -> curso imposible de completar.
    if consecutive_correct >= FADING_STREAK:
        mastery_new = max(mastery_new, node.mastery_threshold)
else:
    consecutive_failed += 1; consecutive_correct = 0
    mastery_new = min(mastery_new, mastery_old)     # un fallo nunca sube la maestría
```

El techo es la corrección de un fallo aritmético real: `mastery_new = 0.6·old + 0.4·score` tiene punto
fijo en `score`, así que el alumno competente-pero-imperfecto (0.85 sostenido) se quedaba a 0.05 del
umbral para siempre, y como `enrollments.status='completed'` exige **todos** los nodos `critical` en
`mastered`, el curso quedaba permanentemente incompleto sin ninguna vía de salida. Con el techo, tres
aciertos consecutivos *son* la evidencia suficiente: es la misma racha que ya se exigía, aplicada
también a la magnitud y no sólo al contador.

Transiciones de `node_state`, deterministas y **completas** (las 8 que cubre
`tests/test_mastery.py`):

| # | Desde | Condición | Hacia | Efectos |
|---|-------|-----------|-------|---------|
| 1 | `not_started` | se pide el probe | `probing` | `first_seen_at`, `mastery` = prior de `user_skills` (§7.1) |
| 2 | `probing` | `probe_verdict == "mastered"` | `mastered` | `probe_score = est`; `mastery = max(prior, est)`; `mastered_at`; **`nodes_completed` NO se incrementa** |
| 3 | `probing` | `probe_verdict == "tiebreak"` | `probing` | `tiebreak_used = true`; se sirve el ítem C; `probe_score` sin escribir aún |
| 4 | `probing` | `tiebreak_verdict == "mastered"` | `mastered` | `probe_score = m`; `mastery = max(prior, m)`; `mastered_at` |
| 5 | `probing` | `probe_verdict`/`tiebreak_verdict == "learning"` | `learning` | `probe_score` escrito; **`mastery` NO se toca** (queda el prior); `scaffold_band` congelado |
| 6 | `learning` | `mastery >= threshold` **y** `consecutive_correct >= 3` | `mastered` | `mastered_at`; `nodes_completed += 1` |
| 7 | `learning` | `consecutive_failed >= 2` | `learning` | baja dificultad, no cambia de estado; señal `reforzar_con_ejemplo` |
| 8 | `learning` | 4.º fallo del mismo ítem tras 3 pistas (§7.4) | `needs_review` | solución trabajada mostrada; el nodo entra en la cola de práctica |

Dos ambigüedades que quedaban abiertas y que afectan a certificados, cerradas arriba: **`mastery` tras
un probe** se escribe sólo si el veredicto domina (`max(prior, estimate)`), y si el veredicto es
`learning` se conserva el prior — de modo que `probe_score` y `mastery` no se pisan; y
**`nodes_completed`** se incrementa sólo en la transición 6. Sin fijar ambas, `enrollments.score`
(media de `mastery` sobre nodos `critical`) variaba según detalles de implementación, y eso sale
impreso en un certificado.

**`mastered → needs_review` no existe en este PR**: requeriría el scheduler de repetición espaciada,
que no está en el repo (§1.3). El único productor de `needs_review` es la transición 8.

**`FADING_STREAK = 3` y `REGRESS_STREAK = 2`**, fijos, iguales para toda criticidad. Se elige el
valor que ya aparece en la investigación (3 aciertos suben, 2 fallos bajan) y no se parametriza por
skill hasta tener datos reales.

Exigir a la vez `mastery >= threshold` **y** una racha de 3 evita el problema central del
*cognitive offloading*: con contenido generado por IA el alumno reporta menos carga cognitiva pero
produce respuestas más débiles — la "ilusión de dominio". Una racha exige generación repetida, no
un pico afortunado.

### 7.4 Escalada de andamiaje

Reglas duras en el prompt de `genera_ui` y en el servicio, no sugerencias:

- **`attempt-before-hint`**: no se ofrece pista hasta que hay al menos un intento registrado en
  `node_attempts` para ese `item_id`. **Un clic-para-explicar dentro de un `QuizItem` sin responder
  cuenta como pista** y consume cupo — ver §8.5, donde antes era una vía de escape que no tocaba
  `hints_used`.
- **Tope de pistas: 3, y con salida definida.** Al cuarto fallo se muestra la solución trabajada
  completa y el nodo pasa a **`state = 'needs_review'`** (no `'learning'`), lo que le da tres cosas que
  antes no tenía — la versión anterior decía "se pasa de nodo" sin definir **ningún** camino de vuelta:
  1. **Visibilidad**: `NodeListRead` expone `needs_practice: true` y el nodo aparece en una sección
     "para practicar", en lugar de desaparecer.
  2. **Reentrada**: se puede reintentar en cualquier momento (`POST /nodes/{id}/render {force:true}`
     regenera con `last_error_kind` en el prompt) y **re-probar** pasados 7 días (§3.4).
  3. **Vía humana**: `POST /nodes/{node_id}/waive` (rol admin o responsable) pone `mastered` con
     `waived_by`/`waived_at` y una fila en `audit_log` (`action='node_waived'`). Es coherente con el
     principio "si sabes, sabes" del producto: un humano que ha visto trabajar a la persona puede
     acreditarla, y queda registrado quién lo hizo.
  Mientras un nodo `critical` esté en `needs_review`, `enrollments.status` **se queda en `active`** y
  `NodeListRead.can_complete` es `false` con el nodo listado en `blocked_by`. El curso no se completa
  en silencio ni se bloquea en silencio: se ve por qué.
- **Clasificación del error** → `last_error_kind`, que entra en el siguiente `genera_ui`:
  `detail` (typo/formato) → corregir y seguir; `procedural` → señalar el paso exacto y repetir;
  `conceptual` → una sola pregunta socrática sobre la parte errónea.
- **No intervenir por defecto.** Si `consecutive_correct >= 1` y no hay señal de sobrecarga, el
  siguiente render no añade andamiaje ni explicaciones extra. El silencio es la opción por defecto.
- **Sin límite de tiempo** en ningún ítem. La presión temporal aumenta la carga cognitiva
  extrínseca.

### 7.5 Cierre del curso

`enrollments.status = 'completed'` cuando **todos los nodos `critical` no archivados del curso están
en `mastered`** (por dominio, por probe o por `waive`). Los `recommended` y `contextual` no bloquean.
`enrollments.score` = media de `learner_node_states.mastery` sobre esos nodos `critical`.
`_assign_course_skills` sigue otorgando `user_skills` con la traducción `mastery → skill_level` de
§3.3 y sin degradar nunca.

**Recálculo obligatorio al cambiar el esquema.** `PUT /courses/{id}/schema` cambia el conjunto de
nodos `critical`, que es precisamente lo que gobierna la condición de cierre. En la misma transacción
del `PUT` (y del `validate`) se recalcula la condición para **todas** las matrículas activas del
curso: un curso ya completado puede volver a `active` si el creador añade un nodo `critical` nuevo, y
uno bloqueado puede completarse si el nodo que faltaba se archiva. Se registra en `audit_log`. Sin
esto, el estado de las matrículas quedaba en función de un esquema que ya no existe.

---

## 8. Clic-para-explicar (Curio)

### 8.1 Qué se porta y qué no

| Se porta | Destino | Nota |
|---|---|---|
| `tokenize()` + `TOKEN_RE` + `Token` | `apps/skillnet-web/src/lib/tokenize.ts` | Función pura, sin dependencias. Se copia con su regex `/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*|[^\p{L}\p{N}]+/gu` |
| `toClickable()` | `src/components/courses/ClickableText.tsx` | Envuelve cada token clicable en `<span className="entity">` |
| Patrón `clickify()` sobre nodos de texto ya renderizados | `ClickableText` + `LessonContent` | **La clave del port**: nunca se tokeniza el markdown crudo, sólo los hijos `typeof child === 'string'` del árbol ya construido. Por eso la estructura no se rompe |
| `ClickableSurface` (un único listener con `onClick` + `onMouseUp`) | `src/components/courses/ClickableSurface.tsx` | Con el ref `justDragged` y su `setTimeout(…, 0)` |
| `expandRangeToWords()` | `src/components/courses/ClickableSurface.tsx` | Snap a palabra completa en selecciones |
| `cleanDescription()` | `src/llm/prompts/explain.py` (**Python**) | La limpieza se hace en el servidor, antes de cachear |
| Prompt de descripción | `src/llm/prompts/explain.py` | Sin etiquetas en mayúsculas (los modelos pequeños las repiten) |
| **NO** se porta `useGenerative` | — | Dispara 4 generaciones LLM por clic. Sólo se quiere el vistazo |
| **NO** se porta `@floating-ui/react` | — | Dependencia nueva. Posicionamiento manual estilo `Overlay.tsx` de la extensión, con `framer-motion` que ya está |
| **NO** se porta el hover | — | Solo clic y selección. El hover con debounce está prometido en la documentación de Curio pero no implementado, y dispararía coste sin intención del usuario |

### 8.2 Correcciones obligatorias respecto al original

Estos tres son bugs reconocidos del original y **no** se replican:

1. **`STOPWORDS` en español y en inglés.** La lista original es sólo inglesa, con lo que en un
   texto español `de`, `la`, `que` serían clicables y `the`, `of` no. Se define
   `STOPWORDS_ES` (~120 palabras función) ∪ `STOPWORDS_EN`.
2. **La clave de caché incluye el contexto.** `(org_id, term_normalized, context_hash, language)`
   — ver §3.4. Sin el `context_hash` la función contradice su propia premisa.
3. **Accesibilidad de teclado.** Las palabras no llevan `tabindex` (inundaría el orden de
   tabulación de un nodo largo). Se implementa **roving tabindex sobre el bloque**: cada bloque de
   texto es `tabindex="0"` con `role="group"`, y dentro de él las flechas ←/→ mueven un cursor
   lógico entre palabras clicables, Enter/Espacio abre la explicación. El `<span>` activo recibe
   `aria-expanded="true"` y hay una regla `:focus-visible` real. Se añade
   `@media (prefers-reduced-motion: reduce)` a las animaciones del popover, que también falta en el
   original.

### 8.3 El contexto que se envía

- **Contexto de bloque**: se sube al bloque más cercano con
  `BLOCK_SELECTOR = 'p,li,h1,h2,h3,h4,h5,h6,blockquote,td,th,dd,dt'`, se normalizan los espacios
  (`.replace(/\s+/g,' ').trim()`) y se recorta a **600 caracteres centrados en el término**, no los
  primeros 600. Corregido respecto al original: en un bloque largo, el término clicado puede
  quedar fuera del contexto enviado al modelo, que es exactamente el peor fallo posible.
- **Contexto de nodo**: `node_id` (el servidor añade `node.title` y `node.summary`). Sustituye al
  `messageId`/último turno de usuario de Curio, que aquí no aplica.

### 8.4 Cómo se sirve

`POST /api/v1/explain` con `Accept: text/event-stream`.

1. Se normaliza el término (`trim().toLowerCase()`) y se calcula `context_hash`.
2. **Hit en `term_explanations`** → se emite un único evento `token` con el texto completo y
   `done`; se incrementa `hit_count` y `last_used_at`. Latencia ~10 ms, coste 0.
3. **Miss** → `LLMService.stream()` con purpose `runtime_fast`, `temperature=0.2`,
   `max_tokens=80`. Se acumula, se pasa por `clean_explanation()` en cada delta y se emite
   `token`. Al terminar se persiste.
4. Rate limit: 30 explicaciones por usuario y minuto, en memoria del proceso. Por encima, `429` y
   el popover muestra "Demasiadas consultas seguidas".
5. **Dos límites, no uno**: más de **140 caracteres** → `422` (una selección accidental de medio
   párrafo no es un término). Entre **61 y 140** caracteres → se explica pero **no se persiste**
   (`term_explanations` sólo cachea ≤60 caracteres **y** ≤4 tokens, §3.4). Guardar frases elegidas por
   el usuario en una fila sin `user_id`, sin ventana de retención y sin endpoint de borrado
   contradecía la propia promesa de privacidad de §3.3.

Prompt (`EXPLAIN_SYSTEM`, en `src/llm/prompts/explain.py`): **exactamente una frase corta**, sin
markdown, sin preámbulo, sin repetir la instrucción, **en el idioma del texto**, explicando el
término en su uso concreto — no traduciéndolo. Sin etiquetas en mayúsculas tipo `TERM:`.

El popover **no** es recursivamente clicable (su contenido se pinta como texto plano). Evita bucles
de generación y no aporta. **Sí** lleva una acción: **"No lo entiendo"**, que abre el chat v1 ya
existente sembrado con el término, el texto del bloque y el `node_id`. Es la salida para quien no
entiende la frase única, que de otro modo no tenía siguiente paso: el chat vive en otra ruta y no
conoce el contexto del nodo.

### 8.5 Dónde se monta y qué clics NO cuentan

`NodeView.tsx` envuelve `<UiSpecRenderer>` en `<ClickableSurface nodeId={nodeId}>`.
`ClickableText` se aplica dentro de `TextContentBlock`, `CalloutBlock`, `StepSequenceBlock`,
`TableBlock`, `CardBlock` (títulos incluidos).

**Regla de hit-test, explícita.** `ClickableSurface` es **un único** listener sobre todo el subárbol, y
ese subárbol ya no es prosa de chat: contiene botones, radios e inputs. El patrón original de Curio
nunca tuvo que distinguir "clic en una palabra" de "clic en un control", y `justDragged` sólo separa
arrastre de clic. Sin una regla, responder una opción de test disparaba **también** la explicación.
Primera línea del handler:

```ts
if ((e.target as HTMLElement).closest(
      'button, a, input, textarea, select, label, [role="radio"], [role="button"], [data-no-explain]'
    )) return;
```

- **`QuizItemBlock` entero lleva `data-no-explain`**: enunciado **y opciones**. La versión anterior sólo
  excluía el enunciado, y las **opciones** son justamente la parte que filtra la respuesta — clicar una
  palabra dentro de la opción correcta devuelve una explicación contextual de ella.
- **`CodeBlockBlock`** y los enlaces siguen excluidos.
- **Dentro de un `QuizItem` sin responder**, si en el futuro se habilitara explain, **cada explain
  contaría como pista** (`hints_used += 1`, sujeto al tope de 3 y a `attempt-before-hint`). Hoy está
  simplemente deshabilitado, que es la versión segura de la misma regla: un explain gratis era una
  pista no contabilizada que además alimentaba el peso más alto del vector (+0.30).
- Test obligatorio en `ClickableSurface.test.tsx`: **clic en el botón de una opción no produce ninguna
  petición a `/explain`**.

---

## 9. Estrategia de latencia

Tres capas, en este orden.

### 9.1 El pre-assessment ES la espera productiva

La contradicción "el pre-assessment y la pantalla de espera ocupan los mismos primeros segundos" se
resuelve fusionándolos:

**Requisito previo, sin el cual esto no funciona:** los ítems del probe están **pre-generados** en
`course_nodes.probe_items` desde la validación del esquema (§3.2, §7.1). Si el probe tuviera que
generarse con una llamada LLM al abrir el nodo, la "espera productiva" tendría delante su propia
espera contra una pantalla en blanco — la espera no puede cubrir a la espera. En el caso residual en
que haya que generarlos (nodo sin pre-generar), se muestra `node.summary` más la línea de apertura
derivada de `goal` mientras se generan.

```
t=0     POST /nodes/{id}/probe            → 2 ítems (pre-generados: instantáneo)
t≈0     el usuario lee y responde el ítem A
t=A     POST /nodes/{id}/probe/answer (A) ─┬─► si el veredicto ya no puede ser "mastered",
                                           │   se dispara POST /nodes/{id}/render EN BACKGROUND
                                           └─► el usuario responde el ítem B
t=B     POST /nodes/{id}/probe/answer (B)  → veredicto final
t=B+ε   GET /nodes/{id}/render/stream      → normalmente ya hay bloques listos
```

Responder el ítem B cuesta 10-20 s de atención humana, que es del mismo orden que
`decide_formato` + `genera_ui`. La espera desaparece porque se solapa con trabajo pedagógicamente
útil (el efecto de pre-pregunta tiene un tamaño de efecto notable por sí mismo). Si el veredicto
final sale `mastered`, el render en vuelo se cancela (`asyncio.Task.cancel()`) y se descarta —
coste asumido a cambio de latencia cero en el caso frecuente.

### 9.2 Skeleton y streaming

- **Skeleton**: `NodeSkeleton.tsx` pinta la forma canónica (título + 3 barras de texto + 1 bloque)
  con un shimmer basado en `transform`/`opacity`, no con `animate-pulse` (`motion-system.md:437,636` lo
  prohíbe; se añade un preset `shimmer` a `src/lib/motion.ts`). **Se implementa como componente nuevo
  `ShimmerSkeleton.tsx`, y `src/components/ui/Skeleton.tsx` NO se toca**: ese fichero usa
  `animate-pulse` y se reexporta como `SkeletonText`/`SkeletonCard`/`SkeletonRow` en páginas v1 (más su
  story), así que cambiarlo sería un cambio visible de v1 **con el flag apagado**, contradiciendo
  §10.1. `design-system.md` §Skeleton, que documenta `animate-pulse` como patrón canónico, es el doc
  obsoleto y se corrige en el `chore` de §14.2 #8.
- **Streaming**: `GET /nodes/{node_id}/render/stream` es SSE con estos eventos:

| Evento | Payload | Cuándo |
|--------|---------|--------|
| `render_step` | `{step, message}` | Al entrar en cada nodo del grafo |
| `ui_format` | `{format, tier}` | Tras `decide_formato` — permite cambiar el skeleton por uno de la forma correcta |
| `ui_block` | `{component}` | Cada vez que `parse_partial` completa un componente nuevo |
| `ui_done` | `{render_id, format}` | Al persistir |
| `node_skipped` | `{reason: "mastered"}` | Si el gate salta el nodo |
| `error` | `{step, message, fallback: bool}` | Fallo; si `fallback` es true, el cliente pide el render otra vez y recibirá el seed |

El canal es `f"node:{request_id}"`. Se mantiene `src/core/sse.py` con su limitación conocida (en
memoria, un worker, pierde eventos previos a la suscripción) y **se le añaden dos funciones**, porque
"se reutiliza tal cual" era incompatible con la mitigación: los suscriptores viven en el dict privado
`_registry` (líneas 11-37) y **no hay accesor**, así que esperar "a que haya un suscriptor" no se podía
programar. En **B5**, y `src/core/sse.py` va en su lista de ficheros:

```python
def subscriber_count(channel: str) -> int:
    return len(_registry.get(channel, ()))

async def wait_for_subscriber(channel: str, timeout: float = 0.5) -> bool:
    """True si aparece un suscriptor antes del timeout. Sondeo cada 25 ms."""
```

Con eso: `POST /nodes/{id}/render` devuelve `202 {request_id}`, el cliente se suscribe, y el runner
hace `await wait_for_subscriber(f"node:{request_id}", 0.5)` antes de empezar el trabajo real. Migrar a
`LISTEN/NOTIFY` es backlog, y sólo hace falta con más de un worker de uvicorn (hoy
`docker/api.Dockerfile` arranca con `--workers 1`, coherente).

### 9.3 Caché

Cuatro niveles:

1. **`node_renders` por `cache_key`** (§3.4). Un hit es una consulta SQL: ~5 ms, 0 tokens. Es el
   nivel que hace que el segundo empleado con el mismo perfil no pague generación. La búsqueda es por
   `cache_key` **a secas**, nunca por `user_id`, o el hit rate sería 0.
2. **`active_render_id` por `(user, node)`** (§5.5). Dentro de un nodo abierto y en una revisita no se
   consulta ni la caché: se sirve el render ya fijado. Es el nivel más barato de todos y además es el
   que garantiza estabilidad espacial.
3. **`course_nodes.probe_items`** (§7.1). Los ítems del pre-assessment se generan **una vez por nodo**
   en la validación y sirven a toda la organización. Es la única pre-generación de este PR, y se
   justifica porque no depende del usuario: N empleados, una generación.
4. **`term_explanations`** para clic-para-explicar (§8.4), y **seed v1** como red final:
   `fallback_seed` sirve `lessons.content`. Esto también responde a la compatibilidad con el catálogo
   offline: sin LLM disponible, el curso **sigue funcionando** en modo v1 degradado en lugar de
   romperse.

### 9.4 Ventana anticipada de renders

La generación sigue siendo on-the-fly: la representación no se incorpora al curso al validarlo ni se
produce el recorrido completo. Lo que cambia es el momento de iniciar el trabajo runtime para que la
latencia del modelo no se convierta en latencia visible:

- al abrir el curso se solicitan las **dos primeras lecciones disponibles**;
- al quedar servida la lección actual, `NodeView` solicita las **tres siguientes**;
- al avanzar, esa ventana de tres se desplaza;
- `POST /nodes/{id}/render {force:false}` es idempotente y reutiliza render listo o tarea en curso;
- cada render conserva los mismos pins, claves de política, versiones y reglas de invalidación que si
  se hubiese solicitado al entrar directamente.

La anticipación es por recorrido probable y está acotada; no genera ramas completas ni todos los
componentes posibles. Por tanto, “pregenerado” aquí significa **render runtime adelantado durante la
sesión**, no un artefacto pedagógico persistido dentro de la definición del curso. La autoridad y las
implicaciones para futuros episodios ramificados están en
[`learning-experience-architecture.md`](learning-experience-architecture.md) §2.1.

---

## 10. Elección de camino: sin flag global

> Esta sección describía originalmente un flag `DYNAMIC_COURSES_MODE` de tres valores
> (`off`/`shadow`/`on`) como mecanismo de despliegue progresivo. Ese flag nunca llegó a
> producción: el mecanismo que sí se implementó, y el que hay hoy en `main`, es más simple —
> la elección es **por curso**, sin ninguna variable de entorno de por medio.

`src/services/course_delivery.py::resolve_delivery(course)` es el único punto de decisión:

```python
def resolve_delivery(course) -> Literal["static", "dynamic"]:
    if course.delivery_mode != CourseDeliveryMode.DYNAMIC:
        return "static"
    if course.schema_status != CourseSchemaStatus.VALIDATED:
        return "static"
    return "dynamic"
```

Un curso va por v2 sólo si tiene `delivery_mode='dynamic'` **y** `schema_status='validated'`.
Cualquier otro curso —incluido cualquiera creado antes de que existiera v2— sigue por v1 en la
misma instancia, sin gate ni entorno especial. `GET /api/v1/health` no expone flags de features;
devuelve estado de BD y de embeddings (`src/routes/health.py`). Prohibido consultar
`course.delivery_mode`/`schema_status` para esta decisión en cualquier otro sitio que no sea esta
función.

### 10.1 Flags secundarias

| Env var | Valores | Default | Qué hace |
|---------|---------|---------|----------|
| `RENDER_BACKEND` | `openui` | `openui` | Dialecto que se le pide al LLM y parser que se usa. Un solo valor válido en este PR; la env var existe para que añadir un dialecto no sea un cambio de código de llamada |
| `LLM_RUNTIME_FAST_MODEL` | id de modelo litellm | vacío → `LLM_MODEL` | Tier rápido del router |
| `LLM_RUNTIME_HEAVY_MODEL` | id de modelo litellm | vacío → `LLM_MODEL` | Tier pesado del router |
| `LLM_FIXTURE_DIR` | ruta | `src/llm/fixture_data` | Dónde busca/graba fixtures (§12) |
| `LLM_FIXTURE_MODE` | `replay` \| `record` | `replay` | `record` graba pares (prompt, respuesta) con una clave real |

**`RENDER_BACKEND_FALLBACK` no existe** — se retira junto con el segundo dialecto (§1.3, §5.4). El
reintento único usa `UI_REPAIR_SYSTEM` con el mismo dialecto.

**`LLM_FIXTURE_DIR` apunta dentro del paquete, no a `tests/`.** El default anterior
(`./tests/fixtures/llm`) hacía **imposible** el perfil `fixtures` de `docker-compose.yml`: la imagen de
runtime copia sólo `.venv`, `src`, `alembic`, `alembic.ini` y `pyproject.toml`
(`docker/api.Dockerfile:34-38`), así que `tests/` no está dentro del contenedor y todas las búsquedas
fallarían — justo la promesa de "el flujo completo se demuestra en local sin ninguna clave". Las
fixtures viven en **`src/llm/fixture_data/`**, entran en la imagen con `src` y no hay que tocar el
Dockerfile. Los tests apuntan al mismo directorio.

Todas se documentan en [`configuration.md`](configuration.md), que dice ademas cuales de
ellas llegan de verdad al contenedor: `LLM_FIXTURE_DIR` y `LLM_FIXTURE_MODE` ya no aparecen
en `.env.example`, porque no hay razon para tocarlas.

---

## 11. API

Prefijo `/api/v1`. Auth por cookie de sesión, como todo lo demás. Los guards de rol y de flag se
implementan como dependencias: `require_dynamic_courses(mode_min="shadow")`.

### 11.1 Esquema del curso (admin)

| Método | Ruta | Request | Response |
|---|---|---|---|
| `POST` | `/courses/{course_id}/schema/propose` | `{"source_document_id": uuid \| null, "intent_density": 1..5}` | `202 {"job_id": str}` — **idempotente mientras el trabajo está en vuelo**: si ya hay un job del curso en estado no terminal (`pending`/`schema_proposing`, sin `cancelled_at`) se devuelve **ese mismo `job_id`** en lugar de lanzar otro diseñador. Dos clics no compran dos ejecuciones ni dejan dos runners escribiendo el mismo conjunto de nodos. La lectura la hace `CourseSchemaService.propose`; la carrera real la cierra el índice único parcial `uq_generation_jobs_schema_in_flight` de `0005`. `intent_density` **no** se reescribe al reusar (el job en curso ya lo leyó) |
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
  "warnings": ["Se eliminó un prerrequisito cíclico entre 'Excepciones' y 'Plazos'"],
  "nodes": [{
    "id": "…", "title": "Plazo de devolución", "summary": "…", "outcome": "…",
    "criticality": "critical", "position": 1,
    "mastery_threshold": 0.90, "estimated_minutes": 6,
    "skill_id": "…", "seed_lesson_id": null,
    "source_document_id": "…", "source_headings": ["Devoluciones", "Plazo"],
    "prerequisite_node_ids": []
  }]
}

// CourseSchemaUpdate — reemplazo completo (no PATCH parcial: el orden y el grafo
// deben validarse como un todo). Los nodos sin "id" se crean; los ausentes se
// ARCHIVAN si tienen progreso, se borran si no.
{ "intent_density": 4, "nodes": [ { /* mismos campos, "id" opcional */ } ] }

// 422 SchemaValidationError
{ "detail": { "code": "schema_invalid",
              "errors": [{"code": "cycle", "node_ids": ["…","…"]},
                         {"code": "missing_summary", "node_ids": ["…"]},
                         {"code": "no_critical_node"}] } }

// 422 al editar un esquema ya validado
{ "detail": { "code": "schema_locked",
              "message": "Este esquema está validado. Usa /schema/unvalidate antes de editarlo." } }
```

**El gate no se puede saltar editando después de validar.** Antes, `PUT …/schema` era un reemplazo
completo que subía `schema_version` **sin** tocar `schema_status` ni `delivery_mode`: sobre un curso
vivo y validado, un creador podía añadir nodos nuevos jamás revisados y los empleados recibían
contenido generado para ellos de inmediato — exactamente lo que §1.1 promete que no puede pasar. Tres
reglas, todas bloqueantes:

1. **`PUT …/schema` sobre `schema_status='validated'` devuelve `422 schema_locked`.** Hay que llamar a
   `POST …/unvalidate`, que pone `schema_status='proposed'` **y** `delivery_mode='static'` en la misma
   transacción y escribe `audit_log` (`course_schema_unvalidated`). Es decir: editar un curso vivo lo
   saca de v2 hasta que se vuelva a validar. Explícito y visible, no implícito.
2. **`reviewed_at` por nodo** (§3.2). `POST …/validate` sólo revisa el grafo; un nodo sin
   `reviewed_at` no se sirve nunca (`409 node_not_reviewed`). El panel de B10 marca cada nodo como
   revisado al abrirlo y editarlo, y `PUT` **limpia `reviewed_at`** de todo nodo cuyo `title`,
   `summary`, `criticality` o `source_headings` haya cambiado.
3. **Un nodo con `attempts_count > 0` no se borra**: `422 node_has_progress`, o se archiva
   (`archived = true`). Borrarlo cascadearía a `learner_node_states` y `node_renders`, destruyendo
   maestría y rastro de auditoría de gente que ya trabajó, y cambiando además el conjunto de nodos
   `critical` que gobierna el cierre de matrícula.

Reglas de validación de `POST …/validate`, todas bloqueantes: DAG acíclico · al menos un nodo
`critical` · todo nodo con `summary` no vacío · todo nodo con `source_document_id` o
`seed_lesson_id` (regla heredada: sin fuente no hay curso) · sin prerrequisitos huérfanos ·
`position` contiguo desde 1 · todo nodo con `reviewed_at`. Al validar: `schema_status='validated'`,
`delivery_mode='dynamic'`, `schema_validated_by/at`, **pre-generación de los probes** de todos los
nodos (§7.1), recálculo del cierre de las matrículas activas (§7.5), y una fila en `audit_log` con
`action='course_schema_validated'` y el diff propuesto→validado en `detail`.

El `PUT` ejecuta `SET CONSTRAINTS uq_course_nodes_position DEFERRED` al inicio de su transacción
(§3.2), sin lo cual cualquier reordenación viola el `UNIQUE (course_id, position)` a mitad de
sentencia.

### 11.2 Onboarding y perfil (empleado)

| Método | Ruta | Request | Response |
|---|---|---|---|
| `GET` | `/onboarding` | — | `200 OnboardingRead` |
| `POST` | `/onboarding` | `OnboardingSubmit` | `200 LearnerProfileRead` |
| `POST` | `/onboarding/skip` | — | `200 LearnerProfileRead` |
| `GET` | `/users/me/learner-profile` | — | `200 LearnerProfileRead` · `404` si no existe |
| `PATCH` | `/users/me/learner-profile` | `{"preset"?, "role_title"?, "sector"?, "goal"?}` | `200 LearnerProfileRead` |
| `DELETE` | `/users/me/learner-profile` | — | `204` — borra las **siete** tablas personales del usuario en este orden: `node_render_views`, `node_feedback`, `node_attempts`, `node_probes`, `learner_node_states`, `learning_events`, `learner_profiles`; y pone `node_renders.generated_by = NULL`. `node_attempts` antes de `node_probes` porque `node_attempts.probe_id` es `ON DELETE SET NULL` (§3.3). Es la vía de supresión del art. 17 RGPD que §3.3 prometía y no tenía endpoint |

```jsonc
// OnboardingRead — el servidor manda las preguntas para que el copy viva en un sitio
{ "version": 1, "completed": false,
  "notice": "Tu puesto y tu sector se envían al proveedor de IA para adaptar los ejemplos. Puedes borrarlos cuando quieras desde Ajustes.",
  "questions": [
    {"id": "role_title", "kind": "text_suggest", "prompt": "¿Cuál es tu puesto?",
     "suggestions": ["Dependiente", "Cajero", "Encargado de turno", "…"]},
    {"id": "goal", "kind": "single_choice", "prompt": "¿Para qué quieres usar SkillNet ahora mismo?",
     "options": [{"value":"onboarding","label":"Acabo de entrar y quiero ponerme al día"},
                 {"value":"specific_gap","label":"Hay algo concreto que necesito dominar"},
                 {"value":"assigned","label":"Me han asignado formación"}], "allow_other": true},
    {"id": "experience_level", "kind": "single_choice",
     "prompt": "¿Cuánta experiencia tienes en tu puesto actual?",
     "options": [{"value":"none","label":"Ninguna"},{"value":"some","label":"Algo"},
                 {"value":"experienced","label":"Bastante"}]},
    {"id": "preset", "kind": "single_choice", "prompt": "¿Cómo prefieres estudiar?",
     "options": [{"value":"standard","label":"Estándar","hint":"Bloques de 10-15 min"},
                 {"value":"focus","label":"Concentración","hint":"Paso a paso, sin distracciones"},
                 {"value":"fast","label":"Ritmo rápido","hint":"Micro-bloques de 3-5 min"}]},
    {"id": "accessibility", "kind": "multi_choice", "optional": true,
     "prompt": "¿Quieres activar algún ajuste de lectura?",
     "options": [{"value":"short_blocks","label":"Bloques más cortos"},
                 {"value":"reduce_motion","label":"Menos animaciones"},
                 {"value":"high_contrast","label":"Más contraste"},
                 {"value":"extra_time","label":"Sin límite de tiempo"}]}
  ]}

// OnboardingSubmit
{ "role_title": "Dependiente", "sector": "retail", "goal": "onboarding",
  "experience_level": "some", "preset": "focus",
  "accessibility": {"short_blocks": true, "reduce_motion": false,
                    "high_contrast": false, "extra_time": false} }

// LearnerProfileRead — format_vector y tutor_notes NO se exponen al cliente
{ "role_title": "Dependiente", "sector": "retail", "goal": "onboarding",
  "experience_level": "some", "preset": "focus", "nodes_completed": 0,
  "onboarding_completed_at": "2026-07-25T09:12:00Z", "onboarding_skipped": false,
  "calibrating": true }
```

`POST /onboarding` escribe `learner_profiles` **y** `users.learning_profile` **y**
`users.accessibility` en una sola transacción.

### 11.3 Runtime (empleado)

| Método | Ruta | Request | Response |
|---|---|---|---|
| `GET` | `/courses/{course_id}/nodes` | — | `200 NodeListRead` |
| `POST` | `/nodes/{node_id}/probe` | — | `200 ProbeRead` |
| `POST` | `/nodes/{node_id}/probe/answer` | `{"probe_id", "item_id", "answer"}` | `200 ProbeAnswerResult` |
| `POST` | `/nodes/{node_id}/render` | `{"force": false, "preview": false}` | `202 {"request_id", "cached": bool}` · `409 node_not_reviewed` |
| `GET` | `/nodes/{node_id}/render` | — | `200 NodeRenderRead` (el render fijado, ver abajo) · `202 {"status":"generating","request_id"}` · `409 node_not_reviewed` |
| `GET` | `/nodes/{node_id}/renders` | — | `200 {"renders": [{render_id, created_at, ui_format}]}` — historial para "ver la versión anterior" (§5.5) |
| `POST` | `/nodes/{node_id}/waive` | `{"reason"?}` | `200 NodeStateRead` — sólo admin/responsable; §7.4 |
| `GET` | `/nodes/{node_id}/render/stream?request_id=…` | — | `200 text/event-stream` |
| `POST` | `/nodes/{node_id}/answer` | `{"render_id", "item_id", "answer", "hints_used", "latency_ms"}` | `200 NodeAttemptResult` — **`hints_used` del body es informativo y el servidor NO debe confiar en él** (B5): es el valor que decide si `NodeAttemptResult.correct_answer` se revela, y un campo que rellena el cliente no puede gobernar esa revelación (`hints_used: 3` sería una clave de respuestas gratis). El conteo válido se deriva en el servidor de `node_attempts.hints_used` para `(user_id, node_id, item_id)`, que sólo incrementa `POST /nodes/{id}/hint`. `QuizItemBlock` (B6) no concede pistas y siempre manda `0` |
| `POST` | `/nodes/{node_id}/hint` | `{"render_id", "item_id"}` | `200 {"hint", "hints_used"}` · `409` si no hay intento previo |
| `POST` | `/nodes/{node_id}/feedback` | `{"difficulty", "unclear"?}` | `204` |
| `POST` | `/nodes/{node_id}/events` | `{"events": [{"type","element","node_id"?,"ms"?}]}` | `204` |
| `POST` | `/explain` | `{"term", "context", "node_id"?, "language"?}` | `200 text/event-stream` |
| `GET` | `/render-kit` | — | `200 UIKitRead` |

```jsonc
// NodeListRead
{ "course_id": "…", "delivery_mode": "dynamic", "schema_version": 3,
  "nodes": [{ "id": "…", "title": "Plazo de devolución", "summary": "…",
              "criticality": "critical", "position": 1,
              "state": "not_started", "mastery": 0.0,
              "locked": false, "locked_by": [],
              "needs_practice": false,          // state == 'needs_review' (§7.4)
              "estimated_minutes": 6 }],
  "can_complete": false, "blocked_by": ["…"], "progress_percent": 0 }

// ProbeRead — sin respuestas correctas
{ "probe_id": "…", "node_id": "…",
  "items": [{ "item_id": "a", "item_type": "test", "bloom_level": "apply",
              "question": "…", "options": ["…","…","…","…"] },
            { "item_id": "b", "item_type": "true_false", "bloom_level": "understand",
              "question": "…" }] }

// ProbeAnswerResult
{ "item_id": "a", "score": 1.0, "passed": true,
  "verdict": null,                       // null hasta que se responden todos los ítems
  "estimate": 0.6, "next_item_id": "b",
  "render_hint": "prefetch" }            // "prefetch" | "skip" | null → el cliente
                                         // dispara POST /render en background

// NodeRenderRead — answer_key NUNCA aparece aquí
{ "render_id": "…", "node_id": "…", "ui_format": "explanation",
  "status": "ready", "backend": "openui", "cached": true,
  "spec": { "version": "skillnet-ui/1", "root": "b0", "format": "explanation",
            "components": [ /* … */ ] } }

// NodeAttemptResult
{ "score": 0.0, "passed": false, "feedback": "…",
  "correct_answer": null,                // sólo cuando hints_used >= 3 o passed
  "mastery": 0.34, "state": "learning",
  "consecutive_correct": 0, "consecutive_failed": 1,
  "next": "retry" }                      // "retry" | "next_item" | "next_node"
```

`GET /courses/{course_id}` **no cambia de forma**. Cuando el curso es dinámico añade
`"delivery_mode": "dynamic"` y devuelve `modules: []`; el frontend usa eso para decidir a qué
vista ir. Ningún campo existente cambia de tipo — el `CourseView` de v1 sigue compilando y
funcionando.

**`GET /nodes/{node_id}/render` no recalcula nada.** Devuelve el `ui_spec` de
`learner_node_states.active_render_id` mientras `render_pinned` sea `true` (§5.5), y escribe una fila
en `node_render_views` la primera vez que ese usuario ve ese render (§2.1). Sólo
`POST …/render {"force": true}` recalcula la `cache_key` y repinta. Sin esta separación, un simple
refetch cambiaba la pantalla a mitad de nodo.

`POST /nodes/{node_id}/render` con `"preview": true` sólo lo puede llamar un admin, genera con el
perfil del admin, no escribe `learner_node_states` y persiste con **`is_preview = true`**, lo que lo
excluye de la caché (§3.4). Sin ese flag, un preview generado **antes** de validar podía servirse
literalmente a un empleado del mismo bucket. Es lo que hace posible el modo `shadow` sin filtrar
contenido no aprobado.

---

## 12. Estrategia de test y fixtures

**Restricción central: no hay claves de API.** Todo debe ser verificable sin red. La solución no es
mockear en cada test, sino una implementación alternativa de `LLMService` seleccionada por
configuración.

### 12.1 `FixtureLLMService`

`src/llm/fixtures.py`

```python
FIXTURE_PREFIX = "fixture/"

class FixtureLLMService(LLMService):
    """Sirve respuestas grabadas. Se activa cuando el modelo resuelto empieza por
    'fixture/'. Ninguna llamada de red."""

    def _key(self, system_prompt: str, user_prompt: str) -> str:
        return sha256(f"{system_prompt}\x00{user_prompt}".encode()).hexdigest()[:16]


class FixtureEmbeddingService(EmbeddingService):
    """Vectores deterministas por hash del texto, dimensión = config.dimensions.
    Ninguna llamada de red. No son semánticos: sirven para que el pipeline
    corra y para asserts de forma, no para medir relevancia."""
```

**Se bifurca en TODOS los puntos de construcción, con un solo helper.** La versión anterior decía
"una sola bifurcación, en la fábrica" y parchaba dos sitios de cinco, con un nombre equivocado. Los
puntos reales son:

| Fichero | Línea | Qué construye |
|---|---|---|
| `src/deps/llm.py` | 29 | `get_llm_service` |
| `src/deps/llm.py` | 33 | `get_tutor_llm_service` |
| `src/deps/llm.py` | 37 | `get_embedding_service` |
| `src/deps/llm.py` | 43 | `get_optional_llm_service` (purpose `eval` — **el que usa `grade_open_answer`**) |
| `src/agents/content/nodes.py` | 82 | `_make_llm` (**no** `_build_llm`, como decía este documento) |
| `src/agents/content/nodes.py` | 88 | `_make_embedder` |
| `src/services/settings_service.py` | 72 | prueba de conexión de settings |
| `src/services/ingestion.py` | 53 | embedder de ingesta |

```python
# src/llm/fixtures.py
def maybe_fixture_llm(config) -> LLMService:
    return FixtureLLMService(config) if config.model.startswith(FIXTURE_PREFIX) else LLMService(config)

def maybe_fixture_embedder(config) -> EmbeddingService:
    return FixtureEmbeddingService(config) if config.model.startswith(FIXTURE_PREFIX) else EmbeddingService(config)
```

Los ocho sitios llaman a uno de los dos. Sin `get_optional_llm_service` parcheado, corregir un
`practical_case`/`dialogue` de un probe o de un desempate intentaría una llamada de red real (§3.4).
Sin `FixtureEmbeddingService`, `load_context` en su rama `chunked` no tiene embedding de query y
además no habría chunk alguno que buscar: `DocumentChunk.embedding` es `Vector(...)`
`nullable=False` (`src/models/document_chunk.py:35-37`), así que sin embedder no se crea ni una fila
(`src/services/ingestion.py:76-81` se traga el fallo y guarda sólo `full_text`).

**Alcance honesto del flujo sin claves:** con `FixtureEmbeddingService` los tests con fixtures cubren
**ambas** ramas de `load_context`. La rama `chunked` se ejercita con vectores deterministas, así que
prueba **el cableado** (que la query llega, que el filtro por headings se aplica, que el contexto se
recorta), **no la relevancia semántica**. La calidad del retrieval sólo se puede juzgar con
`@pytest.mark.integration` y claves reales, y así se etiqueta.

Layout de fixtures (**dentro del paquete**, ver §10.2 — si vivieran en `tests/` el perfil
`fixtures` de Docker no las encontraría):

```
src/llm/fixture_data/
├── index.json                       # {sha16: fichero, prompt_preview, use_case}
├── schema_design/returns_policy.json
├── decide_formato/{explanation,exercise,chart}.json
├── genera_ui/openui_explanation.txt        # dialecto crudo, tal como lo emitiría el modelo
├── genera_ui/openui_exercise.txt
├── genera_ui/openui_table_nested.txt       # Table.rows como string[][]  (regla 2 de §5.4)
├── genera_ui/malformed_unclosed_array.txt  # camino de reintento
├── genera_ui/malformed_unescaped_quote.txt # regla 1 de §5.4
├── genera_ui/malformed_literal_newline.txt # regla 3 de §5.4 — rompe parse_partial
├── genera_ui/invalid_unknown_component.txt # camino de fallback
├── genera_ui/repaired_after_retry.txt      # respuesta a UI_REPAIR_SYSTEM
├── probe_generate/plazo_devolucion.json
└── explain/{mercurio_quimica,mercurio_planeta}.json   # prueba el context_hash
```

Las tres fixtures `malformed_*` corresponden **una a una** a las tres reglas de la gramática congelada
de §5.4: son los fallos que un modelo de 8B comete el primer día, no malformaciones inventadas.

Modo grabación, para cuando alguien tenga una clave: `LLM_FIXTURE_MODE=record` hace que
`LLMService` real escriba cada par (prompt, respuesta) en `LLM_FIXTURE_DIR` y actualice
`index.json`. Así las fixtures son reales, no inventadas a mano. Si falta una fixture en modo
replay, el test falla con el sha y una vista previa del prompt, no con un `KeyError` opaco.

`docker-compose.yml` tiene un perfil `fixtures` con `LLM_MODEL=fixture/local` y
`EMBEDDING_MODEL=fixture/local`, para que el flujo completo se pueda demostrar en local sin
ninguna clave (el camino v2 se activa por curso, no por env var — ver §10). Funciona en el
compose de producción porque las fixtures viajan
dentro de `src/` (§10.2); `docker/compose/dev.yml`, que bind-montea `./apps/skillnet-api:/app`,
funciona igual.

### 12.2 Qué se testea y cómo

| Nivel | Fichero | Qué comprueba | Necesita |
|---|---|---|---|
| Unit | `tests/test_render_openui.py` | `parse()` de 8 dialectos válidos → golden JSON; 6 malformados → `RenderParseError`, incluidas las 3 reglas de la gramática (§5.4); `parse_partial` sobre truncados en **cada** posición mediante un `@pytest.mark.parametrize` sobre `range(len(raw))` — **no** con `hypothesis`, que sería una dependencia de desarrollo nueva y el límite de dependencias de `AGENTS.md` exige justificarla para nada que un bucle no dé | nada |
| Unit | `tests/test_render_roundtrip.py` | `parse(serialize(spec)) == spec` para el backend `openui` sobre 11 specs golden (los 10 de aquí más `inline_nested`, que fija los ids sintéticos del anidado en línea), **incluidos** specs con `QuizItem`, `Stack` anidado y `Table` con `rows` anidadas | nada |
| Unit | `tests/test_render_kit.py` | El catálogo congelado (10 nombres, orden posicional prop a prop, los 6 `item_type` del enum existente) y las 7 reglas: `UISpec` rechaza >12 componentes, ciclos, refs colgantes, `QuizItem` con `correct`, y `explanation`/`mixed` sin bloque `lead` inicial | nada |
| Unit | `tests/test_render_prompt_artifact.py` | **La alarma de deriva** entre `src/render/kit.py` y el artefacto que genera `library.prompt()`: digest normalizado del catálogo, `prompt_sha256`, que el prompt anuncie las 9 firmas y ninguna más, que **no** enseñe sintaxis reactiva, y que las versiones de `@openuidev` sean las auditadas | nada |
| Unit | `tests/test_render_gate.py` | 15 payloads reactivos (`Mutation` suelta, `Query` autodisparada, `refreshInterval`, `@OpenUrl` con `javascript:`, `@ToAssistant`, `$estado`, ternario, builtins…) rechazados, y 6 contenidos legítimos aceptados — incluida la prosa que menciona `Query()` y `$300`, que es el falso positivo medido de un grep de palabras clave; topes de tamaño; `canonicalize()` devuelve la re-serialización y no la entrada | nada |
| Unit | `tests/test_mastery.py` | Tabla de verdad de `probe_verdict` (25 casos), incluido "B perfecto y A a cero" → **no** maestría; que `critical` con 2/2 seleccionadas da `tiebreak`, no `mastered`; que `tiebreak_mastery` **alcanza cada uno de los 3 umbrales** (la tabla de §7.2 caso por caso); el techo de maestría (0.85 sostenido **sí** llega a `mastered` en un nodo `critical`); EWMA; las **8** transiciones de `node_state` de §7.3 | nada |
| Unit | `tests/test_probe_reuse.py` | El segundo `POST /probe` del mismo `(user, node, schema_version)` devuelve el veredicto almacenado y **no** genera ítems; re-probe rechazado si `state != 'needs_review'` o han pasado <7 días; probe diagnóstico (`scored=false`) no consume el intento | nada |
| Unit | `tests/test_node_grading.py` | `content_for()` para los 4 tipos deterministas: recombina `answer_key` + props y `grade()` puntúa igual que en v1 con la misma entrada | nada |
| Unit | `tests/test_schema_validation.py` | Detección de ciclos (auto-arista, 2-ciclo, 5-ciclo, DAG grande válido), huérfanos, `no_critical_node`, poda de ciclos en `persist_schema` | nada |
| Unit | `tests/test_runtime_router.py` | `select_tier` para los 5 formatos; `purpose_for`; precedencia de `resolve_llm_config` con `runtime_fast`/`runtime_heavy` y caída a `LLM_MODEL` | nada |
| Unit | `tests/test_profile_service.py` | Vector con decaimiento (fixture de eventos con `created_at` fijos), normalización L1, `vector_bucket`, calibración con `nodes_completed < 3`, poda de `tutor_notes` a 20 | nada |
| Unit | `tests/test_cache_key.py` | La clave cambia con `schema_version`, `preset`, `role_bucket`, `scaffold_band`, `effective_density`, `PROMPT_VERSION`; **no** cambia con `user_id` ni con `mastery` dentro de una misma `scaffold_band`; dos perfiles con `role_title` distinto **no** comparten clave | nada |
| Unit | `tests/test_schema_gate.py` | `PUT` sobre `validated` → `422 schema_locked`; `unvalidate` pone `proposed` + `static`; borrar un nodo con `attempts_count > 0` → `422`; editar `summary` limpia `reviewed_at`; nodo sin `reviewed_at` → `409` al pedir render | nada |
| Unit | `tests/test_delivery_resolution.py` | Los 12 casos de `resolve_delivery` | nada |
| Graph | `tests/test_runtime_graph.py` | `build_node_graph()` compila; recorrido completo con `FixtureLLMService` y repos falsos: camino feliz, `mastered`→skip, malformado→reintento, inválido→`fallback_seed` | fixtures |
| Graph | `tests/test_schema_graph.py` | Recorrido completo `propose` con fixtures → N nodos con criticidad y prereqs esperados | fixtures |
| Integración | `tests/integration/test_dynamic_flow.py` (`@pytest.mark.integration`) | e2e sobre Postgres real: propose → validate → onboarding → probe → render → answer → maestría → completado | docker db + fixtures |
| Integración | `tests/integration/test_v1_regression.py` (`@pytest.mark.integration`) | El flujo v1 completo sigue idéntico para un curso `static`, y un curso con columnas nuevas puestas a `dynamic` pero sin schema validado sigue sirviéndose por v1 (`resolve_delivery`) | docker db |
| Migración | `tests/integration/test_migration_0005.py` | `upgrade` desde `0004` y `downgrade` de vuelta, con datos v1 presentes. Asserts exactos: las 13 tablas y las 6 columnas de `courses` desaparecen; los 8 enums nuevos desaparecen; **`generation_step` conserva `schema_proposing` y `schema_proposed`** (huérfanos por diseño, §3); ninguna fila v1 alterada; reordenar posiciones 1↔2 en un `PUT` no viola el `UNIQUE` diferido | docker db |

**Sobre `aiosqlite`:** los tests de DB no pueden ir en SQLite (`jsonb`, `text[]`, enums nativos,
`pgvector`). Decisión: los tests de servicio usan repositorios falsos en memoria (protocolos, ya
que los servicios reciben repos por inyección) y todo lo que toque SQL real se marca
`@pytest.mark.integration` y corre contra el Postgres de `docker-compose`. `pytest -m "not
integration"` sigue siendo verde sin Docker y sin red — eso es lo que corre en CI por defecto.

### 12.3 Frontend

| Fichero | Qué |
|---|---|
| `src/lib/tokenize.test.ts` | Tokenización de español con acentos, apóstrofos, guiones, puntuación, emoji; stopwords ES y EN; re-render verbatim (`tokens.join('') === input`) |
| `src/components/courses/UiSpecRenderer.test.tsx` | Renderiza los 10 golden specs (compartidos con el backend vía `src/test/fixtures/ui-specs/*.json`); tipo desconocido → `null` sin crash; refs colgantes → no crash |
| `src/components/courses/ClickableSurface.test.tsx` | Clic en palabra → término correcto; selección parcial → palabra completa; `justDragged`; clic en `CodeBlock` → nada; **clic en el botón de una opción de `QuizItemBlock` → ninguna petición a `/explain`**; clic en el enunciado del quiz → nada |
| `src/api/nodes.test.ts` | Parseo del SSE con `fetch` stubeado (mismo patrón que `client.test.ts`), incluido `ui_block` incremental y `error` con `fallback` |
| Stories | `UiSpecRenderer`, cada bloque, `NodeSkeleton`, popover de explicación, wizard de onboarding — con `a11y` del addon en `error` (no `todo`) para lo nuevo |

Los golden specs son **el mismo fichero JSON** en backend y frontend (copiado por un script en
`pretest`, no duplicado a mano). Si el contrato se rompe, se rompen los dos lados a la vez.

---

## 13. Plan de trabajo por lotes

Regla: cada lote es un commit (o pocos), compila, pasa `pytest -m "not integration"` y `pnpm lint`,
y **deja el flag en `off`** hasta el lote B12. Ningún lote intermedio puede romper v1.

**Las seis únicas superficies v1 que se tocan, declaradas** (todo lo demás es fichero nuevo). Ninguna
cambia comportamiento con el flag apagado, y las seis van cubiertas por tests v1 existentes o nuevos:

| Fichero v1 | Lote | Cambio | Por qué es seguro |
|---|---|---|---|
| `src/agents/content/{nodes,helpers}.py` | B2 | Mover 3 funciones puras a `helpers.py` e importarlas | Sin cambio de comportamiento; `tests/test_generation_pipeline.py` ya lo cubre |
| `src/routes/generation_jobs.py` | B2 | `_TERMINAL_EVENTS` += `schema_ready` (1 línea) | Un tipo de evento que v1 nunca emite |
| `src/core/sse.py` | B5 | +`subscriber_count`, +`wait_for_subscriber` | Sólo añade; `publish`/`subscribe` intactos |
| `src/repositories/document_chunk_repo.py` | B1 | +`similarity_search_by_headings` | Método nuevo; el existente intacto |
| `apps/skillnet-web/src/pages/employee/CourseView.tsx` | B9 | `if (delivery_mode === 'dynamic')` | Con el flag apagado la API nunca devuelve `dynamic` |
| `apps/skillnet-web/src/pages/admin/CreateCourse.tsx` | B10 | Extraer `StepIndicator` + paso opcional | Refactor puro + rama tras el flag |

`src/components/ui/Skeleton.tsx` **ya no está en la lista**: B6 crea `ShimmerSkeleton.tsx` aparte
(§9.2).

```
B0 ──┬── B1 ──┬── B5 ──┬── B9 ── B12
     ├── B2 ──┴─ B10 ──┤
     ├── B3 ──── B8 ───┤
     ├── B4 ───────────┤
     ├── B6 ───────────┤
     └── B7 ───────────┘
```

### B0 — Base: migración, modelos, config *(bloqueante para todo)*

- `alembic/versions/0005_dynamic_courses.py` (nuevo, `down_revision="0004"`, `downgrade` con el
  alcance exacto de §3: sin `op.execute("COMMIT")`, dejando los 2 valores de enum huérfanos)
- `src/models/{course_node.py, course_node_prerequisite.py, learner_profile.py, learner_node_state.py, learning_event.py, node_render.py, node_render_view.py, node_probe.py, node_attempt.py, node_feedback.py, term_explanation.py, llm_usage_log.py, audit_log.py}` (nuevos — 13)
- `src/models/course.py` (+6 columnas, 2 enums), `src/models/generation_job.py` (+2 miembros), `src/models/__init__.py`
- `src/config.py` (`RENDER_BACKEND`, `LLM_RUNTIME_FAST_MODEL`, `LLM_RUNTIME_HEAVY_MODEL`, `LLM_FIXTURE_DIR`, `LLM_FIXTURE_MODE`)
- `src/llm/fixtures.py` (nuevo: `FixtureLLMService`, `FixtureEmbeddingService`, `maybe_fixture_llm`, `maybe_fixture_embedder`), `src/llm/fixture_data/` (directorio de fixtures, dentro del paquete)
- **Los 8 puntos de construcción de §12.1** pasan por los helpers: `src/deps/llm.py` (4), `src/agents/content/nodes.py` (2), `src/services/settings_service.py` (1), `src/services/ingestion.py` (1)
- `src/services/course_delivery.py` (nuevo, `resolve_delivery`)
- `src/deps/features.py` (nuevo, `require_dynamic_courses`)
- `src/routes/health.py` (+`features`), `src/scripts/purge_learning_data.py` (nuevo)
- `tests/test_delivery_resolution.py`, `tests/integration/test_migration_0005.py`
- `.env.example`, `docker-compose.yml` (perfil `fixtures` con `LLM_MODEL` y `EMBEDDING_MODEL` fixture)

### B1 — Adaptador de render y UI Kit (Python) *(paralelo con B2, B3, B4, B6, B7)*

- `src/render/{__init__.py, spec.py, kit.py, errors.py}` (nuevos)
- `src/render/backends/{__init__.py, base.py, openui.py}` (nuevos — **sin `a2tl.py`**, §1.3)
- `src/repositories/document_chunk_repo.py` (+`similarity_search_by_headings`, método nuevo; el existente no se toca)
- `tests/test_render_openui.py`, `test_render_roundtrip.py`, `test_render_kit.py`
- `tests/fixtures/dsl/*.openui`, `tests/fixtures/ui-specs/*.json`
- **NO** se toca el scoping por `org_id` de `src/deps/llm.py` ni de `settings_service.py`: sale a su
  propio `chore` PR con tests de ruta para chat y ejercicios (§4.3, §14.2 #11)

### B2 — Design-time: grafo de esquema + endpoints *(paralelo con B1, B3, B4, B6, B7)*

- `src/agents/schema/{__init__.py, state.py, nodes.py, graph.py, runner.py, errors.py}` (nuevos — nodos **nuevos**, no importados de v1, §4)
- `src/agents/content/helpers.py` (nuevo: `estimate_pages`, `assemble_chunk_text`, `themes_list` **movidas** desde `nodes.py`) + `src/agents/content/nodes.py` (importa desde ahí; sin cambio de comportamiento)
- `src/llm/prompts/schema.py` (nuevo: `SCHEMA_DESIGNER_SYSTEM`, `build_schema_prompt` con `available_headings` como lista cerrada)
- `src/repositories/course_node_repo.py` (nuevo)
- `src/services/course_schema_service.py` (nuevo: propose, update, validate, unvalidate, ciclos, versionado, gate `schema_locked`, `reviewed_at`, archivado, pre-generación de probes, recálculo de matrículas)
- `src/repositories/audit_log_repo.py` (nuevo)
- `src/schemas/course_schema.py` (nuevo)
- `src/routes/course_schema.py` (nuevo), `src/main.py` (registro), `src/routes/generation_jobs.py` (`_TERMINAL_EVENTS` += `schema_ready`, 1 línea — el canal sigue siendo `generation:{job_id}`)
- `tests/test_schema_validation.py`, `tests/test_schema_gate.py`, `tests/test_schema_graph.py`, `src/llm/fixture_data/schema_design/*.json`

### B3 — Perfil del aprendiz y onboarding (API) *(paralelo con B1, B2, B4, B6, B7)*

- `src/repositories/{learner_profile_repo.py, learning_event_repo.py}` (nuevos)
- `src/services/learner_profile_service.py` (nuevo: `EVENT_WEIGHTS` de 7 tipos, vector de 4 dimensiones con decaimiento, `vector_bucket`, calibración, `apply_signals()` con las **5 reglas de disparo** de §3.3)
- `src/schemas/{onboarding.py, learner_profile.py}` (nuevos; `OnboardingRead.notice` incluido)
- `src/routes/{onboarding.py, learner_profile.py}` (nuevos, incluido `DELETE /users/me/learner-profile`), `src/main.py`
- `tests/test_profile_service.py` (una prueba por regla de `tutor_notes`), `tests/test_cache_key.py`

### B4 — Pre-assessment y maestría *(paralelo con B1, B2, B3, B6, B7)*

- `src/services/mastery_service.py` (nuevo: `probe_verdict`, `tiebreak_mastery`/`tiebreak_verdict`, EWMA con techo, las 8 transiciones, `THRESHOLDS`, prior desde `user_skills`)
- `src/services/probe_service.py` (nuevo: lectura de `course_nodes.probe_items`, muestreo del seed, generación por LLM como último recurso, corrección, intento único por versión, probe diagnóstico)
- `src/services/node_grading.py` (nuevo: `content_for()` — adaptador `answer_key` + props → dict v1; **importa** `grade()` de `exercise_service`, no lo mueve)
- `src/repositories/{node_probe_repo.py, node_attempt_repo.py, learner_node_state_repo.py}` (nuevos)
- `src/llm/prompts/probe.py` (nuevo)
- `tests/test_mastery.py`, `tests/test_probe_reuse.py`, `tests/test_node_grading.py`, `src/llm/fixture_data/probe_generate/*.json`

### B5 — Runtime: grafo por nodo + endpoints *(depende de B1 y B4)*

- `src/agents/runtime/{__init__.py, state.py, nodes.py, graph.py, router.py, runner.py, errors.py}` (nuevos; `errors.py` contiene `runtime_node_error_wrapper`, independiente del de v1 — §4.2)
- `src/llm/prompts/runtime.py` (nuevo: `FORMAT_DECIDER_SYSTEM`, `UI_GENERATOR_SYSTEM`, `UI_REPAIR_SYSTEM`, `PROMPT_VERSION`, `build_*`)
- `src/services/node_render_service.py` (nuevo: `cache_key` con `role_bucket`/`scaffold_band`, hit/miss por `cache_key` **sin `user_id`**, fijado de `active_render_id`, escritura de `node_render_views`, cancelación, fallback)
- `src/repositories/{node_render_repo.py, node_render_view_repo.py, llm_usage_repo.py}` (nuevos)
- `src/core/sse.py` (+`subscriber_count`, +`wait_for_subscriber` — §9.2; sólo añade)
- `src/schemas/node.py` (nuevo), `src/routes/nodes.py` (nuevo, incluido `/waive` y `/renders`), `src/main.py`
- `src/services/exercise_service.py`: **no se toca.** `grade()` ya es una función pura de nivel de módulo (línea 73) y se importa tal cual; el adaptador vive en `node_grading.py` (B4)
- `tests/test_runtime_router.py`, `tests/test_runtime_graph.py`, `src/llm/fixture_data/{decide_formato,genera_ui}/*`

### B6 — Frontend: renderer de specs y bloques *(paralelo; sólo necesita el JSON de contrato de B1)*

- `src/types/ui-spec.ts` (nuevo), `src/types/index.ts` (`LearningNode`, `NodeRender`, `LearnerProfile`, `ProbeItem`, sin tocar los tipos v1)
- `src/components/courses/UiSpecRenderer.tsx` (nuevo)
- `src/components/courses/blocks/{StackBlock,TextContentBlock,CardBlock,CalloutBlock,StepSequenceBlock,TableBlock,CodeBlockBlock,ChartBlock,QuizItemBlock,MarkdownBlock}.tsx` (nuevos). `QuizItemBlock` es **autónomo** (§5.3): su propio estado y su propio envío a `POST /nodes/{id}/answer`, y **no** se toca `src/components/exercises/`
- `src/lib/motion.ts` (+preset `shimmer`), `src/components/ui/ShimmerSkeleton.tsx` (**nuevo**; `Skeleton.tsx` de v1 no se toca — §9.2)
- Stories + `UiSpecRenderer.test.tsx`, `src/test/fixtures/ui-specs/` (copia de B1)

### B7 — Curio: clic-para-explicar *(paralelo; necesita `term_explanations` de B0)*

- Backend: `src/llm/prompts/explain.py`, `src/services/explain_service.py`, `src/schemas/explain.py`, `src/routes/explain.py`, `src/repositories/term_explanation_repo.py` (nuevos) + `src/main.py`
- Frontend: `src/lib/tokenize.ts`, `src/components/courses/{ClickableText,ClickableSurface,ExplainPopover}.tsx`, `src/api/explain.ts` (nuevos). `ClickableSurface` implementa el hit-test de §8.5 (`closest(...)`) como primera línea del handler; `ExplainPopover` lleva la acción "No lo entiendo" → chat v1 sembrado
- `src/index.css` (`.entity`, `.entity-open`, `.phrase-rect`, `:focus-visible`, `prefers-reduced-motion`)
- `tests`: `tokenize.test.ts`, `ClickableSurface.test.tsx` (incluido el caso "clic en opción → sin explain"), `src/llm/fixture_data/explain/*.json`

### B8 — Frontend: wizard de onboarding *(depende de B3)*

- `src/components/ui/StepIndicator.tsx` (**extraído** de `CreateCourse.tsx`; `CreateCourse.tsx` pasa a importarlo — refactor sin cambio funcional)
- `src/pages/onboarding/Onboarding.tsx`, `src/components/onboarding/{RoleStep,GoalStep,ExperienceStep,PresetStep,AccessibilityStep}.tsx` (nuevos)
- `src/api/onboarding.ts` (nuevo), `src/api/users.ts` (`useUpdateProfile` acepta `accessibility`)
- `src/types/index.ts`: **arreglar** `learning_profile?: Record<string, unknown> | null` → `learning_profile?: 'standard' | 'focus' | 'fast'`. La columna del backend es el enum `learning_profile` (`src/models/user.py`), así que el wizard tiene que enviar un string plano y el tipo actual lo impide
- `src/App.tsx` (ruta `/onboarding`, fuera de `AppLayout`), `src/components/layout/ProtectedRoute.tsx` (gate con las 4 reglas de §6.1: flag desde `/health`, query condicionada a `role === 'employee'`, 404 ⇒ no redirigir, skeleton mientras carga)

### B9 — Frontend: vista de nodo *(depende de B5 y B6)*

- `src/pages/employee/NodeView.tsx`, `src/components/courses/{NodeList,NodeSkeleton,ProbeRunner,NodeFeedback,RenderControls}.tsx` (nuevos). `RenderControls` es el pie del nodo con "Actualizar esta lección" y "Ver la versión anterior" (§5.5) — no es opcional
- `src/api/nodes.ts` (nuevo: `useCourseNodes`, `useProbe`, `useSubmitProbeAnswer`, `useNodeRender`, `useNodeRenderStream`, `useSubmitNodeAnswer`, `useNodeEvents`, `useNodeRenderHistory`). `useNodeRender` va con `refetchOnWindowFocus: false` — es cinturón sobre tirantes, porque el backend ya sirve el render fijado
- `src/pages/employee/CourseView.tsx` (**única** modificación: si `delivery_mode === 'dynamic'` renderiza `NodeList`; si no, el árbol de v1 intacto)
- `src/App.tsx` (`/empleado/curso/:id/nodo/:nodeId`)

### B10 — Frontend admin: esquema *(depende de B2)*

- `src/pages/admin/CourseSchema.tsx`, `src/components/schema/{NodeEditor,PrerequisitePicker,CriticalityBadge,IntentDensitySlider,SchemaValidationPanel,ReviewChecklist}.tsx` (nuevos). `NodeEditor` expone `default_ui_format`; `ReviewChecklist` marca `reviewed_at` por nodo y bloquea el botón de validar hasta que todos están revisados
- `src/api/schema.ts` (nuevo, incluido `unvalidate` y el aviso de `schema_locked`), `src/pages/admin/CreateCourse.tsx` (paso 1 → "definir esquema" cuando el flag lo permite; el camino v1 sigue disponible), `src/App.tsx` (`/admin/curso/:id/esquema`)

### B11 — Integración y regresión *(depende de B5, B8, B9, B10)*

- `tests/integration/test_dynamic_flow.py`, `tests/integration/test_v1_regression.py`
- `src/services/enrollment_service.py` (cierre por nodos `critical` no archivados, **sólo** en la rama dinámica; recálculo al cambiar el esquema, §7.5)
- `src/services/skill_service.py` (traducción `mastery → skill_level`, **y lectura** de `user_skills` para el prior del probe, §7.1)

### B12 — Docs, flag y PR

- `docs/design/v2-dynamic-courses.md` (este fichero, actualizado con lo aprendido)
- `AGENTS.md` (§"Current phase" → v2 con el flag; **y arreglar la lista de paquetes**: menciona
  `packages/mcp-ui-renderer`, que no existe — `packages/` contiene `a2tl-video`, `a2tl-web`,
  `mcp-md-reader`), `CLAUDE.md` (comandos del perfil `fixtures`)
- **`chore` de docs obsoletos** (§14.2 #8), en este mismo lote: `screens.md` (rutas en español;
  §Employee Settings línea 213, quitar "TEA, TDAH, dislexia flags" y describir `users.accessibility`
  como ajustes neutros), `design-system.md` (§Skeleton: `animate-pulse` → `ShimmerSkeleton`)
- `docs/design/data-model.md` (apéndice v2 apuntando aquí; el cuerpo v1 no se reescribe)
- `README.md` (sección del flag), `.env.example` final
- Flag a `shadow` en el `docker-compose.yml` de desarrollo, `off` en el de producción
- PR a `main` con la tabla de verdad de `resolve_delivery` y la evidencia del test de regresión v1

**Ruta crítica:** B0 → B1 → B5 → B9 → B11 → B12. Todo lo demás cuelga en paralelo. Con dos personas,
la reparto: una hace B0/B1/B5 (adaptador + runtime), la otra B2/B3/B4 (esquema + perfil + maestría)
y luego B6-B10 se pueden solapar.

---

## 14. Riesgos y decisiones abiertas

### 14.1 Riesgos con mitigación decidida

| Riesgo | Probabilidad | Mitigación en este diseño |
|---|---|---|
| Un modelo pequeño (8B) genera dialecto malformado con frecuencia | Alta | Gramática EBNF congelada + 3 reglas de escape en el prompt (§5.4) · `parse_partial` tolerante · 1 reintento con `UI_REPAIR_SYSTEM` (el error exacto en el prompt) · `fallback_seed` a markdown v1. **El usuario nunca ve una pantalla roja** — y eso lo garantiza `fallback_seed`, no un segundo dialecto |
| El contenido generado es pedagógicamente peor que el estático y nadie lo revisa | Alta | Modo `shadow` (previews con `is_preview`, fuera de la caché) · **`reviewed_at` obligatorio por nodo**: un nodo que nadie ha abierto no se sirve · diff propuesto→validado en `audit_log`, para *medir* si los creadores editan · `node_feedback` con disparador: 3+ usuarios marcan `hard` en el mismo nodo → aviso al creador. **El creador decide, el sistema no reescribe solo** |
| Coste por LLM se dispara | Media | Caché compartida por bucket (no por usuario) · probes pre-generados por nodo, no por usuario · el pre-assessment evita generar lo ya sabido · `llm_usage_log` con `use_case`, **tabla creada en `0005`** (§3.5) · presupuestos de `max_tokens` explícitos |
| El hit rate de la caché inter-usuario es mucho peor que el medido | **Alta** | El régimen inter-usuario **no está medido** (§3.4) y `role_bucket` lo empeora a propósito. Es lo primero que se mide (§14.2 #3), y la palanca de retirada es una línea: quitar `role_bucket` o `vector_bucket` de la clave y subir `PROMPT_VERSION` |
| El SSE en memoria pierde eventos o rompe con >1 worker | Media | `202 {request_id}` + suscripción antes del trabajo + espera de 500 ms · fallback a polling de `GET /nodes/{id}/render` (patrón que el frontend ya usa para generación) · documentado: **un solo worker de uvicorn hasta migrar a LISTEN/NOTIFY** |
| Fuga de la respuesta correcta al cliente | Media | `answer_key` en columna separada que ningún schema Pydantic de respuesta incluye · `ProbeSession.probe` tipado como `ProbeRow` (protocolo **sin** `answer_key`) y proyectado por `ProbeSessionRead.from_session` (`extra="forbid"`, campos enumerados a mano) — el servicio ya no devuelve la fila ORM entera a su llamante · test que vuelca el modelo de respuesta y afirma que ni la clave ni sus valores aparecen (`tests/test_probe_answer_key_privacy.py`) · `NodeRenderRead` ya existe (`src/schemas/node.py:115`, llegó con B5) con `extra="forbid"` y la lista de campos enumerada a mano en `NodeRenderRead.of`, que es el contrato entero; **queda pendiente** el test equivalente que vuelque *ese* modelo y afirme la ausencia de la clave, como el de `ProbeSessionRead` · `hints_used` del cliente es informativo y no puede gobernar la revelación (§11.3) |
| Inyección de prompt desde el texto que manda el cliente | Media | `POST /explain` interpola dos valores del cliente (`term`, `context`, y el contexto no se contrasta con el texto real del nodo). **Ninguno va entre comillas**: se sanean (controles, `<`/`>`, rachas de comillas, tope de longitud 140/600) y se vallan en marcas `<<<nombre:token>>>` cuyo token ningún payload saneado puede contener — cerrar la valla exigiría los caracteres que ya se han quitado. El `system` declara que lo que va entre marcas es dato, nunca instrucción. Token derivado del contenido (no aleatorio) para que las fixtures sigan siendo reproducibles. Tests de secuestro en `tests/test_explain_service.py` |
| La regla de maestría deja pasar a quien no sabe | Media | Cláusula `score_a >= 0.5` · desempate con respuesta construida **obligatorio en todo nodo `critical`** · **un solo probe puntuado por versión de esquema** (índice único), que es lo que impide reentrar hasta acertar por azar · racha de 3 además del umbral |
| La regla de maestría deja fuera a quien sí sabe | Media | Techo de maestría: 3 aciertos consecutivos elevan `mastery` al umbral (§7.3), porque el EWMA converge a la media y dejaba el 0.85 sostenido a 0.05 del 0.90 para siempre · salida humana `POST /nodes/{id}/waive` con registro en `audit_log` · nodo en `needs_review` visible y reintentable, no desaparecido |
| El contenido cambia bajo los pies del usuario | Media | `active_render_id` fija el render mientras el nodo está abierto · `scaffold_band` (estable) sustituye a `mastery_band` (cambiaba con cada respuesta) en la clave · regeneración sólo por botón explícito, con "ver la versión anterior" |
| Regresión silenciosa en v1 | Media | `test_v1_regression.py` con el flag en `off` · `resolve_delivery` como único punto de decisión · default `off` |
| Deriva del contrato entre backend y frontend | Media | Golden specs compartidos, copiados por script en `pretest`. Rompen los dos lados a la vez |
| XSS vía contenido generado | Baja (por diseño) | Nunca HTML: IR tipada + render nativo. `SandboxHTML` fuera de scope. `props.text` es texto/markdown inline, renderizado por `react-markdown` sin `rehype-raw` |
| RGPD con datos sensibles | Media | Sin etiquetas de neurotipo · `learning_events` sin texto del usuario, purgado a 90 días por `src/scripts/purge_learning_data.py` (no hay tabla `background_jobs`, §1.3) · `term_explanations` sólo cachea ≤60 caracteres y purga a 180 días · `goal` ya no viaja al LLM · aviso en el punto de recogida (`OnboardingRead.notice`) · `DELETE /users/me/learner-profile` para el art. 17, que borra las **siete** tablas personales (incluidas `node_attempts` y `node_probes`, las que guardan lo que el empleado escribió) y lo demuestra tabla por tabla en `tests/test_gdpr_erasure.py` · `accessibility` nunca va al LLM · agregados de admin con k≥5 · `audit_log` (tabla creada en `0005`) en la validación del esquema |
| Se destruye evidencia de auditoría al dar de baja a un empleado | Media | `node_renders` sin `user_id` y `generated_by` con `ON DELETE SET NULL`; la traza de lectura vive en `node_render_views`, por usuario · un nodo con progreso se archiva, no se borra |

### 14.2 Decisiones abiertas (con fecha de decisión, no "TBD")

1. **Ratio real fast/heavy.** La estimación 90/10 es una hipótesis. Se decide con datos de
   `llm_usage_log` tras 2 semanas en modo `shadow`. Si el heavy supera el 25 %, hay que revisar el
   prompt de `decide_formato` — probablemente esté eligiendo `chart` cuando basta `explanation`.
2. **Latencia real de `genera_ui`. ~~Abierta~~ CERRADA (2026-07-27, medida).** Las fuentes internas
   daban cifras incompatibles (1-2 s vs 22.9 s vs 60-120 s), todas de generación de HTML completo y
   no de IR. Medido con `scripts/quality_bench.py` contra Groq real
   (`groq/llama-3.1-8b-instant` como nivel fast, `groq/openai/gpt-oss-120b` como heavy):
   **de menos de un segundo a ~3 s por render, a ~0.0008 USD por render**, con la contabilidad de
   tokens ya poblada. **El problema de "20-30 segundos" que asumía la investigación no existe en
   esta pila**: las cifras de 60-150 s eran de un modelo 7B en CPU local.

   Consecuencias, y son las que importan: la espera productiva basta de sobra, **no hace falta
   pre-generación**, y no se añade ninguna capa más de espera. El presupuesto de latencia deja de
   ser una restricción de diseño, así que los diales se gastan en *corrección*, no en velocidad
   (`docs/design/tuning.md`). La única restricción operativa real es que **el plan gratuito de Groq
   devuelve 429 con facilidad**: cualquier tanda de medición necesita retroceso exponencial, y el
   banco lo trae dentro y contabiliza la espera aparte para que un 429 no pueda puntuar como fallo
   de calidad.
3. **Tasa de aciertos **y de obsolescencia** de la caché inter-usuario.** Se miden **las dos**, porque
   el ~80 %/0 % citado se midió con una clave **por usuario** y esta clave es compartida: es un
   régimen sin datos (§3.4). Consulta: aciertos por `cache_key` sobre `node_renders` + `node_render_views`,
   y "obsoleta" = render servido cuyo `role_bucket`/`scaffold_band` ya no corresponde al perfil del
   lector. Si los aciertos caen por debajo del 50 %, se quita `vector_bucket`; si además hay
   obsolescencia perceptible, se quita `role_bucket` y se acepta contenido menos personalizado. Un
   cambio de una línea y una constante de `PROMPT_VERSION`.
4. **FSRS vs HLR.** Se mantiene HLR (ya está en el modelo de datos). La decisión de migrar a
   FSRS-6 se toma en el PR de repetición espaciada, no aquí, y requiere fijar antes: número de
   pesos (las fuentes dicen 17, 19 y 21), rango de `difficulty`, y la versión de `py-fsrs` con su
   API (`Scheduler.review_card` vs `FSRS.repeat`).
5. **Umbrales de alerta de retención.** Hay tres juegos incompatibles en la investigación
   (0.85/0.70/0.50 vs 0.50/0.70 vs 85/70/50 + crítico). Se define una tabla canónica única en el PR
   de repetición espaciada.
6. **Interleaving entre nodos.** Mezclar nodos de distintos cursos en una sesión mejora la
   transferencia, pero sobrecarga al novato. Se decide cuando existan datos de `mastery` reales:
   la regla candidata es habilitarlo sólo para nodos con `mastery >= 0.5` (fase `ha` o superior).
7. **¿`Simulation` con estado?** Requiere que la IR crezca con data-binding, que es un cambio
   estructural del contrato. Se decide sólo si el feedback de `node_feedback` muestra que
   `explanation` + `exercise` no basta para los nodos procedimentales.
8. **Rutas en español vs inglés.** El código usa español, los docs inglés. Se sigue el código y se
   corrige `screens.md` en un `chore` aparte. Si se decide lo contrario, es un renombrado
   mecánico de `App.tsx` y de los `Link`, sin efecto en la API.
9. **Umbral de personalización de pesos por empleado.** No aplica hasta que exista FSRS. Cuando
   aplique, elegir entre >50 y >200 revisiones (las fuentes dan ambos) y documentarlo.
10. **Multi-worker.** El diseño asume un worker de uvicorn por el SSE en memoria (coherente con
    `docker/api.Dockerfile`, que arranca con `--workers 1`). Si el despliegue necesita más, la decisión
    es `LISTEN/NOTIFY` de Postgres (sin Redis, coherente con "sin Redis, sin Celery"), y hay que tocar
    sólo `src/core/sse.py`.
11. **Scoping por `org_id` de los org settings.** `select(Organization).limit(1)` en
    `src/deps/llm.py:22-25` y `SettingsService._get_org`. Sale de este PR a un `chore` propio (§4.3)
    porque arreglarlo bien exige meter `CurrentUser` en cuatro dependencias que consumen rutas v1 sin
    tests. **Se decide antes de admitir la segunda organización en una instancia**; hoy la invariante
    de una sola org lo hace inocuo. El `chore` incluye tests de ruta para `chat.py` y `exercises.py`.
12. **Segundo dialecto de render.** Fuera de este PR (§1.3). Se decide **si** el reintento con
    `UI_REPAIR_SYSTEM` deja una tasa de fallo de parseo >5 % medida sobre `node_renders.status`. Si
    hace falta, será un dialecto propio de SkillNet capaz de expresar la `UISpec` completa, no
    `UIDL/1`.
13. **Navegación del curso: lista plana vs canvas con zoom semántico.** `NodeListRead` es una lista
    ordenada, que es una **rebaja deliberada** respecto a la exploración en canvas con raíl de estado
    persistente que recomienda la investigación de Keyhole. Motivo: el canvas es un proyecto de
    frontend propio y este PR ya tiene un renderer nuevo. Se reevalúa cuando existan cursos de >10
    nodos reales; queda anotado aquí en lugar de omitido.
14. **Promover la regla de redundancia (§5.2) de aviso a error.** Se decide con los avisos acumulados
    en `node_renders.error_message` tras 2 semanas en `shadow`: si aparece en <5 % de los renders, se
    promueve a error de validación; si aparece a menudo por tabla-resumen-tras-texto (redundancia
    buena), se retira la heurística.

### 14.3 Lo que encontró la primera ejecución real de las suites de integración (2026-07-27)

Las suites de `tests/integration/` se escribieron en B11 pero **no se habían llegado a ejecutar
nunca contra un PostgreSQL vivo**. La primera vez que corrieron, encontraron siete cosas. Se anotan
aquí porque cinco de ellas contradicen algo que este documento o el código afirmaban, y porque dos
son bugs de **v1** que llevaban ahí desde antes de v2.

**Migraciones (nada de esto era teórico: `alembic upgrade head` desde cero no había funcionado nunca).**

1. `0003` usaba `sa.Enum(..., create_type=False)`. `sa.Enum` **pierde ese flag** al adaptarse al
   dialecto de postgres, así que `CREATE TYPE skill_level` se emitía dos veces y la tirada moría.
   Corregido a `postgresql.ENUM`. Este era el motivo de fondo de que nadie hubiera podido levantar
   la base desde vacío.
2. `0005` y `src/models/learner_profile.py` construían un default JSONB con `sa.text()` que llevaba
   `:` sin escapar. SQLAlchemy los leía como parámetros de bind y el DDL salía como
   `{"texto"NULL,...}`. Corregido escapando `\:`.
3. `0005` usaba un valor nuevo de `generation_step` **en la misma transacción que lo añadía** (el
   índice parcial `uq_generation_jobs_schema_in_flight`) → `UnsafeNewEnumValueUsageError`. Los dos
   `ALTER TYPE … ADD VALUE` van ahora en `op.get_context().autocommit_block()`. La afirmación
   contraria del docstring de `0005` y de la nota de §3 **era falsa** y está corregida en los dos
   sitios.
4. Migración nueva **`0006`**: `user_skills.last_assessed_at` era `timestamp without time zone`
   mientras que sus dos escritores (`SkillService.record_mastery` y
   `EnrollmentService._grant_course_skills`) le pasan valores *aware*. asyncpg rechaza la mezcla, así
   que **subir** de nivel una skill que ya existía reventaba la petición. Sobrevivió hasta ahora
   porque sólo afecta a la rama UPDATE.

**Bugs de producto de v1, descubiertos por la regresión y no por v2.**

5. Cuatro sitios auto-completan una matrícula al llegar a progreso 1.0 y **ninguno concedía las
   skills del curso**. `POST /enrollments/{id}/complete` se encontraba la matrícula ya completada,
   tomaba su retorno temprano, y `user_skills` se quedaba vacía: un empleado terminaba un curso y no
   se le acreditaba nada. Corregido en `EnrollmentService.complete()`.
6. `PUT /lessons/{id}` era un **500 garantizado** (`MissingGreenlet`): leía `lesson.exercises` de un
   loader que nunca las cargaba de forma anticipada. Ninguna prueba cubría esa ruta.

**Entorno.**

7. `docker/compose/dev.yml` montaba el repo del host sobre `/app`, así que `uv run` dentro del
   contenedor veía un virtualenv con binarios ajenos, lo daba por roto y **borraba el `.venv` del
   host** para reconstruirlo. Resuelto con un volumen anónimo sobre `/app/.venv`.

La lección transversal, y es la que vale para el resto del proyecto: **una suite que no se ha
ejecutado no es cobertura**. Las dos rutas de v1 rotas (5 y 6) llevaban meses en el repo con tests
unitarios verdes alrededor.

---

## 15. Revisión: objeciones descartadas

Dos auditorías adversariales revisaron este documento. **Todos los bloqueantes de ambas se
verificaron contra el código y todos resultaron correctos**, y están corregidos arriba. Lo que sigue
son las **partes** de objeciones que no se han aplicado, con la evidencia de por qué.

### 15.1 "Forzar `fill_blank` en el ítem A para que `score_a` sea continuo"

**Descartado: el arreglo propuesto no funciona.** El diagnóstico sí era correcto (con dos ítems
binarios los tres umbrales se comportan igual, y el desempate topaba en 0.80 < 0.90), y está
corregido en §7.2. Pero la vía sugerida —hacer continuo `score_a` usando `fill_blank`— no existe:
`_grade_fill_blank` (`src/services/exercise_service.py:34-43`) devuelve **0.0 en cuanto falla un solo
hueco**, igual que `_grade_test`, `_grade_true_false` y `_grade_order_steps`. Los cuatro tipos
deterministas son todo-o-nada. Hacerlo continuo exigiría cambiar la corrección de v1, que se usa en
producción para `exercises` reales, y eso está fuera de alcance.

Lo aplicado en su lugar: renormalizar el desempate a `0.45a + 0.15b + 0.40c` (llega a 1.0, así que
todos los umbrales son alcanzables), obligar a que el ítem B sea `test` de 4 opciones (para que el
6.25 % citado sea cierto), y hacer el desempate construido **obligatorio** en todo nodo `critical`.
Los umbrales discriminan sin necesidad de crédito parcial (tabla de §7.2).

### 15.2 "Añadir un valor `schema_only` a `generation_output`"

**Descartado por coste/beneficio, no por incorrección.** La observación es válida:
`generation_jobs.output_type` es `NOT NULL` sobre un enum de dos valores y un job de esquema no es
ninguno. Pero añadir un tercer valor amplía el mismo problema que §3 documenta —un enum de Postgres no
puede perder valores, así que el `downgrade` dejaría **tres** huérfanos en lugar de dos— para un campo
que **ningún consumidor de esquema lee**: los clientes se guían por `status`, y
`generation_service` ya cae a `COURSE_AND_MANUAL` ante cualquier valor desconocido. Se documenta como
placeholder explícito en §3.1 en vez de crear deuda de migración.

### 15.3 "Generar el bloque de rol con una llamada `fast` por usuario (~40 tokens)"

**Descartado a favor de la otra opción del mismo revisor.** El problema —el rol no estaba en la
`cache_key` y la personalización por rol se perdía en cada acierto de caché— es real y está corregido.
De las dos vías propuestas se toma la primera (`role_bucket` dentro de la clave), no la del bloque
generado aparte, por dos razones concretas: una llamada LLM extra **por usuario y por nodo** es
precisamente el coste que la caché existe para evitar (y sería el 100 % de los usuarios, no el 20 % de
los fallos de caché); y un bloque generado fuera del `ui_spec` viviría fuera de `node_renders`, es
decir fuera de la auditoría y del `answer_key`-por-construcción. La línea "esto te sirve para X" sí se
implementa, pero **determinista y en el cliente** desde `goal` (§6.2 Q2), sin tokens.

### 15.4 "Añadir `org_id` a las diez tablas nuevas"

**Aplicado en parte, por diseño.** Llevan `org_id` las tablas **top-level**, que es lo que pide la
convención de `data-model.md`: `course_nodes`, `learner_profiles`, `node_renders`,
`term_explanations`, `llm_usage_log`, `audit_log`. **No** lo llevan las tablas hijas cuyo scoping se
deriva sin ambigüedad de su padre y que sólo se consultan por `user_id` o por `node_id`:
`course_node_prerequisites`, `learner_node_states`, `learning_events`, `node_probes`, `node_attempts`,
`node_feedback`, `node_render_views`. Añadir `org_id` ahí sería una columna denormalizada más que
mantener coherente en cada escritura sin ninguna consulta que la use. La incoherencia que señalaba la
objeción —presumir de multi-tenancy con una sola tabla org-scoped— queda resuelta con las seis de
arriba.

### 15.5 Verificaciones que confirmaron el documento (no requerían cambio)

> **DOS DE ESTAS VERIFICACIONES QUEDAN ANULADAS el 2026-07-26** (decisión de producto: adopción
> completa de OpenUI — `docs/design/openui-adoption.md`). Esta sección es la que se lee como *"esto ya
> está comprobado, no lo vuelvas a auditar"*, así que las dos frases caducadas están tachadas abajo en
> lugar de borradas, y lo que sigue siendo cierto queda separado de lo que ya no lo es.
>
> 1. **La promesa de "ninguna dependencia npm nueva" ya NO se sostiene.** Entran tres, con versión
>    exacta y sin `^`: `@openuidev/react-lang@0.2.9`, `@openuidev/lang-core@0.2.10` y `zod@4.4.3`
>    (`apps/skillnet-web/package.json`, resueltas en `pnpm-lock.yaml`). Las versiones están fijadas
>    porque ninguna de las propiedades de seguridad en las que se apoya la adopción es un contrato
>    público del paquete; `tests/test_render_prompt_artifact.py::test_the_pinned_openui_versions_are_the_audited_ones`
>    es la alarma que salta al subirlas.
> 2. **El parser del navegador ya NO es el de Python.** El de Python se conserva, pero como
>    **validador** en el servidor (`src/render/gate.py` + `src/render/spec.py`): valida antes de
>    persistir y re-serializa la `UISpec` al dialecto canónico. El pintado lo hace `<Renderer>` de
>    `@openuidev/react-lang` sobre los componentes que registramos (§5.1, §5.3, §5.4).
>
> **Lo que sí sigue siendo cierto de la frase original, y está comprobado:** la mitigación de XSS.
> `react-markdown` 10 sigue presente **sin** `rehype-raw`, no hay ningún `dangerouslySetInnerHTML` en
> `apps/skillnet-web/src/` y `framer-motion` sigue presente. Esa mitad no depende de la adopción: los
> paquetes de OpenUI no interpretan HTML, mapean el lenguaje a componentes React nuestros.

Se listan para que nadie las vuelva a auditar: la cadena de Alembic es lineal `0001→0004`, así que
`down_revision="0004"` es correcta y no hay heads en conflicto · ninguna ruta nueva de §11 colisiona
con las ~40 existentes · la precedencia de `resolve_llm_config` funciona exactamente como describe
§4.3 para `runtime_fast`/`runtime_heavy` (`src/llm/client.py:61-67`) · `GenerationJobRead.status` es
`str`, así que los dos miembros nuevos del enum no lo rompen · el marcador `integration` ya está en la
configuración de pytest · `react-markdown` 10 está presente **sin** `rehype-raw` y `framer-motion`
está presente, así que ~~la mitigación de XSS y la promesa de "ninguna dependencia npm nueva" se
sostienen~~ **la mitigación de XSS se sostiene** (la promesa de "ninguna dependencia npm nueva", no:
ver el aviso de arriba) · `docker/api.Dockerfile` arranca con `--workers 1`, coherente con el supuesto
del SSE.

Sobre el paquete npm `openui`: ~~es irrelevante que exista o no, porque §5.4 implementa el parser en
**Python** y no añade ninguna dependencia de frontend~~. **Corregido el 2026-07-26:** el paquete real
es `@openuidev/*`, existe, y **sí entra** como dependencia de frontend; el parser de Python se
conserva como validador de servidor, no como el parser del navegador. Lo que sí era un riesgo real
—presentar "OpenUI Lang" como dialecto externo con un ejemplo y ninguna gramática— está cerrado dos
veces: con la EBNF congelada y las tres reglas de escape de §5.4 (más una fixture malformada por
regla) y, desde la adopción, con la implementación de referencia del propio dialecto.
