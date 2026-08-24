---
title: "Degraded-mode UX"
order: 26
section: "core"
---

# Degraded mode: surfacing it in the UI

**Status:** plan (not implemented, except as noted in §2)
**Related:** [`media-artifacts.md`](media-artifacts.md) §5,
[`personalization.md`](personalization.md) §4, [`backend-api.md`](backend-api.md),
[`../../.env.example`](../../.env.example), `README.md` §"Audio, images and the render cache"

> SkillNet degrades in specific ways when external keys are missing (ElevenLabs / OpenRouter)
> or the provider returns quota errors. Today those degradations are **invisible** to admins
> and learners, which confuses ("why is the voice robotic?", "why is there no image?", "why
> doesn't the speaker make sound?"). This document is the plan to make them visible and
> non-alarming, without implementing the UI (except §2, already resolved in code).

## 0. The three degraded states to communicate

Verified against the code (see `media-artifacts.md` §5):

1. **TTS with no key/credit → mascot voice fails hard (500).** `POST /api/v1/tts/synthesize`
   (`src/routes/tts.py`) doesn't fall back to the offline provider; `ElevenLabsProvider.synthesize`
   raises on non-200 (`src/services/tts_service.py`). This is a **known gap**.
2. **TTS with no key/credit → podcast in offline voice (eSpeak).** The podcast does degrade
   through the chain `ElevenLabs → Azure → eSpeak NG` (`src/services/media/podcast/voices.py`),
   but it sounds robotic.
3. **OpenRouter with no key → infographic without poster.** `generate_image`
   (`src/services/media/images.py`) is best-effort; the infographic ships with `has_image=false`.

All of this is **baked into the seed** and shared across learners, so the right message is at
the **deployment/admin** level, not per-user.

## 1. Media health banner / indicator (admin)

**Where.** Backend: extend `GET /health` (`src/routes/health.py`) — or add
`GET /api/v1/settings/media-status` if separating public from authenticated is preferred.
Frontend: consume in `src/api/health.ts` (`HealthRead`) and render on the admin page
`src/pages/admin/Settings.tsx`, which **already has the exact pattern**: today it shows a
single warning line when no LLM model is configured. The media indicator is the same idea.

**Backend — the minimal shape.** Add a `media` block to the `/health` response derived
**purely from configuration** (without calling providers):

```jsonc
"media": {
  "tts": { "provider": "elevenlabs", "configured": true, "live_voice_fallback": false },
  "images": { "configured": false }
}
```

- `tts.configured` = `settings.TTS_PROVIDER != "disabled"` and `settings.TTS_API_KEY` not empty
  (or `provider == "offline"`). Reuse `tts_is_available` from `src/personalization/modality.py`.
- `tts.live_voice_fallback = false` documents the gap: **live voice has no offline safety net**
  even though the podcast does.
- `images.configured` = `bool(settings.OPENROUTER_API_KEY)` or `IMAGE_MODEL` not being
  `openrouter/*` (in which case it uses `LLM_API_KEY`).

**Exhausted quota** detection (optional, phase 2): an in-process counter of 429/402 errors per
provider (same single-worker assumption as `_INFLIGHT` in `node_render_service.py`), exposed
as `"quota_exhausted": true`. V1 stays at "configured / not configured", which already covers
90% of the confusion.

**Frontend — the minimal shape.** In `Settings.tsx`, next to the model warning, a `SettingRow`
(or a discreet banner up top) that only appears when something is degraded. Messages:

- No TTS: *"Audio will use a basic offline voice (robotic) until an ElevenLabs key with
  credit is added. The mascot's live voice will be mute."*
- No images: *"Infographics will be generated without a poster until
  `OPENROUTER_API_KEY` is configured."*

With no degradation, nothing is shown (same discipline as the rest of `Settings.tsx`).

## 2. Mascot voice degrading silently (ALREADY IMPLEMENTED)

**Where.** `src/components/mascota/MascotaCompanion.tsx`.

**Status: already correct — no changes needed.** `speak()` throws on `!res.ok`, and **every**
caller swallows it (`void speak().catch(() => undefined)` in auto-read and in
`handleToggleMute`). A TTS 500 shows no error: the speech bubble text remains and only the
audio is missing. Verified in the current component.

**Optional improvement (low priority).** When the §1 health status says `tts.configured =
false`, **hide the speaker icon** instead of leaving a button that does nothing. This would
mean: pass a `ttsAvailable` prop (from the §1 `useHealth()`) to `MascotaCompanion` and wrap the
mute `<button>` in `ttsAvailable && (...)`. The text bubble always stays. It's purely
cosmetic; the behavior is already safe.

## 3. Mention in onboarding (conditional)

**Where.** `src/pages/onboarding/Onboarding.tsx` and the modality preferences step
(`src/components/onboarding/`, next to `AccessibilityStep.tsx`).

**What.** Onboarding lets the learner choose an audio/visual preference. If `tts.configured =
false` (from §1), in the step where "audio" is offered, add an inline note: *"Audio is in
basic mode on this installation (offline voice)."* — so choosing "audio" doesn't create an
expectation the installation can't meet. It doesn't block the choice (modality resolution
already degrades audio → text via `resolve_declared_modality`), it only informs.

**Priority.** The lowest of the three: it only matters if the deployment runs without TTS and
uses onboarding. Implement after §1.

## Suggested implementation order

1. **§1 backend** — extend `/health` with the `media` block (cheap, no external calls).
2. **§1 frontend** — conditional banner in `Settings.tsx` reusing `useHealth()`.
3. **§2 optional improvement** — hide the mascot speaker when there's no TTS.
4. **§3** — onboarding note.

Each step is independent and doesn't touch generation or the media pipeline; they're all
config reads + conditional rendering.
