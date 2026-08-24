---
title: "Catálogo de componentes Didact"
order: 46
section: "extensibility"
---

# Catálogo de componentes Didact y huecos

**Estado:** catálogo pinneado v1 (34 tipos declarados, 6 bloqueados)
**Fuentes de verdad:**
`apps/skillnet-api/src/personalization/didact_component_registry.v1.json` (delta de
integración del host),
`apps/skillnet-api/src/personalization/didact_snapshot.json` (inventario del proveedor),
`apps/skillnet-api/src/render/kit.py` (el UI Kit que el validador y el prompt conocen).
**Relacionado:** [`didact-integration.md`](didact-integration.md),
[`extensibility.md`](extensibility.md),
[`learning-experience-architecture.md`](learning-experience-architecture.md)

> Este documento inventaría **qué componentes hay hoy**, cuáles están **bloqueados** y qué
> **tipos pedagógicamente valiosos faltan**, con una lista priorizada de recomendaciones. No
> implementa nada: es catálogo + auditoría.

## 1. Dos catálogos, una frontera

SkillNet mantiene dos vistas complementarias sobre los componentes de aprendizaje:

- **El registro de disponibilidad Didact** (`didact_component_registry.v1.json` +
  `didact_catalog.py`) responde *qué está instalado y qué puede ejecutar el host ahora*. Cada
  tipo declara: `renderer_mode` (`direct` / `activity_definition` / `blocked`), `emission`
  (`enabled` / `disabled`), `authoring_strategy` (`inline` / `server_activity` /
  `unsupported`) y los `required_ports`. La identidad pedagógica viene del snapshot
  autoritativo del proveedor (`available_types`, 34 tipos).
- **El UI Kit** (`render/kit.py`) es la fuente de verdad de la **validación**: los nombres de
  componente, los props exactos, los enums cerrados y el orden posicional del dialecto OpenUI
  que el LLM emite. `render/spec.py` lo hace cumplir.

Los puertos de host que SkillNet ofrece hoy son
`["assets", "clock", "evaluation", "persistence", "progress"]`
(`didact_component_registry.v1.json`). Un componente que exige un puerto fuera de esa lista
—`scheduler`, `simulation`, `execution`, `events`, `media`— no puede ejecutarse aunque esté
instalado.

## 2. Catálogo Didact actual (34 tipos)

### 2.1 Componentes habilitados con render directo (`inline`)

Autoría inline: el LLM los emite directamente en el episodio; render propio de SkillNet.

| Tipo Didact | Renderer | Componente kit relacionado |
|---|---|---|
| `didact.flashcard` | `Flashcard` | `Flashcard` (recall activo, no evalúa) |
| `didact.hint-reveal` | `HintReveal` | `HintReveal` (pistas progresivas) |
| `didact.timeline-steps` | `DidactTimeline` | `DidactTimeline` (secuencia cronológica) |
| `didact.worked-example` | `DidactWorkedExample` | `DidactWorkedExample` (solución razonada) |

### 2.2 Componentes habilitados como actividad de servidor (`server_activity`)

Se renderizan vía `DidactActivity` cargando por id una `ActivityDefinition` revisada
(el programa **nunca** contiene respuestas). Requieren los puertos indicados.

| Familia | Tipos | Puertos |
|---|---|---|
| Preguntas de opción | `quiz.single-choice`, `quiz.multi-select`, `quiz.true-false`, `quiz.fill-in-the-blank`, `quiz.short-answer` | `evaluation` |
| Emparejar / ordenar / clasificar | `matching`, `sort`, `categorize`, `word-bank` | `evaluation` |
| Numérico y simbólico | `numeric-question`, `equation-workbench`, `measurement-lab`, `completion-problem` | `evaluation` |
| Visual / espacial | `hotspot`, `label-diagram` | `assets`, `evaluation` |
| Construcción del aprendiz | `concept-map`, `drawing-response`, `evidence-annotation` | `evaluation`, `persistence` |
| Datos / medios | `data-explorer` (sin puertos), `interactive-media` | `assets`, `persistence` |
| Metacognición / progreso | `self-explanation-prompt` (`persistence`), `rubric` (`evaluation`), `progress` / `mastery-badge` (`progress`) | varios |

### 2.3 Componentes BLOQUEADOS (`emission: disabled`, `renderer_mode: blocked`)

Seis tipos declarados pero **no ejecutables** hoy. Se dividen por *causa* del bloqueo:

| Tipo | Motivo del bloqueo | Valor pedagógico |
|---|---|---|
| `didact.retrieval-practice-session` | Falta el puerto `scheduler` (además de `persistence`) | **Alto** — recall espaciado, retención a largo plazo |
| `didact.simulation-lab` | Falta el puerto `simulation` | **Alto** — sistemas cuantitativos ajustables, operaciones |
| `didact.code-exercise` | Falta el puerto `execution` (además de `evaluation`) | **Alto** — práctica ejecutable (SQL, scripting, técnico) |
| `didact.branching-scenario` | **No requiere puertos**; falta autoría/renderer en SkillNet | **Alto** — decisiones consecuentes, onboarding/compliance |
| `didact.practice-set` | Requiere solo `evaluation` (disponible); falta autoría | Medio — compone actividades sueltas en una sesión acotada |
| `didact.glossary-term` | Reemplazado por el componente propio `DidactGlossary` del kit | Bajo — ya cubierto (y el crítico lo desaconseja como cierre) |

Observación importante: `branching-scenario` y `practice-set` **no están bloqueados por falta
de puertos** —los puertos que piden ya existen o no piden ninguno—, sino porque SkillNet
todavía no ha construido su estrategia de autoría/renderer. Son los desbloqueos de menor
coste técnico.

## 3. El UI Kit propio de SkillNet (`render/kit.py`)

Más allá de Didact, el kit incluye componentes de **contenido** y de **experiencia** que el
LLM compone en el episodio. Los relevantes para esta auditoría:

- **Contenedores / contenido**: `Stack` (root), `Card`, `TextContent`, `Callout`,
  `StepSequence`, `Table`, `CodeBlock`, `Chart`, `BeforeAfter`, `Markdown` (solo fallback).
- **Interacción / evaluación inline**: `QuizItem`, `DragOrder`, `Flashcard`, `HintReveal`,
  `DidactGlossary`, `DidactTimeline`, `DidactWorkedExample`.
- **Medios sintetizados**: `AudioExplanation`, `PronunciationExercise`, y los dos
  **broker-scoped** `PodcastPlayer` / `InfographicImage` — reales y validables, pero que el
  generador solo ve cuando el media broker los inyecta por nodo porque existe un artefacto
  READY y la modalidad del aprendiz coincide (ver [`media-artifacts.md`](media-artifacts.md)).
- **Frontera neutral**: `LearningExperience` (referencia opaca a una experiencia resuelta;
  no expone proveedor ni respuestas) y `DidactActivity` (`llm_emittable=False`,
  `legacy_parseable=True`: cargable por id, playback histórico).

Cada componente puede reclamar *funciones de contenido* (`ENUMERAR`, `PROCEDIMENTAR`,
`CUANTIFICAR`, `CONTRASTAR`, `VARIAR`, `EXPLORAR`, `LOCALIZAR`, `EVALUAR`); hoy solo las cuatro
primeras tienen detector que las emita (`render/kit.py`, `shape.py`).

## 4. Auditoría de huecos (¿nos falta más por meter?)

Dos categorías: **(A) desbloquear lo ya declarado** y **(B) tipos genuinamente ausentes**.

### 4.1 (A) Desbloquear lo declarado — mayor retorno inmediato

1. **`branching-scenario`** — *sin coste de puertos*. Escenarios de decisión ramificada con un
   grafo de estado serializable. Cubre una necesidad real que hoy no tiene ningún componente:
   practicar decisiones consecuentes (compliance, atención al cliente, seguridad de
   procedimiento). Solo falta la estrategia de autoría/renderer. **Recomendación: primero.**
2. **`retrieval-practice-session` (recall espaciado)** — requiere un puerto `scheduler`.
   SkillNet ya tiene repetición espaciada (HLR) a nivel de curso; falta exponerla como
   componente in-episode para recall dentro de la lección. **Alto valor de retención.**
3. **`code-exercise` (sandbox)** — requiere un puerto `execution` (adaptador de ejecución en
   sandbox). Habilitaría la colección `technical-training` entera (SQL, scripting). Coste alto
   (aislamiento/seguridad) pero es la palanca clave para cursos técnicos.
4. **`simulation-lab`** — requiere un puerto `simulation`. Sistemas cuantitativos ajustables
   (parámetros, observables, pasos deterministas). Alto valor para matemáticas, ciencia y
   operaciones.
5. **`practice-set`** — puerto `evaluation` ya disponible; solo falta autoría. Compone
   actividades sueltas en una sesión acotada con revisión. Coste bajo, valor medio.

### 4.2 (B) Tipos pedagógicos genuinamente ausentes del catálogo

Juzgados contra necesidades reales de aprendizaje, no una lista genérica:

1. **Tutor socrático / diálogo conversacional evaluado** — SkillNet tiene chat, pero no un
   componente in-episode que conduzca una conversación de práctica con oráculo de corrección.
   Encaja con la frontera `LearningExperience`. **Alto valor** para lengua, razonamiento y
   soft-skills.
2. **Evaluación de habla / grabación de voz con oráculo** — existe `PronunciationExercise`
   (front) pero sin corrección real. Un componente de *speaking assessment* (grabar → puntuar)
   cerraría el bucle de idiomas.
3. **Media anotada con checkpoints / timeline-scrubber** — `interactive-media` está habilitado
   como actividad de servidor, pero un *scrubber* sobre vídeo/audio con puntos de decisión
   incrustados y transcripción navegable no tiene render propio. Valor medio-alto para
   procedimientos y escucha.
4. **Controlador de dificultad adaptativa / ruta de mastery** — hoy la variedad de evaluación
   es rotación determinista (`assessment.py`); falta un componente que ajuste dificultad según
   el desempeño dentro del episodio.
5. **Hoja de cálculo / data-wrangling interactivo** — `data-explorer` cubre exploración
   gráfica/tabular, pero no manipulación tipo spreadsheet (fórmulas, transformaciones).
6. **Anotación colaborativa / respuesta entre pares** — ningún componente multi-aprendiz;
   requeriría el puerto `events`. Valor bajo para el modelo actual (individual), a vigilar.

### 4.3 Recomendaciones priorizadas (top)

| # | Acción | Tipo | Por qué | Coste |
|---|---|---|---|---|
| 1 | Construir autoría/renderer de `branching-scenario` | Desbloqueo | Sin coste de puertos; llena un hueco pedagógico real (decisiones) | Bajo-medio |
| 2 | Exponer recall espaciado como `retrieval-practice-session` (puerto `scheduler`) | Desbloqueo | Retención; ya existe HLR a nivel de curso que reutilizar | Medio |
| 3 | Añadir puerto `execution` para `code-exercise` | Desbloqueo | Habilita cursos técnicos enteros | Alto (sandbox seguro) |
| 4 | Tutor socrático evaluado sobre `LearningExperience` | Nuevo tipo | Práctica conversacional con oráculo; encaja en la frontera neutral | Medio-alto |
| 5 | `practice-set` (autoría, puerto `evaluation` ya disponible) | Desbloqueo | Compone la sesión de práctica; coste bajo | Bajo |
| 6 | `simulation-lab` (puerto `simulation`) | Desbloqueo | Ciencia/mates/operaciones | Alto |

**Resumen de una línea:** el mayor valor a corto plazo no es inventar tipos nuevos, sino
**desbloquear lo que Didact ya declara** —empezando por `branching-scenario`, que no depende de
ningún puerto— y luego proveer los tres puertos de host que faltan (`scheduler`, `execution`,
`simulation`). El único tipo verdaderamente nuevo con retorno claro es el **tutor
conversacional evaluado**.
