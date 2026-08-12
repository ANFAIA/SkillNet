# Cuaderno de experimentos de personalización

**Estado:** documento vivo.  
**Última actualización:** 2026-08-11.  
**Ámbito:** cursos dinámicos v2, generación de UI, perfiles de aprendiz y futura librería
de componentes.

Este documento conserva el conocimiento producido por los experimentos. No es un volcado de logs:
resume hipótesis, método, resultados, decisiones y límites para que el trabajo pueda reproducirse,
criticarse y resultar útil fuera del contexto inmediato del código.

Estados usados:

- **Adoptado:** produjo una mejora y permanece en el producto o en su arquitectura.
- **Revertido:** la prueba produjo información, pero el cambio no debía permanecer.
- **Instrumental:** herramienta para medir; no cambia la experiencia de producción.
- **Abierto:** evidencia insuficiente o siguiente hipótesis pendiente.

## 1. Punto de partida

La personalización existente recibe rol, sector, experiencia, preset, accesibilidad, progreso,
errores, dominio y un `format_vector` inferido. Estas señales participan en la elección de formato,
scaffolding, prompts y clave de caché, pero no forman todavía un plan pedagógico explícito.

Hallazgos estructurales de la auditoría:

- `format_vector` describe afinidad de uso; no demuestra por sí solo aprendizaje.
- Su efecto sobre el contenido es indirecto: participa en la decisión de formato, no en el prompt
  final de UI.
- Durante los primeros tres nodos su contribución es nula por la fase de calibración.
- `memory_md` se usa en tutor/chat, pero no entra en el render compartido. Inyectarlo literalmente
  sin particionar la caché podría filtrar información entre personas.
- Los renders fijados y compartidos ocultan cambios de perfil si una prueba no controla `force`,
  preview, claves y estado previo.

La frontera de diseño resultante se documenta en
[`design/personalization-architecture.md`](design/personalization-architecture.md).

## 2. Barrido de perfiles reales — señal visible, causalidad no aislada

**Estado: instrumental.**

Se compararon renders ya persistidos del mismo nodo para Aitana (novata, `focus`, calibración) y
Diego (experimentado, `standard`, cuatro nodos completados y vector poblado).

| Métrica | Resultado |
|---|---:|
| Pares comparables | 4 |
| Similitud textual media | 0,4233 |
| Rango de similitud | 0,2666–0,6189 |
| Formato distinto | 3/4 |
| Longitud media Aitana | 678,5 caracteres |
| Longitud media Diego | 768,8 caracteres |

La divergencia era grande, pero no podía atribuirse únicamente al perfil: rol, experiencia,
preset, vector y salida de calibración cambiaban simultáneamente. La personalización semántica
explícita por rol era débil; buena parte de la diferencia observada era estructural.

**Aprendizaje:** no atribuir al `format_vector` una diferencia entre perfiles que también difieren
en calibración y experiencia. La siguiente ablación válida debe cambiar una sola señal.

Evidencia preservada:
[`evidencia-testing/2026-08-11/api-sweep/report.md`](evidencia-testing/2026-08-11/api-sweep/report.md).

## 3. Caché por rol y sector — colisión real

**Estado: adoptado.**

La clave usaba rol **o** sector. Dos personas con el mismo rol y sectores diferentes podían compartir
un render aunque el sector literal sí llegaba al prompt. El primer render podía, por tanto, imponer
al segundo ejemplos del sector equivocado.

Se cambió el bucket a un digest no identificativo del par normalizado `rol|sector` y se añadió una
regresión. Resultado de validación: 36 pruebas del módulo correctas.

**Aprendizaje transferible:** toda señal que llegue a un prompt compartido debe estar representada
en la clave de caché mediante una proyección segura y versionada.

## 4. Preferencias de imagen y audio — pedir no basta

**Estado: revertido como cambio de prompt; aprendizaje adoptado.**

Se generaron variantes reales del nodo de extintor con `gpt-4o-mini`.

| Condición | Resultado principal |
|---|---|
| Baseline, 3 renders | Audio 0/3; aviso crítico 3/3; práctica 3/3 |
| “Usa imágenes”, solo prompt | Imagen 0/3 |
| Audio conectado al pipeline | Audio 3/3; aviso crítico 1/3 |
| Audio + protección crítica | Aviso 3/3; audio 1/3; una corrida chocó con el fan-out |

No apareció imagen porque el catálogo y el planificador actuales no ofrecen una capacidad de imagen.
El audio sí apareció al conectarlo, pero desplazó información de seguridad. Proteger la advertencia
redujo de nuevo la presencia del audio.

**Aprendizajes:**

1. Una preferencia no puede cumplirse si el catálogo no aporta la capacidad.
2. La modalidad solicitada debe ser una restricción positiva, no un reemplazo de práctica,
   feedback o seguridad.
3. Avisos y hechos críticos deben viajar como invariantes verificables, no competir por espacio en
   el prompt.
4. Añadir componentes sin ampliar presupuesto, composición y validación puede provocar sustitución,
   no riqueza.

## 5. “Misión cognitiva central” inspirada por Brilliant

**Estado: revertido como regla universal; arquitectura refinada.**

Brilliant prioriza el objetivo, la progresión y el momento de comprensión; la IA implementa y
varía problemas dentro de ese marco. También muestra un concepto desde perspectivas diferentes en
lugar de limitarse a repetir el mismo tipo de pregunta.

Referencias:

- [Brilliant — Learn by doing](https://brilliant.org/)
- [Hand-crafted, machine-made](https://blog.brilliant.org/hand-crafted-machine-made/)
- [Visual Algebra](https://blog.brilliant.org/visual-algebra/)
- [Evals for AI learning games](https://blog.brilliant.org/when-almost-right-is-catastrophically-wrong-evals-for-ai-learning-games/)

Se ejecutaron 26 renders en cuatro tandas: baseline, cambio solo de prompt, contraste con material
cuantitativo y una regla estructural temporal.

Resultados comparables sobre cinco encargos, dos repeticiones:

| Métrica | Baseline | Misión forzada |
|---|---:|---:|
| Hijos medios de `root` | 4,0 | 3,3 |
| Recetas estructurales distintas | 5 | 4 |
| Latencia media | 8,19 s | 8,53 s |
| Primera validación | 10/10 | 10/10 |

La versión centrada mejoró extintor y devoluciones al eliminar comparaciones redundantes. No cambió
reclamaciones y empeoró cadena de frío: eliminó una tabla útil, no produjo el gráfico esperado y
un pase perdió el aviso crítico.

El cambio solo de prompt tampoco actuó como contrato: en 4 de 6 renders el modelo conservó dos
bloques conceptuales.

**Aprendizajes:**

- Una misión central no significa una pantalla pequeña ni un solo componente simple.
- Puede materializarse en una simulación con muchos estados, acciones y feedback, o en varios
  componentes coherentes.
- El problema es la redundancia o la competencia entre misiones, no la cantidad bruta.
- La naturaleza de la fuente debe condicionar la representación antes de escoger componentes.
- Los prompts expresan intención; los contratos y gates deterministas la hacen cumplir.

## 6. Simulación de animación — riqueza como capacidad

**Estado: instrumental; planificador en sombra adoptado para continuar investigando.**

Hipótesis: para aprender animación, un estudio manipulable de fotogramas aporta una capacidad que
un test o una secuencia no pueden sustituir.

Objetivo fijo: crear una animación de pelota con peso, controlar el `timing` y aplicar `squash and
stretch` sin cambiar el volumen aparente.

Perfiles simulados:

- exploradora visual: manipulación directa, feedback inmediato e inspección del resultado;
- experto conciso: prefiere texto, pero debe demostrar el mismo objetivo de producción.

| Catálogo | Planes válidos | Preferencia satisfecha | Cobertura de affordances |
|---|---:|---:|---:|
| Actual: `StepSequence` + `QuizItem` | 0/2 | 0 % | 0,0 |
| Futuro: añade `animation.timeline/ball-studio` | 2/2 | 50 % | 1,0 |
| Futuro sin requisitos de animación | 0/2 | 0 % | 0,0 |

El catálogo actual declina con `mission_unsupported`: no finge que contestar un test equivale a
crear una animación. El futuro selecciona un productor `simulation`, congela el modelo de estado
`animation.ball-timeline/v1` y espera eventos `frame_changed`, `preview_played` y
`animation_submitted`. Si falta el requisito, declina con `missing_requirements`.

La UI simulada mantiene dos componentes (`Stack` + estudio). La riqueza procede de sus affordances,
estados, feedback y evidencia observable, no de aumentar el número de bloques.

Reproducción:

```bash
cd apps/skillnet-api
uv run python scripts/experience_simulation.py tests/fixtures/animation-experience.json
```

## 7. Revisión multiagente — abstracción rechazada

**Estado: revertido antes de integrar.**

Se probó sustituir listas de `QuizItem|DragOrder` por una consulta genérica a
`ContentFunction.EVALUAR`. La revisión independiente detectó que mezclaba dos ejes:

- qué función pedagógica aporta un componente;
- qué productor sabe construirlo.

Una simulación puede enseñar y evaluar, pero necesita estado, motor y validador propios. Enviarla al
agente que solo conoce tests era una abstracción incorrecta. El cambio se retiró completamente.

El contrato en sombra separa ahora `ProducerKind`, affordances, eventos de evidencia y modelo de
estado. **Un experimento revertido no fue trabajo perdido: evitó fijar una frontera equivocada.**

## 8. Instrumentación disponible

`scripts/screen_eval.py` evalúa manifests sin red ni LLM y mide:

- componentes alcanzables desde `root`;
- bloques planificados perdidos y huérfanos añadidos;
- foco de misión central;
- redundancia textual;
- preservación de hechos críticos;
- diversidad entre objetivos y estabilidad entre repeticiones.

```bash
cd apps/skillnet-api
uv run python scripts/screen_eval.py tests/fixtures/screen-eval-scenarios.json
```

Estas métricas son señales, no un objetivo único. Una simulación rica no debe perder puntos por
tener muchos estados o subacciones. Para componentes ricos hay que medir también affordances,
estados válidos, feedback, solución, evidencia y plausibilidad.

## 9. Experimento en sombra sobre OpenUI real

**Fecha / estado:** 2026-08-11, completado; solo observación.

**Pregunta:** ¿puede el planificador explicar y comparar las decisiones de personalización sin
dejar de generar cada pantalla on the fly con OpenUI?

**Tratamiento:** se añadió un `PlanTrace` fail-open en el punto común del runtime, después del
assessment y antes de los generadores monolítico y multiagente. El trace recibe únicamente una
proyección cerrada del perfil, la misión inferida, los requisitos y el catálogo adaptado. No entra
en prompts, caché, selector, assembler, `ui_spec` ni reintentos: OpenUI sigue siendo la autoridad.

**Resultados live (`gpt-4o-mini`, cuatro encargos):** 4/4 renders pasaron a la primera; latencia
p50 8,05 s y p95 9,04 s; se sirvieron 8 de 13 tipos de bloque observables (62 %) y una media de
5,25 tipos por pantalla.

| Encargo | Misión sombra | Candidatos priorizados | Formato OpenUI | Componentes relevantes servidos |
|---|---|---|---|---|
| Extintor | recognize | BeforeAfter, StepSequence, Table | exercise | BeforeAfter, StepSequence, DragOrder |
| Higiene alimentaria | recognize | BeforeAfter, Table | mixed | BeforeAfter, Table, QuizItem |
| Protección de datos | recognize | BeforeAfter, Table | mixed | BeforeAfter, QuizItem |
| Devoluciones | recognize | BeforeAfter, StepSequence, Table | mixed | BeforeAfter, StepSequence, DragOrder |

El plan coincidió parcialmente con la salida, pero resultó demasiado conservador: la misión
`recognize` dominó los cuatro casos y no anticipó algunas interacciones que OpenUI sí añadió. No es
evidencia para sustituir el generador; sí es evidencia de que la taxonomía de misión necesita más
señal del objetivo y del tipo de evidencia esperado. También confirma que `ProducerKind` debe
seguir separado de la función pedagógica: un bloque puede enseñar y evaluar a la vez.

**Decisión:** mantener el planificador en sombra. El siguiente ensayo debe variar una única señal
por vez y medir no solo coincidencia de nombres, sino affordances, eventos de evidencia, estados y
feedback. La futura imagen se incorporará igual que cualquier otra capacidad: descriptor
`Presentation.IMAGE`, productor `MEDIA`, requisitos explícitos y composición posterior dentro del
`ui_spec` validado. Si no existe o no puede generarse un asset adecuado, el productor declina y el
resolver conserva una alternativa; no se inventa una imagen ni se bloquea la pantalla.

**Reproducción:** `scripts/quality_bench.py` serializa `plan_trace` junto al resultado normal del
bench. Los evaluadores offline y sus fixtures permanecen en el repositorio para comparar futuras
versiones sin depender de un proveedor.

## 10. Preferencias declaradas llevadas al producto

**Fecha / estado:** 2026-08-11, primera vertical integrada.

El experimento en sombra se convirtió en un control real y reversible del producto sin sustituir
OpenUI. El onboarding añade una sexta pregunta opcional y el empleado dispone de la ruta
/empleado/ajustes para cambiar en cualquier momento:

- presentación inicial: equilibrada, visual, textual o interactiva;
- detalle: conciso, estándar o detallado;
- imágenes: cuando sean útiles, preferir o evitar;
- accesibilidad, que continúa siendo un contrato funcional separado.

La declaración se persiste como learning_preferences JSONB cerrado y versionado. No se mezcla con
format_vector: lo primero es lo que la persona pide y lo segundo sigue siendo evidencia inferida
de interacción. Un bucket canónico entra en la clave compartida antes de que la preferencia llegue
a los prompts monolítico y multiagente, de modo que dos usuarios equivalentes comparten render y
dos preferencias incompatibles no lo comparten.

Guardar una preferencia incrementa personalization_revision y despeja los pins del alumno sin
borrar historial. Una pantalla visible permanece estable; al volver a abrirla se permite un cache
hit de la nueva variante. Si una generación antigua termina después del cambio, el guard de
revisión impide que vuelva a fijarse.

**Verificación:** migración 0010 -> 0011 aplicada sobre PostgreSQL real; 118 tests backend
focalizados, 2.793 tests backend no-integración fuera del fixture legado del grafo y 454 tests
frontend correctos, además del build de producción y Ruff. El recorrido
visual guardó visual + detallado + preferir imágenes, confirmó persistencia tras recarga y restauró
el perfil demo a equilibrado + estándar + cuando sean útiles. El onboarding mostró el nuevo paso
5 de 6 y la consola no registró errores.

El archivo histórico test_runtime_graph conserva 11 fallos derivados de un fixture multiagente
sin registrar: 38 pruebas del mismo archivo pasan y la suite amplia restante está verde. El cambio
sí corrigió dos fallos funcionales que esa ejecución descubrió (normalización de revisión en la
sesión simulada y ciclo de imports); no se ocultan como si fueran fallos de fixture.

**Límite honesto:** la preferencia visual ya sesga estructura y prompts, pero el catálogo OpenUI
actual todavía no tiene un componente de imagen de lección. Por tanto hoy produce más estructura
visual disponible (tablas, comparaciones, gráficos con datos reales) y deja preparada la selección
de Presentation.IMAGE; no inventa un asset que el productor actual no puede entregar. La imagen
real requiere el futuro descriptor tipado, procedencia, texto alternativo y productor MEDIA.

La matriz de aceptación y el A/B reproducible están en
docs/personalization-preferences-acceptance.md.

## 11. Decisiones acumuladas

1. El objetivo y los hechos críticos no se personalizan.
2. La preferencia explícita prevalece, pero no elimina estrategias necesarias.
3. Preferencia, accesibilidad, misión, representación, componente y apoyo son ejes distintos.
4. `user.md` puede guardar la declaración humana; el renderer consume una proyección cerrada,
   versionada y presente en caché.
5. Los componentes se comparan por capacidades y requisitos, no por nombres React.
6. Función pedagógica y productor son contratos separados.
7. Un productor puede devolver `Declined(reason)`; nunca inventa datos, media, física o estados.
8. La riqueza se mide por acciones y evidencia relevantes, no por cantidad de tarjetas.
9. Una regla no pasa a producción por mejorar una media agregada: debe conservar seguridad,
   objetivo y preferencias en cada caso crítico.

## 12. Siguientes experimentos

1. Ejecutar una matriz A/B con perfiles idénticos y una sola preferencia distinta.
2. Medir cumplimiento visible, hechos críticos, evaluación, coste, latencia y estabilidad.
3. Distinguir cuándo visual produce una mejora real de cuándo solo cambia decoración.
4. Etiquetar qué affordances faltan con más frecuencia en cursos reales.
5. Conectar el primer componente rico de la futura librería mediante el adaptador de catálogo.
6. Probar un productor de imagen tipado con fallback y procedencia, todavía detrás de un flag.

## 13. Plantilla para nuevas entradas

```markdown
### Experimento N — título

**Fecha / estado:**
**Pregunta:** qué queremos aprender.
**Hipótesis:** predicción falsable.
**Tratamiento:** única variable modificada.
**Controles:** perfil, objetivo, fuente, modelo, prompt, caché y repeticiones.
**Métricas:** calidad, seguridad, preferencia, coste y latencia.
**Resultados:** números y ejemplos relevantes.
**Confusores / límites:** qué no puede concluirse.
**Decisión:** adoptar, revertir, repetir o abandonar.
**Artefactos:** comando, fixture, manifest o evidencia.
```

Un resultado negativo se documenta igual que uno positivo. Su valor está en reducir el espacio de
decisiones futuras y evitar que otra persona repita el mismo error sin conocer la evidencia.
