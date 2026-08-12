# Selección Didact R2: facetas, BM25 e híbridos

Fecha: 2026-08-12  
Ámbito: experimento offline; no modifica el runtime.

## Pregunta

¿Qué política ofrece una shortlist de componentes Didact versátil y personalizada sin
entregar los 34 contratos a OpenUI?

Se compararon cinco políticas sobre los mismos 12 perfiles/objetivos y el inventario
completo de 34 tipos. En todos los casos se aplicaron antes los mismos hard gates:
misión, función de la fuente, puertos disponibles y accesibilidad.

## Configuración reproducible

- Fixture: `tests/fixtures/didact-shortlist-v1.json`, versión `didact-shortlist/1`.
- Corpus: snapshot Didact fijado en el repositorio; incluye nombres, descripciones,
  facetas, capacidades, familias, campos de autoría y variantes.
- `top_k=5`.
- BM25: `k1=1.5`, `b=0.75`.
- Híbrido: 55% facetas y 45% BM25.
- Variante diversa: 18% de novedad por distancia Jaccard entre documentos.
- Facetas: fuente 35%, presentación 20%, affordances 40% y orden de catálogo 5%.

No se utilizó un embedding real. El repositorio no contiene pesos versionados de un
modelo local; llamar a un proveedor o descargar pesos haría que esta ronda dejase de
ser offline y reproducible. La estrategia se denomina por ello `bm25-top5`, no
«semántica». Esta ronda sirve como proxy léxico y como línea base para comparar un
embedding local posteriormente.

Comando:

```powershell
cd apps/skillnet-api
.\.venv\Scripts\python.exe scripts\didact_shortlist_experiment.py `
  tests\fixtures\didact-shortlist-v1.json `
  --out ..\..\docs\evidencia-testing\2026-08-12\didact-shortlist-r2\report.json
```

## Resultados

| Política | Tamaño medio | Recall relevante | Evidencia | Affordances | Preferencia | Tipos distintos | Diversidad interna | Latencia media* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Elegibles completos | 10,33 | 100% | 100% | 100% | 100% | 31 | 0,799 | 0,002 ms |
| Facetas top 5 | 4,50 | 95,8% | 100% | 100% | 95,8% | 24 | 0,783 | 0,219 ms |
| BM25 top 5 | 4,50 | 91,7% | 100% | 100% | 91,7% | 26 | 0,786 | 0,192 ms |
| Híbrido facetas + BM25 | 4,50 | 95,8% | 100% | 100% | 95,8% | 24 | 0,786 | 0,228 ms |
| Híbrido + diversidad | 4,50 | 95,8% | 100% | 100% | 95,8% | 24 | 0,790 | 0,657 ms |

Todos obtuvieron cero componentes prohibidos. *La latencia mide únicamente el algoritmo
en un proceso local y una ejecución; no incluye LLM, red, serialización del prompt ni
render. Sirve para comparar órdenes de magnitud, no para predecir la latencia del curso.

## Qué aprendimos

1. El catálogo completo maximiza cobertura, pero después de los gates todavía entrega
   10,33 componentes de media. Es una referencia de techo, no una shortlist apropiada.
2. Las facetas top 5 conservan toda la evidencia y todos los affordances esperados,
   reducen el contexto un 56% frente al conjunto elegible medio y alcanzan 95,8% de
   recall y preferencia.
3. BM25 aumenta la cobertura global del catálogo de 24 a 26 tipos, pero pierde cuatro
   puntos de recall/preferencia. La variedad de catálogo por sí sola no implica una
   selección mejor personalizada.
4. El híbrido recupera la calidad de facetas, pero en este corpus no mejora su cobertura
   global. BM25 cambia el orden, no el conjunto final de forma útil.
5. Forzar diversidad mejora muy poco la distancia interna (0,786 → 0,790) y casi triplica
   el coste algorítmico del híbrido. No justifica activarlo todavía.
6. El 4,2% que falta en facetas e híbridos corresponde al caso de escenario de decisión:
   seleccionan correctamente `didact.branching-scenario`, pero dejan fuera un quiz
   genérico secundario. La evidencia principal permanece cubierta.

## Decisión provisional

Usar **facetas top 5 como baseline de producto**. Es la opción más simple que conserva
la calidad importante en esta ronda. Mantener el híbrido detrás del banco de pruebas,
sin llevarlo aún al runtime.

La siguiente prueba que sí puede cambiar esta decisión es repetir exactamente este
fixture con un modelo de embeddings local cuyos pesos, versión y normalización queden
fijados. Debe superar 95,8% de recall/preferencia o aumentar variedad sin perder
evidencia. Hasta entonces, llamar «semántica» a BM25 sería engañoso.

## Artefactos

- Resultado completo por caso: `report.json`.
- Script: `apps/skillnet-api/scripts/didact_shortlist_experiment.py`.
- Fixture: `apps/skillnet-api/tests/fixtures/didact-shortlist-v1.json`.
- Tests: `apps/skillnet-api/tests/test_didact_shortlist_experiment.py`.

Validación: 5 tests pasan. `py_compile` pasa. Ruff no pudo ejecutarse en esta sesión
porque Windows denegó la ejecución del binario de la venv; no se afirma un resultado de
lint inexistente.

## Seguimiento: estabilidad, causalidad y tamaño dinámico

Se ejecutó una segunda ronda sobre el ganador `facets-top5`. El resultado detallado está
en `sensitivity.json`.

### Estabilidad e invariantes

- 36 perturbaciones controladas de redacción: mayúsculas/puntuación, inversión de los
  términos de búsqueda y paráfrasis mínima.
- Coincidencia exacta de shortlist: 100%; churn medio y máximo: 0.
- Se retiraron todos los puertos disponibles en los 10 perfiles que declaraban alguno.
  Ningún componente con requisitos atravesó los hard gates: 0 violaciones.

La estabilidad de wording es deliberada: la política de facetas no lee el texto libre.
Evita variación accidental, pero tampoco comprende matices expresados únicamente en la
redacción.

### Sensibilidad causal a presentación

Cuatro perfiles cambiaron explícitamente su presentación preferida. La cuota de
componentes compatibles nunca empeoró, pero el lift medio fue solo **8,3 puntos** y el
churn medio 0,20. Solo uno de cuatro probes cambió materialmente.

Esto descubre una limitación: la preferencia de presentación es causal, pero débil. La
mayoría de candidatos comparten representación o las demás facetas dominan. Antes de
afirmar una personalización fuerte conviene usar la presentación como criterio de
desempate más potente o medir su efecto por familias con alternativas reales.

### k3, k5 y expansión 3→5

La política dinámica empieza con tres componentes y amplía a cinco únicamente si falta
un affordance solicitado o existe empate exacto en el corte entre posiciones 3 y 4.
No usa componentes relevantes ni preferencias etiquetadas para tomar la decisión.

| Política | Tamaño medio | Recall | Preferencia | Evidencia | Affordances | Expansiones |
|---|---:|---:|---:|---:|---:|---:|
| k3 fijo | 2,92 | 88,9% | 91,7% | 100% | 100% | — |
| k5 fijo | 4,50 | 95,8% | 95,8% | 100% | 100% | — |
| Dinámico 3→5 | 3,83 | 91,7% | 95,8% | 100% | 100% | 6/12 |

El dinámico reduce un 14,8% el contexto respecto a k5 y conserva preferencia, evidencia
y affordances, pero pierde 4,1 puntos de recall. Con solo 34 componentes y contratos
compactos, el ahorro no compensa todavía la pérdida.

**Decisión afinada:** conservar `facets-top5` fijo como baseline. Mantener 3→5 como
variante experimental para contextos con presupuesto muy restringido. No llevar la
expansión dinámica al runtime hasta tener una señal de incertidumbre mejor calibrada que
un empate de puntuación.

Validación del seguimiento: 6 tests y `py_compile` pasan.
