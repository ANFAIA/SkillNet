# Screening offline de pantallas Didact

Fecha: 2026-08-12. Modelo: `fixture/local`. Repeticiones: 1. Casos/perfiles
emparejados: 5. Presupuesto: 1.200 tokens de salida en los tres brazos.

## Frontera auditada

Antes de construir cualquier prompt, los tres brazos se limitaron estrictamente a los
cinco componentes que el catálogo marca hoy como `emittable`:

- `didact.flashcard`
- `didact.glossary-term`
- `didact.hint-reveal`
- `didact.timeline-steps`
- `didact.worked-example`

Se compararon `full-emittable`, `facets-top5` y
`experience-intent-facets-top5`. Como `k=5` y la frontera contiene exactamente cinco
componentes, las tres estrategias produjeron el mismo conjunto canónico de schemas en
los cinco casos. Solo cambió el orden previo al slice, que este normaliza a propósito.

## Resultado

| Métrica | Full emitible | Facets top-5 | Intent + facets top-5 |
|---|---:|---:|---:|
| UI válida / first pass | 100% | 100% | 100% |
| Cumplimiento del scope Didact | 0% | 0% | 0% |
| Firmas distintas (5 pantallas) | 1 | 1 | 1 |
| Proxy factual medio | 30% | 30% | 30% |
| Preferencia satisfecha | 80% | 80% | 80% |
| Affordance Didact disponible | 0% | 0% | 0% |
| Evidencia disponible | 0% | 0% | 0% |
| Prompt medio | 2.688 chars / 672 tokens proxy | igual | igual |

La latencia del replay osciló en decenas de milisegundos y no se interpreta como una
diferencia entre políticas con una repetición.

## Bloqueo observado

El fixture de `genera_ui` está desactualizado respecto a esta integración: reproduce la
misma pantalla antigua con `StepSequence` para las 15 llamadas. Esa pantalla es válida
para el catálogo general del runtime, pero `StepSequence` no pertenece al scope cerrado
de estos cinco Didact; por eso el cumplimiento del scope es 0% y ninguna salida usa una
affordance Didact. El mismo texto de devoluciones explica además el proxy factual del
30%: acierta el caso de devoluciones, toca parcialmente el de extintor por una palabra y
falla los demás. No es evidencia de calidad de ningún selector.

## Conclusión

El selector live **no puede evaluarse todavía con este screening**. Hay dos bloqueos
independientes y reproducidos:

1. cinco emitibles con `top-5` hacen que todos los brazos sean idénticos;
2. `fixture/local` no genera los nuevos tipos Didact ni responde al scope.

No hay ganador. Para que una siguiente ronda discrimine, primero deben ser emitibles más
de cinco familias seguras y después debe grabarse un fixture sensible a los nuevos
prompts (o ejecutarse un modelo real bajo un protocolo aprobado).

El detalle de los 15 renders queda en `report.json`; el script reproducible es
`apps/skillnet-api/scripts/didact_screening_bench.py` y el corpus fijo está en
`apps/skillnet-api/tests/fixtures/didact-screening-v1.json`.
