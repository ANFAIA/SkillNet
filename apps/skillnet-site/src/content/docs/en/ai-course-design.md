---
title: "AI course design"
order: 17
section: "extensibility"
---

# AI-assisted course schema design

> **Status: closed architectural decisions.** This document covers the AI-assisted course
> creation flow: how the admin builds a schema before anything exists in the database, and
> why each piece is where it is.
>
> It complements `v2-dynamic-courses.md` (which covers the full design-time/runtime cycle)
> and `content-generation.md` (v1 pipeline). Where this document contradicts the other, the
> most recent one wins for the design phase; runtime is not touched here.

Depends on: [v2-dynamic-courses.md](v2-dynamic-courses.md),
[architecture.md](architecture.md), [llm-integration.md](llm-integration.md).

---

## 1. Stateless AI endpoints for design

The design phase uses **stateless** AI endpoints. The frontend is the workspace: all state
lives in React (`useState`) until the admin confirms. The backend endpoints receive the full
context and return results without persisting anything.

### 1.1 Current surface

| Endpoint | Input | Output |
|----------|---------|--------|
| `POST /ai/schema-propose` | `{ title, description, intent_density }` | `{ nodes }` |

### 1.2 Planned surface (backlog)

| Endpoint | Purpose |
|----------|-----------|
| `POST /ai/schema-refine` | Refine an existing schema from admin feedback |
| `POST /ai/node-suggest` | Suggest a new node given the current schema |
| `POST /ai/autocomplete` | Complete node fields (summary, outcome) |

### 1.3 Pattern

Each endpoint is independent and testable in isolation. There are no shared sessions or
server-side state between calls. Context is sent on every request: a schema is 5-15 nodes, a
few KB, a trivial payload.

### 1.4 Why stateless

| Discarded alternative | Problem |
|------------------------|----------|
| Server-side workspace session | Orphaned courses from abandoned sessions; needs cleanup |
| Redis for intermediate state | New infrastructure for data that fits in the body |
| "Draft" entity in the DB | Unfinished draft clutter; the course list gets contaminated |

Advantages of the chosen approach:

- **No orphaned data.** An abandoned design session leaves no trace on the server.
- **Resilient.** A browser refresh only loses the local draft, not a server session. The
  admin can copy their draft before closing if they want (it's plain JSON in React state).
- **Extensible.** Every new AI feature is a new endpoint, with no coupling to a "workspace"
  entity. Adding `POST /ai/schema-refine` doesn't touch any existing endpoint.
- **No extra infrastructure.** Needs no Redis, no session tables, no cleanup cron.

---

## 2. The course is created only on confirmation

The course is **not** created in the database when the admin starts designing. It's created
only when the admin accepts the schema and clicks "Create". At that point:

```
POST /courses                        → creates the course (title, description, delivery_mode)
PUT  /courses/{id}/schema            → writes the schema's nodes
POST /courses/{id}/schema/validate   → blocking gate (if the admin validates on the spot)
```

### 2.1 Consequences

- The `courses` table only contains real courses, never drafts.
- No cleanup jobs are needed for abandoned drafts.
- The admin panel's "Content" list reflects exactly what exists.
- The SPA's flow is a clean transition: React state → POST → the entity exists.

### 2.2 Contrast with v1

In v1, the course is created first and content is generated afterward
(`POST /courses/{id}/generate`). The difference is that in v1 the admin cannot design anything
before creating: the course is an empty container until the pipeline finishes. In the new
flow, the entire creative phase happens **before** the course exists.

---

## 3. Multi-model routing for design tasks

Different AI tasks in the design phase can use different models. The
`resolve_llm_config(org_settings, purpose=...)` infrastructure already supports selection by
purpose.

### 3.1 Current assignment

| Task | Model type | Typical latency | Purpose |
|-------|---------------|-----------------|---------|
| Schema proposal | Fast (8B, GPT-4o-mini) | 2-5 s | `"schema_design"` |
| Per-node content generation (runtime) | Heavy | 1-3 s | `"runtime_heavy"` |

The schema proposal only generates structure: titles, summaries, prerequisites. It doesn't
generate learning content. That makes it viable for fast, cheap models.

### 3.2 Planned assignment (backlog)

| Task | Model type | Purpose |
|-------|---------------|---------|
| Suggestions/autocomplete | Fast | `"schema_assist"` |
| Domain fine-tuned models | Specialized | `"schema_design_ft"` |

The router needs no changes: adding a new purpose is just declaring it in the organization's
configuration and passing it to `resolve_llm_config`.

---

## 4. Real-time interactive editor

The schema editor separates two kinds of operations by their latency:

### 4.1 Local operations (instant, no AI)

- Edit a node's title or summary.
- Delete a node.
- Reorder nodes (drag & drop).
- Add a node manually.
- Change prerequisites.

These operations mutate React state directly. They generate no server calls.

### 4.2 AI operations (fast, 2-5 s)

- Initial proposal from a topic.
- Re-proposal when density changes (`intent_density`).
- New node suggestion (backlog).
- Field autocompletion (backlog).

UI pattern:

1. The admin triggers an action (click, slider).
2. A subtle loading indicator (never a blocking modal, never a full-page spinner).
3. The UI stays interactive — the admin can edit other nodes while the AI works.
4. The result appears inline, like the runtime's click-to-explain (Curio): click → fast call
   → the result appears in place.

---

## 5. Unified flow for courses from a document and from a topic

Both paths converge on the same schema proposal:

```
From a document:                        From a topic:
  upload PDF                              title + description
    → parse to Markdown                       |
    → extract themes                          → extract themes
        |                                        |
        └──────────────┬─────────────────────────┘
                       ▼
              propose schema (same call)
                       ▼
              schema editor (same UI)
```

### 5.1 Differences

| Aspect | From a document | From a topic |
|---------|----------------|------------|
| Input to the proposal | Themes extracted from the Markdown | Themes extracted from the title/description |
| Source document | Attached to the course for runtime RAG | No document; content is generated without RAG |
| Proposal quality | More precise (concrete themes from the material) | More generic (depends on description quality) |

### 5.2 Invariant

The schema proposal endpoint works from extracted themes, **not** from raw documents. Theme
extraction is a prior step (already implemented in `build_schema_graph()` as the
`extract_themes_schema` node). The original document, if it exists, is used later for RAG
when generating node content at runtime.

---

## 6. Backlog: fine-tuning for large courses

For organizations with large document bases or specific domain needs. None of this is
implemented or planned in the short term.

| Line | Description |
|-------|-------------|
| Embedding fine-tuning | Improve RAG in specific domains (medical, legal, engineering) |
| Design model fine-tuning | Learn from schemas admins accept vs. reject |
| Generation model fine-tuning | Learn from validated renders (OpenUI Lang) |
| Adaptive chunking | For very large documents (>100 pages), structure-based chunking strategy |
| Parallel node generation | For courses with 20+ nodes, generate content in parallel instead of sequentially |

Common prerequisite: sufficient data volume. An organization with 5 courses doesn't have
enough data for fine-tuning. This becomes relevant once there are dozens of organizations
with hundreds of validated courses.
