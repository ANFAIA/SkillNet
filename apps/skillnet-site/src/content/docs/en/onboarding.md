---
title: "Onboarding"
order: 41
section: "extensibility"
---

# Onboarding

How a new user comes to *understand and use* SkillNet. This document sets the **model**
(principles + flows), the **architecture** that supports it, and a **phased plan**. It is the
measuring stick: any future onboarding screen is checked against this.

Related: [degraded-mode-ux.md](/en/docs/degraded-mode-ux) (states without a key),
[personalization.md](/en/docs/personalization) (learner profile),
[audience-modes.md](/en/docs/audience-modes) (organization / individual).

---

## 1. Guiding principle

**It should set free, not tie down.** SkillNet sells freedom and adaptation; onboarding has to
*feel* the same. The filter for every decision: **does this stop the user or free them?**

From there, six pillars:

1. **The platform is never empty.** It starts with a demo course already set up (seed). No blank
   dashboard.
2. **Guidance yes, but the door always open.** A "step 1 of N" by default (many people want it and
   it is the path that converts the most), **closable, reopenable, and remembers progress**.
   Closing it does not punish with emptiness: you land on the full platform.
3. **Value is discovered by touching it, instantly.** The first win is **pre-generated** content
   (fast, no key, no waiting). Never a live generation as a welcome (slow = defeat).
4. **The differentiator is the generative UI.** These are not templates with swapped text: each
   lesson's interface is **composed** for that content and that person. It is made evident with an
   *ignorable* nudge ("look at the same lesson for another person → it is different").
5. **Personalization is offered or inferred, never imposed.** Capturing "how you learn" is
   optional; what is not asked is learned from behavior.
6. **The key (API key) unlocks, it does not charge.** Without a key you explore the demo; with a
   key you do it with your own content. You reach the key *once value has already been seen and is
   wanted*.

---

## 2. The architectural idea: **capability-driven onboarding**

The elegant point: onboarding, no-key degradation, and smart defaults are **the same problem** —
*"based on what is available and who you are, show one thing or another"*. They are solved with
**a single source of truth** instead of `if (hasKey)` scattered across the code.

```
                 ┌──────────────────────┐
   settings/env  │  Capabilities        │  ai, generation, tutor, tts, images
   keys          │  (what AI is there?) │  → GET /capabilities  (or /setup/status)
                 └──────────┬───────────┘
                            │  useCapabilities()
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
  Onboarding steps    UI elements          Degraded banners
  (filtered)          (<Gated requires>)   (degraded-mode-ux)
```

### 2.1 `Capabilities` — the source of truth
An object derived from the presence (and validity) of keys, exposed by the backend:

```ts
interface Capabilities {
  ai: boolean          // is there a usable LLM (nothing works without this)
  generation: boolean  // generate courses/lessons
  tutor: boolean       // tutor chat
  tts: boolean         // voice (mascot / podcast) — degrades to offline, see degraded-mode
  images: boolean      // infographics
}
```

- Backend: computed in one place (presence of `LLM_API_KEY`, `TTS_API_KEY`, `OPENROUTER_API_KEY`).
  Today `GET /setup/status` already exists and is the natural place (we already added
  `onboarding_enabled` to it).
- Frontend: **a `useCapabilities()` hook**. Any AI piece consults it; nobody hardcodes "there is a
  key".

### 2.2 Declarative gating (static element vs. needs-a-key)
Instead of scattering conditionals, a single component/hook:

```tsx
<Gated requires="tutor">
  <TutorPromptChip />        {/* only renders if capabilities.tutor */}
</Gated>
```

Rule: **the AI element turns on only if its capability is present.** Without a key it **is not
shown** (not a dead end/error). Examples:

| Always (static / pre-baked) | `requires` (turns on with a key) |
|---|---|
| Demo course (seed), viewing it | Free-form **"other"** option in questions (`generation`/`ai`) |
| Contrast nudge (two people, seed) | Generated preview / "create your first course" (`generation`) |
| Fixed presets for the questions | Chat with the tutor (`tutor`) |
| Tour (joyride) | Personalization that regenerates on the fly (`generation`) |

**Design key:** the no-key side must feel **complete** (the pre-baked content carries the value).
The AI part is **additive**, not "the good stuff was hidden".

### 2.3 Onboarding as **data**, not as a hardcoded flow
The tour is a declarative list of steps; joyride just consumes it. Adding/removing/reordering =
editing data.

```ts
interface OnboardingStep {
  id: string
  role: 'employee' | 'admin'
  target: string           // selector of the element to highlight
  title: string; body: string
  requires?: keyof Capabilities   // step is skipped if the capability is missing
  order: number
}
```

Runtime filter: `steps.filter(role).filter(cap => !s.requires || capabilities[s.requires])`.
A step that talks about the tutor **disappears** without a key, with no ad-hoc branches.

### 2.4 Onboarding state — per user, persisted, reopenable
```ts
interface OnboardingState { completed: boolean; dismissedAt?: string; lastStepId?: string }
```
- Orthogonal to routing: it **never** forces a redirect (the `ONBOARDING_ENABLED` flag already
  exists).
- MVP: `localStorage`. Later phase: per-user field (cross-device).
- Reopenable from a persistent "?"; `lastStepId` gives the "remember where I was" behavior.

### 2.5 Smart defaults — a **resolver** from the org archetype
The admin gives a minimal hint (education / enterprise) → a resolver maps archetype → defaults.

```ts
type Archetype = 'education' | 'enterprise' | ...
function resolveDefaults(a: Archetype): OrgSettings   // e.g. enterprise ⇒ mascot off
```
- **One single resolver**, not scattered conditionals.
- Values are **defaults**, always **overridable** (user/org).
- Every automatic decision is **shown and reversible** ("We turned off the mascot because this is
  an enterprise environment — change it here"). Never silent magic.

### 2.6 Shared demo = first-class asset
The test course is a seed present in every deployment (`is_demo`), an **example for both roles**:
the admin sees "this is what gets generated", the employee *does it*. Visible without a key
(already generated). With a key, **the same** course becomes conversable (tutor) and
adaptable/regenerable — the key does not change *what* you see, it changes *how much you can do
with it*.

---

## 3. Flows (one pattern, two fillings)

Branches only on the **role**; each branch is minimal. Common structure: **framing → one capture
that matters → first win**.

### 3.1 Employee (account created by the admin; never touches the key)
1. Login → **non-empty home** (enrolled in the demo / their courses) + a gentle "start here".
2. **Default, closable tour:** "open your first lesson" → tap a lesson that is **already
   pre-generated and personalized** (instant, prewarm). *Aha* = rich **and** adapts.
3. **Optional micro-capture:** "how do you like things explained? (optional)" → presets **+
   "other"** (the "other" only with a key). Skippable → default profile + behavioral inference.
4. **Contrast nudge (ignorable):** "here is how we explain it to another person" → same material,
   different UI → captures personalization.
5. From there, just learn.

### 3.2 Admin / owner (self-hosts and sets up the organization)
1. **Minimal setup** (already exists) + **one archetype question** (education/enterprise →
   defaults).
2. **Non-empty dashboard** with the demo course + closable tour.
3. **Discover the generative UI by touching** the demo (same two-person contrast).
4. **"Make it yours" moment:** "Create your first course". If **there is no key** → "connect your
   AI" (why + link to the provider + paste + **live validation**). It is not a toll: you arrive
   here already convinced. Meanwhile, everything is explorable; AI actions show "connect a key" in
   their place.
5. **Real generation = in the background + notification.** Never a loading bar as a welcome.
6. Invite employees.

---

## 4. Phased plan (cheap → expensive; nothing complex up front)

Tour engine: **react-joyride** (spotlight, "step 1 of N", skip/close, step control). We provide the
**data and state** (§2.3, §2.4), not the engine.

> **Status (2026-08-21):** Phase 0 ✅, Phase 2 infra (`Capabilities`/`<Gated>`) ✅, and the
> degraded-mode banner ✅ are done and on `main`; the admin tour (Phase 1) too. What remains, with
> a decision/design step in between: the 3-way archetype + `resolveDefaults`, the contrast nudge,
> the API key from the UI, background generation, and Phase 3.

### Phase 0 — MVP ✅ DONE
- **Non-empty home** with the demo (seed). ✅
- **Joyride tour** for employees (home → first pre-generated lesson), closable, `localStorage`. ✅
- **Non-blocking profile** (`ONBOARDING_ENABLED` + existing capture). ✅
- Only **static** elements. ✅

### Phase 1 — make the differentiator visible  ◑ PARTIAL (remainder: pending design)
- ○ **Contrast nudge** (two people, seed data) — pending.
- ✅ **Admin tour** — done: role-aware `ProductTour` (same joyride, admin steps).
- ○ **1 smart default**: enterprise/education archetype → `resolveDefaults` (enterprise turns off
  the mascot) + the line that explains it — pending (needs archetype backend).

### Phase 2 — the self-hosted unlock (the AI layer)  ◑ PARTIAL
- ✅ **`Capabilities` + `useCapabilities()` + `<Gated>`** (§2.1–2.2) — infra done (backend derives
  it from the keys and exposes it at `/setup/status`; the frontend consumes it).
- ✅ **Degraded-mode banners** (`CapabilityHealthBanner` in admin) — done.
- ○ **API key from the UI** (paste + validate) — pending (storage/security decision).
- ○ Turn on the `requires`: free-form **"other"**, **generated preview**, **tutor chat**.
- ○ **Background generation + notification**.

### Phase 3 — the complex part, last  ○ PENDING
- **Infer the profile from behavior** (what they open/re-read/skip). Separable signals module.
- **Cross-device** onboarding state, finer archetypes.

---

## 5. What already exists vs. what's missing

| Already exists (✅) | Missing (○) |
|---|---|
| Setup wizard + **welcome** (logo/mascot/degraded), login, home | **Archetype** question + `resolveDefaults` |
| Demo course (seed) + pre-generated lessons (prewarm) | **Contrast nudge** (two people) |
| **Role-aware joyride tour** (employee + admin), reopenable, per-role state | **API key in the UI** (paste+validate) — today in `.env` |
| Profile capture + `ONBOARDING_ENABLED` flag | **Background generation** + `requires` ("other"/preview/tutor) |
| **`Capabilities` + `useCapabilities` + `<Gated>`** + degraded-mode banner | Phase 3 (infer profile, cross-device) |

---

## 6. Summary in one sentence

**Full platform from the start · guidance by default but always closable and reopenable · value by
touching, not by telling · profile offered or inferred, never imposed · self-chosen and reversible
defaults · the key unlocks, it does not charge** — all under a clean engine: the app declares
*what it needs* (capability × role) and a resolver decides *what to show and how to degrade*.
