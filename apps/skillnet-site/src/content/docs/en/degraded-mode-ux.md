---
title: "Degraded-mode UX"
order: 26
section: "core"
---

# Degraded mode: surfacing it in the UI

**Status:** implemented (2026-08-26). This file describes what is in the code.
**Related:** [`onboarding.md`](/en/docs/onboarding) §2, [`media-artifacts.md`](/en/docs/media-artifacts) §5,
[`configuration.md`](/en/docs/configuration), [`security.md`](/en/docs/security)

> SkillNet degrades in specific ways when an external key is missing or a provider returns
> a quota error. Those degradations used to be **invisible**: the interface accepted the
> job, ran it, and thirty seconds later showed the provider's raw exception. Now every
> capability says what state it is in and why, and whoever is looking decides.

## 1. Three states, not two

A capability is no longer a boolean. It is `{status, reason, hint}` with
`status ∈ {ready, degraded, blocked}` (`src/schemas/capabilities.py`).

| State | Meaning | What the interface does |
|---|---|---|
| `ready` | It works | Nothing special |
| `degraded` | It works with less | Lets you run it, and says what will come back reduced |
| `blocked` | It cannot work | Control visible, inert, with the reason attached |

The distinction is not cosmetic. The podcast carries the offline eSpeak voice at the end of
its chain (`src/services/media/podcast/voices.py`), so `tts` **degrades and never blocks**:
turning the button off would take away something that works today. `images` does block — a
deliberate product decision, see §4.

`reason` is an enum (`missing_api_key`, `not_configured`, `provider_quota`,
`provider_down`), never a sentence: the wording belongs to i18n in the client.

## 2. Where it comes from: config AND runtime

`derive_capabilities()` (`src/services/capabilities.py`) crosses two layers:

- **Config**, pure: reads `settings`, calls nobody, cannot fail. That is what makes it safe
  to serve on a public endpoint.
- **Runtime**: `src/services/provider_health.py`, an in-process TTL registry fed by the real
  failure paths (429/402 → `quota`, anything else → `down`). It can only make a capability
  **worse**, never better, and it heals on its own when the TTL expires.

Single-worker assumption, the same one `_INFLIGHT` in `node_render_service` already makes.
It is a hint for the interface, never a source of truth: losing it on restart is correct.

There are no active probes against the provider. They spend quota and lie just as fast.

## 3. Who sees what

`GET /setup/status` is **public and pre-authentication**. It carries `status` and `reason`;
`hint` always travels as `null`. Naming the environment variable that would fix the problem
is an inventory of the deployment's configuration handed to an anonymous caller.

`GET /settings/capabilities` (`src/routes/settings.py`) serves the same object **with**
`hint`, behind the admin dependency. One derivation, two audiences.

In the client the wording is role-aware too (`src/lib/capabilityCopy.ts`): a learner is told
the feature is unavailable in this installation and nothing more — the shape of the `.env` is
not their business and they can do nothing with it; an admin gets the action that ends it.

## 4. Refusing at the door

`MEDIA_KIND_REQUIREMENTS` (`src/services/media/requirements.py`) declares which capabilities
each media kind needs, and `enqueue_artifact` checks it. It lives there, at the one door
every job starter goes through, rather than on the route that happens to be the admin's: the
lesson player's own audio/video button never went through the studio route.

Only `blocked` refuses (409, `code: capability_blocked`); `degraded` passes. The callers that
create artefacts best-effort (the seed, the end-to-end course orchestrator) catch it and
carry on.

**A product decision, not a bug fix:** with no image key, infographics and slide decks are
**blocked**. They used to degrade to a structured sheet with no poster (`has_image=false`)
and stay useful. The preference is not to offer what cannot be delivered. It is written down
here because it is a feature lost, not gained.

## 5. What a learner sees on a blocked control

`<Gated mode="explain">` (`src/components/CapabilityExplain.tsx`) renders the control
**visible and inert**:

- **`aria-disabled`, never the `disabled` attribute.** `disabled` removes it from the tab
  order, and a control nobody can reach is a control whose explanation nobody can read.
  Since `aria-disabled` blocks nothing by itself, activation is suppressed by hand: the
  click, and the Enter/Space a button turns into one.
- **The sentence always lives in the DOM**, in an `sr-only` span that `aria-describedby`
  points at. The bubble that hover, focus or tap summons is a second `aria-hidden` copy. A
  screen reader does not hover.
- No `z-index`: the wrapper is `relative` only while the bubble is open.

`CapabilityHealthBanner` remains the deployment-level summary and complements this; it does
not repeat it.

## 6. What is no longer true of the previous version of this document

- The mascot-voice gap (a hard 500 with no key) is **closed**: `src/routes/tts.py` falls back
  to eSpeak and returns 204.
- `GET /health` was not extended and `GET /settings/media-status` was never created. The
  information travels on the capabilities payload.
- There is no `tts.configured` and no `"media": {...}` block of the kind this file proposed.
