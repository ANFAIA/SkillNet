# Architecture

> **Status: Draft.** This document captures what is known so far. Sections marked with **(open)** have no decision yet.

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

**(open)** Chunking strategy. How documents get split into retrievable units — by section, by semantic boundary, by fixed size, or something adaptive.

**(open)** Update flow. When source documents change, how does the knowledge layer stay current? Full re-ingestion vs incremental updates.

### 2. Knowledge layer

The system's memory. Stores structured knowledge and makes it available to agents through retrieval.

| Component | Role |
|-----------|------|
| **PostgreSQL** | Persistent storage for structured data: users, courses, progress, organization config |
| **Vector store** | Embeddings of knowledge units for semantic retrieval (RAG) |
| **Access control** | Determines what knowledge is visible to whom |

**What we know from research:**

- Content-based classification of access levels caps at 78% accuracy ([semantic boundaries research](../research/semantic-boundaries/)). Privacy is a human decision, not a content property. The system must enforce organizational access decisions, not guess them.
- Compartment-based access (need-to-know) is the most promising model. An agent is booted with only the compartments its task requires. Control happens at boot (what it can see) and at the boundary (what it can emit), not inside the agent.

**(open)** Vector store choice. pgvector inside PostgreSQL vs a dedicated store (Qdrant, Weaviate, etc.).

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

**(open)** Level 3 latency. Generation takes 20-30s per page. Two approaches being explored: two-agent generation (fast skeleton + background content) and pre-built waiting experiences. Neither is implemented.

**(open)** Frontend architecture. React is in the stack, but the component structure, routing, and state management are not defined. How do Levels 1, 2, and 3 coexist in the same application?

### 5. API

FastAPI serves as the interface between frontend and backend.

**(open)** API design. Endpoints, authentication scheme, real-time communication (WebSockets for streaming agent responses vs SSE vs polling).

**(open)** Multi-tenancy. How organizations are isolated at the API level — separate databases, shared database with row-level security, or schema-per-tenant.

### 6. Infrastructure

| Decision | Current direction |
|----------|------------------|
| **Deployment** | Docker, self-hostable |
| **Database** | PostgreSQL |
| **No vendor lock-in** | Core functionality must work without any specific cloud provider |

**(open)** LLM provider strategy. Which models, how to abstract provider switching, cost management at scale.

**(open)** Background processing. Ingestion and content generation are long-running tasks. Queue system (Celery, Dramatiq, etc.) vs LangGraph's built-in persistence.

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

**(open)** What signals drive adaptation. Completion rate, scores, time spent, interaction patterns, or a combination. How quickly the system should react to new signals.

---

## What's decided vs what's open

| Decided | Open |
|---------|------|
| LangGraph for agent orchestration | Agent communication patterns |
| PostgreSQL for persistence | Vector store choice |
| FastAPI for the API | API contract and auth |
| React for frontend | Frontend architecture |
| Docker for deployment | LLM provider strategy |
| Compartment-based access control | Runtime mandate implementation |
| UIDL for Level 2 UI generation | Level 3 latency solutions |
| Mandate model for agent authority | Formal mandate representation |
| Self-hostable, no vendor lock-in | Multi-tenancy approach |
