---
title: "Node knowledge packs"
order: 29
section: "core"
---

# Per-node pedagogical dossiers (`NodeKnowledgePack`)

## Decision

SkillNet keeps the course index/graph and adds an asynchronous per-node preparation step:

```text
documents → reviewable index → commit → structured pack + reviewable Markdown
                                      ↓ selection by profile and mission
                                      ↘ OpenUI on-the-fly
```

The pack is neither a canonical lesson nor a screen. It is an intermediate source of pedagogical
truth: mandatory facts, safety rules, procedure, cases, common errors, evidence that must be
obtained, known gaps, and bounded spaces where generation is actually allowed. OpenUI still
composes the experience for each context; when a `ready` pack exists, it adapts previously
reviewed material instead of inventing substance and form at the same time. If no pack exists, or
the selection declares a blocking gap, it automatically falls back to the current raw source.

The Markdown is a deterministic projection for humans. It is never re-parsed as authority: the
authority is the versioned JSON `node-knowledge-pack/1` stored in full alongside its hash.

## Implementation status

The vertical is integrated in the development environment:

1. `persist_schema` commits the index and closes its transaction.
2. It then launches `run_packs_for_schema`; a failure does not block `schema_ready` nor change
   the course.
3. The runner opens new sessions, caps concurrency at two nodes, and applies a 120 s timeout per
   node. It does not hold a database connection during model calls.
4. A first call extracts the dossier and a second reviews/corrects it. Both return JSON, use
   temperature zero, and have a maximum of 3,200 output tokens. It is asynchronous preparation:
   this budget is not added to the learner's wait time.
5. References, hashes, node identity, and provenance are installed by the program, not the model.
6. Pydantic rejects extra fields, nonexistent references, cycles, and incoherent packs.
7. The terminal write is conditioned on the claimed fingerprint. An old worker may finish, but
   cannot publish over a newer source.
8. `ready` and `review_required` are distinct states in PostgreSQL as well; a rejected dossier
   cannot appear ready due to a projection error.
9. Creating or modifying the schema automatically enqueues the preparation. Opening the screen
   does not start work. Each node shows, inside its own dropdown, only its actionable status, the
   gaps requiring review, and, when it exists, the readable pedagogical base; there is no global
   panel or manual generation button.
10. The runtime selects invariants and optional material through a closed vocabulary. The
    selection and the pack hash enter the cache key before the prompt is modified.

The `node_knowledge_packs` table keeps the Markdown, the full canonical payload, a compact view of
atoms, provenance, hashes, tokens, duration, and error. Previous snapshots move to `stale` and
remain available for auditing.

Only a `ready` pack can replace `source_context`. `review_required`, `failed`, absence of a pack,
or a `Declined` keep the raw path. If a pack changes between the cache lookup and the start of the
graph, generation is rejected so that raw content is never written under a pack key, or vice versa.

## Why a generic Markdown is not enough

A linear text fixes an explanation too early and pushes all variants to converge. A pack preserves
possibilities. For example, the same allergen rule can produce a table for visual reading, a
decision case for practice, or a detailed explanation, while every variant keeps the same critical
rule and its source.

Selection is deterministic: it always includes invariants and required evidence; filters optional
cases by mission, presentation, and accessibility; includes prerequisites; and returns `Declined`
if essential data is missing. It will never ask the model to fill a factual gap.

## Known evidence and cost

The control run with 72 equivalent plans produced exactly the same planning for raw and pack:
atomizing the same content does not, by itself, improve or flatten the result. The potential
advantage comes from the prior pedagogical work — cases, evidence, errors, and limits — not from
calling the format Markdown.

The current live raw baseline (nine renders with `gpt-4o-mini`) was p50 7.53 s, p95 10.75 s, and
632 average input tokens. Local planning and fingerprinting cost microseconds. Pack preparation
does add two calls per node, but it happens once at course creation and outside the learner's
wait; its tokens and duration are logged to compute the amortized cost.

The benchmark supports `--arm raw|pack|both`. The pack arm replaces only `source_context` after
`load_context`, keeps separate cold sessions, and reports hashes, atoms, context size, and UI
signature per arm. Offline mode already verifies compatibility; a live causal comparison requires
the same model, interleaved order, and 5–10 repetitions per cell.

## Gates applied to the runtime

The integration can run during development, but each individual pack only replaces the raw source
when it meets the structural gates:

- required evidence covered or explicit `Declined`;
- raw fallback when the pack is not `ready`;
- `pack_hash` and selection hash added to the cache key before affecting a screen;
- race test: a result from a stale source can never remain active;
- rich components resolved by capabilities, not hardcoded in the pack.

Factual coverage, quality versus raw, and variety across profiles remain bench metrics, not
responsibilities of the component catalog. The creation screen only exposes, per node, what is
needed to intervene; tokens, duration, hashes, and technical counts stay in observability.

The pack also does not depend on a specific component. It describes what must be learned and what
evidence is needed. The planner later resolves whether the catalog can materialize it as text,
table, image, simulation, or another capability. Adding an animation lab will enrich the
experience without changing the pack's factual contract.

## Result of the first real tuning pass

An 18-call matrix with `gpt-4o-mini` compared budgets of 1,200, 1,600, and 2,048 tokens for the
extractor and reviewer over box, allergens, and complaints. No configuration produced three usable
packs: coverage was 0/7, 2/7, and 7/7 respectively, and the last result lumped the entire procedure
into a single atom. All nine ended up `review_required`, so the fail-closed boundary prevented
incomplete material from reaching the runtime.

Raising the budget did not change the results. The problem is in the prompt contract: its semantic
examples were copied as content and the proposed evidence references were not connected to valid
atoms. Before another screen test, the current contract will be compared against a JSON Schema
without example values and with an explicit coverage/atomization phase. The reproducible report is
at
[`../evidencia-testing/2026-08-11/knowledge-pack-tuning/report.md`](../evidencia-testing/2026-08-11/knowledge-pack-tuning/report.md).

## Traceable gate adopted (`knowledge-pack/v3`)

Subsequent rounds turned coverage and provenance into verifiable properties. The source is
deterministically split into operational units; each atom declares its units and the program adds
a blocking gap if any remain unrepresented. Headings are not confused with facts, admitted
references are literally enumerated, and every `ready` pack requires evidence. An unknown
pedagogical category may degrade to `fact`, but the text or its source is never silently corrected
or reassigned.

With `gpt-4o-mini`, 3,200 tokens per pass, and two calls per node, the gate finished 3/3:

- box: 11 invariants, 100% of the seven gold facts, 35.77 s and about $0.00288;
- allergens: 9 invariants, 100%, 31.94 s and about $0.00249;
- complaints: 19 invariants, 100%, 62.46 s and about $0.00394.

Average preparation was about 43 s and $0.0031 per node. It is slower than extracting a weak
summary, but it happens once and avoids serving incomplete material. That is why the development
environment uses `knowledge-pack/v3`; the version bump prevents reusing older packs under the new
contract.

The first OpenUI A/B (box, three repetitions per arm) kept 3/3 renders passing on the first try.
The pack did not change the five component types, but it raised average visible factual coverage
from 19.0% to 28.6%, reduced input tokens from 616 to 600 and output tokens from 40 to 30; p50
latency was practically neutral (5.609 s raw versus 5.516 s pack). This is a favorable signal, not
definitive proof: `n=3` and the screen's absolute coverage is still low. The next bottleneck is
selecting invariants for a low-density screen, not adding more prose to the extractor.
