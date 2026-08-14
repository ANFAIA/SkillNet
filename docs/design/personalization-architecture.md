# Arquitectura de personalización pedagógica

**Fecha:** 2026-08-11  
**Estado:** arquitectura objetivo y plan incremental; no describe comportamiento ya implementado.  
**Aplica a:** runtime de cursos dinámicos v2 y futura librería externa de componentes.

## 1. Decisión

La personalización se divide en cinco decisiones con distinta autoridad. No se pide a un único
prompt que elija simultáneamente qué enseñar, cómo practicarlo y qué componente dibujar.

```text
CourseNode validado
  -> objetivo de aprendizaje       (qué debe poder hacer; no se personaliza)
  -> misión cognitiva              (qué hará para aprenderlo)
  -> representación               (texto, imagen, audio, tabla, diagrama...)
  -> componente                   (capacidad concreta del catálogo)
  -> apoyo                        (pistas, ejemplo, densidad, feedback)
  -> UI spec validada y fijada
```

La variación valiosa ocurre en representación, componente y apoyo. El objetivo y los hechos
críticos permanecen estables. Así, «personalizar» no significa generar una lección distinta sin
criterio, sino producir variantes comparables de una misma intención pedagógica.

Esta arquitectura concreta y no sustituye las decisiones de
[`adaptive-learning.md`](adaptive-learning.md),
[`arquitectura-componentes-funcional.md`](arquitectura-componentes-funcional.md) y
[`v2-dynamic-courses.md`](v2-dynamic-courses.md).

La arquitectura de publicación que construye variantes durante la generación del curso, expone la
frontera neutral `LearningExperience` y normaliza evidencia de Didact, vídeo, juegos o simulaciones
hacia mastery se define en
[`learning-experience-architecture.md`](learning-experience-architecture.md). Este documento conserva
la autoridad sobre proyección de perfil, apoyo, caché y resolución por capacidades.

## 2. Las cinco capas

| Capa | Pregunta | Entrada principal | Salida | Autoridad |
|---|---|---|---|---|
| Objetivo | ¿Qué evidencia demostrará aprendizaje? | `CourseNode.outcome`, fuente y criticidad | criterio observable | creador; gate de esquema |
| Misión cognitiva | ¿Qué acción central hará el aprendiz? | objetivo, tipo de conocimiento y error previo | `reconocer`, `reconstruir`, `interpretar`, `decidir`, `explicar` o `producir` | política pedagógica |
| Representación | ¿En qué modalidad se expresa? | capacidades de fuente, preferencia declarada y accesibilidad | una o más modalidades compatibles | usuario + restricciones duras |
| Componente | ¿Qué capacidad del catálogo implementa misión y representación? | descriptor de catálogo, dominio, coste y requisitos | `component_id@version` o rechazo | resolver determinista |
| Apoyo | ¿Cuánta ayuda necesita esta persona ahora? | mastery band, experiencia, errores, ajustes de lectura | densidad, pistas, ejemplo y feedback | política adaptativa |

`ContentFunction` sigue describiendo la **forma utilizable de la fuente** (`CONTRASTAR`,
`PROCEDIMENTAR`, `CUANTIFICAR`...). La misión describe la acción del aprendiz. No son el mismo eje:
una fuente procedimental puede servir para `reconstruir` el orden o para `decidir` qué paso aplicar
ante una excepción.

## 3. Contrato intermedio

Antes del blueprint debe existir un plan tipado, pequeño y auditable. Es una decisión de dominio,
no una UI spec y no contiene prosa generada.

```python
@dataclass(frozen=True)
class LearningExperiencePlan:
    objective_id: str
    objective_version: int
    mission: CognitiveMission
    source_functions: tuple[ContentFunction, ...]
    representations: tuple[Presentation, ...]
    required_facts: tuple[str, ...]
    required_safety: tuple[str, ...]
    support: SupportPolicy
    component_candidates: tuple[ComponentRef, ...]
    rationale_codes: tuple[str, ...]
    policy_version: str
```

El plan contiene referencias a hechos o spans de fuente, no copias reescritas por el modelo. Los
agentes de contenido reciben el plan y rellenan componentes; no pueden cambiar misión, candidatos,
criticidad ni restricciones. El ensamblador acepta únicamente IDs declarados por el blueprint:
un bloque huérfano es un error reparable, no un componente que se conecta automáticamente al root.

### Invariantes del plan

1. Hay una misión central por nodo. Puede materializarse en un componente rico con muchos estados
   y acciones, o en varios componentes coherentes; no equivale a limitar la cantidad de UI. Lo que
   se evita es una segunda misión competidora o bloques redundantes sin una capacidad nueva.
2. La verificación observa el objetivo; no se elige por variedad visual.
3. Los avisos, límites y prohibiciones de una fuente crítica son `required_safety` y sobreviven a
   cualquier variante.
4. Una modalidad solicitada aparece cuando existe una capacidad compatible. Si no existe, el plan
   registra un `fallback_reason` visible; nunca finge que la cumplió.
5. Accesibilidad es un filtro obligatorio anterior al ranking. Una preferencia no puede seleccionar
   un componente que la persona no pueda operar.
6. Todo productor puede devolver `Declined(reason)`. Con datos insuficientes se baja al siguiente
   candidato; no se inventan cifras, relaciones espaciales, ramas ni media.
7. El renderer sólo recibe una UI spec validada; nunca HTML o código libre generado.

## 4. Proyección de personalización

El planificador no recibe `memory_md`, eventos crudos ni texto libre de perfil. Recibe una
proyección determinista, de vocabulario cerrado y sin identidad:

```json
{
  "declared_presentations": ["image"],
  "inferred_presentation_bucket": "exercise-high",
  "support_band": "novice",
  "density": 2,
  "accessibility_capabilities": ["keyboard", "reduced_motion"],
  "error_signal": "procedural",
  "calibrating": false,
  "projection_version": "personalization/1"
}
```

La preferencia declarada es una restricción positiva: «incluye imagen», no «elimina texto,
práctica y feedback». El `format_vector` actual queda como señal inferida secundaria. El apoyo cambia
la cantidad de ayuda, no la verdad de la explicación ni el objetivo.

La compilación inicial vive en `src/personalization/projection.py`. Acepta la forma del perfil que
ya carga el runtime, pero descarta `role_title` y `sector`: siguen pudiendo contextualizar ejemplos
en el pipeline actual, no son preferencias ni se copian al plan. Tampoco acepta `user_id`,
`memory_md` o eventos crudos. Durante los tres nodos de calibración el vector inferido se marca como
desconocido. La dimensión heredada `codigo` también permanece desconocida porque asignarla a texto o
imagen inventaría una semántica que los eventos actuales no miden.

## 5. Resolución contra la librería de componentes

La librería publica capacidades; SkillNet conserva la política. Su descriptor versionado debe poder
responder, sin importar React, a estas preguntas:

- qué misiones, funciones de fuente y representaciones soporta;
- qué affordances ofrece (manipular, construir, ensayar, inspeccionar resultado...);
- qué requisitos necesita (`numeric_series`, `image_asset`, `branching_script`...);
- qué operaciones accesibles ofrece y cuál es la alternativa al arrastre;
- qué eventos y evidencias produce y qué contrato de feedback garantiza;
- qué modelo de estado versionado necesita;
- qué productor lo construye (`content`, `assessment`, `media`, `simulation` o `deterministic`);
- qué coste y latencia añade;
- qué schema de props y versión de renderer necesita.

La resolución es intersección más ranking:

```text
candidatos = catálogo
  ∩ misión
  ∩ función de fuente
  ∩ representación solicitada
  ∩ capacidades de accesibilidad
  ∩ requisitos realmente disponibles
  ∩ presupuesto del despliegue

elegido = rank(candidatos, política, exploración controlada)
```

El resultado no es solo un nombre. El plan congela un `ResolvedComponent` con
`component_id@version`, `producer_kind`, affordances, requisitos, `state_model_ref` y eventos de
evidencia. La función pedagógica no decide qué agente lo genera: una simulación puede enseñar y
evaluar a la vez, pero necesita un productor y un validador distintos de un `QuizItem`.

### Imagen generada dentro de OpenUI

Una futura imagen de curso no rompe el principio *on the fly*: el plan resuelve un descriptor con
`presentations={image}`, `producer_kind=media` y requisitos como `source_spans`, `image_brief` o un
`image_asset` ya disponible. El productor de media genera o recupera el recurso, conserva
procedencia y texto alternativo, y devuelve una referencia tipada. El ensamblador la incorpora a la
UI spec de OpenUI junto con práctica y seguridad; no genera HTML ni incrusta un prompt libre en el
cliente. Si faltan productor, presupuesto o evidencia suficiente, el candidato devuelve
`Declined(reason)` y se elige otra representación compatible. La imagen es así una capacidad
dinámica del catálogo, no una plantilla fija ni una excepción en el orquestador.

El catálogo puede crecer a cientos de componentes sin ensanchar el prompt: el LLM, cuando sea
necesario, ve sólo los pocos candidatos ya filtrados. `component_id@version` se persiste; nombres de
clases React no. El kit actual y la librería nueva conviven mediante dos adaptadores que consumen el
mismo plan y producen la misma IR canónica.

## 6. Caché, privacidad y estabilidad

La caché compartida sólo es segura si toda señal que alcance el prompt está representada en una
clave no identificativa. El material de clave objetivo es:

```text
node_id | schema_version | objective_version | policy_version |
projection_version | preference_bucket | support_band | density |
accessibility_capability_bucket | component_catalog_version |
backend | model | prompt_version
```

Reglas:

- nunca incluir `user_id`, memoria libre, diagnósticos o eventos individuales;
- nunca introducir en el prompt un dato que no esté proyectado en la clave;
- los buckets deben ser discretos y tener población suficiente para evitar seudonimización;
- el render se fija al abrir el nodo, como ya decide v2; no cambia durante una pantalla activa;
- cambios de objetivo, política, catálogo o prompt invalidan explícitamente la clave;
- el plan y sus `rationale_codes` se guardan para auditoría, separados de la prosa del render.

## 7. Validación por capas

La validación sintáctica actual es necesaria, pero no suficiente. Cada render pasa puertas distintas:

| Puerta | Comprueba | Tipo |
|---|---|---|
| Plan | misión única, restricciones, candidato disponible | determinista |
| Fuente | cifras, relaciones, media y hechos respaldados | determinista + eval focalizado |
| Componente | props schema, versión, accesibilidad y coste | determinista |
| Ensamblaje | IDs exactos, alcanzabilidad desde `root`, orden y cierre | determinista |
| Pedagógica | objetivo observable, feedback informativo, apoyo coherente | eval rubricado |
| Seguridad | preservación de `required_safety`, sin imposibles ni estados incoherentes | determinista cuando sea posible |

Las métricas distinguen componentes generados de componentes **alcanzables** desde `root`. Un bloque
huérfano no cuenta como variedad ni como cumplimiento. Para componentes interactivos ricos se añaden
evals específicos: solución única, estados posibles, claridad visual, consistencia entre estado y
feedback y plausibilidad de la simulación.

## 8. Experimentos que producen conocimiento

No se compara «prompt A contra prompt B» agregando todos los cursos. Se fija objetivo y fuente, y se
cambia una capa:

1. **Perspectivas:** el mismo objetivo como `interpretar`, `detectar` y `decidir`; hechos críticos
   idénticos.
2. **Representación:** misma misión con tabla, diagrama o imagen; la modalidad solicitada se mantiene
   en todas las variantes asignadas a esa persona.
3. **Apoyo:** mismo componente con ejemplo resuelto, pistas graduadas o caso directo.
4. **Resolver:** mismo plan contra kit actual y librería nueva; golden specs y eventos equivalentes.
5. **Ablación:** con/sin preferencia inferida, nunca con/sin accesibilidad obligatoria.

Por generación se mide: primera validación, fallback, hechos omitidos/inventados, seguridad
preservada, alcanzabilidad, misión cumplida, variedad entre objetivos equivalentes, latencia y coste.
Con usuarios se separan: preferencia, engagement, dominio inmediato y transferencia. Una pantalla
menos plana que no mejora la acción del aprendiz no gana.

## 9. Migración incremental

### Fase 0 — observabilidad sin cambio de comportamiento

- Registrar la decisión actual como `PlanTrace`: formato, `ContentFunction`, blueprint, bloques
  alcanzables, correcciones y fallback.
- Corregir el bench para contar sólo el subgrafo alcanzable desde `root`.
- Crear un corpus pequeño etiquetado por objetivo, misión esperada y hechos obligatorios.

**Gate:** cero diferencia en UI specs servidas.

### Fase 1 — plan en modo sombra

- Construir `LearningExperiencePlan` como función pura a partir del estado ya disponible.
- No usarlo aún para generar; comparar su selección con el pipeline real.
- Versionar proyección y política desde el primer día.

**Gate:** planes deterministas y explicables; ninguna señal libre entra en prompt o caché.

### Fase 2 — misión y apoyo tipados

- Hacer que blueprint consuma `mission` y `SupportPolicy`.
- Mantener el mapeo actual de componentes para aislar el efecto arquitectónico.
- Rechazar extras y huérfanos en vez de conectarlos al root.

**Gate:** seguridad y verificación no regresan; aumenta el cumplimiento del blueprint.

### Fase 3 — resolver de capacidades

- Mover función, requisitos, accesibilidad y coste al registro.
- Resolver candidatos antes de llamar a los agentes escritores.
- Conservar fallback al kit actual y `Declined(reason)`.

**Gate:** añadir un componente no modifica `shape.py`, el prompt global ni el ensamblador.

### Fase 4 — preferencia declarada

- Añadir preferencias de presentación editables en onboarding y ajustes.
- Compilar `user.md` a `PersonalizationProjection`; no inyectarlo directamente.
- Incorporar los buckets a caché y mostrar razones de fallback de modalidad.

**Gate:** pruebas E2E demuestran que una preferencia soportada aparece y persiste, y que cambiarla
regenera sólo renders compatibles, sin filtrar identidad en la caché.

### Fase 5 — librería externa y exploración

- Adaptador dual con golden specs antes de sustituir componentes.
- Activar componentes nuevos por capability flags y por familias.
- Explorar variantes únicamente dentro de planes válidos y con posibilidad de rollback.

**Gate:** equivalencia funcional del adaptador antiguo y el nuevo; los nuevos componentes superan
sus evals específicos antes de producción.

## 10. Ubicación propuesta en código

```text
src/personalization/
  projection.py       # perfil/eventos -> PersonalizationProjection, puro
  policy.py           # objetivo + proyección -> misión y apoyo, puro
  plan.py             # tipos e invariantes de LearningExperiencePlan
  resolver.py         # plan + catálogo -> candidatos o Declined, puro
  cache.py            # serialización versionada de buckets

src/components/
  catalog.py          # Protocol del catálogo, sin React
  legacy_adapter.py   # descriptores del kit actual
  library_adapter.py  # futura librería externa
```

LangGraph orquesta carga, planificación, escritura, validación y persistencia. Las reglas de dominio
anteriores permanecen funciones puras fuera de los nodos y de los prompts. Los subagentes reciben
un contrato congelado y responsabilidades estrechas: planificar, escribir contenido, diseñar
interacción y ensamblar; ninguno puede reinterpretar las decisiones de otra capa.

## 11. Criterio de éxito arquitectónico

La arquitectura habrá funcionado cuando:

- añadir un componente sea registrar capacidades y tests, no editar decisiones centrales;
- dos renders puedan variar sin cambiar objetivo ni hechos obligatorios;
- cada diferencia pueda explicarse mediante códigos de política;
- una petición explícita de modalidad se cumpla o produzca una razón honesta;
- ninguna variante inválida llegue al humano sólo porque compila;
- el sistema pueda volver al kit anterior sin perder estado ni aprendizaje medido.

La estrategia concreta para consumir el catálogo grande de Didact, limitar cada decisión a una
shortlist, distinguir recipes de nuevos componentes y avanzar hacia GenUI de nivel 3 está en
[`didact-integration-strategy.md`](didact-integration-strategy.md).
