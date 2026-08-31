---
title: "Product"
order: 21
section: "start"
---

# Product

> **Status: current product baseline and direction.** This document separates implemented behavior
> from later work.
>
> Setup supports organization and individual workspaces. Their product boundaries and future
> evolution are defined in [audience-modes.md](/en/docs/audience-modes).

---

## What is SkillNet

SkillNet turns an idea or existing knowledge into grounded, traceable training that can take a
different form for different learner profiles and states.

It is not only a course catalog or a static LMS with a chatbot attached. It reads manuals,
procedures, protocols or a generated source, builds a course and keeps the learner experience
separate from the knowledge and objective that must remain stable.

SkillNet is open source and self-hosted. A deployment can begin as an organization workspace or an
individual workspace.

The same source and objective can produce different explanations, activities, media and interfaces.
The system uses current context and revisable learner evidence; it does not claim to know a person's
fixed learning style.

## Roles

| Role | What they do |
|------|-------------|
| **Admin** | Uploads documents, reviews generated content, assigns training, sees team progress |
| **Employee** | Learns, practices and asks questions. The experience can respond to their profile, current state and support needs |

## Current learning surfaces

| Surface | Purpose |
|------|---------|
| **Course** | Modules + exercises + evaluation. Structured learning path, generated from company documents |
| **Course tutor** | Tutor attached to a course or enrollment. It retrieves course material for source-specific questions and can answer general questions without course citations |
| **Generated media** | Podcasts, infographics, slide decks and narrated slide videos when the required providers are configured |

## Content generation

Current creation paths:

- **From documents** — upload PDF, DOCX, Markdown or TXT material and generate a grounded course.
- **From an idea** — SkillNet creates a clearly marked model-generated source with provenance and
  builds from it. This is not equivalent to grounding in uploaded company material.
- **From external clients** — the web UI and `/ext/v1` use the same authoring services. Optional A2A
  and MCP adapters call `/ext/v1` when their Compose profiles are enabled.

The static v1 pipeline and dynamic v2 schema path coexist. The delivery decision is made per course.
Dynamic schemas pass through proposal, node review and validation before learner delivery. See
[v1 scope](/en/docs/course-scope), [dynamic courses](/en/docs/dynamic-courses) and [AI course
design](/en/docs/ai-course-design).

## Exercises

Multiple types are defined by the content itself. Examples include tests, practical cases and
real-world tasks ("do this and tell me if it worked").

Closed generated exercises are prompted to include an explanation. Dynamic Didact activities
preserve server-owned source references. Citation coverage is not yet universal across v1
exercises. Answers are evaluated either deterministically (test, true/false, fill_blank) or by an
LLM with a rubric (practical_case, dialogue).

## Tracking

Learners complete courses. The system records the evidence it can observe:

- Enrollments and course progress
- Node completion and mastery
- Exercise and activity attempts
- Learning events and the rendered experience seen by the learner
- Skill levels recorded from course mastery or explicit verification

The admin talent surfaces expose people, assigned courses, progress and recorded skills with their
source courses. Completion, mastery and skill remain separate claims. End-to-end lineage from a
skill to an attempt, rendered material and source remains active work.

## Adaptation

SkillNet separates the stable course contract from the experience served to one learner.

**Static delivery:** generated Markdown and exercises remain the compatibility path.

**Dynamic delivery:** a validated course schema can produce per-node episodes using grounded course
knowledge, learner profile, current state and an approved component catalog. The controlled runtime
can vary the explanation, example, activity, support, medium and interface without changing the
objective or evidence requirement. Equivalent learner inputs may share a render; adaptive episodes
and multi-agent review are optional features and are disabled by default.

**Learner memory:** editable memory currently personalizes the tutor. Lesson generation uses
declared preferences, learner state and bounded event projections. Using free-form memory to steer
shared lesson renders remains future work. This is distinct from immediate intent.

**Adaptive regeneration:** detecting weak content across many learners and proposing a grounded
revision remains future work.

## Learning Loop

The implemented loop records evidence from each interaction:

```
Learner takes course
    |
    v
Experience and attempts recorded
    |
    v
Progress, mastery and skills updated through their own rules
    |
    v
Course-specific tutor and explain flows retrieve course context
    |
    v
Admin sees progress and recorded skills
    |
    v
(Future) evidence supports reviewed changes to experience or content
```

Recording events is implemented. Proving that an adaptation improves learning and automatically
changing the course from aggregate evidence are separate roadmap outcomes.

## Living Content

Company documentation changes. SkillNet is designed to treat sources as living rather than static.
The following behavior is a product horizon, not the current end-to-end workflow:

- When a document is re-uploaded, the system detects what changed
- Affected courses are flagged for review
- The admin decides whether to regenerate or keep the current version
- Employees see a version indicator so they know if their training is current

This lets SkillNet stay in sync with the company's knowledge instead of generating content only once.
