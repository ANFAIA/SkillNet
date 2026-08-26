# Needle: Router Architecture for Specialized Models

> **Status:** exploratory. Needle was not adopted. Request routing shipped instead as a two-tier `fast`/`heavy` prompt router (`apps/skillnet-api/src/agents/runtime/router.py`), with no separate classifier model. Kept for the architecture argument.

Needle is a 26M-parameter model from Cactus Compute, open source (MIT), that does one thing: given a query and a list of tools, it selects the right tool and fills its arguments. It achieves 1,200 tok/s decode on consumer devices and quantizes to 14 MB in INT4.

## Why This Matters for SkillNet

The router pattern: a single endpoint receives all user requests, classifies them, and dispatches to the right specialized model. Needle is designed for exactly this — it's a "tool calling" model, and tools are just routes.

```
User: "translate to French"
    |
    ▼
Needle (26M, local, 5ms, free)
    |   ┌──────────────────┐
    |   │ tool: translate   │
    └──▶│ args: {           │
        │   language: fr    │
        │   content: ...    │
        │ }                 │
        └──────────────────┘
    |
    ▼
Translate agent → fast inference provider
```

## Simple Attention Networks

Needle is built on a novel architecture that removes all MLP (Feed-Forward Network) layers from the transformer. Only attention remains.

**The thesis:** tool calling is not reasoning — it's retrieval-and-assembly. The model doesn't need to think. It needs to:
1. Match the query to the correct tool name
2. Extract argument values from the input
3. Assemble the JSON output

All three operations are aligning and copying information that already exists in the input. Cross-attention is the right primitive for this. FFN parameters (which occupy ~2/3 of a standard transformer) are wasted on this task.

**Architecture:**
```
Standard transformer: Embed → Self-Attention → FFN → Self-Attention → FFN...
Needle:               Embed → Encoder (Self-Attention → Cross-Attention) → Decoder (Self-Attention → Cross-Attention)
                                        (no FFN anywhere)
```

**Key design decisions:**
- **Encoder-decoder** (not decoder-only): the encoder sees tools bidirectionally, understanding the full JSON structure. The decoder only generates output. Input tokens don't occupy the KV cache.
- **Gated residuals:** `x = x + sigmoid(gate) * Attn(Norm(x))`. A learnable scalar per layer decides how much attention to add. Initialized to 0 (sigmoid(0) = 0.5), so training starts with half-strength residual.
- **Contrastive tool selection head:** CLIP-style head that encodes queries and tools into a 128-dim space for top-k filtering when the tool set is large.
- **INT4 QAT during training:** fake quantization every 100 steps acts as regularization. The model trains at the same precision it deploys to.

**Training:**
- Pretrained on 200B tokens across 16 TPU v6e (27 hours)
- Post-trained on 2B tokens of synthesized function-calling data (45 minutes)
- Dataset synthesized via Gemini with 15 tool categories
- Loss weighting: JSON structure 1x, tool names 2x, argument values 4x

## How Needle Fits in the Router

The router itself is a model — specifically, a tool-calling model. Needle is the best open-source candidate for this role because:

1. **Runs locally on CPU** — zero API cost, zero network latency. 14 MB in INT4.
2. **Fine-tunable on custom tools** — the playground UI generates data via Gemini and trains a checkpoint in one click.
3. **120+ examples per tool needed** — minimal data requirement for fine-tuning.
4. **Beats models 10x its size** on single-shot function calling (FunctionGemma-270M, Qwen-0.6B, Granite-350M).

The router classifies requests into three categories:

1. **Direct transformation** (translate, simplify, summarize) → fast, cheap model
2. **Generation with context** (explain new concept, expand) → more capable model
3. **Ambiguous / complex** → frontier model (Claude, GPT)

For SkillNet's live pages feature, Needle would classify what the user wants and dispatch to the appropriate specialized agent.

## Links

- GitHub: https://github.com/cactus-compute/needle
- Blog: https://cactuscompute.com/blog/needle
- Weights: https://huggingface.co/Cactus-Compute/needle
- Cactus (inference engine): https://github.com/cactus-compute/cactus
