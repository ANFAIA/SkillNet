# Arquitectura neutral de experiencias de aprendizaje

La relación entre modalidad (web, audio, vídeo y futuras) y estructura interna se define en
[delivery-modalities.md](delivery-modalities.md). En caso de duda, el agente selecciona una sola
experiencia para la persona; las modalidades no aparecen como pestañas ni como decisión manual.

**Fecha:** 2026-08-14  
**Estado:** contrato base implementado; rollout incremental y retirada legacy en curso.
**Aplica a:** cursos dinámicos v2, generación de cursos, catálogo educativo y futuras experiencias
de vídeo, juego, simulación o práctica presencial.  
**Autoridad:** este documento gana sobre decisiones anteriores que acoplen el plan pedagógico a un
nombre de componente. `v2-dynamic-courses.md` sigue siendo la autoridad sobre el comportamiento ya
implementado y `didact-integration.md` sobre el inventario ejecutable actual.

## Corte implementado — 14 de agosto de 2026

El primer corte productivo ya incluye intents, variantes, bindings, intentos y evidencia
normalizada append-only; planificación y materialización deterministas durante la validación del
curso; `LearningExperience` con registro lazy; proveedores Didact, texto SkillNet y vídeo con
checkpoint; y aplicación transaccional e idempotente de evidencia a mastery. Los cursos nuevos no
emiten `DidactActivity`; el alias permanece únicamente para reproducir programas históricos.

El runtime usa primero un binding preparado y sólo conserva autoría on-the-fly como compatibilidad
para cursos anteriores a la migración 0016. Las rondas R1–R9 de `output/harness` son un oracle
offline reproducible, complementado por tests de producto; no sustituyen todavía un experimento
online con cohortes reales ni una prueba de carga PostgreSQL.

## 1. Decisión

El curso conserva **qué debe aprenderse** y **qué evidencia lo demuestra**. No conserva como verdad
pedagógica permanente «usar `didact.timeline-steps`», «mostrar un vídeo» o «abrir un minijuego».
Esas son implementaciones reemplazables de una experiencia.

```text
objetivo + hechos de fuente + criticidad
                    │
                    ▼
          PedagogicalContract
                    │
                    ▼
             ExperiencePlan
      (intención, ritmo, acción, evidencia)
                    │
                    ▼
       resolver determinista de capacidades
                    │
          ┌─────────┼──────────┐
          ▼         ▼          ▼
       Didact     vídeo     juego/simulación
          └─────────┼──────────┘
                    ▼
          LearningExperience
                    │
                    ▼
     NormalizedEvidence → mastery → siguiente paso
```

Didact es el proveedor educativo preferido hoy. No es la ontología de SkillNet. Mañana dos
implementaciones distintas pueden competir por el mismo paso si satisfacen el mismo contrato.

## 2. Principios de producto

La experiencia visual sigue siendo minimalista: **una idea y una acción principal por pantalla**.
La complejidad vive en la secuencia, no en mostrar explicación, práctica, solución y evaluación a la
vez.

En formación empresarial el recorrido por defecto es:

```text
explicación mínima → práctica inmediata → transferencia
```

Es una política, no una plantilla rígida. Seguridad, cumplimiento y una regla nueva requieren
explicación previa; un repaso puede ir de resumen a transferencia; un error puede abrir aclaración,
ejemplo y nuevo intento. Los ritmos permitidos incluyen directo, guiado, procedimental, contraste,
exploración con contexto, experto, recuperación y síntesis.

Reglas estables:

1. Una pantalla tiene una función dominante y no necesita scroll para completar la acción.
2. La explicación previa es breve y obligatoria cuando omitirla haría inseguro el ensayo.
3. Se evita repetir ritmo, representación o acción sin motivo pedagógico, pero la variedad nunca
   gana a seguridad, accesibilidad o evidencia.
4. El feedback aparece junto a la acción; no es otra caja ornamental.
5. `TextContent` puede introducir o explicar aquello que ningún proveedor represente con honestidad.
   `Stack` puede permanecer como shell técnico. Ninguno compite como actividad educativa.

## 3. Modelo estable

### 3.1 `PedagogicalContract`

Es la parte duradera del curso y no contiene componentes ni proveedores:

```json
{
  "objective_id": "avoid-cross-contamination",
  "objective_version": 3,
  "outcome": "Preparar el pedido sin contaminación cruzada",
  "knowledge_type": "procedural",
  "criticality": "critical",
  "required_facts": ["atom-17", "atom-21"],
  "required_safety": ["No continuar si la ficha vigente no está disponible"],
  "required_evidence": ["correct_sequence", "safe_decision"],
  "mastery_policy_ref": "critical-procedure/1"
}
```

Los hechos son referencias a átomos o spans del `NodeKnowledgePack`; no reescrituras sin
procedencia. Cambiar de Timeline a vídeo no puede cambiar el objetivo, los hechos críticos ni la
regla de mastery.

### 3.2 `ExperiencePlan` y `ExperienceIntent`

`ExperiencePlan` describe cómo debería transcurrir el aprendizaje. Cada paso es un
`ExperienceIntent`: una necesidad pedagógica abstracta, sin proveedor, componente ni definición de
render.

```json
{
  "plan_id": "plan-node-4/default",
  "contract_ref": "avoid-cross-contamination@3",
  "rhythm": "demonstrate_then_transfer",
  "steps": [
    {
      "step_id": "explain",
      "intent": "explain",
      "learner_actions": ["observe"],
      "representations": ["procedural", "visual"],
      "required_evidence": [],
      "feedback": "progressive"
    },
    {
      "step_id": "practice",
      "intent": "guided_practice",
      "learner_actions": ["sequence"],
      "required_evidence": ["correct_sequence"],
      "feedback": "immediate"
    },
    {
      "step_id": "transfer",
      "intent": "transfer",
      "learner_actions": ["decide"],
      "required_evidence": ["safe_decision"],
      "feedback": "immediate"
    }
  ],
  "support_policy": "standard",
  "policy_version": "experience-policy/1"
}
```

Cada paso se materializa como una pantalla principal. El plan puede incluir ramas omitibles para
experiencia previa, alto mastery o recuperación; no obliga a recorrer siempre tres pantallas.

### 3.3 `ExperienceVariant` e `ImplementationBinding`

Design-time prepara una o más variantes válidas por intención. `ExperienceVariant` expresa una
realización pedagógica y las condiciones en las que conviene; todavía no apunta a una biblioteca.
`ImplementationBinding` enlaza después esa variante con un proveedor, una definición y sus versiones:

```json
{
  "intent_ref": "plan-node-4/default:explain",
  "variants": [
    {
      "variant_id": "motion-demo",
      "representations": ["video", "procedural"],
      "best_for": ["novice", "motion-relevant"]
    },
    {
      "variant_id": "concise-steps",
      "representations": ["textual", "procedural"],
      "best_for": ["review", "low-bandwidth"]
    }
  ],
  "bindings": [
    {
      "binding_id": "binding-video-18",
      "variant_ref": "motion-demo",
      "implementation_ref": "media.checkpoint-video@1",
      "definition_ref": "definition-18@2"
    },
    {
      "binding_id": "binding-timeline-44",
      "variant_ref": "concise-steps",
      "implementation_ref": "didact.timeline-steps@1",
      "definition_ref": "definition-44@1"
    }
  ],
  "fallback_binding_id": "binding-timeline-44"
}
```

Las variantes son equivalentes respecto a la intención del paso, no idénticas. Un vídeo puede
representar movimiento mejor y una secuencia puede ser más rápida y escaneable. La equivalencia se
acepta sólo si ambas preservan hechos, accesibilidad y evidencia exigida.

## 4. Catálogo de capacidades y proveedores

Toda implementación publica un descriptor versionado independiente de React:

```json
{
  "implementation_id": "didact.sort",
  "version": 1,
  "provider": "didact",
  "capabilities": {
    "intents": ["guided_practice", "assessment"],
    "representations": ["interactive", "procedural"],
    "learner_actions": ["sequence"],
    "evidence": ["correct_sequence"],
    "feedback": ["immediate"]
  },
  "requirements": {
    "ports": ["evaluation"],
    "assets": [],
    "runtime": "react"
  },
  "accessibility": {
    "keyboard": true,
    "screen_reader": true,
    "drag_alternative": true
  },
  "producer_kind": "assessment",
  "definition_schema_ref": "didact.sort.definition/1",
  "evidence_adapter_ref": "didact.sort.evidence/1"
}
```

Didact, vídeo, simulación y juegos se registran mediante el mismo contrato. Un proveedor posee
renderer, schema, estado de interacción y traducción de eventos. SkillNet posee objetivo, política,
selección, evaluación segura, procedencia, caché y mastery.

Como proveedor actual, Didact ofrece **29 implementaciones emitibles** y mantiene **5 bloqueadas**
con honestidad: `practice-set`, `retrieval-practice-session`, `branching-scenario`,
`simulation-lab` y `code-exercise`. Esa cifra describe disponibilidad de un proveedor, no limita el
modelo. El resolver puede descubrir las cinco, pero no crear un binding hasta que sus puertos sean
compatibles.

### 4.1 Resolver determinista

El resolver no inventa experiencias. Aplica primero gates obligatorios:

- implementación habilitada y versión compatible;
- intención, acción y representación compatibles;
- evidencia requerida producible;
- facts, assets y puertos disponibles;
- criticidad y seguridad satisfechas;
- alternativa accesible operable;
- dispositivo, conectividad, coste y latencia dentro del presupuesto.

Después ordena candidatos válidos por adecuación pedagógica, calidad de evidencia, apoyo necesario,
preferencia, efectividad histórica y variedad reciente. La variedad sólo desempata entre opciones
válidas. El resultado es una shortlist pequeña; un productor puede devolver `Declined(reason)`.

Ni los detectores de fuente, ni el plan global, ni los prompts deben nombrar implementaciones
concretas. Añadir vídeo o un juego consiste en registrar capacidades, productor, adaptador y pruebas;
no en abrir ramas nuevas en el planificador.

## 5. Generación del curso: trabajo profundo y paralelo

Las decisiones caras ocurren al generar o republicar el curso, cuando hay margen para planificar el
conjunto y producir activos reutilizables. El paralelismo tiene dos niveles: varios nodos se producen
simultáneamente y, dentro de cada nodo, productores independientes trabajan en paralelo.

```text
fuentes + esquema validado
          │
          ▼
  Course Architect ── objetivos, dependencias, criticidad
          │
          ▼
 Experience Director ── ritmos globales, variedad y cobertura
          │
     ┌────┼──────────── nodos en paralelo ────────────┐
     ▼    ▼                                            ▼
   nodo 1 nodo 2 ...                                nodo N
     │
     ├─ Explanation Producer ─┐
     ├─ Activity Producer ────┼─ en paralelo según el plan
     ├─ Assessment Producer ──┤
     └─ Media/Game Producer ──┘
                    │
                    ▼
              Node Assembler
                    │
       ┌────────────┼─────────────┐
       ▼            ▼             ▼
   grounding    accessibility   pedagogy/security
       └────────────┼─────────────┘
                    ▼
              Global Reviewer
```

Los agentes intercambian contratos tipados, no informes libres. El arquitecto fija el contrato; el
director distribuye ritmos; los productores no pueden cambiar hechos críticos o evidencia; los
validadores cargan la fuente de manera independiente. Una cola limita concurrencia por proveedor y
permite reintentar sólo el nodo o productor que falló.

Design-time debe dejar preparados:

- contrato y planes `default`, `experienced` y `remediation` cuando aporten valor;
- definiciones públicas y privadas de las variantes;
- fallbacks honestos y alternativas accesibles;
- assets congelados, transcript, subtítulos y procedencia cuando haya media;
- claves de evaluación server-side y mapeo a evidencia;
- una variante baseline servible sin LLM;
- hashes, versiones, coste, tokens y trazas de decisión.

El revisor global comprueba el curso completo: progresión, ausencia de monotonía mecánica,
cobertura, dificultad, distribución de evaluación y existencia de recuperación. No fuerza variedad
decorativa ni exige usar todas las familias del catálogo.

## 6. Runtime: selección rápida on-the-fly

Cuando el empleado abre un nodo, el runtime no vuelve a diseñar la pedagogía ni consulta a varios
agentes:

```text
estado + perfil proyectado + dispositivo
                    │
                    ▼
 seleccionar plan y variante ya aprobados
                    │
                    ▼
  cargar definición + fijar versión de pantalla
                    │
                    ▼
             servir inmediatamente
```

La selección es una función rápida, explicable y preferentemente determinista. Puede escoger vídeo
para un novato cuando el movimiento importa, Timeline para un repaso o bajo ancho de banda y Sort
tras un error de secuencia. La pantalla queda fijada mientras está abierta.

La personalización generativa residual —por ejemplo adaptar el contexto de un caso al rol— se hace
por prefetch durante el paso anterior. Si no termina, falla o invalida un gate, se sirve la baseline;
el empleado no espera a una nueva deliberación multiagente.

## 7. Frontera neutral de render

OpenUI compone una primitiva neutral:

```text
root = Stack([intro, experience], "md")
intro = TextContent("Revisa la regla antes de decidir.", "lead")
experience = LearningExperience("exp-node-4-practice")
```

`LearningExperience` recibe una referencia opaca. No recibe answer keys, prompts, código libre ni
la definición privada. El host resuelve la variante fijada y carga su adaptador:

```ts
interface ExperienceAdapter {
  implementationId: string
  validateDefinition(definition: unknown): ValidationResult
  render(definition: PublicDefinition, ports: HostPorts): ReactNode
  translateEvidence(event: unknown): NormalizedEvidence[]
  accessibleAlternative?: string
}
```

El frontend mantiene un único `ExperienceAdapterRegistry`, indexado por
`implementation_id@version`. `LearningExperience` consulta ese registro; no contiene un `switch` por
proveedor ni imports estáticos de todo el catálogo. Los loaders pueden seguir siendo lazy.

Los puertos (`assets`, `events`, `evaluation`, `persistence`, `simulation`, `execution`, `progress`)
son capacidades explícitas. El resolver rechaza una implementación si el host no satisface el
contrato concreto; la mera existencia de un endpoint genérico no la habilita.

## 8. Evidencia normalizada y mastery

Cada proveedor traduce sus eventos a un sobre estable:

```json
{
  "schema_version": 1,
  "objective_id": "avoid-cross-contamination",
  "experience_id": "exp-node-4-practice",
  "attempt_id": "attempt-...",
  "evidence_type": "safe_decision",
  "score": 0.8,
  "outcome": "partial",
  "error_kind": "shared_utensil",
  "hints_used": 1,
  "duration_ms": 42000,
  "implementation_ref": "didact.quiz.single-choice@1"
}
```

La autoridad del score es el servidor. La solución y la rúbrica viven en definición privada. Mastery
consume `objective_id`, evidencia, resultado y política; no conoce props de Didact ni estados de un
juego. Esta conexión reemplaza la dependencia histórica de `QuizItem`: cualquier experiencia que
produzca evidencia válida puede actualizar `learner_node_states` y disparar replanificación.

La escritura es idempotente y transaccional. En una sola transacción se valida el binding y la
definición fijados, se inserta el intento, se guarda la evidencia normalizada, se aplica la política
de mastery, se actualiza `learner_node_states` y se registra el evento/auditoría. `attempt_id` tiene
unicidad y una repetición devuelve el resultado ya confirmado. Si una parte falla no queda un intento
sin mastery, ni mastery sin evidencia. El cliente nunca escribe score, outcome o mastery.

Los eventos de engagement —reproducción, clic, permanencia— no se confunden con evidencia de
aprendizaje. Un vídeo pasivo puede explicar, pero no demostrar mastery; necesita checkpoints o una
actividad posterior si el contrato exige evidencia.

## 9. Fallback, seguridad y versionado

Cadena de fallback por paso:

1. siguiente variante aprobada que satisfaga el mismo contrato;
2. experiencia estática del proveedor con hechos preservados;
3. `TextContent` cuando la intención sea únicamente explicar;
4. baseline publicada;
5. `Declined(reason)` visible en traza y revisión.

Nunca se degrada silenciosamente a un componente pedagógico legacy. Una variante no puede ocultar
una omisión de seguridad ni fingir simulación, media o evaluación.

Las definiciones son **append-only**: una corrección crea versión nueva; no muta la que ya vio una
persona. Cada binding persiste `definition_digest`, digest de assets y versiones de contrato,
catálogo, adaptador y renderer. Se versionan por separado:

- `objective_version` y `PedagogicalContract`;
- `policy_version` y `ExperiencePlan`;
- catálogo y `implementation_id@version`;
- definición pública/privada y assets;
- adaptador de evidencia y política de mastery;
- renderer y prompt/productor.

Un curso publicado fija todas las referencias para ser reproducible. Una implementación nueva crea
una variante y pasa validación contra el mismo contrato; no sobrescribe una experiencia que alguien
ya cursó. La caché incluye los IDs, versiones y digests anteriores además de los buckets permitidos
de personalización. Cambios incompatibles invalidan caché y requieren republicación o migración
explícita; nunca se reutiliza una definición sólo porque conserva el mismo nombre lógico.

## 10. Migración desde el estado actual

El runtime actual tiene componentes SkillNet, wrappers Didact directos y `DidactActivity`. La meta
es una frontera única sin romper cursos publicados.

### Fase 1 — contrato y observabilidad

- Persistir trazas de objetivo, plan, candidato, fallback y componentes alcanzables.
- Definir `NormalizedEvidence` y medir qué experiencias actuales no pueden producirlo.
- Marcar de forma explícita documentación y caminos legacy.

**Gate:** cero diferencia en pantallas servidas.

### Fase 2 — modelo neutral y adaptadores

- Formalizar `ExperienceIntent → ExperienceVariant → ImplementationBinding`.
- Introducir la referencia neutral y tratar `DidactActivity` como alias temporal.
- Registrar los componentes Didact emitibles como implementaciones del proveedor `didact`.
- Crear `ExperienceAdapterRegistry` frontend con loaders lazy y pruebas de drift.
- Mantener `Stack` y `TextContent` como primitivas de composición; no como catálogo pedagógico.

**Gate:** golden specs y eventos equivalentes; ninguna clave privada llega al cliente.

### Fase 3 — generación multiagente en design-time

- Generar contratos y planes primero en sombra, con todos los hechos críticos.
- Preparar variantes por nodo en paralelo y validar cada una antes de publicar.
- Conservar la baseline inmediata; medir duración total, camino crítico, coste y reparación aislada.
- Hacer que agentes y caché reciban capacidades y versiones, no nombres React.

**Gate:** contratos deterministas; ningún productor cambia objetivo o seguridad; las variantes quedan
publicadas con definiciones append-only y digests.

### Fase 4 — selección rápida en runtime

- Seleccionar plan, variante y binding aprobados desde estado, proyección y capacidades del host.
- Fijar la pantalla abierta, servir baseline ante miss y pregenerar sólo personalización residual.
- Registrar razones de selección, fallback y latencia sin ejecutar deliberación multiagente.

**Gate:** ningún empleado depende de una llamada LLM para abrir el siguiente paso disponible.

### Fase 5 — evidencia neutral y mastery transaccional

- Traducir evaluaciones y estado de Didact a `NormalizedEvidence`.
- Escribir intento, evidencia, evento y mastery en una transacción idempotente.
- Probar respuesta correcta, parcial, error, pista, reintento, duplicado y rollback.

**Gate:** una actividad Didact evaluable recorre el ciclo de dominio sin `QuizItem`, y un fallo de
persistencia no deja estado parcial.

### Fase 6 — migración de catálogo y proveedores

- Sacar `StepSequence`, `Table`, `Chart`, `BeforeAfter`, `QuizItem`, `DragOrder` y wrappers especiales
  del catálogo que reciben los productores de cursos nuevos.
- Conservar adaptadores legacy de solo lectura para cursos ya publicados.
- No borrar datos ni renderers hasta que la telemetría confirme que no quedan referencias activas.
- Registrar vídeo y después simulación/juego sólo cuando satisfagan puertos, evidencia y alternativa
  accesible; no añadir ramas al planificador.

**Gate:** cursos nuevos usan `LearningExperience` + texto opcional; regresión v1 permanece verde y
añadir un proveedor no modifica esquema de curso, mastery, OpenUI ni planificador.

### Fase 7 — pruebas, rollout y retirada segura

- Ejecutar golden specs de render, contratos y eventos; accesibilidad; seguridad de answer keys;
  concurrencia e idempotencia; caché por digest; y regresión v1/v2.
- Activar por familias y capability flags, comparar cohortes y conservar rollback por binding.
- Validar una plataforma nueva con al menos dos recipes de dominios distintos antes de generalizarla.
- Retirar un renderer legacy sólo cuando no existan publicaciones ni intentos que lo referencien.

**Gate:** equivalencia o mejora medida, cero referencias activas y rollback ensayado.

## 11. Criterios de éxito

La abstracción es real cuando:

- el plan de curso no contiene nombres Didact, React, vídeo o juego;
- dos proveedores pueden satisfacer el mismo paso sin cambiar objetivo ni mastery;
- el runtime selecciona una variante aprobada sin generación bloqueante;
- toda experiencia evaluable produce evidencia normalizada server-owned;
- añadir una implementación exige descriptor, productor, adaptador y tests, no editar decisiones
  centrales;
- los cursos existentes siguen siendo reproducibles y los nuevos no generan bloques pedagógicos
  legacy;
- la variedad cambia el ritmo o la acción con propósito, no sólo el aspecto.

## 12. Decisiones que sustituyen direcciones anteriores

La historia no se reescribe: los documentos anteriores siguen explicando por qué existe el código
actual. Para trabajo nuevo quedan sustituidas estas direcciones concretas:

| Documento anterior | Decisión histórica | Decisión vigente |
|---|---|---|
| `didact-integration.md` | Convivencia pedagógica de bloques SkillNet y Didact; wrappers directos | Didact es proveedor; cursos nuevos cruzan `LearningExperience`; wrappers y legacy quedan sólo lectura |
| `multi-agent-pipeline.md` | Cuatro agentes principalmente en el render que espera/prefetchea el alumno | El trabajo caro y el paralelismo principal ocurren al generar/publicar; runtime selecciona bindings preparados |
| `v2-dynamic-courses.md` | UI spec por nodo generada on-the-fly y mastery acoplado al intento histórico | Runtime neutral con baseline preparada; toda implementación evaluable entra por `NormalizedEvidence` transaccional |
| `personalization-architecture.md` | `LearningExperiencePlan` puede congelar candidatos concretos | El plan contiene intents; variantes y bindings se versionan en capas separadas |

Hasta completar cada fase, el comportamiento implementado de esos documentos sigue siendo la verdad
operativa. Esta tabla define la dirección de migración, no autoriza borrar compatibilidad antes de
sus gates.

## 13. Relación con otros documentos

- [`personalization-architecture.md`](personalization-architecture.md) define la proyección de perfil,
  apoyo, caché y selección por capacidades; este documento añade design-time multiagente, variantes,
  frontera neutral y evidencia común.
- [`didact-integration.md`](didact-integration.md) describe qué puede ejecutar Didact hoy. Didact es
  un proveedor de esta arquitectura.
- [`adaptive-learning.md`](adaptive-learning.md) conserva taxonomía y criterios de experimentación.
- [`v2-dynamic-courses.md`](v2-dynamic-courses.md) es la especificación del runtime actual y de sus
  transiciones de mastery; la migración se aplica sin crear un segundo selector v1/v2.
- [`openui-adoption.md`](openui-adoption.md) conserva las restricciones del dialecto y renderer.
