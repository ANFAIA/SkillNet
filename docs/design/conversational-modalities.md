# Conversación, voz y acompañamiento

> **Estado: dirección de producto y frontera de arquitectura; no compromiso de
> implementación inmediata.** Este documento distingue funciones que pueden parecer
> similares en la interfaz, pero que resuelven necesidades diferentes.

## Decisión

SkillNet tendrá un único tutor contextual y varias superficies que lo utilizan. No se
construirá un asistente independiente para el chat, otro para la mascota y otro para voz.
El contexto pedagógico, las fuentes y la memoria autorizada son comunes; cambian el tipo
de interacción y el resultado esperado.

```text
LearningContext -> Tutor -> ConversationEvent
                              |-> chat escrito
                              |-> sesión de voz
                              |-> companion cue
                              `-> acción educativa validada
```

Las cuatro funciones relacionadas con audio quedan separadas:

| Función | Entrada | Salida | Para qué sirve |
|---|---|---|---|
| Mensaje de audio en el chat | Audio grabado | Texto | Formular una duda sin escribir |
| Conversación Realtime | Voz en directo | Voz en directo y resultado escrito | Practicar una competencia conversacional |
| Mascota o companion | Estado del aprendizaje | Señal visual, texto breve o acción | Orientar dentro de la experiencia |
| Podcast o modalidad de audio | Fuentes y objetivo de un nodo o curso | Audio reproducible | Explicar o repasar contenido de forma lineal |

Compartir infraestructura no convierte estas funciones en variantes intercambiables.

## 1. Mensajes de audio en el chat

Un mensaje de audio es un método de entrada para el chat asíncrono. Se transcribe y
continúa por el mismo flujo que un mensaje escrito:

```text
texto -------------------> mensaje normalizado -> tutor -> respuesta escrita
audio -> transcripción --/
```

La respuesta es siempre texto. El audio no activa TTS ni abre una conversación en vivo.
Esto conserva las ventajas del chat: lectura rápida, citas, historial, búsqueda y
continuación asíncrona.

El mensaje debe conservar que su origen fue audio y la transcripción utilizada. Guardar
el archivo original es una política de retención, no una condición para que el tutor
funcione. La persona debe poder corregir una transcripción errónea antes de reutilizarla
como evidencia o memoria.

**Uso en `organization`:** permite a un empleado plantear una duda con menos fricción,
incluidos contextos donde escribir resulte incómodo o poco accesible. No añade una nueva
función de talento ni cambia la relación empresa-empleado.

**Uso en `individual`:** ofrece la misma comodidad al estudiar documentos propios. No
requiere un flujo distinto.

## 2. Conversaciones Realtime

Realtime es una actividad síncrona con turnos hablados, interrupción y respuesta oral. No
es el modo de voz del chat y no debe aparecer como control global sin propósito.

Se ofrece cuando el objetivo del curso exige practicar desempeño oral, por ejemplo:

- atención a clientes o pacientes;
- entrevista, negociación o venta;
- conversación en otro idioma;
- explicación oral de un procedimiento;
- simulación de una situación difícil o de una objeción.

La sesión recibe un escenario, un papel, criterios de observación y límites definidos por
el curso. Al terminar produce un resultado escrito revisable: resumen, transcripción,
feedback y evidencias candidatas. El modelo conversacional puede orientar y observar, pero
no actualiza directamente dominio, nota o talento. La evaluación confiable sigue en los
servicios pedagógicos del servidor.

```text
RealtimeActivityDefinition
  scenario
  learner_role
  tutor_role
  observable_criteria
  allowed_learning_actions
  completion_condition
```

En `organization` su valor depende de que exista una habilidad conversacional concreta;
no es una función general para todos los cursos. En `individual` puede utilizarse además
para práctica autodirigida, manteniendo el mismo contrato.

## 3. Mascota o companion

La mascota es una representación sustituible del acompañamiento pedagógico. No posee la
conversación, la transcripción, la síntesis de voz ni la memoria del alumno.

Consume señales pequeñas y tipadas:

```text
CompanionCue
  kind: notice | question | hint | success | silence
  text?
  target_id?
  action?: highlight | focus | open_hint
```

Sirve para llamar la atención, formular una pregunta breve, ofrecer una pista y reflejar
el estado de una sesión (`listening`, `thinking`, `speaking`). No lee automáticamente los
nodos ni narra el curso. Su diseño visual puede cambiar sin modificar el tutor.

Esta función tiene sentido en ambos modos porque acompaña a quien aprende. No debe mostrar
lenguaje de RR. HH. ni asumir que el alumno administra el espacio.

## 4. Podcasts y modalidad de audio

El podcast es contenido generado para escuchar, no una conversación y no una interfaz del
tutor. Su cometido es explicar, sintetizar, contrastar o repasar material del curso. Puede
utilizar una o varias voces, pero el resultado es lineal y reproducible.

Escuchar un podcast no demuestra dominio. Solo registra consumo; cualquier evidencia de
aprendizaje debe proceder de una actividad posterior. Las citas se presentan en paralelo
en la interfaz y no se fuerzan dentro de la locución.

Esta frontera complementa [delivery-modalities.md](delivery-modalities.md), que define el
audio como modalidad generada bajo demanda.

## 5. Contexto y eventos compartidos

Todas las superficies reciben un `LearningContext` mínimo, no el curso completo ni el DOM:

- objetivo y nodo actual;
- fragmentos de fuente autorizados;
- intentos relevantes;
- nivel de ayuda permitido;
- preferencias necesarias para esa interacción.

Los proveedores se conectan mediante adaptadores de capacidad. El dominio no expone
eventos específicos de OpenAI, WebRTC u otro proveedor:

```text
ConversationInput = text | recorded_audio | live_audio | learning_event
ConversationEvent = transcript | assistant_text | assistant_audio
                  | companion_cue | learning_action | completed | failed
```

Una instalación puede declarar `transcription`, `realtime` o `speech_generation`. La
ausencia de una capacidad oculta únicamente la función dependiente: un fallo de Realtime
puede volver al chat, y un chat por audio puede volver a entrada escrita.

## 6. Funcionalidad por modo de audiencia

La personalización dentro de un curso ya pertenece al núcleo común y sigue siendo útil
para cada empleado. No se utilizará esta ampliación para añadir al producto empresarial
funciones generales de productividad personal.

| Capacidad | `organization` | `individual` |
|---|---|---|
| Tutor contextual del nodo | Núcleo actual | Núcleo compartido |
| Audio como entrada del chat, respuesta textual | Útil y opcional | Útil y opcional |
| Realtime | Solo prácticas orales diseñadas | Prácticas orales diseñadas o autodirigidas |
| Mascota contextual | Ayuda al empleado dentro del curso | Ayuda dentro del curso |
| Podcast | Formación y repaso del contenido asignado | Estudio y repaso personal |
| Notas personales, planificación general o repaso entre cursos | No se añaden por esta iniciativa | Candidatos futuros del modo individual |
| Talento, equipos e informes colectivos | Se conservan | Se ocultan |

## Fuera de alcance

- responder con audio a una nota de voz enviada al chat;
- convertir cualquier chat en una llamada Realtime;
- usar la mascota para leer nodos completos;
- considerar escucha de audio o conversación libre como dominio demostrado;
- introducir notas, agenda o productividad personal en el modo empresarial;
- acoplar el dominio a un proveedor concreto de voz.

## Orden de implementación futuro

1. Audio grabado como entrada del chat, con respuesta textual.
2. Contrato común de eventos y señales de companion.
3. Actividades Realtime delimitadas por objetivo y criterios observables.
4. Mejora editorial y técnica de podcasts sobre el productor de modalidad existente.

Cada paso debe aportar valor por sí solo y conservar el funcionamiento en instalaciones
que no configuren servicios de audio.
