# Tuning the dynamic-course generator

The dials you turn when v2 output is wrong, and what each one actually does.

This is the companion to `apps/skillnet-api/scripts/quality_bench.py`, which is the only
honest way to tell whether a change helped. The loop is: turn one dial, run the bench,
read the failure dump. A percentage without the failures in front of it does not tell you
what to fix.

```bash
cd apps/skillnet-api
uv run python scripts/quality_bench.py --offline     # no key, checks the harness works
uv run python scripts/quality_bench.py --repeat 3    # real provider from .env
uv run python scripts/quality_bench.py --only extintor --model groq/openai/gpt-oss-120b
```

The bench runs the **real** pipeline: `run_node_render` → `build_node_graph()`
(`src/agents/runtime/graph.py`) → the render nodes in `src/agents/runtime/nodes.py`. Two of
those nodes are flag-gated (`direct_episode` under `ADAPTIVE_EPISODES`, and `genera_ui`
swapping to `genera_ui_multi` under `MULTI_AGENT_RENDER`), so the graph you measure is the
graph your flags build — read `build_node_graph` rather than counting nodes here. The bench
fakes exactly three seams — the DB session, SSE, and a wrapper under `litellm.acompletion`
that adds a User-Agent and backs off on 429. It reports first-try / repaired / fallback /
error rates, p50 and p95 latency, tokens and USD, diffs against the previous run, and dumps
every failed output with the validator's reason.

Useful flags: `--repeat`, `--only`, `--offline`, `--out`, `--compare`, `--pause`, `--arm`,
`--model` / `--model-fast` / `--model-heavy`, `--price-in` / `--price-out`,
`--dump-prompts`, `--list`, `--seed`, plus a `--pack-*` family that overrides the
knowledge-pack dials for one run (see §7).

**Every value below was read out of the module named above it, and re-verified against the
code on 2026-08-27.** There are deliberately no line numbers — see *Why there is no "Line"
column* at the end of this page. Constant names are stable and greppable; grep for the name.

---

## What we measured, and what it means for tuning

Measured against real Groq on 2026-07-27 (`groq/llama-3.1-8b-instant` as the fast tier,
`groq/openai/gpt-oss-120b` as the heavy one): **sub-second to about 3 s per render, at
roughly 0.0008 USD per render**, with token accounting populated.

The "20-30 second generation" problem the research phase assumed **does not exist on this
stack**. The 60-150 s figures in the internal sources came from a 7B model on local CPU.
This matters for tuning because it removes the reason to pre-generate, to add waiting
layers, or to trade quality for latency: there is no latency budget under pressure. Spend
the dials on *correctness*, not on speed.

**Do not read "about 3 s" as the current number.** It was measured on 2026-07-27, on Groq,
against prompts that have since grown worked examples, criticality rules, a dossier and a
higher token budget. Bench runs on the fallback fix of 2026-08-27 sat at **p50 ≈ 7.1-7.7 s**
(see §5). The conclusion survives — nothing here is under latency pressure — but the figure
is a historical reading, not a target, and any comparison you make needs its own baseline
from `--compare`.

The one real operational constraint is that **Groq's free tier returns 429 readily**. Any
measurement run needs backoff — the bench has it built in (`RATE_LIMIT_MAX_RETRIES = 5`,
`RATE_LIMIT_BASE_DELAY = 4.0`, `RATE_LIMIT_MAX_DELAY = 90.0`, in `scripts/quality_bench.py`),
and it counts the waiting separately in `rate_limit_seconds` so a rate limit can never be
scored as a quality failure. If you write your own harness, do the same or your numbers are
noise.

---

## 1. Which model, and how much room it gets

`src/config.py`

| Dial | Current | Turning it |
|---|---|---|
| `LLM_RUNTIME_FAST_MODEL` | `None` | The cheap tier. Empty means it falls back through `org_settings["llm_model"]` → `settings.LLM_MODEL`, so the whole feature works with one model configured. Raise it to a better model and *every* `explanation`/`exercise` render gets better and more expensive — that is ~90 % of renders by design. |
| `LLM_RUNTIME_HEAVY_MODEL` | `None` | The expensive tier, used only for `chart` / `mixed`. Same fallback chain. This is the cheapest place to buy quality, because so few renders route here. |
| `LLM_REASONING_EFFORT` | `"low"` | Only sent to reasoning models (o-series, gpt-oss, deepseek-reasoner). `none` never sends the parameter. Turning it up buys better structure on `chart`/`mixed` and costs thinking tokens billed against the same budget as the answer. |
| `LLM_REASONING_TOKEN_HEADROOM` | `2048` | Extra completion budget handed to a reasoning model *on top of* what the call site asked for, because the call site budgets the answer and cannot see the thinking. Measured failure this exists to fix: on `groq/openai/gpt-oss-120b` at `max_tokens=1200` (the fast tier's budget at the time) the model sometimes spent the whole budget thinking and returned empty `content`, which the runtime read as an invalid program and sent through the repair loop for nothing. Lower it and that comes back; `0` disables the headroom entirely. |

`src/agents/runtime/router.py`

| Dial | Current | Turning it |
|---|---|---|
| `HEAVY_FORMATS` | `{"chart", "mixed", "simulation"}` | Which formats route to the expensive tier. Adding `exercise` here is the blunt way to raise quality across the board; it also moves most of your traffic onto the expensive model, so check the fast/heavy ratio in `llm_usage_log` afterwards. |
| `ALLOWED_UI_FORMATS` | `{"explanation", "exercise", "chart", "mixed"}` | What `decide_formato` is allowed to return. Anything else is clamped by `coerce_ui_format`. `simulation` is deliberately absent: nothing in the frozen kit can render one — which is also why it can sit in `HEAVY_FORMATS` harmlessly. |

---

## 2. Prompts and budgets

`src/llm/prompts/runtime.py`

| Dial | Current | Turning it |
|---|---|---|
| `PROMPT_VERSION` | `"runtime/42"` | Part of the `cache_key`. **Bump it whenever you change any prompt in this module in a way that changes output**, or you will be measuring stale cached renders and concluding your change did nothing. This is the cheapest cache invalidation there is — no DB writes. Forty-two bumps is not churn: the constant carries a dated changelog above it in the module, and reading the last few entries is the fastest way to learn what the prompt has already been taught not to do. |
| `EPISODE_PROMPT_VERSION` | `"episode/10"` | The same mechanism for the **episodic** path (`ADAPTIVE_EPISODES`), which has its own prompt and therefore its own cache partition. Change an episode prompt and bump this one, not `PROMPT_VERSION`. It also has its own changelog above it — `episode/3` is where an episode stopped being one screen, and `episode/10` is where the learner's free-text `learning_note` started steering style. |
| `DECIDE_MAX_TOKENS` | `512` | Budget for `decide_formato`, which answers a one-line JSON object. It was `256` and doubled in `0e31361` along with the prompt expansion, with no measurement recorded for the budget itself — so treat 512 as headroom nobody has needed to defend, not as a tuned value. If the decider truncates, suspect the prompt before the budget. (The module docstring still says `max_tokens=256`; the constant is the truth.) |
| `DECIDE_TEMPERATURE` | `0.0` | Format choice is a classification. Raising this makes the same node render differently for the same learner on different days, which also fragments the cache. |
| `UI_TEMPERATURE` | `0.4` | The content generation temperature. Down toward `0.0` for more syntactically reliable dialect and flatter prose; up for more varied examples and more repair-loop entries. This is the first dial to try when first-try validity is low. |
| `UI_MAX_TOKENS` | `{"fast": 1400, "heavy": 2800}` | Per-tier completion budget, raised from `1200`/`2400` in `0e31361` when the prompts grew worked examples. A `chart`/`mixed` screen needs the room; a plain explanation does not, and paying for it on 90 % of renders is the whole reason the two tiers exist. If failures look like truncated programs, raise the tier that is truncating — but check `LLM_REASONING_TOKEN_HEADROOM` first if the model reasons. |
| `MAX_UI_RETRIES` | `2` | Two repair attempts, then `fallback_seed`. It was `1` until the adaptive-episode measurement showed a second attempt cutting the fallback rate for the cost of one extra generation on the hard cases only — see the comment on the constant itself. Beyond this, a model that keeps failing the same instructions is better served by the seed than by more budget, and the stronger lever is the repair header below. |
| `SOURCE_CONTEXT_MAX_CHARS` | `6000` | How much source text travels with `genera_ui` (`clip_source` trims at a whitespace boundary, never mid-word). Above this the prompt stops being about the node and starts being about the document. Lower it if the model is generating content from the wrong part of a long manual. |
| `_DENSITY_BUDGET` | 5 entries, 1–5 | The length budget per `effective_density`, in blocks. `1` = "2-3 bloques y frases muy cortas"; `5` = "5 bloques bien aprovechados", explicitly "cinco es el techo". **Density buys depth, never a sixth block** — and that is a measured correction, not a preference. Until 2026-07-27 entry 4 asked for "4-6 bloques" and entry 5 for "5-7", above the validator's root cap of 5: on the 30-render baseline of that date, "the root level holds at most 5 elements (got 6/7)" was 2 of the 14 fallbacks, and the model was doing exactly what this table told it. If you raise a number here, check it against `MAX_COMPONENTS` and the root fan-out first. This is the text the model reads — edit the wording, not just the number. |
| `_SCAFFOLD_RULES` | `novice` / `neutral` / `advanced` | What each scaffolding band changes, stated as behaviour rather than as a label. `novice` demands a worked example before asking anything; `advanced` goes straight to edge cases. If advanced learners complain about being over-explained, this is the string to sharpen. |
| `_CRITICALITY_RULES` | `critical` / `recommended` / `contextual` | How node criticality reaches the model — **as behaviour, never as its label**, and that phrasing is the fix for the highest-frequency validation failure on record. Measured on the 30-render baseline of 2026-07-28: eight rejections of the form `prop 'tone' must be one of: info, warn, success (got 'critical')`, plus `'recommended'` and `'contextual'`. The user prompt was handing the model the bare enum token on a line reading `- Criticidad: critical`, four lines above a catalogue entry whose first argument is an enum; the model was copying the only enum-shaped word in front of it into the only enum slot it had. A prohibition in the system prompt (`SkillNet 16`) was already there and did not stop it. **The lesson generalises: removing the token beats forbidding the mistake.** |
| `_ERROR_RULES` | `detail` / `procedural` / `conceptual` | How `last_error_kind` changes the next screen (§7.4). |
| `_SIGNAL_RULES` | 5 actions | Closed vocabulary mapping `tutor_notes.signals` to instructions (`reforzar_con_ejemplo`, `bajar_dificultad`, `subir_dificultad`, `reducir_longitud_modulo`, `revisar_prerrequisito`). Closed on purpose: a signal can never become free-form prose injected into a prompt (§3.3). Add an entry here *and* in the producer, never only here. |
| `_HISTORY_SUPPORT_RULES` | `hints` / `worked-example` | What evaluated evidence from *earlier* nodes asks of this screen: a graduated hint before the answer, or a short worked example followed by an analogous practice. Same objective and same source facts either way — this dial changes support, never content. |
| `FORMAT_DECIDER_SYSTEM` | — | The whole format-selection prompt. The hard rules that matter: no `chart` without real figures in the source, no `exercise` unless the node's expected outcome is an action, never `chart` alone on a `critical` node, and `explanation` when in doubt. If the heavy tier exceeds ~25 % of traffic, this prompt is over-choosing `chart`. |
| `_UI_REPAIR_HEADER` | — | The repair system prompt's header. The MAL/BIEN counterexample block is not decoration: measured against `qwen2.5:7b-instruct` (2026-07-26), the two syntax mistakes a small model makes are **named arguments** and **splitting one call over several lines**, both already forbidden in prose and made anyway. The last paragraph exists because the loop's real failure mode was *chasing the wrong bug* — the model rewriting correct quotes three attempts in a row. With a budget as small as two retries, this header is where quality is bought. |

**The dialect fragment is never written by hand.** `ui_generator_system()` is
`src.render.prompt.render_prompt()` — the artefact generated from the frontend kit — plus
the answer-key protocol. Do not paste component signatures into this module; that is the
drift `tests/test_render_prompt_artifact.py` exists to catch.

---

## 3. The gate: what gets refused before parsing

`src/render/gate.py`. These are safety limits, not quality dials — but a program rejected
here shows up in the bench as a repair or a fallback, so they read like quality problems.

| Dial | Current | Turning it |
|---|---|---|
| `MAX_PROGRAM_BYTES` | `16_384` | Total program size cap, enforced before anything expensive happens. A 12-component spec with long prose is ~4 kB, so this is generous. Bounds the work a poisoned document can ask of the parser and the browser. |
| `MAX_PROGRAM_LINES` | `MAX_COMPONENTS + 8` (= 20) | Counted in **logical** lines — declarations, joined across newlines that fall inside an open bracket (`src/render/lines.py::logical_lines`), which is where lang-core also splits statements. It used to count physical lines, so a correctly sized program with a blank line between declarations measured 23 and the model was told to shorten a lesson that was the right length. `MAX_COMPONENTS` is `12` (`src/render/spec.py`); the `+ 8` is slack for a fenced block and a repair attempt. |
| `MAX_LINE_BYTES` | `4_096` | One line is one component's worth of text. `FALLBACK_BLOCK_CHARS` (§5) sits far below it, and for a reason that is no longer this one — see there. |
| `RENDER_ALLOW_REACTIVE` (in `src/config.py`) | `False` | **Leave it off.** The price of switching it on is stated in `openui-adoption.md` §3: the model has to be taught the whole reactive syntax at once (the prompt flags do not split), and a structural property — "the grammar cannot express it" — degrades into a contract to re-verify on every `@openuidev` release. |

The reactivity check is deliberately light and textual: it blanks every string literal
first, then checks the remaining skeleton against the alphabet the frozen grammar can
produce. That order is the whole trick — a keyword grep over raw text has measured false
positives on legitimate prose ("en SQL una Query() se escribe con SELECT", "cuesta $300").

**The same order has a known blind spot, and it cost a learner.** Blanking string literals
means the gate never looks inside prose, so `[must.atom:1]` — a reference the *server*
minted for its own dossier — travelled inside a `TextContent` and was read on screen
mid-course. There is a second, structural check in `src/agents/runtime/nodes.py` for exactly
that: the `must.` / `selectable.` namespaces the pack generator installs, and bracketed
`[word:12]` refs, with enough shape to leave "los invariantes de un bucle", `[1:30]` and
`[Juan 3:16]` alone. A hit sends the render to **repair, not to a cleanup**: the marker is
the visible symptom of a screen that transcribed the scaffolding instead of teaching from
it, and deleting the token would leave prose nobody wrote for a learner either. If you add
a new server-minted marker anywhere, add it here too.

---

## 4. The mastery rule

`src/services/mastery_service.py`. Everything in this module is pure — no DB, no LLM, no
clock you did not pass in — because the rule that decides what a certificate says has to be
testable case by case. **Changing any of these changes what "mastered" means**, so change
them with the unit tests open.

| Dial | Current | Turning it |
|---|---|---|
| `THRESHOLDS` | `critical 0.90`, `recommended 0.80`, `contextual 0.70` | The mastery bar per criticality. Depends on the node, never on the person (§7.2 rule 4). `course_nodes.mastery_threshold` overrides per node. Raising `critical` makes courses harder to complete, but it no longer *blocks* completion on its own: `node_is_done` counts a node as done when it is mastered **or** has a `completed_at` (migration 0029), and criticality does not gate closure. What the threshold still governs is `score`, the mean of *measured* mastery — the number a certificate prints. |
| `DOUBT_BAND_FLOOR` | `0.55` | Estimates at or above this but below 1.0 go to the tie-break instead of straight to `learning`. Lower it and more learners get a third, constructed item. |
| `W_APPLY` / `W_UNDERSTAND` | `0.6` / `0.4` | Weights of the two selected-response probe items. |
| `W3_APPLY` / `W3_UNDERSTAND` / `W3_CONSTRUCTED` | `0.45` / `0.15` / `0.40` | Renormalized tie-break weights. They sum to 1.0 deliberately: in the previous version the tie-break topped out at 0.80 and was dead code on a `critical` node. |
| `APPLY_FLOOR` | `0.5` | Failing the "apply" item can never yield mastery, whatever the other items say. This is the anti-guessing clause; do not lower it to make numbers look better. |
| `ALPHA` | `0.4` | Weight of new evidence in the EWMA. Higher = mastery reacts faster to the last answer and is noisier. |
| `FADING_STREAK` | `3` | N consecutive correct answers → mastery ceiling applied *and* eligible for `mastered`. The ceiling fixes a real arithmetic bug: `0.6*old + 0.4*score` has its fixed point at `score`, so a sustained 0.85 sat 0.05 below a critical node's threshold forever and the course was permanently unfinishable. Lowering this to 1 removes the "streak, not a lucky spike" defence against cognitive offloading. |
| `REGRESS_STREAK` | `2` | Consecutive failures before difficulty drops and `reforzar_con_ejemplo` is emitted. |
| `HINT_LIMIT` | `3` | Hints per item. A click-to-explain inside an unanswered `QuizItem` counts and consumes quota (§8.5). |
| `WORKED_SOLUTION_FAILURES` | `4` | Failures of the same item before the worked solution is handed over and the learner moves on (rule 8 of §7.3). Independent of `HINT_LIMIT` on purpose: hints are a disclosure budget, these failures are evidence the item is not working. Was `NEEDS_REVIEW_FAILURES`, and did require the hints to be spent first — both changed on 2026-08-28, see `future-progression-modes.md`. |
| `MASTERY_PRIOR` | `high 0.85`, `medium 0.55`, `low 0.25` | Seed for `learner_node_states.mastery` from `user_skills.level` (§7.1). A starting point for the EWMA and the scaffold band only — it never skips a node on its own. |
| `SKILL_LEVEL_MEDIUM_FLOOR` / `SKILL_LEVEL_HIGH_FLOOR` | `0.5` / `0.85` | `mastery` → `user_skills.level` on the way back out. |
| `TARGET_BLOOM` | `shu→understand`, `ha→apply`, `ri→analyze` | The cognitive level asked of the exercise, derived from where mastery sits relative to the threshold. Travels into `build_ui_prompt`. |

**One dial was removed rather than retuned (2026-08-28).** `REPROBE_COOLDOWN_DAYS` (`7`) gated
the re-probe on "only from `needs_review`, and only after this long". Migration `0033` removed
the `needs_review` state, so the first half of that gate can never hold again and a cooldown on
its own decides nothing — keeping it would have widened the rule into "anyone may re-probe a node
they already mastered, one week later". `probe_service._authorize_reprobe` now refuses
unconditionally, and which condition should replace the state is a product decision, not a dial.

---

## 5. Runtime graph behaviour

`src/agents/runtime/nodes.py`

| Dial | Current | Turning it |
|---|---|---|
| `RETRIEVAL_TOP_K` | `8` | Chunks retrieved for the `chunked` branch of `load_context`. Only reached for documents over `FULL_TEXT_PAGE_THRESHOLD` (`5` pages, `src/agents/content/helpers.py`); anything smaller goes in whole and needs no embeddings at all. Raising it feeds more source into a prompt that `SOURCE_CONTEXT_MAX_CHARS` will then clip, so raise both or neither. |
| `FALLBACK_BLOCK_CHARS` | `300` | Size of each `Markdown` block in the seed fallback. **The binding constraint is the viewport, not `MAX_LINE_BYTES`.** It was `2800` — sized only to stay under the 4096-byte line cap, because the whole seed lesson lives on one line once serialized — and that produced a wall of text where a degraded screen should be. The fallback is a safety net, not a document viewer: one lead plus at most two short blocks, and a long source lesson gets cut, not shown. |
| `FALLBACK_MAX_BLOCKS` | `2` | Was `4`, on the reasoning that the root fan-out is capped at 5 and the lead block takes one. That reasoning answered "how many blocks are *allowed*", which is the wrong question for a fallback; `2` answers "how much fits on one screen without scrolling". |

Two things about the fallback that are not dials but decide what these two cut up:

- **The content chain is seed lesson → node summary → an honest "we could not prepare this
  node".** It used to fall through to `state["source_context"]`, which is the *server
  prompt* — and a course authored natively in v2 has no v1 seed lesson, so every failed node
  of such a course wrapped the dossier in `Markdown` blocks and served it. A learner reported
  reading `## Invariantes` and `[must.atom:1]` on screen mid-course. `source_context` is no
  longer a content source anywhere in that module.
- **A fallback is now marked as a failed render**, rather than left looking like a healthy
  screen. That is what makes the fallback rate in the bench and in `node_renders` mean
  anything.

When that leak was found, `node_renders` was 17 fallback / 17 ready — a 50 % fallback rate —
and grouping the rejections said the component rule everyone was staring at accounted for 1
of 7 exhausted loops. 85 % were `implementation_ref must pin a version`, from two bugs
neither of which is a dial: a server-side ref rewrite that was a no-op on the production path
(two readers of one dict with different fallbacks), and an **unsatisfiable rule** — the prompt
said "cierra con DragOrder" while the guard forbade it, so no obedient model and no extra
retry could ever pass. **The lesson for tuning: group the rejection reasons before turning
anything.** The dial you are reaching for is usually not where the mass is.

```
before  n=20  first-try 10  repaired 8  fallback 2  p50 7.73s  12575 tok
after   n=20  first-try 13  repaired 7  fallback 0  p50 7.09s  10652 tok
again   n=20  first-try 14  repaired 6  fallback 0  p50 7.20s  10276 tok
```

An intermediate run with only the *wording* fixed scored **worse** — five fallbacks, all
"prohibido DragOrder". That run is what exposed the second cause, and it is the argument for
running the bench between every single change rather than at the end of a batch.

And a warning about the bench itself: none of the above was measurable at first, because 20
of 20 runs came back as infra errors — `BenchSession` had no `media_artifacts` stub. **A
bench that fails uniformly looks like a bench that found nothing.** Check the error column
before you believe a flat result.

`src/services/node_render_service.py` — how much a degraded screen is allowed to cost. A
`fallback` pin used to be permanent: `NodeView` stops asking for a render once one is served,
so the first transient failure kept a learner on the backup content for good, measurably while
two clean renders of the same node already existed. `GET /nodes/{id}/render` now asks for one
background regeneration on the same `cache_key`, and these two dials bound the bill. A `ready`
pin is never re-resolved — that is the pin doing its job.

| Dial | Current | Turning it |
|---|---|---|
| `FALLBACK_RETRY_MAX_ATTEMPTS` | `3` | Regenerations a single `cache_key` ever gets. Three spread over the cooldown recover a provider outage of about half an hour; past that the failure is not transient, and the learner keeps the backup content for free rather than paying a generation per page view for a node that fails deterministically. Raising it spends real tokens on exactly the nodes least likely to succeed. |
| `FALLBACK_RETRY_COOLDOWN_SECONDS` | `600.0` | Wait between attempts on one key. Lower it and a stampede of learners on the same node turns every view into a generation; raise it and a provider that recovers in two minutes still serves degraded screens for longer. In-memory, single-worker — the same assumption `_INFLIGHT` already makes — so a restart refunds the budget, which only ever costs retries. `reset_fallback_retries()` clears it by key or wholesale, for tests and for ops. |

`src/services/learner_profile_service.py`

| Dial | Current | Turning it |
|---|---|---|
| `CALIBRATION_NODES` | `3` | Below this many completed nodes, `decide_formato` **makes no LLM call at all** and the format is `node.default_ui_format`. Not "asked and ignored" — asked and ignored would still cost a call. The reason is pedagogical, not economic: the learner has to build a mental map before the interface starts moving (the lesson of Office 2000's adaptive menus). Lowering it to 0 turns personalisation on from the first node and makes the bench's calibration cases stop exercising that branch. |

The bench corpus deliberately includes learners with `nodes_completed < 3`
(`extintor`, `prevencion-riesgos`) precisely so this branch is measured.

---

## 6. Working without an API key

`src/config.py`

| Dial | Current | Turning it |
|---|---|---|
| `LLM_FIXTURE_DIR` | `"src/llm/fixture_data"` | Inside the package, so recorded fixtures ship in the Docker image. |
| `LLM_FIXTURE_MODE` | `"replay"` | `replay` serves recorded pairs; `record` calls the real provider and writes every `(prompt, response)` pair into the directory. Fixtures are activated by setting `LLM_MODEL=fixture/local` (and `EMBEDDING_MODEL=fixture/local`), not by this flag. |

`FixtureLLMService` resolves by exact hash of `(system, user)`, so a new corpus has no
recordings and would fail on the first call. Note the consequence for tuning: **changing a
prompt invalidates every fixture**. Re-record, or use `--offline`, which self-seeds.

---

## 7. Knowledge packs: dials this page does not yet catalogue

`src/knowledge_pack/generator.py` is a two-pass, pure generator (extractor → reviewer) that
stops at a validated pack, with no database, delivery or OpenUI dependency. It has its own
budgets — `EXTRACTOR_MAX_TOKENS` and `REVIEWER_MAX_TOKENS` are both `3_200`, clamped between
`MIN_GENERATION_TOKENS = 256` and `MAX_GENERATION_TOKENS = 4_096` — and the bench can
override them and the acceptance bars for one run via `--pack-extractor-tokens`,
`--pack-reviewer-tokens`, `--pack-min-invariants`, `--pack-max-atoms`,
`--pack-min-fact-coverage`, `--pack-require-evidence` and `--pack-source`.

Two things worth knowing before you use those flags. The bench's own defaults for the two
token budgets are `1_600`, i.e. **half** the module's — so a `--pack-*` run is not measuring
the production configuration unless you say so. And `--pack-min-fact-coverage` defaults to
`1.0`, a bar that demands every extracted fact be covered; that is deliberate and it is
strict, so a pack failing the bench is not automatically a pack that would fail in
production.

The design and the measured gate live in [`node-knowledge-packs.md`](node-knowledge-packs.md);
what that page does not carry is a dial table. Cataloguing them here is pending, and this
section exists so nobody concludes from a table's absence that there are no dials.

---

## Why there is no "Line" column

There was one, for every dial, and it was removed on 2026-08-27 after being checked against
the code. **Of 45 line citations, 28 were wrong.** The 17 that were right were almost all in
one table — `mastery_service.py`, a file that has barely moved — so a reader could not even
calibrate a rule of thumb like "probably a bit low".

Wrong is also not harmless here, because a stale line number does not land nowhere. It lands
somewhere real:

- `LLM_RUNTIME_FAST_MODEL` / `_HEAVY_MODEL` were cited at `src/config.py:30-31`, which today
  holds `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` — two plausible-looking settings.
- `_UI_REPAIR_HEADER` was cited at line 267 and lives at 1267. Line 267 is the middle of a
  comment about the answer-key separator.
- `PROMPT_VERSION` was cited at line 44, which is an `import`.

So the column cost a lookup, then cost trust, and then cost a second lookup by name anyway —
which is what the previous version of this page already told you to do ("grep for the name if
the line is off"). A field whose own instructions say to ignore it has no job.

The alternative was to update all 45 and accept they would rot again. It was rejected because
the rot is not incidental: these are files under active work, so the column is stale within
weeks of any refactor, and nothing in CI can notice. **The module path stays** — one per
table, above it — because a path is stable, and a constant name is a stable, unique,
greppable address inside it. The values do not get this excuse: a value is checkable against
the code in seconds and is the entire reason this page exists.

---

## Where the numbers live afterwards

- `llm_usage_log` — per call: `use_case`, `purpose`, `model`, `tier`, `tokens_in`,
  `tokens_out`, `duration_ms`. This is what answers "is the fast/heavy ratio really 90/10".
- `node_renders` — per render: `tokens_*` and `duration_ms` for the *whole* render, both
  calls and every retry included.
- Token counts are `None`, never `0`, when nobody counted. `0` claims the call was free;
  coalescing the two would make an unmeasured cost model look measured.
