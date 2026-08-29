---
title: "Multi-agent pipeline"
order: 28
section: "core"
---

# Multi-Agent Render Pipeline

> **Status: design of the current render pipeline; migration approved.** This document keeps
> the history and operational detail of the subgraph that splits the monolithic `genera_ui`
> node into four specialized agents, defines the pre-generation and streaming strategy, and
> lays out the roadmap toward the multimodal format.
>
> For new work, the target architecture moves the expensive work to generation/publishing,
> lets the runtime pick prepared variants, and uses a neutral boundary. It's defined in
> [`learning-experience-architecture.md`](/en/docs/learning-experience-architecture) and takes
> precedence over this document in that direction. Until its gates are met, this page keeps
> describing the implemented pipeline.

Depends on: [v2-dynamic-courses.md](/en/docs/dynamic-courses),
[openui-adoption.md](/en/docs/openui-adoption), [tuning.md](/en/docs/tuning), and
[learning-experience-architecture.md](/en/docs/learning-experience-architecture).

---

## Table of contents

1. [Why split it up](#1-por-que-segmentar)
2. [The pipeline](#2-el-pipeline)
3. [The four agents](#3-los-cuatro-agentes)
4. [Pre-generation strategy](#4-estrategia-de-pre-generacion)
5. [Streaming as a safety net](#5-streaming-como-red-de-seguridad)
6. [Failure handling](#6-manejo-de-fallos)
7. [The philosophy: the learner never waits](#7-la-filosofia-el-aprendiz-nunca-espera)
8. [SSE and partial streaming](#8-sse-y-streaming-parcial)
9. [New subgraph: `genera_ui_multi`](#9-nuevo-subgrafo-genera_ui_multi)
10. [Feature flag and migration](#10-feature-flag-y-migracion)
11. [Cache key](#11-cache-key)
12. [Per-agent token breakdown](#12-detalle-de-tokens-por-agente)
13. [Tests](#13-tests)
14. [Multimodal future (v3)](#14-futuro-multimodal-v3)
15. [Design decisions](#15-decisiones-de-diseno)
16. [Implementation checklist](#16-checklist-de-implementacion)

---

## 1. Why split it up

### 1.1 The measured problem

The `genera_ui` node does EVERYTHING in a single LLM call:

1. Decides what structure the screen should have (how many blocks, of what type, in what order).
2. Writes the pedagogical content (the explanation, the examples, the data).
3. Creates the assessment questions (QuizItem, DragOrder).
4. Generates the correct answers (answer key).
5. Produces the valid OpenUI Lang program.

Measured on the quality bench (`scripts/quality_bench.py`, 2026-08-06):

| Metric | Current value |
|---------|-------------|
| Catalog coverage | 6-7 of 22 types (27-32%) |
| Types per screen (average) | 3.9-4.3 |
| First-try success | 28-67% (varies between runs) |
| Repairs needed | 11-57% |
| Fallbacks | 14-22% |
| Never-used blocks | BeforeAfter, DragOrder, Tabs, StepByStepReveal, Chart, Accordion... |

The model always produces the same three blocks (Stack + TextContent + QuizItem) because
the prompt asks it to decide the structure AND write the content AND formulate questions
in a single output. An 8B model doesn't have the capacity to attend to all three tasks in
parallel with quality.

### 1.2 The solution

Four agents, with Content Writer and Interaction Designer running **in parallel**:

```
Blueprint Architect (~1s)
        |
    +---+---+
    |       |
Content   Interaction    (parallel via asyncio.gather, ~2s)
Writer    Designer
    |       |
    +---+---+
        |
    Assembler (instant, no LLM)
        |
    Validate + Persist
```

Each agent has a single responsibility, a short prompt, and a validatable output.

### 1.3 Critical constraint: Groq free tier

Groq's free tier has a ceiling of 6,000 tokens per minute (TPM). The monolithic
`genera_ui` already averages ~5,250 input tokens. Three sequential LLM calls would
triple the TPM. The solution:

- **Agent 1 (Blueprint):** ~1,200 input tokens, ~300 output tokens. Compact JSON.
- **Agent 2 (Content):** ~2,500 input tokens, ~600 output tokens. Content blocks only.
- **Agent 3 (Interactions):** ~2,000 input tokens, ~400 output tokens. Interactive blocks + answer key only.
- **Agent 4 (Assembler):** 0 tokens. Pure Python.

Total: ~5,700 input tokens + ~1,300 output tokens = ~7,000 tokens.
Versus the monolithic version: ~5,250 input + ~800 output = ~6,050 tokens.

The difference is ~1,000 tokens (+16%), acceptable because:
1. Repairs are eliminated (which cost a full second call).
2. The source is sent ONCE (to Agent 2), not across all three calls.
3. The blueprint is compact JSON, not OpenUI dialect.

Agents 2 and 3 run in **PARALLEL** via `asyncio.gather`. Both receive the blueprint
and work independently. The Assembler waits for both. With OpenAI there's no
TPM constraint. If Groq free tier is used, a flag sequences them with a ~15s gap.

---

## 2. The pipeline

### 2.1 Full diagram

```
Blueprint Architect (LLM, JSON mode, ~500 output tokens, ~1s)
        |
    +---+---+
    |       |
Content   Interaction      (parallel via asyncio.gather, ~2s)
Writer    Designer
(LLM,     (LLM,
 stream,   ~400 tok out)
 ~600 tok)
    |       |
    +---+---+
        |
    Assembler (no LLM, instant)
        |
    Validate (gate.canonicalize)
        |
    Persist (node_renders)
```

### 2.2 What each agent does

| Agent | LLM | Input | Output | Responsibility |
|--------|-----|---------|--------|-----------------|
| **Blueprint Architect** | Yes (JSON mode) | Node metadata + learner profile + format + shape hints | JSON blueprint: which components, in what order, with what intent | Decide the STRUCTURE. Doesn't write content or questions. Picks the component based on the shape of the material (list -> Table, procedure -> StepByStepReveal, comparison -> BeforeAfter, multiple aspects -> Tabs). |
| **Content Writer** | Yes (streaming) | Blueprint + source document | OpenUI Lang declarations for content blocks (TextContent, Table, StepByStepReveal, Tabs, Callout, etc.) | Write the educational CONTENT. Specialized in pedagogical writing. Streams so the frontend can show blocks progressively. |
| **Interaction Designer** | Yes | Blueprint + source context + learner profile | OpenUI Lang declarations for interactive blocks (QuizItem, DragOrder) + answer key | Create QUESTIONS with plausible distractors. Runs in PARALLEL with the Content Writer. |
| **Assembler** | No | Content Writer + Interaction Designer outputs | Complete OpenUI Lang program + answer key | Merge the outputs, resolve the `root.children` list according to the blueprint order, validate via `gate.canonicalize()`, persist the render. |

---

## 3. The four agents

### 3.1 Agent 1: Blueprint Architect

**Responsibility:** Decide the screen's structure: how many blocks, of what type,
in what order, with what pedagogical intent. Doesn't write content.

**File:** `apps/skillnet-api/src/agents/runtime/agents/blueprint.py`

**Function:**

```python
async def run_blueprint(
    *,
    title: str,
    summary: str,
    outcome: str | None,
    criticality: str,
    ui_format: str,
    effective_density: int,
    scaffold_band: str,
    role_title: str | None,
    sector: str | None,
    experience_level: str,
    target_bloom: str,
    shape_hints: Sequence[str],
    llm: Any,
) -> Blueprint:
    """Produces the screen's JSON blueprint."""
```

**Output (JSON):**

```json
{
  "blocks": [
    {"id": "intro", "type": "TextContent", "intent": "enganchar", "variant": "lead"},
    {"id": "tabla", "type": "Table", "intent": "concepto", "columns": 2, "note": "one allergen per row"},
    {"id": "q1", "type": "QuizItem", "intent": "verificar", "item_type": "test", "bloom": "apply"}
  ]
}
```

**Pydantic type:**

```python
# apps/skillnet-api/src/agents/runtime/agents/types.py

class BlueprintBlock(BaseModel):
    id: str
    type: str  # kit component name
    intent: Literal["enganchar", "concepto", "verificar", "refuerzo"]
    variant: str | None = None       # for TextContent
    columns: int | None = None       # for Table
    item_type: str | None = None     # for QuizItem
    bloom: str | None = None         # for QuizItem/DragOrder
    note: str | None = None          # free-form instruction for agents 2/3

class Blueprint(BaseModel):
    blocks: list[BlueprintBlock]
```

**System prompt:**

```python
BLUEPRINT_SYSTEM = """\
You are SkillNet's screen architect. Your job is to decide the STRUCTURE of a
learning screen: how many blocks, of what type and in what order. You do NOT write
content, you do NOT write text for the learner, you do NOT write questions. You only
decide the shape.

Respond ONLY with valid JSON, with no text before or after:

{"blocks": [
  {"id": "<ascii_id>", "type": "<component>", "intent": "<enganchar|concepto|verificar|refuerzo>", ...},
  ...
]}

Available components for the CONCEPT slot (choose based on the material):
- Table: lists of things, comparisons, label-value pairs. Indicate columns: 1 or 2.
- StepByStepReveal: procedure with per-step explanation.
- BeforeAfter: comparison of two states (right/wrong, before/after).
- Tabs: multiple independent aspects of a topic (3+ tabs).
- StepSequence: simple procedure without detailed explanations.
- Card: group related blocks with a visual border.

Available components for the VERIFY slot (choose based on the concept):
- QuizItem: question with options. Indicate item_type and bloom.
- DragOrder: order elements by dragging.
- BeforeAfter: if the concept has a right/wrong.

Mandatory screen structure:
1. HOOK — TextContent with variant "lead". A real situation from the job.
2. CONCEPT — ONE of the blocks above. NEVER TextContent("body") for the concept.
3. VERIFY — ONE interactive block. If the format is "mixed" or "exercise", it MUST
   be QuizItem or DragOrder.
4. Optionally a reinforcement Callout if the node is mandatory compliance.

MAXIMUM 4 blocks (intro + concept + practice + optionally a Callout).

Hard rules:
- Ids are ASCII without accents: "intro", "tabla", "q1", never "introducción".
- Each id is unique.
- The first block is always TextContent with variant "lead".
- If the format is "exercise" or "mixed", the last block is QuizItem or DragOrder.
- Do NOT invent components that aren't in the list.
- The "note" field is a brief instruction for whoever fills in the content (optional).
"""
```

**User prompt:**

```python
def build_blueprint_prompt(
    *,
    title: str,
    summary: str,
    outcome: str | None,
    criticality: str,
    ui_format: str,
    effective_density: int,
    scaffold_band: str,
    role_title: str | None,
    sector: str | None,
    experience_level: str,
    target_bloom: str,
    shape_hints: Sequence[str],
) -> str:
    parts = [
        f"FORMAT: {ui_format}",
        "",
        "NODE",
        f"- Title: {title}",
        f"- Summary: {summary}",
    ]
    if outcome:
        parts.append(f"- Expected outcome: {outcome}")
    parts.append(f"- {_criticality_rule(criticality)}")
    parts.extend([
        "",
        "LEARNER",
        f"- Role: {role_title or 'not declared'}",
        f"- Sector: {sector or 'not declared'}",
        f"- Experience: {experience_level}",
        f"- Target cognitive level: {target_bloom}",
        f"- Budget: {_density_budget(effective_density)}",
        f"- {_SCAFFOLD_RULES.get(scaffold_band, _SCAFFOLD_RULES['neutral'])}",
    ])
    if shape_hints:
        parts.append("")
        parts.append("SHAPE OF THE MATERIAL (read from the source)")
        for hint in shape_hints:
            parts.append(f"- {hint}")
    parts.append("")
    parts.append("Respond with the JSON only.")
    return "\n".join(parts)
```

**Token budget:** max_tokens=512, temperature=0.2, json_mode=True.

**Output validation:** Parsed as `Blueprint` with Pydantic. If it fails:
- `parse_json_response` is attempted (the usual strategies).
- If it still fails, a default blueprint is generated based on `ui_format` + `shape_hints`.

**Default blueprint (no LLM):**

```python
def default_blueprint(ui_format: str, shape_hints: Sequence[str]) -> Blueprint:
    """The same blueprint the monolithic version would have chosen, without spending a call."""
    blocks = [
        BlueprintBlock(id="intro", type="TextContent", intent="enganchar", variant="lead"),
    ]
    # Concept: Table if there are enumeration hints, StepSequence if procedure, TextContent if none
    if any("Table" in h for h in shape_hints):
        blocks.append(BlueprintBlock(id="concepto", type="Table", intent="concepto", columns=2))
    elif any("StepSequence" in h or "StepByStepReveal" in h for h in shape_hints):
        blocks.append(BlueprintBlock(id="concepto", type="StepByStepReveal", intent="concepto"))
    else:
        blocks.append(BlueprintBlock(id="concepto", type="Table", intent="concepto", columns=1))
    # Verify
    if ui_format in ("exercise", "mixed"):
        blocks.append(BlueprintBlock(id="q1", type="QuizItem", intent="verificar", item_type="test", bloom="apply"))
    else:
        blocks.append(BlueprintBlock(id="q1", type="QuizItem", intent="verificar", item_type="test", bloom="understand"))
    return Blueprint(blocks=blocks)
```

---

### 3.2 Agent 2: Content Writer

**Responsibility:** Write the blueprint's content blocks (TextContent, Table,
StepByStepReveal, StepSequence, Callout, Tabs, BeforeAfter, Card) in OpenUI Lang
dialect. Doesn't write questions or answers. **Streams** its output so the frontend
can show blocks progressively if needed.

**File:** `apps/skillnet-api/src/agents/runtime/agents/content_writer.py`

**Function:**

```python
async def run_content_writer(
    *,
    blueprint: Blueprint,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    scaffold_band: str,
    criticality: str,
    llm: Any,
) -> ContentOutput:
    """Produces the OpenUI Lang declarations for the content blocks."""
```

**Output:**

```python
class ContentOutput(BaseModel):
    """OpenUI Lang declarations for the content blocks, one per line."""
    declarations: str  # text in OpenUI Lang dialect, no root or quizzes
```

Example output:
```
intro = TextContent("A minor fire scare in the warehouse: you have 10 seconds of extinguisher.", "lead")
pasos = StepByStepReveal("PAS Rule", [["P - Pull the Pin", "Pull the ring with a sharp motion."], ["A - Aim at the base", "Never at the flames."], ["S - Sweep side to side", "From 2-3 meters, side to side."]])
```

**System prompt:**

```python
CONTENT_WRITER_SYSTEM: str  # built dynamically

def content_writer_system() -> str:
    return render_prompt().rstrip("\n") + """

## SkillNet Content Writer: your specific task

You are SkillNet's CONTENT writer. You receive a blueprint (the screen's structure)
and the source. Your job is to write ONLY the content blocks, in OpenUI Lang
dialect.

What you DO:
- Write TextContent, Table, StepByStepReveal, StepSequence, Callout, Tabs, TabItem,
  BeforeAfter, Card, Accordion, AccordionItem, Chart, CodeBlock.
- One declaration per line: id = Component(args...)
- Use the EXACT ids from the blueprint.
- Base everything on the source. Do NOT invent data.

What you DON'T do:
- Do NOT write QuizItem or DragOrder (another agent writes those).
- Do NOT write the root = Stack(...) line.
- Do NOT write ---ANSWER-KEY---.
- Do NOT write prose before or after the program.
- Do NOT repeat the instructions or explain what you're doing.

Dialect rules: the ones above (SkillNet 1-13), without exceptions.
- SkillNet 14: ids in ASCII without accents.
- SkillNet 16: Callout has 3 tones (info, warn, success), never "critical".
- SkillNet 17: to the right of the = there's always a call to a block.
- SkillNet 13: do NOT invent figures or data not in the source.

Respond ONLY with the declarations, one per line. Nothing else.
"""
```

**User prompt:**

```python
def build_content_prompt(
    *,
    blueprint: Blueprint,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    scaffold_band: str,
    criticality: str,
) -> str:
    content_blocks = [b for b in blueprint.blocks if b.type not in ("QuizItem", "DragOrder")]
    blocks_desc = "\n".join(
        f"- {b.id}: {b.type} (intent={b.intent}"
        + (f", variant={b.variant}" if b.variant else "")
        + (f", columns={b.columns}" if b.columns else "")
        + (f", note={b.note}" if b.note else "")
        + ")"
        for b in content_blocks
    )
    parts = [
        "BLUEPRINT (write ONLY these blocks, with these exact ids)",
        blocks_desc,
        "",
        f"NODE: {title}",
        f"SUMMARY: {summary}",
        f"- {_criticality_rule(criticality)}",
        f"- {_SCAFFOLD_RULES.get(scaffold_band, _SCAFFOLD_RULES['neutral'])}",
    ]
    if role_title:
        parts.append(f"- Examples are situations for a {role_title}"
                     + (f" in the {sector} sector." if sector else "."))
    parts.append("")
    if source_context.strip():
        parts.append("SOURCE (this is the only truth; don't add data not present here)")
        parts.append(clip_source(source_context))
    else:
        parts.append("NO SOURCE. Stick to the node summary.")
    parts.append("")
    parts.append("Write the declarations, one per line. Nothing else.")
    return "\n".join(parts)
```

**Token budget:** max_tokens=800 (fast) / 1600 (heavy), temperature=0.4.

The source is sent ONLY to this agent. It's the only one that needs to read it to
produce content. Agent 3 receives the trimmed source (to verify answers), not the full text.

---

### 3.3 Agent 3: Interaction Designer

**Responsibility:** Write the blueprint's interactive blocks (QuizItem, DragOrder)
in OpenUI Lang dialect, plus the answer key. Doesn't write explanatory content. Runs
in **PARALLEL** with the Content Writer via `asyncio.gather`.

**File:** `apps/skillnet-api/src/agents/runtime/agents/interaction_designer.py`

**Function:**

```python
async def run_interaction_designer(
    *,
    blueprint: Blueprint,
    content_declarations: str,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    target_bloom: str,
    scaffold_band: str,
    llm: Any,
) -> InteractionOutput:
    """Produces the interactive block declarations + answer key."""
```

**Output:**

```python
class InteractionOutput(BaseModel):
    declarations: str   # OpenUI Lang declarations (QuizItem, DragOrder)
    answer_key: dict    # answer key JSON
```

Example output:
```
declarations:
q1 = QuizItem("q1", "test", "apply", "A celiac customer orders fried food. The oil was previously used for battered food. What do you tell them?", ["That it's fine, the oil doesn't retain gluten", "That it's not safe: gluten traces", "To ask the cook", "Only if they're allergic"])

answer_key:
{"q1": {"correct": 1, "explanation": "Oil that fried a wheat-battered item contains gluten traces."}}
```

**System prompt:**

```python
INTERACTION_DESIGNER_SYSTEM: str  # built dynamically

def interaction_designer_system() -> str:
    return render_prompt().rstrip("\n") + f"""

## SkillNet Interaction Designer: your specific task

You are SkillNet's INTERACTION designer. You receive a blueprint and the content
already written. Your job is to write ONLY the interactive and assessment blocks.

What you DO:
- Write QuizItem and DragOrder, in OpenUI Lang dialect.
- One declaration per line: id = Component(args...)
- Write the {ANSWER_KEY_SENTINEL} block with the correct answers.
- Use the EXACT ids from the blueprint.
- Questions are based on the content already written (below).

What you DON'T do:
- Do NOT write TextContent, Table, StepSequence, or any other content block.
- Do NOT write the root = Stack(...) line.
- Do NOT write prose before or after.

## How to write good questions

Rules for QuizItem of type "test":
- ALWAYS 4 options.
- The DISTRACTORS are real mistakes an employee would make, not nonsense.
- The question poses a CONCRETE CASE: "A customer tells you...", "You receive a delivery of...",
  never "What is..." or "What does... mean".
- The explanation says WHY the correct one is correct.
- QuizItem has EXACTLY 5 arguments: QuizItem("id", "type", "bloom", "question?", ["A", "B", "C", "D"]).

For DragOrder:
- EXACTLY 3 arguments: DragOrder("instruction", ["items..."], ["correct order..."]).
- 4-6 elements, concrete actions.

Answer key format:
After the declarations, a line with exactly {ANSWER_KEY_SENTINEL} followed by
a single JSON:

{ANSWER_KEY_SENTINEL}
{{"q1": {{"correct": 2, "explanation": "Why that one and not another."}}}}

Shape of each entry depending on item_type:
- "test": {{"correct": <0-based index>, "explanation": "..."}}
- "true_false": {{"correct": true|false, "explanation": "..."}}
- "fill_blank": {{"blanks": ["exact text"], "explanation": "..."}}
- "order_steps": {{"correct_order": [indices], "explanation": "..."}}

Respond with the declarations and their key. Nothing else.
"""
```

**User prompt:**

```python
def build_interaction_prompt(
    *,
    blueprint: Blueprint,
    content_declarations: str,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    target_bloom: str,
    scaffold_band: str,
) -> str:
    interaction_blocks = [b for b in blueprint.blocks if b.type in ("QuizItem", "DragOrder")]
    if not interaction_blocks:
        return ""  # no interactive blocks to write
    blocks_desc = "\n".join(
        f"- {b.id}: {b.type} (item_type={b.item_type or 'test'}, bloom={b.bloom or target_bloom})"
        for b in interaction_blocks
    )
    parts = [
        "BLUEPRINT (write ONLY these blocks, with these exact ids)",
        blocks_desc,
        "",
        f"NODE: {title}",
        f"SUMMARY: {summary}",
        f"- Target cognitive level: {target_bloom}",
        f"- {_SCAFFOLD_RULES.get(scaffold_band, _SCAFFOLD_RULES['neutral'])}",
    ]
    if role_title:
        parts.append(f"- Questions are about situations for a {role_title}"
                     + (f" in the {sector} sector." if sector else "."))
    parts.append("")
    parts.append("CONTENT ALREADY WRITTEN (your question must be based on this)")
    parts.append(content_declarations)
    parts.append("")
    if source_context.strip():
        parts.append("ORIGINAL SOURCE (to verify the answer is correct)")
        parts.append(clip_source(source_context, limit=3000))
    parts.append("")
    parts.append("Write the declarations and the answer key. Nothing else.")
    return "\n".join(parts)
```

**Token budget:** max_tokens=600 (fast) / 1200 (heavy), temperature=0.3.

Note: the source is trimmed to 3,000 characters (half the usual limit) because
this agent only needs it to verify that its answer is correct, not to
generate new content.

---

### 3.4 Agent 4: Assembler (no LLM)

**Responsibility:** Combine the outputs of agents 2 and 3 into a complete OpenUI
Lang program, validate it, and prepare it for `validate_ui`. It's instant: it doesn't
call any LLM.

**File:** `apps/skillnet-api/src/agents/runtime/agents/assembler.py`

**Function:**

```python
def assemble(
    *,
    blueprint: Blueprint,
    content_output: ContentOutput,
    interaction_output: InteractionOutput | None,
    ui_format: str,
) -> tuple[str, dict]:
    """Assembles the full program + answer key. Returns (raw_dsl, answer_key)."""
```

**Logic:**

```python
def assemble(
    *,
    blueprint: Blueprint,
    content_output: ContentOutput,
    interaction_output: InteractionOutput | None,
    ui_format: str,
) -> tuple[str, dict]:
    # 1. Collect all declarations
    all_declarations: list[str] = []
    declared_ids: set[str] = set()

    # Content declarations
    for line in content_output.declarations.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if "=" in line:
            block_id = line.split("=", 1)[0].strip()
            declared_ids.add(block_id)
        all_declarations.append(line)

    # Interaction declarations
    if interaction_output and interaction_output.declarations.strip():
        for line in interaction_output.declarations.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" in line:
                block_id = line.split("=", 1)[0].strip()
                declared_ids.add(block_id)
            all_declarations.append(line)

    # 2. Build the root line
    # The root's children are the blueprint's ids, in order, filtered to those
    # that were actually declared. If a blueprint id wasn't declared, it's skipped.
    root_children = [b.id for b in blueprint.blocks if b.id in declared_ids]
    gap = "md"
    root_line = f'root = Stack([{", ".join(root_children)}], "{gap}")'

    # 3. Assemble the full program (root first for streaming)
    program_lines = [root_line] + all_declarations
    program = "\n".join(program_lines)

    # 4. Answer key
    answer_key = {}
    if interaction_output:
        answer_key = interaction_output.answer_key

    # 5. Rebuild the full raw_dsl (program + sentinel + key)
    raw_dsl = program
    if answer_key:
        raw_dsl += f"\n{ANSWER_KEY_SENTINEL}\n" + json.dumps(answer_key, ensure_ascii=False)

    return raw_dsl, answer_key
```

**Conflict resolution:**

| Conflict | Resolution |
|-----------|-----------|
| Blueprint id not declared by any agent | Skipped from `root.children`. Warning log. |
| Agent declares an id not in the blueprint | Included (the model may have renamed it). Warning log. |
| Duplicate ids between agents | The second one wins (interaction over content). Error log. |
| Blueprint requests QuizItem but Agent 3 failed | Assembled without interaction; `validate_ui` will reject it if the format requires it and the repair kicks in. |

---

## 4. Pre-generation strategy

Content generation doesn't wait for the learner. The system works ahead of time.

### 4.1 First node: generated at course creation

When a course is activated (`schema_status = 'validated'`), the render of the first
node is generated **synchronously** (await). At this point no learner exists yet, so
the content is generic — no profile, no `format_vector`, no error history.

That's deliberate: every learner who opens the course will find the first node
ready immediately. Adaptation starts from node 2, once there's data.

### 4.2 Following nodes: sliding window of 3

When the learner is on node N, the frontend fires `POST /nodes/{id}/render`
(fire-and-forget, `{ force: false }`) for nodes N+1, N+2, and N+3. The code is
in `NodeView.tsx`:

```tsx
// Sliding window: pre-render the next 3 nodes ahead of the current position.
const ahead = ordered
  .filter((n) => n.position > node.position)
  .slice(0, 3)
for (const n of ahead) {
  void post(`/nodes/${n.id}/render`, { force: false }).catch(() => undefined)
}
```

The backend is **idempotent**: if the render already exists in cache or a generation
is already in flight for that `cache_key`, the work isn't duplicated. Every visit
to a node slides the window forward.

Additionally, when the learner opens the course (`CourseView.tsx`), the first
two nodes that are `not_started` or `learning` get pre-rendered:

```tsx
// Give the learner an immediate start and one immediate continuation. The
// remaining lessons are still generated at learning time; NodeView maintains
// the rolling three-ahead window once the learner enters the course.
return [...dynamicNodes.nodes]
  .sort((a, b) => a.position - b.position)
  .filter((n) => n.state === 'not_started' || n.state === 'learning')
  .slice(0, 2)
```

There is no lock filter: progression has been linear since 2026-08-28 and
`GET /courses/{id}/nodes` no longer sends `locked`/`locked_by`
(`docs/design/future-progression-modes.md`). The `slice(0, 2)` is not new either — this
document said "only 1 ahead" before that, while the code has pre-rendered two since
2026-08-17.

### 4.3 Adapting to the learner from node 2 onward

From the second node onward, content adapts to the learner's profile:

- **`format_vector`**: 4 dimensions (visual, textual, interactive, example) inferred from
  the learner's `learning_events` (scroll_slow, quiz_correct, quiz_wrong, explain_click,
  expand, etc.). 30-day sliding window with exponential decay.
- **`scaffold_band`**: If the learner makes mistakes, the system lowers the intensity
  (more explanations, less density). If they succeed, it raises it (more challenge, more density).
- **`target_bloom`**: The target cognitive level adjusts based on the learner's
  current mastery of the node.
- **Calibration period**: The first 3 completed nodes (`CALIBRATION_NODES = 3`)
  accumulate the vector but don't use it — `vector_bucket` returns `""` so it doesn't enter
  the `cache_key` or the prompt.

### 4.4 Future: adaptive lookahead

Auto-adjust the window size based on the model's inference speed:

- Fast model (< 1s per render, e.g. Groq llama-3.1-8b-instant): 1 node ahead.
- Slow model (> 5s per render, e.g. local 7B on CPU): 3-4 nodes ahead.

---

## 5. Streaming as a safety net

### 5.1 The ideal case: pre-generated content

In the normal case, the content is already cached by the time the learner reaches
the node. The response is instant. No loading, no visible streaming. The learner
opens the node and the content is right there.

### 5.2 The fallback case: invisible streaming

If pre-generation didn't complete in time (because the learner navigates fast, because
it's a node that skipped the window, or because the model was slow), the Content Writer
streams blocks as it generates them. The frontend shows each block with an opacity
transition (fade-in). Meanwhile, the Interaction Designer generates the quiz in parallel.

The goal is for the learner to **never know** that generation is happening.
No "Preparing your lesson...", no skeletons, no progress bars,
no spinners. The content simply appears, as if it had always been there
but the page was loading.

### 5.3 Streaming implementation

Every agent that streams calls `_stream_declarations()`, which parses
individual declarations as the LLM produces them and emits them as
`ui_block` events over SSE:

```python
async def _stream_declarations(
    llm: Any,
    system: str,
    user_prompt: str,
    *,
    request_id: str,
    backend_name: str = "openui",
    usage_out: dict[str, Any] | None = None,
) -> str:
    """Streaming of individual declarations, emitting ui_block for each one."""
    backend = get_render_backend(backend_name)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    chunks: list[str] = []
    announced: set[str] = set()
    async for delta in llm.stream(messages, temperature=..., max_tokens=..., usage_out=usage_out):
        chunks.append(delta)
        if "\n" not in delta:
            continue
        text_so_far = "".join(chunks)
        for line in text_so_far.strip().splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            block_id = line.split("=", 1)[0].strip()
            if block_id in announced:
                continue
            try:
                test_program = f'root = Stack([{block_id}], "md")\n{line}'
                partial = backend.parse_partial(test_program, ui_format="explanation")
                for component in partial.components:
                    if component.id == block_id and component.id not in announced:
                        announced.add(component.id)
                        await sse.publish(
                            node_channel(request_id),
                            "ui_block",
                            {"component": component.model_dump()},
                        )
            except Exception:
                continue
    return "".join(chunks)
```

---

## 6. Failure handling

### 6.1 Per-agent failures

The system has a fallback for every point of failure, from more to less degradation:

| Agent | Failure | Response |
|--------|-------|-----------|
| **Blueprint Architect** | LLM doesn't return valid JSON | Use `default_blueprint()` based on `ui_format` + `shape_hints`. Warning log. Continue the pipeline. |
| **Blueprint Architect** | LLM returns unknown component types | Filter out the unknown ones. If nothing remains, `default_blueprint()`. |
| **Content Writer** | LLM doesn't produce parseable declarations | Subgraph failure. The outer graph goes to the repair loop with the monolithic version. |
| **Interaction Designer** | LLM doesn't produce a valid QuizItem | Serve the content without a quiz (explanation-only). The learner learns without practicing. |
| **Interaction Designer** | Incomplete or malformed answer key | Subgraph failure. The monolithic repair fixes it. |
| **Content Writer + Interaction Designer** | Both fail | `fallback_seed`: the v1 lesson rendered as `Markdown`. Final safety net. |
| **Assembler** | `gate.canonicalize()` rejects the program | Retry the failing agent once. If it persists, fallback. |
| **Assembler** | Ids don't match | Assemble what's there. Warning. `validate_ui` decides whether it's valid. |

### 6.2 Retry: falling back to the monolithic version

The retry loop (`MAX_UI_RETRIES = 1`) uses the monolithic version, not multi-agent:

```python
if retry:
    return await genera_ui(state)  # monolithic, with repair prompt
```

Reason: the repair prompt is optimized to receive the previous program and the
validator's errors. Regenerating with multi-agent on retry wouldn't leverage that information.

### 6.3 Safety invariants

The three safety invariants from `nodes.py`'s docstring remain intact:

1. **Raw bytes are never persisted.** The Assembler produces `raw_dsl`, which goes through
   `validate_ui` -> `canonicalize` -> re-serializes. The browser only ever sees the re-serialization.
2. **Answer key kept separate.** The Assembler explicitly separates it. `validate_ui` does
   `split_answer_key` as always.
3. **No tools or reactivity.** The agents' prompts never mention reactivity.
   `check_static_only` still runs in `canonicalize`.

---

## 7. The philosophy: the learner never waits

Six mechanisms, each covering a scenario:

| Mechanism | When it acts | Result |
|-----------|-------------|-----------|
| Pre-generated first node | When the course is activated | Every learner finds node 1 ready. |
| Sliding window of 3 | While the learner is on node N | N+1, N+2, N+3 are generated fire-and-forget. |
| Prefetch on course open | When `CourseView` loads | The first two nodes not started or in progress are pre-generated. |
| Backend idempotency | Always | If a render or generation is already in flight, no duplicate work happens. |
| Invisible streaming | If pre-generation didn't complete | Blocks appear with fade-in. The learner doesn't see "loading". |
| Adaptive `format_vector` | From node 2 onward | Content adapts to the learner's profile with every interaction. |

The system learns from the learner's events: `quiz_correct`, `quiz_wrong`,
`scroll_slow`, `scroll_fast`, `explain_click`, `expand`, `view`. Each event has a
fixed weight (0.30 for `explain_click`, 0.20 for `quiz_correct`, etc.) and feeds a
4-dimensional vector that decays over time (30-day window). That vector
determines what type of content the learner receives.

---

## 8. SSE and partial streaming

### 8.1 Events during multi-agent

The subgraph emits `render_step` with messages that inform the frontend of the current phase:

| Phase | SSE message |
|------|-------------|
| Blueprint | "Designing the structure..." |
| Content Writer | "Writing the content..." |
| Interaction Designer | "Designing the questions..." |
| Assembler | (no message: it's instant) |

These messages are only seen if pre-generation didn't complete in time. In the
normal case (cache hit), the response is direct and there's no generation SSE.

### 8.2 Partial block streaming

- **Content Writer:** Each completed declaration is parsed and emitted as
  `ui_block`, exactly like the monolithic version. Content appears block by block.
- **Interaction Designer:** Same as the Content Writer, but for interactive blocks.
- The `root` isn't emitted until the Assembler builds it, but since the frontend already
  knows the order from streaming the individual blocks, the experience is identical.

---

## 9. New subgraph: `genera_ui_multi`

### 9.1 Subgraph structure

The current `genera_ui` node is replaced (under feature flag) by a function that
orchestrates the four agents:

```
genera_ui_multi:
    run_blueprint -> asyncio.gather(run_content_writer, run_interaction_designer) -> assemble
```

Content Writer and Interaction Designer run in **parallel**. There's no conditional
routing: it's a chain with a parallel fork. If an agent fails, the whole subgraph fails and
the outer graph treats it as a `genera_ui` failure (goes to the repair loop or fallback,
exactly as now).

### 9.2 New files

```
apps/skillnet-api/src/agents/runtime/agents/
    __init__.py
    types.py              # Blueprint, BlueprintBlock, ContentOutput, InteractionOutput
    blueprint.py          # run_blueprint + prompt
    content_writer.py     # run_content_writer + prompt
    interaction_designer.py  # run_interaction_designer + prompt
    assembler.py          # assemble (no LLM)
```

### 9.3 Integration with the existing graph

**Modified file:** `apps/skillnet-api/src/agents/runtime/nodes.py`

A `genera_ui_multi` function is added that replaces `genera_ui` under feature flag:

```python
from src.agents.runtime.agents.blueprint import run_blueprint
from src.agents.runtime.agents.content_writer import run_content_writer
from src.agents.runtime.agents.interaction_designer import run_interaction_designer
from src.agents.runtime.agents.assembler import assemble

@runtime_node_error_wrapper("genera_ui")
async def genera_ui_multi(state: NodeRuntimeState) -> dict:
    """Multi-agent version of genera_ui. Same signature, same output."""
    request_id = str(state["request_id"])
    org_id = _uuid(state["org_id"])
    node = state.get("node") or {}
    profile = state.get("profile") or {}
    node_state = state.get("node_state") or {}
    tier = str(state.get("tier") or "fast")
    ui_format = coerce_ui_format(state.get("ui_format"))
    retry = int(state.get("retry_count") or 0)

    # On retry, fall back to the monolithic version (the repair prompt is optimized for it)
    if retry:
        return await genera_ui(state)

    llm = await _make_llm(org_id, tier)
    mastery = float(node_state.get("mastery") or 0.0)
    threshold = threshold_for(
        node.get("criticality") or "recommended", node.get("mastery_threshold")
    )

    await publish_step(request_id, "genera_ui", "Designing the structure...")
    started = time.monotonic()

    # --- Agent 1: Blueprint ---
    blueprint = await run_blueprint(
        title=str(node.get("title") or ""),
        summary=str(node.get("summary") or ""),
        outcome=node.get("outcome"),
        criticality=str(node.get("criticality") or "recommended"),
        ui_format=ui_format,
        effective_density=int(state.get("effective_density") or 3),
        scaffold_band=str(state.get("scaffold_band") or "neutral"),
        role_title=profile.get("role_title"),
        sector=profile.get("sector"),
        experience_level=str(profile.get("experience_level") or "unknown"),
        target_bloom=target_bloom(mastery, threshold),
        shape_hints=list(state.get("shape_hints") or ()),
        llm=llm,
    )
    tokens_in_total = 0
    tokens_out_total = 0

    await publish_step(request_id, "genera_ui", "Writing the content...")

    # --- Agents 2+3: Content Writer + Interaction Designer (PARALLEL) ---
    content_coro = run_content_writer(
        blueprint=blueprint,
        title=str(node.get("title") or ""),
        summary=str(node.get("summary") or ""),
        source_context=str(state.get("source_context") or ""),
        role_title=profile.get("role_title"),
        sector=profile.get("sector"),
        scaffold_band=str(state.get("scaffold_band") or "neutral"),
        criticality=str(node.get("criticality") or "recommended"),
        llm=llm,
    )

    interaction_coro = None
    interaction_blocks = [b for b in blueprint.blocks if b.type in ("QuizItem", "DragOrder")]
    if interaction_blocks:
        await publish_step(request_id, "genera_ui", "Designing the questions...")
        interaction_coro = run_interaction_designer(
            blueprint=blueprint,
            content_declarations="",  # parallel: no content yet
            title=str(node.get("title") or ""),
            summary=str(node.get("summary") or ""),
            source_context=str(state.get("source_context") or ""),
            role_title=profile.get("role_title"),
            sector=profile.get("sector"),
            target_bloom=target_bloom(mastery, threshold),
            scaffold_band=str(state.get("scaffold_band") or "neutral"),
            llm=llm,
        )

    # Run in parallel
    if interaction_coro:
        content_output, interaction_output = await asyncio.gather(
            content_coro, interaction_coro
        )
    else:
        content_output = await content_coro
        interaction_output = None

    # --- Agent 4: Assembler ---
    raw_dsl, answer_key_from_assembler = assemble(
        blueprint=blueprint,
        content_output=content_output,
        interaction_output=interaction_output,
        ui_format=ui_format,
    )

    duration_ms = int((time.monotonic() - started) * 1000)

    return {
        "raw_dsl": raw_dsl,
        "model": getattr(llm, "model", "unknown"),
        "duration_ms": duration_ms + int(state.get("duration_ms") or 0),
        "tokens_in": _accumulate(state.get("tokens_in"), tokens_in_total or None),
        "tokens_out": _accumulate(state.get("tokens_out"), tokens_out_total or None),
        "current_step": "genera_ui",
    }
```

---

## 10. Feature flag and migration

### 10.1 Feature flag

**File:** `apps/skillnet-api/src/config.py`

```python
# Multi-agent pipeline (experimental)
MULTI_AGENT_RENDER: bool = Field(default=False, env="MULTI_AGENT_RENDER")
```

**File:** `apps/skillnet-api/src/agents/runtime/graph.py`

```python
from src.config import settings

def build_node_graph():
    graph = StateGraph(NodeRuntimeState)

    # Choose the genera_ui implementation
    if settings.MULTI_AGENT_RENDER:
        from src.agents.runtime.nodes import genera_ui_multi
        graph.add_node("genera_ui", genera_ui_multi)
    else:
        graph.add_node("genera_ui", genera_ui)

    # ... rest of the graph identical
```

### 10.2 Behavior according to the flag

| `MULTI_AGENT_RENDER` value | Behavior |
|-------------------------------|----------------|
| `false` (default) | Monolithic. Everything as today. |
| `true` | Multi-agent on the first attempt. Monolithic on retry. |

### 10.3 Cache key

The cache key does NOT change. The cache is invalidated by `PROMPT_VERSION` (which
already gets bumped when prompts change). Multi-agent produces the same `raw_dsl` that
goes through the same `validate_ui`, `canonicalize`, and `persist_render`.

The cache key includes the pipeline version, so there's no cross-contamination
between renders generated by the monolithic version and multi-agent:

```python
PROMPT_VERSION = "runtime/12"  # multi-agent pipeline
```

### 10.4 Rollback

One line. Set `MULTI_AGENT_RENDER=false` in the `.env`. No restart needed: the graph
is recompiled on every invocation (`build_node_graph()` is called per request).

### 10.5 Deployment plan

1. **Phase 1: Implement and test offline.**
   - Create `src/agents/runtime/agents/` with the four modules.
   - Unit tests for each agent with fixtures.
   - Integration test of the full flow with `MULTI_AGENT_RENDER=true`.

2. **Phase 2: Comparative quality bench.**
   - Run `scripts/quality_bench.py` with `MULTI_AGENT_RENDER=false` (baseline).
   - Run with `MULTI_AGENT_RENDER=true` (multi-agent).
   - Compare: catalog coverage, first-try success, tokens, latency.
   - Acceptance criteria: coverage > 50%, success > 70%, latency < 150% of monolithic.

3. **Phase 3: Enable by default.**
   - Change `MULTI_AGENT_RENDER`'s default to `true`.
   - Monitor in production for 1 week.
   - If regression > 10% on any metric, revert to `false`.

---

## 11. Cache key

The cache key's shape does NOT change. The `build_cache_key` function in
`apps/skillnet-api/src/services/cache_key.py` remains the sole authority, and is called
from exactly two places: the pre-graph check in `NodeRenderService` and `load_context`
inside the graph.

What changes is `PROMPT_VERSION`, which is already part of the key. Enabling
multi-agent bumps it to `"runtime/12"`, which invalidates the entire monolithic cache
without touching the hashing logic.

---

## 12. Per-agent token breakdown

### 12.1 Agent 1: Blueprint Architect

| Field | Estimated tokens |
|-------|-----------------|
| System prompt | ~400 |
| User prompt | ~300 |
| **Total input** | **~700** |
| Output (JSON) | ~150-300 |
| max_tokens | 512 |
| temperature | 0.2 |

### 12.2 Agent 2: Content Writer

| Field | Estimated tokens |
|-------|-----------------|
| System prompt (dialect + rules) | ~1,200 |
| User prompt (blueprint + source) | ~1,300 |
| **Total input** | **~2,500** |
| Output (declarations) | ~300-600 |
| max_tokens fast/heavy | 800 / 1,600 |
| temperature | 0.4 |

### 12.3 Agent 3: Interaction Designer

| Field | Estimated tokens |
|-------|-----------------|
| System prompt (dialect + quiz rules) | ~1,000 |
| User prompt (blueprint + content + trimmed source) | ~1,000 |
| **Total input** | **~2,000** |
| Output (declarations + answer key) | ~200-400 |
| max_tokens fast/heavy | 600 / 1,200 |
| temperature | 0.3 |

### 12.4 Comparison with the monolithic version

| | Monolithic | Multi-agent |
|--|-----------|-------------|
| LLM calls | 1 (+ 1 if repair) | 3 (+ 1 if repair) |
| Input tokens (total) | ~5,250 | ~5,200 |
| Output tokens (total) | ~800 | ~1,100 |
| Tokens if repair | ~10,500 + ~1,600 | ~5,200 + ~5,250 + ~800 (monolithic on retry) |
| Source in the prompt | 1 time, complete | 1 time complete (Agent 2) + 1 time trimmed (Agent 3) |

The real advantage is in the repair rate: if multi-agent raises first-try
success from 30-65% to 70-90%, the total cost drops because retries are eliminated
(which today cost a full second call).

---

## 13. Tests

### 13.1 New unit tests

```
apps/skillnet-api/tests/unit/test_blueprint_agent.py
apps/skillnet-api/tests/unit/test_content_writer_agent.py
apps/skillnet-api/tests/unit/test_interaction_designer_agent.py
apps/skillnet-api/tests/unit/test_assembler.py
```

Each test uses an LLM fixture (`fixture/local`) that returns predefined responses.

### 13.2 Integration tests

```
apps/skillnet-api/tests/integration/test_multi_agent_pipeline.py
```

- Full-flow test with `MULTI_AGENT_RENDER=true`.
- Fallback-to-monolithic test on retry.
- Test that the safety invariants are maintained (separate answer key, canonicalize).

### 13.3 Quality bench

The existing bench (`scripts/quality_bench.py`) works unchanged: multi-agent
produces the same output (`raw_dsl` + answer key) as the monolithic version, and the bench
measures the final result.

---

## 14. Multimodal future (v3)

### 14.1 Vision

The same source document generates multiple content formats:

| Format | Description |
|---------|-------------|
| Interactive lesson | The current format: text + quiz (v2). |
| Audio explanation | NotebookLM-style conversation, not robotic TTS. Two voices discuss the concept. |
| Review cards | Flashcards generated from the same material. Built-in spaced repetition. |
| Diagram | Visual representation of the concept (mermaid, d3, or generated SVG). |
| Explainer video | Narrated slides with the conversational audio as the soundtrack. |

### 14.2 Optimal format detection

The system detects which format works for each learner and offers more of that.
The current `format_vector` has 4 dimensions; in v3 it expands to 6-7:

| Dimension | Current | v3 |
|-----------|--------|-----|
| visual | Yes | Yes |
| textual | Yes | Yes |
| interactive | Yes | Yes |
| example | Yes | Yes |
| auditory | - | New |
| spatial (diagrams) | - | New |
| repetition (flashcards) | - | New |

The learner's events (`audio_play`, `audio_complete`, `flashcard_flip`,
`diagram_zoom`) feed the vector's new dimensions.

### 14.3 Architecture

The same multi-agent pipeline, with additional agents:

```
Blueprint Architect
        |
    +---+---+---+
    |   |   |   |
Content  Quiz  Audio  Diagram    (parallel)
Writer   Desn  Script  Generator
    |   |   |   |
    +---+---+---+
        |
    Multi-format Assembler
```

The Blueprint Architect decides not only the lesson's structure but also which formats
get generated for this node, based on the learner's `format_vector`.

---

## 15. Design decisions

| Decision | Discarded alternative | Reason |
|----------|----------------------|-------|
| Agents 2+3 in **parallel** | Sequential with gap | Default: parallel (OpenAI). Flag to sequence if Groq free tier is used (6k TPM). |
| Blueprint as JSON, not as DSL | Blueprint as partial OpenUI Lang | JSON is easier to parse and validate; the model doesn't need to know the dialect's syntax to decide the structure. |
| Retry falls back to monolithic | Retry repeats multi-agent | The repair prompt is optimized for the single-output flow. Multi-agent doesn't leverage the validator's errors because each agent did only part of the work. |
| All three agents share the same LLM | Agent 1 uses "fast", agents 2+3 use the format's tier | Simplifies things and avoids routing decisions. The blueprint is so cheap it doesn't justify a separate tier. |
| Don't touch `validate_ui` or `persist_render` | Duplicate validation per agent | The chain produces the same `raw_dsl` as the monolithic version; there's no reason to change anything after the Assembler. |
| Source context only in Agent 2 (full) and Agent 3 (trimmed) | Source in all three | The Blueprint doesn't need the source (it decides via `shape_hints`). Saves ~1,500 input tokens per render. |
| Environment feature flag | Per-organization flag | Unnecessary complexity in the first iteration. All organizations use the same flag. |
| Generic first node (no profile) | Wait for the first learner | Every learner finds node 1 ready. Adaptation starts at node 2, once there's data. |
| Sliding window of 3 (no more) | Pre-generate the whole course | Later nodes benefit from more learner data. Pre-generating everything wastes adaptation. |
| Invisible streaming (no indicators) | Skeleton screens / progress bars | The learner shouldn't know generation is happening. The UX is "content that appears", not "content that's being generated". |

---

## 16. Implementation checklist

Each item is an independent, testable unit of work:

- [ ] `src/agents/runtime/agents/__init__.py` — Empty package.
- [ ] `src/agents/runtime/agents/types.py` — `Blueprint`, `BlueprintBlock`, `ContentOutput`, `InteractionOutput`.
- [ ] `src/agents/runtime/agents/blueprint.py` — `run_blueprint`, `default_blueprint`, `BLUEPRINT_SYSTEM`, `build_blueprint_prompt`.
- [ ] `src/agents/runtime/agents/content_writer.py` — `run_content_writer`, `content_writer_system`, `build_content_prompt`.
- [ ] `src/agents/runtime/agents/interaction_designer.py` — `run_interaction_designer`, `interaction_designer_system`, `build_interaction_prompt`.
- [ ] `src/agents/runtime/agents/assembler.py` — `assemble`.
- [ ] `src/agents/runtime/nodes.py` — `genera_ui_multi`.
- [ ] `src/config.py` — `MULTI_AGENT_RENDER`.
- [ ] `src/agents/runtime/graph.py` — Feature flag in `build_node_graph`.
- [ ] `src/llm/prompts/runtime.py` — Bump `PROMPT_VERSION`.
- [ ] `tests/unit/test_blueprint_agent.py`
- [ ] `tests/unit/test_content_writer_agent.py`
- [ ] `tests/unit/test_interaction_designer_agent.py`
- [ ] `tests/unit/test_assembler.py`
- [ ] `tests/integration/test_multi_agent_pipeline.py`
- [ ] Run `quality_bench.py` in both modes and document results.
