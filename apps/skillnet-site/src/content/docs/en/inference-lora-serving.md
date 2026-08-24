---
title: "LoRA serving options"
order: 62
section: "research"
---

# LoRA Serving Options for SkillNet UI

## Context

SkillNet needs to generate UI (A2TL-Web/JSON) using a trained LoRA. The goal is to serve the LoRA faster than a local RTX 4060 (~20-50 tok/s) without managing complex infrastructure.

**Multi-LoRA is not needed.** Only a single hosted LoRA is required.

## Verified Options

| Option | Hosts Custom LoRA | Base Model | Approximate Cost | Approximate Speed | Ease |
|---|---|---|---|---|---|
| **Groq LoRA** | Yes, Enterprise-only | Officially only `Llama 3.1 8B` | No public pricing | ~560 tok/s (base 8B) | Medium |
| **Together AI** | Yes, dedicated endpoint | Wide (Llama, Qwen, Mistral, etc.) | H100: $5.49/h per minute online | Not officially published | Easy |
| **Fireworks AI** | Yes, on-demand only | Wide (Llama, Qwen, DeepSeek, etc.) | H100: $7/h per minute online | ~90 tok/s on 8B H100 | Easy |
| **Modal** | Yes, with vLLM self-host | Any model supported by vLLM | H100: $3.95/h, L4: $0.80/h | Depends on GPU and config | Hard |
| **Cerebras** | Yes, Enterprise + preview | Llama, Qwen3-Coder, GPT-OSS, etc. | No public pricing | ~1,000-1,700 tok/s | Very hard |

## Analysis by Option

### Groq
- Clear process: upload a ZIP with `adapter_model.safetensors` + `adapter_config.json`, register as fine-tuned model, call via API.
- Hard limitation: only `Llama 3.1 8B` according to current docs. The 70B mentioned in a 2025 announcement no longer appears.
- Cold start proportional to rank (8, 16, 32, 64).
- **Verdict:** good if Enterprise access is granted and 8B is enough. Not self-service.

### Together AI
- Trains and serves LoRAs. Fine-tuning from $0.48/1M tokens (≤16B).
- Serving requires a dedicated endpoint.
- Billed per minute of GPU uptime.
- **Verdict:** good for iteration, but the endpoint must be shut down to avoid continuous cost.

### Fireworks AI
- Similar to Together. LoRA fine-tuning from $0.50/1M tokens (≤16B).
- Custom LoRAs only on on-demand deployments.
- Live merge offers the same performance as the base model.
- **Verdict:** balanced option to start.

### Modal
- Cheaper than Together/Fireworks (L4 at $0.80/h, H100 at $3.95/h).
- Requires setting up vLLM, volumes, autoscaling.
- Cold starts if `min_containers=0`.
- **Verdict:** better long-term cost, but more work.

### Cerebras
- Multi-LoRA in private preview for dedicated endpoints.
- Process for a single LoRA is not publicly documented.
- Enterprise required. No public pricing.
- **Verdict:** overkill for a single LoRA. Only for massive production scale.

## Realistic Monthly Costs (Fireworks H100)

| Usage | Monthly Cost |
|---|---|
| 2 h/day | ~$15-20 |
| 8 h/day | ~$170 |
| 24/7 | ~$500 |

Modal L4 24/7: ~$580/month, but much cheaper per hour.

## Recommendation for SkillNet

1. **Train the LoRA on Fireworks AI or Together AI** (self-service, cheap).
2. **Serve it on Fireworks on-demand** with a small model (8B-9B) and autoscaling to 0 to avoid continuous cost.
3. If usage becomes regular, evaluate **Modal with L4** to reduce cost.
4. **Groq or Cerebras** only if Enterprise access is obtained and extreme speed is justified.

## Next Steps

- Define the SkillNet A2TL-Web/JSON format.
- Generate 100-200 training examples.
- Train a test LoRA on Fireworks/Together.
- Measure speed and quality against local RTX 4060.

## Sources

- Groq LoRA docs: https://console.groq.com/docs/lora
- Together AI fine-tuning: https://docs.together.ai/docs/fine-tuning/overview
- Together AI dedicated endpoints pricing: https://docs.together.ai/docs/dedicated-endpoints/pricing
- Fireworks fine-tuning: https://docs.fireworks.ai/fine-tuning/fine-tuning-models
- Fireworks pricing: https://fireworks.ai/pricing
- Modal pricing: https://modal.com/pricing
- Cerebras Multi-LoRA blog: https://www.cerebras.ai/blog/introducing-multi-lora-on-cerebras-inference
- Cerebras dedicated endpoints: https://inference-docs.cerebras.ai/dedicated/overview
