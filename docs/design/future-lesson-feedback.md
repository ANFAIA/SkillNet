# Future: end-of-node lesson feedback

> Status: **removed on 2026-08-29**, deliberately, to cut complexity. Documented here so the
> idea can come back on purpose rather than by accident — and so whoever brings it back fixes
> the thing that made it useless the first time.
>
> Nothing was migrated away: `node_feedback` was empty by construction (see below), so
> migration `0036` dropped a table with no rows in it.

## What existed

A three-button question at the end of a dynamic node — "¿Cómo te ha resultado esta lección?",
answers `easy` / `ok` / `hard` — plus an optional free-text box ("algo no ha quedado claro").

| Piece | Where it lived |
|---|---|
| The form | `apps/skillnet-web/src/components/courses/NodeFeedback.tsx` |
| Its hook | `useNodeFeedback` in `src/api/nodes.ts` |
| Its i18n | the nine `feedback.*` keys, in `en.ts` and `es.ts` |
| The endpoint | `POST /nodes/{id}/feedback` in `src/routes/nodes.py` |
| The request | `NodeFeedbackRequest` in `src/schemas/node.py` |
| The row | `node_feedback` (`src/models/node_feedback.py`, migration `0005`) |
| The signals | `bajar_dificultad` / `subir_dificultad` in `learner_profile_service.py` |

## Why it went

**Nobody could reach it.** `NodeFeedback.tsx` was imported by no screen — `NodeView.tsx`
included — so no build of the SPA ever rendered the question. `POST /nodes/{id}/feedback` was
the table's only writer, and it had no caller outside the integration test that exercised it
directly. Hence: `node_feedback` empty by construction, `_feedback_difficulty()` returning
`None` on every code path, and `NodeSignalContext.difficulty` a field that could only ever be
`None`.

**And it would not have worked even with a client.** The `difficulty` answer became the
`bajar_dificultad` / `subir_dificultad` signals in
`learner_profile_service.evaluate_signals`, which are stored in `learner_profiles.tutor_notes`.
A stored signal only turns into an instruction the generator can act on inside
`_SIGNAL_RULES`, and `_SIGNAL_RULES` is read in exactly one place: `build_ui_prompt`, the
legacy render path. The path that serves production is `build_episode_ui_prompt`, and it
never looks at signals at all. So a learner pressing "Difícil" would have written a row, and
the next screen would have been identical.

That is the whole reason this never worked, and it is a wiring problem, not a product one.

## What did **not** go

Difficulty inferred from what the learner actually does. `MasteryEvidenceService` builds a
`NodeSignalContext` after every graded answer from `consecutive_failed`,
`consecutive_correct`, the recent event types and the prerequisite graph, and the three
surviving signals of §3.3 (`reforzar_con_ejemplo`, `reducir_longitud_modulo`,
`revisar_prerrequisito`) are untouched. Measured difficulty was always the better signal;
what left was the self-reported half.

## What bringing it back well would take, in order

1. **Make signals reach the episode path first.** Until `build_episode_ui_prompt` consumes
   `signal_actions_for_node` the way `build_ui_prompt` does, no new signal changes anything a
   learner sees. Do this before adding a source, not after — it is verifiable on the three
   signals that already exist, with no new table and no new UI.
2. **Then decide whether self-reported difficulty adds anything** on top of measured
   evidence. It is a real question: a learner who answers everything right but found it
   exhausting is invisible to `consecutive_correct`. Answer it with the signals that already
   work before re-introducing a form.
3. **Only then**: the table, the endpoint, the two signals, and a component that is actually
   mounted. Whichever screen mounts it goes in the same commit as the component — a form no
   screen renders is what got us here.
4. If the free-text box comes back, `node_feedback.unclear` becomes the second place in the
   product where text the learner wrote is persisted (§3.3 of `v2-dynamic-courses.md`). That
   means it goes back into `ERASURE_ORDER` in `repositories/learner_profile_repo.py` and into
   `tests/test_gdpr_erasure.py` in the same change, not later.

## Related

- `docs/design/v2-dynamic-courses.md` §3.3 — the signal table, now annotated with the two
  retired rows.
- `apps/skillnet-api/alembic/versions/0036_drop_node_feedback.py` — the drop, with the
  downgrade that recreates the table exactly as `0005` had it.
