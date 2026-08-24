---
title: "Opciones de servicio de LoRA"
order: 62
section: "research"
---

# Opciones de servicio de LoRA para la UI de SkillNet

## Contexto

SkillNet necesita generar UI (A2TL-Web/JSON) usando una LoRA entrenada. El objetivo es servir la LoRA más rápido que una RTX 4060 local (~20-50 tok/s) sin gestionar infraestructura compleja.

**No hace falta multi-LoRA.** Solo se necesita una única LoRA alojada.

## Opciones verificadas

| Opción | Aloja LoRA propia | Modelo base | Coste aproximado | Velocidad aproximada | Facilidad |
|---|---|---|---|---|---|
| **Groq LoRA** | Sí, solo Enterprise | Oficialmente solo `Llama 3.1 8B` | Sin precio público | ~560 tok/s (base 8B) | Media |
| **Together AI** | Sí, endpoint dedicado | Amplio (Llama, Qwen, Mistral, etc.) | H100: $5.49/h por minuto en línea | No publicado oficialmente | Fácil |
| **Fireworks AI** | Sí, solo on-demand | Amplio (Llama, Qwen, DeepSeek, etc.) | H100: $7/h por minuto en línea | ~90 tok/s en 8B H100 | Fácil |
| **Modal** | Sí, con self-host de vLLM | Cualquier modelo soportado por vLLM | H100: $3.95/h, L4: $0.80/h | Depende de la GPU y la config | Difícil |
| **Cerebras** | Sí, Enterprise + preview | Llama, Qwen3-Coder, GPT-OSS, etc. | Sin precio público | ~1.000-1.700 tok/s | Muy difícil |

## Análisis por opción

### Groq
- Proceso claro: subir un ZIP con `adapter_model.safetensors` + `adapter_config.json`, registrarlo como modelo fine-tuned, llamarlo vía API.
- Limitación dura: solo `Llama 3.1 8B` según la documentación actual. El 70B mencionado en un anuncio de 2025 ya no aparece.
- Cold start proporcional al rank (8, 16, 32, 64).
- **Veredicto:** bien si se consigue acceso Enterprise y 8B es suficiente. No es self-service.

### Together AI
- Entrena y sirve LoRAs. Fine-tuning desde $0.48/1M tokens (≤16B).
- Servir requiere un endpoint dedicado.
- Se factura por minuto de GPU activa.
- **Veredicto:** bueno para iterar, pero hay que apagar el endpoint para evitar coste continuo.

### Fireworks AI
- Similar a Together. Fine-tuning de LoRA desde $0.50/1M tokens (≤16B).
- LoRAs propias solo en despliegues on-demand.
- El merge en vivo ofrece el mismo rendimiento que el modelo base.
- **Veredicto:** opción equilibrada para empezar.

### Modal
- Más barato que Together/Fireworks (L4 a $0.80/h, H100 a $3.95/h).
- Requiere montar vLLM, volúmenes, autoscaling.
- Cold starts si `min_containers=0`.
- **Veredicto:** mejor coste a largo plazo, pero más trabajo.

### Cerebras
- Multi-LoRA en preview privada para endpoints dedicados.
- El proceso para una sola LoRA no está documentado públicamente.
- Requiere Enterprise. Sin precio público.
- **Veredicto:** excesivo para una sola LoRA. Solo para escala de producción masiva.

## Costes mensuales realistas (Fireworks H100)

| Uso | Coste mensual |
|---|---|
| 2 h/día | ~$15-20 |
| 8 h/día | ~$170 |
| 24/7 | ~$500 |

Modal L4 24/7: ~$580/mes, pero mucho más barato por hora.

## Recomendación para SkillNet

1. **Entrenar la LoRA en Fireworks AI o Together AI** (self-service, barato).
2. **Servirla en Fireworks on-demand** con un modelo pequeño (8B-9B) y autoscaling a 0 para evitar coste continuo.
3. Si el uso se vuelve regular, evaluar **Modal con L4** para reducir coste.
4. **Groq o Cerebras** solo si se obtiene acceso Enterprise y se justifica velocidad extrema.

## Próximos pasos

- Definir el formato A2TL-Web/JSON de SkillNet.
- Generar 100-200 ejemplos de entrenamiento.
- Entrenar una LoRA de prueba en Fireworks/Together.
- Medir velocidad y calidad frente a la RTX 4060 local.

## Fuentes

- Docs de Groq LoRA: https://console.groq.com/docs/lora
- Fine-tuning de Together AI: https://docs.together.ai/docs/fine-tuning/overview
- Precios de endpoints dedicados de Together AI: https://docs.together.ai/docs/dedicated-endpoints/pricing
- Fine-tuning de Fireworks: https://docs.fireworks.ai/fine-tuning/fine-tuning-models
- Precios de Fireworks: https://fireworks.ai/pricing
- Precios de Modal: https://modal.com/pricing
- Blog de Multi-LoRA de Cerebras: https://www.cerebras.ai/blog/introducing-multi-lora-on-cerebras-inference
- Endpoints dedicados de Cerebras: https://inference-docs.cerebras.ai/dedicated/overview
