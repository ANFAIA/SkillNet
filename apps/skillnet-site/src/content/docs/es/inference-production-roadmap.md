---
title: "Hoja de ruta a producción"
order: 62
section: "research"
group: "inference"
---

# Hoja de Ruta a Producción: Páginas Vivas

> **Estado:** propuesta, no un plan en vigor. La función de "páginas vivas" (traducir, simplificar o ampliar una página a demanda) no está implementada; las fases 2 a 4 nunca se empezaron.

## Filosofía

Primero que funcione, luego optimizar. El concepto se valida con modelos gratuitos y lentos. Una vez que el sistema funciona, cada pieza mejora de forma independiente.

## Fase 0 — Validación del Concepto (ahora)

**Objetivo:** Demostrar que la idea funciona, aunque sea lenta.

**Stack:**
- Modelo gratuito: Llama 3.1 8B en Groq (capa gratuita)
- Página de skillnet-docs con el contenido separado como estado de React
- Entrada del usuario para el idioma destino
- Llamada directa a la API desde el frontend o un backend mínimo

**Resultado:** La página se traduce. Tarda entre 800ms y 7s según la caché esté fría o caliente. Pero FUNCIONA. Presentable como "esto es lo que hace, la optimización viene después."

**Coste:** $0 (capa gratuita de Groq)

**Tiempo:** 1-2 días

## Fase 1 — Iteración Funcional

**Objetivo:** Funcionar en un escenario real sin ser óptimo.

**Stack:**
- Backend mínimo (FastAPI o Node) que recibe peticiones y llama a Groq
- Streaming SSE para que la página se escriba en tiempo real
- Caché para resultados frecuentes

**Mejora respecto a la Fase 0:** El streaming lo hace sentir instantáneo. Las traducciones repetidas vienen de la caché.

**Coste:** ~$0 (Groq gratis) + tiempo de backend

**Tiempo:** ~1 semana

## Fase 2 — Modelo Fine-Tuned (Calidad)

**Objetivo:** Traducciones correctas (acentos, gramática, terminología del dominio).

**Pasos:**
1. Generar 500-1.000 pares de markdown traducido
2. Entrenar una LoRA en GPU local (QLoRA 8B, ~1-2h) o GPU en la nube (A100, ~20 min)
3. Desplegar la LoRA en Together AI o Fireworks AI

**Resultado:** Traducciones idiomáticamente correctas. El modelo sabe que "français" lleva acento y que "employé" se escribe correctamente.

**Coste:** ~$10 (RunPod) + ~$50/mes (Together/Fireworks)

**Tiempo:** ~1 semana

## Fase 3 — Optimización de Velocidad

**Objetivo:** Respuesta en <500ms siempre.

| Opción | Latencia | Coste | Esfuerzo |
|---|---|---|---|
| Caché inteligente | Instantánea en repetición | $0 | Bajo |
| Prompt caching (Groq) | -50% coste de entrada | Incluido | Bajo |
| Groq Performance Tier | Mayor prioridad | ~$100-200/mes | Medio |
| Cerebras Developer | Desde $10 | Desde $10 | Bajo |
| Groq Enterprise LoRA | ~840 tok/s | Precio Enterprise | Alto |

**Ruta recomendada:** Empezar con caché + prompt caching (cubre el 80% de los casos a $0). Si no es suficiente, subir a Groq Performance Tier (~$100-200/mes).

## Fase 4 — Expansión Multi-Agente

**Objetivo:** No solo traducción — múltiples modos de adaptación de contenido.

**Agentes:**
- **Traductor:** Traduce a cualquier idioma preservando la estructura
- **Simplificador:** Reduce la dificultad técnica
- **Expansor:** Genera secciones nuevas bajo demanda
- **Accesibilidad:** Reescribe para dislexia, baja visión, etc.

**Router:** Un pequeño clasificador (Needle o basado en palabras clave) decide qué agente activar según la intención del usuario.

**Coste:** Igual que la Fase 3, multiplicado por N agentes. Cada agente es solo un prompt distinto sobre el mismo modelo.

## Resumen de Costes

| Fase | Coste inicial | Coste mensual | Token/s |
|---|---|---|---|
| Fase 0: Validación | $0 | $0 | ~200-800 |
| Fase 1: Funcional | $0 | $0 | ~200-800 |
| Fase 2: Calidad (LoRA) | ~$10 | ~$50-100 | ~200-400 |
| Fase 3: Velocidad | ~$0-100 | ~$100-300 | ~500-1.000 |
| Fase 4: Multi-agente | ~$0 | ~$100-300 | ~500-1.000 |

**Total para producción real:** ~$50-100/mes (Fase 2).

## Decisiones Futuras

- [ ] Modelo base para la LoRA (Llama 3.1 8B, Qwen3 8B, Gemma 4)
- [x] Hosting para el modelo fine-tuned — ver [Opciones de servicio de LoRA](/docs/inference-lora-serving)
- [ ] Tamaño del dataset (500, 1.000, 2.000 pares)
- [ ] Idiomas prioritarios (francés, alemán, portugués, chino)
- [ ] Caché: duración, estrategia de invalidación
- [ ] Router: basado en reglas o modelo pequeño (Needle)
- [ ] Seguridad: rate limiting, autenticación, saneamiento de salida
