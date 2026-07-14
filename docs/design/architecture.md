# Architecture

> **Status: v1 complete.** All sections have detailed specification documents linked below.

## Document index

| Document | What it covers |
|----------|----------------|
| [architecture.md](architecture.md) | System overview, layers, cross-cutting concerns, decided vs deferred |
| [data-model.md](data-model.md) | PostgreSQL schema — 15+ tables, indexes, key queries |
| [screens.md](screens.md) | 20 screen specs with routes, sections, data, states, actions |
| [design-system.md](design-system.md) | Visual tokens, component patterns, anti-patterns |
| [product.md](product.md) | What SkillNet is, roles, content types |
| [content-generation.md](content-generation.md) | LangGraph generation pipeline, 7 agent roles, RAG integration |
| [chat-agents.md](chat-agents.md) | Tutor and admin chat agents, PageIndex pattern, RAG decision tree |
| [rag-retrieval.md](rag-retrieval.md) | Document ingestion, chunking, hybrid search, reranking, embeddings |
| [backend-api.md](backend-api.md) | FastAPI project layout, 73 endpoints, dependency injection |
| [llm-integration.md](llm-integration.md) | Provider abstraction, streaming, prompt management, cost tracking |
| [background-processing.md](background-processing.md) | LangGraph persistence + PostgreSQL job runner, lifecycle flows |
| [docker-deployment.md](docker-deployment.md) | Docker Compose services, Dockerfiles, dev/prod, first-run |
| [security.md](security.md) | Auth, agent compartments, GDPR, API security, secrets |
| [mcp-external-api.md](mcp-external-api.md) | MCP Server, external REST API, webhooks, integrations |
| [frontend-backend-integration.md](frontend-backend-integration.md) | TanStack Query, SSE, Level 2/3 UI, file upload |
| [snml-spec.md](snml-spec.md) | SNML content format — Markdown + interactive components, dual render (doc/web) |

---

## System overview

SkillNet takes an organization's internal knowledge (manuals, processes, documentation) and turns it into a living learning system. The core flow:

```
Internal docs ──→ Ingestion ──→ Knowledge layer ──→ Agent teams ──→ Interface ──→ Learner
                                      ↑                                            │
                                      └────────────── progress ────────────────────┘
```

Knowledge flows in one direction: from raw documentation through structured knowledge to generated learning experiences. Learner progress feeds back into the knowledge layer to drive adaptation.

---

## Layers

### 1. Ingestion

Takes raw company documentation and transforms it into structured knowledge the system can reason about.

- **Input:** Markdown, PDFs, internal wikis, process documents
- **Output:** Structured knowledge units indexed for retrieval

**(deferred)** Chunking strategy. RAG conditional approach is documented (small docs go whole, large docs get chunked). The specific chunking method (semantic by sections with fixed fallback) will be decided when the ingestion pipeline is built.

**(deferred)** Update flow. When source documents change, how does the knowledge layer stay current? Full re-ingestion vs incremental updates.

### 2. Knowledge layer

The system's memory. Stores structured knowledge and makes it available to agents through retrieval.

| Component | Role |
|-----------|------|
| **PostgreSQL + pgvector** | Single database for all data: relational (users, courses, progress) and vector (embeddings). One backup, one connection, transactional joins between content and vectors. |
| **Access control** | Determines what knowledge is visible to whom |

**What we know from research:**

- Content-based classification of access levels caps at 78% accuracy ([semantic boundaries research](../research/semantic-boundaries/)). Privacy is a human decision, not a content property. The system must enforce organizational access decisions, not guess them.
- Compartment-based access (need-to-know) is the most promising model. An agent is booted with only the compartments its task requires. Control happens at boot (what it can see) and at the boundary (what it can emit), not inside the agent.

**Vector store: pgvector.** Embeddings live inside PostgreSQL as a `vector` column. One database for everything — relational queries and semantic search in the same transaction. At MVP scale (dozens of documents, hundreds of employees), pgvector is more than sufficient. If the system ever needs to handle millions of vectors at thousands of QPS, embeddings can migrate to a dedicated store without touching the relational schema.

**(open)** Knowledge graph. Whether relationships between knowledge units need explicit graph structure or if vector proximity + metadata is sufficient. The G-SPEC paper suggests 68% of security gains come from graph structure.

### 3. Agent teams

Specialized AI agents orchestrated with LangGraph. Each agent type has a distinct role:

| Agent | Responsibility |
|-------|---------------|
| **Ingestion agents** | Process raw documents into structured knowledge |
| **Content agents** | Generate courses, exercises, evaluations from knowledge |
| **Tutoring agents** | Guide learners through content, adapt pace, and answer questions on demand — retrieves from the knowledge layer (RAG) contextualized with the learner's progress |

**What we know from research:**

- Authority between agents follows a mandate model, not ownership ([multi-agent coordination research](../research/multi-agent-coordination/)). An agent acts on someone's behalf, for a specific purpose, with defined limits. When serving multiple users, its permissions are the intersection of all active mandates.
- Agent isolation enables reliable verification. If reviewer and author don't share context, error rates multiply (independent verification).

**Orchestration:** LangGraph manages agent state machines and transitions. Each agent type is a graph with defined nodes and edges.

**(open)** Agent communication. How agents pass results between each other — direct state handoff, shared memory, message queue.

**(open)** Mandate implementation. The mandate concept is clear (principal, agent, objective, permissions, limits) but the runtime representation and enforcement mechanism are not defined yet.

### 4. Interface layer

How content reaches the learner. Three generation levels, used where appropriate:

| Level | How | When to use |
|-------|-----|-------------|
| **1 — Static** | Pre-built React components, agent sends data | Login, settings, navigation, admin screens |
| **2 — Declarative** | Agent emits a compact spec (UIDL), renderer expands to HTML | Dashboards, course listings, reports, progress views |
| **3 — Generative** | Agent writes full HTML/CSS/JS | Personalized lessons, adaptive tutoring, agent responses |

Most of SkillNet is Level 1 and 2. Level 3 applies only where content, context, and user variability are all high — the moments where pre-designed screens aren't feasible.

**What exists:**

- [UIDL renderer](../../packages/mcp-ui-renderer/) — Level 2 implementation. 76% token savings vs equivalent HTML.

**Level 3 latency: deferred.** The approach for handling generation wait times (skeleton + SSE streaming, pre-generation, or waiting screen) will be decided when the generation pipeline is built. SSE infrastructure will already be in place from the tutor chat.

**Frontend architecture: single SPA.** One React app with React Router. Level 1 (static) are regular React components. Level 2 (declarative) uses a renderer component that takes a compact spec and paints it — the specific format (UIDL or otherwise) is not locked. Level 3 (generative) injects agent-generated HTML into an isolated container (shadow DOM or iframe) to prevent CSS conflicts. The user doesn't know which level they're seeing — navigation is the same everywhere.

**Routing: fixed routes with dynamic content.** Every screen has a predictable URL (`/dashboard`, `/courses/:id`, `/courses/:id/module/:mid/lesson/:lid`, `/admin/users`, `/settings`). URLs are shareable and browser back/forward works. When Level 3 generates content, it renders inside the fixed route — the URL doesn't change, only what's inside.

**State management: React Query (TanStack Query).** Server state (courses, progress, skills, exercises) is fetched and cached by React Query — the backend is the single source of truth. Local UI state (sidebar open, filter active, modal visible) uses plain `useState`. No global store needed. If a case arises later, Zustand can be added in minutes.

### 5. API

FastAPI serves as the interface between frontend and backend.

**API style: pragmatic REST.** Standard CRUD for data resources (`GET/POST/PUT/DELETE /api/v1/courses`) plus explicit action endpoints for operations (`POST /courses/{id}/generate`, `POST /courses/{id}/publish`, `POST /exercises/{id}/attempt`). No GraphQL, no pure REST. Routes say what they do.

**(open)** API contract details. Specific endpoints, request/response schemas, versioning.

**Authentication: session cookies via fastapi-users.** Login sends email + password, backend creates a session in PostgreSQL and returns an `httpOnly` cookie (7-day expiry). The browser sends the cookie automatically on every request — no token management in frontend code. Each device gets its own independent session. Account creation is admin-only by default (the admin creates employees from the panel); self-registration can be enabled per deployment as a config flag. Built on fastapi-users `CookieTransport`.

**Real-time: SSE (Server-Sent Events).** Agent responses stream token-by-token via `StreamingResponse` in FastAPI. Unidirectional (server → client). The user sends a question as a regular POST, then opens an SSE connection to receive the streamed response. Standard for LLM streaming (ChatGPT, Claude). No WebSocket infrastructure needed.

**Multi-tenancy: not applicable.** SkillNet is self-hosted — one instance per company, one database, one Docker Compose. The `organizations` table exists for data scoping but has a single row per deployment. If SaaS becomes a future need (post-beca), the schema already scopes by `org_id`, so row-level security can be added without restructuring.

### 6. Infrastructure

| Decision | Current direction |
|----------|------------------|
| **Deployment** | Docker, self-hostable |
| **Database** | PostgreSQL |
| **No vendor lock-in** | Core functionality must work without any specific cloud provider |

**LLM provider: user's choice.** SkillNet doesn't lock into any provider. The user configures their own API key and endpoint. Any OpenAI-compatible API works out of the box (OpenAI, DeepSeek, Groq, Together, local via Ollama/LM Studio, etc.). The backend talks to a single interface — base URL + API key + model name — set in environment variables. No provider-specific code in business logic.

**Background processing: hybrid.** LangGraph persistence for the generation pipeline (already a graph, built-in checkpointing, interrupt/resume) + PostgreSQL-backed job runner for everything else (zero new dependencies, `SELECT FOR UPDATE SKIP LOCKED`). No Redis needed for MVP. Full design in [background-processing.md](background-processing.md).

---

## Cross-cutting concerns

### Access control model

Based on [semantic boundaries](../research/semantic-boundaries/) and [multi-agent coordination](../research/multi-agent-coordination/) research:

```
Boot ──→ Agent (compartmented context) ──→ Boundary ──→ Output
  │                                           │
  │  "what it can see"                        │  "what it can emit"
  │  Deterministic filter by labels           │  Hard layer (scanner) + soft layer (customs agent)
```

Control is never inside the agent. The agent operates freely within its compartmented context. Enforcement is structural.

### Adaptation loop

The system adapts to each learner:

```
Learner completes exercise ──→ Progress recorded
                                     │
                        ┌────────────┴────────────┐
                        │                         │
              Content difficulty            Content format
              adjusts to level              adjusts to learner
```

**(deferred)** Adaptation signals. What data drives personalization (scores only, scores + time, full behavioral patterns). The data model already captures scores and timestamps in `exercise_attempts`, so any approach can be implemented later without schema changes. Will be decided when there is real user data to analyze.

---

## What's decided vs what's deferred

| Decided | Deferred |
|---------|----------|
| PostgreSQL + pgvector (single DB) | Knowledge graph structure |
| FastAPI, pragmatic REST | Adaptation signals |
| Session cookies + fastapi-users | |
| SSE for real-time streaming | |
| React SPA, React Router, fixed routes | |
| React Query for state management | |
| LangGraph for agent orchestration | |
| Compartment-based access control | |
| Mandate model for agent authority | |
| Self-hosted, one instance per company | |
| LLM provider agnostic (OpenAI-compatible API) | |
| Data model defined ([data-model.md](data-model.md)) | |
| Agent communication patterns (see [content-generation.md](content-generation.md), [chat-agents.md](chat-agents.md)) | |
| Background processing (see [background-processing.md](background-processing.md)) | |
| Mandate implementation (see [security.md](security.md)) | |
| Chunking strategy (see [rag-retrieval.md](rag-retrieval.md)) | |
| Level 3 latency (see [frontend-backend-integration.md](frontend-backend-integration.md)) | |
