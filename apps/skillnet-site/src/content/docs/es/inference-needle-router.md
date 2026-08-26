---
title: "Router Needle"
order: 64
section: "research"
group: "inference"
---

# Needle: Arquitectura de Router para Modelos Especializados

> **Estado:** exploratorio. Needle no se adoptó. El enrutado de peticiones se resolvió con un router de dos niveles `fast`/`heavy` (`apps/skillnet-api/src/agents/runtime/router.py`), sin modelo clasificador aparte. Se conserva por el argumento arquitectónico.

Needle es un modelo de 26M de parámetros de Cactus Compute, de código abierto (MIT), que hace una sola cosa: dados una consulta y una lista de herramientas, elige la herramienta correcta y rellena sus argumentos. Alcanza 1.200 tok/s de decode en dispositivos de consumo y se cuantiza a 14 MB en INT4.

## Por qué importa para SkillNet

El patrón de router: un único endpoint recibe todas las peticiones del usuario, las clasifica y las despacha al modelo especializado correcto. Needle está diseñado exactamente para esto — es un modelo de "tool calling", y las herramientas son simplemente rutas.

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

## Redes de atención simples

Needle está construido sobre una arquitectura novedosa que elimina todas las capas MLP (Feed-Forward Network) del transformer. Solo queda la atención.

**La tesis:** el tool calling no es razonamiento, es recuperación y ensamblaje. El modelo no necesita pensar. Necesita:
1. Emparejar la consulta con el nombre de herramienta correcto
2. Extraer los valores de los argumentos de la entrada
3. Ensamblar la salida JSON

Las tres operaciones consisten en alinear y copiar información que ya existe en la entrada. La cross-attention es la primitiva correcta para esto. Los parámetros de la FFN (que ocupan ~2/3 de un transformer estándar) se desperdician en esta tarea.

**Arquitectura:**
```
Standard transformer: Embed → Self-Attention → FFN → Self-Attention → FFN...
Needle:               Embed → Encoder (Self-Attention → Cross-Attention) → Decoder (Self-Attention → Cross-Attention)
                                        (no FFN anywhere)
```

**Decisiones de diseño clave:**
- **Encoder-decoder** (no decoder-only): el encoder ve las herramientas de forma bidireccional, entendiendo la estructura JSON completa. El decoder solo genera la salida. Los tokens de entrada no ocupan la caché KV.
- **Residuales con puerta (gated):** `x = x + sigmoid(gate) * Attn(Norm(x))`. Un escalar aprendible por capa decide cuánta atención añadir. Se inicializa a 0 (sigmoid(0) = 0.5), así que el entrenamiento empieza con la mitad de fuerza en el residual.
- **Cabeza de selección de herramienta contrastiva:** cabeza estilo CLIP que codifica consultas y herramientas en un espacio de 128 dimensiones para filtrado top-k cuando el conjunto de herramientas es grande.
- **INT4 QAT durante el entrenamiento:** la cuantización simulada cada 100 pasos actúa como regularización. El modelo entrena a la misma precisión con la que se despliega.

**Entrenamiento:**
- Preentrenado con 200B tokens en 16 TPU v6e (27 horas)
- Post-entrenado con 2B tokens de datos sintéticos de function-calling (45 minutos)
- Dataset sintetizado vía Gemini con 15 categorías de herramientas
- Ponderación de la pérdida: estructura JSON 1x, nombres de herramientas 2x, valores de argumentos 4x

## Cómo encaja Needle en el router

El router en sí es un modelo, en concreto un modelo de tool calling. Needle es el mejor candidato de código abierto para este papel porque:

1. **Corre localmente en CPU** — coste de API cero, latencia de red cero. 14 MB en INT4.
2. **Ajustable (fine-tunable) sobre herramientas propias** — la UI del playground genera datos vía Gemini y entrena un checkpoint con un clic.
3. **Se necesitan 120+ ejemplos por herramienta** — requisito de datos mínimo para el fine-tuning.
4. **Supera a modelos 10 veces más grandes** en function calling de un solo intento (FunctionGemma-270M, Qwen-0.6B, Granite-350M).

El router clasifica las peticiones en tres categorías:

1. **Transformación directa** (traducir, simplificar, resumir) → modelo rápido y barato
2. **Generación con contexto** (explicar un concepto nuevo, ampliar) → modelo más capaz
3. **Ambiguo / complejo** → modelo frontera (Claude, GPT)

Para la funcionalidad de páginas vivas de SkillNet, Needle clasificaría lo que quiere el usuario y despacharía al agente especializado adecuado.

## Enlaces

- GitHub: https://github.com/cactus-compute/needle
- Blog: https://cactuscompute.com/blog/needle
- Weights: https://huggingface.co/Cactus-Compute/needle
- Cactus (motor de inferencia): https://github.com/cactus-compute/cactus
