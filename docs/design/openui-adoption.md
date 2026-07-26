# Adopción de OpenUI: decisión

> **Decisión:** nos quedamos en el **nivel (a)** — la gramática de OpenUI Lang como formato de salida
> del LLM, parseada en **Python** en el backend, IR `UISpec` validada al cliente. No entra ninguna
> dependencia npm. Lo que sí cambia hoy son **tres líneas de prompt** y **la forma de nombrar el
> dialecto**, porque hoy el código y el prompt dan a entender que implementamos el estándar, y no es
> verdad: implementamos un **subconjunto estricto** con validación adicional propia.
>
> Estado: decidido. Fecha: 2026-07-26. Rama `feat/dynamic-courses`, sin commitear.
> Sustituye, en lo referente a *runtime*, a la nota del vault `a2ui_protocol.md` (1 jul) y precisa la
> síntesis del 24 jul (`_sintesis_para_repo.md`, `docs/research/generative-ui/README.md`): la síntesis
> manda sobre la nota vieja, pero "adoptar OpenUI Lang" no significa "instalar el paquete".

Toda la evidencia de este documento se produjo ejecutando `@openuidev/lang-core@0.2.10` y
`@openuidev/react-lang@0.2.9` reales contra nuestras 16 fixtures. Los scripts viven en un sandbox
temporal (`.../scratchpad/openui-probe/`, 11 ficheros `.mjs`); ver el paso 4 del plan para cómo
conservarlos. **Cero cambios en el repo** durante esa investigación.

---

## 1. Qué es cierto y qué era falso

| Afirmación que circulaba | Veredicto | Evidencia |
|---|---|---|
| "La gramática que generamos coincide con OpenUI Lang" | **Cierto, y comprobado, no asumido.** El orden posicional del estándar sale de `Object.keys(def.properties)` del JSON Schema, o sea del orden de claves del `z.object()` — la misma convención que `ComponentSpec.props` en `src/render/kit.py`. Las 9 firmas del kit de §5.3 salen **idénticas prop a prop y posición a posición**, mismos literales de enum. | `kit.mjs` |
| "Su parser aceptaría nuestras fixtures" | **Cierto: 10 de 10 válidas, cero errores.** `meta.errors=[]`, `incomplete=false`, `unresolved=[]`, `orphaned=[]` en las diez. Incluso el fence ```` ```openui ```` no le molesta. | `compat.mjs` |
| "Su parser es el estándar, será más completo que el nuestro" | **FALSO. Nuestro parser Python es estrictamente más estricto, y eso es la ventaja.** El parser real acepta **3 de nuestras 6 malformadas en silencio**, una de ellas **perdiendo una línea entera sin avisar** (`malformed_missing_assign` descarta `Stack([intro],"md")`, `statementCount=1`, y la raíz pasa a ser otro nodo). No comprueba tipos, ni enums (`gap="enorme"`, `item_type="no_existe"` pasan), ni ids duplicados, ni HTML inyectado (`<script>alert(1)</script>` pasa), ni ninguna de las 7 reglas de contrato de §5.2, ni el máximo de bloques de la regla 4. La razón es estructural, no un bug: `compileSchema()` sólo guarda `{name, required, defaultValue}` — **el parser real no conoce los tipos ni los enums**, por mucho Zod que se le ponga. Sus 5 códigos de error (`unknown-component`, `missing-required`, `null-required`, `excess-args`, `inline-reserved`) son un **subconjunto** de los nuestros. | `compat.mjs`, `detail.mjs`, `syntax.mjs` (bloque C) |
| "Nuestra gramática es OpenUI Lang" | **Medio falso, y hay que decirlo.** El dialecto real **no es línea a línea**: acepta sentencias partidas en varias líneas, saltos de línea literales dentro de un string, anidado **inline** sin id, booleanos, `null`, objetos `{k: v}`, aritmética, comentarios `//` y fences markdown. Para él `\n` es whitespace, no separador. Nuestra **regla de escape nº 3** ("cada salto de línea real cierra un bloque") es **nuestra**, no del estándar — y está bien que lo sea, es lo que hace `parse_partial` trivial. Pero el prompt no debe venderla como parte de OpenUI Lang. | `syntax.mjs` (bloque A) |
| "El AST del paquete convierte a nuestra `UISpec`" | **Cierto y sin pérdida en las 10 válidas: 10 idénticos, 0 difieren.** Mismos ids, tipos, props, children y el mismo `format` inferido por la misma heurística. Su `root` es un árbol con hijos incrustados y el nuestro una lista plana; el aplanado por `statementId` es total (30 líneas). Escapes y serialización también coinciden: `jsonToOpenUI()` produce **el mismo texto** que nuestro `serialize()` (salvo el `\n` final, que nosotros ponemos). | `to-uispec.mjs`, `diff-ir.mjs`, `esc.mjs` |
| "…sin pérdida en todos los casos" | **Falso: 4 casos de borde sí pierden.** (1) **Huérfanos**: `meta.orphaned` da sólo el *nombre*, el nodo no está en el árbol — reconstruir sus props es imposible, y nuestra `UISpec` sí lo conserva y lo cuenta para el máximo de 12. (2) **Nodos inline**: `statementId: null`, hay que sintetizar ids, así que la identidad de bloque no es estable entre un intento y su reparación — y es exactamente lo que `node_render_views` necesita para medir. (3) **DAG**: un nodo con dos padres aparece **dos veces** en el árbol con el mismo `statementId`. (4) **Ciclos**: el árbol se trunca en silencio, reportado como `unresolved` con `errors=[]`. | `lossy.mjs` |
| "OpenUI Lang no tiene data binding ni lifecycle: es one-shot, sólo render" (vault) | **OBSOLETO Y FALSO en 0.2.10.** El lenguaje tiene estado mutable (`$var = default` → `stateDeclarations`, `createStore()` con get/set/subscribe), expresiones que sobreviven al parseo (`BinOp`, `Ternary`, `Member`, `StateRef`, `RuntimeRef`; `hasDynamicProps: true`), 13 builtins (`Count`, `Sum`, `Round`, `Filter`, `Sort`…) más `@Each`, acciones (`Action([...])` → ActionPlan ejecutable con `Run`/`ToAssistant`/`OpenUrl`/`Set`/`Reset`) y **binding a dos bandas real**: `markReactive(schema)` hace que la prop se evalúe a `ReactiveAssign` y salga como `$binding<number>` en el prompt. Lo **único** que no tiene es lifecycle: no hay `onMount`, ni efectos, ni timers salvo `Query(refresh)`. | `reactive.mjs`, `binding.mjs`, `mutation.mjs` |
| "Su `library.prompt()` podría sustituir a nuestro `prompt_fragment()`" | **Falso.** Las 9 firmas son equivalentes, pero: no tiene sitio para las 7 reglas de contrato de §5.2 (sólo `additionalRules: string[]` de texto libre), no tiene las 3 reglas de escape, no tiene EBNF, el ~80 % está **cableado en inglés** (`generateSystemPrompt` no acepta idioma), y **enseña sintaxis que nuestro parser rechaza** (booleanos, `null`, objetos, anidado inline). Su regla 5 ("toda variable no referenciada se descarta en silencio") es cierta en su runtime y **falsa en el nuestro**: divergencia de semántica, no de redacción. | `prompt-real.txt`, `prompt-bindings.txt`, `prompt-python.txt` |
| "Nos falta un componente `Simulation`" | **Falso.** Una simulación con parámetros ajustables es un `Chart` con `values` expresados más `Slider`s bindados: demostrado ejecutándose (`$precio`/`$descuento`/`$unidades` → `[1200,960]` → `[3000,1500]` → `[1350,675]`, sin reparsear). El `ChartBlock` de SVG inline no se toca. §5.3 dejó `Simulation` fuera y sigue teniendo razón. | `reactive.mjs`, programa 2 |

**No verificado, y lo digo con esas palabras:** (1) **el render en React de verdad**. Por sus tipos,
`@openuidev/react-lang` cablea `Renderer`, `reactive()`, `useStateField()` y `useTriggerAction()`, pero
**no he montado un componente React ni pintado un píxel**: mi demostración de reactividad usa el
runtime framework-agnóstico de `lang-core` (`createStore` + `evaluateElementProps` + `evaluate`).
Lo probado es que el *lenguaje* y el *runtime* lo expresan y lo calculan. (2) **La frase del vault,
textualmente**: no tengo acceso al vault de Obsidian desde esta máquina y `grep -rniE 'data
binding|one-shot|lifecycle' docs/` no la encuentra en el repo; quien tenga el vault debe localizar la
nota exacta y corregirla citando este documento. (3) **La densidad de tokens**: §5.4 justifica el
dialecto por "≈50 % menos que JSON equivalente" y **no está medido** — ni contra el JSON de la
`UISpec`, ni entre prompts (el suyo son 3254–3330 caracteres y el nuestro 3722, pero caracteres no son
tokens). (4) `mergeStatements()`, `enrichErrors()`, `@Each`/`@Filter`/`@Sort`: leídos en los `.d.mts`,
**no ejecutados**.

---

## 2. Qué significaría "adoptar OpenUI", en tres niveles

### (a) Sólo la gramática, parseo en Python — **lo que ya hay**

`src/render/backends/openui.py` (568 líneas) parsea el dialecto, `src/render/spec.py` valida la IR con
Pydantic, React renderiza componentes propios desde JSON.

- **Coste marginal: 0.** Ya está escrito, con 981 líneas de test y 16 fixtures.
- **Riesgo: bajo y conocido.** El único riesgo real es de *expectativas*: el nombre "OpenUI Lang" en
  el prompt y en el docstring sugiere conformidad total, y el punto 1 demuestra que no la hay ni la
  queremos. Un modelo de 8B que haya visto OpenUI Lang en su entrenamiento **va a emitir** booleanos,
  `null`, objetos y anidado inline, porque el estándar los tiene — y hoy el prompt **no los prohíbe**:
  sólo la EBNF los omite, que no es lo mismo para un modelo pequeño.
- **Lo que no da:** reactividad. Nada de `$state`, ternarios ni `Action`.

### (b) `@openuidev/lang-core` en el backend o en un paso de build, manteniendo la IR

Dos sub-variantes, y ninguna sobrevive al análisis como código de producción:

- **b1 — su parser delante o en lugar del nuestro.** Ganancia de validación: **cero** (sus 5 códigos
  son un subconjunto de los nuestros) y pérdida real: las 7 reglas de §5.2, los tipos, los enums, y
  3 de las 6 malformadas pasarían, una descartando una línea entera. Coste: Node en el runtime del
  backend Python o un subproceso, más `@openuidev/lang-core` + `zod` (**7,2 MB en `node_modules`, de
  los cuales 5,9 MB son zod**). **Rechazado.**
- **b2 — su `library.prompt()` como generador del prompt en un paso de build.** Perdería §5.2, las
  reglas de escape y el idioma, y enseñaría sintaxis que rechazamos. **Rechazado.**
- **b3 — el paquete sólo como *arnés de compatibilidad*, fuera del build de producción.** Un script
  que comprueba que nuestras fixtures válidas siguen siendo aceptadas por el parser real. Esto sí
  tiene valor (es la única prueba de que "adoptamos OpenUI Lang" no es marketing), y **no es una
  dependencia**: el repo no tiene `package.json` en la raíz ni `pnpm-workspace.yaml`, así que un
  directorio `tools/openui-compat/` con su propio `package.json` no lo instala `pnpm install` en
  `apps/skillnet-web` ni lo copia ningún Dockerfile. **Aceptado como opcional**, paso 4.

### (c) Adopción completa: `@openuidev/react-lang` y `<Renderer>` en el navegador

- **Coste:** `@openuidev/react-lang@0.2.9` + `@openuidev/lang-core@0.2.10` + peer `zod` (7,2 MB), más
  reescribir los 10 componentes de bloque como renderers de su registro, más mover el parseo al
  cliente, más `parse_partial` en streaming en el navegador.
- **Riesgo, y es el que decide:** **cambia la postura de seguridad**. Hoy el navegador recibe
  **JSON validado por Pydantic** y nunca markup ni un DSL que tenga que interpretar; el nivel (c)
  mueve el parseo de salida del LLM al cliente. Con él, la única validación en el camino es la del
  parser real — el que acepta `<script>alert(1)</script>`, enums inventados y tipos incorrectos. No
  es que su parser sea inseguro: es que **no valida**, y nuestra defensa es la validación.
  Además, `0.2.x` publicado el 24 de julio de 2026: **su API romperá**, y el arnés ya encontró tres
  bugs de firma en un día (`createParser(library)` es un error de tipo silencioso que vacía el
  catálogo; los errores están en `meta.errors`; `defineComponent` exige `component`).
- **Lo que sí daría:** reactividad de verdad, gratis, sin escribir runtime.

---

## 3. Recomendación: **(a)**, con tres cambios de texto y una precisión de nombre

Nos quedamos en (a). Los tres argumentos de §5.4 siguen en pie y ahora están **medidos**, no
argumentados: (i) `AGENTS.md:96` prohíbe añadir dependencias sin comprobar que el stack existente
cubre la necesidad — y lo cubre, con un parser más estricto; (ii) las fixtures cubren el parser sin
navegador; (iii) el navegador recibe JSON validado. Añado un cuarto: la compatibilidad **ya está
demostrada** sin instalar nada, así que instalar el paquete no compraría compatibilidad, compraría
mantenimiento de una API `0.2.x`.

### Lo que se pierde con esta decisión, dicho sin adornos

1. **La reactividad, hoy.** Es la pérdida real y no es pequeña: el estándar **ya sabe expresar** un
   quiz que corrige al instante y una simulación con sliders, y nuestra gramática congelada no. Está
   demostrado ejecutándose (8 líneas, cuatro estados, sin tocar la red). Renunciamos a ello en este PR
   y lo cubrimos con `QuizItemBlock` autónomo en React (§5.3), que es lo que §5.3 ya decidió.
2. **Su bucle de reparación.** `mergeStatements(existing, patch, rootId)` con recolección de statements
   inalcanzables y `enrichErrors()` (que añade a cada error un `hint` con la firma correcta) son
   exactamente la forma del `UI_REPAIR_SYSTEM` de §5.4. **No los he ejecutado**, sólo leído los tipos;
   si el bucle de reparación falla en la práctica, ahí hay una idea a copiar en Python.
3. **`@Each`/`@Filter`/`@Sort`.** Permitirían un quiz de N ítems desde un array en vez de N statements,
   lo que aliviaría el máximo de 12 bloques de la regla 4. **No explorado.**

### Sobre la corrección inmediata del quiz: el precio, dicho claro

La corrección **100 % en cliente rompe la regla 5 de §5.2**. En la demostración, el veredicto se
escribe `$elegida == 1`: la respuesta correcta y la explicación viajan al cliente en texto plano, que
es exactamente lo que `ANSWER_KEY_KEYS` y "answer_key nunca serializado al cliente" prohíben.
Corrección instantánea sin servidor y secreto de la clave son **incompatibles por construcción** — no
es un defecto de OpenUI Lang, es aritmética.

La vía que **sí** respeta la regla está demostrada (`mutation.mjs`): `Button("Comprobar",
Action([@Run(corregir)]))` + `corregir = Mutation("grade_answer", {item_id:"q1", choice:$elegida})` +
`Callout(corregir.correct ? "success" : "warn", corregir.explanation)`. Los args evaluados son
`{"item_id":"q1","choice":1}` — **no contienen la respuesta correcta**. Con `createQueryManager`
apuntando literalmente a `POST /nodes/{id}/answer`: 1 viaje al servidor, la clave se queda en
`answer_key`, y el estado local (selección, "ya respondida", contador de aciertos) sigue siendo
instantáneo. Es la misma arquitectura que ya tenemos, sólo que expresada en el dialecto en vez de en
TSX. Por eso no urge.

---

## 4. Plan: qué se hace, qué toca, cómo se verifica sin claves ni base de datos

Los pasos 1–3 son **para este PR** y son cambios de texto. El 4 es opcional. El 5 no es este PR.

### Paso 1 — Dejar de dar a entender que implementamos el estándar (documentación, 0 riesgo)

Es la parte de "qué hay que renombrar o documentar". **No se renombra ningún identificador.** El id de
backend `openui`, `RENDER_BACKEND`, `_BACKENDS` y `OpenUiLangBackend` se quedan: `openui` entra en las
claves de caché y en `config.py` (fichero compartido), y renombrarlo invalidaría renders por cero
ganancia. Lo que cambia es la **prosa**:

- `src/render/backends/openui.py`, docstring de módulo: decir en la primera línea que es un
  **subconjunto estricto de OpenUI Lang parseado en Python**, no una implementación del estándar;
  que el estándar admite multilínea, anidado inline, booleanos, `null`, objetos, comentarios y
  aritmética y **nosotros no**; y que la **regla de escape nº 3 es nuestra**, no del estándar, con la
  razón (`parse_partial`).
- `GRAMMAR`: una línea de comentario encima diciendo que es la gramática **congelada nuestra**, un
  subconjunto verificado contra `@openuidev/lang-core@0.2.10`.
- `docs/design/v2-dynamic-courses.md` §5.4: sustituir la nota de §15.5 ("es irrelevante que el paquete
  npm exista o no") por un puntero a este documento — ya no es irrelevante, **existe, lo hemos
  ejecutado y sabemos exactamente en qué se parece y en qué no**.

Verificación: `uv run ruff check src tests` y `uv run pytest -m "not integration" -q` sin nuevos
fallos. Son docstrings; ningún test depende de su texto.

### Paso 2 — Los tres cambios en `_PREAMBLE` (`src/render/backends/openui.py`)

Cada uno respaldado por lo que hace el prompt real, y **los tres son gratis ahora y caros después**:
`src/llm/fixture_data/index.json` tiene hoy **3 claves** (2 `explain`, 1 `probe_generate`) y **ninguna
de `genera_ui`**, y las claves de fixture son el hash del texto exacto del prompt. Tocar `_PREAMBLE`
después de que alguien grabe fixtures de `genera_ui` obliga a regrabarlas.

1. **"Escribe `root = Stack(...)` en la primera línea."** Su prompt lo dice y nosotros no. Es lo que
   hace que el armazón aparezca antes en streaming, y encaja exactamente con las zonas de estabilidad
   espacial de §5.5 (`NodeView.tsx`). Aquí él es mejor que nosotros.
2. **Una verificación final de 2–3 líneas** (toda referencia definida, todo alcanzable desde la raíz,
   nada repetido). Su prompt tiene un `## Final Verification`; es barato y se copia.
3. **Prohibir explícitamente** booleanos, `null`, objetos `{}`, anidado inline y comentarios. Es el
   cambio más importante de los tres: un modelo que haya visto OpenUI Lang **los va a emitir** porque
   el estándar los tiene, y hoy sólo están *ausentes* de la EBNF, no *prohibidos* en imperativo.
   Prohibirlo en una frase cuesta ~20 tokens y ahorra un reintento.

Verificación, sin claves ni BD: `uv run pytest -m "not integration" -q -k "render or openui or
roundtrip or cache_key"` y luego la suite completa. Si algún test fija el texto del prompt (los hay en
`test_render_openui.py`), se actualiza la aserción **en el mismo cambio**, nunca aflojándola.

### Paso 3 — Anotar §5.3 con lo que ya no hay que discutir

En `docs/design/v2-dynamic-courses.md` §5.3, una línea: `Simulation` se queda fuera y ahora está
**demostrado** que no hace falta (es `Chart` con `values` expresados + `Slider`s; `ChartBlock` no se
toca). Y en §5.2, junto a la regla 5, la nota de que la corrección 100 % en cliente es incompatible
con ella por construcción, con el patrón `Mutation` + `@Run` como la vía que sí la respeta.
Verificación: es un `.md` (y además no versionado en esta rama); ninguna.

### Paso 4 — (Opcional) conservar el arnés de compatibilidad, sin dependencia

Los 11 `.mjs` viven en un sandbox temporal y **se van a perder**. Si se quieren conservar:
`tools/openui-compat/` con su propio `package.json`, un `README.md` de cuatro líneas y un
`compat.mjs` que lea `apps/skillnet-api/tests/fixtures/dsl/*.openui` y afirme que las válidas siguen
siendo aceptadas por el parser real. **No es una dependencia del producto**: no hay `package.json` ni
`pnpm-workspace.yaml` en la raíz del repo, `pnpm install` en `apps/skillnet-web` no lo ve y ningún
Dockerfile lo copia. **No entra en CI** — se ejecuta a mano cuando se toca el kit o la gramática, o
cuando salga una versión nueva del paquete. Verificación: `node tools/openui-compat/compat.mjs` en una
máquina con red; en esta, `pnpm exec tsc -b` y `pnpm test` de `apps/skillnet-web` deben quedar
idénticos, porque el directorio es invisible para ellos.

Si no se hace el paso 4, hay que aceptar el hueco explícitamente: **la compatibilidad quedará
afirmada en este documento y no re-verificable**.

### Paso 5 — No es este PR: la v2 del dialecto

Si se quiere quiz interactivo de verdad, el camino es **una v2 de nuestra gramática** con `$state`,
ternario y `Action` — parseada en Python, como ahora — **no** un segundo backend, **no** una
dependencia npm, **no** el `<Renderer>` de React. Toca `openui.py`, `spec.py`, `kit.py`, el prompt y
los componentes de bloque; es una versión del dialecto, no un parche, y este PR no la presupuesta.

---

## 5. Qué se decide más adelante, y con qué señal

| Decisión aplazada | Señal concreta que la dispara | Qué haríamos |
|---|---|---|
| Nivel (c): `<Renderer>` de React en el navegador | Un **segundo cliente** que no sea nuestro React (móvil nativo, embed de terceros, un canal de chat) que tenga que pintar la misma `UISpec`. Mientras el único consumidor sea `apps/skillnet-web`, mover el render al cliente sólo compra dependencias y pierde validación. | Reevaluar con la API ya estable (**≥ 1.0**), y sólo si se resuelve antes que la validación de §5.2 vive en algún sitio del camino |
| v2 del dialecto con `$state`/`Action` | **`node_render_views`** mostrando que los nodos con `QuizItem` tienen abandono o tiempo-hasta-primera-respuesta peores que el resto, o feedback explícito de "no sé si acerté". Es una decisión de producto con dato, no de arquitectura. | Paso 5 del plan, con `Mutation` + `@Run` (1 round-trip) para no romper la regla 5 |
| Copiar `mergeStatements`/`enrichErrors` a Python | La tasa de éxito del **primer reintento** de `UI_REPAIR_SYSTEM` medida en producción. Si el modelo no se recupera con el error en la mano, su `hint` con la firma correcta es lo primero a copiar. | Reimplementar en `openui.py`, no importar |
| Fijar o abandonar el "≈50 % menos que JSON" de §5.4 | Que alguien lo pida en una revisión, o que el coste de tokens de `genera_ui` aparezca en la factura. **Hoy es una afirmación sin medir.** | Medirlo con `tiktoken` sobre las 10 fixtures válidas contra su `UISpec` en JSON, y corregir el número en §5.4 o borrarlo |
| Explorar `@Each`/`@Filter`/`@Sort` | Que el máximo de 12 bloques de la regla 4 empiece a rechazar specs legítimos (un quiz de 6 ítems ya son 7 bloques). | Evaluar si la iteración sobre arrays entra en la v2 del dialecto |
| Corregir la nota del vault | Nadie con acceso al vault lo ha hecho todavía. | Localizar la nota que dice "no tiene data binding / one-shot / sólo render", marcarla obsoleta y apuntar aquí |

---

## Apéndice: lo que se rechazó, y por qué

- **Sustituir nuestro parser por `createParser`.** Acepta 3 de 6 malformadas en silencio (una con
  pérdida de datos) y no comprueba tipos, enums ni las 7 reglas de §5.2. Sería cambiar el contrato
  por una dependencia npm.
- **Ponerlo delante como pre-validador.** Ganancia de validación: cero. Coste: `@openuidev/lang-core`
  + `zod` (7,2 MB), contra `AGENTS.md:96`.
- **Sustituir `prompt_fragment()` por `library.prompt()`.** Perdería §5.2, las reglas de escape y el
  idioma, y enseñaría sintaxis que rechazamos.
- **Añadir un componente `Simulation`.** Es `Chart` + `Slider`s + expresiones. §5.3 sigue teniendo
  razón.
- **Corrección 100 % en cliente en este PR.** Funciona; exige serializar la respuesta correcta al
  cliente y rompe la regla 5.
- **Cambiar la gramática congelada en este PR.** Es la vía correcta cuando toque el quiz interactivo,
  pero es una v2, no un parche.
