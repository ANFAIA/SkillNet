# Personalización longitudinal Didact 34/34 — ronda 1

Fecha: 2026-08-12  
Harness: `apps/skillnet-api/scripts/didact_learner_journey_bench.py`  
Fixture: `apps/skillnet-api/tests/fixtures/didact-learner-journeys-v1.json`

## Pregunta

¿Dos personas con perfiles y comportamiento diferentes reciben experiencias diferentes
durante un curso completo, sin cambiar el objetivo ni los hechos, y siguen adaptándose
después del onboarding?

## Método

Simulación determinista y reproducible, desconectada de producción y sin LLM. Cuatro
perfiles recorren cinco nodos del mismo curso. Cada trayectoria contiene seis observaciones:

1. render tras el onboarding;
2. render posterior a la primera respuesta/error;
3. render al superar los tres nodos de calibración;
4. regeneración del mismo nodo tras cambiar ajustes;
5. siguiente render después de la recuperación;
6. render de finalización.

Son 24 renders en total. En cada render el catálogo creativo recibido contiene los 34 tipos
Didact. Además de comparar personas, el harness genera contrafactuales emparejados: conserva
persona, nodo, objetivo y hechos, y cambia solo `last_error_kind`, `format_vector` o los
ajustes declarados. Así una diferencia puede atribuirse a esa señal.

La prueba usa la proyección y el planificador puros reales, además de las funciones reales de
`vector_bucket`, `preference_bucket` y `build_cache_key`. No mide calidad lingüística, tiempo
de proveedor, interfaz del navegador ni comportamiento estocástico de un modelo.

## Resultados

| Medida | Resultado |
|---|---:|
| Renders que consideraron el universo 34/34 | 100% |
| Preservación de objetivo y referencias de hechos | 100% |
| Integridad de progresión longitudinal | 100% |
| Trayectorias que llegaron a recuperación y finalización | 100% |
| Errores respondidos o perfil ya en apoyo máximo | 100% |
| Renders rechazados | 0% |
| Comprobaciones de caché superadas | 100% |
| Firmas diferentes entre cuatro perfiles por etapa | 4 de 4 |
| Cambio causal al modificar ajustes | 100% |
| Cambio causal ante una señal de error | 66,7% |
| Cambio causal por `format_vector` después de calibración | **25%** |
| Componentes utilizados en las 24 decisiones | 5 de 34 |
| Familias de productor utilizadas | 3 |

Las cuatro personas obtuvieron una firma distinta en todas las etapas. La firma incluye
componente, presentación, banda de apoyo, densidad, ejemplo resuelto y pistas graduadas; no
cuenta cambios invisibles de metadatos como adaptación educativa.

## Qué se ha demostrado

- El onboarding sí causa diferencias estables: novato visual, experto textual, usuario
  interactivo y perfil neutro no reciben la misma experiencia.
- Cambiar los ajustes durante el curso sí regenera causalmente otra experiencia en los cuatro
  perfiles probados.
- Los errores activan ayuda adicional cuando existe margen para hacerlo. El 66,7% no es un
  fallo aleatorio: el perfil novato ya tenía pistas activadas antes del error, por lo que la
  política actual se satura y no puede expresar “más ayuda”.
- Los objetivos y hechos permanecen idénticos mientras cambia la forma de aprender.
- La caché es repetible, ignora el vector durante los tres nodos de calibración, se separa por
  vector después y se invalida al cambiar ajustes. Una regeneración forzada queda aislada.

## Brechas descubiertas y primera corrección

### 1. El vector aprendido estaba desconectado del ranking

Después de calibración, `format_vector` cambia la clave de caché, pero el
`inferred_presentation_bucket` calculado por la proyección no participa en el ranking de
componentes de `plan_experience`. Resultado: se paga una nueva generación potencialmente
cacheada en otro bucket, pero el plan determinista sigue siendo el mismo.

El contrafactual inicial lo detectó con un 0%. Se aplicó una corrección mínima: después de
calibración, el bucket inferido desempata entre candidatos que ya superaron misión, fuente,
requisitos y accesibilidad. Nunca amplía elegibilidad y una preferencia declarada continúa
reduciendo primero el conjunto de candidatos.

Después de la corrección el cambio causal es 25%: cambia el perfil sin preferencia declarada;
los otros tres permanecen iguales porque su elección explícita vence correctamente a la
inferencia. Las pruebas unitarias cubren texto, visual, datos e interacción, ausencia de efecto
antes de calibración, bucket desconocido, determinismo y preservación de hechos.

### 2. Tener 34 disponibles no produce por sí solo una variedad de 34

Los 34 estuvieron presentes en todas las decisiones, pero solo cinco ganaron alguna selección.
Esto confirma la intuición del producto: catálogo completo es condición necesaria, no
suficiente. El ranking actual favorece de forma estable unos pocos tipos y no incorpora
necesidad de novedad, continuidad de mecánica, complementariedad entre nodos ni historial de
componentes ya vistos.

### 3. El apoyo tiene poca resolución

Una banda novata ya activa ejemplo resuelto y pistas. Un error posterior no puede aumentar la
ayuda dentro de esa banda. Hace falta expresar escalones de intervención o cambiar el tipo de
ayuda, no solo un booleano.

## Decisión provisional

Mantener el universo 34/34, la estabilidad de hechos y las reglas de caché. La siguiente ronda
debe probar, todavía fuera de producción:

1. validar con modelos reales que el bucket inferido como preferencia secundaria produce una
   adaptación útil, no solo una diferencia estructural;
2. añadir memoria de mecánicas ya utilizadas y una bonificación limitada por novedad útil;
3. modelar recuperación por escalones: pista conceptual, ejemplo parcial, cambio de
   representación y práctica más simple;
4. repetir las trayectorias con varias semillas y modelos pequeños reales, evaluando también
   grounding, calidad pedagógica, tiempo, tokens y recuperación ante una salida inválida;
5. ejecutar una trayectoria desde la interfaz y los endpoints reales para validar pinning,
   SSE, persistencia de eventos y regeneración, ya como prueba de integración separada.

Esta ronda no elige todavía una política final. Fija una línea base auditable y localiza dos
problemas concretos que una comparación solo de pantallas iniciales no habría mostrado.
