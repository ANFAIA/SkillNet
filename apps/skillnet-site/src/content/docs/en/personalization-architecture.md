---
title: "Personalization architecture"
order: 38
section: "extensibility"
---

# Pedagogical personalization architecture

**Date:** 2026-08-11
**Status:** target architecture and incremental plan; does not describe behavior already
implemented.
**Applies to:** the dynamic courses v2 runtime and a future external component library.

## 1. Decision

Personalization is split into five decisions with different authority. A single prompt is not
asked to simultaneously choose what to teach, how to practice it, and which component to draw.

```text
Validated CourseNode
  -> learning objective       (what the learner must be able to do; not personalized)
  -> cognitive mission        (what they will do to learn it)
  -> representation           (text, image, audio, table, diagram...)
  -> component                (concrete catalog capability)
  -> support                  (hints, example, density, feedback)
  -> validated, frozen UI spec
```

The valuable variation happens in representation, component, and support. The objective and the
critical facts stay stable. So "personalizing" does not mean generating an arbitrarily different
lesson, but producing comparable variants of the same pedagogical intent.

This architecture is concrete and does not replace the decisions in
[`adaptive-learning.md`](adaptive-learning.md),
[`arquitectura-componentes-funcional.md`](arquitectura-componentes-funcional.md), and
[`v2-dynamic-courses.md`](v2-dynamic-courses.md).

The publishing architecture that builds variants during course generation, exposes the neutral
`LearningExperience` boundary, and normalizes evidence from Didact, video, games, or simulations
toward mastery is defined in
[`learning-experience-architecture.md`](learning-experience-architecture.md). This document keeps
authority over profile projection, support, caching, and capability-based resolution.

## 2. The five layers

| Layer | Question | Main input | Output | Authority |
|---|---|---|---|---|
| Objective | What evidence will demonstrate learning? | `CourseNode.outcome`, source, and criticality | observable criterion | creator; schema gate |
| Cognitive mission | What core action will the learner take? | objective, knowledge type, and prior error | `recognize`, `reconstruct`, `interpret`, `decide`, `explain`, or `produce` | pedagogical policy |
| Representation | In what modality is it expressed? | source capabilities, declared preference, and accessibility | one or more compatible modalities | user + hard constraints |
| Component | What catalog capability implements mission and representation? | catalog descriptor, domain, cost, and requirements | `component_id@version` or rejection | deterministic resolver |
| Support | How much help does this person need right now? | mastery band, experience, errors, reading adjustments | density, hints, example, and feedback | adaptive policy |

`ContentFunction` still describes the **usable form of the source** (`CONTRAST`, `PROCEDURALIZE`,
`QUANTIFY`...). The mission describes the learner's action. They are not the same axis: a
procedural source can serve to `reconstruct` the order, or to `decide` which step to apply when
facing an exception.

## 3. Intermediate contract

Before the blueprint there must be a typed, small, auditable plan. It is a domain decision, not a
UI spec, and it contains no generated prose.

```python
@dataclass(frozen=True)
class LearningExperiencePlan:
    objective_id: str
    objective_version: int
    mission: CognitiveMission
    source_functions: tuple[ContentFunction, ...]
    representations: tuple[Presentation, ...]
    required_facts: tuple[str, ...]
    required_safety: tuple[str, ...]
    support: SupportPolicy
    component_candidates: tuple[ComponentRef, ...]
    rationale_codes: tuple[str, ...]
    policy_version: str
```

The plan contains references to facts or source spans, not copies rewritten by the model. Content
agents receive the plan and fill in components; they cannot change the mission, candidates,
criticality, or constraints. The assembler accepts only IDs declared by the blueprint: an orphan
block is a reparable error, not a component that gets automatically wired to the root.

### Plan invariants

1. There is one central mission per node. It can materialize as a rich component with many states
   and actions, or as several coherent components; it does not equate to limiting the amount of
   UI. What is avoided is a second, competing mission or redundant blocks that add no new
   capability.
2. Verification observes the objective; it is not chosen for visual variety.
3. The warnings, limits, and prohibitions of a critical source are `required_safety` and survive
   any variant.
4. A requested modality appears when a compatible capability exists. If it doesn't, the plan
   records a visible `fallback_reason`; it never pretends to have satisfied it.
5. Accessibility is a mandatory filter applied before ranking. A preference cannot select a
   component the person cannot operate.
6. Any producer can return `Declined(reason)`. With insufficient data it falls back to the next
   candidate; it does not invent figures, spatial relationships, branches, or media.
7. The renderer only receives a validated UI spec; never free-form HTML or generated code.

## 4. Personalization projection

The planner does not receive `memory_md`, raw events, or free-text profile. It receives a
deterministic, closed-vocabulary, identity-free projection:

```json
{
  "declared_presentations": ["image"],
  "inferred_presentation_bucket": "exercise-high",
  "support_band": "novice",
  "density": 2,
  "accessibility_capabilities": ["keyboard", "reduced_motion"],
  "error_signal": "procedural",
  "calibrating": false,
  "projection_version": "personalization/1"
}
```

The declared preference is a positive constraint: "include image", not "remove text, practice, and
feedback". The current `format_vector` remains as a secondary inferred signal. Support changes the
amount of help, not the truth of the explanation nor the objective.

The initial compilation lives in `src/personalization/projection.py`. It accepts the profile shape
already loaded by the runtime, but discards `role_title` and `sector`: they can still contextualize
examples in the current pipeline, but are not preferences and are not copied into the plan. It also
does not accept `user_id`, `memory_md`, or raw events. During the three calibration nodes the
inferred vector is marked as unknown. The legacy `codigo` dimension also remains unknown, because
assigning it to text or image would invent a semantics that the current events do not measure.

## 5. Resolution against the component library

The library publishes capabilities; SkillNet keeps the policy. Its versioned descriptor must be
able to answer, without knowing React, these questions:

- what missions, source functions, and representations it supports;
- what affordances it offers (manipulate, build, rehearse, inspect result...);
- what requirements it needs (`numeric_series`, `image_asset`, `branching_script`...);
- what accessible operations it offers and what the alternative to dragging is;
- what events and evidence it produces and what feedback contract it guarantees;
- what versioned state model it needs;
- what producer builds it (`content`, `assessment`, `media`, `simulation`, or `deterministic`);
- what cost and latency it adds;
- what props schema and renderer version it needs.

Resolution is intersection plus ranking:

```text
candidates = catalog
  ∩ mission
  ∩ source function
  ∩ requested representation
  ∩ accessibility capabilities
  ∩ actually available requirements
  ∩ deployment budget

chosen = rank(candidates, policy, controlled exploration)
```

The result is not just a name. The plan freezes a `ResolvedComponent` with `component_id@version`,
`producer_kind`, affordances, requirements, `state_model_ref`, and evidence events. The pedagogical
function does not decide which agent generates it: a simulation can teach and assess at the same
time, but it needs a producer and validator different from a `QuizItem`.

### Image generated within OpenUI

A future course image does not break the *on the fly* principle: the plan resolves a descriptor
with `presentations={image}`, `producer_kind=media`, and requirements such as `source_spans`,
`image_brief`, or an already available `image_asset`. The media producer generates or retrieves the
asset, preserves provenance and alt text, and returns a typed reference. The assembler incorporates
it into the OpenUI UI spec alongside practice and safety; it does not generate HTML or embed a
free-form prompt on the client. If a producer, budget, or sufficient evidence is missing, the
candidate returns `Declined(reason)` and another compatible representation is chosen. The image is
thus a dynamic catalog capability, not a fixed template or an exception in the orchestrator.

The catalog can grow to hundreds of components without widening the prompt: the LLM, when
necessary, sees only the few already-filtered candidates. `component_id@version` is persisted;
React class names are not. The current kit and the new library coexist through two adapters that
consume the same plan and produce the same canonical IR.

## 6. Cache, privacy, and stability

The shared cache is only safe if every signal reaching the prompt is represented in a
non-identifying key. The target key material is:

```text
node_id | schema_version | objective_version | policy_version |
projection_version | preference_bucket | support_band | density |
accessibility_capability_bucket | component_catalog_version |
backend | model | prompt_version
```

Rules:

- never include `user_id`, free-text memory, diagnostics, or individual events;
- never introduce into the prompt a datum that isn't projected in the key;
- buckets must be discrete and have enough population to avoid pseudonymization;
- the render is frozen when the node is opened, as v2 already decides; it does not change during
  an active screen;
- changes to objective, policy, catalog, or prompt explicitly invalidate the key;
- the plan and its `rationale_codes` are stored for auditing, separate from the render prose.

## 7. Layered validation

Current syntactic validation is necessary, but not sufficient. Each render passes distinct gates:

| Gate | Checks | Type |
|---|---|---|
| Plan | single mission, constraints, available candidate | deterministic |
| Source | figures, relationships, media, and backed facts | deterministic + focused eval |
| Component | props schema, version, accessibility, and cost | deterministic |
| Assembly | exact IDs, reachability from `root`, order, and closure | deterministic |
| Pedagogical | observable objective, informative feedback, coherent support | rubric-based eval |
| Safety | preservation of `required_safety`, no impossible or incoherent states | deterministic where possible |

Metrics distinguish generated components from components **reachable** from `root`. An orphan block
does not count as variety or as compliance. For rich interactive components, specific evals are
added: unique solution, possible states, visual clarity, consistency between state and feedback,
and plausibility of the simulation.

## 8. Experiments that produce knowledge

It's not "prompt A versus prompt B" compared by aggregating all courses. Objective and source are
fixed, and a single layer is changed:

1. **Perspectives:** the same objective as `interpret`, `detect`, and `decide`; identical critical
   facts.
2. **Representation:** same mission with table, diagram, or image; the requested modality is kept
   across all variants assigned to that person.
3. **Support:** same component with a worked example, graded hints, or a direct case.
4. **Resolver:** same plan against the current kit and the new library; equivalent golden specs and
   events.
5. **Ablation:** with/without inferred preference, never with/without mandatory accessibility.

Per generation, the following is measured: first-pass validation, fallback, facts
omitted/invented, safety preserved, reachability, mission fulfilled, variety across equivalent
objectives, latency, and cost. With users, the following are separated: preference, engagement,
immediate mastery, and transfer. A less flat screen that doesn't improve the learner's action does
not win.

## 9. Incremental migration

### Phase 0 — observability with no behavior change

- Log the current decision as `PlanTrace`: format, `ContentFunction`, blueprint, reachable blocks,
  corrections, and fallback.
- Fix the bench to count only the subgraph reachable from `root`.
- Create a small corpus labeled by objective, expected mission, and mandatory facts.

**Gate:** zero difference in served UI specs.

### Phase 1 — plan in shadow mode

- Build `LearningExperiencePlan` as a pure function from the state already available.
- Do not use it yet to generate; compare its selection against the real pipeline.
- Version the projection and the policy from day one.

**Gate:** deterministic, explainable plans; no free-form signal enters the prompt or the cache.

### Phase 2 — typed mission and support

- Make the blueprint consume `mission` and `SupportPolicy`.
- Keep the current component mapping to isolate the architectural effect.
- Reject extras and orphans instead of wiring them to the root.

**Gate:** safety and verification do not regress; blueprint compliance increases.

### Phase 3 — capability resolver

- Move function, requirements, accessibility, and cost into the registry.
- Resolve candidates before calling the writer agents.
- Keep fallback to the current kit and `Declined(reason)`.

**Gate:** adding a component does not modify `shape.py`, the global prompt, or the assembler.

### Phase 4 — declared preference

- Add editable presentation preferences in onboarding and settings.
- Compile `user.md` into `PersonalizationProjection`; do not inject it directly.
- Incorporate the buckets into the cache and show modality fallback reasons.

**Gate:** E2E tests demonstrate that a supported preference appears and persists, and that
changing it regenerates only compatible renders, without leaking identity into the cache.

### Phase 5 — external library and exploration

- Dual adapter with golden specs before replacing components.
- Enable new components via capability flags and by family.
- Explore variants only within valid plans and with rollback capability.

**Gate:** functional equivalence between the old and new adapters; the new components pass their
specific evals before production.

## 10. Proposed location in code

```text
src/personalization/
  projection.py       # profile/events -> PersonalizationProjection, pure
  policy.py           # objective + projection -> mission and support, pure
  plan.py             # types and invariants of LearningExperiencePlan
  resolver.py         # plan + catalog -> candidates or Declined, pure
  cache.py            # versioned serialization of buckets

src/components/
  catalog.py          # catalog Protocol, no React
  legacy_adapter.py   # descriptors of the current kit
  library_adapter.py  # future external library
```

LangGraph orchestrates loading, planning, writing, validation, and persistence. The domain rules
above remain pure functions outside the nodes and the prompts. Subagents receive a frozen contract
and narrow responsibilities: planning, writing content, designing interaction, and assembling;
none can reinterpret another layer's decisions.

## 11. Architectural success criteria

The architecture will have worked when:

- adding a component means registering capabilities and tests, not editing central decisions;
- two renders can vary without changing the objective or the mandatory facts;
- every difference can be explained through policy codes;
- an explicit modality request is either fulfilled or produces an honest reason;
- no invalid variant reaches the human just because it compiles;
- the system can revert to the previous kit without losing state or measured learning.

The concrete strategy for consuming Didact's large catalog, limiting each decision to a shortlist,
distinguishing recipes from new components, and moving toward level-3 GenUI is in
[`didact-integration-strategy.md`](didact-integration-strategy.md).
