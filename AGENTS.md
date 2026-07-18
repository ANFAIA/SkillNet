# AGENTS.md

## Project

SkillNet — open-source training platform for SMEs. Turns company documents into courses, tracks employee skills. Self-hosted, one instance per company.

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19 + Vite + Tailwind v4 + React Router + TanStack Query |
| Backend | Python + FastAPI + fastapi-users |
| Database | PostgreSQL + pgvector |
| Auth | Session cookies (httpOnly, 7-day expiry) via fastapi-users CookieTransport |
| Real-time | SSE (Server-Sent Events) for streaming LLM responses |
| AI orchestration | LangGraph |
| LLM | Any OpenAI-compatible API (user configures endpoint + key + model) |
| Deployment | Docker Compose |

## Repo structure

```
skillnet/
├── AGENTS.md                         # This file (root instructions)
├── apps/
│   └── skillnet-web/                 # React SPA (frontend)
│       └── AGENTS.md                 # Frontend-specific instructions
├── packages/
│   ├── mcp-md-reader/                # Markdown reader MCP server (TypeScript)
│   └── mcp-ui-renderer/             # UI renderer for declarative specs (TypeScript)
├── docs/
│   ├── design/
│   │   ├── architecture.md           # Architecture decisions (decided + deferred)
│   │   ├── data-model.md             # PostgreSQL schema (15 tables)
│   │   ├── screens.md                # Screen specs for all 20 screens
│   │   └── design-system.md          # Visual design tokens and component patterns
│   └── research/                     # Investigation by topic
└── assets/
```

## Current phase: v1

**Read `docs/design/v1-scope.md` FIRST.** It defines what v1 is, what it isn't, and overrides other docs where they contradict. All other design docs cover the full product (v1 + v2 + future) — v1-scope.md has priority.

## Architecture (key decisions)

Full details in `docs/design/architecture.md`. Summary:

- **Database:** PostgreSQL + pgvector. Single DB for relational and vector data. Schema in `docs/design/data-model.md`
- **API:** Pragmatic REST. CRUD for resources + action endpoints for operations (`POST /courses/:id/generate`, `POST /courses/:id/publish`, `POST /exercises/:id/attempt`)
- **Auth:** Session cookies via fastapi-users. No JWT tokens in frontend. Browser sends cookie automatically
- **Frontend:** Single SPA with React Router. Fixed routes, dynamic content. TanStack Query for server state, `useState` for UI state
- **Real-time:** SSE for streaming agent responses. `StreamingResponse` in FastAPI
- **Self-hosted:** One instance per company. `organizations` table scopes data but has one row per deployment
- **LLM:** Provider-agnostic via litellm. User sets `LLM_MODEL` (e.g. `anthropic/claude-sonnet-4-20250514`, `deepseek/deepseek-chat`, `ollama/llama3`) in env vars. Any provider litellm supports works

## Commands

```bash
# Frontend (from apps/skillnet-web/)
pnpm install
pnpm dev              # dev server on localhost:5173
pnpm build            # production build
pnpm lint             # oxlint

# Backend (from apps/skillnet-api/ — not yet created)
# uv sync
# uv run uvicorn main:app --reload

# Full stack (from root)
# docker compose up
```

## Code conventions

- **Language:** TypeScript for frontend, Python for backend
- **Formatting:** Prettier for TS, Ruff for Python
- **Imports:** Absolute imports from `src/` in frontend
- **Components:** One component per file. File name matches component name. Functional components only
- **Naming:** PascalCase for components, camelCase for functions/variables, kebab-case for files in frontend. snake_case for Python
- **CSS:** Tailwind utility classes. Follow design system tokens in `docs/design/design-system.md`. No inline styles
- **State:** TanStack Query for server data. `useState` for local UI state. No global store unless explicitly needed
- **API calls:** All through TanStack Query hooks. No raw fetch in components

## Git workflow

- Branch from `main`
- Commit format: `type: description` (types: feat, fix, docs, refactor, test, chore)
- PR into `main`
- No force push to `main`

## Boundaries

- **DO NOT** modify `packages/mcp-md-reader/` or `packages/mcp-ui-renderer/` without explicit instruction
- **DO NOT** modify `docs/research/` — these are completed investigations
- **DO NOT** add dependencies without checking if the existing stack covers the need
- **DO NOT** use AI-slop patterns: gratuitous gradients, rounded-2xl on everything, pastel icon backgrounds on every card, decorative animations. Follow `docs/design/design-system.md`
- **DO NOT** hardcode LLM provider logic. All LLM calls go through litellm
- **DO NOT** add authentication logic in frontend. Session cookies are handled by the browser automatically

## Key references

- **v1 scope & decisions: `docs/design/v1-scope.md`** (READ FIRST — overrides other docs)
- Screen specs: `docs/design/screens.md`
- Data model: `docs/design/data-model.md`
- Architecture: `docs/design/architecture.md`
- Design system: `docs/design/design-system.md`
