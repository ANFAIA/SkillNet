---
title: "Rich open-question generation"
order: 30
section: "core"
---

# Rich, multimodal generation — open questions

**Date:** 2026-08-09
**Status:** session notes. Nothing here is a decision. These are hypotheses and questions to
resolve once the ongoing deep research on NotebookLM closes.
**Origin:** work session on why generated courses come out poor.

---

## 1. What is already decided (do not redo)

The "one agent decides, another produces" architecture **already exists and is documented**.
Before proposing anything, read:

| What | Where |
|---|---|
| Planner + producers + assembler | `multi-agent-pipeline.md` §2-3 (Blueprint Architect, Content Writer, Interaction Designer, Assembler) |
| Frozen block vocabulary | `v2-dynamic-courses.md` §5.3 |
| Canonical IR `UISpec` and render adapter | `v2-dynamic-courses.md` §5.2, §5.4 |
| OpenUI decision, level (c) without reactivity | `openui-adoption.md` |
| Multimodal v3: Audio Script + Diagram Generator in parallel | `multi-agent-pipeline.md` §14 |
| Personalization: `format_vector`, learner profile, mastery | `v2-dynamic-courses.md` §3.3, §7 |

**Consequence:** the problem of poor courses is **not an agent-architecture problem**. That
layer is already designed. Look for the cause elsewhere.

---

## 2. The main hypothesis: the ceiling is in the vocabulary, not the pipeline

The frozen UI Kit (`v2-dynamic-courses.md` §5.3) declares **nine components emittable by
the LLM**: `Stack`, `TextContent`, `Card`, `Callout`, `StepSequence`, `Table`, `CodeBlock`,
`Chart`, `QuizItem`. Plus `Markdown`, which only the server writes.

Of those nine, **none produces explanatory visual content**:

- `Chart` only covers `bar` and `line` over numeric data. It is not a conceptual diagram.
- `ImageCard` is **explicitly excluded**, along with `Timeline`, `DragDrop`, `Simulation`
  and `SandboxHTML` (decision from 2026-07-26).

In other words: the model does not emit images or diagrams **because the dialect does not
allow it**. If this is correct, improving the Content Writer's prompt or switching models
will not move the needle, and it would explain why recent work on the UI has not resolved
the feeling of poverty.

**How to check this before touching anything:** take three real segment documents
(restaurant, accounting firm, clinic), generate the course today, and count the distribution
of emitted blocks. If the split is overwhelmingly `TextContent` + `QuizItem`, the hypothesis
holds and the problem is in the kit. If the model already uses `StepSequence`, `Table` and
`Callout` fluently and it still reads as poor, the cause is elsewhere and must be sought in
the quality of each block, not in the catalog.

That measurement is cheap and unblocks the decision. Do it first.

---

## 3. Open questions

### 3.1 Do the producers have their own grounding?

Do the Content Writer and the Interaction Designer retrieve their own source passages, or do
they only receive the blueprint from the Blueprint Architect?

If they only receive the blueprint, they are writing from memory about a brief, which is a
recipe for inventing plausible detail — exactly the kind of content that reads well and
teaches nothing.

**Verify in:** `apps/skillnet-api/src/agents/runtime/agents/` and the `genera_ui_multi`
subgraph.

### 3.2 Can a producer decline?

Today `multi-agent-pipeline.md` §6 covers **failures** (the agent crashes, is retried, falls
back to the monolithic path). It does not appear to cover **semantic rejection**: the
producer replying "this content does not support a diagram, it's a list of unrelated
requirements."

Without that path, once visual producers are added the planner will force bad diagrams, and
the result will be multimodal noise instead of better lessons. The rejection path is what
turns "more formats" into "better content."

This is a contract change between planner and producer, not the implementation of an agent.

### 3.3 Extracted image vs. generated image

These are two distinct problems and should not be mixed:

- **Generated** (image model, SVG, mermaid): useful for conceptual diagrams, flows,
  relationships. Note: for explanation, declarative generation (mermaid/SVG) is
  deterministic, versionable and cheap; an image model is not.
- **Extracted from the source document**: the photo of the actual machine, the actual dish,
  the actual form that is already inside the client's PDF.

For the target segments (restaurants, retail, accounting firms, clinics) the second is
probably worth more than the first, and today it is being discarded during ingestion. Check
whether the ingestion pipeline retains images from the sources or only extracts text.

### 3.4 Does it pad or produce less?

When the source is poor, does the pipeline generate less content and say so, or does it pad
to cover the course structure? Suspicion: it pads. If so, this is a cause of perceived
poverty independent of the vocabulary, and it is fixed in the review node, not in the kit.

### 3.5 Is v2 active?

Check the status of the feature flag (`v2-dynamic-courses.md` §10) in the environment where
the poor courses are being seen. If what is being judged is still the v1 monolithic
pipeline, everything above is moot and the answer is much simpler.

**Check this first of all.**

---

## 4. What the NotebookLM research contributes, and what it does not

The ongoing deep research is at
`Obsidian Vault/15_TRABAJO/SkillNet/07_ANFAIA/investigacion/notebooklm/`.

**What it will NOT give, because NotebookLM does not have it:**

- **Planner.** In NotebookLM the planner is the human: they decide which artifact they want
  and press the button. SkillNet cannot ask that of a restaurant manager, so the central
  piece of the problem is exactly the one the reference does not solve. It is already
  designed here (Blueprint Architect) and there is nothing to copy.
- **Learner model.** NotebookLM produces one artifact for whoever asks, with no profile, no
  mastery, no adaptation. All of that is proprietary (`format_vector`, pre-assessment,
  scaffolding escalation) and has no equivalent there.

**What it WILL give, and is what is being asked of it:**

- The **per-artifact quality mechanism**: what makes a mind map or a study guide come out
  good — fixed skeleton, output schema, critique pass, how much source each generation sees.
- The **output contract** of each artifact and how validity is enforced.
- The real **cost and latency** of audio and video, which is what decides whether v3 fits
  into a self-hosted SMB deployment.
- How a good product behaves when the source is weak (§3.4).

That is the material needed to decide the leap to v3, and that is why the research is read
**before** touching the kit.

---

## 5. Boundary note: this is not Oikolon

Oikolon (`investigacion/componentes_agentes/` in the vault) is Ismael's idea of UI
components that are autonomous agents **at runtime**, with lifecycle, permissions and DBP
boundaries.

What this document covers is a different thing: the division of labor **at generation time**
between a planner and block producers. The result of that generation is a static `UISpec`
that gets rendered and that's it.

They resemble each other in vocabulary ("components", "agents") and are not the same. Keep
them separate; if they ever converge, let it be by an explicit decision and not by confusion
of names.

---

## 6. Suggested order

1. Check the v2 feature flag (§3.5). Cheap, and may invalidate everything else.
2. Measure the block distribution with three real documents (§2).
3. Read the NotebookLM synthesis once it closes.
4. With 1-3 on the table, decide whether the kit should be extended and with what, and
   whether the planner-producer contract needs the rejection path.

None of this is decided before step 3.
