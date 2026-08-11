# Vision

> **Status: Draft.** The philosophical foundation of SkillNet. This document explains why SkillNet is built the way it is — not what it does, but what it believes.

---

## The Problem with Current Training Software

Most training platforms are built the same way: an admin creates courses, employees take them, everyone sees the same thing. The platform doesn't change between the first employee and the hundredth. The content is static. The experience is fixed.

AI has been added to these platforms as a layer on top — a chatbot that answers questions, a generator that creates quizzes. But the underlying structure hasn't changed. The course is still the same for everyone. The dashboard looks identical. The path is predetermined.

**Adding AI to a static system doesn't make it intelligent. It makes it a static system with a chatbot.**

## What SkillNet Believes

### 1. The application should learn from the user, not the other way around

Current platforms require employees to adapt to the system: learn the interface, follow the path, complete the modules. SkillNet should adapt to the employee: their level, their pace, their gaps, their questions.

This is not about customization settings. It's about the system observing how each person works and adjusting accordingly — without being told to.

### 2. Intelligence lives in the architecture, not the model

A powerful LLM is one component. The real intelligence comes from how the system is structured:

- **Memory** — what the system remembers about each person and each company
- **Context** — what information is available at each moment
- **Tools** — what the system can do, not just say
- **Feedback loops** — how the system learns from its own mistakes

The model is replaceable. The architecture is the product.

### 3. Training should be built from living knowledge, not static courses

Company documentation changes. Policies are updated, procedures are revised, new regulations appear. Training that was correct last month may be wrong today.

SkillNet treats source documents as the single source of truth. Courses and manuals are derived from them, not independent artifacts. When the source changes, the training adapts.

### 4. The same knowledge should produce different experiences for different people

Two employees reading the same manual should not take the same course. One is new and needs foundations. The other has five years of experience and needs edge cases. The manual is the same — the training should not be.

This is not personalization as a feature. It's the default behavior of a system that understands who is learning.

## How This Shapes Technical Decisions

| Decision | Why |
|----------|-----|
| **LangGraph pipeline with human checkpoints** | Content generation is too important to fully automate. The admin is accountable for what employees learn. The system proposes, the human decides. |
| **Three UI levels (static, declarative, generative)** | Most of the app should be fast and predictable (Level 1). Where content varies by user, use specs (Level 2). Only generate full HTML when nothing pre-built fits (Level 3). |
| **Conditional RAG (small docs go whole, large docs get chunked)** | Don't over-engineer for problems that don't exist. A 3-page policy doesn't need a vector store. The system should be smart about when to be complex. |
| **PageIndex pattern for tutor retrieval** | Course content is already structured (modules > lessons). Use that structure instead of embedding everything. Two SQL queries + one short LLM call beats semantic search for in-course questions. |
| **Provider-agnostic LLM layer** | The model will change. The architecture shouldn't depend on any specific provider. Any OpenAI-compatible API works. |
| **Self-hosted, one instance per company** | Company training data is sensitive. Multi-tenancy adds complexity and risk. One instance per company is simpler and more trustworthy. |
| **Exercise attempts and learning events tracked** | Not for vanity analytics. They support the future learning loop: separate preference, engagement and effectiveness. Spaced repetition is not on the current roadmap; see [adaptive-learning.md](adaptive-learning.md). |

## What This Means for the Roadmap

**MVP (now):** Generate courses from documents. Employees take them. Admin sees progress. The system is static but well-architected for adaptation.

**Phase 2:** Tutor agent that adapts to each employee. Mixed learning strategies that respect explicit presentation preferences. Skill levels that reflect real ability, not just completion.

**Phase 3:** Adaptive regeneration — the system identifies weak modules from real data and regenerates them. Living content that stays in sync with company documentation.

**Phase 4:** Multi-agent coordination within a company. Different agents for different roles, sharing knowledge through structured compartments.

Each phase builds on the architecture decisions made in the previous one. Nothing is bolted on. Everything grows from the same foundation.

## The Thesis in One Sentence

> SkillNet is not a platform that delivers training. It's a system that builds the right training for each person, from the knowledge that already exists in their company.
