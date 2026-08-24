---
title: "Didact integration"
order: 47
section: "extensibility"
---

# Didact integration in SkillNet

**Status:** full inventory integrated; functional adoption by families
**Didact:** <https://github.com/JoseEstevez520/Didact> (MIT)
**Revision examined:** [`06c80e8`](https://github.com/JoseEstevez520/Didact/commit/06c80e8a8af4f20ad20ba345b7b6b13e1cc27e0c)
**Related:** `openui-adoption.md`, `personalization-architecture.md`,
`learning-experience-architecture.md`, `v2-dynamic-courses.md`

> **Scope of this document:** describes the current inventory and executable integration
> of Didact. The target neutral architecture —where Didact is a replaceable provider,
> `LearningExperience` replaces the specific boundary, and legacy pedagogical blocks leave
> new courses— is defined in
> [`learning-experience-architecture.md`](learning-experience-architecture.md). When a
> historical incremental-adoption decision on this page contradicts that target, the
> neutral document wins; this page still wins on which types and ports work today.

## Decision

SkillNet keeps pedagogical authoring, personalization, RAG, evaluation security, and
on-the-fly generated OpenUI composition. Didact contributes accessible educational
contracts and components. It is not integrated as a second course engine nor as a
list of widgets the LLM must fully know.

```text
objective + knowledge pack + closed profile
                 │
                 ▼
      SkillNet experience plan
                 │
                 ▼
   Didact capability resolver
                 │  2–5 compatible candidates
                 ▼
       on-the-fly OpenUI generation
                 │
                 ▼
  validation → adapted Didact render → events
```

Didact offers the facets needed to select without inferring from names: purpose,
representation, learner action, context, accessibility, maturity, authoring schema,
capabilities, and optional dependencies. SkillNet adapts them to `ComponentDescriptor`;
the catalog doesn't decide by itself what the person should learn.

## Direct OpenUI base

Integration started with two experiences from the real `skillnet-ui/1` catalog:

| Component | Why it's included | State it keeps |
| --- | --- | --- |
| `Flashcard(front, back)` | Recall attempt before reveal; useful for recognizing or reconstructing | reveal and local self-assessment |
| `HintReveal(title, hints, solution)` | Progressive hints and solution on request; especially useful with more scaffolding | hint count and visible solution |

Both comply with the static dialect: literal properties, local React state, no
`Query`, `Mutation`, executable code, or identity. Glossary, Timeline, and WorkedExample
were later added as direct blocks, and `DidactActivity` as an opaque reference to
server-owned definitions. Their schemas exist in frontend and backend; the drift test
checks names, property order, and the prompt artifact. The prompt version invalidates
renders produced with earlier catalogs.

In the first adoption, `StepSequence` wasn't replaced by `Timeline`: they represented the
same capability and duplicating them in the catalog was avoided. This was an incremental
decision, **not the target state**. For new courses, the approved migration removes
`StepSequence` and the other legacy pedagogical components from the authoring catalog;
Didact enters through the neutral `LearningExperience` boundary. Legacy renderers remain
only to play back published courses. Spaced repetition also wasn't added; Didact
correctly separates the card from repeat scheduling, and SkillNet doesn't need that
scheduler yet.

## Selection as the catalog grows

### Current executable boundary

Full availability and model exposure are two distinct sets:

- `didact_snapshot.json` and `export_didact_descriptors()` project the **34 types** to
  the resolver. They keep identity, facets, actions, representations, accessibility,
  producer, and port requirements; a blocked type remains discoverable for
  experiments and to explain what capability is missing.
- `openui_names_for_shortlist()` is the fail-closed gate. It only translates a type
  to its schema name when the renderer, emission permission, and ports are ready.
- `build_didact_prompt_slice()` serializes only those accepted schemas along with
  the safe screen shell. An installed but blocked type produces an explicit error;
  it never silently disappears or reaches the LLM without a contract.

Today all 34 types are inventoried and lazy-loaded in the frontend. Twenty-nine
have an honest emission path: five direct OpenUI blocks, eleven server-side
evaluations, three activities with reviewed assets, two host progress reads, and
eight activities with definition, state, and ports. The other five remain
available to the resolver but blocked until a scheduler, adapted simulation, or
sandbox exist. The runtime table at the end of this document is the authority on
each family.

The boundary is already wired to the generator: the runtime forms a shortlist of
3-5 types, applies renderer, port, and data gates, and hands the model only the
allowed slice. For rich activities, an authoring phase creates a server-owned
`ActivityDefinition` and validates it before persisting. If it can't build one with
backed data, it `Decline`s and falls back to a safe representation.

The model must not receive all of Didact's components. Deterministic filters are
applied before each generation:

1. availability and allowed maturity;
2. cognitive mission and source function;
3. requirements present in the knowledge pack;
4. mandatory accessibility capabilities;
5. available producer (`content`, `assessment`, `media`, `simulation`, or `deterministic`);
6. declared presentation preferences, as a bias rather than an obligation;
7. screen complexity budget.

The result is a small, versioned collection, not a rigid final choice. The LLM can
compose among those candidates and `Decline` if none honestly represents the
mission. `component_id@version`, capabilities, and selection version will enter
trace and cache once the filter moves from shadow to production.

## Adoption levels

### Level A — static and safe

Flat props or lists, ephemeral state, no external services. Can go directly into
OpenUI: Flashcard, HintReveal, Glossary, and some visual representations.

### Level B — response and host evaluation

The component collects a serializable response, but SkillNet keeps the correct
answer and evaluates it via API. Matching, evidence-based rubrics, annotation, and
advanced questions need mapping to the endpoint and event envelope before entering.

### Level C — engine or injected medium

CodeExercise, InteractiveMedia, BranchingScenario, and SimulationLab need an
explicit execution, playback, or state-transition port. A simulation is data +
state + deterministic transitions + renderer; never LLM-invented code inside the
OpenUI program.

## Invariants

- More components add richness when they add actions, states, feedback, or useful
  representations.
- Critical facts and safety rules come from the knowledge pack, not the component.
- A visual preference doesn't force a valueless image nor allow inventing an asset.
- The answer key never reaches props in the browser.
- Dragging is never the only way to interact.
- A missing capability produces an explicit fallback or `Decline`, not a faked
  simulation.
- The copy of a Didact component lives in SkillNet and is updated deliberately; a
  mutable `main` is not consumed in production.

## Frontend runtime matrix (2026-08-13)

All 34 types are installed, have a lazy loader, and can be referenced via
`DidactActivity(activity_id, component_id)`. OpenUI never receives the public
definition, correct answers, or evaluation configuration. The `didact.progress`
and `didact.mastery-badge` percentage is injected by the host from
`LearnerNodeState`; the client can't write it.

| State | Types | Reason |
|---|---|---|
| Usable local/static | flashcard, glossary-term, hint-reveal, rubric, timeline-steps, worked-example, data-explorer | Doesn't claim correctness; absent optional ports degrade |
| Host persistence | self-explanation-prompt, concept-map, drawing-response, evidence-annotation | State via `/activities/{id}/state`; drawing and annotation accept async evaluation |
| Compatible host evaluation | equation-workbench, measurement-lab | Async callback with result from `/activities/{id}/evaluate` |
| Server-side evaluation | matching, sort, categorize, five quiz types, completion-problem, numeric-question, word-bank | `SecureEvaluatedActivity` adapter; the key never reaches props, DOM, or events |
| Reviewed assets | hotspot, label-diagram, interactive-media | Opaque `skasset_` refs; geometry/transcript verified server-side |
| Read-only progress | progress, mastery-badge | `GET /activities/{id}/progress` projects node mastery; `progress.write` is forbidden |
| Blocked: composition/scheduling | practice-set, retrieval-practice-session | Composes evaluable children or requires a scheduler; not faked |
| Blocked: runtime | branching-scenario, simulation-lab | Missing adaptation of remote transitions to the component's concrete state |
| Blocked: execution | code-exercise | The generic response still doesn't satisfy `ArtifactExecutionResponse` |

Definition, state, evaluation, transition, execution, assets, and progress
endpoints are wired as generic ports. A port is only exposed when the concrete
contract is compatible. The mere existence of `/evaluate` doesn't unlock a quiz
that self-corrects in the browser, nor does `/progress` enable `practice-set`.

## Proposed next wave

1. real scheduler before emitting `retrieval-practice-session`;
2. composition of evaluable children before emitting `practice-set`;
3. deterministic transitions for `branching-scenario` and `simulation-lab` over the
   component's concrete state;
4. `code-exercise` sandbox that satisfies `ArtifactExecutionResponse`;
5. measure the 7 selection strategies with the offline bench and, if a key is
   available, a small LLM pilot.

Each wave is measured with the same node and knowledge pack: critical-fact
coverage, obtainable evidence, action variety, accessibility, repair rate, tokens,
latency, and stability. A component isn't promoted just because its isolated
story is appealing.

## Closing status as of August 13, 2026

- All 34 Didact types are pinned by commit, inventoried, and available via lazy
  loaders; the full catalog doesn't increase the initial bundle.
- 29 types are emittable. Five remain honestly blocked: `practice-set`,
  `retrieval-practice-session`, `branching-scenario`, `simulation-lab`, and
  `code-exercise`.
- The runtime defaults to `top5` over a shortlist of 3-5 candidates. Dual-agent and
  specialist remain in shadow. The full catalog remains queryable by the resolver.
- The optional authoring call logs tokens, model, and duration; if it fails, the
  lesson continues with a safe representation. An `unsupported` type declines
  before reaching the LLM.
- The fixture experiment favors intent + shortlist + specific schema: 89.8 points
  and 100% gate pass, versus 27.8 for the legacy arm. This is architecture
  evidence, not definitive proof of LLM quality.
- Causal personalization remains weak (15.4% in the fixture). The next round must
  isolate scaffolding, presentation, and depth with real models and blind
  evaluation.
