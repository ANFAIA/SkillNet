---
title: "Vision"
order: 20
section: "start"
---

# Vision

> **Status: product direction.** These are the ideas that should survive model, interface and
> implementation changes.

## The structural problem

Organizations already contain the knowledge their people need, but it often has no reliable
channel. It lives in documents, conversations and the heads of a few experienced people. When
someone new arrives, another person has to stop their work and reconstruct the training.

SkillNet separates three things that traditional course software tends to bind together:

- the **knowledge and objective** can be shared;
- the **way that knowledge is explained, practised and experienced** can change;
- the **evidence required to show understanding** must remain traceable.

## What SkillNet believes

### Knowledge should be able to teach

The goal is not to remove the people who know. It is to give their knowledge another channel. A
source can become a course, a grounded tutor, practice and reusable learning material while keeping
its provenance visible.

### The same knowledge does not require the same experience

One person may need foundations; another may need an example, a simulation or a difficult case. The
objective and evidence bar can stay stable while explanation, activity, medium and interface change.
Variation only becomes personalization when it is grounded, appropriate and useful for the learning
objective.

### Intent is not memory

Understanding what someone asks for now is different from knowing what has helped over time.
Context and intent shape tutor and contextual-explain interactions. Editable learner memory
accumulates declared preferences and curated observations from tutor and media interactions, and
currently personalizes the tutor. Lesson generation uses declared preferences, learner state and
bounded event projections; free-form memory does not steer shared renders. Memory must remain
inspectable, correctable and revisable.

### Technology should adapt to people

Software traditionally asks people to learn its fixed screens. Generative interfaces allow the
application to compose a surface for the current task, but more generation is not automatically
better. The first two levels are implemented; the third remains research:

1. **Fixed structure, changing content** for predictable work.
2. **Controlled composition** from approved components for most adaptive experiences.
3. **Open generation** only when a new simulation is necessary and can be validated for quality,
   latency, cost and safety.

### Components are part of the pedagogy

A course is not text inside cards. Worked examples, diagrams, practice activities, audio and
simulations make different actions possible. SkillNet uses OpenUI to compose a supported,
version-pinned subset of Didact's educational components instead of rewriting the application.

### Learning must leave evidence

Completion, mastery and skill are different claims. SkillNet records attempts, progress, rendered
experiences and source provenance. Talent surfaces show skills with their source courses; complete
lineage from a skill to attempt, render and source remains active work.

### Knowledge should remain alive and portable

Sources change, so courses should not become detached copies that silently age. Knowledge and
talent data should also remain available through open interfaces rather than being trapped inside a
closed super-application.

## Boundaries

SkillNet does not claim that a model can infer a person's ideal way of learning from a few clicks.
It does not turn preferences into fixed learning-style labels, and it does not assume that a richer
interface produces better learning. Admins retain authority over sources and objectives. The
self-service API supports inspecting, editing and clearing retained memory; learner-facing controls
remain roadmap work. Generated screens remain constrained and validated.

## The thesis in one sentence

> SkillNet turns shared knowledge into grounded, traceable learning that can take different forms
> for different learner profiles and states.
