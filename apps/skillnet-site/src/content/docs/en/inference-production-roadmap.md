---
title: "Production roadmap"
order: 62
section: "research"
group: "inference"
---

# Production Roadmap: Live Pages

> **Status:** proposal, not a plan of record. The "live pages" feature (translate, simplify or expand a page on demand) is not implemented; phases 2 to 4 were never started.

## Philosophy

First make it work, then optimize. The concept is validated with free, slow models. Once the system works, each piece improves independently.

## Phase 0 — Concept Validation (now)

**Goal:** Demonstrate the idea works, even if slow.

**Stack:**
- Free model: Llama 3.1 8B on Groq (free tier)
- skillnet-docs page with content separated as React state
- User input for target language
- Direct API call from frontend or minimal backend

**Result:** Page translates. Takes 800ms-7s depending on cold/warm cache. But it WORKS. Showable as "this is what it does, optimization comes next."

**Cost:** $0 (Groq free tier)

**Time:** 1-2 days

## Phase 1 — Functional Iteration

**Goal:** Work in a real scenario without being optimal.

**Stack:**
- Minimal backend (FastAPI or Node) receiving requests and calling Groq
- SSE streaming so the page writes in real-time
- Cache for frequent results

**Improvement over Phase 0:** Streaming makes it feel instant. Repeated translations come from cache.

**Cost:** ~$0 (Groq free) + backend time

**Time:** ~1 week

## Phase 2 — Fine-tuned Model (Quality)

**Goal:** Correct translations (accents, grammar, domain terminology).

**Steps:**
1. Generate 500-1,000 pairs of translated markdown
2. Train LoRA on local GPU (QLoRA 8B, ~1-2h) or cloud GPU (A100, ~20 min)
3. Deploy LoRA on Together AI or Fireworks AI

**Result:** Idiomatically correct translations. The model knows "français" takes an accent and "employé" is spelled correctly.

**Cost:** ~$10 (RunPod) + ~$50/mo (Together/Fireworks)

**Time:** ~1 week

## Phase 3 — Speed Optimization

**Goal:** Response in <500ms always.

| Option | Latency | Cost | Effort |
|---|---|---|---|
| Smart caching | Instant on repeat | $0 | Low |
| Prompt caching (Groq) | -50% input cost | Included | Low |
| Groq Performance Tier | Higher priority | ~$100-200/mo | Medium |
| Cerebras Developer | From $10 | From $10 | Low |
| Groq Enterprise LoRA | ~840 tok/s | Enterprise pricing | High |

**Recommended path:** Start with cache + prompt caching (covers 80% of cases at $0). If insufficient, upgrade to Groq Performance Tier (~$100-200/mo).

## Phase 4 — Multi-Agent Expansion

**Goal:** Not just translation — multiple content adaptation modes.

**Agents:**
- **Translator:** Translate to any language preserving structure
- **Simplifier:** Reduce technical difficulty
- **Expander:** Generate new sections on demand
- **Accessibility:** Rewrite for dyslexia, low vision, etc.

**Router:** A small classifier (Needle or keyword-based) decides which agent to activate based on user intent.

**Cost:** Same as Phase 3, multiplied by N agents. Each agent is just a different prompt on the same model.

## Cost Summary

| Phase | Initial cost | Monthly cost | Token/s |
|---|---|---|---|
| Phase 0: Validation | $0 | $0 | ~200-800 |
| Phase 1: Functional | $0 | $0 | ~200-800 |
| Phase 2: Quality (LoRA) | ~$10 | ~$50-100 | ~200-400 |
| Phase 3: Speed | ~$0-100 | ~$100-300 | ~500-1,000 |
| Phase 4: Multi-agent | ~$0 | ~$100-300 | ~500-1,000 |

**Total for real production:** ~$50-100/mo (Phase 2).

## Future Decisions

- [ ] Base model for LoRA (Llama 3.1 8B, Qwen3 8B, Gemma 4)
- [x] Hosting for fine-tuned model
- [ ] Dataset size (500, 1,000, 2,000 pairs)
- [ ] Priority languages (French, German, Portuguese, Chinese)
- [ ] Cache: duration, invalidation strategy
- [ ] Router: rules-based or small model (Needle)
- [ ] Security: rate limiting, auth, output sanitization
