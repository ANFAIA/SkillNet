# AGENTS.md

> **Asked to start the project? → [`RUNNING.md`](RUNNING.md).** Five steps, one decision
> (API key, local model, or neither), and it says what to verify afterwards. Do not
> reconstruct the commands from this file — the seed step is easy to miss and without it the
> dashboard is empty.

## Project

SkillNet — open-source adaptive learning system. It creates courses from an idea or source material
and can adapt their explanations, activities and interfaces to each person. Self-hosted, with
organization and individual workspace modes.

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
├── RUNNING.md                        # How to start the project — read this first
├── apps/
│   ├── skillnet-api/                 # FastAPI + LangGraph + pgvector (backend)
│   ├── skillnet-web/                 # React SPA (frontend)
│   │   └── AGENTS.md                 # Frontend-specific instructions
│   ├── skillnet-a2a/                 # A2A agent server (optional, `--profile a2a`)
│   └── skillnet-site/                # Public landing site
├── packages/
│   ├── a2tl-video/                   # A2TL-Video — compact spec for agent-generated video (TypeScript)
│   ├── a2tl-web/                     # A2TL-Web — compact spec for agent-generated web pages (TypeScript)
│   ├── mcp-md-reader/                # Markdown reader MCP server (TypeScript)
│   └── skillnet-mcp/                 # SkillNet MCP server — thin client of /ext/v1 (TypeScript)
├── docs/
│   ├── design/
│   │   ├── v1-scope.md               # What v1 is and isn't
│   │   ├── v2-dynamic-courses.md     # The v2 design (Spanish) — implemented, chosen per course
│   │   ├── ai-course-design.md       # Stateless AI endpoints and multi-model routing for course design (Spanish)
│   │   ├── openui-adoption.md        # Why OpenUI, and what its reactive layer would cost (Spanish)
│   │   ├── tuning.md                 # The dials for generation quality, and what each does
│   │   ├── architecture.md           # Architecture decisions (decided + deferred)
│   │   ├── data-model.md             # PostgreSQL schema (v1 body + v2 appendix)
│   │   ├── screens.md                # Screen specs
│   │   └── design-system.md          # Visual design tokens and component patterns
│   └── research/                     # Investigation by topic
└── assets/
```

## Current phase: v1 and v2 always available

Both v1 (static courses) and v2 (dynamic courses) are always available. The choice is
**per-course** via `delivery_mode`: a course is dynamic (v2) when it has
`delivery_mode='dynamic'` **and** `schema_status='validated'`. Every other course stays on v1.

Consequences for anything you change:

- `src/services/course_delivery.resolve_delivery` is the single decision point for v1 vs v2;
  do not add a second one.
- `tests/integration/test_v1_regression.py` exists to catch a break in v1 behaviour.
- `docs/design/v1-scope.md` still defines the v1 product and still wins on v1 questions. It no
  longer wins on "is v2 implemented" -- it is not a forward-looking document any more.
- `docs/design/v2-dynamic-courses.md` is the design of record for everything v2.
- Tuning generation quality: `docs/design/tuning.md` plus
  `apps/skillnet-api/scripts/quality_bench.py`.

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

# Backend (from apps/skillnet-api/)
uv sync
uv run uvicorn src.main:app --reload
uv run pytest -m "not integration"      # unit tests: no database, no API key
uv run pytest -m integration            # needs a live PostgreSQL. EMPTIES document_chunks
uv run ruff check src tests scripts
uv run python scripts/retrieval_bench.py   # RAG retrieval quality (needs a seeded database)
uv run python scripts/quality_bench.py --offline   # generation quality, no API key

# Full stack (from root)
docker compose up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build      # hot reload
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d --build   # local model
docker compose exec api uv run python -m src.seed_learning_demo               # public demo dataset
```

`uv run pytest -m integration` leaves `document_chunks` empty — the downgrade in
`test_migration_0005` passes through migration 0008, which changes the vector dimension, and
768-component vectors cannot survive a return to a 384 column. Re-run the seed afterwards.

There is also a `fixtures` profile (`docker compose --profile fixtures up -d db
api-fixtures`), but it is **not** the keyless path for the web app: `docker/nginx.conf`
proxies to `api` unconditionally, so the SPA never reaches it. To run the whole stack without
keys, set `LLM_MODEL=fixture/local` and `EMBEDDING_MODEL=fixture/local` in `.env` instead.

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

- **DO NOT** modify anything under `packages/` (`a2tl-video`, `a2tl-web`, `mcp-md-reader`) without explicit instruction
- **DO NOT** modify `docs/research/` — these are completed investigations
- **DO NOT** add dependencies without checking if the existing stack covers the need
- **DO NOT** use AI-slop patterns: gratuitous gradients, rounded-2xl on everything, pastel icon backgrounds on every card, decorative animations. Follow `docs/design/design-system.md`
- **DO NOT** hardcode LLM provider logic. All LLM calls go through litellm
- **DO NOT** add authentication logic in frontend. Session cookies are handled by the browser automatically

## Key references

- **v1 scope & decisions: `docs/design/v1-scope.md`** (defines the v1 product; wins on v1 questions)
- **v2 dynamic courses: `docs/design/v2-dynamic-courses.md`** (design of record for v2; chosen per course via `delivery_mode`, no global flag)
- AI-assisted course design: `docs/design/ai-course-design.md` (stateless AI endpoints, commit-on-create, multi-model routing for the design phase)
- Generation tuning: `docs/design/tuning.md` (the dials, with current values and what turning them does)
- OpenUI adoption: `docs/design/openui-adoption.md` (why the real packages, and the cost of the reactive layer)
- Screen specs: `docs/design/screens.md`
- Data model: `docs/design/data-model.md`
- Architecture: `docs/design/architecture.md`
- Design system: `docs/design/design-system.md`
- Motion system: `docs/design/motion-system.md` (animation spec, research findings, prioritized backlog)
