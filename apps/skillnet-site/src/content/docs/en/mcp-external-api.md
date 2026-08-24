---
title: "MCP external API"
order: 45
section: "extensibility"
---

---
type: architecture
tags: [skillnet, api, mcp, webhooks, integrations, ai-native]
---

## 8. MCP Server & External API

SkillNet is the skills data layer of the ecosystem. The training app is the interface for collecting data. This document defines how that data goes out to the outside world: REST API for classic integrations, MCP Server for AI agents, webhooks for automations, and export for offline analysis.

Design principle: **the same business logic layer** feeds the internal API (frontend), the external API (third parties), and the MCP Server. Code is not duplicated. All three channels call the same Python services.

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

### 8.1 REST API for external consumers

Separate from the internal API used by the frontend. Different prefix, different authentication, different rate limiting.

#### 8.1.1 Authentication: API Keys

API keys are for machine-to-machine integrations. There are no sessions, no cookies.

**Data model:**

```sql
CREATE TABLE api_keys (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id),
    created_by  uuid NOT NULL REFERENCES users(id),
    name        text NOT NULL,              -- "BambooHR sync", "Metabase read"
    key_hash    text NOT NULL,              -- bcrypt hash of the key
    key_prefix  text NOT NULL,              -- "sn_example" (first 8 chars, for identification)
    scopes      text[] NOT NULL DEFAULT '{}', -- ['skills:read', 'skills:write', 'users:read']
    last_used_at timestamptz,
    expires_at  timestamptz,                -- null = never expires
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);
```

**Key format:** `sn_{32_chars_random}` (example: `sn_example_00000000000000000000000000000000`). The `sn_` prefix allows recognizing that it is a SkillNet key. The full key is shown to the user ONLY once when it's created. In the database only the hash is stored.

**Sent in request:**

```http
GET /ext/v1/skills
Authorization: Bearer sn_example_00000000000000000000000000000000
```

**Available scopes:**

| Scope | Allows |
|-------|---------|
| `skills:read` | Read taxonomy, matrix, gaps, who_knows |
| `skills:write` | Verify skills (verify_skill) |
| `users:read` | Read employee profiles and their skills |
| `courses:read` | Read course catalog and progress |
| `export:read` | Download full CSV/JSON exports |
| `webhooks:manage` | Register and manage webhooks |

**Management:** The admin creates and revokes API keys from the company panel (`/admin/settings/api-keys`). They can assign individual scopes to each key.

#### 8.1.2 Endpoints

Prefix: `/ext/v1/`. All endpoints are automatically scoped to the API key's `org_id`.

##### Skills taxonomy

```
GET /ext/v1/skills
```

Lists all skills in the organization, grouped by category.

**Query params:**
- `category` (string, optional) -- filter by category name
- `search` (string, optional) -- search by skill name (ILIKE)

**Response 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "name": "returns",
      "description": "Full returns management process",
      "category": {
        "id": "uuid",
        "name": "Sales"
      }
    }
  ],
  "meta": {
    "total": 23,
    "timestamp": "2026-07-14T10:30:00Z"
  }
}
```

##### Full skill matrix

```
GET /ext/v1/skills/matrix
```

Employee x skill matrix with levels. The view a manager sees at a glance in the app, here in data format.

**Query params:**
- `page` (int, default 1) -- page
- `per_page` (int, default 50, max 200) -- employees per page
- `skill` (string, optional) -- filter by skill name
- `level` (enum: low/medium/high, optional) -- filter by minimum level
- `user_id` (uuid, optional) -- filter by employee

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
            "skill_name": "returns",
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

##### Gap analysis

```
GET /ext/v1/skills/gaps
```

Detects gaps: skills the organization needs but where few employees have sufficient level.

**Query params:**
- `skill` (string, optional) -- gap for a specific skill
- `min_level` (enum: low/medium/high, default medium) -- minimum level considered "covered"
- `threshold` (float 0-1, default 0.5) -- ratio below which it is considered a gap (e.g.: if < 50% of the team has it, it's a gap)

**Response 200:**

```json
{
  "data": [
    {
      "skill": {
        "id": "uuid",
        "name": "python",
        "category": "Technology"
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

`gap_severity`: `critical` (< 20% coverage), `warning` (20-50%), `moderate` (50-70%).

##### Skills of an employee

```
GET /ext/v1/users/{user_id}/skills
```

Complete skill profile of an individual employee.

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
        "skill_name": "returns",
        "category": "Sales",
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

##### Verify a skill

```
POST /ext/v1/skills/verify
```

Registers or updates the level of a skill for a user. Equivalent to `verify_skill()`.

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

`skill_id` can be replaced with `skill_name` (string) -- the system searches by name within the org. If it doesn't exist, it returns 404.

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

Requires `skills:write` scope.

##### Find who knows

```
GET /ext/v1/skills/who-knows
```

Finds employees with a given skill, optionally filtered by minimum level.

**Query params:**
- `skill` (string, required) -- skill name
- `min_level` (enum: low/medium/high, default low) -- minimum level
- `limit` (int, default 10) -- maximum results

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
    "skill": "returns",
    "min_level": "low",
    "total": 2
  }
}
```

##### Create a full course in one call

```
POST /ext/v1/courses/full
```

**Implemented (2026-08).** Creates a dynamic course from start to finish in a single request:
proposes the schema, generates the knowledge packs (with automatic retries), reviews all nodes,
validates the course, and warms up the first renders. Optionally enrolls an employee and generates
artifacts (podcast, infographic). Replaces the seven-call dance that the creation
assistant used to do (`create -> propose -> poll job -> PUT schema -> poll packs -> review -> validate`).

The `org_id` and creating admin come from the API key (`created_by` column). Requires scope
`courses:write`. Underneath, it reuses the same services as the admin panel; it does not reimplement
anything about generation. The logic lives in `apps/skillnet-api/src/services/course_orchestration.py`
(`create_course_end_to_end`).

**Request body:**

```json
{
  "title": "Food hygiene and handling",
  "document_id": "uuid | null",
  "intent_density": 3,
  "enroll_user_id": "uuid | null",
  "generate_artifacts": ["podcast", "infographic"],
  "artifact_node_limit": 1
}
```

Only `title` is mandatory. `document_id` anchors the schema in an already processed document
(`status='ready'`); without it, the course is synthesized from the title. `intent_density` (1-5)
regulates depth.

**Response 201** (honestly reports partial success — it never hangs waiting):

```json
{
  "course_id": "uuid",
  "title": "Food hygiene and handling",
  "schema_status": "validated",
  "schema_version": 2,
  "node_count": 8,
  "packs_ready": 6,
  "packs_all_ready": false,
  "packs_summary": "6/8 nodes ready",
  "nodes": [
    {"node_id": "uuid", "title": "Importance of hygiene", "status": "ready"},
    {"node_id": "uuid", "title": "Cleaning and disinfection", "status": "failed"}
  ],
  "reviewed": true,
  "validated": true,
  "enrolled_user_id": "uuid | null",
  "prewarm_spawned": true,
  "artifacts": [{"artifact_id": "uuid", "node_id": "uuid", "kind": "podcast", "status": "pending"}],
  "warnings": ["only 6/8 knowledge packs reached ready within the timeout"]
}
```

The per-node status of `packs` can be `ready`, `review_required`, `failed`, `pending`, `stale`, or
`missing`. Since DeepSeek is unstable with strict JSON, the runner retries in a bounded way
(`max_attempts=3`) and supersedes previous versions of the schema; if some node does not converge
within the time limit, the course is still validated regardless (validation doesn't depend on the
packs) with a `warning` and the actual count. The remaining packs keep completing in the background.

##### Mentorship suggestions

```
GET /ext/v1/skills/mentorship
```

Returns mentor-mentee pairs based on real skills data.

**Query params:**
- `skill` (string, optional) -- filter by specific skill
- `limit` (int, default 20) -- maximum pairs

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
        "name": "returns"
      }
    }
  ],
  "meta": {
    "total_pairs": 8
  }
}
```

Uses the same matching query documented in `data-model.md` (mentor with level=high, mentee with level=low, same org, different user).

#### 8.1.3 Rate limiting

Applied per API key, not per IP. Implemented with a FastAPI middleware that uses counters in PostgreSQL (`api_key_usage` table) or Redis if available.

| Plan | Requests/minute | Requests/day |
|------|-----------------|--------------|
| Self-hosted (default) | 120 | No limit |
| SaaS Starter (future) | 60 | 10,000 |
| SaaS Growth (future) | 120 | 50,000 |

**Headers in each response:**

```http
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 117
X-RateLimit-Reset: 1720954260
```

**Response 429 when exceeded:**

```json
{
  "error": "rate_limit_exceeded",
  "message": "120 requests per minute exceeded. Retry after 23 seconds.",
  "retry_after": 23
}
```

For self-hosted, the limit is configurable via environment variable (`SKILLNET_API_RATE_LIMIT=120`). The SME that doesn't need a limit can set it to 0 (no limit).

#### 8.1.4 Pagination

All endpoints that return lists use offset-based pagination.

**Params:** `page` (int, default 1) and `per_page` (int, default 50, max 200).

**Meta in response:**

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

Cursor-based pagination is not used because the data volume of an SME (dozens of employees, dozens of skills) doesn't justify it. If needed for enterprise in the future, it can be added without breaking the existing contract.

#### 8.1.5 Versioning

Path-based: `/ext/v1/`. If a breaking change is needed, `/ext/v2/` is created while keeping v1 operational for at least 12 months.

**Informational headers:**

```http
X-SkillNet-API-Version: v1
X-SkillNet-Deprecation: 2028-01-01  # only if v1 is going to be retired
```

**Rule:** a new field in the response is NEVER a breaking change (clients must ignore unknown fields). A removed field or a type change IS breaking and requires a new version.

#### 8.1.6 Error format

Consistent throughout the API:

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

HTTP codes used: 200, 201, 400 (bad request), 401 (no auth), 403 (insufficient scope), 404 (not found), 422 (validation), 429 (rate limit), 500 (server error).

---

### 8.2 MCP Server

> **Note (2026-08-04):** this section was written before `/ext/v1` existed and before
> MCP standardized graphical interfaces. Two decisions from here have become outdated: the
> **SSE** transport (deprecated in MCP in favor of Streamable HTTP) and **direct access to
> PostgreSQL with asyncpg** (today it would duplicate the logic that `/ext/v1` already has). The
> revision is in section 8.8, which also covers the case of offering SkillNet as a connector to
> third-party AI clients. Read 8.8 before implementing anything from 8.2.

#### 8.2.1 What it is

A separate process that exposes SkillNet's data as MCP (Model Context Protocol) tools. Any MCP-compatible AI agent (Claude Desktop, custom assistants, Slack agents) can connect and query skills data in real time.

It is not part of the FastAPI server. It's an independent process that connects to the same PostgreSQL database.

```
┌──────────────────────────────────────────────────┐
│                  Docker Compose                   │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │  FastAPI     │  │  MCP Server  │  │PostgreSQL│ │
│  │  (port 8000) │  │  (port 3001) │  │(port 5432)│ │
│  │             │  │              │  │          │ │
│  │  Internal API│  │  Python      │  │  Shared  │ │
│  │  External API│  │  MCP SDK     │  │  Database │ │
│  │  SSE tutor  │  │  stdio/SSE   │  │          │ │
│  └──────┬──────┘  └──────┬───────┘  └────┬─────┘ │
│         │                │               │       │
│         └────────────────┴───────────────┘       │
│                    PostgreSQL connection          │
└──────────────────────────────────────────────────┘
```

#### 8.2.2 Exposed tools

Each MCP tool corresponds to a business function. The AI agent reads the tool's description and decides when to use it.

##### `verify_skill`

Registers or updates the level of a skill for a user.

```python
@server.tool()
async def verify_skill(
    user: str,          # employee's name or email
    skill: str,         # skill name
    level: str,         # "low", "medium", "high"
    verified_by: str = None  # verifier's name or email (optional)
) -> dict:
    """
    Verify or set a skill level for an employee.
    
    Use this when someone confirms that an employee knows how to do something.
    Examples:
    - "Juan already knows returns. Maria taught him." -> verify_skill("Juan", "returns", "high", "Maria")
    - "Set Laura's CSS level to medium" -> verify_skill("Laura", "css", "medium")
    
    Returns the updated skill record with the previous level.
    """
```

**Response:**

```json
{
  "user": "Juan Garcia",
  "skill": "returns",
  "level": "high",
  "previous_level": "medium",
  "verified_by": "Maria Lopez",
  "timestamp": "2026-07-14T10:30:00Z"
}
```

##### `who_knows`

Finds people with a given skill.

```python
@server.tool()
async def who_knows(
    skill: str,          # skill name
    min_level: str = "low"  # minimum level: "low", "medium", "high"
) -> dict:
    """
    Find employees who have a specific skill at or above a minimum level.
    
    Use this when someone asks "who can do X?" or "who knows X?"
    Examples:
    - "Who knows CSS?" -> who_knows("css")
    - "Who's an expert in returns?" -> who_knows("returns", "high")
    
    Returns a list of matching employees with their levels and when they were last assessed.
    """
```

**Response:**

```json
{
  "skill": "returns",
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

Skills gap analysis for a team or specific skill.

```python
@server.tool()
async def get_gap(
    skill: str = None,  # specific skill (optional)
    min_level: str = "medium"  # minimum level considered "covered"
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

**Response (no specific skill):**

```json
{
  "gaps": [
    {
      "skill": "python",
      "category": "Technology",
      "coverage": "2/12 employees (17%)",
      "severity": "critical",
      "employees_below": ["Laura Perez", "Carlos Ruiz", "...8 more"]
    },
    {
      "skill": "excel",
      "category": "Technology",
      "coverage": "4/12 employees (33%)",
      "severity": "warning",
      "employees_below": ["Ana Lopez", "Pedro Gil", "...6 more"]
    }
  ],
  "summary": "2 critical gaps, 3 warnings out of 23 skills"
}
```

##### `list_skills`

Returns the full skills taxonomy.

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
      "name": "Sales",
      "skills": ["returns", "customer_service", "closing"]
    },
    {
      "name": "Technology",
      "skills": ["html_css", "excel", "python"]
    }
  ],
  "total_skills": 23
}
```

##### `get_user_skills`

Complete skill profile of an employee.

```python
@server.tool()
async def get_user_skills(
    user: str  # employee's name or email
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
    {"skill": "returns", "category": "Sales", "level": "high", "last_assessed": "3 days ago"},
    {"skill": "html_css", "category": "Technology", "level": "medium", "last_assessed": "1 week ago"}
  ],
  "summary": {"high": 2, "medium": 2, "low": 1, "total": 5}
}
```

##### `search_knowledge`

Semantic search across company documents.

```python
@server.tool()
async def search_knowledge(
    query: str,      # question or search term
    limit: int = 5   # maximum results
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

**Implementation:** Generates a query embedding with the same model used for indexing (`multilingual-e5-small`), searches by cosine distance in `document_chunks`, returns the most relevant chunks with a reference to the source document.

**Response:**

```json
{
  "query": "return policy",
  "results": [
    {
      "content": "The customer has 30 natural days to return any product with the original receipt...",
      "source": "Returns Manual",
      "page": 3,
      "section": "Deadlines",
      "relevance": 0.92
    }
  ],
  "total": 3
}
```

#### 8.2.3 MCP Resources

Static resources that the AI agent can read for context.

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

Returns the taxonomy in a format readable by the agent. It updates automatically when the admin adds or modifies skills.

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

#### 8.2.4 Technical implementation

**SDK:** `mcp` (Anthropic's official Python MCP SDK). Version >= 1.0.

**Transport:**

| Mode | When to use it |
|------|---------------|
| **stdio** | Local connection. Claude Desktop connects to the MCP server as a child process. For the admin using Claude on their own machine. |
| **SSE** | Remote connection. The MCP server listens on an HTTP port. For AI agents connecting from outside (Slack, n8n, cloud agents). |

For self-hosted, both modes are available. Docker Compose brings up the MCP server with SSE by default on port 3001.

**File structure:**

```
services/
  mcp-server/
    __init__.py
    server.py          # Entry point, registers tools and resources
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
    db.py              # PostgreSQL connection (asyncpg)
    auth.py            # MCP auth token validation
    config.py          # Environment variables
    Dockerfile
```

**Database connection:**

The MCP server connects to the same PostgreSQL instance as FastAPI. It uses `asyncpg` directly (not SQLAlchemy). Separate connection pool so as not to interfere with FastAPI's pool.

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

**MCP authentication:**

For SSE mode (remote access), the MCP server validates a token that is an API key from the `api_keys` table. The required scope is `mcp:connect`. In stdio mode (local), no authentication is needed -- the process runs on the admin's machine.

**Docker Compose configuration (fragment):**

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

**Claude Desktop configuration (stdio, local):**

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

Push notifications to external URLs when relevant events occur. For automations with n8n, Zapier, Make, or custom systems.

#### 8.3.1 Events

| Event | When it fires | Key payload |
|--------|-------------------|---------------|
| `skill_level_changed` | An employee's level in a skill goes up or down | user, skill, old_level, new_level, source |
| `course_completed` | An employee finishes all modules of a course | user, course, score, completed_at |
| `enrollment_created` | An admin assigns a course to an employee | user, course, assigned_by, deadline |
| `gap_detected` | An analysis detects a critical gap (< 20% coverage) | skill, coverage_ratio, affected_users_count |
| `certificate_expiring` | A certificate expires in 30 days or less | user, certificate, expires_at, days_remaining |
| `feedback_submitted` | An employee submits post-course feedback | user, course, responses |

#### 8.3.2 Webhook registration

**Data model:**

```sql
CREATE TABLE webhooks (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id),
    created_by  uuid NOT NULL REFERENCES users(id),
    url         text NOT NULL,              -- https://hooks.example.com/skillnet
    secret      text NOT NULL,              -- to sign payloads (HMAC-SHA256)
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

**Registration via API:**

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

Requires `webhooks:manage` scope.

**Management:** The admin can also create webhooks from the company panel (`/admin/settings/webhooks`). They can see the delivery history, resend failed deliveries, and deactivate webhooks.

#### 8.3.3 Payload format

All events follow the same format:

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
      "name": "returns",
      "category": "Sales"
    },
    "old_level": "medium",
    "new_level": "high",
    "source": "checkpoint",
    "triggered_by": "system"
  }
}
```

**HMAC signature:**

Each request includes an `X-SkillNet-Signature` header with an HMAC-SHA256 of the body using the webhook's `secret`.

```http
POST https://hooks.example.com/skillnet
Content-Type: application/json
X-SkillNet-Signature: sha256=a1b2c3d4e5f6...
X-SkillNet-Event: skill_level_changed
X-SkillNet-Delivery: evt_uuid
```

The receiver verifies the signature to ensure the payload comes from SkillNet and hasn't been modified.

#### 8.3.4 Retries with exponential backoff

If delivery fails (10-second timeout, or response code >= 400):

| Attempt | Wait | Accumulated time |
|---------|--------|------------------|
| 1 | Immediate | 0 |
| 2 | 1 minute | 1 min |
| 3 | 5 minutes | 6 min |
| 4 | 30 minutes | 36 min |
| 5 | 2 hours | 2h 36min |
| 6 | 12 hours | 14h 36min |

After 6 failed attempts, the status changes to `exhausted` and it is marked as failed. The admin can resend manually from the panel.

If a webhook has more than 10 consecutive `exhausted` deliveries, it is automatically deactivated and the admin is notified.

---

### 8.4 Data export

#### 8.4.1 CSV: skills matrix

```
GET /ext/v1/export/skills-matrix.csv
Authorization: Bearer sn_example_...
```

Direct download of the skills matrix in CSV. Format:

```csv
employee_name,employee_email,skill_name,skill_category,level,source,last_assessed_at
Juan Garcia,juan@empresa.com,returns,Sales,high,checkpoint,2026-07-10T14:00:00Z
Juan Garcia,juan@empresa.com,html_css,Technology,medium,manual,2026-07-08T09:00:00Z
Ana Lopez,ana@empresa.com,returns,Sales,medium,checkpoint,2026-07-09T11:00:00Z
```

Also available from the company panel as an "Export CSV" button.

Requires `export:read` scope.

#### 8.4.2 JSON: full profiles

```
GET /ext/v1/export/profiles.json
Authorization: Bearer sn_example_...
```

Downloads all employee profiles with their skills, courses in progress, and completed exercises.

```json
{
  "exported_at": "2026-07-14T10:30:00Z",
  "organization": "My Company",
  "employees": [
    {
      "id": "uuid",
      "full_name": "Juan Garcia",
      "email": "juan@empresa.com",
      "role": "employee",
      "hired_at": "2025-01-15",
      "skills": [
        {"name": "returns", "level": "high", "source": "checkpoint"}
      ],
      "enrollments": [
        {
          "course": "HTML Basics",
          "status": "in_progress",
          "score": null,
          "deadline": "2026-08-01"
        }
      ]
    }
  ]
}
```

Requires `export:read` scope.

#### 8.4.3 Scheduled reports

Future implementation (Phase 3). Concept:

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

Or with email delivery:

```json
{
  "delivery": {
    "method": "email",
    "to": ["rrhh@empresa.com"]
  }
}
```

The system generates the export according to the configured frequency and delivers it to the destination. Useful for the SME that wants a CSV in their email every Monday without having to log into the platform.

---

### 8.5 Integration patterns

#### 8.5.1 HR tool (BambooHR, Factorial, Personio)

**Data flow: bidirectional.**

```
BambooHR                          SkillNet
   │                                 │
   ├── Employee onboarding ──────►  Create user
   ├── Employee offboarding ─────►  Deactivate user
   ├── Department change ────────►  Update team
   │                                 │
   │  ◄─── skill_level_changed ─────┤  Webhook
   │  ◄─── course_completed ────────┤  Webhook
   │                                 │
   └── Skills query ─────────────►  GET /ext/v1/users/{id}/skills
```

**Implementation:**

1. **MVP phase:** Manual CSV import. The admin exports employees from BambooHR as CSV and imports it into SkillNet.
2. **Phase 2:** Webhook from BambooHR -> SkillNet. When an employee is onboarded/offboarded in BambooHR, SkillNet receives the notification and updates.
3. **Phase 3:** Bidirectional via API. BambooHR queries skills from SkillNet and SkillNet reads employee data from BambooHR.

**Concrete example with Factorial (popular among Spanish SMEs):**

```python
# Factorial webhook → SkillNet
# Factorial notifies employee onboarding
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
# SkillNet creates the user automatically
```

#### 8.5.2 AI agent (Claude Desktop, ChatGPT, custom agent)

**Scenario 1: Claude Desktop with MCP (local mode)**

The company admin uses Claude Desktop as an assistant. They connect SkillNet's MCP server as a data source.

```
Admin opens Claude Desktop
  → Claude sees SkillNet's tools (verify_skill, who_knows, etc.)

Admin: "Who can cover a cash register shift tomorrow?"
Claude:
  1. Calls who_knows("cash_register", "medium")
  2. Receives: Juan (high), Ana (medium), Carlos (medium)
  3. Calls get_user_skills("Juan") to check availability
  4. Answers: "Juan is the most qualified on cash register (high level,
     last exercise 2 days ago). Ana and Carlos can also cover it
     but with medium level."

Admin: "Confirm that Laura already knows how to close the register, Juan taught her yesterday"
Claude:
  1. Calls verify_skill("Laura", "register_closing", "medium", "Juan")
  2. SkillNet updates the record
  3. Answers: "Recorded. Laura goes from low to medium on register closing,
     verified by Juan."
```

**Configuration:** The admin installs SkillNet MCP in Claude Desktop by adding the JSON configuration to `claude_desktop_config.json`. In local mode (stdio), it points directly at the process. In remote mode (SSE), it points to the MCP server's URL with a token.

**Scenario 2: Custom agent in Slack**

A Slack bot connected via SSE to SkillNet's MCP server. Employees ask in a channel and the bot answers.

```
#general
@skillbot who knows python?
  → Bot calls who_knows("python", "medium")
  → "Juan Garcia (high), Ana Lopez (medium). Juan's latest data point: 3 days ago."

@skillbot what does the kitchen team lack?
  → Bot calls get_gap(skill=None) and filters by team
  → "Critical gaps: hygiene (only 1/5 covered), allergens (2/5)."
```

**Scenario 3: ChatGPT with function calling**

ChatGPT doesn't use MCP natively, but it can consume the external REST API via function calling or GPT Actions.

```python
# Function definitions for ChatGPT
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
# ChatGPT calls GET /ext/v1/skills/who-knows?skill=X&min_level=Y
```

#### 8.5.3 BI tool (Metabase, Grafana)

**Pattern: direct PostgreSQL (read-only) connection or via API.**

**Option A: Direct connection (self-hosted)**

Metabase connects directly to SkillNet's PostgreSQL database with a read-only user.

```sql
-- Create read-only user for BI
CREATE USER metabase_reader WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE skillnet TO metabase_reader;
GRANT USAGE ON SCHEMA public TO metabase_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_reader;
```

Advantages: no rate limit, custom SQL queries, complex joins.
Disadvantages: direct coupling to the schema (if tables change, dashboards break).

**Option B: Via REST API**

Metabase queries SkillNet's API on scheduled intervals and materializes the data in its own database.

```
GET /ext/v1/skills/matrix      → "Skills Matrix" table in Metabase
GET /ext/v1/skills/gaps         → "Skills Gaps" table in Metabase
GET /ext/v1/export/profiles.json → "Employee Profiles" table in Metabase
```

**Pre-suggested dashboards:**

| Dashboard | Source data | Questions it answers |
|-----------|-------------|------------------------|
| Skills coverage | skills/matrix | What % of the team masters each skill? |
| Gaps by team | skills/gaps | Where are we weakest? |
| Training progress | enrollments + attempts | Who is advancing and who is stuck? |
| Time trend | historical user_skills | Are we improving as a team? |
| Training ROI | enrollments + user_skills | How many new skills per completed course? |

**Grafana:** Same pattern. Direct connection to PostgreSQL via the native PostgreSQL plugin. Useful for real-time alerts (e.g.: "notify if any skill's coverage ratio drops below 30%").

---

### 8.6 Channel summary by use case

| Who | What they need | Channel |
|-------|-------------|-------|
| SME without IT | See who knows what | Web app (skill matrix) + CSV export |
| SME with Excel | Monthly skills report | Scheduled or manual CSV export |
| Manager with Claude Desktop | Ask in natural language about their team | MCP Server (stdio, local) |
| Slack/Teams bot | Skills queries from chat | MCP Server (SSE, remote) or REST API |
| n8n / Zapier | Automate: course completed -> notify | Webhooks |
| BambooHR / Factorial | Sync employees | REST API + webhooks |
| Metabase / Grafana | Skills dashboards | Direct PostgreSQL connection or REST API |
| Custom AI agent | Query skills programmatically | MCP Server or REST API |
| Data analyst | Offline analysis | JSON/CSV export |

---

### 8.7 Implementation roadmap

| Phase | What is built | When |
|------|-----------------|--------|
| **MVP** | Business logic (verify_skill, who_knows, get_gap) as internal Python services. CSV export from the company panel. No external API yet. | Phase 1 (current) |
| **Phase 2** | External REST API (`/ext/v1/`) with API keys. Basic MCP server (3 tools: who_knows, get_gap, list_skills). Webhooks for skill_level_changed and course_completed. | Post-grant |
| **Phase 3** | Full MCP server (6 tools + resources). All webhooks. JSON export. BambooHR/Factorial integrations. Scheduled reports. | Scale |

Each phase builds on the previous one. The business logic written in Phase 1 is reused in the APIs and MCP of Phases 2 and 3. Nothing is rewritten.

---

### 8.8 SkillNet as a connector for AI clients (exploration, not committed)

**Status: future possibility.** Nothing in this section is planned or has a date. It is documented
so the decision is on record for the day it's picked back up, and to correct what section 8.2
took for granted.

Section 8.2 assumes the MCP user is *the admin of the instance itself*, connecting their
Claude Desktop to their SkillNet via stdio. This section covers the opposite: **exposing SkillNet
outward** so that any Claude user (or other MCP host) can connect their instance as a remote
connector and query their skills data from the conversation.

It's the literal application of this document's opening paragraph — "SkillNet is the skills
data layer of the ecosystem" — to a distribution channel that already exists as of 2026.

#### 8.8.1 The four layers and which one is missing

| Layer | What it is | Status |
|------|--------|--------|
| 1. Organization-scoped business logic | `SkillService`, scoped by `org_id` on each call | **done** |
| 2. Remote transport + end-user authentication | Streamable HTTP + OAuth 2.1 | **doesn't exist** |
| 3. MCP tools | thin wrapper over `/ext/v1` | partial (the API exists, the wrapper doesn't) |
| 4. MCP App: graphical interface inside the chat | `ui://` resources | doesn't exist |

The bulk of the work is layer 2. Layers 3 and 4 are small on top of it.

What no longer needs solving: **isolation by organization**. All `/ext/v1` endpoints
receive the `org_id` from the credential and propagate it to the service
(`src/routes/ext/skills.py`). A multi-tenant connector rests on that as-is; the OAuth
token becomes the carrier of the `org_id` instead of the API key, and underneath nothing changes.

#### 8.8.2 Hardening `/ext/v1` beforehand

Before the external API is consumed by someone other than us, `_get_api_key()` in
`src/routes/ext/auth.py` needs to enforce two things that the data model already accounts for
but the dependency doesn't yet check:

- **`scopes`**: the `api_keys` table stores them and section 8.1.1 specifies them, but no
  route enforces them today. `POST /skills/verify` must require `skills:write`; reads must
  require `skills:read`.
- **`expires_at`**: only `is_active` is checked.

This is the first task of any work in this direction, and it is independent of the rest.

#### 8.8.3 Corrections to section 8.2

**Transport: Streamable HTTP, not SSE.** The SSE transport was deprecated in MCP. For remote
access, Streamable HTTP is used; stdio remains valid for the local case in 8.2.

**The MCP server is a client of `/ext/v1`, not of PostgreSQL.** Section 8.2.4 proposes
`asyncpg` against the same database. It was written when the external API didn't exist. Today
that would duplicate the organization scoping, level validation, and error handling on a
second path to the data, against the principle stated at the start of this document. The server
speaks HTTP with `/ext/v1` and doesn't need database credentials.

**Location: `packages/skillnet-mcp/`, TypeScript.** Consistent with `packages/mcp-md-reader` and
`packages/a2tl-video`, and it's where the MCP Apps SDKs live.

#### 8.8.4 Tool split: reads for the model, writes for the interface

MCP Apps (SEP-1865) adds `_meta.ui.visibility`, which accepts `["model"]`, `["app"]`, or both. A
tool marked `["app"]` **does not appear in the model's list of tools**: only the app's own
interface can invoke it, from the same connection.

| Tool | `visibility` | Annotation | Interface |
|------|-------------|-----------|----------|
| `who_knows` | `model` | `readOnlyHint` | yes |
| `get_gap` | `model` | `readOnlyHint` | yes |
| `get_user_skills` | `model` | `readOnlyHint` | yes |
| `list_skills` | `model` | `readOnlyHint` | no, text is enough |
| `verify_skill` | **`app`** | `destructiveHint` | triggered by a button |

That the only write is `app`-only is this section's design decision. A model that can raise an
employee's skill level on its own is an unacceptable failure in a personnel data product. With
`visibility: ["app"]` it's not a prompt instruction that can be ignored: the tool doesn't exist
for the model. There is still a human pressing a button.

#### 8.8.5 What the graphical interface adds

An MCP App is a self-contained HTML that the server publishes as a `ui://` resource, with
`mimeType` `text/html;profile=mcp-app`, linked to a tool via `_meta.ui.resourceUri`. The host
renders it in an isolated iframe inside the conversation.

It turns the scenario already described in 8.5.2 — "who can cover a cash register shift
tomorrow?" — from a paragraph of prose into the actual skill matrix, with levels, last
assessment date, and a verify button that calls `verify_skill` without going through the model.

Two standard details that matter to the design:

- **`structuredContent` vs. `content`**: `content` is seen by the model and the app;
  `structuredContent` goes only to the app, typed. The full matrix travels in `structuredContent`
  and a two-line summary goes in `content`. The model doesn't consume the entire table in tokens.
- **CSP `default-src 'none'` by default**: the iframe can't make a single network request unless
  it's declared in `_meta.ui.csp.connectDomains`. This is avoided: the interface gets data by
  calling tools, not the API on its own. It also doesn't expose credentials to the browser.

There are standardized CSS variables (`--color-background-primary`, `--font-sans`, ...) that the
host injects; using them, the interface respects the client's light/dark theme with no extra work.

On reusing components from `skillnet-web`: `components/courses/kit/` carries along
`NodeRenderContext` and OpenUI Lang, which don't fit in a self-contained bundle. The first views
are written lightweight and separate; if the channel proves valuable, the pure presentation
components are extracted into a shared package.

#### 8.8.6 Authentication: the big block

MCP clients don't let the user paste a `client_id` and a `client_secret`. They require
**OAuth 2.1 with Dynamic Client Registration** (or Client ID Metadata Documents): the client
registers on the fly. SkillNet would need to publish:

- `/.well-known/oauth-protected-resource` (RFC 9728)
- `/.well-known/oauth-authorization-server`
- `/register` — DCR, `application/json` (RFC 7591)
- `/authorize` — validating redirect URI, scope, and PKCE
- `/token` — `application/x-www-form-urlencoded`, single-use code, PKCE verification

Plus OAuth 2.1's requirement to rotate or bind public clients' refresh tokens to the issuer.

Today SkillNet has cookie sessions for the SPA and API keys for machines. What's missing is the
intermediate case: *this specific person, from this organization, authorizes an external client
to read their skills data*. It is real work and is the reason this section is not a small task.

#### 8.8.7 Self-hosted and connector directories

SkillNet is self-hosted: one instance per company, each with its own URL. That fits poorly with
the "one directory connector points to a single domain" model, but directories do support
**bring-your-own-connection** connectors, where the user supplies their own URL and credentials
when connecting. That's the right fit.

And there's an earlier step that doesn't depend on anyone: in clients that support custom remote
connectors, any user can add one by pasting a URL, without review or approval. The first clients
don't need SkillNet to be listed anywhere. The directory is distribution, not a technical
requirement.

If the listing is ever requested, the requirements that cause the most rejections are: each tool
with `title` and its `readOnlyHint` / `destructiveHint` annotation, HTTPS, OAuth, public
documentation with usage examples, and a **public and complete privacy policy** — whose absence
is an outright rejection. For a product that handles employee data, that policy is needed anyway,
before any directory.

#### 8.8.8 Order if resumed

1. Enforce `scopes` and `expires_at` in `/ext/v1` (8.8.2). Independent and cheap.
2. Remote MCP server over Streamable HTTP, authenticated with an API key, wrapping `/ext/v1`.
   Already useful for one's own instance or a pilot client, and validates whether the tools are good.
3. OAuth 2.1 with DCR (8.8.6). The expensive block. From here anyone can connect.
4. MCP App: interface for `who_knows` and `get_gap`.
5. Directory listing, if it makes commercial sense by then.

Step 2 is cheap and answers the question that matters — whether the product feels useful inside
an assistant. It's not worth paying for step 3 without having gone through step 2.

---

### 8.9 A2A service implemented (`apps/skillnet-a2a`)

**Status: implemented and in the compose.** It is the materialization of step 2 of the 8.8.8
roadmap: a remote server that wraps `/ext/v1` and exposes SkillNet's capabilities to external
agents. It does not talk to PostgreSQL: it is an HTTP client of `/ext/v1` (principle from 8.8.3).
It lives in its own process/container (`docker/a2a.Dockerfile`, compose profile), published only
on `127.0.0.1`.

#### 8.9.1 Protocol and authentication

Speaks **A2A JSON-RPC 2.0 over HTTP** (not MCP yet; same family of "tools for agents"):

- `GET /.well-known/agent.json` — the AgentCard: name, version, `skills[]`, and auth schema.
- `POST /` — `message/send` and `tasks/get` methods.

Two credentials, in two hops:

1. The external agent authenticates to the A2A with a **bearer `A2A_AUTH_KEY`** (mandatory: the
   server refuses to start without it, see `require_auth_key` in `src/main.py`).
2. The A2A calls `/ext/v1` with its own **internal API key** (`A2A_INTERNAL_API_KEY`), created at
   bootstrap with scopes `skills:read`, `skills:write`, `users:read`, `courses:write`.

In between there's an LLM orchestrator (`src/orchestrator.py`) that interprets the natural
language of the message and decides which tool to call, in a bounded tool-calling loop.

#### 8.9.2 Exposed tools

Each tool is a thin wrapper over an `/ext/v1` endpoint (`src/tools.py` + `src/skillnet_client.py`):

| Tool | `/ext/v1` endpoint | What it does |
|------|--------------------|----------|
| `who_knows` | `GET /skills/who-knows` | Finds employees with a skill (filtered by minimum level) |
| `get_gap` | `GET /skills/gaps` | Analyzes skills gaps in the organization |
| `verify_skill` | `POST /skills/verify` | Registers/updates an employee's skill level |
| `list_skills` | `GET /skills` | Lists the skills taxonomy by category |
| `get_user_skills` | `GET /users/{id}/skills` | Complete skill profile of an employee |
| **`create_course`** | `POST /courses/full` | **Creates a complete course from start to finish in one call** |

#### 8.9.3 `create_course` (new, 2026-08)

The tool the owner requested: an agent creates a course "like the rest of the tools it has."
Wraps `POST /ext/v1/courses/full` (8.1.2). The client uses a long timeout (600 s) because the
whole flow —proposing the schema, generating packs with retries, reviewing, validating,
warming up— runs on the server and can take minutes with a real provider.

**Parameters:** `title` (required), `document_id`, `intent_density` (1-5), `enroll_user_id`,
`generate_artifacts` (e.g. `["podcast", "infographic"]`).

**Natural language examples** that the orchestrator maps to the tool:

- "Create a course about food safety" -> `create_course(title="Food safety")`
- "Set up a 5-node onboarding course from document X and enroll Maria" ->
  `create_course(title="Onboarding", document_id="X", enroll_user_id="<Maria>")`

**Returns** the `course_id`, the per-node status of the packs, `validated`, `enrolled_user_id`,
and `artifacts` (see the response body in 8.1.2). Honestly reports partial success.

#### 8.9.4 Direct CLI (`scripts/create_course.py`)

For direct use or by subagents without going through HTTP, there is a CLI that calls the
orchestrator **in-process** (it needs DB access and LLM config, so it runs inside the api
container):

```bash
docker compose exec -T api sh -c \
  'cd /app && uv run python scripts/create_course.py "Food safety fundamentals"'

# with document, enrollment, and artifact:
docker compose exec -T api sh -c 'cd /app && uv run python scripts/create_course.py \
  "Onboarding" --document-id <uuid> --enroll-user-id <uuid> --artifacts podcast'
```

By default it acts as the admin of the first organization; it can be set with `--org-id` /
`--admin-id`. It exits with code 0 if the course ended up validated, 1 otherwise. It prints the
same structured JSON as the endpoint.

#### 8.9.5 Three paths, one orchestrator

The three channels (A2A tool, CLI, `/ext/v1/courses/full` HTTP endpoint) converge on a single
function, `create_course_end_to_end` in `src/services/course_orchestration.py`, true to the
principle stated at the start of this document: the same business logic layer, no code
duplication. The orchestrator reuses `CourseService`, `CourseSchemaService`, the knowledge pack
runner (with its retry/supersede logic), the render prewarm, `EnrollmentService`, and the media
generators — it does not reimplement generation.
