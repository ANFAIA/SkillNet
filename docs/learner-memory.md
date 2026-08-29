# Learner memory — the per-learner "user.md"

A human-readable, agent-maintained notebook of how each learner uses SkillNet. It is the
**prose complement** to the numeric learner model, not a replacement for it: the vectors keep
doing the deterministic, cacheable, auditable work; the notebook captures the softer, textual
things they cannot — what the learner asks the tutor, the steering they type when generating
media, where they struggle, what content they prefer — and feeds them back to the tutor as
context so the experience is personalized.

> **Estado:** implementado (backend). Un panel de front-end de solo-lectura/edición queda
> como seguimiento. Las decisiones de **privacidad y retención** de más abajo están marcadas
> **CONFIRMAR con Jose**.

## Where it sits in the existing learner model

`docs/design/v2-dynamic-courses.md` (§3.3) splits the learner model into three independent
sources, and this is deliberately a fourth, textual, one that sits alongside them:

| Source | Lives in | Shape | Written by |
| --- | --- | --- | --- |
| Declared | `learner_profiles` (role, sector, experience, preset) | structured | onboarding |
| Inferred | `learning_events` → `format_vector` | numeric vector | interaction events |
| Competence | `learner_node_states` | mastery per node | grading |
| **Narrative (new)** | `learner_profiles.memory_md` | **markdown prose** | agents + the learner |

The numeric `tutor_notes` field is, by design, a **controlled vocabulary — never LLM prose**
(`src/services/learner_profile_service.py`), because that is what makes it auditable and
erasable. **This new field deliberately reverses that decision for the one place it is worth
it.** The notebook is prose on purpose; the trade is that it is employee-private, curated
(not free-append), short, and fully erasable — see below.

## Storage

Two additive, nullable columns on `learner_profiles` (migration `0010_learner_memory.py`):

- `memory_md TEXT` — the notebook, canonical markdown. `NULL` = "empty notebook".
- `memory_updated_at TIMESTAMPTZ` — last write.

`learner_profiles` is already `UNIQUE (user_id)`, so there is exactly one notebook per
learner. No new table, no new index; the down-migration is a clean `DROP COLUMN`.

## The notebook shape (fixed sections)

`src/services/learner_memory.py` owns a **fixed** set of five section headings, in render
order. A writer must name one of them or the call is rejected (`UnknownSectionError`), so the
notebook can never sprout ad-hoc sections and the read-back prompt always knows its shape:

```
## Perfil declarado
## Cómo aprende
## Le cuesta / dudas frecuentes
## Preferencias de contenido
## Notas del tutor
```

Each entry is one short markdown bullet. An empty section renders `_(sin datos)_`.

## Curation (deterministic, unit-tested, no LLM)

Everything above `LearnerMemoryService` is a pure function over markdown strings — no
session, no network, no LLM — so the merge is deterministic and testable without a database
(`tests/test_learner_memory.py`). `note(...)` runs these rules:

1. **Clean** — collapse the text to one printable line, cap at `ENTRY_MAX_CHARS` (240). Never
   store a raw multi-line chat transcript.
2. **Supersede near-duplicates** — an incoming note that says the same thing as an existing
   one (identical after accent/punct-folding, a substring, or ≥ 70 % token overlap) **drops
   the old line and appends the fresh wording**. The notebook does not accumulate three
   slightly-different copies of one fact; a stale line is replaced.
3. **Cap** — keep only the newest `MAX_ENTRIES_PER_SECTION` (8) entries per section.
4. A learner's freeform `PUT` is normalized back to the five canonical sections and capped at
   `MAX_TOTAL_CHARS` (8 000); unknown headings are dropped on the next render.

## Writers (who fills the notebook)

Wired, live, and best-effort (a failure never breaks the request that triggered it):

1. **Media steering** — `src/routes/media.py`. When an **employee** enqueues a rich-media
   generation with a steering prompt (`spec.prompt` / `spec.steering`), it records
   `Pidió enfoque: «…» al generar {kind}` under **Preferencias de contenido**.
   **This is the ONE writer that intentionally keeps a short slice of the user's own text
   verbatim** — the extra info they typed is exactly the preference worth honouring, so it is
   kept literally (capped and curated). Everything else stores a distilled observation.
2. **Tutor chat hook** — `src/services/chat_service.py`, after the turn's `done` event (so it
   never delays a token). Distilled and **non-verbatim**: it records the **node title** the
   learner consulted the tutor about (`Consultó al tutor mientras estudiaba «…»`) under
   **Le cuesta / dudas frecuentes**, only when a lesson title travels in the client context.
   It never stores the learner's own words.

Designed, not yet wired (safe follow-ups):

3. **Node-state hook** — `LearnerProfileService.apply_signals` already maps grading signals to
   the controlled `tutor_notes` vocabulary (`reforzar_con_ejemplo`, `reducir_longitud_modulo`,
   `revisar_prerrequisito`) on every `/answer`. Translating those actions to a prose line under
   **Notas del tutor** is a clean next writer; it was left out of this pass to avoid touching
   the grading transaction's careful semantics.
   (`/feedback` and the two `*_dificultad` actions were removed on 2026-08-29 —
   `docs/design/future-lesson-feedback.md`.)
4. **Perfil declarado** — could be seeded/synced from onboarding (role, sector, experience).

## Read path (who reads it back)

- **Tutor** — `chat_service` injects the trimmed notebook (empty sections dropped, capped at
  `LEARNER_MEMORY_MAX_CHARS` = 1 200) into the **tutor** turn as a labelled context block, so
  answers can be personalized. This is safe because a chat turn is **per-user and uncached**.
  The **admin** assistant is never given it (see Privacy).
- **Generators** — the trimmed notebook is exposed in the render context
  (`profile_payload["memory_md"]` in `src/agents/runtime/nodes.py`), so `decide_formato` and
  the generation agents *can* reach it. **It is deliberately NOT fed into the generation
  prompt yet.** Node renders are cached under a `cache_key` that (correctly, §3.4) excludes
  `user_id`: two learners in the same bucket share a row. Injecting one learner's prose into
  that shared, cached prompt would leak their personalization into a render served to
  everyone in the bucket — a correctness *and* privacy problem.
  - **Follow-up (CONFIRMAR con Jose):** to activate generator personalization, fold a coarse,
    **non-identifying** "preferences bucket" derived from the notebook into `cache_key`
    (mirroring `vector_bucket`), or add a per-user render path for high-value nodes. The
    plumbing (memory in the render context) is already in place.

## Privacy & retention — CONFIRMAR con Jose

- **Employee-private by default.** The notebook is the learner's own prose. **The admin has
  no route to it** — consistent with the GDPR-cautious line the rest of the learner model
  draws (the admin only ever sees k ≥ 5 aggregates, never one person's text). The tutor reads
  it to personalize for that same learner; the admin assistant never receives it.
- **GDPR self-service** (`src/routes/learner_memory.py`, employee-only):
  - `GET /api/v1/users/me/memory` — right of access (returns the markdown).
  - `PUT /api/v1/users/me/memory` — right of rectification (the learner edits it).
  - `DELETE /api/v1/users/me/memory` — right of erasure of **this field** (idempotent).
- **Full erasure already covers it.** `memory_md` lives on `learner_profiles`, which is
  deleted **whole** by `DELETE /users/me/learner-profile`
  (`LearnerProfileRepository.erase_user_data`), so the art. 17 path needs no change and the
  table-by-table erasure test still holds (a column was added, not a table).
- **Retention — DECISION PENDIENTE.** `learning_events` are purged at **90 days**
  (`src/scripts/purge_learning_data`). The notebook is a *curated summary*, not an event log,
  so it does not grow unbounded (8 entries/section), and there is a reasonable argument to let
  it persist for the life of the profile. Two options for Jose to choose:
  - **A (recommended):** persist for the life of the profile (erased with the profile / on the
    learner's `DELETE`). Simple; matches "it's a summary, not raw data".
  - **B:** extend the 90-day purge to also stale-out notebook entries older than N days (needs
    a per-entry timestamp, which the current markdown does not carry — a schema change).
  Until confirmed, the implementation follows **A**.
- **One verbatim slice, called out.** Only the media-steering writer keeps a short piece of
  the user's own text (their steering prompt). Every other writer stores a distilled
  observation. This is the intended exception and is documented at the call site.

## Tests

- `tests/test_learner_memory.py` — the pure curation core (dedupe, supersede, cap, markdown
  round-trip, prompt trimming). Runs under `pytest -m "not integration"`.
- `tests/integration/test_learner_memory_api.py` — the three endpoints and the DB-backed
  service round-trip end-to-end (needs a live Postgres, `-m integration`).
