# Selección de componentes — ronda 1

**Fecha:** 2026-08-12  
**Estado:** experimento offline; no modifica el runtime ni los cursos servidos.  
**Catálogo:** `skillnet-ui/1+1308d5c93feb`, 11 actividades adaptadas.  
**Fixture:** `component-selection/1`, seis intenciones, shortlist `k=2`.

## Pregunta

¿Podemos reducir el catálogo que verá el generador sin perder componentes válidos,
acciones educativas ni eventos de evidencia?

## Brazos

1. `eligible-full`: aplica solo restricciones duras y conserva todos los elegibles.
2. `facets-top-k`: puntúa función de fuente, presentación, affordances, evidencia y rango.
3. `lexical-diverse-top-k`: recuperación TF-IDF local más un bonus de diversidad. No es un
   embedding semántico.

Los tres brazos aplican antes los mismos filtros de misión, función de fuente, requisitos y
accesibilidad. No hubo LLM, red, base de datos ni juez subjetivo.

## Resultados

| Estrategia | Hit en casos | Recall relevante | Precisión | Affordances | Evidencia | Prohibidos |
|---|---:|---:|---:|---:|---:|---:|
| Elegibles completos | 100 % | 100 % | 86,1 % | 100 % | 100 % | 0 |
| Facetas, top 2 | 100 % | 94,4 % | 91,7 % | 94,4 % | **100 %** | 0 |
| Léxico diverso, top 2 | 100 % | 94,4 % | 91,7 % | 94,4 % | 83,3 % | 0 |

El coste local fue despreciable: p95 aproximado de `0,0065 ms`, `0,015 ms` y `0,254 ms`
respectivamente. Estas cifras solo miden selección en memoria, no generación OpenUI.

## Hallazgo principal

La diversidad léxica no fue una mejora gratuita. En el caso de reconstruir un procedimiento eligió
`StepSequence + HintReveal`, una combinación razonable para aprender, pero dejó fuera `DragOrder` y
perdió el evento obligatorio `order_checked`. El selector por facetas eligió
`DragOrder + StepSequence`: conservó la evidencia, aunque perdió el apoyo progresivo de
`HintReveal`.

Esto demuestra por qué la variedad no puede optimizarse independientemente de evidencia y apoyo. El
próximo selector debe cubrir primero obligaciones y usar la diversidad para ocupar los huecos
restantes, no competir contra ellas en una suma única.

## Lo que esta ronda no demuestra

- No compara calidad de cursos generados.
- No prueba embeddings semánticos.
- Los conjuntos relevantes/prohibidos son golds pequeños declarados para el banco.
- El catálogo adaptado todavía es menor que Didact completo.
- `k=2` puede ser demasiado agresivo; se comparará con `k=3` y `k=5`.

## Decisión y siguiente ronda

No se promueve ningún selector a producción. La siguiente ronda mantendrá puertas duras comunes y
comparará:

1. facetas con cobertura obligatoria y después diversidad;
2. recuperación semántica local si existe un modelo real, nunca vectores hash de fixture;
3. `k=2`, `k=3` y `k=5`;
4. el mismo scope convertido a fragmento de prompt en renders controlados.

La generación real solo comenzará cuando seguridad, hechos críticos, evidencia y accesibilidad sean
gates no compensables. Latencia, tokens y coste se compararán aparte de la calidad.

## Reproducción

```bash
cd apps/skillnet-api
uv run python scripts/component_selection_bench.py \
  tests/fixtures/component-selection-v1.json
```

Implementación: `scripts/component_selection_bench.py`. Evaluador de futuras rondas:
`src/agents/runtime/selection_eval.py`. Constructor de scopes experimentales:
`src/render/prompt_slice.py`.
