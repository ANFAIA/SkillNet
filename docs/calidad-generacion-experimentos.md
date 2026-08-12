# Calidad de generación: bucle experimental

> Los experimentos posteriores centrados en perfiles, preferencias, misiones cognitivas y
> componentes ricos continúan en
> [`personalization-experiments.md`](personalization-experiments.md).

Fecha: 2026-08-11. Rama `feat/notebook-media`. Pila viva: multi-agente
(`MULTI_AGENT_RENDER=true`, `SEMANTIC_ROUTER=true`) sobre `gpt-4o-mini`.

Queja de partida del propietario: los cursos generados se sienten **planos — sin variedad,
sin personalización**. Este documento mide el estado, prueba variaciones acotadas, se queda
con lo que funciona y revierte lo que no, y arregla los defectos que aparecen por el camino.

Método: `scripts/quality_bench.py` corre el pipeline real sobre 10 encargos fijos y reporta
acierto-a-la-primera / reparado / fallback / error, p50/p95, tokens y cobertura del catálogo
de bloques. Para juzgar ganchos y relleno (que el banco no puntúa) se generan nodos reales
contra el proveedor del `.env` y se leen las salidas.

---

## Baseline (2026-08-11)

**Banco offline** (`--offline`, sin clave, fixtures guionizados): 6/10 a la primera, 4
reparados, 0 fallback. Sirve solo para comprobar que el arnés funciona; la variedad offline
es la de los fixtures, no la del modelo.

**Banco en vivo** (`gpt-4o-mini`, 10 encargos, `--repeat 1`):

| Métrica | Baseline |
|---|---|
| Acierto a la primera | **10/10 (100 %)** |
| Reparados / fallback / error | 0 / 0 / 0 |
| p50 / p95 latencia | 6.81 s / 12.99 s |
| Cobertura del catálogo | **8 de 13 tipos (62 %)** |
| Tipos distintos por pantalla (media) | **5.00** |
| Bloques presentes | Stack, TextContent, Callout, StepSequence, Table, QuizItem, BeforeAfter, DragOrder |
| Nunca usados | Card, CodeBlock, Chart, AudioExplanation, PronunciationExercise |

Lectura: el trabajo previo de **variedad de evaluación**
(`docs/variedad-evaluacion-diagnostico.md`, `assessment.py`) ya subió mucho la variedad —
`DragOrder`, `BeforeAfter`, `true_false` y `fill_blank` aparecen de forma estable, no solo
`QuizItem test`. La "planitud" que queda es sobre todo de **contenido** (ganchos y relleno) y
de dos **defectos estructurales** que se ven al inspeccionar el contenido real (abajo).

**Muestra de contenido real** (renders persistidos, curso "Servicio de sala"): tablas y
comparativas bien fundadas en la fuente; leads variados pero con ~la mitad flojos
(consecuencia abstracta o pregunta retórica reciclada). Dos defectos estructurales visibles
en `node_renders` — ver bugs 1 y 2.

Notas de medición honestas:
- La contabilidad de tokens de salida marca ~35/render, imposible para un render completo
  (el content writer solo ya presupuesta 1600). En el camino multi-agente **el render no
  agrega los tokens de las 3–4 llamadas**; el coste real está infravalorado. Bug de
  medición documentado abajo (no arreglado: cambio profundo, riesgo alto de noche).
- La columna USD sale `n/d` porque 2 de 10 renders no devolvieron tokens y el banco no
  inventa coste. El coste por render medido antes (docs) es ~0.0008 USD.

---

## Experimento 1 — el blueprint no cuela contenido ni se trunca  ✅ SE QUEDA

**Hipótesis.** El nodo de alérgenos caía a `default_blueprint` (una `Table` genérica),
colapsando la variedad. Causa: el Blueprint Architect a veces mete el **contenido** dentro
del JSON (`text`, `before`, `after`), el JSON se pasa del tope de `max_tokens=512`, se corta
a media frase → `JSON inválido` → `default_blueprint`.

Evidencia baseline (log en vivo):
```
[3/10] alergenos-hosteleria ... blueprint: LLM response unparseable, using default.
raw={"blocks":[{"id":"lead",...,"before":"Un cliente pregunta por un alérgeno y el camarero no
```
(cortado a media frase → truncación por tope de tokens).

**Cambio.**
- `blueprint.py`: regla dura nueva — "SOLO ESTRUCTURA; PROHIBIDO campos `text`/`before`/
  `after`/`rows`/`options`; el JSON debe ser corto".
- `blueprint.py`: `max_tokens` 512 → **768** (red de seguridad ante la fuga residual).
- `PROMPT_VERSION` `runtime/20` → **`runtime/21`** (invalida la caché de renders).

**Después** (banco en vivo, alérgenos ×3 pases + tanda completa ×1): **0 caídas a
`default_blueprint`**; alérgenos cierra "OK a la primera [mixed/heavy]" sin el aviso de
`unparseable`. Cobertura estable en 62 %, tipos/pantalla 5.00 → **5.10**. Sin regresión de
acierto (10/10). Verdicto: **se queda** — quita un modo de fallo que reducía la variedad a
una tabla genérica, y estructuralmente elimina el riesgo de truncación.

---

## Experimento 2 — reglas de LEAD más estrictas  ❌ REVERTIDO

**Hipótesis.** Los leads flojos son el mayor contribuidor a la sensación de "plano".
Prohibir explícitamente los arranques genéricos ("¿Estás listo para...?"), la muletilla
final ("¿Sabes cómo...?") y la consecuencia abstracta ("puede afectar/arruinar/marcar la
diferencia"), y exigir un ancla concreta de la fuente, debería subir la calidad del gancho.

**Medición before/after** (mismos 3 nodos, `content_writer` real, `gpt-4o-mini`, ×2):

_Antes:_
- "¿Estás listo para abrir la sala y asegurar que todo esté en orden...?" (genérico)
- "El cliente espera su cuenta y tú debes asegurarte de que todo esté correcto..." (vago)
- **"Un cliente pide un plato con alérgeno, pero tú no lo has marcado. ¿Qué haces?"** (bueno)

_Después (con las reglas nuevas):_
- "Revisar las reservas y contar el fondo de caja son pasos clave antes de abrir la sala."
- "Comprobar la cuenta antes de cobrar es clave para evitar errores en el servicio."
- "El orden de la mesa y el marcado de alérgenos son clave para una comanda precisa."

**Verdicto: revertido (pérdida).** El cambio no eliminó el relleno: lo **cambió de cliché**
("puede afectar" → "es clave / es esencial / son pasos clave"), y de paso **suprimió los
buenos leads situacionales** que el prompt actual sí produce a veces (el del alérgeno). La
prohibición de la pregunta retórica solo se obedeció a medias. El prompt de lead actual es
mejor que mi edición; se restaura tal cual. Lección: sobre este prompt ya muy afinado,
añadir prohibiciones empuja al modelo a un relleno distinto, no a mejor gancho. Una mejora
real de leads probablemente necesita ejemplos por-dominio o un reescritor dedicado, no más
reglas negativas — se deja para un experimento con mejor instrumentación (un juez de calidad
de lead, hoy no existe).

---

## Bugs arreglados

### Bug 1 — el bloque de verificación no siempre cerraba la pantalla  ✅ ARREGLADO

**Síntoma** (render real de "Cobro y cierre de mesa"):
```
root = Stack([lead, callout, ejercicio, step_sequence], "md")
```
El `DragOrder` ("ejercicio", ordena los pasos) aparece **antes** del `StepSequence` que
**muestra el orden correcto**: el ejercicio no cierra la pantalla y su respuesta queda
servida justo debajo.

**Causa.** Tras `_apply_assessment` (que fuerza `DragOrder` cuando hay `StepSequence`), el id
del bloque de verificación del blueprint (p.ej. `drag_order`/`q1`) no coincide con el id que
emite el Interaction Designer, cuyo ejemplo de `DragOrder` está fijado a `ejercicio`. El
bloque llega como **huérfano** y el ensamblador cableaba los huérfanos **antes** del último
hijo, asumiendo que el último hijo era el ejercicio. Cuando el ejercicio ES el huérfano, lo
metía delante de un bloque de contenido.

**Arreglo** (`assembler.py`, Python puro, sin LLM): tras cablear huérfanos, se normaliza para
que **el bloque de verificación (`QuizItem`/`DragOrder`) sea siempre el último hijo de root**,
detectándolo por la línea escrita, no por el id del blueprint. Test de regresión nuevo
(`test_verification_orphan_lands_last_not_before_a_content_block`) que reproduce exactamente
el nodo "Cobro y cierre". Es un contrato que el propio blueprint ya declara ("la pantalla
acaba en QuizItem o DragOrder"); ahora se cumple pase lo que pase con los ids.

### Bug 2 (TableBlock, `key`) — ya estaba arreglado, no requería cambio

El encargo señalaba un warning de `key` de React en `TableBlock.tsx`. Al inspeccionarlo, los
tres `.map` (cabeceras, filas, celdas) **ya llevan `key`** (`key={idx}` / `key={rowIdx}` /
`key={cellIdx}`), añadidos en el commit `59bf25a` ("rediseño limpio de los bloques"). El
resto de bloques de `components/courses/blocks/*` también tienen `key`. No hay warning que
arreglar; no se toca el frontend.

---

## Bug encontrado, NO arreglado (documentado)

**Contabilidad de tokens en el camino multi-agente.** `node_renders.tokens_out` marca ~35
por render, imposible para un render con 3–4 llamadas (blueprint + content writer +
interaction designer). El render agrega mal (o solo cuenta una llamada). Impacto: los
paneles de coste **infravaloran** el gasto real del multi-agente. No se arregla esta noche:
toca el punto de persistencia de uso y la agregación entre agentes, con riesgo de tocar la
regla de `llm_usage_log`; mejor un cambio diurno con su test. Punto de entrada:
`src/agents/runtime/nodes.py` (persist) + el bucle de `genera_ui_multi`.

---

## Estado final

- Acierto a la primera **10/10**, 0 fallback (sin cambio: ya era perfecto).
- Cobertura del catálogo **62 %** estable; tipos por pantalla **5.00 → 5.10**.
- Variedad de evaluación real: `test`, `true_false`, `fill_blank`, `DragOrder` — cuatro
  interacciones, repartidas por nodo de forma determinista y estable.
- **Menos "plano" por dos vías estructurales**: (1) el blueprint ya no colapsa a una tabla
  genérica al truncarse; (2) el ejercicio siempre cierra la pantalla y ya no se autoespoilea.
- El relleno de leads sigue siendo la palanca abierta: el intento de reglas más duras fue una
  pérdida y se revirtió; necesita instrumentación (un juez de leads) antes de volver a tocarlo.

Artefactos del banco: `apps/skillnet-api/bench_out/{baseline,exp1,final}/`.
