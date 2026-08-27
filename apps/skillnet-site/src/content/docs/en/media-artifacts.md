---
title: "Media artifacts"
order: 14
section: "extensibility"
---

# Media artifacts

**Status:** in production (podcast and infographic integrated into the episode; slides and video
generatable)
**Related:** [`personalization.md`](/en/docs/personalization),
[`podcast-studio-plan.md`](/en/docs/podcast-studio-plan),
[`llm-integration.md`](/en/docs/llm-integration), [`backend-api.md`](/en/docs/backend-api)

> A **media artifact** is a piece of media generated and *grounded* in a course's content: a
> podcast (audio overview), an infographic, a slide deck, or a narrated video. They are
> generated asynchronously, saved per organization, and some are injected inside the episode as
> UI components when the learner's preference calls for them.

## 1. The four generators

All under `src/services/media/`. Each declares its `MediaKind`, emits steps over SSE, and
persists a `spec_json` with citations.

| Generator | `MediaKind` | What it produces | File |
|---|---|---|---|
| Podcast | `PODCAST` | One- or two-voice audio overview: grounded bundle → validated script → an mp3 | `podcast/generator.py` |
| Infographic | `INFOGRAPHIC` | NotebookLM-style vertical poster (PNG): content agent → image model | `infographic/generator.py` |
| Slides | `SLIDES` | Slide deck (kit blocks per slide) + a landscape illustration per slide | `slides/generator.py` |
| Video | `VIDEO` | Narrated slides served as HTML (not a generative video model): deck → per-slide narration → an mp3 per slide | `video/generator.py` |

Grounded details:

- **Podcast** (`podcast/generator.py`): `grounded bundle → script → voices → mp3` pipeline.
  SSE steps `guion`/`voz`/`listo`. `spec_json` carries `turns` with `citation_ids` per turn; the
  `data` is the mp3. Default runtime for uploaded-course scope raised to 600 s.
- **Infographic** (`infographic/generator.py`): two stages (content agent with facts as data,
  then image model), size `1024x1536`. The image is *best-effort*: if it fails, it degrades to
  a spec with no image (`has_image=False`). Steps `datos`/`imagen`/`listo`.
- **Slides** (`slides/generator.py`): validated deck + one illustration per slide (`1536x1024`,
  cover `1024x1024`), saved in `AssetStore` and referenced by content hash
  (`image_ref`/`image_ext`). Best-effort illustrations per slide; optional decorative cover.
- **Video** (`video/generator.py`): "narrated slides shipped as HTML, never a real generative
  video model". Three stages (deck → one narration line per slide → an mp3 per slide via the
  podcast's TTS path). Nothing is stitched into a video file: the frontend chains the clips.

## 2. `src/routes/media.py` route

Router under `/media`.

| Method | Route | Returns | Notes |
|---|---|---|---|
| POST | `/media/artifacts` | `202 {artifact_id, status}` | Enqueues a job. Permission via `can_generate_artifacts`. The row is committed before the task is launched |
| GET | `/media/artifacts` | `list[MediaArtifactRead]` | Query `course_id` (required), `node_id`, `include_nodes`. Three shapes: one node / all of the course / course-level only |
| GET | `/media/artifacts/{id}` | `MediaArtifactRead` | One |
| GET | `/media/artifacts/{id}/stream` | SSE | Channel `media:{id}`; events `media_step` and terminal `media_done`/`media_error` |
| GET | `/media/artifacts/{id}/asset` | bytes | The rendered asset, or 404 |
| GET | `/media/artifacts/{id}/asset/{ref}` | bytes | A sub-asset by content hash (`ref` must be a sha256 the spec lists) |

### Scope and personalization note

- **Scope** — `MediaScope` enum in `src/schemas/media.py`: `NODE="node"`, `COURSE="course"`,
  `STANDALONE="standalone"`. The contract is validated: `node` requires `node_id`; `course` and
  `standalone` cannot carry it. It is resolved in the route and written into `spec["scope"]`.
- **Personalization note** — `body.note` is folded into `spec["note"]` and seeds the `prompt`
  (and the `query` when standalone). For employees it is persisted *verbatim* into the
  learner's memory (`_remember_media_steering`, best-effort):
  `Pidió enfoque: «...» al generar {kind}` ("Asked for focus: «...» when generating {kind}").

## 3. Data models

**`src/models/media_artifact.py`** — org-scoped, not per-user.

- `MediaKind`: `PODCAST, SLIDES, INFOGRAPHIC, VIDEO, MINDMAP, REPORT, COVER_IMAGE`.
- `MediaArtifactStatus`: `PENDING → RUNNING → DONE | ERROR` (the runner walks through
  `pending → running → done|error`; note the failure state is `error`, not "failed").
- Fields: `org_id`, `course_id`, `node_id` (nullable), `kind`, `status`, `spec_json` (JSONB),
  `asset_path` (nullable), `content_hash` (sha256, dedup key), `error`. **There is no `scope`
  column**: the scope lives inside `spec_json`.

**`src/models/course_artifact_generator.py`** — `course_artifact_generators` table, composite PK
`(course_id, user_id)`. Records *who*, besides admins, can generate course-level media. It does
not carry kind/status/scope enums.

## 4. In-lesson components and the broker

`src/agents/runtime/media_broker.py` decides whether an artifact becomes a component inside the
episode. `MEDIA_COMPONENT_BY_KIND` maps `PODCAST → "PodcastPlayer"` and
`INFOGRAPHIC → "InfographicImage"` (the kit's two *broker-scoped* components — see
[`didact-components.md`](/en/docs/didact-components)).

Injection requires **three conditions at once**:

1. **Artifact READY** — `ready_media_for_node` only returns rows with `status == DONE`, of kind
   PODCAST/INFOGRAPHIC, org-scoped, the most recent wins, and it discards rows without an
   `asset_path`.
2. **The learner's modality matches** — `gate_offers` is a pure filter: `podcast` only if
   `_prefers_audio(prefs)`, `infographic` only if `_prefers_visual(prefs)` (see
   [`personalization.md`](/en/docs/personalization) §2).
3. **It is grounded** in the node's content.

When it passes the filter, `offers_prompt_addendum` injects a *grounded* whitelist into the
prompt: "there is already-generated and verified media material, chosen because it matches this
learner's modality preference... Use EXACTLY the given artifact_id (never invent or modify it)",
and it emits signatures like `PodcastPlayer("{artifact_id}", "{title}")` /
`InfographicImage("{artifact_id}", "{title}")`. The offer **only widens** what can be emitted:
it does not weaken validation. Its footprint enters the render key, so a learner with media
enabled gets a different render.

## 5. Providers: TTS chain and image model

**TTS** (`src/services/media/podcast/voices.py`) — "richest first, ending in an offline safety
net". `_build_fallback_chain`:

1. **ElevenLabs** (Text-to-Dialogue, one call → one mp3), `model_id = PODCAST_DIALOGUE_MODEL`
   (`"eleven_v3"`), voices `PODCAST_VOICE_A`/`_B`. Provider configured by `TTS_PROVIDER`
   (default `"disabled"`).
2. **Azure AI Speech** — only if region + endpoint + key are configured; voices
   `es-ES-AlvaroNeural` / `es-ES-ElviraNeural`.
3. **eSpeak NG offline** — "no key, no quota, always last"; voices `es+m3` / `es+f3`.

Public entry point `synthesize_podcast`: cache → dialogue → fallback. If TTS is not available,
modality resolution degrades audio → text (`fallback_reason="tts_disabled"`).

**Image model** (`src/services/media/images.py`) — `generate_image` via litellm; primary
`IMAGE_MODEL = "openrouter/google/gemini-2.5-flash-image"` (NotebookLM's "Nano Banana" via
OpenRouter), fallback `IMAGE_FALLBACK_MODEL = "gpt-image-1"` (one attempt). Keys: `openrouter/*`
uses `OPENROUTER_API_KEY`, otherwise `LLM_API_KEY`. Without a key the image is *best-effort*:
it degrades to `has_image=False` (infographic with no poster) without breaking the job.

### Key dependency and "baked at seed time"

Two practical consequences of this chain, important for demos and for UX:

1. **Audio/image quality is only as good as the keys of whoever ran the seed.** The artifacts
   (podcast mp3, poster PNG) are generated **at seed time**, saved content-addressed in
   `data/media_assets`, and served to **all** learners from storage; they are not regenerated
   per user. A learner on an already-seeded DB hears/sees what was generated back then.
2. **Known gap in the mascot's live voice.** Unlike the podcast (which degrades to offline
   eSpeak), the `POST /api/v1/tts/synthesize` route **fails hard with a 500** when ElevenLabs
   has no key/credit — it does not fall back to the offline provider. The frontend already
   swallows it silently (`MascotaCompanion.tsx`), but the admin/settings surface does not
   indicate it.

The plan for surfacing these degraded states in the UI (admin banner, extended `/health`,
onboarding) is in [`degraded-mode-ux.md`](/en/docs/degraded-mode-ux).
