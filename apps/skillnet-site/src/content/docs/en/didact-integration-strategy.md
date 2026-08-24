---
title: "Didact integration strategy"
order: 48
section: "extensibility"
---

# Didact–SkillNet integration strategy

**Date:** 2026-08-12
**Status:** working direction for incremental integration.
**Scope:** educational catalog, component selection, recipes, and level-3 GenUI.

## 1. Starting point

Didact is no longer just a set of visual primitives. The catalog declares 24 distinct
educational types and provides:

- typed manifests with role, families, representations, learner actions, purposes, and contexts;
- availability, maturity, and version per component;
- authoring schema, capabilities, events, pedagogical evidence, and accessibility;
- QTI/xAPI mappings and optional dependencies;
- five editorial collections: fundamentals, math/data, languages, visual/spatial, and corporate
  training;
- registry and kits for copying code without turning Didact into a rigid product dependency;
- general components like quizzes, matching/sort/categorize, rubrics, timelines, hotspot,
  generative practice, numeric questions, and experimental `InteractiveMedia`;
- an explicit direction toward experience platforms: interactive media, data, decisions,
  simulations, and artifact creation.

SkillNet remains its first demanding consumer, not Didact's design criterion. The library
must stay general, and the specific adapter lives in SkillNet.

## 2. Main decision: large catalog, small context

Catalog growth must not linearly widen the prompt. The model never receives the full 24,
50, or 100 components. SkillNet resolves in layers and only exposes a short list of
compatible candidates:

```text
NodeKnowledgePack
  -> objective + mission + evidence + available requirements
  -> mandatory catalog filters
  -> collection/context priority
  -> capability and diversity ranking
  -> shortlist of 3–5 candidates
  -> producer configures or returns Declined
  -> validation of props, evidence, accessibility, and assembly
  -> on-the-fly OpenUI
```

Mandatory filters run before any LLM decision:

1. component available and with allowed maturity;
2. compatible mission, purpose, and learner action;
3. representation supported by the source and declared preferences;
4. requirements present (`numeric_series`, image regions, media, decision graph...);
5. an operable accessible alternative;
6. producer available and compatible with the current OpenUI dialect;
7. cost, latency, and dependencies within budget;
8. events able to produce the evidence required by the pack.

Collections are editorial priors, not closed lists. `corporate-training` can prioritize
practice, rubric, progress, or interactive media, but a component outside the collection
remains eligible when its capabilities fit better.

The final ranking must favor mission and evidence coverage, not visual novelty. Exploration
of underused components happens only among valid candidates and with measurable rollback.

## 3. Boundary of responsibilities

### Didact owns

- prop schema and version;
- rendering, ephemeral state, and interactive behavior;
- response, result, feedback, and event contract;
- accessibility and equivalent alternative;
- component's own variants;
- lifecycle, dependencies, and technical compatibility;
- general recipes demonstrating reuse across multiple domains.

### SkillNet owns

- course objective, cognitive mission, and mandatory facts;
- `NodeKnowledgePack` and evidence that must be obtained;
- personalization projection and declared preferences;
- selection policy, cost, privacy, and cache;
- data, media, and service availability;
- producer choice and fallback;
- interpretation of events as progress or mastery;
- screen composition and distribution of learning across nodes.

The adapter translates Didact manifests into SkillNet descriptors. It doesn't manually
copy names into `shape.py`, prompts, or agents. The plan freezes `component_id@version`,
capabilities, producer, requirements, events, and state model before generating the screen.

## 4. Recipes, variants, and specialized components

A specific course use case is a **recipe** by default. It can combine configuration,
content, theme, assets, and feedback rules without creating another public export.

A new component is created only when it brings at least one structural difference:

- new representation of knowledge;
- new meaningful learner action;
- different state or response model;
- validation or feedback specific to the domain;
- specific accessibility contract;
- stable composition of several interactions that needs to be reused.

Changing text, examples, sector, difficulty, image, aesthetics, or dataset doesn't
justify another component. That belongs to props, variants, or recipes. A recipe that
repeats across different domains can be promoted to a reusable platform or molecule
after the pattern is proven.

## 5. Molecules and level-3 GenUI

A molecule is a composed educational experience with its own contract: it coordinates
multiple states, actions, feedback, and evidence, but remains declarative and
validatable. Possible examples are a branching scenario, a manipulation lab, a media
with checkpoints, or an artifact-creation environment.

This makes level-3 GenUI viable without generating free code:

```text
the model does NOT generate JSX, hooks, or HTML
the model DOES choose a platform and generate a versioned configuration
the platform controls states, actions, solution, feedback, and events
the validator rejects impossible configurations before rendering
```

A complex component can produce a richer experience than a collection of small blocks
because it offers depth of action, states, and feedback. The metric is not the number
of components on screen, but:

- distinct educational affordances;
- reachable meaningful states;
- decisions or manipulations the learner performs;
- feedback tied to the action;
- observable evidence;
- transfer to the node's objective.

The first level-3 platform must be validated with at least two recipes from different
domains. If it only works for one example, it's still a specialized implementation, not
a general molecule.

## 6. Incremental integration

### Phase A — Catalog exporter

- Read Didact manifests via a versioned build artifact.
- Produce SkillNet descriptors without importing React in the backend.
- Detect drift: added, removed, renamed, or schema-incompatible component.
- Temporarily keep the legacy adapter as fallback.

### Phase B — Compatibility matrix

Classify each available type as:

- `FIT_STATIC`: literal props and ephemeral React state;
- `FIT_SERVER_EVALUATED`: needs self-contained backend evaluation;
- `FIT_MEDIA`: needs a producer/asset with provenance;
- `FIT_SIMULATION`: needs a validated state model;
- `BLOCKED`: missing infrastructure;
- `DECLINED`: doesn't meet security or the OpenUI contract.

The classification is derived from capabilities and requirements; it's not maintained
as another list of hardcoded names.

### Phase C — First integrated set

Integrate a few different capabilities, not many equivalent components. Good
candidates for learning about the boundary are:

- `Hotspot`, for spatial representation and accessible alternative;
- matching/categorize, for manipulation and scoring;
- `NumericQuestion`, for quantitative validation;
- `InteractiveMedia`, for composition, transcript, and checkpoints;
- generative practice or self-explanation, for evidence different from a choice test.

The final selection depends on the adapter confirming its real requirements; this list
is not an implementation commitment.

### Phase D — Bounded resolution

- Resolve candidates from mission, representation, action, requirements, and evidence.
- Deliver at most 3–5 candidates to the producer.
- Log filters, ranking, `Declined`, and fallback in `PlanTrace`.
- Add catalog and component version to the cache.

### Phase E — Evals and replacement

- Golden specs of props and events between the legacy block and Didact.
- Keyboard, screen reader, reduced motion, and drag-alternative tests.
- Critical facts and evidence preserved from pack to reachable UI.
- A/B by objective and profile, not just type count.
- Retire the legacy block only after equivalence or proven improvement.

### Phase F — Level-3 pilot

- Choose a declarative platform with its own state and feedback.
- Create two recipes from different domains.
- Generate configurations, never code.
- Measure first-try validity, reachable states, evidence, latency, cost, and transfer.
- Keep a fallback to a level-2 experience when data or infrastructure is missing.

## 7. Metrics that avoid optimizing for empty variety

Per render:

- invariant and safety coverage;
- evidence actually obtainable;
- candidate requested, chosen, and fallback reason;
- component and version;
- reachable affordances, states, and events;
- first-attempt validity and repairs;
- latency, tokens, and cost;
- accessibility and operability;
- diversity across equivalent objectives, not within a single screen.

Per catalog addition:

- number of core edits needed;
- percentage of nodes where it turns out compatible;
- selection rate when it's a candidate;
- `Declined` rate and reasons;
- overlap with existing components;
- learning or evidence improvement versus the fallback.

The architecture will have worked when adding a component consists of publishing its
manifest, adapting it, and testing it, without modifying detectors, global prompts, or
central assemblers.

## 8. Next continuation point

The next session should start with an executable Didact → SkillNet inventory, not by
copying visual components. The initial deliverable is:

1. versioned export of available manifests;
2. pure adapter to `ComponentDescriptor`;
3. derived `FIT/BLOCKED/DECLINED` matrix;
4. shortlist of one component per new capability;
5. fixtures demonstrating resolution without showing the model the full catalog.

Afterward the first real component is integrated and the raw/legacy/Didact bench is
repeated with the same traceable packs.
