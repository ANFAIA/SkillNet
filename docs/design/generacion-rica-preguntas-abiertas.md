# Generación rica y multimodal — preguntas abiertas

**Fecha:** 2026-08-09
**Estado:** notas de sesión. Nada aquí es decisión. Son hipótesis y preguntas a resolver
cuando cierre la deep research sobre NotebookLM que está en curso.
**Origen:** sesión de trabajo sobre por qué los cursos generados salen pobres.

---

## 1. Lo que ya está decidido (no rehacer)

La arquitectura de "un agente decide, otro produce" **ya existe y está documentada**. Antes
de proponer nada, leer:

| Qué | Dónde |
|---|---|
| Planificador + productores + ensamblador | `multi-agent-pipeline.md` §2-3 (Blueprint Architect, Content Writer, Interaction Designer, Assembler) |
| Vocabulario de bloques congelado | `v2-dynamic-courses.md` §5.3 |
| IR canónica `UISpec` y adaptador de render | `v2-dynamic-courses.md` §5.2, §5.4 |
| Decisión OpenUI, nivel (c) sin reactividad | `openui-adoption.md` |
| Multimodal v3: Audio Script + Diagram Generator en paralelo | `multi-agent-pipeline.md` §14 |
| Personalización: `format_vector`, perfil del aprendiz, maestría | `v2-dynamic-courses.md` §3.3, §7 |

**Consecuencia:** el problema de los cursos pobres **no es de arquitectura de agentes**. Esa
capa está diseñada. Buscar la causa en otro sitio.

---

## 2. La hipótesis principal: el techo está en el vocabulario, no en el pipeline

El UI Kit congelado (`v2-dynamic-courses.md` §5.3) declara **nueve componentes emitibles por
el LLM**: `Stack`, `TextContent`, `Card`, `Callout`, `StepSequence`, `Table`, `CodeBlock`,
`Chart`, `QuizItem`. Más `Markdown`, que solo escribe el servidor.

De esos nueve, **ninguno produce contenido visual explicativo**:

- `Chart` solo cubre `bar` y `line` sobre datos numéricos. No es un diagrama conceptual.
- `ImageCard` está **excluido explícitamente**, junto con `Timeline`, `DragDrop`, `Simulation`
  y `SandboxHTML` (decisión del 2026-07-26).

Es decir: el modelo no emite imágenes ni diagramas **porque el dialecto no se lo permite**. Si
esto es correcto, mejorar el prompt del Content Writer o cambiar de modelo no va a mover la
aguja, y explicaría por qué el trabajo reciente sobre la UI no ha resuelto la sensación de
pobreza.

**Cómo comprobarlo antes de tocar nada:** coger tres documentos reales de segmento
(restauración, gestoría, clínica), generar el curso hoy, y contar la distribución de bloques
emitidos. Si el reparto es abrumadoramente `TextContent` + `QuizItem`, la hipótesis se sostiene
y el problema está en el kit. Si el modelo ya usa `StepSequence`, `Table` y `Callout` con
soltura y aun así se percibe pobre, la causa es otra y hay que buscarla en la calidad de cada
bloque, no en el catálogo.

Esa medición es barata y desbloquea la decisión. Hacerla primero.

---

## 3. Preguntas abiertas

### 3.1 ¿Los productores tienen anclaje propio?

¿El Content Writer y el Interaction Designer recuperan sus propios pasajes fuente, o solo
reciben el blueprint del Blueprint Architect?

Si solo reciben el blueprint, están escribiendo de memoria sobre un encargo, que es una receta
para inventar detalle plausible — justo el tipo de contenido que se lee bien y no enseña nada.

**Verificar en:** `apps/skillnet-api/src/agents/runtime/agents/` y el subgrafo `genera_ui_multi`.

### 3.2 ¿Puede un productor declinar?

Hoy `multi-agent-pipeline.md` §6 cubre **fallos** (el agente peta, se reintenta, se cae al
monolítico). No parece cubrir el **rechazo semántico**: que el productor conteste "este
contenido no admite diagrama, es una lista de requisitos sin relaciones entre sí".

Sin esa vía, cuando se añadan productores visuales el planificador forzará diagramas malos, y
el resultado será ruido multimodal en vez de lecciones mejores. La vía de rechazo es lo que
convierte "más formatos" en "mejor contenido".

Es un cambio de contrato entre planificador y productor, no de implementación de un agente.

### 3.3 Imagen extraída vs imagen generada

Son dos problemas distintos y conviene no mezclarlos:

- **Generada** (modelo de imagen, SVG, mermaid): sirve para diagramas conceptuales, flujos,
  relaciones. Ojo: para explicación, la generación declarativa (mermaid/SVG) es determinista,
  versionable y barata; un modelo de imagen no lo es.
- **Extraída del documento fuente**: la foto de la máquina real, del plato real, del formulario
  real que ya está dentro del PDF del cliente.

Para los segmentos objetivo (restauración, retail, gestorías, clínicas) la segunda vale
probablemente más que la primera, y hoy se está descartando en la ingesta. Ver si el pipeline
de ingesta conserva las imágenes de las fuentes o solo extrae texto.

### 3.4 ¿Rellena o produce menos?

Cuando la fuente es pobre, ¿el pipeline genera menos contenido y lo dice, o rellena para cubrir
la estructura del curso? Sospecha: rellena. Si es así, es una causa de pobreza percibida
independiente del vocabulario, y se arregla en el nodo de revisión, no en el kit.

### 3.5 ¿Está v2 activo?

Comprobar el estado del feature flag (`v2-dynamic-courses.md` §10) en el entorno donde se
están viendo los cursos pobres. Si lo que se está juzgando es todavía el pipeline monolítico
de v1, todo lo anterior sobra y la respuesta es mucho más simple.

**Comprobar esto primero de todo.**

---

## 4. Qué aporta la investigación de NotebookLM, y qué no

La deep research en curso está en
`Obsidian Vault/15_TRABAJO/SkillNet/07_ANFAIA/investigacion/notebooklm/`.

**Lo que NO va a dar, porque NotebookLM no lo tiene:**

- **Planificador.** En NotebookLM el planificador es el humano: decide qué artefacto quiere y
  pulsa el botón. SkillNet no puede pedirle eso al gerente de un restaurante, así que la pieza
  central del problema es justo la que el referente no resuelve. Ya está diseñada aquí
  (Blueprint Architect) y no hay nada que copiar.
- **Modelo del aprendiz.** NotebookLM produce un artefacto para quien pregunte, sin perfil ni
  maestría ni adaptación. Todo eso es propio (`format_vector`, pre-assessment, escalada de
  andamiaje) y no tiene equivalente allí.

**Lo que sí va a dar, y es lo que se le está pidiendo:**

- El **mecanismo de calidad por artefacto**: qué hace que un mapa mental o una guía de estudio
  salgan buenos — esqueleto fijo, esquema de salida, pasada de crítica, cuánta fuente ve cada
  generación.
- El **contrato de salida** de cada artefacto y cómo se fuerza que sea válido.
- El **coste y la latencia** reales de audio y vídeo, que es lo que decide si v3 cabe en un
  despliegue self-hosted de una PYME.
- Cómo se comporta un producto bueno cuando la fuente es floja (§3.4).

Ese es el material que hace falta para decidir el salto a v3, y por eso la investigación se
lee **antes** de tocar el kit.

---

## 5. Nota de deslinde: esto no es Oikolon

Oikolon (`investigacion/componentes_agentes/` en el vault) es la idea de Ismael de componentes
de UI que son agentes autónomos **en runtime**, con lifecycle, permisos y fronteras DBP.

Lo de este documento es otra cosa: el reparto de trabajo **en tiempo de generación** entre un
planificador y unos productores de bloque. El resultado de esa generación es un `UISpec`
estático que se renderiza y ya está.

Se parecen en el vocabulario ("componentes", "agentes") y no son lo mismo. Mantenerlos
separados; si algún día convergen, que sea por una decisión explícita y no por confusión de
nombres.

---

## 6. Orden sugerido

1. Comprobar el feature flag de v2 (§3.5). Barato, y puede invalidar todo lo demás.
2. Medir la distribución de bloques con tres documentos reales (§2).
3. Leer la síntesis de NotebookLM cuando cierre.
4. Con 1-3 sobre la mesa, decidir si el kit se amplía y con qué, y si el contrato
   planificador-productor necesita la vía de rechazo.

Nada de esto se decide antes del paso 3.
