---
title: "Didact components"
order: 46
section: "extensibility"
---

# Didact component catalog and gaps

**Status:** pinned v1 catalog (34 declared types, 6 blocked)
**Sources of truth:**
`apps/skillnet-api/src/personalization/didact_component_registry.v1.json` (host
integration delta),
`apps/skillnet-api/src/personalization/didact_snapshot.json` (provider inventory),
`apps/skillnet-api/src/render/kit.py` (the UI Kit known to the validator and the prompt).
**Related:** [`didact-integration.md`](didact-integration.md),
[`extensibility.md`](extensibility.md),
[`learning-experience-architecture.md`](learning-experience-architecture.md)

> This document inventories **what components exist today**, which ones are **blocked**,
> and what **pedagogically valuable types are missing**, with a prioritized list of
> recommendations. It doesn't implement anything: it's catalog + audit.

## 1. Two catalogs, one boundary

SkillNet maintains two complementary views over learning components:

- **The Didact availability registry** (`didact_component_registry.v1.json` +
  `didact_catalog.py`) answers *what's installed and what the host can run now*. Each
  type declares: `renderer_mode` (`direct` / `activity_definition` / `blocked`), `emission`
  (`enabled` / `disabled`), `authoring_strategy` (`inline` / `server_activity` /
  `unsupported`), and the `required_ports`. Pedagogical identity comes from the
  provider's authoritative snapshot (`available_types`, 34 types).
- **The UI Kit** (`render/kit.py`) is the source of truth for **validation**: component
  names, exact props, closed enums, and the positional order of the OpenUI dialect the
  LLM emits. `render/spec.py` enforces it.

The host ports SkillNet offers today are
`["assets", "clock", "evaluation", "persistence", "progress"]`
(`didact_component_registry.v1.json`). A component that requires a port outside that
list — `scheduler`, `simulation`, `execution`, `events`, `media` — can't run even if
it's installed.

## 2. Current Didact catalog (34 types)

### 2.1 Enabled components with direct render (`inline`)

Inline authoring: the LLM emits them directly in the episode; render is native to SkillNet.

| Didact type | Renderer | Related kit component |
|---|---|---|
| `didact.flashcard` | `Flashcard` | `Flashcard` (active recall, not evaluated) |
| `didact.hint-reveal` | `HintReveal` | `HintReveal` (progressive hints) |
| `didact.timeline-steps` | `DidactTimeline` | `DidactTimeline` (chronological sequence) |
| `didact.worked-example` | `DidactWorkedExample` | `DidactWorkedExample` (reasoned solution) |

### 2.2 Enabled components as server activity (`server_activity`)

Rendered via `DidactActivity` loading a reviewed `ActivityDefinition` by id
(the program **never** contains answers). They require the listed ports.

| Family | Types | Ports |
|---|---|---|
| Choice questions | `quiz.single-choice`, `quiz.multi-select`, `quiz.true-false`, `quiz.fill-in-the-blank`, `quiz.short-answer` | `evaluation` |
| Match / order / classify | `matching`, `sort`, `categorize`, `word-bank` | `evaluation` |
| Numeric and symbolic | `numeric-question`, `equation-workbench`, `measurement-lab`, `completion-problem` | `evaluation` |
| Visual / spatial | `hotspot`, `label-diagram` | `assets`, `evaluation` |
| Learner construction | `concept-map`, `drawing-response`, `evidence-annotation` | `evaluation`, `persistence` |
| Data / media | `data-explorer` (no ports), `interactive-media` | `assets`, `persistence` |
| Metacognition / progress | `self-explanation-prompt` (`persistence`), `rubric` (`evaluation`), `progress` / `mastery-badge` (`progress`) | various |

### 2.3 BLOCKED components (`emission: disabled`, `renderer_mode: blocked`)

Six declared types that are **not runnable** today. They split by *cause* of the block:

| Type | Reason for block | Pedagogical value |
|---|---|---|
| `didact.retrieval-practice-session` | Missing `scheduler` port (plus `persistence`) | **High** — spaced recall, long-term retention |
| `didact.simulation-lab` | Missing `simulation` port | **High** — adjustable quantitative systems, operations |
| `didact.code-exercise` | Missing `execution` port (plus `evaluation`) | **High** — executable practice (SQL, scripting, technical) |
| `didact.branching-scenario` | **Requires no ports**; missing authoring/renderer in SkillNet | **High** — consequential decisions, onboarding/compliance |
| `didact.practice-set` | Requires only `evaluation` (available); missing authoring | Medium — composes standalone activities into a bounded session |
| `didact.glossary-term` | Replaced by the kit's own `DidactGlossary` component | Low — already covered (and the critic discourages it as a closer) |

Important observation: `branching-scenario` and `practice-set` are **not blocked for
lack of ports** — the ports they ask for either already exist or none are required —
but because SkillNet hasn't yet built their authoring/renderer strategy. They are the
unlocks with the lowest technical cost.

## 3. SkillNet's own UI Kit (`render/kit.py`)

Beyond Didact, the kit includes **content** and **experience** components that the LLM
composes in the episode. The ones relevant to this audit:

- **Containers / content**: `Stack` (root), `Card`, `TextContent`, `Callout`,
  `StepSequence`, `Table`, `CodeBlock`, `Chart`, `BeforeAfter`, `Markdown` (fallback only).
- **Inline interaction / evaluation**: `QuizItem`, `DragOrder`, `Flashcard`, `HintReveal`,
  `DidactGlossary`, `DidactTimeline`, `DidactWorkedExample`.
- **Synthesized media**: `AudioExplanation`, `PronunciationExercise`, and the two
  **broker-scoped** `PodcastPlayer` / `InfographicImage` — real and validatable, but the
  generator only sees them when the media broker injects them per-node because a READY
  artifact exists and the learner's modality matches (see [`media-artifacts.md`](media-artifacts.md)).
- **Neutral boundary**: `LearningExperience` (opaque reference to a resolved experience;
  doesn't expose provider or answers) and `DidactActivity` (`llm_emittable=False`,
  `legacy_parseable=True`: loadable by id, historical playback).

Each component can claim *content functions* (`ENUMERATE`, `PROCEDURALIZE`,
`QUANTIFY`, `CONTRAST`, `VARY`, `EXPLORE`, `LOCATE`, `EVALUATE`); today only the first four
have a detector that emits them (`render/kit.py`, `shape.py`).

## 4. Gap audit (do we still need to add more?)

Two categories: **(A) unlock what's already declared** and **(B) genuinely missing types**.

### 4.1 (A) Unlock what's declared — highest immediate return

1. **`branching-scenario`** — *no port cost*. Branching decision scenarios with a
   serializable state graph. Covers a real need with no current component:
   practicing consequential decisions (compliance, customer service, procedural
   safety). Only the authoring/renderer strategy is missing. **Recommendation: first.**
2. **`retrieval-practice-session` (spaced recall)** — requires a `scheduler` port.
   SkillNet already has spaced repetition (HLR) at the course level; it's missing as an
   in-episode component for recall within a lesson. **High retention value.**
3. **`code-exercise` (sandbox)** — requires an `execution` port (a sandboxed execution
   adapter). Would enable the entire `technical-training` collection (SQL, scripting).
   High cost (isolation/security) but it's the key lever for technical courses.
4. **`simulation-lab`** — requires a `simulation` port. Adjustable quantitative systems
   (parameters, observables, deterministic steps). High value for math, science, and
   operations.
5. **`practice-set`** — `evaluation` port already available; only authoring is missing.
   Composes standalone activities into a bounded session with review. Low cost, medium
   value.

### 4.2 (B) Pedagogical types genuinely absent from the catalog

Judged against real learning needs, not a generic list:

1. **Socratic tutor / evaluated conversational dialogue** — SkillNet has chat, but no
   in-episode component that runs a practice conversation with a correctness oracle.
   Fits the `LearningExperience` boundary. **High value** for language, reasoning, and
   soft skills.
2. **Speech assessment / voice recording with oracle** — `PronunciationExercise` exists
   (front-end) but without real correction. A *speaking assessment* component (record →
   score) would close the language loop.
3. **Annotated media with checkpoints / timeline scrubber** — `interactive-media` is
   enabled as a server activity, but a *scrubber* over video/audio with embedded
   decision points and navigable transcript has no native render. Medium-high value for
   procedures and listening.
4. **Adaptive difficulty controller / mastery path** — today evaluation variety is
   deterministic rotation (`assessment.py`); a component that adjusts difficulty based on
   performance within the episode is missing.
5. **Interactive spreadsheet / data wrangling** — `data-explorer` covers graphical/tabular
   exploration but not spreadsheet-style manipulation (formulas, transformations).
6. **Collaborative annotation / peer response** — no multi-learner component exists;
   would require the `events` port. Low value for the current (individual) model, worth
   watching.

### 4.3 Prioritized recommendations (top)

| # | Action | Type | Why | Cost |
|---|---|---|---|---|
| 1 | Build `branching-scenario` authoring/renderer | Unlock | No port cost; fills a real pedagogical gap (decisions) | Low-medium |
| 2 | Expose spaced recall as `retrieval-practice-session` (`scheduler` port) | Unlock | Retention; reuses existing course-level HLR | Medium |
| 3 | Add an `execution` port for `code-exercise` | Unlock | Enables entire technical courses | High (secure sandbox) |
| 4 | Evaluated Socratic tutor over `LearningExperience` | New type | Conversational practice with oracle; fits the neutral boundary | Medium-high |
| 5 | `practice-set` (authoring, `evaluation` port already available) | Unlock | Composes the practice session; low cost | Low |
| 6 | `simulation-lab` (`simulation` port) | Unlock | Science/math/operations | High |

**One-line summary:** the highest short-term value isn't inventing new types, but
**unlocking what Didact already declares** — starting with `branching-scenario`, which
depends on no port — and then providing the three missing host ports (`scheduler`,
`execution`, `simulation`). The only truly new type with a clear return is the
**evaluated conversational tutor**.
