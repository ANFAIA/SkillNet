---
title: "Integración de Didact"
order: 47
section: "extensibility"
---

# Integración de Didact en SkillNet

**Estado:** inventario completo integrado; adopción funcional por familias  
**Didact:** <https://github.com/JoseEstevez520/Didact> (MIT)  
**Revisión examinada:** [`06c80e8`](https://github.com/JoseEstevez520/Didact/commit/06c80e8a8af4f20ad20ba345b7b6b13e1cc27e0c)  
**Relacionado:** `openui-adoption.md`, `personalization-architecture.md`,
`learning-experience-architecture.md`, `v2-dynamic-courses.md`

> **Alcance de este documento:** describe el inventario y la integración ejecutable actual de
> Didact. La arquitectura objetivo neutral —donde Didact es un proveedor reemplazable,
> `LearningExperience` sustituye la frontera específica y los bloques pedagógicos legacy salen de
> cursos nuevos— se define en
> [`learning-experience-architecture.md`](learning-experience-architecture.md). Cuando una decisión
> histórica de adopción incremental de esta página contradiga ese objetivo, gana el documento
> neutral; esta página sigue ganando sobre qué tipos y puertos funcionan hoy.

## Decisión

SkillNet conserva la autoría pedagógica, la personalización, el RAG, la seguridad de evaluación y la composición OpenUI generada en el momento. Didact aporta contratos y componentes educativos accesibles. No se integra como un segundo motor de cursos ni como una lista de widgets que el LLM deba conocer completa.

```text
objetivo + knowledge pack + perfil cerrado
                 │
                 ▼
      plan de experiencia SkillNet
                 │
                 ▼
   resolver de capacidades de Didact
                 │  2–5 candidatos compatibles
                 ▼
       generación OpenUI on-the-fly
                 │
                 ▼
  validación → render Didact adaptado → eventos
```

Didact ofrece las facetas necesarias para seleccionar sin inferir por nombres: propósito, representación, acción del alumno, contexto, accesibilidad, madurez, esquema de autoría, capacidades y dependencias opcionales. SkillNet las adapta a `ComponentDescriptor`; el catálogo no decide por sí solo qué debe aprender la persona.

## Base OpenUI directa

La integración comenzó con dos experiencias del catálogo real `skillnet-ui/1`:

| Componente | Para qué entra | Estado que conserva |
| --- | --- | --- |
| `Flashcard(front, back)` | Intento de recuerdo antes de revelar; útil para reconocer o reconstruir | revelado y autoevaluación local |
| `HintReveal(title, hints, solution)` | Pistas progresivas y solución bajo petición; especialmente útil con más apoyo | número de pistas y solución visible |

Ambos cumplen el dialecto estático: propiedades literales, estado React local, sin `Query`, `Mutation`, código ejecutable ni identidad. Después se sumaron Glossary, Timeline y WorkedExample como bloques directos, y `DidactActivity` como referencia opaca a definiciones server-owned. Sus esquemas existen en frontend y backend; el test de deriva comprueba nombres, orden de propiedades y artefacto del prompt. La versión del prompt invalida renders producidos con catálogos anteriores.

En la primera adopción no se sustituyó `StepSequence` por `Timeline`: representaban la misma
capacidad y se evitó duplicarlas en el catálogo. Esta fue una decisión incremental, **no el estado
objetivo**. Para cursos nuevos, la migración aprobada retira `StepSequence` y los demás componentes
pedagógicos legacy del catálogo de autoría; Didact entra a través de la frontera neutral
`LearningExperience`. Los renderers legacy permanecen sólo para reproducir cursos publicados.
Tampoco se añadió repetición espaciada; Didact separa correctamente la tarjeta de la planificación de
repasos y SkillNet no necesita todavía ese scheduler.

## Selección cuando crezca el catálogo

### Frontera ejecutable actual

La disponibilidad completa y la exposición al modelo son dos conjuntos distintos:

- `didact_snapshot.json` y `export_didact_descriptors()` proyectan los **34 tipos** al
  resolver. Conservan identidad, facetas, acciones, representaciones, accesibilidad,
  productor y requisitos de puertos; un tipo bloqueado sigue siendo descubrible para
  experimentos y para explicar qué capacidad falta.
- `openui_names_for_shortlist()` es la puerta fail-closed. Solo traduce un tipo a su
  nombre de schema cuando renderer, permiso de emisión y puertos están listos.
- `build_didact_prompt_slice()` serializa exclusivamente esos schemas aceptados junto
  con el shell seguro de pantalla. Un tipo instalado pero bloqueado produce error
  explícito; nunca desaparece silenciosamente ni llega al LLM sin contrato.

Hoy los 34 tipos están inventariados y se cargan de forma lazy en el frontend. Veintinueve
tienen una ruta de emisión honesta: cinco bloques OpenUI directos, once evaluaciones
server-side, tres actividades con assets revisados, dos lecturas de progreso del host y
ocho actividades con definición, estado y puertos. Los otros cinco permanecen
disponibles para el resolver, pero bloqueados hasta que existan scheduler, simulación
adaptada o sandbox. La tabla de runtime al final de este documento es la autoridad sobre
cada familia.

La frontera ya está conectada al generador: el runtime forma una shortlist de 3-5 tipos,
aplica gates de renderer, puertos y datos, y entrega al modelo solo el slice permitido. Para
actividades ricas, una fase de autoría crea una `ActivityDefinition` server-owned y la
valida antes de persistir. Si no puede construirla con datos respaldados, hace `Decline` y
vuelve a una representación segura.

El modelo no debe recibir todos los componentes de Didact. Antes de cada generación se aplican filtros deterministas:

1. disponibilidad y madurez permitida;
2. misión cognitiva y función de la fuente;
3. requisitos presentes en el knowledge pack;
4. capacidades obligatorias de accesibilidad;
5. productor disponible (`content`, `assessment`, `media`, `simulation` o `deterministic`);
6. preferencias declaradas de presentación, como sesgo y no como obligación;
7. presupuesto de complejidad de la pantalla.

El resultado es una colección pequeña y versionada, no una elección final rígida. El LLM puede componer entre esos candidatos y `Decline` si ninguno representa honestamente la misión. `component_id@version`, capacidades y versión de selección entrarán en traza y caché cuando el filtro pase de sombra a producción.

## Niveles de adopción

### Nivel A — estático y seguro

Props planas o listas, estado efímero, sin servicios externos. Puede entrar directamente en OpenUI: Flashcard, HintReveal, Glossary y algunas representaciones visuales.

### Nivel B — respuesta y evaluación del host

El componente recoge una respuesta serializable, pero SkillNet conserva la respuesta correcta y evalúa por API. Matching, rúbricas con evidencia, anotación y preguntas avanzadas necesitan mapearse al endpoint y al sobre de eventos antes de entrar.

### Nivel C — motor o medio inyectado

CodeExercise, InteractiveMedia, BranchingScenario y SimulationLab necesitan un puerto explícito de ejecución, reproducción o transición de estados. Una simulación es datos + estado + transiciones deterministas + renderer; nunca código inventado por el LLM dentro del programa OpenUI.

## Invariantes

- Más componentes aportan riqueza cuando añaden acciones, estados, feedback o representaciones útiles.
- Los hechos críticos y las reglas de seguridad proceden del knowledge pack, no del componente.
- Una preferencia visual no fuerza una imagen sin valor ni permite inventar un asset.
- El answer key nunca llega en las props del navegador.
- Arrastrar nunca es la única vía de interacción.
- Una capacidad ausente produce fallback explícito o `Decline`, no una simulación fingida.
- La copia de un componente Didact vive en SkillNet y se actualiza deliberadamente; no se consume `main` mutable en producción.

## Matriz de runtime del frontend (2026-08-13)

Los 34 tipos estan instalados, tienen loader lazy y pueden referenciarse mediante
`DidactActivity(activity_id, component_id)`. OpenUI nunca recibe la definicion publica,
respuestas correctas ni configuracion de evaluacion. El porcentaje de `didact.progress` y
`didact.mastery-badge` lo inyecta el host desde `LearnerNodeState`; el cliente no puede
escribirlo.

| Estado | Tipos | Motivo |
|---|---|---|
| Usable local/estatico | flashcard, glossary-term, hint-reveal, rubric, timeline-steps, worked-example, data-explorer | No afirman correccion; puertos opcionales ausentes degradan |
| Persistencia host | self-explanation-prompt, concept-map, drawing-response, evidence-annotation | Estado por `/activities/{id}/state`; dibujo y anotacion aceptan evaluacion async |
| Evaluacion host compatible | equation-workbench, measurement-lab | Callback async con resultado de `/activities/{id}/evaluate` |
| Evaluacion server-side | matching, sort, categorize, cinco quiz, completion-problem, numeric-question, word-bank | Adaptador `SecureEvaluatedActivity`; la clave no llega a props, DOM ni eventos |
| Assets revisados | hotspot, label-diagram, interactive-media | Refs opacas `skasset_`; geometria/transcript verificados en servidor |
| Progreso de solo lectura | progress, mastery-badge | `GET /activities/{id}/progress` proyecta mastery del nodo; `progress.write` esta prohibido |
| Bloqueado: composicion/agenda | practice-set, retrieval-practice-session | Compone hijos evaluables o exige scheduler; no se finge |
| Bloqueado: runtime | branching-scenario, simulation-lab | Falta adaptar transiciones remotas al estado concreto del componente |
| Bloqueado: ejecucion | code-exercise | La respuesta generica aun no satisface `ArtifactExecutionResponse` |

Los endpoints de definicion, estado, evaluacion, transicion, ejecucion, assets y progreso
estan conectados como puertos genericos. Un puerto solo se expone cuando el contrato
concreto es compatible. La mera existencia de `/evaluate` no desbloquea un quiz que se
autocorrige en el navegador, ni `/progress` habilita `practice-set`.

## Siguiente ola propuesta

1. scheduler real antes de emitir `retrieval-practice-session`;
2. composición de hijos evaluables antes de emitir `practice-set`;
3. transiciones deterministas de `branching-scenario` y `simulation-lab` sobre el estado concreto del componente;
4. sandbox de `code-exercise` que cumpla `ArtifactExecutionResponse`;
5. medir las 7 estrategias de selección con el banco offline y, si hay clave, un piloto LLM pequeño.

Cada ola se mide con el mismo nodo y knowledge pack: cobertura de hechos críticos, evidencia obtenible, variedad de acciones, accesibilidad, tasa de reparación, tokens, latencia y estabilidad. No se promueve un componente solo porque su story aislada sea atractiva.

## Estado de cierre del 13 de agosto de 2026

- Los 34 tipos de Didact están fijados por commit, inventariados y disponibles mediante
  loaders lazy; el catálogo completo no aumenta el bundle inicial.
- 29 tipos son emitibles. Cinco siguen bloqueados con honestidad: `practice-set`,
  `retrieval-practice-session`, `branching-scenario`, `simulation-lab` y `code-exercise`.
- El runtime usa por defecto `top5` sobre una shortlist de 3-5 candidatos. Dual-agent y
  specialist permanecen en sombra. El catálogo completo permanece consultable por el resolver.
- La llamada opcional de autoría registra tokens, modelo y duración; si falla, la lección
  continúa con una representación segura. Un tipo `unsupported` declina antes del LLM.
- El experimento fixture favorece intención + shortlist + esquema específico: 89,8 puntos
  y 100% de gates, frente a 27,8 del brazo legacy. Es evidencia de arquitectura, no prueba
  definitiva de calidad LLM.
- La personalización causal sigue siendo débil (15,4% en el fixture). La próxima ronda debe
  aislar apoyo, presentación y profundidad con modelos reales y evaluación ciega.
