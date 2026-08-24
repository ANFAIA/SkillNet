---
title: "Media artifacts"
order: 14
section: "extensibility"
---

# Media artifacts

**Status:** in production (podcast and infographic integrated in the episode; slides and
video generatable)
**Related:** [`personalization.md`](personalization.md),
[`podcast-studio-plan.md`](podcast-studio-plan.md),
[`llm-integration.md`](llm-integration.md), [`backend-api.md`](backend-api.md)

> A **media artifact** is a piece of media generated and *grounded* in a course's content: a
> podcast (audio overview), an infographic, a slide deck, or a narrated video. They are
> generated asynchronously, saved per organization, and some are injected into the episode as
> UI components when the learner's preference calls for them.

## 1. The four generators

All under `src/services/media/`. Each one declares its `MediaKind`, emits steps over SSE, and
persists a `spec_json` with citations.

| Generator | `MediaKind` | What it produces | File |
|---|---|---|---|
| Podcast | `PODCAST` | One- or two-voice audio overview: grounded bundle → validated script → an mp3 | `podcast/generator.py` |
| Infographic | `INFOGRAPHIC` | Vertical NotebookLM-style poster (PNG): content agent → image model | `infographic/generator.py` |
| Slides | `SLIDES` | Slide deck (kit blocks per slide) + one landscape illustration per slide | `slides/generator.py` |
| Video | `VIDEO` | Narrated slides served as HTML (not a generative video model): deck → per-slide narration → one mp3 per slide | `video/generator.py` |

Grounded details:

- **Podcast** (`podcast/generator.py`): pipeline `grounded bundle → script → voices → mp3`.
  SSE steps `script`/`voice`/`ready`. `spec_json` carries `turns` with `citation_ids` per
  turn; the `data` is the mp3. Default runtime for the uploaded-course scope raised to 600 s.
- **Infographic** (`infographic/generator.py`): two stages (content agent with facts as data,
  then an image model), size `1024x1536`. The image is *best-effort*: on failure it degrades
  to a spec with no image (`has_image=False`). Steps `data`/`image`/`ready`.
- **Slides** (`slides/generator.py`): validated deck + one illustration per slide
  (`1536x1024`, cover `1024x1024`), stored in `AssetStore` and referenced by content hash
  (`image_ref`/`image_ext`). Per-slide illustrations are best-effort; the cover is optional
  and decorative.
- **Video** (`video/generator.py`): "narrated slides shipped as HTML, never a real generative
  video model". Three stages (deck → one narration line per slide → one mp3 per slide via the
  podcast's TTS path). Nothing gets stitched into a video file: the frontend chains the clips.

## 2. Route `src/routes/media.py`

Router under `/media`.

| Method | Route | Returns | Notes |
|---|---|---|---|
| POST | `/media/artifacts` | `202 {artifact_id, status}` | Queues a job. Permission via `can_generate_artifacts`. The row is committed before the task is launched |
| GET | `/media/artifacts` | `list[MediaArtifactRead]` | Query `course_id` (required), `node_id`, `include_nodes`. Three shapes: a single node / all of a course / course-level only |
| GET | `/media/artifacts/{id}` | `MediaArtifactRead` | One |
| GET | `/media/artifacts/{id}/stream` | SSE | Channel `media:{id}`; events `media_step` and terminal `media_done`/`media_error` |
| GET | `/media/artifacts/{id}/asset` | bytes | The rendered asset or 404 |
| GET | `/media/artifacts/{id}/asset/{ref}` | bytes | A sub-asset by content hash (`ref` must be a sha256 listed in the spec) |

### Scope and personalization note

- **Scope** — enum `MediaScope` in `src/schemas/media.py`: `NODE="node"`, `COURSE="course"`,
  `STANDALONE="standalone"`. The contract is validated: `node` requires `node_id`; `course`
  and `standalone` cannot carry one. It is resolved in the route and written into
  `spec["scope"]`.
- **Personalization note** — `body.note` is folded into `spec["note"]` and seeds the `prompt`
  (and `query` when standalone). For employees it is persisted *verbatim* in the learner's
  memory (`_remember_media_steering`, best-effort): `Requested focus: "..." when generating
  {kind}`.

## 3. Data models

**`src/models/media_artifact.py`** — org-scoped, not per user.

- `MediaKind`: `PODCAST, SLIDES, INFOGRAPHIC, VIDEO, MINDMAP, REPORT, COVER_IMAGE`.
- `MediaArtifactStatus`: `PENDING → RUNNING → DONE | ERROR` (the runner walks
  `pending → running → done|error`; note that the failure state is `error`, not "failed").
- Fields: `org_id`, `course_id`, `node_id` (nullable), `kind`, `status`, `spec_json` (JSONB),
  `asset_path` (nullable), `content_hash` (sha256, dedup key), `error`. **There is no
  `scope` column**: scope lives inside `spec_json`.

**`src/models/course_artifact_generator.py`** — table `course_artifact_generators`, composite
PK `(course_id, user_id)`. Records *who*, besides admins, can generate course-level media. It
does not carry kind/status/scope enums.

## 4. In-lesson components and the broker

`src/agents/runtime/media_broker.py` decides whether an artifact becomes a component inside
the episode. `MEDIA_COMPONENT_BY_KIND` maps `PODCAST → "PodcastPlayer"` and
`INFOGRAPHIC → "InfographicImage"` (the kit's two *broker-scoped* components — see
[`didact-components.md`](didact-components.md)).

Injection requires **three conditions at once**:

1. **Artifact READY** — `ready_media_for_node` only returns rows with `status == DONE`, of
   kind PODCAST/INFOGRAPHIC, org-scoped, with the most recent winning, and it discards rows
   without `asset_path`.
2. **The learner's modality matches** — `gate_offers` is a pure filter: `podcast` only if
   `_prefers_audio(prefs)`, `infographic` only if `_prefers_visual(prefs)` (see
   [`personalization.md`](personalization.md) §2).
3. **It is grounded** in the node's content.

When it passes the filter, `offers_prompt_addendum` injects a *grounded* allow-list into the
prompt: "already-generated and verified media material exists, chosen because it matches this
learner's modality preference... Use EXACTLY the given artifact_id (never invent or modify
it)", and it emits signatures such as `PodcastPlayer("{artifact_id}", "{title}")` /
`InfographicImage("{artifact_id}", "{title}")`. The offer **only widens** what can be emitted:
it never weakens validation. Its fingerprint enters the render key, so a learner with media
enabled gets a different render.

## 5. Providers: the TTS chain and the image model

**TTS** (`src/services/media/podcast/voices.py`) — "richest first, ending in an offline
safety net". `_build_fallback_chain`:

1. **ElevenLabs** (Text-to-Dialogue, one call → one mp3), `model_id = PODCAST_DIALOGUE_MODEL`
   (`"eleven_v3"`), voices `PODCAST_VOICE_A`/`_B`. Provider configured via `TTS_PROVIDER`
   (default `"disabled"`).
2. **Azure AI Speech** — only if region + endpoint + key are configured; voices
   `es-ES-AlvaroNeural` / `es-ES-ElviraNeural`.
3. **eSpeak NG offline** — "no key, no quota, always last"; voices `es+m3` / `es+f3`.

Public entry point `synthesize_podcast`: cache → dialogue → fallback. If TTS is unavailable,
modality resolution downgrades audio → text (`fallback_reason="tts_disabled"`).

**Image model** (`src/services/media/images.py`) — `generate_image` via litellm; primary
`IMAGE_MODEL = "openrouter/google/gemini-2.5-flash-image"` (NotebookLM's "Nano Banana" via
OpenRouter), fallback `IMAGE_FALLBACK_MODEL = "gpt-image-1"` (one attempt). Keys:
`openrouter/*` uses `OPENROUTER_API_KEY`, otherwise `LLM_API_KEY`. Without a key the image is
*best-effort*: degrades to `has_image=False` (infographic with no poster) without breaking
the job.

### Key dependency and "baked at seed time"

Two practical consequences of this chain, important for demos and for UX:

1. **Audio/image quality is that of whoever's keys ran the seed.** Artifacts (podcast mp3,
   poster PNG) are generated **at seed time**, saved content-addressed under
   `data/media_assets`, and served to **all** learners from storage; they are not
   regenerated per user. A learner on an already-seeded DB hears/sees what was generated
   then.
2. **Known gap in the mascot's live voice.** Unlike the podcast (which degrades to offline
   eSpeak), the `POST /api/v1/tts/synthesize` route **fails hard with 500** when ElevenLabs
   has no key/credit — it does not fall back to the offline provider. The frontend already
   swallows this silently (`MascotaCompanion.tsx`), but the admin/settings surface doesn't
   indicate it.

The plan for surfacing these degraded states in the UI (admin banner, extended `/health`,
onboarding) is in [`degraded-mode-ux.md`](degraded-mode-ux.md).
