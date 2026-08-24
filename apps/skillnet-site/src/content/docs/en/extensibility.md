---
title: "Extensibility (MCP/A2A)"
order: 15
section: "extensibility"
---

# Extensibility: how to add a Didact component

**Status:** reference guide (real touch points in the code)
**Related:** [`didact-components.md`](didact-components.md),
[`didact-integration.md`](didact-integration.md), [`design-system.md`](design-system.md)

> A learning component doesn't live in a single place: it crosses the availability
> registry, the validator's UI Kit, the frontend kit (where the prompt comes from), and
> —if it evaluates— the evidence policy. This guide lists the **real** touch points with
> file:line, so adding a component is a local edit rather than a hunt.

## Overview: the four layers a component touches

```
1. Availability registry   didact_component_registry.v1.json   (installed? ports? emission?)
2. UI Kit (validator)      src/render/kit.py + src/render/spec.py   (props, enums, positional order)
3. Frontend kit + prompt   apps/skillnet-web/.../kit/  →  drift digest   (what the LLM sees)
4. Evidence policy         src/services/evidence_contract_policy.py   (certifies? support_only?)
```

## 1. Entry in the availability registry

`apps/skillnet-api/src/personalization/didact_component_registry.v1.json`. Add an object
to `components` with:

- `id` — the `didact.*` from the authoritative snapshot (`didact_snapshot.json`,
  `available_types`).
- `renderer_mode` — `direct` (SkillNet's own render), `activity_definition` (via
  `DidactActivity` loading a reviewed `ActivityDefinition`), or `blocked`.
- `renderer_symbol` — the renderer's symbol, or `null` if `blocked`.
- `emission` — `enabled` / `disabled` (explicit permission for OpenUI, independent of
  renderer availability).
- `required_ports` — a subset of the host ports. If you request a port outside
  `available_host_ports` (`assets`, `clock`, `evaluation`, `persistence`, `progress`),
  the component ends up **degraded/blocked** even if installed. The possible ports are
  in `didact_catalog.py` (`HostPort`: also `events`, `execution`, `media`, `scheduler`,
  `simulation`).
- `authoring_strategy` — `inline`, `server_activity`, or `unsupported`.

The catalog is projected in `didact_catalog.py` (`DidactComponentAvailability`,
`AvailabilityStatus` = `READY` / `DEGRADED` / `BLOCKED`). Exposure to the prompt is a
second, stricter operation in `didact_descriptors.py`: only a type with an enabled
renderer and satisfied ports crosses the OpenUI boundary.

## 2. Declare it in the frontend kit — `kit.py` derives itself

Since the catalogue refactor, `apps/skillnet-api/src/render/kit.py` no longer
hand-declares `UI_KIT`: it *builds* it from `openui_catalog.json`, the artifact
generated from the frontend kit. So step one is on the frontend, in
`apps/skillnet-web/src/components/courses/kit/`:

- `kit/schemas.ts` — add the zod prop schema, and register the name in
  `KIT_COMPONENT_NAMES` (order = positional order of the OpenUI dialect, §5.4),
  `KIT_DESCRIPTIONS`, and `KIT_PROP_SCHEMAS`.
- A renderer `.tsx` block, exported from `blocks/index.ts`.
- `kit/library.tsx` — `defineComponent(...)` and add it to `createLibrary`.
- Run `node scripts/generate-openui-prompt.mjs` (in `apps/skillnet-web`) to regenerate
  `openui_prompt.txt` / `openui_catalog.json`.

`kit.py::_build_ui_kit()` picks the new name up from that artifact automatically —
**no edit to `kit.py` needed** for a plain component (props, no container role, no
content-function claim).

Only touch `kit.py` when the component needs backend-only metadata the artifact
cannot express — add an entry to `_BACKEND_METADATA` for:

- `is_container=True` (it can hold children as a valid `root`),
- `functions=(FunctionFit(ContentFunction.X, rank),)` if you want the function layer
  to propose it,
- or, if the component doesn't come from the frontend catalogue at all (server-only,
  legacy, or `broker_scoped=True` like `PodcastPlayer`/`InfographicImage`), add it to
  `_BACKEND_ONLY_COMPONENTS` instead.

A component left out of `_BACKEND_METADATA` gets safe defaults (`is_container=False`,
no functions) rather than being dropped — it just can't be used as `root` until someone
declares it explicitly. `PropKind` (`STRING`, `NUMBER`, `ENUM`, `STRING_LIST`,
`STRING_MATRIX`, `NUMBER_LIST`, `REFS`) is inferred from the zod schema; `REFS` maps to
`Component.children`, never to `props`.

Structure rules are enforced by `src/render/spec.py`: the `root` must be a container
(rule 1), a maximum of `MAX_ROOT_CHILDREN = 5` root children (rule 4), etc. `spec.py` is
the only layer that validates props/enums/arity; the OpenUI parser only checks presence
and arity.

## 3. The frozen-list tests are the real review gate

There's no drift digest to keep two hand-written catalogues honest anymore — there's
only one hand-written catalogue (the frontend kit), and `kit.py` derives from it. What's
left is a deliberate guardrail: `tests/test_render_kit.py::test_catalogue_is_the_frozen_list`
and its neighbors **fail on purpose** when a new component shows up that nobody has
signed off on, so you can't ship one silently. Update the frozen list in that test
alongside your `_BACKEND_METADATA` decision (container? content function? broker-scoped?)
— that's the actual review step, not paperwork to route around.

A `broker_scoped` component (`PodcastPlayer`, `InfographicImage`) is deliberately absent
from the frontend catalogue (`KIT_COMPONENT_NAMES`) and injected per node by the media
broker instead — see `schemas.ts` for why.

## 4. The certification family (if the component evaluates)

If the component checks knowledge and you want it to **certify mastery**, it must enter
the evidence policy: `apps/skillnet-api/src/services/evidence_contract_policy.py`.

- The certifiable family is `_FACT_RECOGNITION_COMPONENTS`, backed by a **real
  deterministic scorer** (there's an import-time guard `_UNSCORABLE`: a component
  without a scorer can't certify).
- It's accepted (`EvidencePolicyAccepted`, `evidence_type="grounded_fact_recognition"`,
  with an `oracle_ref`) only for a `RECOGNIZE` mission whose evidence atoms are all in
  `_RECOGNIZABLE_ATOM_KINDS = {FACT, PROCEDURE_STEP, CRITERION}`.
- In any other case, the node **declines to `support_only`** with a typed reason
  (`CRITICAL_ORACLE_UNAVAILABLE`, `EXECUTION_ORACLE_UNAVAILABLE`, `RUBRIC_ORACLE_UNAVAILABLE`,
  `REQUIRED_EVIDENCE_UNSUPPORTED`). A new component that evaluates without a reliable
  oracle **must not** certify: it's served as non-evaluative practice. The scorer for
  activities lives in `src/services/didact_evidence.py`.

Honesty rule reflected in the prompt (`llm/prompts/runtime.py`): a knowledge/recall node
certifies with a real, varied evaluation; only when no reliable check exists does the
screen stay as practice and **not** certify.

## 5. Checklist for a new component

1. Is the `didact.*` in `didact_snapshot.json` (`available_types`)? If not, it's not an
   installed Didact type.
2. Registry: add the entry in `didact_component_registry.v1.json` with `renderer_mode`,
   `emission`, `required_ports`, `authoring_strategy`. If it requests an unavailable
   port, it will be blocked (document the gap in [`didact-components.md`](didact-components.md)).
3. Frontend kit: schema + block + `library.tsx` entry, then regenerate the artifact
   (`generate-openui-prompt.mjs`). `kit.py` derives itself — only add a
   `_BACKEND_METADATA` entry if it's a container or claims a content function.
4. Update the frozen list in `tests/test_render_kit.py` (or mark `broker_scoped` if it
   goes through the broker instead of the prompt).
5. Certification: if it evaluates, give it a deterministic scorer and declare it in
   `evidence_contract_policy.py`; if there's no reliable oracle, have it decline to
   `support_only`.
6. Verify with the quality bench: `uv run python scripts/lesson_quality_bench.py --self-test`
   and, against real renders, `--db`.
