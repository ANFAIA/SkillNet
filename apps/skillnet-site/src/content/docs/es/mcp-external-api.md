---
title: "Servidor MCP y API externa"
order: 45
section: "extensibility"
---

---
tipo: arquitectura
tags: [skillnet, api, mcp, webhooks, integraciones, ai-native]
---

## 8. MCP Server & External API

SkillNet es la capa de datos de skills del ecosistema. La app de formacion es la interfaz para recoger datos. Este documento define como esos datos salen hacia el mundo exterior: REST API para integraciones clasicas, MCP Server para agentes IA, webhooks para automatizaciones, y export para analisis offline.

Principio de diseno: **una misma capa de logica de negocio** alimenta la API interna (frontend), la API externa (terceros), y el MCP Server. No se duplica codigo. Los tres canales llaman a los mismos servicios Python.

```
                     ┌──────────────────────────────────────┐
                     │          Business Logic Layer        │
                     │  verify_skill() who_knows() get_gap()│
                     │  list_skills()  get_user_skills()    │
                     └───────┬──────────┬──────────┬────────┘
                             │          │          │
                    ┌────────┘    ┌─────┘    ┌─────┘
                    ▼            ▼          ▼
             ┌──────────┐ ┌──────────┐ ┌──────────┐
             │ Internal │ │ External │ │   MCP    │
             │ API      │ │ REST API │ │  Server  │
             │ (cookie) │ │ (apikey) │ │ (stdio/  │
             │ /api/v1/ │ │ /ext/v1/ │ │  SSE)    │
             └──────────┘ └──────────┘ └──────────┘
                  ↑            ↑            ↑
               React        HR tools     AI agents
               SPA          BI tools     Claude/GPT
```

---

### 8.1 REST API para consumidores externos

Separada de la API interna que usa el frontend. Distinto prefijo, distinta autenticacion, distinto rate limiting.

#### 8.1.1 Autenticacion: API Keys

Las API keys son para integraciones maquina-a-maquina. No hay sesiones, no hay cookies.

**Modelo de datos:**

```sql
CREATE TABLE api_keys (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id),
    created_by  uuid NOT NULL REFERENCES users(id),
    name        text NOT NULL,              -- "BambooHR sync", "Metabase read"
    key_hash    text NOT NULL,              -- bcrypt hash del key
    key_prefix  text NOT NULL,              -- "sn_example" (primeros 8 chars, para identificar)
    scopes      text[] NOT NULL DEFAULT '{}', -- ['skills:read', 'skills:write', 'users:read']
    last_used_at timestamptz,
    expires_at  timestamptz,                -- null = no expira
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);
```

**Formato del key:** `sn_{32_chars_random}` (ejemplo: `sn_example_00000000000000000000000000000000`). El prefijo `sn_` permite reconocer que es un key de SkillNet. El key completo se muestra al usuario UNA sola vez al crearlo. En la base de datos se guarda solo el hash.

**Envio en request:**

```http
GET /ext/v1/skills
Authorization: Bearer sn_example_00000000000000000000000000000000
```

**Scopes disponibles:**

| Scope | Permite |
|-------|---------|
| `skills:read` | Leer taxonomia, matrix, gaps, who_knows |
| `skills:write` | Verificar skills (verify_skill) |
| `users:read` | Leer perfiles de empleados y sus skills |
| `courses:read` | Leer catalogo de cursos y progreso |
| `export:read` | Descargar CSV/JSON completos |
| `webhooks:manage` | Registrar y gestionar webhooks |

**Gestion:** El admin crea y revoca API keys desde el panel de empresa (`/admin/settings/api-keys`). Puede asignar scopes individuales a cada key.

#### 8.1.2 Endpoints

Prefijo: `/ext/v1/`. Todos los endpoints estan scoped al `org_id` del API key automaticamente.

##### Taxonomia de skills

```
GET /ext/v1/skills
```

Lista todas las skills de la organizacion, agrupadas por categoria.

**Query params:**
- `category` (string, opcional) -- filtrar por nombre de categoria
- `search` (string, opcional) -- busqueda por nombre de skill (ILIKE)

**Response 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "name": "devoluciones",
      "description": "Proceso completo de gestion de devoluciones",
      "category": {
        "id": "uuid",
        "name": "Ventas"
      }
    }
  ],
  "meta": {
    "total": 23,
    "timestamp": "2026-07-14T10:30:00Z"
  }
}
```

##### Skill matrix completa

```
GET /ext/v1/skills/matrix
```

Matriz empleados x skills con niveles. La vista que un jefe ve de un vistazo en la app, aqui en formato datos.

**Query params:**
- `page` (int, default 1) -- pagina
- `per_page` (int, default 50, max 200) -- empleados por pagina
- `skill` (string, opcional) -- filtrar por nombre de skill
- `level` (enum: low/medium/high, opcional) -- filtrar por nivel minimo
- `user_id` (uuid, opcional) -- filtrar por empleado

**Response 200:**

```json
{
  "data": {
    "users": [
      {
        "id": "uuid",
        "full_name": "Juan Garcia",
        "skills": [
          {
            "skill_id": "uuid",
            "skill_name": "devoluciones",
            "level": "high",
            "source": "checkpoint",
            "last_assessed_at": "2026-07-10T14:00:00Z"
          },
          {
            "skill_id": "uuid",
            "skill_name": "html_css",
            "level": "medium",
            "source": "manual",
            "last_assessed_at": "2026-07-08T09:00:00Z"
          }
        ]
      }
    ]
  },
  "meta": {
    "page": 1,
    "per_page": 50,
    "total_users": 12,
    "total_pages": 1,
    "timestamp": "2026-07-14T10:30:00Z"
  }
}
```

##### Analisis de gaps

```
GET /ext/v1/skills/gaps
```

Detecta huecos: skills que la organizacion necesita pero donde hay pocos empleados con nivel suficiente.

**Query params:**
- `skill` (string, opcional) -- gap para una skill concreta
- `min_level` (enum: low/medium/high, default medium) -- nivel minimo considerado "cubierto"
- `threshold` (float 0-1, default 0.5) -- ratio por debajo del cual se considera gap (ej: si < 50% del equipo la tiene, es gap)

**Response 200:**

```json
{
  "data": [
    {
      "skill": {
        "id": "uuid",
        "name": "python",
        "category": "Tecnologia"
      },
      "total_users": 12,
      "users_at_level": 2,
      "coverage_ratio": 0.17,
      "gap_severity": "critical",
      "users_below": [
        {
          "id": "uuid",
          "full_name": "Laura Perez",
          "current_level": "low"
        }
      ]
    }
  ],
  "meta": {
    "min_level": "medium",
    "threshold": 0.5,
    "timestamp": "2026-07-14T10:30:00Z"
  }
}
```

`gap_severity`: `critical` (< 20% cobertura), `warning` (20-50%), `moderate` (50-70%).

##### Skills de un empleado

```
GET /ext/v1/users/{user_id}/skills
```

Perfil completo de skills de un empleado individual.

**Response 200:**

```json
{
  "data": {
    "user": {
      "id": "uuid",
      "full_name": "Juan Garcia",
      "role": "employee"
    },
    "skills": [
      {
        "skill_id": "uuid",
        "skill_name": "devoluciones",
        "category": "Ventas",
        "level": "high",
        "source": "checkpoint",
        "last_assessed_at": "2026-07-10T14:00:00Z"
      }
    ],
    "summary": {
      "total_skills": 5,
      "high": 2,
      "medium": 2,
      "low": 1
    }
  }
}
```

##### Verificar una skill

```
POST /ext/v1/skills/verify
```

Registra o actualiza el nivel de una skill para un usuario. Equivale a `verify_skill()`.

**Request body:**

```json
{
  "user_id": "uuid",
  "skill_id": "uuid",
  "level": "high",
  "source": "manual",
  "verified_by": "uuid"
}
```

`skill_id` puede sustituirse por `skill_name` (string) -- el sistema busca por nombre dentro de la org. Si no existe, devuelve 404.

**Response 201:**

```json
{
  "data": {
    "user_skill_id": "uuid",
    "user_id": "uuid",
    "skill_id": "uuid",
    "level": "high",
    "source": "manual",
    "previous_level": "medium",
    "last_assessed_at": "2026-07-14T10:30:00Z"
  }
}
```

Requiere scope `skills:write`.

##### Buscar quien sabe

```
GET /ext/v1/skills/who-knows
```

Encuentra empleados con una skill determinada, opcionalmente filtrado por nivel minimo.

**Query params:**
- `skill` (string, requerido) -- nombre de la skill
- `min_level` (enum: low/medium/high, default low) -- nivel minimo
- `limit` (int, default 10) -- maximo resultados

**Response 200:**

```json
{
  "data": [
    {
      "user_id": "uuid",
      "full_name": "Juan Garcia",
      "level": "high",
      "source": "checkpoint",
      "last_assessed_at": "2026-07-10T14:00:00Z"
    },
    {
      "user_id": "uuid",
      "full_name": "Ana Lopez",
      "level": "medium",
      "source": "manual",
      "last_assessed_at": "2026-07-08T09:00:00Z"
    }
  ],
  "meta": {
    "skill": "devoluciones",
    "min_level": "low",
    "total": 2
  }
}
```

##### Crear un curso completo en una llamada

```
POST /ext/v1/courses/full
```

**Implementado (2026-08).** Crea un curso dinamico de principio a fin en una sola peticion:
propone el esquema, genera los knowledge packs (con reintentos automaticos), revisa todos los nodos,
valida el curso y calienta los primeros renders. Opcionalmente matricula a un empleado y genera
artefactos (podcast, infografia). Sustituye el baile de siete llamadas que hacia el asistente de
creacion (`create -> propose -> poll job -> PUT schema -> poll packs -> review -> validate`).

La `org_id` y el admin creador salen del API key (columna `created_by`). Requiere scope
`courses:write`. Debajo reutiliza los mismos servicios que el panel de administracion; no reimplementa
nada de la generacion. La logica vive en `apps/skillnet-api/src/services/course_orchestration.py`
(`create_course_end_to_end`).

**Request body:**

```json
{
  "title": "Higiene y manipulacion de alimentos",
  "document_id": "uuid | null",
  "intent_density": 3,
  "enroll_user_id": "uuid | null",
  "generate_artifacts": ["podcast", "infographic"],
  "artifact_node_limit": 1
}
```

Solo `title` es obligatorio. `document_id` ancla el esquema en un documento ya procesado
(`status='ready'`); sin el, el curso se sintetiza desde el titulo. `intent_density` (1-5) regula la
profundidad.

**Response 201** (reporta exito parcial con honestidad — nunca se cuelga esperando):

```json
{
  "course_id": "uuid",
  "title": "Higiene y manipulacion de alimentos",
  "schema_status": "validated",
  "schema_version": 2,
  "node_count": 8,
  "packs_ready": 6,
  "packs_all_ready": false,
  "packs_summary": "6/8 nodes ready",
  "nodes": [
    {"node_id": "uuid", "title": "Importancia de la higiene", "status": "ready"},
    {"node_id": "uuid", "title": "Limpieza y desinfeccion", "status": "failed"}
  ],
  "reviewed": true,
  "validated": true,
  "enrolled_user_id": "uuid | null",
  "prewarm_spawned": true,
  "artifacts": [{"artifact_id": "uuid", "node_id": "uuid", "kind": "podcast", "status": "pending"}],
  "warnings": ["only 6/8 knowledge packs reached ready within the timeout"]
}
```

El estado por nodo de `packs` puede ser `ready`, `review_required`, `failed`, `pending`, `stale` o
`missing`. Como DeepSeek es inestable con JSON estricto, el runner reintenta de forma acotada
(`max_attempts=3`) y supersede versiones anteriores del esquema; si algun nodo no converge dentro del
tiempo limite, el curso sale igualmente validado (la validacion no depende de los packs) con un
`warning` y el conteo real. Los packs restantes siguen completandose en segundo plano.

##### Sugerencias de mentoria

```
GET /ext/v1/skills/mentorship
```

Devuelve pares mentor-aprendiz basados en datos reales de skills.

**Query params:**
- `skill` (string, opcional) -- filtrar por skill concreta
- `limit` (int, default 20) -- maximo pares

**Response 200:**

```json
{
  "data": [
    {
      "mentor": {
        "id": "uuid",
        "full_name": "Juan Garcia",
        "level": "high"
      },
      "mentee": {
        "id": "uuid",
        "full_name": "Laura Perez",
        "level": "low"
      },
      "skill": {
        "id": "uuid",
        "name": "devoluciones"
      }
    }
  ],
  "meta": {
    "total_pairs": 8
  }
}
```

Usa la misma query de matching documentada en `data-model.md` (mentor con level=high, mentee con level=low, misma org, distinto usuario).

#### 8.1.3 Rate limiting

Se aplica por API key, no por IP. Implementado con un middleware FastAPI que usa contadores en PostgreSQL (tabla `api_key_usage`) o Redis si esta disponible.

| Plan | Requests/minuto | Requests/dia |
|------|-----------------|--------------|
| Self-hosted (default) | 120 | Sin limite |
| SaaS Starter (futuro) | 60 | 10.000 |
| SaaS Growth (futuro) | 120 | 50.000 |

**Headers en cada response:**

```http
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 117
X-RateLimit-Reset: 1720954260
```

**Response 429 cuando se excede:**

```json
{
  "error": "rate_limit_exceeded",
  "message": "120 requests per minute exceeded. Retry after 23 seconds.",
  "retry_after": 23
}
```

Para self-hosted el limite es configurable via variable de entorno (`SKILLNET_API_RATE_LIMIT=120`). La PYME que no necesita limite puede ponerlo a 0 (sin limite).

#### 8.1.4 Paginacion

Todos los endpoints que devuelven listas usan paginacion offset-based.

**Params:** `page` (int, default 1) y `per_page` (int, default 50, max 200).

**Meta en response:**

```json
{
  "meta": {
    "page": 1,
    "per_page": 50,
    "total": 234,
    "total_pages": 5
  }
}
```

No se usa cursor-based porque el volumen de datos de una PYME (decenas de empleados, docenas de skills) no lo justifica. Si en el futuro se necesita para enterprise, se puede anadir sin romper el contrato existente.

#### 8.1.5 Versionado

Path-based: `/ext/v1/`. Si se necesita un breaking change, se crea `/ext/v2/` manteniendo v1 operativo durante 12 meses como minimo.

**Headers informativos:**

```http
X-SkillNet-API-Version: v1
X-SkillNet-Deprecation: 2028-01-01  # solo si v1 va a retirarse
```

**Regla:** un nuevo campo en el response NUNCA es breaking change (los clientes deben ignorar campos desconocidos). Un campo eliminado o un cambio de tipo SI es breaking y requiere nueva version.

#### 8.1.6 Formato de errores

Consistente en toda la API:

```json
{
  "error": "not_found",
  "message": "Skill 'blockchain' not found in this organization",
  "details": {
    "resource": "skill",
    "identifier": "blockchain"
  }
}
```

Codigos HTTP usados: 200, 201, 400 (bad request), 401 (no auth), 403 (scope insuficiente), 404 (not found), 422 (validation), 429 (rate limit), 500 (server error).

---

### 8.2 MCP Server

> **Nota (2026-08-04):** esta seccion se escribio antes de que existiera `/ext/v1` y antes de que
> MCP estandarizase las interfaces graficas. Dos decisiones de aqui han quedado desfasadas: el
> transporte **SSE** (deprecado en MCP a favor de Streamable HTTP) y el acceso **directo a
> PostgreSQL con asyncpg** (hoy duplicaria la logica que `/ext/v1` ya tiene). La revision esta en
> la seccion 8.8, que ademas cubre el caso de ofrecer SkillNet como conector a clientes IA de
> terceros. Leer 8.8 antes de implementar nada de 8.2.

#### 8.2.1 Que es

Un proceso separado que expone los datos de SkillNet como herramientas MCP (Model Context Protocol). Cualquier agente IA compatible con MCP (Claude Desktop, asistentes custom, agentes de Slack) puede conectarse y consultar datos de skills en tiempo real.

No es parte del servidor FastAPI. Es un proceso independiente que se conecta a la misma base de datos PostgreSQL.

```
┌──────────────────────────────────────────────────┐
│                  Docker Compose                   │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │  FastAPI     │  │  MCP Server  │  │PostgreSQL│ │
│  │  (port 8000) │  │  (port 3001) │  │(port 5432)│ │
│  │             │  │              │  │          │ │
│  │  API interna│  │  Python      │  │  Shared  │ │
│  │  API externa│  │  MCP SDK     │  │  Database │ │
│  │  SSE tutor  │  │  stdio/SSE   │  │          │ │
│  └──────┬──────┘  └──────┬───────┘  └────┬─────┘ │
│         │                │               │       │
│         └────────────────┴───────────────┘       │
│                    PostgreSQL connection          │
└──────────────────────────────────────────────────┘
```

#### 8.2.2 Tools expuestas

Cada tool MCP corresponde a una funcion de negocio. El agente IA lee la descripcion de la tool y decide cuando usarla.

##### `verify_skill`

Registra o actualiza el nivel de una skill para un usuario.

```python
@server.tool()
async def verify_skill(
    user: str,          # nombre o email del empleado
    skill: str,         # nombre de la skill
    level: str,         # "low", "medium", "high"
    verified_by: str = None  # nombre o email del verificador (opcional)
) -> dict:
    """
    Verify or set a skill level for an employee.
    
    Use this when someone confirms that an employee knows how to do something.
    Examples:
    - "Juan already knows returns. Maria taught him." -> verify_skill("Juan", "devoluciones", "high", "Maria")
    - "Set Laura's CSS level to medium" -> verify_skill("Laura", "css", "medium")
    
    Returns the updated skill record with the previous level.
    """
```

**Response:**

```json
{
  "user": "Juan Garcia",
  "skill": "devoluciones",
  "level": "high",
  "previous_level": "medium",
  "verified_by": "Maria Lopez",
  "timestamp": "2026-07-14T10:30:00Z"
}
```

##### `who_knows`

Encuentra personas con una skill determinada.

```python
@server.tool()
async def who_knows(
    skill: str,          # nombre de la skill
    min_level: str = "low"  # nivel minimo: "low", "medium", "high"
) -> dict:
    """
    Find employees who have a specific skill at or above a minimum level.
    
    Use this when someone asks "who can do X?" or "who knows X?"
    Examples:
    - "Who knows CSS?" -> who_knows("css")
    - "Who's an expert in returns?" -> who_knows("devoluciones", "high")
    
    Returns a list of matching employees with their levels and when they were last assessed.
    """
```

**Response:**

```json
{
  "skill": "devoluciones",
  "min_level": "low",
  "results": [
    {
      "name": "Juan Garcia",
      "level": "high",
      "source": "checkpoint",
      "last_assessed": "3 days ago"
    },
    {
      "name": "Ana Lopez",
      "level": "medium",
      "source": "manual",
      "last_assessed": "1 week ago"
    }
  ],
  "total": 2
}
```

##### `get_gap`

Analisis de gaps de skills para un equipo o skill especifica.

```python
@server.tool()
async def get_gap(
    skill: str = None,  # skill concreta (opcional)
    min_level: str = "medium"  # nivel minimo para considerar "cubierto"
) -> dict:
    """
    Analyze skills gaps in the organization.
    
    Use this when someone asks "what skills are we missing?" or "who needs training in X?"
    Examples:
    - "What are our biggest skill gaps?" -> get_gap()
    - "How many people need Python training?" -> get_gap("python")
    
    Returns gaps with severity (critical/warning/moderate) and affected employees.
    """
```

**Response (sin skill especifica):**

```json
{
  "gaps": [
    {
      "skill": "python",
      "category": "Tecnologia",
      "coverage": "2/12 employees (17%)",
      "severity": "critical",
      "employees_below": ["Laura Perez", "Carlos Ruiz", "...8 more"]
    },
    {
      "skill": "excel",
      "category": "Tecnologia",
      "coverage": "4/12 employees (33%)",
      "severity": "warning",
      "employees_below": ["Ana Lopez", "Pedro Gil", "...6 more"]
    }
  ],
  "summary": "2 critical gaps, 3 warnings out of 23 skills"
}
```

##### `list_skills`

Devuelve la taxonomia completa de skills.

```python
@server.tool()
async def list_skills() -> dict:
    """
    List all skills in the organization's taxonomy, grouped by category.
    
    Use this to understand what skills exist before querying specific ones.
    """
```

**Response:**

```json
{
  "categories": [
    {
      "name": "Ventas",
      "skills": ["devoluciones", "atencion_cliente", "cierre"]
    },
    {
      "name": "Tecnologia",
      "skills": ["html_css", "excel", "python"]
    }
  ],
  "total_skills": 23
}
```

##### `get_user_skills`

Perfil completo de skills de un empleado.

```python
@server.tool()
async def get_user_skills(
    user: str  # nombre o email del empleado
) -> dict:
    """
    Get the complete skill profile for an employee.
    
    Use this when someone asks "what does X know?" or "what's X's skill level?"
    Examples:
    - "What skills does Juan have?" -> get_user_skills("Juan")
    - "Show me Laura's profile" -> get_user_skills("Laura")
    
    Returns all skills with levels and a summary.
    """
```

**Response:**

```json
{
  "user": "Juan Garcia",
  "role": "employee",
  "skills": [
    {"skill": "devoluciones", "category": "Ventas", "level": "high", "last_assessed": "3 days ago"},
    {"skill": "html_css", "category": "Tecnologia", "level": "medium", "last_assessed": "1 week ago"}
  ],
  "summary": {"high": 2, "medium": 2, "low": 1, "total": 5}
}
```

##### `search_knowledge`

Busqueda semantica en los documentos de la empresa.

```python
@server.tool()
async def search_knowledge(
    query: str,      # pregunta o termino de busqueda
    limit: int = 5   # maximo resultados
) -> dict:
    """
    Search company documentation using semantic search.
    
    Use this when someone needs to find information in the company's uploaded documents.
    Examples:
    - "What's the return policy?" -> search_knowledge("return policy")
    - "How do we handle customer complaints?" -> search_knowledge("customer complaints process")
    
    Returns relevant passages from company documents with source references.
    """
```

**Implementacion:** Genera embedding del query con el mismo modelo que se uso para indexar (`multilingual-e5-small`), busca por distancia coseno en `document_chunks`, devuelve los chunks mas relevantes con referencia al documento fuente.

**Response:**

```json
{
  "query": "return policy",
  "results": [
    {
      "content": "The customer has 30 natural days to return any product with the original receipt...",
      "source": "Manual de Devoluciones",
      "page": 3,
      "section": "Plazos",
      "relevance": 0.92
    }
  ],
  "total": 3
}
```

#### 8.2.3 Resources MCP

Recursos estaticos que el agente IA puede leer para tener contexto.

##### Skills taxonomy

```python
@server.resource("skillnet://taxonomy")
async def taxonomy_resource() -> str:
    """
    The complete skills taxonomy for this organization.
    Categories and skills. Read this to understand what skills exist
    before using who_knows() or get_gap().
    """
```

Devuelve la taxonomia en formato legible para el agente. Se actualiza automaticamente cuando el admin anade o modifica skills.

##### Organization info

```python
@server.resource("skillnet://org")
async def org_resource() -> str:
    """
    Basic information about this organization: name, number of employees,
    number of skills tracked, number of courses available.
    Read this for context before answering questions about the company.
    """
```

#### 8.2.4 Implementacion tecnica

**SDK:** `mcp` (Python MCP SDK oficial de Anthropic). Version >= 1.0.

**Transporte:**

| Modo | Cuando usarlo |
|------|---------------|
| **stdio** | Conexion local. Claude Desktop se conecta al MCP server como proceso hijo. Para el admin que usa Claude en su maquina. |
| **SSE** | Conexion remota. El MCP server escucha en un puerto HTTP. Para agentes IA que se conectan desde fuera (Slack, n8n, agentes cloud). |

Para self-hosted, ambos modos estan disponibles. El Docker Compose levanta el MCP server con SSE por defecto en el puerto 3001.

**Estructura de archivos:**

```
services/
  mcp-server/
    __init__.py
    server.py          # Entry point, registra tools y resources
    tools/
      verify_skill.py
      who_knows.py
      get_gap.py
      list_skills.py
      get_user_skills.py
      search_knowledge.py
    resources/
      taxonomy.py
      org_info.py
    db.py              # Conexion a PostgreSQL (asyncpg)
    auth.py            # Validacion de MCP auth token
    config.py          # Variables de entorno
    Dockerfile
```

**Conexion a la base de datos:**

El MCP server se conecta a la misma instancia de PostgreSQL que FastAPI. Usa `asyncpg` directamente (no SQLAlchemy). Connection pool separado para no interferir con el pool de FastAPI.

```python
# db.py
import asyncpg

pool: asyncpg.Pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=2,
        max_size=5
    )

async def get_org_id() -> str:
    """Single-tenant: return the one org_id."""
    row = await pool.fetchrow("SELECT id FROM organizations LIMIT 1")
    return str(row["id"])
```

**Autenticacion MCP:**

Para el modo SSE (acceso remoto), el MCP server valida un token que es una API key de la tabla `api_keys`. El scope requerido es `mcp:connect`. En modo stdio (local), no se necesita autenticacion -- el proceso corre en la maquina del admin.

**Configuracion Docker Compose (fragmento):**

```yaml
services:
  mcp-server:
    build: ./services/mcp-server
    ports:
      - "3001:3001"
    environment:
      - DATABASE_URL=postgresql://skillnet:password@db:5432/skillnet
      - MCP_TRANSPORT=sse
      - MCP_PORT=3001
    depends_on:
      - db
```

**Configuracion Claude Desktop (stdio, local):**

```json
{
  "mcpServers": {
    "skillnet": {
      "command": "python",
      "args": ["-m", "services.mcp_server.server"],
      "env": {
        "DATABASE_URL": "postgresql://skillnet:password@localhost:5432/skillnet"
      }
    }
  }
}
```

---

### 8.3 Webhooks

Notificaciones push a URLs externas cuando ocurren eventos relevantes. Para automatizaciones con n8n, Zapier, Make, o sistemas custom.

#### 8.3.1 Eventos

| Evento | Cuando se dispara | Payload clave |
|--------|-------------------|---------------|
| `skill_level_changed` | Un empleado sube o baja de nivel en una skill | user, skill, old_level, new_level, source |
| `course_completed` | Un empleado termina todos los modulos de un curso | user, course, score, completed_at |
| `enrollment_created` | Un admin asigna un curso a un empleado | user, course, assigned_by, deadline |
| `gap_detected` | Un analisis detecta un gap critico (< 20% cobertura) | skill, coverage_ratio, affected_users_count |
| `certificate_expiring` | Un certificado expira en 30 dias o menos | user, certificate, expires_at, days_remaining |
| `feedback_submitted` | Un empleado envia feedback post-curso | user, course, responses |

#### 8.3.2 Registro de webhooks

**Modelo de datos:**

```sql
CREATE TABLE webhooks (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id),
    created_by  uuid NOT NULL REFERENCES users(id),
    url         text NOT NULL,              -- https://hooks.example.com/skillnet
    secret      text NOT NULL,              -- para firmar payloads (HMAC-SHA256)
    events      text[] NOT NULL,            -- ['skill_level_changed', 'course_completed']
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE webhook_deliveries (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id    uuid NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event         text NOT NULL,
    payload       jsonb NOT NULL,
    response_code int,
    response_body text,
    attempt       int NOT NULL DEFAULT 1,
    delivered_at  timestamptz,
    next_retry_at timestamptz,
    status        text NOT NULL DEFAULT 'pending',  -- pending, delivered, failed, exhausted
    created_at    timestamptz NOT NULL DEFAULT now()
);
```

**Registro via API:**

```
POST /ext/v1/webhooks
Authorization: Bearer sn_example_...
```

```json
{
  "url": "https://hooks.example.com/skillnet",
  "events": ["skill_level_changed", "course_completed"],
  "secret": "whsec_my_secret_string"
}
```

Requiere scope `webhooks:manage`.

**Gestion:** El admin tambien puede crear webhooks desde el panel de empresa (`/admin/settings/webhooks`). Puede ver el historial de entregas, reenviar entregas fallidas, y desactivar webhooks.

#### 8.3.3 Formato de payload

Todos los eventos siguen el mismo formato:

```json
{
  "id": "evt_uuid",
  "type": "skill_level_changed",
  "created_at": "2026-07-14T10:30:00Z",
  "org_id": "uuid",
  "data": {
    "user": {
      "id": "uuid",
      "full_name": "Juan Garcia",
      "email": "juan@empresa.com"
    },
    "skill": {
      "id": "uuid",
      "name": "devoluciones",
      "category": "Ventas"
    },
    "old_level": "medium",
    "new_level": "high",
    "source": "checkpoint",
    "triggered_by": "system"
  }
}
```

**Firma HMAC:**

Cada request incluye un header `X-SkillNet-Signature` con un HMAC-SHA256 del body usando el `secret` del webhook.

```http
POST https://hooks.example.com/skillnet
Content-Type: application/json
X-SkillNet-Signature: sha256=a1b2c3d4e5f6...
X-SkillNet-Event: skill_level_changed
X-SkillNet-Delivery: evt_uuid
```

El receptor verifica la firma para asegurar que el payload viene de SkillNet y no ha sido modificado.

#### 8.3.4 Reintentos con backoff exponencial

Si la entrega falla (timeout de 10 segundos, o response code >= 400):

| Intento | Espera | Tiempo acumulado |
|---------|--------|------------------|
| 1 | Inmediato | 0 |
| 2 | 1 minuto | 1 min |
| 3 | 5 minutos | 6 min |
| 4 | 30 minutos | 36 min |
| 5 | 2 horas | 2h 36min |
| 6 | 12 horas | 14h 36min |

Tras 6 intentos fallidos, el status cambia a `exhausted` y se marca como fallido. El admin puede reenviar manualmente desde el panel.

Si un webhook tiene mas de 10 entregas `exhausted` consecutivas, se desactiva automaticamente y se notifica al admin.

---

### 8.4 Data export

#### 8.4.1 CSV: skills matrix

```
GET /ext/v1/export/skills-matrix.csv
Authorization: Bearer sn_example_...
```

Descarga directa de la skill matrix en CSV. Formato:

```csv
employee_name,employee_email,skill_name,skill_category,level,source,last_assessed_at
Juan Garcia,juan@empresa.com,devoluciones,Ventas,high,checkpoint,2026-07-10T14:00:00Z
Juan Garcia,juan@empresa.com,html_css,Tecnologia,medium,manual,2026-07-08T09:00:00Z
Ana Lopez,ana@empresa.com,devoluciones,Ventas,medium,checkpoint,2026-07-09T11:00:00Z
```

Tambien disponible desde el panel de empresa como boton "Exportar CSV".

Requiere scope `export:read`.

#### 8.4.2 JSON: perfiles completos

```
GET /ext/v1/export/profiles.json
Authorization: Bearer sn_example_...
```

Descarga todos los perfiles de empleados con sus skills, cursos en progreso, y ejercicios completados.

```json
{
  "exported_at": "2026-07-14T10:30:00Z",
  "organization": "Mi Empresa",
  "employees": [
    {
      "id": "uuid",
      "full_name": "Juan Garcia",
      "email": "juan@empresa.com",
      "role": "employee",
      "hired_at": "2025-01-15",
      "skills": [
        {"name": "devoluciones", "level": "high", "source": "checkpoint"}
      ],
      "enrollments": [
        {
          "course": "HTML Basico",
          "status": "in_progress",
          "score": null,
          "deadline": "2026-08-01"
        }
      ]
    }
  ]
}
```

Requiere scope `export:read`.

#### 8.4.3 Informes programados

Implementacion futura (Fase 3). Concepto:

```
POST /ext/v1/export/schedules
```

```json
{
  "format": "csv",
  "type": "skills_matrix",
  "frequency": "weekly",
  "day": "monday",
  "delivery": {
    "method": "webhook",
    "url": "https://hooks.example.com/reports"
  }
}
```

O con entrega por email:

```json
{
  "delivery": {
    "method": "email",
    "to": ["rrhh@empresa.com"]
  }
}
```

El sistema genera el export segun la frecuencia configurada y lo entrega al destino. Util para la PYME que quiere un CSV en su email cada lunes sin tener que entrar a la plataforma.

---

### 8.5 Patrones de integracion

#### 8.5.1 Herramienta de HR (BambooHR, Factorial, Personio)

**Flujo de datos: bidireccional.**

```
BambooHR                          SkillNet
   │                                 │
   ├── Alta de empleado ──────────►  Crear usuario
   ├── Baja de empleado ──────────►  Desactivar usuario
   ├── Cambio de departamento ───►  Actualizar equipo
   │                                 │
   │  ◄─── skill_level_changed ─────┤  Webhook
   │  ◄─── course_completed ────────┤  Webhook
   │                                 │
   └── Consulta skills ──────────►  GET /ext/v1/users/{id}/skills
```

**Implementacion:**

1. **Fase MVP:** Import CSV manual. El admin exporta empleados de BambooHR como CSV y lo importa en SkillNet.
2. **Fase 2:** Webhook de BambooHR -> SkillNet. Cuando se da de alta/baja a un empleado en BambooHR, SkillNet recibe la notificacion y actualiza.
3. **Fase 3:** Bidireccional via API. BambooHR consulta skills de SkillNet y SkillNet lee datos de empleados de BambooHR.

**Ejemplo concreto con Factorial (popular en PYMEs espanolas):**

```python
# Factorial webhook → SkillNet
# Factorial notifica alta de empleado
POST /ext/v1/integrations/factorial/webhook
{
  "event": "employee_created",
  "data": {
    "first_name": "Laura",
    "last_name": "Perez",
    "email": "laura@empresa.com",
    "start_date": "2026-08-01"
  }
}
# SkillNet crea el usuario automaticamente
```

#### 8.5.2 Agente IA (Claude Desktop, ChatGPT, agente custom)

**Escenario 1: Claude Desktop con MCP (modo local)**

El admin de la empresa usa Claude Desktop como asistente. Conecta el MCP server de SkillNet como fuente de datos.

```
Admin abre Claude Desktop
  → Claude ve las tools de SkillNet (verify_skill, who_knows, etc.)

Admin: "Quien puede cubrir un turno en caja manana?"
Claude:
  1. Llama who_knows("caja", "medium")
  2. Recibe: Juan (high), Ana (medium), Carlos (medium)
  3. Llama get_user_skills("Juan") para ver disponibilidad
  4. Responde: "Juan es el mas cualificado en caja (nivel alto, 
     ultimo ejercicio hace 2 dias). Ana y Carlos tambien pueden 
     pero con nivel medio."

Admin: "Confirma que Laura ya sabe cerrar caja, se lo enseno Juan ayer"
Claude:
  1. Llama verify_skill("Laura", "cierre_caja", "medium", "Juan")
  2. SkillNet actualiza el registro
  3. Responde: "Registrado. Laura pasa de bajo a medio en cierre de caja, 
     verificado por Juan."
```

**Configuracion:** El admin instala SkillNet MCP en Claude Desktop anadiendo la configuracion JSON a `claude_desktop_config.json`. En modo local (stdio), apunta directamente al proceso. En modo remoto (SSE), apunta a la URL del MCP server con un token.

**Escenario 2: Agente custom en Slack**

Un bot de Slack conectado via SSE al MCP server de SkillNet. Los empleados preguntan en un canal y el bot responde.

```
#general
@skillbot quien sabe python?
  → Bot llama who_knows("python", "medium")
  → "Juan Garcia (alto), Ana Lopez (medio). Ultimo dato de Juan: hace 3 dias."

@skillbot que le falta al equipo de cocina?
  → Bot llama get_gap(skill=None) y filtra por equipo
  → "Gaps criticos: higiene (solo 1/5 cubierto), alergenos (2/5)."
```

**Escenario 3: ChatGPT con function calling**

ChatGPT no usa MCP nativamente, pero puede consumir la REST API externa mediante function calling o GPT Actions.

```python
# Definicion de funciones para ChatGPT
functions = [
    {
        "name": "who_knows",
        "description": "Find employees with a specific skill",
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {"type": "string"},
                "min_level": {"type": "string", "enum": ["low", "medium", "high"]}
            },
            "required": ["skill"]
        }
    }
]
# ChatGPT llama a GET /ext/v1/skills/who-knows?skill=X&min_level=Y
```

#### 8.5.3 Herramienta de BI (Metabase, Grafana)

**Patron: conexion directa a PostgreSQL (read-only) o via API.**

**Opcion A: Conexion directa (self-hosted)**

Metabase se conecta directamente a la base de datos PostgreSQL de SkillNet con un usuario read-only.

```sql
-- Crear usuario read-only para BI
CREATE USER metabase_reader WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE skillnet TO metabase_reader;
GRANT USAGE ON SCHEMA public TO metabase_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_reader;
```

Ventajas: sin limite de rate, queries SQL custom, joins complejos.
Desventajas: acoplamiento directo al schema (si las tablas cambian, los dashboards se rompen).

**Opcion B: Via API REST**

Metabase consulta la API de SkillNet en intervalos programados y materializa los datos en su propia base de datos.

```
GET /ext/v1/skills/matrix      → Tabla "Skills Matrix" en Metabase
GET /ext/v1/skills/gaps         → Tabla "Skills Gaps" en Metabase
GET /ext/v1/export/profiles.json → Tabla "Employee Profiles" en Metabase
```

**Dashboards pre-sugeridos:**

| Dashboard | Datos fuente | Preguntas que responde |
|-----------|-------------|------------------------|
| Cobertura de skills | skills/matrix | Que % del equipo domina cada skill? |
| Gaps por equipo | skills/gaps | Donde estamos mas debiles? |
| Progreso de formacion | enrollments + attempts | Quien avanza y quien esta atascado? |
| Tendencia temporal | user_skills historico | Estamos mejorando como equipo? |
| ROI de formacion | enrollments + user_skills | Cuantas skills nuevas por curso completado? |

**Grafana:** Mismo patron. Conexion directa a PostgreSQL via plugin PostgreSQL nativo. Util para alertas en tiempo real (ej: "notificar si coverage ratio de alguna skill cae por debajo de 30%").

---

### 8.6 Resumen de canales por caso de uso

| Quien | Que necesita | Canal |
|-------|-------------|-------|
| PYME sin IT | Ver quien sabe que | App web (skill matrix) + export CSV |
| PYME con Excel | Informe mensual de skills | Export CSV programado o manual |
| Jefe con Claude Desktop | Preguntar en natural sobre su equipo | MCP Server (stdio, local) |
| Bot de Slack/Teams | Consultas de skills desde chat | MCP Server (SSE, remoto) o API REST |
| n8n / Zapier | Automatizar: curso completado -> notificar | Webhooks |
| BambooHR / Factorial | Sincronizar empleados | API REST + webhooks |
| Metabase / Grafana | Dashboards de skills | Conexion directa a PostgreSQL o API REST |
| Agente IA custom | Consultar skills programaticamente | MCP Server o API REST |
| Data analyst | Analisis offline | Export JSON/CSV |

---

### 8.7 Roadmap de implementacion

| Fase | Que se construye | Cuando |
|------|-----------------|--------|
| **MVP** | Logica de negocio (verify_skill, who_knows, get_gap) como servicios internos de Python. Export CSV desde el panel de empresa. Sin API externa aun. | Fase 1 (actual) |
| **Fase 2** | API externa REST (`/ext/v1/`) con API keys. MCP server basico (3 tools: who_knows, get_gap, list_skills). Webhooks para skill_level_changed y course_completed. | Post-beca |
| **Fase 3** | MCP server completo (6 tools + resources). Todos los webhooks. Export JSON. Integraciones BambooHR/Factorial. Informes programados. | Escala |

Cada fase se construye sobre la anterior. La logica de negocio escrita en Fase 1 se reutiliza en las APIs y el MCP de Fases 2 y 3. No se reescribe nada.

---

### 8.8 SkillNet como conector para clientes IA (exploracion, no comprometido)

**Estado: posibilidad futura.** Nada de esta seccion esta planificado ni tiene fecha. Se documenta
para que la decision este tomada por escrito el dia que se retome, y para corregir lo que la
seccion 8.2 daba por bueno.

La seccion 8.2 asume que el usuario del MCP es *el admin de la propia instancia*, conectando su
Claude Desktop a su SkillNet por stdio. Esta seccion cubre lo contrario: **exponer SkillNet hacia
fuera** para que cualquier usuario de Claude (u otro host MCP) conecte su instancia como conector
remoto y consulte sus datos de skills desde la conversacion.

Es la aplicacion literal del primer parrafo de este documento — "SkillNet es la capa de datos de
skills del ecosistema" — a un canal de distribucion que en 2026 ya existe.

#### 8.8.1 Las cuatro capas y cual falta

| Capa | Que es | Estado |
|------|--------|--------|
| 1. Logica de negocio scoped por organizacion | `SkillService`, alcanzado por `org_id` en cada llamada | **hecha** |
| 2. Transporte remoto + autenticacion de usuario final | Streamable HTTP + OAuth 2.1 | **no existe** |
| 3. Tools MCP | envoltura fina sobre `/ext/v1` | parcial (la API esta, la envoltura no) |
| 4. MCP App: interfaz grafica dentro del chat | recursos `ui://` | no existe |

El grueso del trabajo es la capa 2. Las capas 3 y 4 son pequenas encima de ella.

Lo que ya no hay que resolver: **el aislamiento por organizacion**. Todos los endpoints de
`/ext/v1` reciben el `org_id` de la credencial y lo propagan al servicio
(`src/routes/ext/skills.py`). Un conector multi-inquilino se apoya en eso tal cual; el token de
OAuth pasa a ser el portador del `org_id` en lugar de la API key, y por debajo no cambia nada.

#### 8.8.2 Endurecimiento previo de `/ext/v1`

Antes de que la API externa la consuma alguien que no seamos nosotros, `_get_api_key()` en
`src/routes/ext/auth.py` tiene que hacer cumplir dos cosas que el modelo de datos ya contempla
pero la dependencia todavia no comprueba:

- **`scopes`**: la tabla `api_keys` los almacena y la seccion 8.1.1 los especifica, pero ninguna
  ruta los exige hoy. `POST /skills/verify` debe requerir `skills:write`; las lecturas,
  `skills:read`.
- **`expires_at`**: solo se comprueba `is_active`.

Es la primera tarea de cualquier trabajo en esta direccion, y es independiente del resto.

#### 8.8.3 Correcciones a la seccion 8.2

**Transporte: Streamable HTTP, no SSE.** El transporte SSE quedo deprecado en MCP. Para acceso
remoto se usa Streamable HTTP; stdio sigue siendo valido para el caso local de 8.2.

**El servidor MCP es un cliente de `/ext/v1`, no de PostgreSQL.** La seccion 8.2.4 propone
`asyncpg` contra la misma base de datos. Se escribio cuando la API externa no existia. Hoy eso
duplicaria el alcance por organizacion, la validacion de niveles y el tratamiento de errores en un
segundo camino a los datos, contra el principio declarado al inicio de este documento. El servidor
habla HTTP con `/ext/v1` y no necesita credenciales de base de datos.

**Ubicacion: `packages/skillnet-mcp/`, TypeScript.** Coherente con `packages/mcp-md-reader` y
`packages/a2tl-video`, y es donde estan los SDK de MCP Apps.

#### 8.8.4 Reparto de tools: lectura para el modelo, escritura para la interfaz

MCP Apps (SEP-1865) anade `_meta.ui.visibility`, que acepta `["model"]`, `["app"]` o ambos. Una
tool marcada `["app"]` **no aparece en la lista de herramientas del modelo**: solo la puede invocar
la interfaz de la propia app, desde la misma conexion.

| Tool | `visibility` | Anotacion | Interfaz |
|------|-------------|-----------|----------|
| `who_knows` | `model` | `readOnlyHint` | si |
| `get_gap` | `model` | `readOnlyHint` | si |
| `get_user_skills` | `model` | `readOnlyHint` | si |
| `list_skills` | `model` | `readOnlyHint` | no, basta texto |
| `verify_skill` | **`app`** | `destructiveHint` | la dispara un boton |

Que la unica escritura sea `app`-only es la decision de diseno de esta seccion. Un modelo que puede
subir el nivel de una skill de un empleado por su cuenta es un fallo inaceptable en un producto de
datos de personal. Con `visibility: ["app"]` no es una instruccion del prompt que se pueda ignorar:
la herramienta no existe para el modelo. Sigue habiendo un humano pulsando un boton.

#### 8.8.5 Que aporta la interfaz grafica

Una MCP App es un HTML autocontenido que el servidor publica como recurso `ui://`, con
`mimeType` `text/html;profile=mcp-app`, enlazado a una tool por `_meta.ui.resourceUri`. El host lo
renderiza en un iframe aislado dentro de la conversacion.

Convierte el escenario ya descrito en 8.5.2 — "quien puede cubrir un turno en caja manana?" — de un
parrafo de prosa en la matriz de skills real, con niveles, fecha de ultima evaluacion y un boton de
verificar que llama a `verify_skill` sin pasar por el modelo.

Dos detalles del estandar que importan al diseno:

- **`structuredContent` frente a `content`**: `content` lo ven el modelo y la app;
  `structuredContent` va solo a la app, tipado. La matriz completa viaja en `structuredContent` y en
  `content` va un resumen de dos lineas. El modelo no consume la tabla entera en tokens.
- **CSP `default-src 'none'` por defecto**: el iframe no puede hacer una sola peticion de red si no
  se declara en `_meta.ui.csp.connectDomains`. Se evita: la interfaz obtiene datos llamando a tools,
  no a la API por su cuenta. Ademas no expone credenciales al navegador.

Hay variables CSS estandarizadas (`--color-background-primary`, `--font-sans`, ...) que el host
inyecta; usandolas, la interfaz respeta el tema claro/oscuro del cliente sin trabajo extra.

Sobre reutilizar componentes de `skillnet-web`: `components/courses/kit/` arrastra
`NodeRenderContext` y OpenUI Lang, que no encajan en un bundle autocontenido. Las primeras vistas se
escriben ligeras y aparte; si el canal demuestra valor, se extraen los componentes de presentacion
puros a un paquete compartido.

#### 8.8.6 Autenticacion: el bloque grande

Los clientes MCP no permiten que el usuario pegue un `client_id` y un `client_secret`. Exigen
**OAuth 2.1 con Dynamic Client Registration** (o Client ID Metadata Documents): el cliente se
registra en caliente. SkillNet tendria que publicar:

- `/.well-known/oauth-protected-resource` (RFC 9728)
- `/.well-known/oauth-authorization-server`
- `/register` — DCR, `application/json` (RFC 7591)
- `/authorize` — validando redirect URI, scope y PKCE
- `/token` — `application/x-www-form-urlencoded`, codigo de un solo uso, verificacion PKCE

Mas la exigencia de OAuth 2.1 de rotar o vincular al emisor los refresh tokens de clientes
publicos.

Hoy SkillNet tiene sesion por cookie para la SPA y API keys para maquinas. Falta el caso
intermedio: *esta persona concreta, de esta organizacion, autoriza a un cliente externo a leer sus
datos de skills*. Es trabajo real y es el motivo por el que esta seccion no es una tarea pequena.

#### 8.8.7 Autohospedado y directorios de conectores

SkillNet es autohospedado: una instancia por empresa, cada una con su URL. Eso encaja mal con el
modelo de "un conector del directorio apunta a un dominio unico", pero los directorios contemplan
conectores de **conexion propia**, donde es el usuario quien aporta su URL y sus credenciales al
conectar. Ese es el encaje correcto.

Y hay un escalon anterior que no depende de nadie: en los clientes que soportan conectores remotos
personalizados, cualquier usuario puede anadir uno pegando una URL, sin revision ni aprobacion. Los
primeros clientes no necesitan que SkillNet este listado en ningun sitio. El directorio es
distribucion, no requisito tecnico.

Si algun dia se solicita el listado, los requisitos que mas rechazos causan son: cada tool con
`title` y su anotacion `readOnlyHint` / `destructiveHint`, HTTPS, OAuth, documentacion publica con
ejemplos de uso, y una **politica de privacidad publica y completa** — cuya ausencia es rechazo
directo. Para un producto que trata datos de empleados, esa politica hace falta igualmente antes
que ningun directorio.

#### 8.8.8 Orden si se retoma

1. Hacer cumplir `scopes` y `expires_at` en `/ext/v1` (8.8.2). Independiente y barato.
2. Servidor MCP remoto sobre Streamable HTTP, autenticado con API key, envolviendo `/ext/v1`.
   Sirve ya para una instancia propia o un cliente piloto, y valida si las tools son buenas.
3. OAuth 2.1 con DCR (8.8.6). El bloque caro. A partir de aqui conecta cualquiera.
4. MCP App: interfaz para `who_knows` y `get_gap`.
5. Listado en directorio, si tiene sentido comercial para entonces.

El paso 2 es barato y responde a la pregunta que importa — si el producto se siente util dentro de
un asistente. No conviene pagar el paso 3 sin haber pasado por el 2.

---

### 8.9 Servicio A2A implementado (`apps/skillnet-a2a`)

**Estado: implementado y en el compose.** Es la materializacion del paso 2 del roadmap de 8.8.8:
un servidor remoto que envuelve `/ext/v1` y expone las capacidades de SkillNet a agentes externos.
No habla con PostgreSQL: es un cliente HTTP de `/ext/v1` (principio de 8.8.3). Vive en su propio
proceso/contenedor (`docker/a2a.Dockerfile`, perfil de compose), publicado solo en `127.0.0.1`.

#### 8.9.1 Protocolo y autenticacion

Habla **A2A JSON-RPC 2.0 sobre HTTP** (no MCP todavia; misma familia de "tools para agentes"):

- `GET /.well-known/agent.json` — el AgentCard: nombre, version, `skills[]` y esquema de auth.
- `POST /` — metodos `message/send` y `tasks/get`.

Dos credenciales, en dos saltos:

1. El agente externo se autentica ante el A2A con un **bearer `A2A_AUTH_KEY`** (obligatorio: el
   servidor se niega a arrancar sin el, ver `require_auth_key` en `src/main.py`).
2. El A2A llama a `/ext/v1` con su propia **API key interna** (`A2A_INTERNAL_API_KEY`), creada en el
   bootstrap con scopes `skills:read`, `skills:write`, `users:read`, `courses:write`.

Entre medias hay un orquestador LLM (`src/orchestrator.py`) que interpreta el lenguaje natural del
mensaje y decide que tool llamar, en un bucle de tool-calling acotado.

#### 8.9.2 Tools expuestas

Cada tool es una envoltura fina sobre un endpoint `/ext/v1` (`src/tools.py` + `src/skillnet_client.py`):

| Tool | Endpoint `/ext/v1` | Que hace |
|------|--------------------|----------|
| `who_knows` | `GET /skills/who-knows` | Encuentra empleados con una skill (filtro por nivel minimo) |
| `get_gap` | `GET /skills/gaps` | Analiza gaps de skills en la organizacion |
| `verify_skill` | `POST /skills/verify` | Registra/actualiza el nivel de una skill de un empleado |
| `list_skills` | `GET /skills` | Lista la taxonomia de skills por categoria |
| `get_user_skills` | `GET /users/{id}/skills` | Perfil completo de skills de un empleado |
| **`create_course`** | `POST /courses/full` | **Crea un curso completo de principio a fin en una llamada** |

#### 8.9.3 `create_course` (nuevo, 2026-08)

La tool que pedia el owner: un agente crea un curso "como el resto de tools que tiene". Envuelve
`POST /ext/v1/courses/full` (8.1.2). El cliente usa un timeout largo (600 s) porque el flujo completo
—proponer esquema, generar packs con reintentos, revisar, validar, calentar— corre en el servidor y
puede tardar minutos con un proveedor real.

**Parametros:** `title` (obligatorio), `document_id`, `intent_density` (1-5), `enroll_user_id`,
`generate_artifacts` (p.ej. `["podcast", "infographic"]`).

**Ejemplos en lenguaje natural** que el orquestador mapea a la tool:

- "Crea un curso sobre seguridad alimentaria" -> `create_course(title="Seguridad alimentaria")`
- "Monta un curso de onboarding de 5 nodos desde el documento X y matricula a Maria" ->
  `create_course(title="Onboarding", document_id="X", enroll_user_id="<Maria>")`

**Devuelve** el `course_id`, el estado por nodo de los packs, `validated`, `enrolled_user_id` y
`artifacts` (ver el cuerpo de respuesta en 8.1.2). Reporta exito parcial con honestidad.

#### 8.9.4 CLI directa (`scripts/create_course.py`)

Para uso directo o de subagentes sin pasar por HTTP, hay una CLI que llama al orquestador
**en proceso** (necesita acceso a la BD y a la config de LLM, asi que corre dentro del contenedor api):

```bash
docker compose exec -T api sh -c \
  'cd /app && uv run python scripts/create_course.py "Fundamentos de seguridad alimentaria"'

# con documento, matricula y artefacto:
docker compose exec -T api sh -c 'cd /app && uv run python scripts/create_course.py \
  "Onboarding" --document-id <uuid> --enroll-user-id <uuid> --artifacts podcast'
```

Por defecto actua como el admin de la primera organizacion; se puede fijar con `--org-id` /
`--admin-id`. Sale con codigo 0 si el curso quedo validado, 1 si no. Imprime el mismo JSON estructurado
que el endpoint.

#### 8.9.5 Los tres caminos, un solo orquestador

Los tres canales (tool A2A, CLI, endpoint HTTP `/ext/v1/courses/full`) convergen en una sola funcion,
`create_course_end_to_end` en `src/services/course_orchestration.py`, fiel al principio del inicio de
este documento: una misma capa de logica de negocio, no se duplica codigo. El orquestador reutiliza
`CourseService`, `CourseSchemaService`, el runner de knowledge packs (con su reintento/supersede), el
prewarm de renders, `EnrollmentService` y los generadores de media — no reimplementa la generacion.
