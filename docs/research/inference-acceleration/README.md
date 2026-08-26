# Inference Acceleration

> **Status:** the July 2026 measurements below still hold, and Groq is a supported `LLM_MODEL` value. The specialized hardware (LPU, wafer-scale) was surveyed, not adopted.

Hardware and models specialized for fast LLM inference, enabling real-time content generation. Instead of waiting 10-30s for a page to translate or adapt, specialized hardware can do it in <1s.

## The Problem

Standard LLM inference (Claude, GPT-4) runs at ~50-100 tokens/second. For a page of ~500 tokens, that means 5-10 seconds of wait time. For interactive experiences where the user expects instant response, this is too slow.

The bottleneck is not compute — it's memory. GPUs store model weights in HBM (High Bandwidth Memory) outside the chip. Every inference step spends most of its time fetching weights from external memory rather than computing.

## Hardware Solutions

### Groq — LPU (Language Processing Unit)

Groq builds a custom chip called the LPU, designed from scratch for inference only (not training). Three key innovations:

1. **SRAM as primary storage.** Instead of external HBM, Groq integrates hundreds of MB of SRAM directly on the processor. Access latency drops from ~200ns (HBM) to ~10ns (SRAM).

2. **Static scheduling via compiler.** A GPU decides at runtime which cores do what (dynamic scheduling). Groq's compiler pre-computes every clock cycle before execution — it knows exactly when each data item arrives, which core processes it, and at what nanosecond. No cache coherency, no reorder buffers, no speculative execution overhead.

3. **Direct chip-to-chip connectivity.** Multiple LPUs connect directly via a plesiosynchronous protocol that aligns hundreds of chips to act as a single core. The compiler schedules both compute and network.

**Real-world speeds:** 500-1,000 tok/s depending on model. Llama 3.1 8B runs at 840 tok/s, Qwen3 32B at 662 tok/s.

### Cerebras — WSE (Wafer-Scale Engine)

Cerebras takes the opposite approach: make the chip so large that everything fits on one die.

1. **One giant chip.** The WSE-3 has 4 trillion transistors and 900,000 cores on a single processor — ~50x larger than an NVIDIA GPU. No chip-to-chip interconnect because there's only one chip.

2. **44 GB of on-chip SRAM** with 21 PB/s memory bandwidth. Roughly 1,000-2,000x higher effective memory bandwidth than an NVIDIA B200 (which depends on off-chip HBM).

3. **Disaggregated inference** (in partnership with AWS). Inference has two phases: prefill (parallel input processing, compute-heavy) and decode (sequential token generation, memory-bandwidth-bound). Cerebras partnered with AWS so Trainium handles prefill and CS-3 handles decode — each optimized for its phase.

**Real-world speeds:** Meta reports 2,000 tok/s on Llama 4. OpenAI released Codex-Spark at 1,200 tok/s on Cerebras.

### Comparison

| | GPU (NVIDIA) | Groq (LPU) | Cerebras (WSE-3) |
|---|---|---|---|
| Memory | HBM off-chip | SRAM on-chip | SRAM on-chip |
| Die size | ~500 mm² | Standard | ~46,000 mm² (wafer-scale) |
| Multi-chip | Many required | Many act as one | Single chip |
| Memory latency | ~200ns (HBM) | ~10ns (SRAM) | ~10ns (SRAM) |
| Designed for | General purpose | Inference only | Inference (+ some training) |

### Limitations

1. **Large models don't fit in SRAM.** A 70B model in FP16 needs ~140 GB. Cerebras has 44 GB. For these models, you must split across multiple chips, increasing cost and complexity.

2. **Inference only.** You train models on GPUs. Cerebras can train too, but it's not the primary use case.

3. **Small ecosystem.** CUDA has 20 years of optimizations. Groq and Cerebras have their own compilers. Not every model is optimized. New models must be ported.

4. **MoE models.** Mixture-of-Experts (Mixtral, DeepSeek) activate only 2 of 8 experts per token. This is efficient on GPU (load fewer weights) but in SRAM-limited hardware, you can't load all experts at once.

## Test Results (2026-07-15)

Real test with Groq API (free tier), translating skillnet-docs markdown to French.

**Cold start (first request):** 7.5s TTFB — model loading into LPU
**Warm cache (subsequent):** 597ms TTFB, 810ms total for full page (~200 tokens)

**Models compared:**

| Model | Total time | Translation quality | Tok/s |
|---|---|---|---|
| Llama 3.1 8B | 252ms | Poor accents (e, é, è) | 258 |
| Llama 4 Scout | 314ms | Poor accents | 185 |
| Qwen3 32B | 580ms | Good, but thinks out loud | 345 |
| Qwen3.6 27B | 491ms | Good, but thinks out loud | ~300 |

The speed is real — a full page translates in <1s on warm cache. Accent issues are solved with a fine-tuned model (LoRA).

## Pricing (2026)

### Groq

| Model | Tok/s | Input (1M tok) | Output (1M tok) |
|---|---|---|---|
| Llama 3.1 8B | 840 | $0.05 | $0.08 |
| Qwen3 32B | 662 | $0.29 | $0.59 |
| Llama 4 Scout | 594 | $0.11 | $0.34 |

Cost per typical translation (~200 in + 500 out): **$0.00005-$0.00035**.

### Cerebras

- **Free:** access to all models, basic rate limits
- **Developer:** from $10, 10x rate limits
- **Enterprise:** dedicated endpoint, custom weights, uptime guarantees
- **Cerebras Code Pro:** $50/month, 24M tokens/day

## Connection to SkillNet

Week 3 meeting identified Groq and Cerebras as tools for **on-the-fly content generation**. The existing two-layer model (generate JSON offline → render cheap online) can shift to near-realtime if generation runs at 1,000+ tok/s.

For live pages (content that transforms as the user interacts), fast inference enables:
- Page translation in <1s (instead of 10-30s)
- Content simplification at user request
- Dynamic expansion of sections on demand

This hardware exists today as a service — no on-premise deployment needed.

## Related Decisions

- [Production Roadmap: Live Pages](./production-roadmap.md)
