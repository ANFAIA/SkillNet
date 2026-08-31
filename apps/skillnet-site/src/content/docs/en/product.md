---
title: "Product"
order: 21
section: "start"
---

# Product

> **Status: current product baseline and direction.** This document separates implemented behavior
> from later work.
>
> The current company-first product remains the implemented baseline. The future
> audience model for organization and individual deployments is defined in
> [audience-modes.md](/en/docs/audience-modes).

---

## What is SkillNet

SkillNet turns an idea or existing knowledge into grounded, traceable training that can take a
different form for each person.

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
| **Employee** | Learns, practices, asks questions. The experience adapts to their level and pace |

## Content types

| Type | Purpose |
|------|---------|
| **Course** | Modules + exercises + evaluation. Structured learning path, generated from company documents |
| **Manual** | Reference material. Employees consult when they need it. Organized for lookup, not learning |
| **Chatbot** | Per-content chatbot. Employees ask questions about the material and get answers grounded in it |

## Content generation

Current creation paths:

- **From documents** — upload PDF, DOCX, Markdown or TXT material and generate a grounded course.
- **From an idea** — SkillNet creates a generated source with provenance and builds from it.
- **From external clients** — the web UI, `/ext/v1`, A2A and MCP use the same authoring services.

The static v1 pipeline and dynamic v2 schema path coexist. The delivery decision is made per course.
See [v1 scope](/en/docs/course-scope), [dynamic courses](/en/docs/dynamic-courses) and
[AI course design](/en/docs/ai-course-design).

## Exercises

Multiple types, defined by the content itself. Examples include tests, practical cases, real-world tasks ("do this and tell me if it worked"), and others to be determined as the product evolves.

Every exercise includes an explanation citing the source material. Answers are evaluated either deterministically (test, true/false, fill_blank) or by an LLM with a rubric (practical_case, dialogue).

## Tracking

Learners complete courses. The system records the evidence it can observe:

- Enrollments and course progress
- Node completion and mastery
- Exercise and activity attempts
- Learning events and the rendered experience seen by the learner
- Skills recorded through course work

The admin talent surfaces expose people, assigned courses, progress and recorded skills. Completion,
mastery and skill remain separate claims.

## Adaptation

SkillNet separates the stable course contract from the experience served to one learner.

**Static delivery:** generated Markdown and exercises remain the compatibility path.

**Dynamic delivery:** a validated course schema can produce per-node episodes using grounded course
knowledge, learner profile, current state and an approved component catalog. The runtime may adapt
the explanation, example, activity, support, medium and interface without changing the objective or
evidence requirement.

**Longer-term adaptation:** learner memory may use declared preferences and observed outcomes across
sessions. This is distinct from immediate intent, and every retained hypothesis must remain
inspectable and correctable.

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
Tutor and explain flows use grounded course context
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
- Affected courses and manuals are flagged for review
- The admin decides whether to regenerate or keep the current version
- Employees see a version indicator so they know if their training is current

This lets SkillNet stay in sync with the company's knowledge instead of generating content only once.
