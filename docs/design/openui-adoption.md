# Adopción de OpenUI: decisión

> **DECISIÓN VIGENTE (2026-07-26, tarde): adopción completa — nivel (c), sin reactividad.**
>
> Entran las dependencias reales `@openuidev/react-lang@0.2.9` y `@openuidev/lang-core@0.2.10`
> (+ `zod@4.4.3`, versiones **exactas**, sin `^`). El navegador recibe **dialecto** y lo pinta con
> `<Renderer>` sobre los componentes que registramos nosotros; el **prompt lo genera su
> `library.prompt()`** desde el catálogo del frontend, en un **paso de build**, y Python lo lee como
> dato. Dejamos de mantener el generador de prompt propio.
>
> **Motivo, en las palabras del dueño del producto:** *"quiero usar su dependencia y olvidarnos de
> rompernos la cabeza con inventar nosotros"*. Traducido a la decisión: **preferimos mantenimiento
> ajeno a mantenimiento propio.** El coste de la librería (una API `0.2.x` que romperá) se paga con
> dinero y con un test de deriva; el coste de la gramática, el prompt y el runtime propios se paga con
> nuestro tiempo, en cada cambio, para siempre.
>
> **La capa reactiva queda apagada y con puerta**: sin `toolProvider`, sin `onAction`, sin
> `onStateUpdate`, sin `tools` en el prompt, y ningún componente que llame a `useTriggerAction()`.
> Las condiciones para encenderla algún día están en §6, y no son negociables.
>
> Esto **anula la recomendación (a)** que este documento hacía por la mañana. La evidencia de §1 y §2
> sigue siendo válida y es la que hizo posible decidir; lo que cambia es la conclusión, y el §3 dice
> exactamente por qué. Sustituye, en lo referente a *runtime*, a la nota del vault `a2ui_protocol.md`
> (1 jul) y precisa la síntesis del 24 jul (`_sintesis_para_repo.md`,
> `docs/research/generative-ui/README.md`).
>
> Estado: decidido y **ejecutado** en la rama `feat/dynamic-courses`.

Toda la evidencia de este documento se produjo ejecutando `@openuidev/lang-core@0.2.10` y
`@openuidev/react-lang@0.2.9` reales contra nuestras 16 fixtures. Los scripts viven en un sandbox
temporal (`.../scratchpad/openui-probe/`, ~25 ficheros `.mjs` contando los de la revisión de
seguridad de la tarde: `sec-*.mjs` y `SEGURIDAD-MUTACIONES.md`). **Se van a perder** cuando se limpie
el sandbox; conservarlos en `tools/openui-compat/` con su propio `package.json` sigue siendo la forma
de que la compatibilidad y los 15 payloads sean re-verificables, y sigue sin hacerse.

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
| "Su `library.prompt()` podría sustituir a nuestro `prompt_fragment()`" | **Los hechos siguen en pie; el veredicto se revisó la misma tarde (§3): sí lo sustituye, pasándole nuestras reglas por `additionalRules`.** Lo que sigue siendo cierto: Las 9 firmas son equivalentes, pero: no tiene sitio para las 7 reglas de contrato de §5.2 (sólo `additionalRules: string[]` de texto libre), no tiene las 3 reglas de escape, no tiene EBNF, el ~80 % está **cableado en inglés** (`generateSystemPrompt` no acepta idioma), y **enseña sintaxis que nuestro parser rechaza** (booleanos, `null`, objetos, anidado inline). Su regla 5 ("toda variable no referenciada se descarta en silencio") es cierta en su runtime y **falsa en el nuestro**: divergencia de semántica, no de redacción. | `prompt-real.txt`, `prompt-bindings.txt`, `prompt-python.txt` |
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

### (a) Sólo la gramática, parseo en Python — **lo que había hasta el 2026-07-26**

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
- **b2 — su `library.prompt()` como generador del prompt en un paso de build.** **ADOPTADO** (§3 y
  §4). El diagnóstico era correcto y la conclusión no: §5.2 y las reglas de escape entran por
  `additionalRules`, la sintaxis que rechazamos se prohíbe en imperativo con una regla que anula la
  suya, y el idioma **sí** se pierde en parte y se acepta como coste.
- **b3 — el paquete sólo como *arnés de compatibilidad*, fuera del build de producción.** Un script
  que comprueba que nuestras fixtures válidas siguen siendo aceptadas por el parser real. Esto sí
  tiene valor (es la única prueba de que "adoptamos OpenUI Lang" no es marketing), y **no es una
  dependencia**: el repo no tiene `package.json` en la raíz ni `pnpm-workspace.yaml`, así que un
  directorio `tools/openui-compat/` con su propio `package.json` no lo instala `pnpm install` en
  `apps/skillnet-web` ni lo copia ningún Dockerfile. **Aceptado como opcional**, paso 4.

### (c) Adopción completa: `@openuidev/react-lang` y `<Renderer>` en el navegador — **ES LA DECISIÓN**

- **Coste:** `@openuidev/react-lang@0.2.9` + `@openuidev/lang-core@0.2.10` + peer `zod` (7,2 MB), más
  reescribir los 10 componentes de bloque como renderers de su registro, más mover el parseo al
  cliente, más `parse_partial` en streaming en el navegador.
- **Riesgo, y es el que había que resolver:** **cambia la postura de seguridad**. Antes el navegador
  recibía **JSON validado por Pydantic** y nunca un DSL que tuviera que interpretar. La objeción era
  "la única validación en el camino pasa a ser la de su parser, el que acepta
  `<script>alert(1)</script>`, enums inventados y tipos incorrectos". **Se resolvió, y así es como:**
  el parseo del cliente **no** sustituye a la validación — el servidor sigue parseando y validando con
  Pydantic antes de persistir, y el navegador recibe la **re-serialización canónica** de lo validado,
  nunca la salida del modelo (§4). Su parser en el cliente pinta; el nuestro decide.
  Además, `0.2.x` publicado el 24 de julio de 2026: **su API romperá**, y el arnés ya encontró tres
  bugs de firma en un día (`createParser(library)` es un error de tipo silencioso que vacía el
  catálogo; los errores están en `meta.errors`; `defineComponent` exige `component`).
- **Lo que sí daría:** reactividad de verdad, gratis, sin escribir runtime.

---

## 3. Decisión: **(c) sin reactividad**. Por qué, qué se gana y qué se pierde

La recomendación anterior de este documento era **(a)** y era defendible: el parser propio es
estrictamente más estricto (§1), la compatibilidad ya estaba demostrada sin instalar nada, y el
navegador recibía JSON validado. El dueño del producto decidió lo contrario, y el criterio que decide
no es técnico sino de **quién paga el mantenimiento**:

- Con (a) mantenemos nosotros, para siempre: la gramática congelada, el generador de prompt, la
  EBNF, el catálogo duplicado en Python y en TypeScript, y cualquier v2 del dialecto que el producto
  pida (`$state`, `Action`, iteración). Cada cambio del kit se paga dos veces.
- Con (c) mantiene Thesys el lenguaje, el parser, el streaming y el prompt; nosotros mantenemos
  **una lista de componentes** y **una puerta**. El precio es una dependencia `0.2.x` que romperá, y
  eso es exactamente lo que un test de deriva convierte en un fallo de CI en vez de en una sorpresa.

### Lo que se gana

1. **Un solo sitio donde se declara el catálogo.** `apps/skillnet-web/src/components/courses/kit/`
   (zod + `defineComponent`). `apps/skillnet-web/scripts/generate-openui-prompt.mjs` llama a
   `library.prompt()` y escribe dos artefactos versionados que Python lee como dato:
   `apps/skillnet-api/src/render/openui_prompt.txt` y `openui_catalog.json`. **Node no entra en el
   camino de una petición**: es un paso de build.
2. **El prompt lo escribe su librería.** Sus bloques de sintaxis, firmas, *hoisting/streaming* y
   *Final Verification* — incluida la regla "escribe `root = Stack(...)` en la primera línea", que
   nosotros no teníamos y que es la que hace aparecer el armazón antes en streaming. Nuestras 7 reglas
   de contrato, las 3 de escape y el idioma entran por `additionalRules`, así que **no se pierde nada
   de §5.2**.
3. **Streaming real en el navegador, gratis.** `<Renderer isStreaming>` reparsea cada chunk y revela
   de arriba abajo. No escribimos runtime.
4. **La reactividad queda a un interruptor de distancia**, con las condiciones de §6 escritas y
   medidas, en vez de a una v2 del dialecto propio.

### Lo que se pierde, dicho sin adornos

1. **El prompt deja de estar íntegramente en español.** `library.prompt()` cablea sus bloques en
   inglés y no acepta idioma: aporta 3254 de los 6420 caracteres del artefacto (~51 %), y esos 3254
   son suyos y en inglés. Antes eran 3722, todos nuestros y en español. Es la pérdida más visible y
   **no tiene arreglo salvo un PR upstream**.
2. **+2698 caracteres de prompt** por petición de generación, y con ellos tres bloques que enseñan
   cosas que nuestra puerta rechaza (ver los puntos 7 y 8). Cada uno necesita una regla nuestra que lo
   anule explícitamente — `SkillNet 4`, `SkillNet 12` y `SkillNet 13`, 1506 caracteres de
   contradicción deliberada. Feo, y medido: sin `SkillNet 4` un modelo pequeño emite booleanos, `null`
   y objetos porque el estándar los tiene.
3. **Una dependencia `0.2.x` en el camino crítico del render.** Ninguna de las propiedades de
   seguridad en las que nos apoyamos (`RESERVED_CALLS`, `open_url` delegado a `onAction`, ausencia de
   `fetch` en el bundle) es contrato público. Mitigación: versiones exactas, `PINNED_VERSIONS` en
   `tests/test_render_prompt_artifact.py`, y la obligación de re-ejecutar `sec-sinks.mjs`,
   `sec-runtime.mjs` y `sec-builtins.mjs` en cada subida.
4. **El navegador ya recibe un lenguaje que tiene que interpretar.** Era el argumento (iii) de §5.4 y
   ha dejado de ser cierto. Lo que lo sustituye no es una promesa, son cuatro controles apilados
   (§5), el primero de los cuales es que **el navegador nunca ve el texto crudo del modelo**.
5. **Dos catálogos que pueden divergir** — el de zod (frontend) y `src/render/kit.py` (validación).
   No se ha eliminado la duplicación; se ha vuelto **detectable**: el digest normalizado del catálogo
   se recalcula desde `kit.py` y se compara con el artefacto en cada `pytest`. Hoy coinciden byte a
   byte (`skillnet-ui/1+ecaa7d56dcff` sale igual desde el kit de zod del frontend y desde el
   bootstrap transcrito de §5.3, que es la comprobación cruzada más barata que había).
6. **Lo que ya se perdía con (a) y sigue perdido:** su bucle de reparación (`mergeStatements`,
   `enrichErrors`) no se usa — el reintento sigue siendo `UI_REPAIR_SYSTEM` en Python — y
   `@Each`/`@Filter`/`@Sort` siguen sin explorar, así que el máximo de 12 bloques sigue siendo un
   máximo de 12 *statements*.
7. **Su bloque `## Important Rules` le pide al modelo que se invente datos** — *"When asked about
   data, generate realistic/plausible data"* — y ofrece *"forms for input"*, una categoría de
   componente que el catálogo no tiene. En un generador de formación de **cumplimiento normativo** eso
   es lo contrario del producto: todo dato tiene que venir del documento del cliente (§5.1). Está
   cableado en el bundle (offset 23931) y `SystemPromptOptions` no tiene ningún flag para apagarlo.
   Anulado con `SkillNet 13`, que prohíbe explícitamente inventar cifras, plazos, importes,
   sanciones y referencias normativas, y ordena omitir el dato cuando la fuente no lo dé. Detectado en
   la revisión del 2026-07-26; **este coste se había aceptado sin verlo**, no estaba en esta lista.
8. **Su regla de sintaxis 6 enseña una firma FALSA del componente más usado** — *"Write
   `Stack([children], \"row\", \"l\")` NOT …"* — con tres argumentos y un `gap` de `"l"`, cuando el
   nuestro es `Stack(children, gap)` con `gap` en `sm|md|lg`. `Stack` es la raíz de **todos** los
   programas, así que es el patrón que un modelo pequeño copia primero, y copiarlo se rechaza de
   entrada: gasta el único reintento (`MAX_UI_RETRIES = 1`) y cae en `fallback_seed`. También está
   cableado (offset 9470) y tampoco es suprimible. Anulado con `SkillNet 12`, y con red debajo: los
   tests de `test_render_prompt_artifact.py` recorren **toda** llamada `Componente(...)` del prompt y
   comprueban aridad y valores de enum contra `UI_KIT`, con los dos ejemplos malos del proveedor
   fijados en `VENDOR_SYNTAX_EXAMPLES` para que un ejemplo malo *nuevo* falle en vez de pasar
   desapercibido.

### Lo que NO se adopta, y esto es la mitad de la decisión

**La capa reactiva.** No porque no se pueda acotar — se puede, el corte es duro y está medido en
`SEGURIDAD-MUTACIONES.md` — sino por dos razones concretas:

- **No hay perfil parcial en el prompt.** Pasar `tools` activa el bloque completo de expresiones
  (`$var`, ternario, `@Set`, `@Run`, builtins) y `{tools:[...], bindings:false}` **sigue** enseñando
  `$var`. Medido: 12601 caracteres con tools contra 3254 sin ellas. Enseñar la reactividad es todo o
  nada.
- **Cambia una propiedad estructural por un contrato.** Hoy "la gramática no puede expresar una
  mutación" es una propiedad de la gramática congelada. Con reactividad pasa a ser "el paquete se
  comporta así en 0.2.10", que hay que verificar en cada release.

Con el perfil apagado, **un PDF envenenado no puede provocar ni una petición de red**: no hay
`toolProvider` que la ejecute, no hay componente que dispare la acción, el backend no persiste el
programa del modelo, y el navegador nunca ve su texto crudo.

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

## 4. Qué se ha ejecutado (backend), y cómo se verifica sin claves ni base de datos

| Qué | Dónde | Nota |
|---|---|---|
| Paso de build del prompt | `apps/skillnet-web/scripts/generate-openui-prompt.mjs` | Lee el catálogo del kit del frontend, llama a `library.prompt({preamble, additionalRules, examples})` y escribe los artefactos. `--check` falla si están rancios (para CI). Resuelve `@openuidev/lang-core` **como lo resuelve `react-lang`**, así el build compila el catálogo con el mismo parser que usará el navegador. |
| Artefactos versionados | `apps/skillnet-api/src/render/openui_prompt.txt`, `openui_catalog.json` | El `.json` lleva el catálogo normalizado, `catalog_digest`, `catalog_version`, `prompt_sha256`, las versiones de los paquetes y de qué fichero se leyó el catálogo (`catalog_source`). |
| Lector en Python | `apps/skillnet-api/src/render/prompt.py` | `render_prompt()`, `catalog_version()`, `library_version()`, `artefact_drift()`. Sin Node en tiempo de petición. |
| Test de deriva | `apps/skillnet-api/tests/test_render_prompt_artifact.py` (57 tests) | Recalcula el digest normalizado del catálogo desde `src/render/kit.py` y lo compara con el artefacto; comprueba también que el prompt no enseña reactividad, que las versiones son las auditadas y —desde la revisión del 2026-07-26— que **toda** llamada `Componente(...)` del prompt cuadra en aridad y enums con `UI_KIT`. |
| Presupuesto de pintado | `apps/skillnet-api/src/render/spec.py` (`MAX_RENDERED_NODES = 64`) + `kit/assertStaticOnly.ts` (`too-many-elements`) | Recupera el tope que el renderizador propio llevaba como `MAX_RENDERED`. La regla 4 cuenta **componentes** y la lista es un DAG, así que 12 componentes expanden un árbol sin cota: medido con `lang-core` 0.2.10, 370 bytes → 29 526 elementos y 550 bytes → OOM del heap de V8 (no capturable: la pestaña muere). El tope del servidor es el que cuenta, porque el del cliente necesita un `ParseResult` que en ese caso ya no existe. |
| Puerta ligera y textual | `apps/skillnet-api/src/render/gate.py` | Topes de tamaño + rechazo de reactividad **sobre el esqueleto** (se vacían los literales de texto primero). `canonicalize()` es lo único que produce el texto que se sirve. |
| Tests de la puerta | `apps/skillnet-api/tests/test_render_gate.py` (66 tests) | 15 payloads reactivos rechazados, 6 contenidos legítimos aceptados (incluida la prosa que menciona `Query()` y `$300`). |
| Trazabilidad en BD | `node_renders.dialect`, `catalog_version`, `library_version` + `ck_node_renders_served_provenance` | `raw_dsl` **desaparece como nombre**: la tentación que documenta la revisión de seguridad era servirlo. Migración **0005 modificada en su sitio**, no una 0006. |
| Retirada | `prompt_fragment`, `GRAMMAR`, `ESCAPE_RULES`, `_PREAMBLE`, `_catalogue()`, `_contract()`, `_EXAMPLE` | Fuera de `src/render/backends/openui.py` y de `base.py`. El **parser se queda**: es la puerta estructural. |

`src/render/kit.py` **se conserva** y sigue teniendo trabajo real: es el catálogo con el que
`src/render/spec.py` valida tipos, enums y las 7 reglas — cosas que el parser de OpenUI no comprueba
(§1) — y es el lado Python del test de deriva.

Verificación ejecutada, sin Docker, sin Postgres y sin claves:
`uv run ruff check src tests` → los 5 errores preexistentes, ninguno nuevo.
`uv run pytest -m "not integration" -q` → **1 failed, 1736 passed** (el fallo es
`test_grade_open_answer_fallback`, preexistente en `main`).
Frontend: `pnpm exec tsc -b` → 0 · `pnpm test` → **272 passed** en 14 ficheros · `pnpm lint` → 0
errores, 7 warnings preexistentes.

### La regla arquitectónica que más importa

**El navegador sólo recibe texto re-serializado desde la `UISpec` ya validada. Nunca el texto del
modelo.** `<Renderer response>` acepta texto, y mandar el crudo saltaría las dos puertas de golpe.
Por eso `serialize()` ahora cubre **los diez** componentes (`Markdown` incluido: el `fallback_seed` lo
escribe el servidor y también necesita forma de dialecto) mientras `parse()` sigue rechazando
`Markdown`, porque el **modelo** no puede emitirlo. La asimetría no desapareció: cambió de sitio.

### Los cuatro controles que sustituyen a "el navegador recibe JSON validado"

Apilados de fuera hacia dentro, todos medidos en `SEGURIDAD-MUTACIONES.md`:

1. **El navegador nunca ve el texto del modelo** — sólo la re-serialización canónica. Una `UISpec` no
   puede representar un AST reactivo, así que la propiedad es estructural.
2. **`toolProvider` ausente** en el `<Renderer>` → `createQueryManager(null)` y las guardas de
   `lang-core` cortan queries **y** mutaciones a cero. Es el corte duro.
3. **`onAction` y `onStateUpdate` ausentes** → `@OpenUrl` y `@ToAssistant` son no-ops (el runtime no
   navega, sólo reenvía a la prop) y `@Set` no se persiste. Refuerzo: ningún componente registrado
   llama a `useTriggerAction()`, así que un `ActionPlan` no es ni alcanzable.

Los controles 2 y 3 son **ausencias de props**, la clase de corrección que una suite no nota: hasta la
revisión del 2026-07-26 sólo los protegía un comentario. Desde entonces los guarda
`apps/skillnet-web/src/components/courses/UiSpecRenderer.runtime.test.tsx`, que mockea `<Renderer>`,
captura sus props y exige que `toolProvider`, `onAction` y `onStateUpdate` **no estén como clave**
(así `toolProvider={undefined}` también falla), que `<Renderer>` se monte desde un único módulo, y que
ningún fichero importe `useTriggerAction`, `reactive`, `markReactive`, `createQueryManager`,
`createStore` ni `useStateField` de `@openuidev`.
4. **La puerta, en los dos lados** — `gate.py` + el parser Python antes de persistir;
   `assertStaticOnly(parseResult)` en `onParseResult` en el cliente. Prohibido el grep de palabras
   clave sobre el texto crudo como rechazo duro: rechaza lecciones legítimas.

Los cuatro son sobre **reactividad**, y por eso ninguno vio el agotamiento de recursos: un árbol de
29 526 elementos sin una sola `Query` pasa los cuatro. Ese hueco lo cierra `MAX_RENDERED_NODES` (§4),
y la lección general es que la puerta del cliente no puede ser la única para nada que mate al parser:
un OOM del heap de V8 ocurre **dentro** de `parseBothWays`, antes de que exista un `ParseResult` que
inspeccionar, y el `try/catch` de `gateProgram` no lo captura.

Y el quinto, el más barato: **el prompt**. Sin `tools` y sin `markReactive`, `library.prompt()` no
menciona la sintaxis reactiva. Es mitigación en profundidad, no una barrera: si el modelo la emite de
memoria, quien la rechaza es la puerta.

## 5. Qué se decide más adelante, y con qué señal

| Decisión aplazada | Señal concreta que la dispara | Qué haríamos |
|---|---|---|
| ~~Nivel (c)~~ | **Decidido y ejecutado el 2026-07-26.** Ya no es una decisión aplazada. | — |
| Encender la reactividad (`Mutation` para corregir sin filtrar la `answer_key`) | **`node_render_views`** mostrando que los nodos con `QuizItem` tienen abandono o tiempo-hasta-primera-respuesta peores que el resto, o feedback explícito de "no sé si acerté". Decisión de producto con dato. | Las condiciones no negociables están en §6. Nunca una v2 del dialecto propio: ese camino ya no existe |
| Copiar `mergeStatements`/`enrichErrors` a Python | La tasa de éxito del **primer reintento** de `UI_REPAIR_SYSTEM` medida en producción. Si el modelo no se recupera con el error en la mano, su `hint` con la firma correcta es lo primero a copiar. | Reimplementar en `openui.py`, no importar |
| Fijar o abandonar el "≈50 % menos que JSON" de §5.4 | Que alguien lo pida en una revisión, o que el coste de tokens de `genera_ui` aparezca en la factura. **Hoy es una afirmación sin medir**, y ahora hay además +1660 caracteres fijos de prompt que sí están medidos. | Medirlo con `tiktoken` sobre las 10 fixtures válidas contra su `UISpec` en JSON, y corregir el número en §5.4 o borrarlo |
| Devolver el prompt al español | Un PR upstream que acepte idioma en `generateSystemPrompt`, o que el modelo pequeño empiece a contestar en inglés. | Medir la tasa de respuesta en inglés antes de escribir código |
| Explorar `@Each`/`@Filter`/`@Sort` | Que el máximo de 12 bloques de la regla 4 empiece a rechazar specs legítimos (un quiz de 6 ítems ya son 7 bloques). | Evaluar si la iteración sobre arrays entra en la v2 del dialecto |
| Corregir la nota del vault | Nadie con acceso al vault lo ha hecho todavía. | Localizar la nota que dice "no tiene data binding / one-shot / sólo render", marcarla obsoleta y apuntar aquí |

---

## 6. Si algún día se enciende la reactividad: condiciones no negociables

De `SEGURIDAD-MUTACIONES.md`, y ninguna es opcional:

- `toolProvider` con **forma MCP** (`{ callTool({name, arguments}) }`) y un `Set` de nombres
  permitidos. **Nunca un mapa de funciones**: `map[toolName]` es acceso a propiedad y
  `Mutation("constructor")` devuelve `status:"success"` con `errores=[]`, lo que rompe el *halt on
  failure* de las cadenas `@Run`. Medido.
- **Cero `Query` permitidas, sólo `Mutation`.** Las queries se auto-disparan en un `useEffect` en
  cuanto `isStreaming` pasa a `false`, **sin ningún clic**, y aceptan `refreshInterval` sin tope
  (4 llamadas en 3,3 s con `refreshInterval=1`, medido). El razonamiento "hace falta que el empleado
  pulse algo" vale para `Mutation` y **no** para `Query`.
- La allowlist va **dentro de `callTool`**, no en un grep del texto: el nombre del tool puede ser una
  expresión calculada (`Mutation($t + "_all_users", ...)` sale como `BinOp`/`StateRef`).
- `onAction`, si se cablea, **filtra por tipo** y descarta `open_url` y `continue_conversation`. El
  parser acepta `javascript:` en `@OpenUrl` sin quejarse.
- Autorización **siempre en el servidor**: `grade_answer` comprueba que el `node_id` pertenece a un
  curso al que el usuario tiene acceso, y es idempotente. La allowlist del cliente es reducción de
  superficie, no autorización.
- `RENDER_ALLOW_REACTIVE` (`src/config.py`) es el interruptor del lado servidor, y hoy está en
  `False`. Encenderlo relaja **sólo** la comprobación textual: el parser Python sigue rechazando,
  porque su gramática no puede representar una mutación. Para encenderla de verdad hay que cambiar la
  gramática, y eso es un PR con esta lista delante.

---

## Apéndice: lo que se rechazó, y por qué

- **Sustituir nuestro parser por `createParser` en el backend.** Sigue rechazado, y ahora es la
  decisión que sostiene toda la postura de seguridad: acepta 3 de 6 malformadas en silencio (una con
  pérdida de datos), no comprueba tipos, enums ni las 7 reglas de §5.2, y deja pasar
  `Mutation("delete_all_users", {...})` con `meta.errors=[]`. Adoptar la dependencia no era adoptar
  su validación.
- **Servir `raw_dsl` al navegador.** Es el riesgo dominante de esta migración, no el paquete. La
  columna ya no existe con ese nombre.
- ~~**Sustituir `prompt_fragment()` por `library.prompt()`.**~~ **Aceptado el 2026-07-26.** El motivo
  del rechazo (perdería §5.2, las 3 reglas de escape y el idioma) se resolvió metiéndolas por
  `additionalRules`; lo que no se resolvió es el idioma de **sus** bloques, y se acepta como coste
  (§3).
- **Añadir un componente `Simulation`.** Es `Chart` + `Slider`s + expresiones. §5.3 sigue teniendo
  razón.
- **Corrección 100 % en cliente en este PR.** Funciona; exige serializar la respuesta correcta al
  cliente y rompe la regla 5.
- **Cambiar la gramática congelada en este PR.** Es la vía correcta cuando toque el quiz interactivo,
  pero es una v2, no un parche.
