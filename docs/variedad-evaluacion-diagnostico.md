# Diagnóstico: por qué todos los nodos evalúan con el mismo QuizItem "test"

Fecha: 2026-08-11. Rama `feat/notebook-media`.

## Síntoma (palabras del propietario)

Cada curso, cada vez que se hace, renderiza **el mismo único componente de "test"
(QuizItem)**. No hay variedad de ejercicios ni de interacción.

## Evidencia ANTES del arreglo

La pila viva corre con `MULTI_AGENT_RENDER=true` y `SEMANTIC_ROUTER=true` sobre
`gpt-4o-mini` (medido en el contenedor `repo-notebook-media-api-1`), así que el camino
activo es el multi-agente (`genera_ui_multi`), **no** el monolítico.

Distribución de los `node_renders` ya persistidos:

```
item_type de cada QuizItem:   test | 5      (5 de 5, el 100 %)
bloques usados:               TextContent, QuizItem, Stack, Table, Callout, BeforeAfter
DragOrder:                    0
true_false / fill_blank / practical_case / dialogue:  0
```

Generación fresca de 6 nodos variados (preview, `force`) el 2026-08-11:

| nodo | ui_format | criticidad | bloques | item_type |
|------|-----------|-----------|---------|-----------|
| Los catorce alérgenos | explanation | critical | Stack,TextContent,Table,Callout,QuizItem | **test** |
| Responder al cliente | exercise | critical | Stack,TextContent,BeforeAfter,Callout,QuizItem | **test** |
| Apertura del turno | explanation | recommended | Stack,TextContent,Table,QuizItem | **test** |
| Tomar la comanda en el TPV | exercise | critical | Stack,TextContent,BeforeAfter,Callout,QuizItem | **test** |
| Coordinación con cocina | chart | recommended | Stack,TextContent,BeforeAfter,QuizItem | **test** |
| Gestión de una queja | mixed | recommended | Stack,TextContent,BeforeAfter,Callout,QuizItem | **test** |

6 de 6 terminan en `QuizItem` de tipo `test`. **Cero** `DragOrder`, incluso en el nodo
claramente procedimental "Tomar la comanda en el TPV". El *contenido* sí varía algo
(Table, Callout, BeforeAfter); la **evaluación** es monótona por completo.

## El kit ya tiene la variedad; no se está usando

El kit (`src/render/kit.py` ↔ `kit/library.tsx` + `kit/schemas.ts`) ya soporta, de punta
a punta y con corrección de notas en el backend:

- **QuizItem** con seis `item_type` (`ExerciseType`): `test`, `true_false`, `fill_blank`,
  `order_steps`, `practical_case`, `dialogue`. El front los pinta distinto:
  `test`/`true_false` → opción única (radio); `fill_blank`/`practical_case`/`dialogue`
  → área de texto (`QuizItemBlock.tsx`, `SINGLE_CHOICE_TYPES`).
- **DragOrder** (arrastrar para ordenar), interacción completamente distinta.
- La corrección (`src/services/node_grading.py`) es determinista y 0.0/1.0 para
  `test`, `true_false`, `fill_blank`, `order_steps`; `practical_case`/`dialogue` van por
  LLM (`grade_open_answer`) solo si hay `LLM_EVAL_MODEL` (por defecto `None`).

Es decir: **`test`, `true_false`, `fill_blank` y `DragOrder` funcionan de extremo a
extremo sin depender de ningún LLM de evaluación.** Son cuatro interacciones distintas
ya disponibles que nunca se emiten.

## Causa raíz (camino multi-agente, el vivo)

1. **Blueprint** (`src/agents/runtime/agents/blueprint.py`). El menú del slot VERIFICAR
   solo dice "QuizItem o DragOrder". El `item_type` no se explica nunca (no hay menú de
   los seis tipos ni un solo ejemplo de algo que no sea `test`), así que el LLM emite
   `QuizItem` y deja `item_type` en su valor por defecto. La única regla que elegiría
   `DragOrder` es "si el concepto es un procedimiento (StepSequence)", pero el blueprint
   casi nunca elige `StepSequence` (prefiere `Table`/`BeforeAfter`), luego `DragOrder`
   no sale jamás.
2. **`default_blueprint` y `_ensure_verification`** fijan `item_type="test"` a pelo.
   El fallback y la red de seguridad refuerzan la monotonía.
3. **Interaction Designer** (`interaction_designer.py`). Su único ejemplo resuelto es
   `QuizItem("q1", "test", "apply", ...)`. Reproduce fielmente el `item_type` que le pasa
   el blueprint (siempre `test`) y no tiene ninguna guía para escribir `true_false`,
   `fill_blank` ni `practical_case`.

Nada en el pipeline convierte una señal del *contenido* del nodo en una elección de
formato de evaluación. Y como para un aprendiz nuevo `target_bloom` es siempre
`understand` (`mastery 0 < 0.5 → "shu"`), tampoco el nivel de Bloom aporta variación
entre nodos.

## Causa raíz (camino monolítico, `MULTI_AGENT_RENDER=false`)

El mismo sesgo vive en `src/llm/prompts/runtime.py` (`_BLOCK_CHOICE`): "En los demás
casos -> QuizItem", y **los dos ejemplos resueltos (B y C) usan `QuizItem(..., "test", ...)`**.
La sección "cómo hacer buenas preguntas" solo describe el tipo `test` ("SIEMPRE 4
opciones"). El modelo nunca ve usado otro tipo, así que nunca lo emite.

## Defecto latente encontrado de paso

`blueprint.py::default_blueprint` y los ejemplos de `content_writer.py` mencionan
`StepByStepReveal`, que **no existe en el kit** (el kit tiene `StepSequence`). Si el
blueprint llegara a proponerlo, el validador lo rechazaría (`unknown-component`) y el nodo
caería al fallback — colapsando aún más la variedad. Se corrige el `default_blueprint` de
paso; los ejemplos de `content_writer` quedan anotados (son de contenido, no de evaluación).

## Arreglo aplicado (ver sección "Después")

Palanca 1 (la de menor riesgo y más impacto): **usar la variedad que ya existe.** Se
añade un planificador de evaluación determinista (`src/agents/runtime/assessment.py`) que,
igual que `shape.py`, lee propiedades del *nodo* (no del aprendiz) y le asigna un formato
de verificación estable:

- Si el material es un **procedimiento** → `DragOrder` (ordenar los pasos).
- En caso contrario, rota de forma determinista y estable por nodo entre
  `QuizItem test`, `true_false` y `fill_blank` (hash del `node_id`), de modo que los nodos
  hermanos de un curso no caen todos en `test`.

El plan se **impone** en el blueprint (post-proceso de `_ensure_verification`) para que no
dependa del capricho del LLM, y se **enseña** al Interaction Designer con ejemplos de cada
tipo. El camino monolítico recibe el mismo plan como pista y un menú de `item_type` con
ejemplos. Es estable por nodo (misma pantalla en cada visita → respeta la calibración
§6.4 y no ensucia el `cache_key` más allá del bump de `PROMPT_VERSION`).

Tipos nuevos de bloque: **ninguno.** El kit ya tenía la variedad; el problema era que el
generador no la elegía. Propuestas de bloques nuevos para el futuro, más abajo.

## Propuestas de bloques nuevos (futuro, NO implementadas)

Si se quiere ampliar más allá de lo que el kit ya cubre, encajarían con la arquitectura
actual (enum cerrado, props posicionales, sin HTML, lockstep back↔front + test de drift):

- **Cloze / rellenar huecos múltiple**: hoy `fill_blank` se pinta como un `textarea` de un
  solo hueco. Un bloque con varios huecos embebidos en la frase daría un ejercicio
  visualmente distinto (ya hay corrección `blanks[]` en el backend).
- **Categorizar / clasificar en cubos** (arrastrar ítems a categorías).
- **Emparejar pares** (matching).

Cada uno exige: `render/kit.py` + `kit/library.tsx` + `kit/schemas.ts` + `blocks/*.tsx`
+ regenerar el artefacto del prompt + actualizar los tests de drift + una rama de
corrección en `node_grading.py`. Es un cambio grande; se deja documentado en vez de
medio-hacerlo.

## Después del arreglo

Regenerados los 10 nodos de los dos cursos sembrados sobre la pila viva (multi-agente,
`gpt-4o-mini`), el 2026-08-11, con el planificador activo. Formato de verificación del
último render de cada nodo:

| curso | nodo | verificación |
|-------|------|--------------|
| Servicio | 1. Apertura del turno | test |
| Servicio | 2. Recibir y acomodar | test |
| Servicio | 3. Tomar la comanda en el TPV | test |
| Servicio | 4. Coordinación con cocina | **fill_blank** |
| Servicio | 5. Servicio en mesa | **true_false** |
| Servicio | 6. Cobro y cierre de mesa | **DragOrder** (ordena los pasos) |
| Servicio | 7. Gestión de una queja | **true_false** |
| Alérgenos | 1. Los catorce alérgenos | **true_false** |
| Alérgenos | 2. Responder al cliente | test |
| Alérgenos | 3. Contaminación cruzada | **true_false** |

Distribución global (antes → después):

```
ANTES:   test 100 %   (5/5, y 6/6 en la muestra fresca)   DragOrder 0
DESPUÉS: test 4 · true_false 4 · fill_blank 1 · DragOrder 1
```

De un único formato a cuatro interacciones distintas, repartidas de forma determinista y
estable por nodo (misma pantalla en cada visita). El nodo "Cobro y cierre", cuyo concepto
es una `StepSequence`, se cierra ordenando los pasos con `DragOrder`.

### Qué se cambió

- **`src/agents/runtime/assessment.py`** (nuevo): planificador determinista
  `plan_assessment(plan, ui_format, node_id)`. Procedimiento → `DragOrder`; en otro caso
  rota `test`/`true_false`/`fill_blank` por un hash del `node_id`.
- **`decide_formato`** calcula el plan y lo lleva en el estado (`assessment_*`).
- **Multi-agente** (camino vivo): `run_blueprint` recibe el plan, lo enseña en el prompt y
  lo **impone** con `_apply_assessment` (reescribe el bloque de cierre sin importar lo que
  decida el LLM). Además, si el blueprint eligió una `StepSequence`, el cierre pasa a
  `DragOrder`. El `interaction_designer` aprende a escribir cada `item_type` con un ejemplo
  resuelto por tipo. Corregido de paso `default_blueprint` (`StepByStepReveal`, que no
  existe en el kit, → `StepSequence`).
- **Monolítico** (`MULTI_AGENT_RENDER=false`): `build_ui_prompt` inyecta la línea "CÓMO
  VERIFICAR"; `_BLOCK_CHOICE` enseña los cuatro `item_type` con ejemplos D (true_false) y
  E (fill_blank). `PROMPT_VERSION` sube a `runtime/20` (invalida la caché de renders).
- **Bloques nuevos de kit: ninguno.** El kit ya tenía la variedad; el generador no la
  elegía. El lockstep back↔front y los tests de drift no se tocan.

### Qué pasó y qué falló en las comprobaciones

- Backend: `ruff check src` limpio, `import src.main` OK.
- `uv run pytest -m "not integration"`: **2765 pasan, 1 falla**
  (`test_the_packaged_fixtures_are_registered_under_the_canonical_keys`, el fallo
  preexistente y esperado: el `index.json` empaquetado quedó fijado a un prompt anterior;
  regenerarlo exige re-grabar salidas del modelo). Los tests de `test_runtime_graph` que
  reconstruyen el prompt canónico se actualizaron para incluir la línea "CÓMO VERIFICAR"
  (misma cuenta de fallos que en la base: cero regresiones).
  - Nota de entorno: `uv run pytest` a veces carga el `.env` de la raíz (que trae
    `MULTI_AGENT_RENDER=true`), y entonces los tests de `test_runtime_graph` —cuyos
    fixtures son del camino monolítico— fallan por fixtures ausentes. Es preexistente
    (la base lo reproduce igual). Con la config prevista
    (`MULTI_AGENT_RENDER=false`) queda el único fallo esperado.
- Frontend: sin cambios (el kit ya soportaba todos los `item_type` y `DragOrder`), así que
  no hubo nada que compilar.
