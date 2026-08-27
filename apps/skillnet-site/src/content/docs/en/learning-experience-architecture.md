---
title: "Learning experience architecture"
order: 27
section: "core"
---

# Neutral architecture of learning experiences

**Date:** 2026-08-14  
**Status:** vertical slice implemented behind rollout

**Applies to:** dynamic v2 courses, experience selection and future providers

**Authority:** this document defines the boundary between persisted truth, episodic direction,
capability selection and render. [`v2-dynamic-courses.md`](/en/docs/dynamic-courses) keeps the
specification of the v2 path and the historical fallback; [`didact-integration.md`](/en/docs/didact-integration)
describes Didact's executable inventory.

The relationship between modality and internal structure is expanded in
[`delivery-modalities.md`](/en/docs/delivery-modalities). Audio and video are representations that can
live inside an experience; they are not navigation destinations or tabs the person has to choose.

## 1. Decision

The published course keeps its **constitution**: what competency matters, what source truth
backs it, what errors are critical and what evidence lets us claim mastery. It does not keep a
sequence of screens, a modality, a visual variant or a component as pedagogical truth.

The presentation is decided when the person opens the node. The server builds a grounded
`EpisodeBrief` adapted to their state; it then filters the catalog by capabilities and pins a
versioned implementation. The resulting output is anchored so a refresh does not change the
activity mid-attempt.

```text
published course
  CompetencyContract + SourceAffordanceMap + EvidenceGate
                           │
              person's current state
                           │
                           ▼
              EpisodeBrief on-the-fly
       (mission, action, evidence, limits, continuation)
                           │
                           ▼
        CapabilityBroker → honest shortlist of 1–3
                           │
                           ▼
       ExperienceResolver → binding/definition pinned
                           │
                           ▼
             LearningExperience + shell_mode
                           │
                           ▼
       server-owned evidence → mastery → continuation
```

Didact is today's main educational provider, not SkillNet's ontology. `skillnet.text-content`
and `media.checkpoint-video` cross the same boundary. Adding a simulation or a code lab must not
modify the course contract, the episodic director or `LearningExperience`.

## 2. What is fixed and what is generated

| Fixed when the course is validated/published | Decided when the node is opened |
|---|---|
| Outcome, criticality and prerequisites | Concrete mission for this attempt |
| `CompetencyContract` and its version | `EpisodeBrief` and budget |
| Required facts and provenance | Dominant action and amount of support |
| `SourceAffordanceMap`, revisions and digests | Representation suited to the task and context |
| `EvidenceGate`, private oracles and critical errors | Shortlist of available capabilities |
| Mastery policy | Binding and definition pinned for the render |
| Versioned catalog and security policies | `shell_mode` and continuation conditions |

Videos, games, alternative sequences, pedagogical baselines or speculative presentation
artifacts are not pre-created for each course. Knowledge packs, affordance maps, indexes and
oracles are not "course content already assembled": they are the reproducible truth and the
limits from which the runtime can generate without inventing.

`node_renders` persists the validated result that was actually served, for cost, auditing and
reproducibility purposes. That cache is the consequence of a runtime decision, not a
presentation plan prepared during publication.

### 2.1 Anticipatory generation during the session

"On-the-fly" describes **when** the experience is decided, it does not force waiting with an
empty screen. The decision still uses the current constitution, the learner's state and the
runtime policy, but it can run a few steps before the person opens the lesson:

1. when the course map is opened, the client requests the first two available lessons in the
   background;
2. once a lesson already has a served render, the client keeps a moving window with the next
   three lessons requested;
3. as the learner advances, the window shifts and prepares the new lesson coming up ahead;
4. repeated requests are idempotent: a render that is ready or in progress does not start
   another generation;
5. opening a lesson fixes its render, so refreshing, answering or going back does not silently
   change what the person was looking at.

This does **not** make the course static nor mix presentation artifacts with its definition.
These are anticipated, cached runtime renders. The full course is not generated, all branches
are not chosen ahead of time, and invalidation still depends on versions, digests and
`generation_policy_key`. The window today uses lessons from the published path; once a
competency admits several internal episodes or probabilistic branches, the same rule must apply
to eligible continuations, not to fabricating every alternative.

## 3. Stable contracts

### 3.1 `CompetencyContract`

Defines the job outcome, mandatory facts, criticality, prerequisites, evidence gates, critical
errors and `mastery_policy_ref`. It does not admit provider, component, slot or layout. A change
from Timeline to video cannot change a safe procedure or lower the required evidence.

### 3.2 `SourceAffordanceMap`

Fixes the exact available sources and revisions, their digests and which actions they honestly
support: inspecting a procedure, recognizing a state, ordering steps or executing in a sandbox,
for example. An affordance can be exact, derived or synthetic, but it always references the
source that backs it. If the source does not allow an action, the generator must not simulate
that it does.

### 3.3 `EpisodeBrief`

It is a learning beat created on-the-fly and free of provider names. It contains:

- an exact reference to competency, grounding and the person's state;
- a mission with a single dominant action;
- authorized source and affordances;
- assessment mode and gates, if demonstrable;
- critical errors and recovery;
- content, interaction, media and latency budget;
- continuation conditions, including a default exit.

It does not contain `ScreenScheme`, `lead`, `concept`, `practice`, `component_id`, `provider` nor
layout instructions. Explanation, practice and transfer remain possible resources, not a recipe
that must always appear or appear in that order. The coherent unit is the complete mission: it
can span a vertical scroll and contain several pieces if all of them serve the same dominant
action.

## 4. Tickets and SQL are not the same experience

The abstraction exists precisely to allow radical differences without creating two platforms.

| | Retrieve tickets | SQL |
|---|---|---|
| Job outcome | Attend to a customer and retrieve the correct ticket without exposing or confusing data | Build or fix a query that produces the requested result |
| Source truth | Current provider manual, visible fields, exceptions and process limits | Schema, test data, dialect and execution constraints |
| Plausible dominant action | Diagnose the case and choose/execute the next operational step | Write, run and debug a query |
| Required affordance | Faithful operational case, search, states and process decisions | Executable editor and sandbox with resettable state |
| Valid evidence | Correct decision and sequence, including handling of critical errors | Executed result, tests and explanation of the failure |
| Resulting experience | Guided case or attention simulation with pinpoint reference to the manual | Code lab with engine feedback and test cases |

A quiz can serve as a limited check in both domains, but it does not replace operational
transfer or execution. The broker must decline rather than present a low-fidelity imitation as
evidence of mastery.

## 5. Broad catalog, small context

Each implementation publishes a versioned `CapabilityDescriptor`, framework-neutral: learner
actions, producible evidence, affordances, accessibility, security, ports, latency and quality.
The full catalog can grow without entering entirely into the prompt or the browser's initial
bundle.

At runtime, `CapabilityBroker` applies hard gates in this conceptual order:

1. learner action;
2. required evidence;
3. real affordances of the source;
4. accessibility;
5. security;
6. available ports;
7. latency budget.

Only afterward does it rank the valid candidates deterministically. It returns an honest
shortlist of one to three; it does not pad the minimum with worse options. If none survives, it
can widen the catalog once, applying exactly the same gates. If there is still no valid option,
it returns `Declined(reason)`.

The broker filters **capabilities**. `ExperienceResolver` then takes that list and pins a
published binding (`experience_id`, `implementation_ref`, `definition_ref`). This separation
prevents the pedagogical policy from knowing provider details. On the frontend,
`ExperienceAdapterRegistry` lazily loads the adapter by `implementation_ref`; `LearningExperience`
does not contain a central `switch` nor static imports of the whole catalog.

## 6. Evidence, support and mastery

The evaluation authority is the server. Answer keys, oracles and rubrics remain in the private
definition. An evaluable implementation sends a stable attempt tied to `experience_id`; the
server validates the binding and translates the result into normalized evidence before applying
the mastery policy.

Writing an attempt, evidence and mastery must be idempotent and transactional. The client never
writes score, outcome or mastery. Playback, click, dwell time and media completion are usage
signals, not learning evidence.

`support_only` is an honest output when there is grounded material to help but no certified
capability to produce the required evidence. In that mode:

- the `EpisodeBrief` uses `assessment_mode: none` and does not reference `EvidenceGate`;
- the person may receive an explanation, example or operational reference;
- no event updates mastery or satisfies a gate;
- the continuation cannot declare the competency mastered.

Turning that support into evidence requires another evaluable experience, with a port, binding
and server-owned oracle. Adding a "completed" button or a playback checkpoint is not enough. A
competency without a wired oracle is never synthesized: it does not grant mastery and does not
turn into an invented quiz; it declines toward `support_only` (with grounded material) or toward
an explicit decline.

### 6.0 Grounding requirement: the knowledge pack

The grounded episodic shell **requires** a `node_knowledge_packs` in `READY` state for the node,
with the current `schema_version` and `generator_version`. Without it, `direct_episode` declines
with `missing_knowledge_pack` and the node falls back to `legacy_stepper`: this is the underlying
reason why a freshly seeded or merely validated course never reaches the episode.

Packs are produced **only** by the LLM-backed runner (`run_packs_for_schema`), and it is only
triggered from the schema generation agent and from `PUT /{course_id}/schema`. **Neither seeding
nor `POST /schema/validate` create packs.** That is why the public seed (`seed_learning_demo`,
via the `create_course_end_to_end` orchestrator) runs that same runner after validating each
course when a real generation LLM is configured: this way a seeded course is capable of
end-to-end episode delivery. With the `fixture/local` model there is nothing to ground, so the
step is skipped —the runtime stays on `legacy_stepper`, without breaking—. The runner is
fail-open: a missing pack degrades to legacy, it never brings down generation or seeding.

Operational consequence for the demo: a course must go through generation/`PUT /schema` (or
through LLM-backed seeding) to have `READY` packs; turning on `ADAPTIVE_EPISODES` alone is not
enough —it only enables the branch that later declines if there is no pack—.

### 6.1 Decline reason, preserved and server-only

When the episode declines or degrades, the exact policy code is frozen in the render's
server-only provenance (`GenerationProvenance.episode_decline_reason`, alongside `shell_mode` and
`episode_status`). This way a `declined + legacy_stepper` render stops being an opaque symptom:
the reason —`evidence_policy:pack_not_ready`, `critical_oracle_unavailable`,
`missing_knowledge_pack`…— stays inspectable in traces and tests. It is a policy identifier, not
learner data, and like all of `UISpec.generation` it is excluded from dumps toward the client. A
decline is a safe fallback for a real failure, not an excuse to reduce the formula to
lead/concept/practice: the "oracle unavailable / unsupported" reasons keep the episodic shell as
`support_only`; only a real generation failure falls to `legacy_stepper`.

### 6.2 The job profile only enters if the source backs it

The learner's job and sector **do not** enter the generative prompt unless the source itself
backs them. The check is structural (`_profile_is_grounded` in `llm/prompts/runtime.py`): it
tokenizes the job/sector and only injects them if either appears in the source text. When it
does not —a retail profile over a boxing source— the job is **omitted entirely**, not marked
"undeclared": without a role to hang the examples on, the model cannot invent "a customer walks
up…" in a course that is not about customer service. There is no domain list; the profile only
adjusts difficulty, support and examples that are **compatible**, and the source and node always
prevail. The `role_bucket` keeps partitioning the cache even when the role does not enter the
text (bounded waste, never a wrong cross-match).

## 7. Episodic shell and modalities

`shell_mode` is a server-owned decision persisted with the render:

- `episode`: shows a coherent mission in a single vertical flow. It does not group by
  "resolvable" components, it does not create slides and it does not introduce a second scroll
  inside the content.
- `legacy_stepper`: keeps exactly the historical navigation for older renders and for the
  rollout fallback.

The browser does not infer the shell from component names, provider, block order or the
presence of a quiz. A refresh returns the same render and the same fixed `shell_mode`.

Audio and video are embedded wherever the mission needs them. There are no Web/Audio/Video tabs
nor three parallel versions of the same screen. Declared preferences, bandwidth, accessibility
and observed effectiveness are selection signals, never a rigid taxonomy of "learning styles".
Video does not autoplay and requires subtitles or a transcript; audio needs controls, a
transcript and an accessible alternative.

Continuation belongs to the episode and its evidence, not to the scroll position. A mission can
continue to additional practice, recovery, the next state or human review depending on its
conditions; the shell only presents that decision.

### 7.1 Multi-screen episode, content vs. evaluation, critic and pre-warm

**Multi-screen.** An episode is no longer ONE screen. Each **direct child of the root Stack is
a SCREEN** the learner steps through one by one (frontend pagination, no scroll)
(`llm/prompts/runtime.py`, version note `episode/3`, and the `_EPISODE_MULTISCREEN` block). The
natural ceiling is the validator's cap: `MAX_ROOT_CHILDREN = 5` (`render/spec.py`). The first
child is always a `TextContent variant="lead"` (rule 7 of `spec.py`). Focus rule: **A SINGLE
FOCUS PER SCREEN** —one idea, OR a set of definitions, OR an interaction, never all three. A
simple node is one screen; a rich one is several. The deterministic schema planner
(`agents/runtime/screen_scheme.py`) distributes three lead/concept/practice slots, and the
concept block takes shape from the material (`Table`, `Chart`, `StepSequence`, `BeforeAfter`),
never prose. Catalog-agnostic post-hoc evaluation lives in `agents/runtime/screen_eval.py`.

**Content vs. evaluation.** The most important distinction in the prompt
(`_EPISODE_QUALITY_RULES`, `runtime.py`): CONTENT/RESOURCE teaches or helps study (`TextContent`,
`Table`, `BeforeAfter`, `DidactTimeline`, and also `Flashcard`) and **never** certifies;
EVALUATION/TEST is a real check (`QuizItem`, `DragOrder` or a server-side experience). A content
block used as a test is an error even if the schema validates. The `agents/runtime/assessment.py`
planner picks the closing test with a deterministic rotation (`DIDACT_CLOSER_ROTATION`);
`Flashcard` was retired as a closer on 2026-08-17 because it turned every "evaluation" into a
simple *reveal*.

**Certification vs. `support_only`.** The policy lives in
`src/services/evidence_contract_policy.py`. It is only **certified** (accept,
`evidence_type="grounded_fact_recognition"` with `oracle_ref`) for a `RECOGNIZE` mission whose
atoms are all in `{FACT, PROCEDURE_STEP, CRITERION}`, backed by a real deterministic scorer
(`_UNSCORABLE` guard). Otherwise the node **declines to `support_only`** with a typed reason
(`CRITICAL_ORACLE_UNAVAILABLE`, `EXECUTION_ORACLE_UNAVAILABLE`, `RUBRIC_ORACLE_UNAVAILABLE`,
`REQUIRED_EVIDENCE_UNSUPPORTED`). The projection guard in `src/services/episode_inputs.py` is
fail-closed: a `critical` node without safety atoms is downgraded to `recommended` instead of
dying, and evidence gates require a server-owned `oracle_ref` + `evidence_type` or they decline
(`MISSING_REQUIRED_EVIDENCE`). The provenance state is
`episode_status ∈ {ready, support_only, declined, not_requested}` (`render/spec.py`).

**Lean generator + critic.** With `MULTI_AGENT_RENDER`, the episode is composed by specialized
agents (`agents/runtime/agents/`): `blueprint` (decides the screen structure without writing
content; "the CONCEPT block is always interactive or structured, NEVER prose"), `content_writer`,
`interaction_designer` and `assembler` (plain Python, no LLM; forces the server-owned
`LearningExperience` into the root's last child). The **critic**
(`agents/runtime/agents/episode_critic.py`) does *one* review of an episode that is **already
valid** (pedagogy, not syntax): a single focus per screen, content vs. evaluation kept separate
(flags a flashcard/reveal used as a test and any `DidactGlossary`), fit between component and
material, evaluation variety and a sensible number of screens. It is fail-open (`_MAX_NOTES = 4`,
any error → no review).

**Pre-warm on validate.** A validated course is servable, but its renders do not exist yet.
After `validate` (`routes/course_schema.py`), `spawn_prewarm_first_nodes`
(`services/node_render_service.py`) is launched, which warms the **shared** renders of the first
nodes in the background (with a synthetic default-bucket learner that never pins) so that the
first opening is an instant cache hit. It is superseded per course
(`cancel_by_prefix(f"prewarm:{course_id}:")`) and waits for the packs to be ready
(`_PREWARM_PACK_WAIT_SECONDS = 300.0`).

## 8. Compatibility and rollout

`ScreenScheme` and the historical screen formula remain solely as a rollout fallback. They are
used when `ADAPTIVE_EPISODES` is disabled, when the episodic director declines, or when serving
an already-pinned legacy render. They do not constrain the episodic prompt, they are not
projected inside `EpisodeBrief`, and they are not the product model for new courses.

The safe chain is:

1. grounded episode with certified capability;
2. `support_only` episode when it can help without asserting evidence;
3. explicit decline toward the `legacy_stepper` path during rollout;
4. visible and traceable error if no safe fallback exists either.

`DidactActivity` is kept as a read alias for historical publications. New renders cross
`LearningExperience`; adapters or legacy data are not removed while active references exist.
Incompatible versions and digests invalidate the cache and require explicit regeneration or
migration.

## 9. Simulations and level-3 GenUI

The registry already admits future providers, but registering a name does not create a real
capability. A level-3 simulation or experience is only enabled when it provides:

- deterministic state model, transitions and invariants;
- explicit simulation or execution port;
- reproducible reset and isolation between attempts;
- server-owned oracle and translation to evidence;
- declared fidelity relative to the source and the work environment;
- accessible alternative and safe behavior on failure;
- met latency budget and honest fallback.

The generator selects recipes and typed definitions; it does not generate free executable code
inside the OpenUI program. The first pilot must demonstrate at least one operational case such as
an incident-management tool and another executable one such as SQL. If both require editing the
core contract, the abstraction is not yet sufficient.

## 10. Rollout validation checklist

### Docker and backend

- Rebuild the stack with `docker compose up -d --build` and confirm that API, web and database
  are healthy.
- Enable `ADAPTIVE_EPISODES` only in the intended test environment and verify that the policy
  version separates legacy and episodic cache keys.
- Use a validated dynamic course with a `ready` knowledge pack, current sources and a node that
  does not yet have a pinned render.
- Confirm in the `GET /nodes/{id}/render` response that `shell_mode` is `episode` and that the
  render gets anchored; a second GET must return the same identity.
- Test `ready`, `support_only` and decline to legacy separately. In `support_only`, check that no
  evidence is created and mastery does not change.

### Fresh node

- Validate with a new or explicitly regenerated node. A node with a previous `active_render_id`
  must keep serving its pinned version and does not demonstrate the new rollout.
- Cover at least one operational-manual case and one SQL/code case; their actions, affordances
  and chosen components must be materially different.
- Confirm that facts, source revision, gates, critical errors and binding appear in the
  server-side trace without exposing private oracles to the client.
- Force a missing port or missing evidence and check `support_only`/`Declined`, never a
  simulation or a faked evaluation.

### Browser

- Open the episodic node on desktop and mobile viewport: one mission, one vertical page scroll,
  no Web/Audio/Video tabs, no slides and no nested content scroll.
- Check keyboard navigation, visible focus, screen reader, contrast and reduced-motion
  preference.
- For video/audio, verify absence of autoplay, controls, subtitles or transcript and an
  accessible alternative.
- Reload and go back/forward: identity, content and `shell_mode` must remain stable.
- Open a `legacy_stepper` render and confirm its historical navigation has not changed.
- Run an evaluable evidence submission twice with the same `attempt_id`: it must be idempotent.
  Repeat with a `support_only` experience: mastery must stay the same.

## 11. Success criteria

The abstraction is sufficient when:

- the course fixes truth and evidence, not a pre-created presentation;
- Tickets and SQL produce radically different episodes from the same runtime contract;
- the catalog can grow without enlarging the prompt or modifying the core;
- a shortlist can contain a single valid candidate or decline with an observable reason;
- every mastery update comes from server-owned evidence;
- `support_only` helps without certifying;
- `shell_mode` does not depend on browser heuristics;
- audio and video are part of the mission, not of a navigation across modalities;
- `ScreenScheme` can be retired once rollout ends without changing `EpisodeBrief` or the
  bindings;
- a future simulation enters via descriptor, ports, definition, adapter and tests, not via a
  special branch in the planner.

## 12. Relationship to other documents

- [`v2-dynamic-courses.md`](/en/docs/dynamic-courses) defines v2 delivery, persistence, cache and
  mastery transition. Its screen recipes describe the `legacy_stepper` fallback.
- [`node-knowledge-packs.md`](/en/docs/node-knowledge-packs) defines the preparation of source truth
  that feeds `SourceAffordanceMap`.
- [`delivery-modalities.md`](/en/docs/delivery-modalities) defines modality as an affordance and
  selection signal, not as a tab.
- [`didact-integration.md`](/en/docs/didact-integration) lists the Didact provider's real components,
  ports and blockers.
- [`didact-integration-strategy.md`](/en/docs/didact-integration-strategy) develops level-3 recipes and
  GenUI.
- [`openui-adoption.md`](/en/docs/openui-adoption) keeps the dialect, security and renderer
  constraints.
