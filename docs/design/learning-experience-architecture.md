# Arquitectura neutral de experiencias de aprendizaje

**Fecha:** 2026-08-14  
**Estado:** corte vertical implementado detrás de rollout

**Aplica a:** cursos dinámicos v2, selección de experiencias y futuros proveedores

**Autoridad:** este documento define la frontera entre verdad persistida, dirección episódica,
selección de capacidades y render. [`v2-dynamic-courses.md`](v2-dynamic-courses.md) conserva la
especificación del camino v2 y del fallback histórico; [`didact-integration.md`](didact-integration.md)
describe el inventario ejecutable de Didact.

La relación entre modalidad y estructura interna se amplía en
[`delivery-modalities.md`](delivery-modalities.md). Audio y vídeo son representaciones que pueden
vivir dentro de una experiencia; no son destinos de navegación ni pestañas que la persona deba
elegir.

## 1. Decisión

El curso publicado conserva su **constitución**: qué competencia importa, qué verdad fuente la
sustenta, qué errores son críticos y qué evidencia permite afirmar dominio. No conserva una
secuencia de pantallas, una modalidad, una variante visual ni un componente como verdad pedagógica.

La presentación se decide cuando la persona abre el nodo. El servidor construye un `EpisodeBrief`
grounded y adaptado a su estado; después filtra el catálogo por capacidades y fija una implementación
versionada. El resultado abierto queda anclado para que un refresco no cambie la actividad a mitad de
un intento.

```text
curso publicado
  CompetencyContract + SourceAffordanceMap + EvidenceGate
                           │
             estado actual de la persona
                           │
                           ▼
              EpisodeBrief on-the-fly
       (misión, acción, evidencia, límites, continuación)
                           │
                           ▼
        CapabilityBroker → shortlist honesta de 1–3
                           │
                           ▼
       ExperienceResolver → binding/definición fijados
                           │
                           ▼
             LearningExperience + shell_mode
                           │
                           ▼
       evidencia server-owned → mastery → continuación
```

Didact es el proveedor educativo principal hoy, no la ontología de SkillNet. `skillnet.text-content`
y `media.checkpoint-video` atraviesan la misma frontera. Añadir una simulación o un laboratorio de
código no debe modificar el contrato del curso, el director episódico ni `LearningExperience`.

## 2. Qué se fija y qué se genera

| Se fija al validar/publicar el curso | Se decide al abrir el nodo |
|---|---|
| Outcome, criticidad y prerrequisitos | Misión concreta para este intento |
| `CompetencyContract` y su versión | `EpisodeBrief` y presupuesto |
| Hechos requeridos y procedencia | Acción dominante y cantidad de apoyo |
| `SourceAffordanceMap`, revisiones y digests | Representación adecuada al trabajo y al contexto |
| `EvidenceGate`, oráculos privados y errores críticos | Shortlist de capacidades disponibles |
| Política de mastery | Binding y definición pública fijados para el render |
| Catálogo versionado y políticas de seguridad | `shell_mode` y condiciones de continuación |

No se precrean para cada curso vídeos, juegos, secuencias alternativas, baselines pedagógicas ni
artefactos de presentación especulativos. Los packs de conocimiento, mapas de affordances, índices y
oráculos no son “contenido del curso ya montado”: son la verdad reproducible y los límites desde los
que el runtime puede generar sin inventar.

`node_renders` persiste el resultado validado que efectivamente se sirvió por coste, auditoría y
reproducibilidad. Esa caché es consecuencia de una decisión runtime, no un plan de presentación
preparado durante la publicación.

## 3. Contratos estables

### 3.1 `CompetencyContract`

Define el resultado laboral, hechos obligatorios, criticidad, prerrequisitos, gates de evidencia,
errores críticos y `mastery_policy_ref`. No admite proveedor, componente, slot o layout. Un cambio de
Timeline a vídeo no puede cambiar un procedimiento seguro ni rebajar la evidencia requerida.

### 3.2 `SourceAffordanceMap`

Fija las fuentes y revisiones exactas disponibles, sus digests y qué acciones permiten sostener con
honestidad: inspeccionar un procedimiento, reconocer un estado, ordenar pasos o ejecutar en un
sandbox, por ejemplo. Una affordance puede ser exacta, derivada o sintética, pero siempre referencia
la fuente que la respalda. Si la fuente no permite una acción, el generador no debe simular que sí.

### 3.3 `EpisodeBrief`

Es un beat de aprendizaje creado on-the-fly y libre de nombres de proveedor. Contiene:

- referencia exacta a competencia, grounding y estado de la persona;
- una misión con una sola acción dominante;
- fuente y affordances autorizadas;
- modo de evaluación y gates, si son demostrables;
- errores críticos y recuperación;
- presupuesto de contenido, interacción, media y latencia;
- condiciones de continuación, incluida una salida por defecto.

No contiene `ScreenScheme`, `lead`, `concept`, `practice`, `component_id`, `provider` ni instrucciones
de layout. Explicación, práctica y transferencia siguen siendo recursos posibles, no una receta que
deba aparecer siempre ni en ese orden. La unidad coherente es la misión completa: puede ocupar un
scroll vertical y contener varias piezas si todas sirven a la misma acción dominante.

## 4. Tickets y SQL no son la misma experiencia

La abstracción sirve precisamente para permitir diferencias radicales sin crear dos plataformas.

| | Recuperar entradas | SQL |
|---|---|---|
| Resultado laboral | Atender a un cliente y recuperar la entrada correcta sin exponer ni confundir datos | Construir o corregir una consulta que produce el resultado solicitado |
| Verdad fuente | Manual vigente del proveedor, campos visibles, excepciones y límites del proceso | Esquema, datos de prueba, dialecto y restricciones de ejecución |
| Acción dominante plausible | Diagnosticar el caso y elegir/ejecutar el siguiente paso operativo | Escribir, ejecutar y depurar una consulta |
| Affordance necesaria | Caso operativo fiel, búsqueda, estados y decisiones del procedimiento | Editor y sandbox ejecutable con estado reiniciable |
| Evidencia válida | Decisión y secuencia correctas, incluido el tratamiento de errores críticos | Resultado ejecutado, tests y explicación del fallo |
| Experiencia resultante | Caso guiado o simulación de atención con referencia puntual al manual | Laboratorio de código con feedback del motor y casos de prueba |

Un cuestionario puede servir como comprobación limitada en ambos dominios, pero no sustituye la
transferencia operacional ni la ejecución. El broker debe declinar antes que presentar una imitación
de baja fidelidad como evidencia de dominio.

## 5. Catálogo amplio, contexto pequeño

Cada implementación publica un `CapabilityDescriptor` versionado y neutral respecto al framework:
acciones del aprendiz, evidencia producible, affordances, accesibilidad, seguridad, puertos, latencia
y calidad. El catálogo completo puede crecer sin entrar entero en el prompt ni en el bundle inicial
del navegador.

En runtime, `CapabilityBroker` aplica hard gates en este orden conceptual:

1. acción del aprendiz;
2. evidencia requerida;
3. affordances reales de la fuente;
4. accesibilidad;
5. seguridad;
6. puertos disponibles;
7. presupuesto de latencia.

Sólo después ordena los candidatos válidos de forma determinista. Devuelve una shortlist honesta de
uno a tres; no rellena el mínimo con opciones peores. Si no sobrevive ninguna, puede ampliar el
catálogo una sola vez, aplicando exactamente los mismos gates. Si aún no hay opción válida, devuelve
`Declined(reason)`.

El broker filtra **capacidades**. `ExperienceResolver` toma después esa lista y fija un binding
publicado (`experience_id`, `implementation_ref`, `definition_ref`). Esta separación evita que la
política pedagógica conozca detalles de proveedor. En el frontend, `ExperienceAdapterRegistry` carga
el adaptador de forma lazy por `implementation_ref`; `LearningExperience` no contiene un `switch`
central ni imports estáticos de todo el catálogo.

## 6. Evidencia, soporte y mastery

La autoridad de evaluación es el servidor. Answer keys, oráculos y rúbricas permanecen en la
definición privada. Una implementación evaluable envía un intento estable ligado a
`experience_id`; el servidor valida el binding y traduce el resultado a evidencia normalizada antes
de aplicar la política de mastery.

La escritura de intento, evidencia y mastery debe ser idempotente y transaccional. El cliente nunca
escribe score, outcome o dominio. Reproducción, clic, permanencia y finalización de media son señales
de uso, no evidencia de aprendizaje.

`support_only` es una salida honesta cuando existe material grounded para ayudar pero no una
capacidad certificada para producir la evidencia requerida. En ese modo:

- el `EpisodeBrief` usa `assessment_mode: none` y no referencia `EvidenceGate`;
- la persona puede recibir explicación, ejemplo o referencia operativa;
- ningún evento actualiza mastery ni satisface un gate;
- la continuación no puede declarar la competencia dominada.

Para convertir ese apoyo en evidencia hace falta otra experiencia evaluable, con puerto, binding y
oráculo server-owned. No basta con añadir un botón de “completado” o un checkpoint de reproducción.

## 7. Shell episódico y modalidades

`shell_mode` es una decisión server-owned persistida con el render:

- `episode`: muestra una misión coherente en un único flujo vertical. No agrupa por componentes
  “resolubles”, no crea slides y no introduce un segundo scroll dentro del contenido.
- `legacy_stepper`: conserva exactamente la navegación histórica para renders antiguos y para el
  fallback de rollout.

El navegador no infiere el shell por nombres de componentes, proveedor, orden de bloques ni presencia
de un quiz. Un refresh devuelve el mismo render y el mismo `shell_mode` fijados.

Audio y vídeo se embeben donde la misión los necesita. No existen pestañas Web/Audio/Vídeo ni tres
versiones paralelas de la misma pantalla. Las preferencias declaradas, ancho de banda, accesibilidad y
efectividad observada son señales de selección, nunca una taxonomía rígida de “estilos de
aprendizaje”. El vídeo no usa autoplay y requiere subtítulos o transcript; el audio necesita
controles, transcript y alternativa accesible.

La continuación pertenece al episodio y a su evidencia, no a la posición del scroll. Una misión
puede continuar a práctica adicional, recuperación, siguiente estado o revisión humana según sus
condiciones; el shell sólo presenta esa decisión.

## 8. Compatibilidad y rollout

`ScreenScheme` y la fórmula histórica de pantalla permanecen únicamente como fallback de rollout.
Se usan cuando `ADAPTIVE_EPISODES` está desactivado, cuando el director episódico declina o al servir
un render legacy ya fijado. No limitan el prompt episódico, no se proyectan dentro de `EpisodeBrief` y
no son el modelo de producto para cursos nuevos.

La cadena segura es:

1. episodio grounded con capacidad certificada;
2. episodio `support_only` cuando puede ayudar sin afirmar evidencia;
3. decline explícito hacia el camino `legacy_stepper` durante el rollout;
4. error visible y trazable si tampoco existe un fallback seguro.

`DidactActivity` se conserva como alias de lectura para publicaciones históricas. Los renders nuevos
cruzan `LearningExperience`; no se borran adaptadores o datos legacy mientras existan referencias
activas. Versiones y digests incompatibles invalidan caché y exigen regeneración o migración
explícita.

## 9. Simulaciones y GenUI de nivel 3

El registro ya admite futuros proveedores, pero registrar un nombre no crea una capacidad real. Una
simulación o experiencia de nivel 3 sólo se habilita cuando aporta:

- modelo de estado, transiciones e invariantes deterministas;
- puerto explícito de simulación o ejecución;
- reset reproducible y aislamiento entre intentos;
- oráculo server-owned y traducción a evidencia;
- fidelidad declarada respecto a fuente y entorno laboral;
- alternativa accesible y comportamiento seguro ante fallo;
- presupuesto de latencia cumplido y fallback honesto.

El generador selecciona recipes y definiciones tipadas; no genera código libre ejecutable dentro del
programa OpenUI. El primer piloto debe demostrar al menos un caso operativo como Gestión Tickets y
otro ejecutable como SQL. Si ambos requieren editar el contrato central, la abstracción aún no es
suficiente.

## 10. Checklist de validación de rollout

### Docker y backend

- Reconstruir la pila con `docker compose up -d --build` y confirmar que API, web y base de datos
  están healthy.
- Activar `ADAPTIVE_EPISODES` sólo en el entorno de prueba previsto y verificar que la versión de
  política separa las claves de caché legacy y episódicas.
- Usar un curso dinámico validado con knowledge pack `ready`, fuentes vigentes y un nodo que todavía
  no tenga un render fijado.
- Confirmar en la respuesta de `GET /nodes/{id}/render` que `shell_mode` es `episode` y que el render
  queda anclado; un segundo GET debe devolver la misma identidad.
- Probar por separado `ready`, `support_only` y decline hacia legacy. En `support_only`, comprobar que
  no se crea evidencia ni cambia mastery.

### Nodo fresco

- Validar con un nodo nuevo o regenerado explícitamente. Un nodo con `active_render_id` anterior debe
  seguir reproduciendo su versión fijada y no demuestra el rollout nuevo.
- Cubrir al menos un caso de manual operativo y uno de SQL/código; sus acciones, affordances y
  componentes elegidos deben ser materialmente distintos.
- Confirmar que facts, revisión de fuente, gates, errores críticos y binding aparecen en la traza
  server-side sin exponer oráculos privados al cliente.
- Forzar falta de puerto o evidencia y comprobar `support_only`/`Declined`, nunca una simulación o
  evaluación fingida.

### Navegador

- Abrir el nodo episódico en viewport de escritorio y móvil: una misión, un scroll vertical de página,
  sin tabs Web/Audio/Vídeo, sin slides y sin scroll anidado del contenido.
- Comprobar navegación por teclado, foco visible, lector de pantalla, contraste y preferencia de
  movimiento reducido.
- Para vídeo/audio, verificar ausencia de autoplay, controles, subtítulos o transcript y alternativa
  accesible.
- Recargar y volver atrás/adelante: identidad, contenido y `shell_mode` deben permanecer estables.
- Abrir un render `legacy_stepper` y confirmar que su navegación histórica no ha cambiado.
- Ejecutar una evidencia evaluable dos veces con el mismo `attempt_id`: debe ser idempotente. Repetir
  con una experiencia `support_only`: el dominio debe permanecer igual.

## 11. Criterios de éxito

La abstracción es suficiente cuando:

- el curso fija verdad y evidencia, no una presentación precreada;
- Tickets y SQL producen episodios radicalmente distintos desde el mismo contrato de runtime;
- el catálogo puede crecer sin agrandar el prompt ni modificar el core;
- una shortlist puede contener un único candidato válido o declinar con una razón observable;
- toda actualización de mastery procede de evidencia server-owned;
- `support_only` ayuda sin certificar;
- `shell_mode` no depende de heurísticas del navegador;
- audio y vídeo forman parte de la misión, no de una navegación por modalidades;
- `ScreenScheme` puede retirarse al terminar el rollout sin cambiar `EpisodeBrief` ni los bindings;
- una futura simulación entra mediante descriptor, puertos, definición, adaptador y pruebas, no mediante
  una rama especial en el planificador.

## 12. Relación con otros documentos

- [`v2-dynamic-courses.md`](v2-dynamic-courses.md) define entrega v2, persistencia, caché y transición
  de mastery. Sus recetas de pantalla describen el fallback `legacy_stepper`.
- [`node-knowledge-packs.md`](node-knowledge-packs.md) define la preparación de verdad fuente que
  alimenta `SourceAffordanceMap`.
- [`delivery-modalities.md`](delivery-modalities.md) define modalidad como affordance y señal de
  selección, no como pestaña.
- [`didact-integration.md`](didact-integration.md) enumera componentes, puertos y bloqueos reales del
  proveedor Didact.
- [`didact-integration-strategy.md`](didact-integration-strategy.md) desarrolla recipes y GenUI de
  nivel 3.
- [`openui-adoption.md`](openui-adoption.md) conserva las restricciones de dialecto, seguridad y
  renderer.
