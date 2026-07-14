<p align="center">
  <img src="assets/logo.png" alt="SkillNet" width="160">
  <h1 align="center">SkillNet</h1>
  <p align="center">
    <strong>Turn company knowledge into adaptive training — automatically.</strong>
  </p>
  <p align="center">
    <a href="https://anfaia.org"><img src="https://img.shields.io/badge/ANFAIA-Fellowship_2026-blue?style=flat-square" alt="ANFAIA 2026"></a>
    <a href="https://skillnet-docs.vercel.app/"><img src="https://img.shields.io/badge/docs-website-blue?style=flat-square" alt="Docs"></a>
    <img src="https://img.shields.io/badge/license-Apache_2.0-green?style=flat-square" alt="License">
    <img src="https://img.shields.io/badge/status-research_phase-orange?style=flat-square" alt="Status">
    <img src="https://img.shields.io/badge/open_source-brightgreen?style=flat-square" alt="Open Source">
  </p>
</p>

---

## What is SkillNet?

SkillNet takes a company's internal documentation (manuals, processes, wikis) and transforms it into a **living learning system**: auto-generated courses, AI tutoring agents, and adaptive progress tracking. Built for SMEs where critical knowledge lives in people's heads, not in systems.

Research project for the [ANFAIA 2026 Fellowship](https://anfaia.org). Early stage — architecture defined, implementation underway.

---

## How it works

```
                                  ┌─────────────────────────────────────┐
                                  │         KNOWLEDGE LAYER             │
                                  │   PostgreSQL + pgvector + RAG       │
                                  └──────┬──────────────┬───────────────┘
                                         │              │
                                    writes          reads from
                                         │              │
┌──────────────┐    ┌────────────────────┐│  ┌───────────┴───────────┐    ┌──────────────┐
│  Internal    │───▶│    Ingestion       │┘  │    Agent Teams        │───▶│   Learner    │
│  Documents   │    │  (chunk + embed)   │   │  Tutor · Content ·   │    │  Interface   │
└──────────────┘    └────────────────────┘   │  Admin assistant      │    └──────┬───────┘
                                             └───────────────────────┘           │
                                                                                 │
                                                    progress + feedback ─────────┘
```

Knowledge flows one direction: raw docs become structured knowledge, agents use it to generate courses and answer questions. Learner progress feeds back to drive adaptation.

---

## Content generation pipeline

A team of 7 specialized agents transforms documents into complete courses via a LangGraph state machine. Two mandatory human checkpoints keep admins in control.

```
  Document(s)
       │
       ▼
  ┌──────────────────┐
  │  prepare_context  │  Gather source material
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │  extract_themes   │  Identify key topics
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │ design_structure  │  Create course outline
  └────────┬─────────┘
           ▼
  ┌─────────────────────────────┐
  │  ADMIN CHECKPOINT 1         │  Review and edit structure
  │  (human-in-the-loop)        │  before content generation
  └────────┬────────────────────┘
           ▼
  ┌──────────────────┐
  │ generate_modules  │  Parallel content generation
  │ generate_manual   │  (lessons, exercises, manual)
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │  review_quality   │  Independent verification
  └────────┬─────────┘       (compartmented context)
      pass │    fail ──▶ refine_content (max 2 cycles)
           ▼
  ┌─────────────────────────────┐
  │  ADMIN CHECKPOINT 2         │  Final review before
  │  (human-in-the-loop)        │  anything reaches learners
  └────────┬────────────────────┘
           ▼
  ┌──────────────────┐
  │     publish       │  Course + Manual live
  └──────────────────┘
```

---

## Chat agents

```
  Employee ──▶ POST /api/v1/chat       ──▶ TutorAgent  ──▶ SSE stream
                                            (RAG-grounded answers,
                                             no tool calling)

  Admin    ──▶ POST /api/v1/chat/admin ──▶ AdminAgent  ──▶ SSE stream
                                            (13 tools,
                                             DB read + write)
```

Both are LangGraph state machines with shared infrastructure (LLMClient, chat persistence, SSE streaming).

---

## Tech stack

| Layer | Technology | Why |
|-------|------------|-----|
| **Frontend** | React + Vite + Tailwind | Responsive dashboard with brand identity, fast dev iteration |
| **Backend** | FastAPI (Python) | Async, simple, mature — 73 endpoints defined |
| **Database** | PostgreSQL + pgvector | Relational data + vector embeddings in one DB, no extra infra |
| **Orchestration** | LangGraph | Multi-agent state machines with checkpointing and human-in-the-loop |
| **Deployment** | Docker Compose | One command, everything runs. Dev and prod configs |
| **LLM** | Provider-agnostic | Abstraction layer with streaming, prompt management, cost tracking |

---

## Open questions

Things actively being evaluated — not decided yet:

| Question | Current thinking |
|----------|-----------------|
| **LLM provider** | DeepSeek API vs local models — both supported via abstraction layer |
| **Content format** | JSON vs YAML vs Markdown for generated course content |
| **Agent orchestration** | LangGraph chosen for v1, may evolve |
| **UIDL depth** | How much of the frontend should be generated (Level 2 built, Level 3 exploring) |
| **Chunking strategy** | Semantic by sections with fixed fallback — deferred until ingestion pipeline is built |

---

## Research areas

The project investigates four open problems in applied AI:

| Area | Why it matters | Status |
|------|----------------|--------|
| [Semantic Boundaries](docs/research/semantic-boundaries/) | Multi-tenant access control for knowledge | Exploring structural approaches |
| [Generative UI](docs/research/generative-ui/) | Interfaces generated per-learner on the fly | UIDL Level 2 built, Level 3 exploring |
| [Multi-Agent Coordination](docs/research/multi-agent-coordination/) | Governance for multi-agent multi-user systems | Mandate-based authority model discovered |
| [Post-Markdown](docs/research/post-markdown/) | Efficient doc consumption by agents | Built mcp-md-reader (90% token savings) |

See [`docs/research/`](docs/research/) for detailed write-ups.

---

## Repository structure

```
skillnet/
├── apps/
│   └── skillnet-web/              Frontend — React + Vite + Tailwind
├── packages/
│   ├── mcp-md-reader/             Markdown reading for LLM agents (90% token savings)
│   └── mcp-ui-renderer/           Compact DSL → standalone HTML pages
├── docs/
│   ├── design/                    Architecture specs (14 documents, v1 complete)
│   └── research/                  Open research by topic
└── assets/
    └── logo.png
```

---

## Quick start

```bash
# Frontend (React dashboard)
cd apps/skillnet-web
npm install
npm run dev
```

Backend and infrastructure setup via Docker Compose — see [`docs/design/docker-deployment.md`](docs/design/docker-deployment.md).

---

## Ethics

- **Data sovereignty** — User metrics are encrypted and belong to the employee and the organization, not an external SaaS
- **Equal access** — Democratizing knowledge within organizations, designed for any user profile including neurodiversity
- **Bias reduction** — Objective, data-driven assessment instead of perception-based evaluation
- **SDGs** — Aligned with SDG 4 (quality education) and SDG 8 (decent work)

---

## License

Distributed under the [Apache 2.0](LICENSE) license.

---

<p align="center">
  <em>Research project — architecture, stack and scope may evolve during development.</em>
  <br><br>
  Built as part of the <a href="https://anfaia.org">ANFAIA Fellowship 2026</a>
</p>
