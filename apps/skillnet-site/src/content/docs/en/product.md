---
title: "Product"
order: 21
section: "start"
---

# Product

> **Status: Draft.** This document defines what SkillNet is, who it's for, and what it does.
>
> The current company-first product remains the implemented baseline. The future
> audience model for organization and individual deployments is defined in
> [audience-modes.md](/en/docs/audience-modes).

---

## What is SkillNet

SkillNet is a learning system that builds training for each person from knowledge that already exists in their company.

It is neither a course catalog nor a static LMS with an added AI layer. It reads company manuals, procedures, and protocols, then turns them into training adapted to the learner as well as the subject.

SkillNet is open source and self-hosted, with one instance per company. It is deliberately not multi-tenant.

SkillNet does not compete with enterprise offerings. It is intended for companies that those offerings do not serve.

The same company knowledge should produce different training experiences for different people. The system uses each person's role, level, and progress to build those differences instead of relying on an admin to configure them manually.

## Roles

| Role | What they do |
|------|-------------|
| **Admin** | Uploads documents, reviews generated content, assigns training, sees team progress |
| **Employee** | Learns, practices, asks questions. The experience adapts to their level and pace |

## Content types

| Type | Purpose |
|------|---------|
| **Course** | Modules + exercises + evaluation. Structured learning path, generated from company documents |
| **Manual** | Reference material. Employees consult when they need it. Organized for lookup, not learning |
| **Chatbot** | Per-content chatbot. Employees ask questions about the material and get answers grounded in it |

## Content generation

The primary way to create content:

- **From documents** — Upload a PDF, manual, or protocol. A team of AI agents extracts themes, designs a structure, generates modules and exercises, reviews quality, and produces a course + manual. The admin reviews at two checkpoints before anything reaches employees.

The generation pipeline is a LangGraph state machine with 10 nodes, 7 specialized agents, and 2 mandatory human checkpoints. See [content-generation.md](/en/docs/content-generation).

Future generation methods (not in MVP):

- From conversation — tell the AI what you know, it structures the course
- From scratch — give it a topic and level, it generates original content
- From living docs — when source documents change, affected courses are flagged for regeneration

## Exercises

Multiple types, defined by the content itself. Examples include tests, practical cases, real-world tasks ("do this and tell me if it worked"), and others to be determined as the product evolves.

Every exercise includes an explanation citing the source material. Answers are evaluated either deterministically (test, true/false, fill_blank) or by an LLM with a rubric (practical_case, dialogue).

## Tracking

Employees complete courses. The system records what they know how to do:

- Exercise attempts with scores and timestamps
- Skill levels that increase when exercises are passed
- Spaced repetition scheduling for review
- Deadlines and enrollment status

The admin sees team progress, skill gaps, and alerts. How exactly this is presented is open — the data model supports multiple views.

## Adaptation

SkillNet adapts at two levels:

**Level 1 — Content generation (offline, expensive):** The course is generated once from company documents. But the generation process already considers the target audience: the admin specifies who the course is for, and agents adjust Bloom levels, exercise difficulty, and examples accordingly.

**Level 2 — Experience adaptation (real-time, cheap):** Each employee sees the same course differently based on their profile:

- A beginner gets more theory lessons and guided examples
- An experienced employee skips to exercises and gets harder practical cases
- The tutor agent adjusts its explanations based on conversation history and past performance
- Spaced repetition schedules exercises for review at the optimal moment

**Level 3 — Adaptive regeneration (future, data-driven):** After a course has been taken by enough employees, the system identifies patterns: which modules have low pass rates, which exercises are too easy or too hard, which topics generate the most tutor questions. This data feeds back into the generation pipeline to regenerate weak modules automatically.

| Signal | What it tells us | Action |
|--------|-----------------|--------|
| Low pass rate on a module | Content is unclear or too difficult | Regenerate module with simpler explanations |
| High tutor questions on a topic | Employees don't understand from the course alone | Add examples or a dedicated lesson |
| Fast completion + high scores | Content is too easy | Increase exercise difficulty or add advanced module |
| Abandoned course at a specific point | Friction or disengagement | Investigate and adjust that section |
| Spaced repetition failures | Retention is poor | Adjust FSRS parameters or add reinforcement |

How adaptation works in practice is open. The data model already captures all the signals needed (exercise_attempts with scores, timestamps, tutor chat logs, spaced_repetition table). No schema changes required — just the logic to act on the data.

## Learning Loop

The system learns from every interaction:

```
Employee takes course
    |
    v
Exercise attempts recorded (score, time, answer)
    |
    v
Skill levels updated
    |
    v
Spaced repetition schedules next review
    |
    v
Tutor chat logs questions and confusions
    |
    v
Admin sees patterns: skill gaps, struggling employees, weak modules
    |
    v
(Future) System flags content for regeneration based on real data
```

The learning loop is not part of the MVP, but it guides the product direction. Every table in the data model already supports it, and the loop remains a design constraint rather than an afterthought.

## Living Content

Company documentation changes. Policies are updated, procedures are revised, new regulations appear. SkillNet treats source documents as living, not static:

- When a document is re-uploaded, the system detects what changed
- Affected courses and manuals are flagged for review
- The admin decides whether to regenerate or keep the current version
- Employees see a version indicator so they know if their training is current

This lets SkillNet stay in sync with the company's knowledge instead of generating content only once.
