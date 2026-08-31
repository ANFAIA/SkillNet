# Vision

> **Status: product direction.** This document explains the ideas that should survive model,
> interface and implementation changes. Current behavior and future work are separated in the
> [roadmap](../ROADMAP.md).

## The structural problem

Organizations already contain the knowledge their people need, but that knowledge often has no
reliable channel. It lives in documents, conversations and the heads of a few experienced people.
When someone new arrives, another person has to stop their work and reconstruct the training.

Traditional learning software stores courses. Adding a chatbot or a quiz generator can make those
courses easier to produce, but it does not change the deeper structure: the experience is still
designed once and repeated for everyone.

SkillNet starts from a different separation:

- the **knowledge and objective** can be shared;
- the **way that knowledge is explained, practised and experienced** can change;
- the **evidence required to show understanding** must remain traceable.

## What SkillNet believes

### 1. Knowledge should be able to teach without depending on one person being available

The goal is not to remove the people who know. It is to give their knowledge another channel. A
source can become a course, a grounded tutor, practice and reusable learning material while keeping
its provenance visible.

### 2. The same knowledge does not require the same experience

One person may need foundations; another may need an example, a simulation or a difficult case. The
objective and evidence bar can stay stable while explanation, activity, medium and interface change.

Variation alone is not personalization. An adaptation only earns its place when it is grounded in
the course, appropriate to the current person and useful for the learning objective.

### 3. Intent is not memory

Understanding what someone asks for in the current moment is different from knowing what has helped
them over time. SkillNet treats them as separate concerns:

- **Context and intent** shape tutor and contextual-explain interactions.
- **Editable learner memory** accumulates declared preferences and curated observations from tutor
  and media interactions, and currently personalizes the tutor.

Lesson generation currently uses declared preferences, learner state and bounded event projections;
free-form memory does not steer shared renders. Memory must remain inspectable and correctable. A
system should form revisable hypotheses about a person, not turn a preference into a permanent label.

### 4. Technology should adapt to people, not make every person adapt to one interface

Software traditionally asks users to learn its fixed screens and workflows. Generative interfaces
make another direction possible: the application can compose the surface needed for the current
task from a controlled set of capabilities.

This does not mean generating arbitrary code for every screen. SkillNet frames the design space in
three levels; the first two are implemented and the third remains research:

1. **Fixed structure, changing content** for common and predictable work.
2. **Controlled composition** from approved components for most adaptive learning experiences.
3. **Open generation** only when a new simulation or interaction is genuinely necessary and can be
   validated for quality, latency, cost and safety.

The boundary will move as models improve. More generation is not automatically better.

### 5. Components are part of the pedagogy

A course is not text placed inside cards. A worked example, comparison, diagram, practice activity,
audio explanation and simulation each make different actions possible. SkillNet uses OpenUI to
compose a supported, version-pinned subset of Didact's educational components.

The model should speak the language of the interface rather than rewrite the application from
scratch.

### 6. Learning must leave evidence

Completion, mastery and skill are different claims. SkillNet records attempts, progress, rendered
experiences and source provenance. Talent surfaces currently show recorded skills with their source
courses; complete lineage from skill to attempt, render and source remains active work.

Traceability is not only an admin feature. It is what makes adaptation testable: the system can ask
whether a different explanation actually helped instead of assuming that it did.

### 7. Knowledge should remain alive and portable

Company knowledge changes. Courses should not become detached copies that silently age. The source
should remain identifiable so that future changes can be detected, reviewed and propagated.

The resulting knowledge and talent data should also be available through open interfaces. SkillNet
is not meant to become a closed super-application; its capabilities can reach the chats, agents and
tools people already use.

## How the vision shapes engineering

| Product principle | Engineering consequence |
| --- | --- |
| Grounding before generation | Sources, knowledge packs, provenance and deterministic fallbacks precede interface generation. |
| Same knowledge, different path | The course contract stays separate from the per-learner episode. |
| Intent is not memory | Current request context and accumulated learner evidence have separate contracts and controls. |
| Controlled generation first | OpenUI programs are validated against an approved catalog; open HTML is not part of the current runtime. |
| Components carry pedagogy | Didact components expose learning actions, not just visual decoration. |
| Evidence over labels | Attempts, mastery and skills remain distinct and auditable. |
| Models will change | The LLM layer stays provider-agnostic and the architecture owns product behavior. |
| Organizations own their knowledge | Self-hosting and open interfaces remain first-class constraints. |

## Boundaries

SkillNet does not claim that a model can infer a person's ideal way of learning from a few clicks.
It does not treat popular learning-style categories as identities. It does not assume that a richer
interface produces better learning. Those are questions to evaluate with evidence.

The system proposes and adapts within explicit contracts. Admins retain authority over sources and
course objectives. The self-service API supports inspecting, editing and clearing retained memory;
learner-facing controls remain roadmap work. Generated screens remain constrained and validated by
the runtime.

## The thesis in one sentence

> SkillNet turns shared knowledge into grounded, traceable learning that can take different forms
> for different learner profiles and states.
