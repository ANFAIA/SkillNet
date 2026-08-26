---
title: "Functional component architecture"
order: 22
section: "core"
---

# Component architecture by function

**Date:** 2026-08-09
**Status:** proposal. Nothing here is implemented.
**Origin:** measurement from August 8-9 (`testing_cursos/INFORME.md`, `INFORME_GENERO.md`)
and research in `07_ANFAIA/investigacion/ui_innovadora/catalogo_y_abstraccion_componentes.md`.

---

## 1. The problem, with numbers

The kit has **22 emittable components**. Across 71 measured renders, **7** appear. The other 15
never appear — not once, across seven documents from four segments and three different genres.

What was ruled out by measurement, not opinion:

| Hypothesis | Verdict |
|---|---|
| The catalog is too large and the model gets lost | **False.** OpenUI advertises 53 signatures in 13 KB; A2UI, 18+14; Khan Perseus, 34 widgets. 22 in 8 KB isn't close to any ceiling |
| The veto on `Tabs`/`Card`/`Accordion` was holding them back | **False.** It was removed on 2026-08-09 (`c02427a`) and they still came out **zero** times |
| The model doesn't know how to use rich blocks | **False.** Given contrast content, it emitted `Table(["Situation","Result"], [...])` — a `BeforeAfter` written inside a `Table`. It understood the semantics and had nowhere to route it |
| The system ignores the document's genre | **False.** With non-procedural material, `StepSequence` dropped from 90% to 0% and `DragOrder` from 100% to 0% |

What remains standing, and is the cause:

**`shape.py` produces four signals and all of them name a concrete component**:
`enumeration`→`Table`, `labelled_list`→`Table`, `numeric_series`→`Table`, `procedure`→`StepSequence`.
On material that is neither a list nor a procedure, **the only block anyone can propose is
`Table`** — and in the genre test it appeared in 18 of 18 nodes.

Outside those four signals the model receives **no** discriminating signal at all. *The 99%
Success Paradox* (Meta, 2026-05) describes the regime: with K·R̄/N above 3-5, selectivity
collapses and the model **falls back on its priors** — concentration on the prototypical and a
permanently dead tail. With 22 components shown and 3-5 plausible per lesson, λ≈4.0. That is
exactly what was measured.

**Operational conclusion:** adding capacity without adding signal does nothing. It is proven in
this repository, with a commit and a measurement.

---

## 2. The structural cause: the cost of adding

Adding a new component today costs six edits:

| Edit | Nature |
|---|---|
| `kit.py` — validation | local, mechanical |
| React block | local, mechanical |
| Registration in the kit library | local, mechanical |
| Regenerate `openui_prompt.txt` | local, automatic |
| **`shape.py` — a signal that can name it** | **central** |
| **Blueprint prompt — a rule that routes toward it** | **central** |

The last two get more tangled with every component. Four signals for 22 components no longer
scale.

Hence the explanation for the 15 dead ones: **nobody decided no. Nobody paid the central edit.**
`BeforeAfter` is not turned off by design — reaching it meant touching the detector, and that
was never done.

With the cost of adding high, the catalog freezes on its own. That is the problem this
architecture solves; richness is the consequence, not the direct goal.

---

## 3. The central move

Introduce a **content function** layer between source analysis and component selection.

```
TODAY
  source ──> detectors (4) ──> ShapeSignal(block="Table") ──> hint ──> blueprint ──> component
                                            ▲
                                  the block's name is hardwired here

PROPOSED
  source ──> detectors ──┐
                          ├──> ContentFunction ──> registry ──> functional producer ──> component
            classifier ──┘                          ▲                    │
            (only if no                    each component            can DECLINE
             signal exists)                declares its functions
```

Three properties, each answering a measurement finding:

**The component declares what it is for.** It leaves `shape.py` and enters `ComponentSpec`.
Adding a component stops touching anything central: it becomes registration. *Answers §2.*

**The decision moves up a level.** The router chooses between 5-8 functions, not between 22
components. "Does this content contrast two states, enumerate, describe a procedure, or explore
a variable?" is a semantic question about the text — something a language model does well.
"`BeforeAfter` or a two-column `Table`?" is a UI question it has no criteria for, and today it
always answers `Table`. *Answers §1.*

**Each decision's λ goes down.** The comparison agent shows 4 components with 2 plausible: λ≈2,
outside the collapse regime. Without trimming the total catalog. *Answers the Meta paper.*

---

## 4. Design decisions

### 4.1 The partition axis is function, not domain

A comparison agent serves restaurants, retail, admin services, and clinics alike. Partitioning
by domain multiplies agents that do the same thing.

Domain enters **afterward**, as a label that filters the catalog within each functional agent.
This way an algebra component never competes in a cooking course, and the total catalog can grow
to 200 without any single decision seeing more than a dozen.

### 4.2 `shape.py`'s asymmetry is preserved

The module states it literally:

> *"a missed hint costs nothing (the prompt falls back to what it says today), while a hint the
> material cannot support sends the model to invent rows."*

That asymmetry is a system invariant, not a detail. Every threshold in `shape.py` is calibrated
against a real failure documented in its comments. **The new semantic classifier inherits the
same rule: when in doubt, emit no function.**

### 4.3 Two classification speeds

Deterministic detectors **stay where they are correct**. They are fast, free, and were written
because the model failed at enumerations.

The semantic classifier kicks in **only when the detectors produce no signal at all** — which is
exactly the material that today falls into `Table` by default, and where the 15 dead components
are.

Cost: one short call, only on nodes without a signal. It does not touch the path that already
works.

### 4.4 The producer can decline

A producer returns the component **or** `Declined(reason)`. The planner moves down the ordered
list of candidates for that function.

Without this, expanding the catalog produces forced blocks instead of better lessons — and with
interactive components it's worse than with text: a `SliderExploration` needs a **relationship**
between variable and effect that the client's document almost never states. If the producer
cannot refuse, it invents one. Block C already measured a **32% rate of invented content with
poor sources, including fabricated figures**; with interactive components that stops being a
wrong data point and becomes a learner playing with a fake model.

**The rejection path is what makes rich components safe.** It is not architectural elegance.

### 4.5 The descriptor carries cost, not just purpose

`ComponentSpec` gains fields:

```python
@dataclass(frozen=True)
class ComponentSpec:
    name: str
    purpose: str                          # already exists
    props: tuple[PropSpec, ...]           # already exists
    is_container: bool = False            # already exists
    llm_emittable: bool = True            # already exists
    # new
    functions: tuple[ContentFunction, ...] = ()   # which functions it competes for
    when: str = ""                        # usage hint, OpenUI-style
    requires: tuple[Requirement, ...] = () # e.g. IMAGE_URL, NUMERIC_RELATION
    cost: Cost = Cost.FREE                # FREE | LLM | SLOW | PAID
    domains: tuple[str, ...] = ()         # empty = all
```

`cost` is what lets a self-hosted SMB deployment turn off expensive producers without breaking
anything. `requires` is what prevents proposing `HotspotImage` when there is no image pipeline
behind it.

---

## 5. The content functions

Starting point, to be validated with phase 3 measurement:

| Function | What it recognizes | Current candidates |
|---|---|---|
| `ENUMERAR` (enumerate) | a set of items with no causal order | `Table` (1-2 col), `Card` |
| `PROCEDIMENTAR` (proceduralize) | ordered steps | `StepSequence`, `StepByStepReveal`, `DiagramBuilder` |
| `CONTRASTAR` (contrast) | two states, right/wrong, before/after | `BeforeAfter`, `Table` (2 col), `Callout` |
| `VARIAR` (vary) | same process with case-based variants | `Tabs`, `Accordion` |
| `CUANTIFICAR` (quantify) | comparable figures | `Chart`, `Table` |
| `EXPLORAR` (explore) | relationship between variable and effect | `SliderExploration`, `ManipulableGraph` |
| `LOCALIZAR` (locate) | parts of an object or space | `HotspotImage` |
| `EVALUAR` (evaluate) | learning verification | `QuizItem`, `DragOrder` |

The four current signals map without loss: `enumeration`/`labelled_list`→`ENUMERAR`,
`numeric_series`→`CUANTIFICAR`, `procedure`→`PROCEDIMENTAR`. **The migration starts out
equivalent to what exists**, which is what makes it safe.

`CONTRASTAR`, `VARIAR`, `EXPLORAR`, and `LOCALIZAR` are the four that don't exist today — and
they cover exactly the dead blocks.

---

## 6. Phases, each separately measurable

Uses the harness already built: `testing_cursos/driver.py`, `bloque_a.py`, `comparar_v14_v15.py`.
The baseline is in `datos/manifest_bloqueA_v14_baseline.json`.

### Phase 0 — Fix the misplaced rule *(1 line)*

In `blueprint.py`, the only rule that mentions the right/wrong case is written in the **VERIFICAR**
slot section, where `BeforeAfter` is illegal (that slot only allows `QuizItem`/`DragOrder`, and
fifteen lines below: "NO EXCEPTIONS"). The rule is unreachable by construction. Move it to the
CONCEPTO slot.

**Measure:** does `BeforeAfter` ever appear? **Cost:** one line and a `PROMPT_VERSION` bump.

### Phase 1 — Descriptors *(without touching architecture)*

Rewrite `kit.py`'s one-line `purpose` fields as real usage hints, OpenUI-prompt style
(*"prefer it when labels are long"*, *"use it when the content contrasts two states"*).

It's the only lever in the report backed by numbers: Trace-Free+ (Intuit, 2026-04) measures
**−29.23% degradation and +60.89% per-query success** with 150+ tools, just by changing
descriptions.

**Measure:** block distribution against baseline. **Success criterion:** at least 3 of the 15
dead ones appear. **If none appear**, description-based signal isn't enough for this model and
phase 4 (classifier) moves up in priority.

### Phase 2 — The registry

`ComponentSpec` gains `functions`, `when`, `requires`, `cost`, `domains`. Write
`registry.candidates_for(function, domain, budget)`.

`shape.py` stops naming blocks: its signals now emit `ContentFunction`. The function→components
mapping lives in the registry.

**Measure:** the distribution must not change. This is an equivalence refactor; if it changes,
something broke. **And the real metric:** how much it costs to add component number 23 after
this. If it still requires touching `shape.py`, the phase failed.

### Phase 3 — New functions via detector

Add deterministic detectors for `CONTRASTAR` and `VARIAR` where the text allows it (markers like
"instead", "never … always", "depending on the type of"). Same asymmetry: when in doubt, emit
nothing.

**Measure:** do `BeforeAfter`, `Tabs`, `Card` appear?

### Phase 4 — Semantic classifier for the rest

Only on nodes where detectors produce no signal. A short call that returns a function or `none`.

**Measure:** coverage (what % of signal-less nodes get one), accuracy against a hand-labeled test
bank, and the latency/cost delta. **This is a classification problem over a small label set: it
can actually be evaluated**, unlike "generate good lessons."

### Phase 5 — Functional producers with a rejection path

One producer per function, each with its reduced catalog. Returns a component or `Declined`.

**Measure:** rejection rate per function and what happens next. A producer that never declines is
suspicious; one that always declines is misrouted.

### Phase 6 — Domain scoping

`domains` stops being empty. The total catalog can grow without any single decision seeing more
than a dozen candidates.

---

## 7. What this architecture does NOT touch

- **The `Chart` guard** (`shape.py:500-522`). It forbids charts on `critical` nodes and on
  sources without figures, with the reason written right next to it: *"the source has no
  representable figures and a chart would have to invent them"*. It exists to prevent block C's
  problem. It stays.
- **Deterministic detectors where they are correct.** Every threshold is calibrated against a
  real failure.
- **Reactivity.** The non-negotiable conditions in §6 of `openui-adoption.md` remain in force and
  this doesn't touch them: there is no `Mutation` or `Query` here.
- **`SandboxHTML`.** See §8.
- **The current parallelism** of Content Writer and Interaction Designer. Latency today is 3.8 s
  per render, and there is sliding-window pre-generation (§4.2 of `multi-agent-pipeline.md`): the
  learner never waits. **This architecture is not justified by speed.**

---

## 8. On generating components on the fly

The slot is already reserved: `UiFormat.SIMULATION` exists in `models/node_render.py:55` marked
*"reserved and never emitted"*, and `nivel3_openui.md` designs the entire path.

The research supplies the mechanism that makes it viable, and it's not the one assumed:

> A component can be generated in full and still be deterministically validatable **exactly to
> the extent that its parameter space is total.**

Brilliant's promise of configurations *"guaranteed to be correct, solvable and meaningful"* does
not describe a validator: it describes an **API with no invalid configurations**. And Brilliant
does not hand-write the content — it generates 1,000+ problems with an LLM; its jump from 0% to
93% on one puzzle type came from redesigning the engine to be *LLM-friendly*.

Consequence for this architecture: the path to on-the-fly generation **is not a free HTML
sandbox**, it is designing components whose parameter space admits no invalid states. That is a
requirement on `ComponentSpec`, and it fits here naturally — but it is work for after phase 5,
and only makes sense once the rejection path is working.

---

## 9. Honest risk

**Nobody does this.** The report says so without ambiguity: in Vercel AI SDK, Tambo, OpenAI Apps
SDK, and MCP Apps the decision *is* the tool call and the props *are* its arguments. OpenUI,
LangChain, A2UI, and Thesys emit the tree directly. The only prior step documented in the
industry is **retrieval**, not classification — and `shape.py` is already that.

Also: **there is no public benchmark between 10 and 30 options** (everything starts at ~50
tools), and **the dead-components phenomenon is not described anywhere**.

This can be read two ways and both are true. It is original ground — proprietary material for
ANFAIA — and it is ground with no net: there's no one to copy when something doesn't work.

The mitigation is in §6: small phases, each measurable with the harness that already exists, and
one — phase 2 — that must come out **identical** to the baseline. If a phase doesn't move its
metric, it reverts on its own: they are independent commits.

---

## 10. The metric that decides whether this worked

It's not "are the courses richer?", which always ends up in opinions.

It's **how much it costs to add component number 30**. Today it's six edits, two of them
central. If after phase 2 it's four and all local, the architecture worked. If `shape.py` still
needs touching, it didn't.

That figure gets measured the first time one is added.

---

## 11. Boundary with the external component library

The visual catalog is being developed as an independent library and will gradually replace the
current components. SkillNet must not duplicate its implementation nor couple its pedagogical
reasoning to concrete React components.

The boundary is:

- **The library owns** the props schema, rendering, interactive states, accessibility, and
  versioning of each component.
- **SkillNet owns** the pedagogical function, usage conditions, evidence requirements,
  selection, cost policy, and interpretation of learning events.
- **The shared versioned descriptor** connects both sides via a stable `component_id`,
  `props_schema`, presentation capabilities, requirements, events, and pedagogical metadata.

During the migration, old adapters and library components will coexist. Each replacement must
pass golden specs for structure, accessibility, and events before the local block is retired; the
component's name must not be hardwired again into central detectors. The full contract and its
relationship to QTI, H5P, and xAPI are described in
[`adaptive-learning.md`](/en/docs/adaptive-learning).

The continuation with Didact's real catalog — 24 current educational types, facet-based
resolution, candidate shortlists, recipes, and declarative molecules for level-3 GenUI — is
defined in [`didact-integration-strategy.md`](/en/docs/didact-integration-strategy).
