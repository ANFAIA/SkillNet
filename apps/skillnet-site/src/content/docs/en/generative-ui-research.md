---
title: "Generative UI (research)"
order: 55
section: "research"
group: "generative-ui"
---

# Generative UI

How AI agents produce user interfaces, and why it changes everything for platforms like SkillNet.

## Three levels

| Level | Name | How it works | Tokens | Latency |
|-------|------|-------------|--------|---------|
| **1** | Static | Agent sends data to pre-built components | ~300 | <2s |
| **2** | Declarative | Agent emits a compact spec; a renderer expands it to HTML | ~458 | <0.1s |
| **3** | Generative | Agent writes raw HTML/CSS/JS from scratch | ~3,343 | 23s |

Level 2 is **7.3x more token-efficient** than Level 3 for the same information. Level 3 produces near-human quality (ELO 1736 vs expert 1800 in [Google's evaluation](https://arxiv.org/abs/2604.09577)) but is too slow and expensive for interactive use.

## The real problem

Generating a full HTML page costs 2,000–8,000 output tokens. At scale, that's $30–$120/day for UI alone. Generation latency is 20–30 seconds per page. And 12–65% of generated code contains security vulnerabilities.

The question isn't whether agents *can* generate UI. They can. The question is whether it's practical, and the answer is: **not at Level 3, not for everything.**

## When does generative UI make sense?

Three variables determine which level you need. When all three are high, Level 3 is the only option. When any is low, Level 2 suffices.

| Variable | Low | High |
|----------|-----|------|
| **Content variability** | A landing page, a blog, a shop with 20 products. Everyone sees the same thing. | Personalized training, medical records, tech support. Each person sees something different. |
| **Context variability** | An analytics dashboard updated daily. The format is predictable. | Emergencies, logistics, live events. What you need changes every minute. |
| **User variability** | All admins do the same tasks. One screen fits all. | A new waiter vs a veteran vs a manager vs a cook. Each role needs completely different views. |

The matrix:

```
Content   Context   User   → Level
───────   ───────   ────   ──────────────────
LOW       LOW       LOW    → Level 1 (static). Fixed screens. No AI needed.
HIGH      LOW       LOW    → Level 2 (declarative). Fixed components, variable data.
HIGH      HIGH      LOW    → Level 2–3. Fixed components, generated content.
HIGH      HIGH      HIGH   → Level 3 (generative). You cannot pre-design screens.
```

### Where Level 3 fits in SkillNet

SkillNet is not a Level 3 platform. It's a platform where Level 3 **can be integrated** in the scenarios where all three variables are high:

- **Content:** each company has its own courses, each course is unique, each lesson adapts to the learner
- **Context:** a new hire needs one thing, someone with an exam tomorrow needs another, someone standing in front of a fryer needs something else entirely
- **User:** new staff, veterans, managers, cooks, security. Each role needs completely different views

When the combination of variables produces millions of possible screens (50 companies × 200 courses × 1,000 employees × skill level × time of day), pre-designed screens are not feasible. That's where generative UI becomes the only practical approach.

But most of the platform doesn't need it. Login, settings, and profile screens are Level 1. Dashboards and course listings are Level 2. Level 3 applies specifically to personalized lessons, adaptive tutoring, and agent responses: the moments where the content truly must be generated for that person in that context.

## What we built: A2TL-Web

The core discovery: you can get **76% of the token savings** by having the agent describe *what* to show instead of *how* to render it. We built **A2TL-Web (Agent to Transformation Language — Web)**, a compact format where the agent writes a spec and a deterministic renderer expands it to full HTML.

```
UIDL/1
theme dark
layout stack

h1 "Training Dashboard"
text "Week 2 progress for the kitchen team" dim

metrics 3
  "Completed" "12/20" green "On track"
  "Avg Score" "87%" blue "+5% vs last week"
  "Time Spent" "4.2h" orange "Below target"

chart bar "Scores by Module"
  x "Safety" "Prep" "Service" "Cleanup"
  y 92 85 78 91

table "Pending Exercises"
  cols Module Exercise Due
  row "Safety" "Fire extinguisher drill" "Tomorrow"
  row "Service" "Customer complaint handling" "Friday"
```

This spec is ~360 tokens. The renderer expands it to a complete standalone HTML page with Chart.js charts, styled tables, metric cards, and responsive layout (~2,400 tokens of HTML). The agent never generates HTML; it never deals with CSS or JavaScript.

**Implementation:** [github.com/JoseEstevez520/a2tl-web](https://github.com/JoseEstevez520/a2tl-web), an MCP server and CLI tool. Available as a tool for any MCP-compatible agent. v1.2.0 adds a brand/theme system: a JSON preset (~8 properties: colors, font, logo, radius, footer) that the renderer applies without changing the spec. The LLM writes the same compact format; the organization's brand is applied at render time.

| Metric | A2TL-Web | Equivalent raw HTML |
|--------|----------|---------------------|
| Tokens | ~360 | ~1,471 |
| Bytes | 1,327 | 9,992 |
| Lines | 40 | 180+ |
| **Savings** | **76%** fewer tokens | |

A2TL-Web operates at Level 2: the agent writes a compact spec, and a local renderer expands it deterministically. This means no LLM is involved in the rendering step. Level 3 (where the agent generates the full HTML) is a different approach with different trade-offs that we still want to explore.

### What A2TL-Web does not solve

No complex interactivity (filters, forms, state management). No nested layouts. Limited to Chart.js chart types. Static HTML output, no real-time updates. For those, you need a component registry (Level 1) or full generation (Level 3).

However, the renderer is extensible. Organizations can register custom components in their renderer without changing the spec format. This means the spec stays compact and stable while each deployment can support domain-specific elements. See [extending the renderer](https://github.com/JoseEstevez520/a2tl-web/blob/main/docs/extending.md) for details.

### Experimental: applying the same idea to video (A2TL-Video)

The same principle — agent describes *what*, renderer decides *how* — was applied experimentally to explainer videos. [A2TL-Video (Agent to Transformation Language — Video)](https://github.com/JoseEstevez520/a2tl-video) is a compact format inspired by Remotion where 98 lines / 1,173 tokens produce a 74-second video — 48% fewer tokens than equivalent Remotion JSX (2,257 tokens) and 94% fewer than the HTML player output (21,305 tokens). Measured with tiktoken.

```
VDSL/1
theme dark-tech
canvas 1920x1080

scene "The Problem" 6s crossfade
  text "Your data has no walls." hero center word-stagger 0-4s

scene "The Solution" 8s blur-crossfade
  viz 0.5-8s build-up
    type: flow-diagram
    steps:
      - label: "Label" desc: "tag your data" icon: tag color: blue
      - label: "Check" desc: "verify at the gate" icon: shield color: green
```

The pipeline compiles `.vdsl` to either a self-contained HTML player (instant playback, no dependencies) or MP4 via Remotion. It includes 17 built-in components, 4 themes, a `<vdsl-player>` web component for embedding, and inline palette/font overrides. The idea is simple: agents shouldn't need to know HTML, CSS, animation libraries, or video frameworks. They describe *what* to show, and the renderer takes care of everything else.

## Five prototypes compared

We built five prototypes at different levels and measured them head-to-head on the same dataset. The key findings:

1. **Level 2 (A2TL-Web) is 7.3x more token-efficient than Level 3** for the same content
2. **Level 3 latency (23s) is prohibitive** for interactive use
3. **A vault-to-page pipeline (no LLM) is the most efficient**: 0 tokens, 310ms, functional HTML
4. **A bidirectional loop works** (agent generates → user interacts → agent regenerates) but costs ~3,500 tokens per cycle
5. **Level 3 visual quality is inconsistent.** Each page looks different. Level 2 uses a design system, so output is always consistent.

Full data: [experiments/prototype-benchmarks.md](/en/docs/generative-ui-benchmarks)

## Who is working on this

Generative UI is still early. The main players shipping it in production (July 2026):

- **Google.** Full generative UI in [Gemini](https://gemini.google.com) and Search AI Mode. Also created [A2UI](https://github.com/google/a2ui), an open-source protocol where agents emit JSON describing UI intent and the client renders native components.
- **Anthropic.** [Claude Artifacts](https://support.anthropic.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them) and [MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) render interactive UI in sandboxed iframes.
- **Vercel.** [v0](https://v0.dev) generates React + Tailwind from prompts. The [AI SDK](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces) streams React Server Components.
- **CopilotKit.** [AG-UI](https://docs.ag-ui.com/) is an event-based protocol for bidirectional agent-to-frontend communication. Complements A2UI (AG-UI transports A2UI payloads).

All of these work at Level 3 (full HTML/CSS/JS generation) or Level 1 (component registries). A2TL-Web is a Level 2 tool we built to solve a specific problem: generating structured content (dashboards, reports, summaries) without the cost and latency of full generation. It is not an alternative to Level 3. We still want to explore Level 3 for the scenarios where free-form generation is needed.

## A key insight

Our own development process is already generative UI. In every working session, the AI reads data from the knowledge base, decides what to investigate or build, and generates documents, web pages, dashboards, and specs adapted to the current context. The pattern is the same: a system that generates personalized content in the moment based on who's asking and what they need.

That hands-on experience (knowing what works, what fails, what frustrates, what saves time) is the foundation for designing SkillNet's generative UI.

## Where the research is now

The main open problem is **generation latency**. Level 3 takes 20-30 seconds per page. That's fine for a report you generate once, but unacceptable for interactive use. The question we're investigating: how do you make the wait not feel like a wait?

The web already deals with this. Skeleton screens, loaders, progressive rendering. These patterns reduce perceived latency, and research shows that skeletons in particular make users perceive load times as shorter. The question is how to adapt these patterns to generative UI, where the content doesn't exist yet.

Two approaches we're exploring:

**1. Two-agent generation.** One fast agent generates the skeleton (layout, placeholders, structure) while a second agent generates the actual content in the background. The user sees something immediately, and the real content fills in as it's ready. This optimizes perceived time because the user is never staring at a blank screen.

**2. Pre-built waiting experiences.** Instead of a generic spinner, use pre-designed interactive screens for the wait. For example, a character animation or a visual element that's always ready, combined with a short text generated by a fast, lightweight agent. The user gets something engaging and contextual (not just "loading...") while the full generation happens in the background. By the time the real content is ready, the user has already had a few seconds of interaction, and the generation has had time to complete.

Both approaches share the same idea: use the waiting time productively instead of trying to eliminate it. Give the user something meaningful while the heavy generation runs behind the scenes.

A separate direction is emerging for A2TL-Web itself: positioning it as a consumption standard rather than a growing DSL. The idea follows the post-Markdown thesis -- don't change the format, make the reader smarter. The spec stays minimal and stable; the renderer is the extension point, not the spec. Each organization extends their own renderer to support whatever components they need (domain-specific charts, interactive widgets, custom cards) while the agent keeps writing the same compact format. This keeps the LLM-facing surface small and predictable, and pushes complexity to the deterministic side of the system where it's easier to control.

## Open questions

- If there are no pre-designed screens, what is there? A continuous flow?
- If every user sees something different, how do you maintain brand identity?
- If the LLM generates everything, what does the developer do? Design rules? Train models? Define limits?
- What is SkillNet if it's born with native generative UI? It's not an LMS with a chatbot. It's... what?

## Update — July 24, 2026: Landscape scan, decisions, and new architecture

A deep investigation session produced a comprehensive scan of the generative UI landscape: 21 academic papers, 3 frameworks, 2 protocols, and 1 production-ready standard. The key findings and decisions are documented in the vault; this section summarizes what changed.

### Papers that validated our direction

| Paper | Why it matters |
|-------|----------------|
| **[MAIC-UI](https://arxiv.org/abs/2604.25806)** (Tsinghua) | Academic twin of SkillNet. Same source (PDFs → interactive courseware), similar pipeline. +9.21 STEM points in 53 students over 3 months. **Validates our entire approach.** |
| **[The Keyhole Effect](https://arxiv.org/abs/2602.00947)** (Reddy) | Neuroscience basis for why chat-only interfaces fail at learning/analysis. The chat destroys spatial memory, forces verbalization (which degrades visual memory), blocks cognitive offloading. **SkillNet's tutor cannot be chat-only.** |
| **[Stanford SALT GenUI](https://arxiv.org/abs/2508.19227)** | Pipeline: requirement → DSL → generate → refine. 72% human preference over chat. Adaptive reward function. **Validates our 7-stage pipeline.** |
| **[Software as Content](https://arxiv.org/abs/2603.21334)** (Xie & Xie) | Generated apps as persistent interaction layer, not disposable chat. **Exactly where SkillNet needs to go.** |
| **[The Missing Layer](https://arxiv.org/abs/2606.15902)** | GenUI in education should be design-time (authoring), not just runtime. **Validates our schema/content separation.** |
| **[Macaron-A2UI](https://arxiv.org/abs/2605.24830)** | LoRA + GRPO on declarative DSL surpasses GPT-5.4 with prompting. **Direct inspiration for fine-tuning a small model to generate UI DSL natively.** |
| **[Google GenUI](https://arxiv.org/abs/2604.09577)** — Leviathan et al. | Foundational paper. LLMs generate UI comparable to human experts (ELO 1736 vs 1800). |

Full list of 21 papers: `docs/research/generative-ui/papers/awesome_generative_ui.md` (or vault reference).

### Frameworks and protocols evaluated

| Resource | Type | What it offers |
|----------|------|----------------|
| **[A2UI](https://a2ui.org/)** (Google) | Open protocol | Agent-driven UI standard. Declarative JSON, framework-agnostic, safe by design (pre-approved component catalog). v0.9.1 in production, v1.0 candidate. Multi-client (React, Angular, Flutter, Lit). |
| **[OpenUI Lang](https://www.openui.com/)** (Thesys) | DSL + Runtime | Line-oriented DSL, 52-67% fewer tokens than JSON, streaming parser with validation, React `<Renderer />`, system prompt generator (`library.prompt()`). 7K ⭐, production use. |
| **[OpenGenerativeUI](https://github.com/CopilotKit/OpenGenerativeUI)** (CopilotKit) | Framework | Sandboxed HTML/SVG in iframes, progressive skills, visual decision matrix. Most complete framework. |
| **A2TL-Web** (ours) | DSL | 76% token savings vs HTML, brand system, video coverage. No runtime, parser, or validation. |

### Decisions taken

#### 1. Adopt OpenUI Lang as runtime (replace A2TL-Web for production)

A2TL-Web achieves higher compression (76% vs 52-67%), but OpenUI Lang has:
- Parser with AST + JSON Schema validation
- Production-proven React renderer
- Automatic system prompt generation from component schemas
- Ecosystem (7K ⭐, benchmarks, OpenUI Cloud)
- Multi-framework support

A2TL remains as an experiment and design reference. OpenUI Lang is the production runtime.

#### 2. New architecture: design-time schema → runtime generation

**Before (v1):** Admin uploads docs → pipeline generates entire course as Markdown → all employees see the same content.

**After (v2):**
```
Admin defines schema (nodes, prerequisites, criticality)
    ↓
Employee opens course → pre-assessment per node
    ↓
For each node NOT mastered:
    ├── decide_formato (8B LLM) → optimal UI type
    ├── genera_ui (8B or 120B) → OpenUI Lang
    └── render (OpenUI <Renderer />)
    ↓
Feedback → next node
```

This enables real personalization without regenerating the entire course.

#### 3. Parallel LLM routing (8B / 120B)

~90% of SkillNet UIs are Level 2 (standard components). A small model suffices.

| Model | Speed | Cost input/1M | Use case |
|-------|-------|---------------|----------|
| Llama 3.1 8B (Groq) | 560 t/s | $0.05 | Skeleton + standard components (~90% of UIs) |
| GPT-OSS 120B (Groq) | 500 t/s | $0.15 | SandboxHTML, simulations, diagrams (~10%) |

Router: if the UI needs SandboxHTML → 120B, else 8B.

#### 4. Stack (current)

```
Frontend:     React + OpenUI <Renderer /> + SkillNet UI Kit
Backend:      FastAPI + LangGraph (per-node pipeline)
Fast LLM:     Llama 3.1 8B (Groq) — 90% of UIs
Heavy LLM:    GPT-OSS 120B (Groq) — simulations/diagrams
Format:       OpenUI Lang
Protocol ref: A2UI (for future multi-client)
```

#### 5. QLoRA fine-tuning (backlog)

Inspired by Macaron-A2UI (LoRA + GRPO on A2UI surpasses GPT-5.4). Fine-tune Qwen3-30B or Llama-3.1-8B with QLoRA to generate OpenUI Lang natively. Cheaper inference, fewer format errors, no heavy prompting.

### What this means for the existing pipeline

| Today (v1) | Tomorrow (v2) |
|------------|---------------|
| Admin uploads docs → full course generated | Admin defines schema → no content until runtime |
| All employees see same content | Each employee gets UI generated from their profile + pre-assessment |
| Single LLM for everything | Router: 8B for 90%, 120B for 10% |
| Content in fixed Markdown + JSON | UI in OpenUI Lang, rendered via `<Renderer />` |
| No effectiveness metrics | Feedback loop → system adapts per node |

### Immediate roadmap

1. Define SkillNet UI Kit — Zod schemas for educational components (TextContent, Card, Simulation, Quiz, StepSequence, Chart, Table, CodeBlock)
2. Integrate OpenUI in skillnet-web — `npm install openui`, mount `<Renderer />` with the UI Kit
3. New pipeline nodes: `decide_formato → genera_ui` in LangGraph with LLM routing
4. Connect with existing admin schema
5. Pre-assessment per node (2-3 questions before generation)
6. Feedback loop — user interaction → system adapts next node

### Full documentation

Each finding has its detailed document in the vault (`07_ANFAIA/investigacion/ui_innovadora/`). The synthesis and decision document is at `_sintesis_para_repo.md`.

## References

- Leviathan et al., "Generative UI: LLMs are Effective UI Generators" ([arXiv 2604.09577](https://arxiv.org/abs/2604.09577), Google Research, 2025)
- [A2UI Protocol](https://github.com/google/a2ui) (Google, Apache 2.0)
- [AG-UI Protocol](https://docs.ag-ui.com/) (CopilotKit)
- [Vercel AI SDK: Generative UI](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces)
- [PAGEN benchmark](https://generativeui.github.io/)
- [TOON format](https://github.com/toon-format/toon), JSON alternative for LLMs (30-60% savings, but fragile in multi-turn)
- [TypeFox: Semiformal DSL for web apps](https://www.typefox.io/blog/turn-ai-prompts-into-web-apps-using-a-semiformal-dsl/) (70-85% savings)
