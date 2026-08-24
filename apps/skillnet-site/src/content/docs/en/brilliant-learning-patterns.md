---
title: "Brilliant-style learning patterns"
order: 40
section: "extensibility"
---

# Brilliant experience patterns applicable to SkillNet

**Observation date:** 2026-08-12
**Status:** design reference and experiment proposal; does not describe already
implemented functionality.
**Scope:** lesson distribution, interaction depth, progression, feedback, and navigation.

This document does not propose copying Brilliant's interface, content, or proprietary
mechanics. It extracts observable patterns from their public surfaces and translates
them into decisions that fit OpenUI, the `NodeKnowledgePack`, and Didact.

## 1. What was observed directly

The claims in this section come from Brilliant's public pages; they do not require
account access nor do they reconstruct protected content.

### Hierarchy and navigation

- The catalog groups courses into **Learning Paths** ordered from fundamentals to
  application, with regular checkpoints. A path recommends a sequence, but Premium
  allows jumping to any lesson; the free tier keeps sequential progress.
- The public page for *Solving Equations* presents a visible hierarchy of
  **course -> 13 levels -> 4-7 lessons per level -> Level Review**. It states 68
  lessons and 895 exercises. The person can see the full map, but the main action
  remains starting or continuing the next lesson.
- Names show a progression of actions and models: finding unknowns, building
  expressions, substituting, distributing, factoring, combining, working with
  inequalities, and reasoning with systems. It's not a flat list of independent
  topics.

Sources: [public catalog](https://brilliant.org/courses/),
[Solving Equations](https://brilliant.org/courses/pre-algebra/),
[Learning Paths](https://brilliant.org/help/features/what-are-learning-paths/).

### Learning pace

- Brilliant describes its lessons as brief explanations mixed with manipulable
  problems, simulations, and immediate feedback.
- In *Solving Equations* they state each lesson begins with a problem at the edge of
  what the person already understands, requiring a small mental leap. It first lets
  them try; names and formal theory appear after building intuition.
- For a single concept they don't generate one question: they describe a difficulty
  ramp, variations, and edge cases. Their public reference talks about more than
  twenty problems per concept in some courses.
- In programming courses they look for a **central activity that scales from simple
  to complex**. In their image-processing example, the same surface lets you
  decompose operations, combine them, and see an immediate visual consequence.

Sources: [Solving Equations: action first](https://blog.brilliant.org/solving-equations/),
[Hand-crafted, machine-made](https://blog.brilliant.org/hand-crafted-machine-made/),
[Decomposition and Abstraction](https://blog.brilliant.org/decomposition-and-abstraction/),
[Brilliant Basics](https://brilliant.org/help/using-brilliant/).

### Interaction depth and feedback

- Interaction is not limited to selecting an answer: public examples include
  dragging a tangent, balancing weights, building equations, configuring filters,
  manipulating circuits, and observing consequences.
- The main feedback can be in the system itself: a scale tilts, an image changes, or
  a simulation stops reaching its target. An explanation or hint may appear
  afterward.
- Koji uses lesson state, incorrect attempts, and stuck points. It can highlight a
  region, annotate a graph, or introduce an intermediate question. Its help
  increases at the start and is withdrawn when it's time to demonstrate knowledge.
- Brilliant does not consider it enough for an activity to compile. Their evals
  check correctness, solvability, visual clarity, state consistency, impossible
  states, and model plausibility. A failing activity is discarded before human
  review.

Sources: [Koji and contextual feedback](https://blog.brilliant.org/a-world-class-tutor-in-every-home/),
[evals for educational games](https://blog.brilliant.org/when-almost-right-is-catastrophically-wrong-evals-for-ai-learning-games/).

## 2. Design inferences

These are interpretations, not claims literally published by Brilliant.

### "One idea per screen" means a mission, not a widget

The useful unit appears to be a **cognitive beat**: a main question, decision, or
manipulation. A beat can be small and resolved on one screen, but a rich activity can
be sustained across several phases:

```text
challenge -> exploration -> consequence -> hint/retry -> formalization -> variation
```

All those phases can occur within a single simulation if they keep answering the
same question. Splitting them into six cards doesn't make it clearer. Likewise, a
screen with a table, text, quiz, and accordion can still be flat if it contains
several competing missions.

### Valuable variety happens across the sequence

Brilliant appears to prioritize continuity of a central metaphor or activity within a
course — a scale, a visual pattern, an image filter — and vary problems, constraints,
and difficulty. Therefore, variety should not be measured only as the number of
Didact types per screen. There are three levels:

1. **local depth:** states, actions, feedback, and retries within one activity;
2. **practice variation:** new cases of the same capability without changing the
   objective;
3. **representation change:** another perspective when it adds understanding or
   transfer.

### Feedback is part of the component, not trailing text

When the consequence of an action is visible within the model, the person can form
and correct hypotheses. A generic correct/incorrect message doesn't replace that
causal relationship. Textual explanation is still useful, but it must respond to the
specific attempt and not take the place of the experience.

## 3. Contrast with SkillNet and Didact

### What is already on the right track

- `NodeKnowledgePack` separates invariants and evidence from the final narration.
- The architecture distinguishes objective, mission, representation, component, and
  support.
- The resolver delivers a shortlist, instead of showing the model all of Didact.
- `ActivityDefinition` allows separating public configuration, private evaluation,
  and learner state.
- `Declined`, port requirements, and per-component validators prevent faking
  simulations or inventing datasets.
- OpenUI still creates the composition on the fly; Didact provides declarative
  surfaces, not a second course engine.

### The current gap

The pipeline decides well **which component can appear**, but it still doesn't
clearly represent **how an experience develops across several phases**. The node and
the screen tend to coincide. This favors two failure modes:

- composing several short blocks around an explanation and calling it richness;
- generating a rich activity as an isolated configuration, without a ramp,
  variations, or feedback adapted to the attempt.

There's also a missing way to express continuity: two consecutive nodes may select
different components even when it would be pedagogically better to keep the same
mechanic and raise a single difficulty.

## 4. Recommended direction

### 4.1 Add a beat plan, not another screen template

Between the experience plan and OpenUI it's worth introducing a small, typed
sequence:

```text
LearningExperiencePlan
  -> beats[2..5]
       mission
       phase: challenge | explore | formalize | vary | apply | checkpoint | reflect
       evidence_required
       activity_ref optional
       support_policy
       page_boundary_reason
  -> OpenUI generates only the current beat
```

Not all seven phases need appear. The plan chooses the minimum the objective
requires and can keep the same `activity_ref` across beats. This way the course
remains on-the-fly without rebuilding the pedagogical intent on every screen.

### 4.2 Rule for deciding a screen change

Keep the current activity when:

- it follows the same mission and the same causal model;
- the next step depends on the previous state or attempt;
- switching surfaces would lose manipulation, comparison, or context.

Create a new screen when:

- the main cognitive action changes;
- a variation begins that must be measured without previous help;
- moving from exploration to transfer or checkpoint;
- density or accessibility make the composition no longer operable.

The boundary is recorded as a policy reason, not delegated to an LLM's aesthetic
preference.

### 4.3 Choose one central mechanic per segment

Each level or small group of nodes should be able to freeze a `core_mechanic_id`.
The resolver still allows alternatives, but favors continuity while the mechanic:

- produces the required evidence;
- supports the next difficulty;
- remains accessible;
- doesn't force data the source doesn't contain.

This doesn't reduce personalization: one person may receive more hints, another a
more direct entry, and another an alternative representation. What's stable is the
objective and the segment's coherence, not a shared canonical screen.

### 4.4 Minimum contract for rich feedback

An evaluable component should declare, when applicable:

1. observable consequence of the action;
2. diagnosis based on the attempt, not on identity;
3. hint ladder;
4. ability to retry without revealing the answer immediately;
5. explanation or solution after sufficient evidence;
6. an event that allows reducing support in later attempts.

For simulations, add state coverage, invariants, and plausibility. For closed
questions, the key stays on the server.

## 5. Next round of experiments

The whole navigation shouldn't be redesigned yet. First it needs to be checked
whether the sequence produces a better experience than the current screen.

### Experiment A: composed screen versus beats

Same `NodeKnowledgePack`, objective, and profile:

- control: one current OpenUI screen;
- treatment: 3 beats (`challenge -> explore/formalize -> checkpoint`) with state
  continuity.

Measure coverage, meaningful actions, feedback tied to the attempt, retries, total
time, visible latency, tokens, first-pass validity, and blind coherence evaluation.

### Experiment B: component variety versus depth

- variant 1: three or four different, shallow components;
- variant 2: one Didact activity with three states and feedback;
- variant 3: rich activity plus a separate checkpoint.

The hypothesis is that 2 or 3 will outperform 1 when the component really models the
phenomenon. It shouldn't be assumed: it must be measured per objective and source
type.

### Experiment C: mechanic continuity

Compare three independent nodes against a segment that keeps `core_mechanic_id` and
raises a single difficulty per node. Measure model comprehension, transfer to the
final case, and sense of repetition.

### Experiment D: adaptive help

Same activity and ground truth, varying only `support_policy`: direct entry, initial
hint, or hint ladder. Verify that personalization changes the help causally without
altering success criteria or source facts.

## 6. Provisional decision

The next evolution should not be "one screen equals one idea" as a literal rule, nor
"many components per screen". The unit must be a **cognitive mission with variable
depth**. A screen can contain a rich, multi-phase activity; a lesson can use several
screens when the action changes or an independent checkpoint is needed.

Brilliant's most transferable contribution to SkillNet is not its aesthetics. It is
this combination:

```text
visible map + intentional progression + action before theory
+ central mechanic that scales + in-context feedback + whole-system evaluation
```

SkillNet can keep its differential advantage — personalized on-the-fly generation —
if it generates each beat's configuration and support from a frozen intent, instead
of reinventing the entire pedagogy on every render.
