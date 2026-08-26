---
title: "Aceleración de inferencia"
order: 61
section: "research"
group: "inference"
---

# Aceleración de inferencia

> **Estado:** las medidas de julio de 2026 siguen siendo válidas y Groq es un valor admitido de `LLM_MODEL`. El hardware especializado (LPU, oblea completa) se estudió, no se adoptó.

Hardware y modelos especializados para inferencia rápida de LLM, que permiten la generación de contenido en tiempo real. En lugar de esperar 10-30s a que una página se traduzca o adapte, hardware especializado puede hacerlo en <1s.

## El problema

La inferencia estándar de LLM (Claude, GPT-4) corre a ~50-100 tokens/segundo. Para una página de ~500 tokens, eso supone 5-10 segundos de espera. Para experiencias interactivas donde el usuario espera respuesta instantánea, esto es demasiado lento.

El cuello de botella no es el cómputo —es la memoria. Las GPU almacenan los pesos del modelo en HBM (High Bandwidth Memory) fuera del chip. Cada paso de inferencia dedica la mayor parte del tiempo a traer pesos desde memoria externa en lugar de calcular.

## Soluciones de hardware

### Groq — LPU (Language Processing Unit)

Groq construye un chip a medida llamado LPU, diseñado desde cero solo para inferencia (no para entrenamiento). Tres innovaciones clave:

1. **SRAM como almacenamiento principal.** En lugar de HBM externa, Groq integra cientos de MB de SRAM directamente en el procesador. La latencia de acceso baja de ~200ns (HBM) a ~10ns (SRAM).

2. **Planificación estática vía compilador.** Una GPU decide en tiempo de ejecución qué núcleos hacen qué (planificación dinámica). El compilador de Groq precalcula cada ciclo de reloj antes de la ejecución —sabe exactamente cuándo llega cada dato, qué núcleo lo procesa y en qué nanosegundo. Sin coherencia de caché, sin buffers de reordenación, sin sobrecarga de ejecución especulativa.

3. **Conectividad directa chip a chip.** Varias LPU se conectan directamente mediante un protocolo plesíncrono que alinea cientos de chips para actuar como un único núcleo. El compilador planifica tanto el cómputo como la red.

**Velocidades reales:** 500-1.000 tok/s según el modelo. Llama 3.1 8B corre a 840 tok/s, Qwen3 32B a 662 tok/s.

### Cerebras — WSE (Wafer-Scale Engine)

Cerebras toma el enfoque opuesto: hacer el chip tan grande que todo quepa en un único die.

1. **Un chip gigante.** El WSE-3 tiene 4 billones de transistores y 900.000 núcleos en un único procesador —~50x más grande que una GPU de NVIDIA. Sin interconexión chip a chip porque solo hay un chip.

2. **44 GB de SRAM en el propio chip** con 21 PB/s de ancho de banda de memoria. Aproximadamente 1.000-2.000x más ancho de banda efectivo de memoria que una NVIDIA B200 (que depende de HBM fuera del chip).

3. **Inferencia desagregada** (en colaboración con AWS). La inferencia tiene dos fases: prefill (procesamiento paralelo de la entrada, intensivo en cómputo) y decode (generación secuencial de tokens, limitada por ancho de banda de memoria). Cerebras se asoció con AWS de modo que Trainium se encarga del prefill y CS-3 del decode —cada uno optimizado para su fase.

**Velocidades reales:** Meta reporta 2.000 tok/s en Llama 4. OpenAI lanzó Codex-Spark a 1.200 tok/s en Cerebras.

### Comparación

| | GPU (NVIDIA) | Groq (LPU) | Cerebras (WSE-3) |
|---|---|---|---|
| Memoria | HBM fuera del chip | SRAM en el chip | SRAM en el chip |
| Tamaño del die | ~500 mm² | Estándar | ~46.000 mm² (a nivel de oblea) |
| Multi-chip | Se requieren muchos | Muchos actúan como uno | Chip único |
| Latencia de memoria | ~200ns (HBM) | ~10ns (SRAM) | ~10ns (SRAM) |
| Diseñado para | Propósito general | Solo inferencia | Inferencia (+ algo de entrenamiento) |

### Limitaciones

1. **Los modelos grandes no caben en SRAM.** Un modelo de 70B en FP16 necesita ~140 GB. Cerebras tiene 44 GB. Para estos modelos, hay que repartir entre varios chips, aumentando coste y complejidad.

2. **Solo inferencia.** Los modelos se entrenan en GPU. Cerebras también puede entrenar, pero no es el caso de uso principal.

3. **Ecosistema pequeño.** CUDA lleva 20 años de optimizaciones. Groq y Cerebras tienen sus propios compiladores. No todos los modelos están optimizados. Los modelos nuevos deben portarse.

4. **Modelos MoE.** Mixture-of-Experts (Mixtral, DeepSeek) activa solo 2 de 8 expertos por token. Esto es eficiente en GPU (se cargan menos pesos), pero en hardware limitado por SRAM no se pueden cargar todos los expertos a la vez.

## Resultados de pruebas (2026-07-15)

Prueba real con la API de Groq (nivel gratuito), traduciendo Markdown de skillnet-docs al francés.

**Arranque en frío (primera petición):** 7,5s de TTFB —carga del modelo en la LPU
**Caché caliente (peticiones siguientes):** 597ms de TTFB, 810ms en total para una página completa (~200 tokens)

**Modelos comparados:**

| Modelo | Tiempo total | Calidad de traducción | Tok/s |
|---|---|---|---|
| Llama 3.1 8B | 252ms | Acentos deficientes (e, é, è) | 258 |
| Llama 4 Scout | 314ms | Acentos deficientes | 185 |
| Qwen3 32B | 580ms | Buena, pero piensa en voz alta | 345 |
| Qwen3.6 27B | 491ms | Buena, pero piensa en voz alta | ~300 |

La velocidad es real —una página completa se traduce en <1s con caché caliente. Los problemas de acentos se resuelven con un modelo ajustado (LoRA).

## Precios (2026)

### Groq

| Modelo | Tok/s | Entrada (1M tok) | Salida (1M tok) |
|---|---|---|---|
| Llama 3.1 8B | 840 | $0,05 | $0,08 |
| Qwen3 32B | 662 | $0,29 | $0,59 |
| Llama 4 Scout | 594 | $0,11 | $0,34 |

Coste por traducción típica (~200 entrada + 500 salida): **$0,00005-$0,00035**.

### Cerebras

- **Gratis:** acceso a todos los modelos, límites de tasa básicos
- **Developer:** desde $10, 10x los límites de tasa
- **Enterprise:** endpoint dedicado, pesos personalizados, garantías de disponibilidad
- **Cerebras Code Pro:** $50/mes, 24M tokens/día

## Conexión con SkillNet

La reunión de la semana 3 identificó Groq y Cerebras como herramientas para la **generación de contenido al vuelo**. El modelo actual de dos capas (generar JSON offline → renderizar barato online) puede pasar a casi tiempo real si la generación corre a 1.000+ tok/s.

Para páginas en vivo (contenido que se transforma mientras el usuario interactúa), la inferencia rápida permite:
- Traducción de página en <1s (en lugar de 10-30s)
- Simplificación de contenido a petición del usuario
- Expansión dinámica de secciones bajo demanda

Este hardware existe hoy como servicio —no requiere despliegue on-premise.

## Decisiones relacionadas

- [Hoja de ruta de producción: páginas en vivo](/docs/inference-production-roadmap)
</content>
