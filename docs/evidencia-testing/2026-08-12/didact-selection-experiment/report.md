# Experimento offline de selección Didact

Fecha: 2026-08-12  
Benchmark: `didact-selection/1`  
Catálogo: los 34 `ComponentDescriptor` exportados por el snapshot Didact actual  
Corpus: 10 intenciones/perfiles fijos, compartidos sin cambios por los cuatro brazos  
Ejecución: 500 repeticiones por caso y brazo, sin red, LLM ni base de datos

## Pregunta

Qué política ofrece el mejor equilibrio entre versatilidad y personalización antes de
entregar componentes a OpenUI:

1. catálogo elegible completo;
2. ranking por facetas con `k=3`;
3. ranking por facetas con `k=5`;
4. ranking por facetas y relevancia léxica, con diversidad MMR y `k=5`.

Todos los brazos reciben exactamente el mismo conjunto tras los filtros duros de
misión, función de la fuente, requisitos disponibles y accesibilidad. Presentación y
acciones preferidas son señales de ranking, no filtros.

## Resultado cuantitativo

| Política | Recall relevante | Precisión | Cobertura de acciones | Prohibidos | Preferencia | Diversidad semántica |
|---|---:|---:|---:|---:|---:|---:|
| elegible completo | 1.000 | 0.247 | 1.000 | 26.3% | 59.0% | 0.431 |
| facetas k=3 | 0.933 | **0.450** | 1.000 | **15.0%** | **75.0%** | 0.429 |
| facetas k=5 | 0.967 | 0.315 | 1.000 | 23.5% | 67.0% | 0.414 |
| facetas + MMR k=5 | **1.000** | 0.335 | 1.000 | 21.5% | 67.0% | 0.416 |

Los tiempos medianos de la ejecución conservada fueron 0.001 ms para el catálogo
completo, 0.011–0.012 ms para facetas y 0.415 ms para MMR. Incluso MMR queda en
4.002 ms en p95 en este catálogo; la latencia no decide el resultado.

## Lectura

- **`facets-k3` es el mejor valor por defecto para personalización.** Frente al
  catálogo completo aumenta el ajuste a preferencias de 59% a 75%, casi duplica la
  precisión (24.7% a 45.0%) y reduce la tasa de componentes marcados como
  contraproducentes de 26.3% a 15.0%. Sacrifica 6.7 puntos de recall.
- **`facets-mmr-k5` es el brazo conservador cuando no se puede perder cobertura.**
  Recupera 100% de recall y mejora precisión/prohibidos respecto a `facets-k5`, pero
  pierde personalización frente a `k=3`.
- **La diversidad MMR no queda validada como beneficio material.** A igual `k=5`, la
  diversidad solo pasa de 0.414 a 0.416. La mejora de recall proviene sobre todo de la
  señal léxica en el caso de evaluaciones de elección, no de una expansión semántica
  clara.
- **El catálogo completo maximiza cobertura por construcción, no calidad de
  selección.** También entrega muchos distractores y reduce el ajuste de
  presentación; no conviene como contexto normal del modelo.

## Hallazgo de contrato

Los 34 descriptores actuales exportan **cero `evidence_events`**. Los diez casos piden
una señal observable y todos los brazos obtienen cobertura explícita 0.0. El bench no
la imputa a partir del nombre o del tipo de productor. Esto impide comparar selección
por evidencia de forma honesta y señala una carencia del contrato, no del ranking.

## Recomendación

Usar `facets-k3` como hipótesis principal y ampliar dinámicamente a cinco candidatos
cuando los tres primeros no cubran componentes relevantes o acciones deseadas. No
adoptar MMR todavía: repetir después de enriquecer los descriptores con eventos de
evidencia y añadir más casos con candidatos semánticamente redundantes.

## Reproducción

Desde `apps/skillnet-api`:

```powershell
.venv\Scripts\python.exe scripts/didact_selection_experiment.py `
  tests/fixtures/didact-selection-v1.json `
  --repetitions 500 `
  --out ..\..\docs\evidencia-testing\2026-08-12\didact-selection-experiment\report.json

.venv\Scripts\python.exe -m pytest tests/test_didact_selection_experiment.py -q
```

El JSON conserva los resultados por caso, shortlists, métricas agregadas, parámetros
de política y latencias. Las pruebas verifican catálogo de 34 entradas, igualdad de
entrada entre brazos, límites `k`, selección de componentes especializados y la
ausencia explícita de evidencia.
