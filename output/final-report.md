# Informe final de pruebas de generación

Fecha de ejecución: 2026-08-13.

## Alcance

- 5 rondas de generación on-the-fly.
- 10 perfiles inventados por ronda.
- 508 pantallas capturadas en total en las rondas principales.
- Pruebas de generación de cursos v1 y v2.
- Comparación de formatos, componentes, longitud, caché, errores y similitud entre perfiles.
- Todos los runners tienen timeout HTTP, timeout de render, timeout de job y captura de errores por perfil.

## Resultados por ronda

| Ronda | Versión | Perfiles | Pantallas | Media caracteres | Máximo | Similitud media | Concepto + QuizItem |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | runtime/30 | 10 | 80 | 639,7 | 920 | 0,4683 | 0 |
| 2 | runtime/31 | 10 | 80 | 641,3 | 1050 | 0,4260 | 0 |
| 3 | runtime/32 | 10 | 120 | 639,1 | 910 | 0,3941 | 0 |
| 4 | runtime/33 | 10 | 120 | 850,0 | 2879 | 0,2805 | 0 |
| 5 | runtime/34 | 10 | 108 | 820,3 | 2879 | 0,2505 | 0 |

La ronda 4 bajó mucho la similitud y aumentó la variedad, pero se rechazó como tratamiento final por el exceso de contenido en fallback. La ronda 5 mantuvo la diversidad y añadió `StepSequence` y `BeforeAfter`.

## Hallazgos

1. El problema de “explicar y preguntar lo mismo” no aparece en las 508 pantallas: `concepto + QuizItem` fue `0` en todas las rondas.
2. La práctica actual se presenta como actividad Didact o Flashcard y no como un QuizItem repetitivo. En las capturas no hubo QuizItems, por lo que las estrategias de respuestas erróneas no pudieron probar adaptación de mastery.
3. La personalización es visible: la similitud media bajó de `0,4683` a `0,2505` entre perfiles y rondas, especialmente al combinar roles, preferencias, experiencia y cursos con formas distintas.
4. La variedad estructural mejora con cursos procedimentales: en la ronda 5 aparecieron `StepSequence` 12 veces y `BeforeAfter` una vez, además de `Flashcard`, `HintReveal` y actividades Didact.
5. La composición dominante sigue siendo `Stack + TextContent + Table`. No debe aceptarse variedad decorativa: la forma debe depender de listas, procedimientos, contrastes o cifras reales.
6. El límite de prompt no bastó para controlar fallback. El origen del outlier de `2879` caracteres era determinista: `FALLBACK_BLOCK_CHARS=2800`.
7. Se corrigió el fallback a `300` caracteres por bloque y como máximo dos bloques, además del lead. Las dos pruebas focalizadas de fallback pasan y el smoke posterior quedó en `1550` caracteres máximos sin Markdown largo.
8. `Devoluciones en tienda` contiene varios nodos con contenido de platos/comida y produjo fallbacks en algunas ejecuciones. Requiere revisión del documento/schema de origen antes de usarlo como curso de producción.
9. La generación v2 funcionó de forma consistente: propuestas de 6-8 nodos, estado `schema_proposed`, revisión, validación `200`, `schema_status=validated` y `delivery_mode=dynamic`.
10. La generación v1 funcionó en varios smoke tests, pero es más lenta y algunas ejecuciones superaron el límite de 300 s. Esto debe tratarse como una limitación operacional independiente del runtime v2.

## Cambios conservados

- `runtime/36` en `apps/skillnet-api/src/llm/prompts/runtime.py`.
- Prompt de transferencia entre concepto y práctica.
- Reglas de variedad justificada por la forma del material.
- Reglas de contexto por puesto y sector.
- Restricciones explícitas de viewport.
- Fallback compacto en `apps/skillnet-api/src/agents/runtime/nodes.py`.
- Harness y evidencia en `output/`.

## Limitaciones

- La sesión no recargó los agentes personalizados creados después de arrancar OpenCode. Las rondas
  ejecutadas usaron el subagente `general`; esas configuraciones locales no formaban parte del
  producto ni de la evidencia reproducible y se retiraron al cerrar la campaña.
- Los renders observados no contenían QuizItems; falta una ronda específica sobre actividades Didact, respuestas, mastery, errores y replanificación posterior.
- La métrica de “sin scroll” es una aproximación por caracteres/programa. Falta validación visual real en navegador para cada componente.
- Las respuestas `409` de matrícula son esperadas por idempotencia y no son fallos del producto.

## Evidencia

- `output/rounds/round-01/summary.json`
- `output/rounds/round-02/summary.json`
- `output/rounds/round-03/summary.json`
- `output/rounds/round-04/summary.json`
- `output/rounds/round-05/summary.json`
- `output/harness/profile_run.py`
- `output/harness/course_run.py`
- `output/harness/analyze_round.py`
