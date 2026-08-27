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

The bench runs the **real** pipeline (`run_node_render` → `build_node_graph()` → the eight
nodes of `src/agents/runtime/nodes.py`). It fakes exactly three seams — the DB session, SSE,
and a wrapper under `litellm.acompletion` that adds a User-Agent and backs off on 429. It
reports first-try / repaired / fallback / error rates, p50 and p95 latency, tokens and USD,
diffs against the previous run, and dumps every failed output with the validator's reason.
Useful flags: `--repeat`, `--only`, `--offline`, `--out`, `--compare`, `--pause`,
`--model` / `--model-fast` / `--model-heavy`, `--price-in` / `--price-out`,
`--dump-prompts`, `--list`, `--seed`.

**Every value below was read out of the file cited.** Line numbers drift; the constant
names do not, so grep for the name if the line is off.

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

The one real operational constraint is that **Groq's free tier returns 429 readily**. Any
measurement run needs backoff — the bench has it built in (`RATE_LIMIT_MAX_RETRIES = 5`,
`RATE_LIMIT_BASE_DELAY = 4.0`, `RATE_LIMIT_MAX_DELAY = 90.0`, `quality_bench.py:119-121`),
and it counts the waiting separately in `rate_limit_seconds` so a rate limit can never be
scored as a quality failure. If you write your own harness, do the same or your numbers are
noise.

---

## 1. Which model, and how much room it gets

`src/config.py`

| Dial | Line | Current | Turning it |
|---|---|---|---|
| `LLM_RUNTIME_FAST_MODEL` | 30 | `None` | The cheap tier. Empty means it falls back through `org_settings["llm_model"]` → `settings.LLM_MODEL`, so the whole feature works with one model configured. Raise it to a better model and *every* `explanation`/`exercise` render gets better and more expensive — that is ~90 % of renders by design. |
| `LLM_RUNTIME_HEAVY_MODEL` | 31 | `None` | The expensive tier, used only for `chart` / `mixed`. Same fallback chain. This is the cheapest place to buy quality, because so few renders route here. |
| `LLM_REASONING_EFFORT` | 41 | `"low"` | Only sent to reasoning models (o-series, gpt-oss, deepseek-reasoner). `none` never sends the parameter. Turning it up buys better structure on `chart`/`mixed` and costs thinking tokens billed against the same budget as the answer. |
| `LLM_REASONING_TOKEN_HEADROOM` | 45 | `2048` | Extra completion budget handed to a reasoning model *on top of* what the call site asked for, because the call site budgets the answer and cannot see the thinking. Measured failure this exists to fix: on `groq/openai/gpt-oss-120b` at `max_tokens=1200` the model sometimes spent the whole budget thinking and returned empty `content`, which the runtime read as an invalid program and sent through the repair loop for nothing. Lower it and that comes back; `0` disables the headroom entirely. |

`src/agents/runtime/router.py`

| Dial | Line | Current | Turning it |
|---|---|---|---|
| `HEAVY_FORMATS` | 36 | `{"chart", "mixed", "simulation"}` | Which formats route to the expensive tier. Adding `exercise` here is the blunt way to raise quality across the board; it also moves most of your traffic onto the expensive model, so check the fast/heavy ratio in `llm_usage_log` afterwards. |
| `ALLOWED_UI_FORMATS` | 40 | `{"explanation", "exercise", "chart", "mixed"}` | What `decide_formato` is allowed to return. Anything else is clamped by `coerce_ui_format`. `simulation` is deliberately absent: nothing in the frozen kit can render one. |

---

## 2. Prompts and budgets

`src/llm/prompts/runtime.py`

| Dial | Line | Current | Turning it |
|---|---|---|---|
| `PROMPT_VERSION` | 44 | `"runtime/2"` | Part of the `cache_key`. **Bump it whenever you change any prompt in this module in a way that changes output**, or you will be measuring stale cached renders and concluding your change did nothing. This is the cheapest cache invalidation there is — no DB writes. |
| `DECIDE_MAX_TOKENS` | 48 | `256` | Budget for `decide_formato`, which answers a one-line JSON object. There is no reason to raise it; if the decider is truncating, the prompt is wrong, not the budget. |
| `DECIDE_TEMPERATURE` | 49 | `0.0` | Format choice is a classification. Raising this makes the same node render differently for the same learner on different days, which also fragments the cache. |
| `UI_TEMPERATURE` | 52 | `0.4` | The content generation temperature. Down toward `0.0` for more syntactically reliable dialect and flatter prose; up for more varied examples and more repair-loop entries. This is the first dial to try when first-try validity is low. |
| `UI_MAX_TOKENS` | 57 | `{"fast": 1200, "heavy": 2400}` | Per-tier completion budget. A `chart`/`mixed` screen needs the room; a plain explanation does not, and paying for it on 90 % of renders is the whole reason the two tiers exist. If failures look like truncated programs, raise the tier that is truncating — but check `LLM_REASONING_TOKEN_HEADROOM` first if the model reasons. |
| `MAX_UI_RETRIES` | 261 | `2` | Two repair attempts, then `fallback_seed`. It was `1` until the adaptive-episode measurement showed a second attempt cutting the fallback rate for the cost of one extra generation on the hard cases only — see the comment on the constant itself. Beyond this, a model that keeps failing the same instructions is better served by the seed than by more budget, and the stronger lever is the repair header below. |
| `SOURCE_CONTEXT_MAX_CHARS` | 65 | `6000` | How much source text travels with `genera_ui` (`clip_source` trims at a whitespace boundary, never mid-word). Above this the prompt stops being about the node and starts being about the document. Lower it if the model is generating content from the wrong part of a long manual. |
| `_DENSITY_BUDGET` | 77 | 5 entries, 1–5 | The length budget in words, per `effective_density`. `1` = "2-3 bloques y frases muy cortas", `5` = "5-7 bloques". This is the text the model actually reads — edit the wording, not just the number of blocks. |
| `_SCAFFOLD_RULES` | 86 | `novice` / `neutral` / `advanced` | What each scaffolding band changes, stated as behaviour rather than as a label. `novice` demands a worked example before asking anything; `advanced` goes straight to edge cases. If advanced learners complain about being over-explained, this is the string to sharpen. |
| `_ERROR_RULES` | 102 | `detail` / `procedural` / `conceptual` | How `last_error_kind` changes the next screen (§7.4). |
| `_SIGNAL_RULES` | 119 | 5 actions | Closed vocabulary mapping `tutor_notes.signals` to instructions. Closed on purpose: a signal can never become free-form prose injected into a prompt (§3.3). Add an entry here *and* in the producer, never only here. |
| `FORMAT_DECIDER_SYSTEM` | 133 | — | The whole format-selection prompt. The hard rules that matter: no `chart` without real figures in the source, no `exercise` unless the node's expected outcome is an action, never `chart` alone on a `critical` node, and `explanation` when in doubt. If the heavy tier exceeds ~25 % of traffic, this prompt is over-choosing `chart`. |
| `_UI_REPAIR_HEADER` | 267 | — | The repair system prompt's header. The MAL/BIEN counterexample block is not decoration: measured against `qwen2.5:7b-instruct` (2026-07-26), the two syntax mistakes a small model makes are **named arguments** and **splitting one call over several lines**, both already forbidden in prose and made anyway. The last paragraph exists because the loop's real failure mode was *chasing the wrong bug* — the model rewriting correct quotes three attempts in a row. With one retry only, this header is where quality is bought. |

**The dialect fragment is never written by hand.** `ui_generator_system()` is
`src.render.prompt.render_prompt()` — the artefact generated from the frontend kit — plus
the answer-key protocol. Do not paste component signatures into this module; that is the
drift `tests/test_render_prompt_artifact.py` exists to catch.

---

## 3. The gate: what gets refused before parsing

`src/render/gate.py`. These are safety limits, not quality dials — but a program rejected
here shows up in the bench as a repair or a fallback, so they read like quality problems.

| Dial | Line | Current | Turning it |
|---|---|---|---|
| `MAX_PROGRAM_BYTES` | 47 | `16_384` | Total program size cap, enforced before anything expensive happens. A 12-component spec with long prose is ~4 kB, so this is generous. Bounds the work a poisoned document can ask of the parser and the browser. |
| `MAX_PROGRAM_LINES` | 50 | `MAX_COMPONENTS + 8` (= 20) | Counted in **logical** lines — declarations, joined across newlines that fall inside an open bracket (`src/render/lines.py::logical_lines`), which is where lang-core also splits statements. It used to count physical lines, so a correctly sized program with a blank line between declarations measured 23 and the model was told to shorten a lesson that was the right length. `MAX_COMPONENTS` is `12` (`src/render/spec.py:51`); the `+ 8` is slack for a fenced block and a repair attempt. |
| `MAX_LINE_BYTES` | 53 | `4_096` | One line is one component's worth of text. Note `FALLBACK_BLOCK_CHARS` below is set well under this on purpose. |
| `RENDER_ALLOW_REACTIVE` (`src/config.py:85`) | 85 | `False` | **Leave it off.** The price of switching it on is stated in `openui-adoption.md` §3: the model has to be taught the whole reactive syntax at once (the prompt flags do not split), and a structural property — "the grammar cannot express it" — degrades into a contract to re-verify on every `@openuidev` release. |

The reactivity check is deliberately light and textual: it blanks every string literal
first, then checks the remaining skeleton against the alphabet the frozen grammar can
produce. That order is the whole trick — a keyword grep over raw text has measured false
positives on legitimate prose ("en SQL una Query() se escribe con SELECT", "cuesta $300").

---

## 4. The mastery rule

`src/services/mastery_service.py`. Everything in this module is pure — no DB, no LLM, no
clock you did not pass in — because the rule that decides what a certificate says has to be
testable case by case. **Changing any of these changes what "mastered" means**, so change
them with the unit tests open.

| Dial | Line | Current | Turning it |
|---|---|---|---|
| `THRESHOLDS` | 37 | `critical 0.90`, `recommended 0.80`, `contextual 0.70` | The mastery bar per criticality. Depends on the node, never on the person (§7.2 rule 4). `course_nodes.mastery_threshold` overrides per node. Raising `critical` makes courses harder to complete — completion requires *every* non-archived critical node mastered. |
| `DOUBT_BAND_FLOOR` | 38 | `0.55` | Estimates at or above this but below 1.0 go to the tie-break instead of straight to `learning`. Lower it and more learners get a third, constructed item. |
| `W_APPLY` / `W_UNDERSTAND` | 39 | `0.6` / `0.4` | Weights of the two selected-response probe items. |
| `W3_APPLY` / `W3_UNDERSTAND` / `W3_CONSTRUCTED` | 42 | `0.45` / `0.15` / `0.40` | Renormalized tie-break weights. They sum to 1.0 deliberately: in the previous version the tie-break topped out at 0.80 and was dead code on a `critical` node. |
| `APPLY_FLOOR` | 44 | `0.5` | Failing the "apply" item can never yield mastery, whatever the other items say. This is the anti-guessing clause; do not lower it to make numbers look better. |
| `ALPHA` | 48 | `0.4` | Weight of new evidence in the EWMA. Higher = mastery reacts faster to the last answer and is noisier. |
| `FADING_STREAK` | 49 | `3` | N consecutive correct answers → mastery ceiling applied *and* eligible for `mastered`. The ceiling fixes a real arithmetic bug: `0.6*old + 0.4*score` has its fixed point at `score`, so a sustained 0.85 sat 0.05 below a critical node's threshold forever and the course was permanently unfinishable. Lowering this to 1 removes the "streak, not a lucky spike" defence against cognitive offloading. |
| `REGRESS_STREAK` | 50 | `2` | Consecutive failures before difficulty drops and `reforzar_con_ejemplo` is emitted. |
| `HINT_LIMIT` | 54 | `3` | Hints per item. A click-to-explain inside an unanswered `QuizItem` counts and consumes quota (§8.5). |
| `NEEDS_REVIEW_FAILURES` | 55 | `4` | Failures of the same item, after the hints are spent, before the node exits to `needs_review`. |
| `REPROBE_COOLDOWN_DAYS` | 59 | `7` | Re-probe only from `needs_review`, and only after this long. This is the anti-retry rule (§3.4). |
| `MASTERY_PRIOR` | 63 | `high 0.85`, `medium 0.55`, `low 0.25` | Seed for `learner_node_states.mastery` from `user_skills.level` (§7.1). A starting point for the EWMA and the scaffold band only — it never skips a node on its own. |
| `SKILL_LEVEL_MEDIUM_FLOOR` / `SKILL_LEVEL_HIGH_FLOOR` | 67 / 68 | `0.5` / `0.85` | `mastery` → `user_skills.level` on the way back out. |
| `TARGET_BLOOM` | 69 | `shu→understand`, `ha→apply`, `ri→analyze` | The cognitive level asked of the exercise, derived from where mastery sits relative to the threshold. Travels into `build_ui_prompt`. |

---

## 5. Runtime graph behaviour

`src/agents/runtime/nodes.py`

| Dial | Line | Current | Turning it |
|---|---|---|---|
| `RETRIEVAL_TOP_K` | 104 | `8` | Chunks retrieved for the `chunked` branch of `load_context`. Only reached for documents over `FULL_TEXT_PAGE_THRESHOLD` (`5` pages, `src/agents/content/helpers.py:20`); anything smaller goes in whole and needs no embeddings at all. Raising it feeds more source into a prompt that `SOURCE_CONTEXT_MAX_CHARS` will then clip, so raise both or neither. |
| `FALLBACK_BLOCK_CHARS` | 108 | `2800` | Size of each `Markdown` block in the seed fallback. Capped well below `MAX_LINE_BYTES` (4096) because the whole seed lesson lives on **one** line once serialized, escaped newlines and all. |
| `FALLBACK_MAX_BLOCKS` | 110 | `4` | Root fan-out is capped at 5 and the lead block takes one of them. |

`src/services/learner_profile_service.py`

| Dial | Line | Current | Turning it |
|---|---|---|---|
| `CALIBRATION_NODES` | 66 | `3` | Below this many completed nodes, `decide_formato` **makes no LLM call at all** and the format is `node.default_ui_format`. Not "asked and ignored" — asked and ignored would still cost a call. The reason is pedagogical, not economic: the learner has to build a mental map before the interface starts moving (the lesson of Office 2000's adaptive menus). Lowering it to 0 turns personalisation on from the first node and makes the bench's calibration cases stop exercising that branch. |

The bench corpus deliberately includes learners with `nodes_completed < 3`
(`extintor`, `prevencion-riesgos`) precisely so this branch is measured.

---

## 6. Working without an API key

`src/config.py`

| Dial | Line | Current | Turning it |
|---|---|---|---|
| `LLM_FIXTURE_DIR` | 49 | `"src/llm/fixture_data"` | Inside the package, so recorded fixtures ship in the Docker image. |
| `LLM_FIXTURE_MODE` | 50 | `"replay"` | `replay` serves recorded pairs; `record` calls the real provider and writes every `(prompt, response)` pair into the directory. Fixtures are activated by setting `LLM_MODEL=fixture/local` (and `EMBEDDING_MODEL=fixture/local`), not by this flag. |

`FixtureLLMService` resolves by exact hash of `(system, user)`, so a new corpus has no
recordings and would fail on the first call. Note the consequence for tuning: **changing a
prompt invalidates every fixture**. Re-record, or use `--offline`, which self-seeds.

---

## Where the numbers live afterwards

- `llm_usage_log` — per call: `use_case`, `purpose`, `model`, `tier`, `tokens_in`,
  `tokens_out`, `duration_ms`. This is what answers "is the fast/heavy ratio really 90/10".
- `node_renders` — per render: `tokens_*` and `duration_ms` for the *whole* render, both
  calls and every retry included.
- Token counts are `None`, never `0`, when nobody counted. `0` claims the call was free;
  coalescing the two would make an unmeasured cost model look measured.
