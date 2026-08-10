# NotebookLM Imitation Roadmap — Rich Media Artifacts for SkillNet

Build-oriented plan for imitating NotebookLM's output artifacts inside SkillNet
(FastAPI + LangGraph + litellm backend, React 19 + TanStack Query frontend).

Derived from the deep-research notes in
`Obsidian Vault/15_TRABAJO/SkillNet/07_ANFAIA/investigacion/notebooklm/` (synthesis +
per-artifact reports A3–A9). All product claims below are sourced there; this doc turns
them into concrete pipelines against our stack. It does **not** re-derive the media APIs —
those are settled (see "Assumed tech" below).

> **Framing (from `notas_generacion_rica.md`).** SkillNet already has the two things
> NotebookLM lacks: a **planner** (Blueprint Architect → Content Writer → Assembler,
> `docs/design/multi-agent-pipeline.md`) and a **learner model** (`format_vector`, mastery,
> `v2-dynamic-courses.md`). What NotebookLM gives us is the **per-artifact quality mechanism**
> (fixed skeleton, output schema, critique pass, how much source each generation sees) and the
> real cost/latency of audio & video. The current "poor courses" ceiling is hypothesised to be
> the **frozen block vocabulary** (9 kit blocks, none produce explanatory visuals; `ImageCard`
> and `Timeline` were excluded 2026-07-26), not the agent architecture. These media artifacts
> are the lever that unfreezes the vocabulary.

## Assumed tech (already researched — do not re-research)

- **Images:** `litellm.image_generation(model="openrouter/google/gemini-2.5-flash-image", prompt=..., size=..., n=1)` → `resp.data[0].b64_json`. This is NotebookLM's actual engine family ("Nano Banana" = Gemini 2.5 Flash Image). Stopgap: `gpt-image-1` on the existing OpenAI key. OpenRouter key is now in the repo `.env`.
- **Audio (podcast):** LLM (`gpt-4o-mini` via litellm) writes a JSON two-host dialogue script → ElevenLabs **Text-to-Dialogue** `client.text_to_dialogue.convert(inputs=[DialogueInput(voice_id, text), ...], model_id="eleven_v3")` → single mp3. Fallback: per-turn TTS + ffmpeg concat. ElevenLabs is already wired in SkillNet with a `tts_cache`.
- **Existing kit:** React DSL blocks — `TextContent, Callout, Table, Chart, Card, StepSequence, QuizItem, CodeBlock, BeforeAfter, Stack, AudioExplanation` — rendered from a spec. Plus an image-storage design (store on disk, dedup by `content_hash`, serve via a `SourceImage` component).

---

## 1. What NotebookLM actually produces

NotebookLM groups every "shaped" output in a **Studio** panel. Each has its own generation
contract. The full inventory (per synthesis §3 and A6):

| Artifact | Input | Pipeline (as reconstructed) | Grounding | User control | Limits / gotchas |
|---|---|---|---|---|---|
| **Chat** | selected sources + history | retrieval-first ("retrieves most relevant… then builds a response"); 1M-token window; RAG w/ intermediate questions | **inline citations = direct quotes**, hover→full text, click→jump to passage; abstains if out of corpus | per-source checkbox, chat styles (Default/Learning Guide/Custom), free goals | 50 chats/day free |
| **Audio Overview** (podcast) | sources + prompt + format + language + length | Gemini writes 2-host **dialogue script** → "Content Studio" editorial layer → dedicated voice model → mp3; multiple internal "edit cycles" | **no citations in the audio**; a *parallel* quotes/citations panel plays alongside; interactive hosts answer "based on your sources" | format (Deep Dive / The Brief 1-host <2min / Critique / Debate); 80+ languages; length Shorter/Default/Longer (English only); focus/expertise prompt | 3/day free; "a couple of minutes" to generate; weakest grounding, admits "inaccuracies", occasional "third voice" glitch |
| **Video Overview** | sources + format + language + style + steering prompt | Gemini extracts content → **script/slides (internal storyboard, inferred)** → Nano Banana generates **contextual illustrations + reuses assets pulled from sources** → TTS narration (1 host) → render to MP4 | no documented citations; only "AI-generated… may contain inaccuracies" notice | format (Explainer 16:9 ~80 langs / Short 9:16 ~60s / Cinematic — Short & Cinematic English-only, 18+); 8+ visual styles; steering prompt | 3/day free; "sometimes >30 min" to generate; **no script/storyboard preview before render** |
| **Mind Map** | selected sources | model produces a **topic tree**; delivered as **SVG with text nodes + connector paths** (explicit graph serialized in the page, not a static image) | node does **not** cite; clicking a node **fires a focused chat question**, whose answer carries citations | zoom, expand/collapse, download PNG; regenerate = delete note | 10/20/100/500/1000 per day by plan |
| **Flashcards** | sources + difficulty + prompt + count | generated in background; term/definition pairs | grounded only in sources; **Explain** button cites the passage (even for wrong answers) | difficulty easy/medium/hard; count fewer/standard/more; delete a card; Got it!/Missed it!; CSV export | daily quota by plan |
| **Quizzes** | idem | interactive, Hint + results; question types undocumented | idem; Explain cites the passage of your mistake | difficulty, count, Hint, fullscreen | daily quota |
| **Slide Deck** | sources + format + language + length + prompt | background ("multiple minutes"); per-slide revision with "Pending Changes" + "Generate revised deck" | inaccuracy notice; **sources are NOT consulted during revisions** — the only artifact whose revision is decoupled from the corpus | per-slide edit/delete/reorder; export PDF/PPTX | revised-deck quota by plan |
| **Infographic** | sources + language + detail + orientation + style + prompt | background ("a couple of minutes") | inaccuracy notice | rename/download/share/delete; regenerate | daily quota — output is a **single PNG sheet** in a visual style |
| **Reports** (briefing / study guide / FAQ / timeline / custom) | sources + natural-language prompt + params + **dynamic template suggestion** | model suggests a structure from the detected topic (paper→white paper, story→character analysis), then prompt+params drive it; 130+ languages | "grounded only in your source materials" | free-text prompt, structure/style/tone/language params, custom formats; agentic outputs editable after generation (2026) | daily quota. FAQ & Timeline one-click were removed Sep-2025 → recreated via "Create your own" Report |
| **Study guide** | selected notes | quick action: "key questions + glossary" | over selected notes/sources | regenerate; only written notes editable | 1000 notes/notebook |

### UX around it (A7 — the part that makes it feel good)

- **Three responsive panels:** Sources / Chat / Studio. Generation is **background work**, never a blocking modal — you keep working (browse a mind map, read a study guide) while audio/video renders.
- **Waiting is reframed, not hidden:** one-click "Generate", the wait is *declared* ("may take several minutes"), then background listening, multitask, offline download, and length control were added in waves to amortize the one-time cost.
- **Citations are the trust primitive:** hover = full quoted text, click = navigate to the passage in context. Citations only exist for **indexed passages**; sources too short reference the whole document.
- **Artifact→source loop:** a saved chat answer keeps inline clickable citations and can be **promoted to a new source**.
- **Personalization by prompt** everywhere: every generator takes a free-text steering prompt plus structured params; the prompt is saved and viewable ("View custom prompt").

---

## 2. Per-artifact imitation plan for SkillNet

Shared foundations these all build on (build once, reuse everywhere):

- **`MediaArtifact` model + async job runner.** Table `course_media_artifacts` (id, course_id, node_id nullable, kind, status[`pending|running|ready|failed`], spec_json, output_ref, source_citations_json, schema_version, created_at). Generation runs as a **LangGraph background job** returning immediately with a `pending` row; the SPA polls (TanStack Query `refetchInterval` while `pending|running`) or subscribes to the existing SSE action channel. This is the single most important primitive — it makes every artifact match NotebookLM's "background, non-blocking" contract. **Effort M, dependency for everything below.**
- **Grounding context builder.** Reuse `src/services/retrieval.py` to assemble the grounded context for a course/node: retrieved passages **each carrying a `citation_id`** (source doc + char span, the unit the image-storage/citation design already tracks). Every generator receives `[{citation_id, text, source_title, span}]`, and every generator is instructed to **emit `citation_id`s alongside its output** so we can render the same hover/click-to-passage affordance NotebookLM has. **Effort S–M, dependency for grounding on all artifacts.**
- **Asset store.** Extend the existing content-hash image store to hold generated PNGs/MP3s/MP4s (`dedup by content_hash`, serve via a signed static route). `SourceImage` component already renders stored images. **Effort S.**

### 2a. Audio Overview / Podcast — **highest impact, lowest effort**

- **What:** a 2-host conversational audio summary of a course (or node), playable inline.
- **Pipeline (our stack):**
  1. **Script agent** (`gpt-4o-mini` via litellm) with a fixed system prompt defining the two personas + show format. Output is **strict JSON** (Pydantic-validated, same discipline as the kit DSL): `{turns: [{speaker: "A"|"B", text, citation_ids: [...]}], format, language, target_seconds}`. Feed it the grounded context bundle. Support NotebookLM's formats as prompt presets: **Deep Dive** (2 hosts), **The Brief** (1 host, <2 min), **Critique**, **Debate**.
  2. **Voice synthesis:** ElevenLabs Text-to-Dialogue — `convert(inputs=[DialogueInput(voice_id_A, turn.text), DialogueInput(voice_id_B, turn.text), ...], model_id="eleven_v3")` → single mp3. **Fallback:** per-turn TTS + ffmpeg concat (already have ffmpeg patterns). Cache by `content_hash(script)` in the existing `tts_cache`.
  3. Store mp3 in asset store; expose via the existing `AudioExplanation` block (extend it to a full-course player).
- **Grounding:** citations do **not** go in the audio (matches NotebookLM). Instead persist `turns[].citation_ids` and render a **parallel quotes panel** beside the player — click a quote → jump to the source passage. This is the single feature every open-source replica failed to ship, and we get it nearly free because retrieval already yields citable passages.
- **Cost/latency reality (A8/A9):** the LLM script dominates cost, not the TTS. NotebookLM takes "a couple of minutes"; ours will be faster (short scripts). Groq-class script gen is sub-second; ElevenLabs is the latency floor. Budget seconds, not minutes.
- **Effort: S–M.** Deps: async job runner, ElevenLabs (already wired), grounding builder.

### 2b. Video Overview — **narrated slides, NOT a real video model**

- **What:** the deliverable is a **composite of narrated slides** exported to MP4 ("a visual alternative to Audio Overviews" — internally slide deck + narration). Do **not** chase Cinematic (Veo 3 / director agent) — that's the trap (§3).
- **Pipeline (our stack) — mirrors the only serious OSS replica, `open-video-overview`:**
  1. **Storyboard agent** (litellm) → strict JSON: `{scenes: [{title, narration, bullet_points, image_prompt, reused_asset_ref?, citation_ids}], format: "explainer"|"short", aspect: "16:9"|"9:16"}`. This is the internal "script/slides" step NotebookLM keeps hidden.
  2. **Per-scene image:** `litellm.image_generation(model="openrouter/google/gemini-2.5-flash-image", prompt=scene.image_prompt + style_suffix, size=...)`. Apply the visual **style** as a suffix in the prompt (NotebookLM's inferred approach). Reuse assets pulled from the source doc when `reused_asset_ref` is set (retail machines, real forms, etc. — the "extracted vs generated image" distinction flagged in `notas_generacion_rica.md` Q3).
  3. **Narration:** reuse 2a's TTS (single host for video). Get per-scene durations from TTS timing.
  4. **Assembly:** ffmpeg — Ken Burns/crossfade over each still, timed to its narration segment, concat → MP4. Store in asset store.
- **Cheaper alternative worth prototyping first:** skip MP4 render entirely and ship an **HTML "video" player** — a React slideshow component that advances stills in sync with the single mp3 (timings from step 3). Zero ffmpeg, instant, editable, and it fits the SPA. Offer MP4 export as a later "download" affordance. This is the pragmatic win.
- **Grounding:** persist `scenes[].citation_ids`; show a citations strip under the player (NotebookLM itself has none here, so we'd exceed it).
- **Effort: M** (HTML player) / **L** (true MP4 render + asset reuse). Deps: 2a, image gen, asset store, ffmpeg.

### 2c. Slide Deck — **structured, per-slide editable**

- **What:** a presentable deck, revisable slide-by-slide.
- **Pipeline:** deck agent → JSON `{slides: [{layout, title, body_blocks[], image_prompt?, citation_ids}]}` where `body_blocks` **reuse the existing kit DSL** (TextContent, Table, Chart, Callout, StepSequence). This is the vocabulary-unfreezing move: the deck is just kit blocks in a slide frame. Render with a `SlideDeck` React component (kit blocks per slide, keyboard nav, fullscreen). Export PDF/PPTX later.
- **Revision:** per-slide edit/regenerate/reorder with "Pending Changes". **Deliberately copy NotebookLM's decoupling:** revisions operate on the artifact JSON, **not** the corpus — much cheaper and it's the one place they intentionally drop grounding. Regenerating the whole deck re-consults sources.
- **Grounding:** each slide keeps `citation_ids`; footnote-style citation chips.
- **Effort: M.** Deps: async runner, image gen, kit DSL (already have).

### 2d. Infographic — **single stylized sheet**

- **What:** one PNG sheet in a chosen visual style — the fastest visual "wow".
- **Pipeline:** **two-stage** to keep it grounded (image models can't be trusted with facts):
  1. **Content agent** (litellm) → JSON `{title, sections: [{heading, stat?, one_line, citation_ids}], orientation, style}` from grounded context. This *is* the grounding — the facts/numbers are extracted and verified against passages here.
  2. **Render** — two options: (a) generate the whole sheet with `gemini-2.5-flash-image` passing the structured content + style in the prompt (fastest, matches NotebookLM, but text-in-image can garble); or (b) **render the JSON as an SVG/HTML infographic template** we control (crisp text, real citations, themeable light/dark) and rasterize. Recommend (b) for a learning product — legible, accurate, and it dovetails with the kit. Use (a) only for decorative backdrops.
- **Grounding:** citations attach to each stat/section; hover chips.
- **Effort: S** (HTML/SVG template) / **M** (image-model sheet). Deps: content agent, asset store.

### 2e. Mind Map — **explicit tree, nodes fire chat**

- **What:** branching topic map of a course.
- **Pipeline:** tree agent → JSON `{root, nodes: [{id, label, parent_id, citation_ids}]}` (an explicit graph, exactly how NotebookLM serializes it — do NOT generate an image). Render client-side with an SVG/React tree (d3-hierarchy or react-flow), zoom + expand/collapse, PNG export.
- **Grounding:** node itself doesn't cite; **clicking a node opens the course chat with a focused question** ("Explain <label> from the sources") — the chat answer carries citations. This is NotebookLM's exact loop and it reuses SkillNet's existing chat + gen-UI.
- **Effort: M.** Deps: tree agent, existing chat.

### 2f. Flashcards & Quiz — **already half-built**

- **What:** graded-difficulty decks and interactive quizzes.
- **Pipeline:** SkillNet already has `QuizItem`. Add a **flashcard/quiz generator agent** → JSON with difficulty (easy/medium/hard) and count (fewer/standard/more), each item carrying `citation_ids`. Flashcards = term/definition + Got it!/Missed it!; CSV export. Quiz = interactive with Hint.
- **Grounding:** the **Explain** button is the key feature — it shows *why* an answer is right/wrong **with a citation to the passage**. This directly serves SkillNet's pedagogy and is cheap.
- **Effort: S.** Deps: existing QuizItem, grounding builder.

### 2g. Briefing Report / Study Guide — **prompt + dynamic template**

- **What:** a structured document (briefing, study guide "key questions + glossary", FAQ, timeline, custom).
- **Pipeline:** report agent with **dynamic template suggestion** (detect course domain → suggest structure) + free-text prompt + params (tone, language, detail). Output = kit-DSL document (TextContent, Callout, Table, StepSequence). Render with existing block renderer. FAQ/Timeline = just prompt presets (as NotebookLM now does).
- **Grounding:** "grounded only in sources"; inline citation chips throughout (same as chat).
- **Effort: S–M.** Deps: grounding builder, kit DSL.

---

## 3. Recommended build order

**Prototype first (max demo impact / least effort):**

1. **Async `MediaArtifact` job runner + grounding-context builder + asset store** (the shared spine). Nothing ships without it. **M.**
2. **Audio Overview / Podcast (2a).** Highest wow-per-effort: ElevenLabs is wired, the script is one litellm call, and the **parallel citations panel** is a feature every OSS replica lacks — instant differentiation. **S–M.**
3. **Infographic via HTML/SVG template (2d option b)** and **Flashcards/Quiz with Explain-cites-passage (2f).** Both are small, both directly unfreeze the "no explanatory visuals" ceiling, both grounded and accurate. **S each.**
4. **Slide Deck (2c)** reusing kit blocks + **Video-as-HTML-slideshow (2b HTML player)** built on the deck + the podcast TTS. This gets a "video overview" on screen with no ffmpeg. **M.**
5. **Mind Map (2e)** and **Reports/Study Guide (2g)** — solid, reuse chat + kit. **M / S–M.**

**Traps — do NOT do these for the demo (per A8/A9 costs & the OSS-replica graveyard):**

- **True generative video / Cinematic** (Veo 3, director agent, MP4 render pipelines). NotebookLM itself takes ">30 minutes" and no open-source project has replicated it at useful quality — `open-video-overview` ships "rough edges", `open-cinematic-overviews` has 0 stars and a 404 README. Ship narrated-slides-as-HTML instead.
- **"Studio-quality" conversational audio** (interruptions, overlaps, disfluencies, sustained two-voice personality). No open weights reproduce it; only Kokoro-82M and CosyVoice2 are Apache-2.0, and neither is natively conversational. ElevenLabs Text-to-Dialogue is the ceiling we can reach — accept concatenated-turn quality and move on.
- **Interactive audio hosts** (talk-back). Zero OSS attempts across 9,300+ repos. Out of scope.
- **Text-baked-into-generated-images for anything factual.** Image models garble text and numbers; always extract facts in a JSON content stage and render text ourselves (§2d).
- **Trusting revisions to stay grounded.** Copy NotebookLM's honest decoupling (deck revisions don't re-hit sources) rather than pretending otherwise — but label it, and re-ground on full regeneration.

**Guiding principle from the notes:** the expensive wait is paid once and amortized (background gen, keep working, offline/replay). Build the async spine first so every artifact inherits the non-blocking UX for free.

---

## 4. Open questions / gaps (from `_huecos.md` + `notas_generacion_rica.md`)

Things the research flags as unresolved that will bite us during the build:

- **H2 — where disfluencies come from** (script text vs voice model): affects how "natural" our podcast can get. We likely can't match it; ElevenLabs `eleven_v3` audio tags are our only lever.
- **H3 / H8 — exact 2026 TTS model & whether Audio and Video share it:** unknown/black box. Doesn't block us (we use ElevenLabs), but sets the quality ceiling we're chasing.
- **H4 — citation mechanism (retrieve-then-read vs post-hoc attribution):** undocumented. **Design decision for us:** we control it — emit `citation_id`s *during* generation (retrieve-then-read style) since our retrieval already returns citable passages; don't build a separate post-attribution pass unless quality demands it.
- **H9 — real per-output cost:** no published figure. Derived TTS rates only (Gemini 2.5 Flash TTS ≈ $0.015/min audio; the LLM script is the real cost driver). Run SkillNet's own `quality_bench`-style measurement on each media pipeline before promising cost numbers.
- **Storyboard/script are never previewed before render in NotebookLM.** Open product question for us: do we let admins **edit the script/storyboard JSON before synthesis**? We can (our artifacts are JSON specs) and it would beat NotebookLM — but it adds a UX surface. Decide per artifact.
- **Extracted vs generated images** (`notas_generacion_rica.md` Q3): for restauración/retail/gestorías/clínicas, the *real* machine/form image beats a generated illustration, and today the ingest discards them. Decide whether the media pipeline pulls source-embedded images (needs ingest to retain them) — high value, currently a gap.
- **Can a producer decline?** (Q2): today there's failure handling, not semantic refusal. Adding visual producers without a "decline" path risks forced, low-value diagrams. Relevant when wiring infographic/video agents into the planner.
- **Is v2 even active?** (Q5): confirm the `delivery_mode='dynamic'` + `schema_status='validated'` path is live for the target course before judging output quality — otherwise these artifacts hang off the v1 monolith.
- **H22 — video daily quota** and general rate-limits: NotebookLM doesn't publish video quotas; irrelevant to self-host but a reminder that media gen needs our own quota/guardrails to control cost.

---

*Sources: `salidas/_sintesis.md` (§1,§3,§6), `04_audio_overview.md`, `05_video_overview.md`,
`06_artefactos_estudio.md`, `07_ux_producto.md`, `03_retrieval_grounding_citas.md`,
`08_limites_fallos_costes.md`, `09_replicas_opensource.md`, `_huecos.md`,
`notas_generacion_rica.md`. Confidence tags ([CONFIRMADO]/[INFERIDO]/[ESPECULACION]) preserved
in the underlying notes.*
