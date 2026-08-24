---
title: "Arquitectura de componentes por función"
order: 22
section: "core"
---

# Arquitectura de componentes por función

**Fecha:** 2026-08-09
**Estado:** propuesta. Nada aquí está implementado.
**Origen:** medición de los días 8 y 9 de agosto (`testing_cursos/INFORME.md`, `INFORME_GENERO.md`)
e investigación en `07_ANFAIA/investigacion/ui_innovadora/catalogo_y_abstraccion_componentes.md`.

---

## 1. El problema, con números

El kit tiene **22 componentes emitibles**. En 71 renders medidos aparecen **7**. Los otros 15,
nunca — ni una vez, en siete documentos de cuatro segmentos y tres géneros distintos.

Lo que se descartó por medición, no por opinión:

| Hipótesis | Veredicto |
|---|---|
| El catálogo es demasiado grande y el modelo se pierde | **Falsa.** OpenUI anuncia 53 firmas en 13 KB; A2UI, 18+14; Khan Perseus, 34 widgets. 22 en 8 KB no está cerca de ningún techo |
| El veto a `Tabs`/`Card`/`Accordion` los frenaba | **Falsa.** Se retiró el 2026-08-09 (`c02427a`) y volvieron a salir **cero** veces |
| El modelo no sabe usar bloques ricos | **Falsa.** Ante contenido de contraste emitió `Table(["Situacion","Resultado"], [...])` — un `BeforeAfter` escrito dentro de una `Table`. Entendió la semántica y no tuvo por dónde sacarla |
| El sistema ignora el género del documento | **Falsa.** Con material no procedimental, `StepSequence` cayó del 90% al 0% y `DragOrder` del 100% al 0% |

Lo que queda en pie, y es la causa:

**`shape.py` produce cuatro señales y todas nombran un componente concreto**: `enumeration`→`Table`,
`labelled_list`→`Table`, `numeric_series`→`Table`, `procedure`→`StepSequence`. Sobre material que no
es lista ni procedimiento, **el único bloque que alguien puede proponer es `Table`** — y en el test de
género salió en 18 de 18 nodos.

Fuera de esas cuatro señales el modelo no recibe **ninguna** señal discriminante. *The 99% Success
Paradox* (Meta, 2026-05) describe el régimen: con K·R̄/N por encima de 3-5 la selectividad colapsa y
el modelo **cae en sus priores** — concentración en los prototípicos y cola muerta permanente. Con 22
componentes mostrados y 3-5 plausibles por lección, λ≈4,0. Es exactamente lo medido.

**Conclusión operativa:** añadir capacidad sin añadir señal no hace nada. Está demostrado en este
repositorio, con un commit y una medición.

---

## 2. La causa estructural: el coste de añadir

Meter un componente nuevo hoy cuesta seis ediciones:

| Edición | Naturaleza |
|---|---|
| `kit.py` — validación | local, mecánica |
| Bloque React | local, mecánica |
| Registro en la librería del kit | local, mecánica |
| Regenerar `openui_prompt.txt` | local, automática |
| **`shape.py` — una señal que pueda nombrarlo** | **central** |
| **Prompt del blueprint — una regla que encamine hacia él** | **central** |

Las dos últimas se enredan más con cada componente. Cuatro señales para 22 componentes ya no dan.

De ahí la explicación de los 15 muertos: **nadie decidió que no. Nadie pagó la edición central.**
`BeforeAfter` no está apagado por diseño — llegar a él costaba tocar el detector y no se hizo.

Con el coste de añadir alto, el catálogo se congela solo. Ese es el problema que esta arquitectura
resuelve; la riqueza es la consecuencia, no el objetivo directo.

---

## 3. El movimiento central

Introducir una capa de **función de contenido** entre el análisis de la fuente y la elección de
componente.

```
HOY
  fuente ──> detectores (4) ──> ShapeSignal(block="Table") ──> hint ──> blueprint ──> componente
                                            ▲
                                  el nombre del bloque va cableado aquí

PROPUESTO
  fuente ──> detectores ──┐
                          ├──> ContentFunction ──> registro ──> productor funcional ──> componente
            clasificador ─┘                          ▲                    │
            (sólo si no                    cada componente          puede DECLINAR
             hay señal)                    declara sus funciones
```

Tres propiedades, y cada una responde a un hallazgo de la medición:

**El componente declara para qué sirve.** Sale de `shape.py` y entra en `ComponentSpec`. Añadir un
componente deja de tocar nada central: es registrar. *Responde al §2.*

**La decisión sube de nivel.** El router elige entre 5-8 funciones, no entre 22 componentes.
"¿Este contenido contrasta dos estados, enumera, describe un procedimiento o explora una variable?"
es una pregunta semántica sobre el texto — lo que un modelo de lenguaje hace bien. "¿`BeforeAfter` o
`Table` de dos columnas?" es una pregunta de UI sobre la que no tiene criterio, y hoy contesta
`Table` siempre. *Responde al §1.*

**El λ de cada decisión baja.** El agente de comparaciones enseña 4 componentes con 2 plausibles:
λ≈2, fuera del régimen de colapso. Sin recortar el catálogo total. *Responde al paper de Meta.*

---

## 4. Decisiones de diseño

### 4.1 El eje de partición es la función, no el dominio

Un agente de comparaciones sirve a restauración, retail, gestoría y clínica por igual. Partir por
dominio multiplica agentes que hacen lo mismo.

El dominio entra **después**, como etiqueta que filtra el catálogo dentro de cada agente funcional.
Así un componente de álgebra no compite nunca en un curso de cocina, y el catálogo total puede crecer
a 200 sin que ninguna decisión vea más de una docena.

### 4.2 Se conserva la asimetría de `shape.py`

El módulo lo dice literalmente:

> *"a missed hint costs nothing (the prompt falls back to what it says today), while a hint the
> material cannot support sends the model to invent rows."*

Esa asimetría es un invariante del sistema, no un detalle. Cada umbral de `shape.py` está calibrado
contra un fallo real documentado en sus comentarios. **El clasificador semántico nuevo hereda la
misma regla: ante la duda, no emite función.**

### 4.3 Dos velocidades de clasificación

Los detectores deterministas **se quedan donde aciertan**. Son rápidos, gratis y se escribieron
porque el modelo fallaba las enumeraciones.

El clasificador semántico entra **sólo cuando los detectores no producen ninguna señal** — que es
exactamente el material que hoy cae en `Table` por descarte, y donde están los 15 muertos.

Coste: una llamada corta y sólo en los nodos sin señal. No toca el camino que ya funciona.

### 4.4 El productor puede declinar

Un productor devuelve el componente **o** `Declined(motivo)`. El planificador baja por la lista
ordenada de candidatos de esa función.

Sin esto, ampliar el catálogo produce bloques forzados en vez de mejores lecciones — y con
componentes interactivos es peor que con texto: un `SliderExploration` necesita una **relación**
entre variable y efecto que el documento del cliente casi nunca enuncia. Si el productor no puede
negarse, la inventa. El bloque C ya midió un **32% de contenido inventado con fuente pobre,
incluidas cifras falsas**; con componentes interactivos eso deja de ser un dato erróneo y pasa a ser
un aprendiz jugando con un modelo falso.

**La vía de rechazo es lo que hace seguros los componentes ricos.** No es elegancia arquitectónica.

### 4.5 El descriptor lleva coste, no sólo propósito

`ComponentSpec` gana campos:

```python
@dataclass(frozen=True)
class ComponentSpec:
    name: str
    purpose: str                          # ya existe
    props: tuple[PropSpec, ...]           # ya existe
    is_container: bool = False            # ya existe
    llm_emittable: bool = True            # ya existe
    # nuevos
    functions: tuple[ContentFunction, ...] = ()   # para qué funciones compite
    when: str = ""                        # pista de uso, estilo OpenUI
    requires: tuple[Requirement, ...] = () # p.ej. IMAGE_URL, NUMERIC_RELATION
    cost: Cost = Cost.FREE                # FREE | LLM | SLOW | PAID
    domains: tuple[str, ...] = ()         # vacío = todos
```

`cost` es lo que permite que un despliegue self-hosted de una PYME apague los productores caros sin
que se rompa nada. `requires` es lo que evita proponer `HotspotImage` cuando no hay pipeline de
imágenes detrás.

---

## 5. Las funciones de contenido

Punto de partida, a validar con la medición de la fase 3:

| Función | Qué reconoce | Candidatos actuales |
|---|---|---|
| `ENUMERAR` | conjunto de elementos sin orden causal | `Table` (1-2 col), `Card` |
| `PROCEDIMENTAR` | pasos con orden | `StepSequence`, `StepByStepReveal`, `DiagramBuilder` |
| `CONTRASTAR` | dos estados, bien/mal, antes/después | `BeforeAfter`, `Table` (2 col), `Callout` |
| `VARIAR` | mismo proceso con variantes por caso | `Tabs`, `Accordion` |
| `CUANTIFICAR` | cifras comparables | `Chart`, `Table` |
| `EXPLORAR` | relación entre variable y efecto | `SliderExploration`, `ManipulableGraph` |
| `LOCALIZAR` | partes de un objeto o espacio | `HotspotImage` |
| `EVALUAR` | verificación de aprendizaje | `QuizItem`, `DragOrder` |

Las cuatro señales actuales mapean sin pérdida: `enumeration`/`labelled_list`→`ENUMERAR`,
`numeric_series`→`CUANTIFICAR`, `procedure`→`PROCEDIMENTAR`. **La migración empieza siendo
equivalente a lo que hay**, que es lo que la hace segura.

`CONTRASTAR`, `VARIAR`, `EXPLORAR` y `LOCALIZAR` son las cuatro que hoy no existen — y cubren
exactamente los bloques muertos.

---

## 6. Fases, cada una medible por separado

Se usa el arnés ya construido: `testing_cursos/driver.py`, `bloque_a.py`, `comparar_v14_v15.py`.
La baseline está en `datos/manifest_bloqueA_v14_baseline.json`.

### Fase 0 — Corregir la regla mal colocada *(1 línea)*

En `blueprint.py`, la única regla que menciona el caso bien/mal está escrita en la sección del slot
**VERIFICAR**, donde `BeforeAfter` es ilegal (ese slot sólo admite `QuizItem`/`DragOrder`, y quince
líneas más abajo: "NO HAY EXCEPCIONES"). La regla es inalcanzable por construcción. Moverla al slot
CONCEPTO.

**Medida:** ¿aparece `BeforeAfter` alguna vez? **Coste:** una línea y un bump de `PROMPT_VERSION`.

### Fase 1 — Descriptores *(sin tocar arquitectura)*

Reescribir los `purpose` de una línea de `kit.py` como pistas de uso reales, al estilo del prompt de
OpenUI (*"prefiérelo cuando las etiquetas son largas"*, *"úsalo cuando el contenido contrasta dos
estados"*).

Es la única palanca del informe con números: Trace-Free+ (Intuit, 2026-04) mide **−29,23% de
degradación y +60,89% de éxito por consulta** con 150+ herramientas, sólo cambiando descripciones.

**Medida:** distribución de bloques contra baseline. **Criterio de éxito:** al menos 3 de los 15
muertos aparecen. **Si no aparece ninguno**, la señal por descripción no basta en este modelo y la
fase 4 (clasificador) sube de prioridad.

### Fase 2 — El registro

`ComponentSpec` gana `functions`, `when`, `requires`, `cost`, `domains`. Se escribe
`registry.candidates_for(function, domain, budget)`.

`shape.py` deja de nombrar bloques: sus señales pasan a emitir `ContentFunction`. El mapeo
función→componentes vive en el registro.

**Medida:** la distribución no debe cambiar. Es un refactor de equivalencia; si cambia, algo se rompió.
**Y la métrica de verdad:** cuánto cuesta añadir el componente número 23 después de esto. Si sigue
exigiendo tocar `shape.py`, la fase falló.

### Fase 3 — Funciones nuevas por detector

Añadir detectores deterministas para `CONTRASTAR` y `VARIAR` donde el texto lo permita (marcadores
tipo "en cambio", "nunca … siempre", "según el tipo de"). Misma asimetría: ante la duda, no emitir.

**Medida:** ¿aparecen `BeforeAfter`, `Tabs`, `Card`?

### Fase 4 — Clasificador semántico para el resto

Sólo en nodos donde los detectores no producen señal. Una llamada corta que devuelve una función o
`ninguna`.

**Medida:** cobertura (qué % de nodos sin señal reciben una), precisión contra un banco de casos
etiquetados a mano, y el delta de latencia y coste. **Es un problema de clasificación sobre un
conjunto pequeño de etiquetas: se puede evaluar de verdad**, a diferencia de "genera buenas
lecciones".

### Fase 5 — Productores funcionales con vía de rechazo

Un productor por función, cada uno con su catálogo reducido. Devuelve componente o `Declined`.

**Medida:** tasa de rechazo por función y qué pasa después. Un productor que nunca declina es
sospechoso; uno que declina siempre está mal enrutado.

### Fase 6 — Ámbito por dominio

`domains` deja de estar vacío. El catálogo total puede crecer sin que ninguna decisión vea más de una
docena de candidatos.

---

## 7. Lo que esta arquitectura NO toca

- **El guard de `Chart`** (`shape.py:500-522`). Prohíbe chart en nodos `critical` y sobre fuentes sin
  cifras, con la razón escrita al lado: *"la fuente no trae cifras representables y un chart tendría
  que inventarlas"*. Existe para impedir el problema del bloque C. Se queda.
- **Los detectores deterministas donde aciertan.** Cada umbral está calibrado contra un fallo real.
- **La reactividad.** Las condiciones no negociables del §6 de `openui-adoption.md` siguen vigentes y
  esto no las toca: aquí no hay `Mutation` ni `Query`.
- **`SandboxHTML`.** Ver §8.
- **El paralelismo actual** de Content Writer e Interaction Designer. La latencia hoy es de 3,8 s por
  render y hay pregeneración con ventana deslizante (§4.2 de `multi-agent-pipeline.md`): el aprendiz
  no espera. **Esta arquitectura no se justifica por velocidad.**

---

## 8. Sobre generar componentes al vuelo

El hueco ya está reservado: `UiFormat.SIMULATION` existe en `models/node_render.py:55` marcado
*"reserved and never emitted"*, y `nivel3_openui.md` diseña el camino entero.

La investigación aporta el mecanismo que lo hace viable, y no es el que se suponía:

> Un componente puede generarse íntegramente y seguir siendo validable de forma determinista
> **exactamente en la medida en que su espacio de parámetros sea total.**

La promesa de Brilliant de configuraciones *"guaranteed to be correct, solvable and meaningful"* no
describe un validador: describe una **API sin configuraciones inválidas**. Y Brilliant no escribe el
contenido a mano — genera 1.000+ problemas con LLM; su salto del 0% al 93% en un tipo de puzle vino
de rediseñar el motor para que fuera *LLM-friendly*.

Consecuencia para esta arquitectura: la vía a la generación al vuelo **no es un sandbox de HTML
libre**, es diseñar componentes cuyo espacio de parámetros no admita estados inválidos. Eso es un
requisito sobre `ComponentSpec`, y encaja aquí de forma natural — pero es trabajo de después de la
fase 5, y sólo tiene sentido con la vía de rechazo funcionando.

---

## 9. Riesgo honesto

**Nadie hace esto.** El informe lo dice sin ambigüedad: en Vercel AI SDK, Tambo, OpenAI Apps SDK y
MCP Apps la decisión *es* la llamada a herramienta y los props *son* sus argumentos. OpenUI,
LangChain, A2UI y Thesys emiten el árbol directo. El único paso previo documentado en la industria es
de **recuperación**, no de clasificación — y `shape.py` ya es eso.

Además: **no existe ningún benchmark público entre 10 y 30 opciones** (todo empieza en ~50
herramientas) y **el fenómeno de componentes muertos no está descrito en ninguna parte**.

Se puede leer de dos formas y las dos son ciertas. Es terreno original —material propio para ANFAIA—
y es terreno sin red: no hay nadie a quien copiar cuando algo no funcione.

La mitigación es la del §6: fases pequeñas, cada una medible con el arnés que ya existe, y una
—la fase 2— que debe salir **idéntica** a la baseline. Si una fase no mueve su métrica, se revierte
sola: son commits independientes.

---

## 10. La métrica que decide si esto funcionó

No es "¿los cursos son más ricos?", que acaba siempre en opiniones.

Es **cuánto cuesta añadir el componente número 30**. Hoy son seis ediciones, dos de ellas centrales.
Si después de la fase 2 son cuatro y todas locales, la arquitectura funcionó. Si sigue habiendo que
tocar `shape.py`, no.

Esa cifra se mide la primera vez que se añada uno.

---

## 11. Frontera con la librería externa de componentes

El catálogo visual se está desarrollando como una librería independiente y sustituirá
gradualmente los componentes actuales. SkillNet no debe duplicar su implementación ni acoplar su
razonamiento pedagógico a componentes React concretos.

La frontera es:

- **La librería posee** el esquema de props, renderizado, estados interactivos, accesibilidad y
  versionado de cada componente.
- **SkillNet posee** la función pedagógica, las condiciones de uso, los requisitos de evidencia, la
  selección, la política de coste y la interpretación de eventos de aprendizaje.
- **El descriptor versionado compartido** conecta ambos lados mediante un `component_id` estable,
  `props_schema`, capacidades de presentación, requisitos, eventos y metadatos pedagógicos.

Durante la migración convivirán adaptadores antiguos y componentes de la librería. Cada sustitución
debe superar specs doradas de estructura, accesibilidad y eventos antes de retirar el bloque local;
el nombre del componente no debe aparecer cableado de nuevo en detectores centrales. El contrato
completo y su relación con QTI, H5P y xAPI se describe en
[`adaptive-learning.md`](adaptive-learning.md).

La continuación con el catálogo real de Didact —24 tipos educativos actuales, resolución por
facetas, shortlist de candidatos, recipes y moléculas declarativas para GenUI de nivel 3— se define
en [`didact-integration-strategy.md`](didact-integration-strategy.md).
