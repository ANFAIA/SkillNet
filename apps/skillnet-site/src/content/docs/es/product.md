---
title: "Producto"
order: 21
section: "start"
---

# Producto

> **Estado: Borrador.** Define qué es SkillNet, para quién es y qué hace.
>
> El actual producto orientado a empresa sigue siendo la base implementada. El futuro
> modelo de audiencia para despliegues de organización e individual se define en
> [audience-modes.md](/docs/audience-modes).

---

## Qué es SkillNet

SkillNet es un sistema de aprendizaje que construye la experiencia de formación adecuada para cada persona, a partir del conocimiento que ya existe en su empresa.

SkillNet lee el conocimiento de una empresa, incluidos sus manuales, procedimientos y protocolos, y lo convierte en formación adaptada a quien aprende. No es un catálogo de cursos ni un LMS estático con una capa de IA.

Código abierto, autoalojado, una instancia por empresa. No es multi-tenant — por diseño.

No compite con las ofertas de nivel empresarial. Existe para las empresas a las que esas ofertas no atienden.

**La idea central:** el mismo conocimiento de empresa debería producir experiencias de formación distintas según el rol, el nivel y el progreso de cada persona, sin que un admin tenga que configurar cada variante.

## Roles

| Rol | Qué hace |
|------|-------------|
| **Admin** | Sube documentos, revisa el contenido generado, asigna formación, ve el progreso del equipo |
| **Empleado** | Aprende, practica, pregunta. La experiencia se adapta a su nivel y ritmo |

## Tipos de contenido

| Tipo | Propósito |
|------|-----------|
| **Curso** | Módulos + ejercicios + evaluación. Camino de aprendizaje estructurado, generado a partir de documentos de empresa |
| **Manual** | Material de referencia. Los empleados lo consultan cuando lo necesitan. Organizado para consulta, no para aprendizaje |
| **Chatbot** | Chatbot por contenido. Los empleados preguntan sobre el material y obtienen respuestas fundamentadas en él |

## Generación de contenido

La vía principal para crear contenido:

- **A partir de documentos** — Sube un PDF, manual o protocolo. Un equipo de agentes de IA extrae temas, diseña una estructura, genera módulos y ejercicios, revisa la calidad y produce un curso + manual. El admin revisa en dos puntos de control antes de que nada llegue a los empleados.

El pipeline de generación es una máquina de estados de LangGraph con 10 nodos, 7 agentes especializados y 2 puntos de control humanos obligatorios. Ver [content-generation.md](/docs/content-generation).

Futuros métodos de generación (no en el MVP):

- Desde conversación — le dices a la IA lo que sabes, ella estructura el curso
- Desde cero — le das un tema y un nivel, genera contenido original
- Desde documentos vivos — cuando los documentos fuente cambian, los cursos afectados se marcan para regeneración

## Ejercicios

Múltiples tipos, definidos por el propio contenido. Ejemplos incluyen tests, casos prácticos, tareas del mundo real ("haz esto y dime si funcionó"), y otros por determinar según evolucione el producto.

Todo ejercicio incluye una explicación que cita el material fuente. Las respuestas se evalúan de forma determinista (test, verdadero/falso, rellenar hueco) o mediante un LLM con rúbrica (caso práctico, diálogo).

## Seguimiento

Los empleados completan cursos. El sistema registra lo que saben hacer:

- Intentos de ejercicio con puntuaciones y marcas de tiempo
- Niveles de habilidad que aumentan cuando se superan ejercicios
- Programación de repetición espaciada para el repaso
- Plazos y estado de inscripción

El admin ve el progreso del equipo, las lagunas de habilidad y las alertas. Cómo se presenta exactamente esto queda abierto — el modelo de datos soporta múltiples vistas.

## Adaptación

SkillNet se adapta en dos niveles:

**Nivel 1 — Generación de contenido (offline, costoso):** El curso se genera una vez a partir de los documentos de empresa. Pero el proceso de generación ya tiene en cuenta la audiencia objetivo: el admin especifica para quién es el curso, y los agentes ajustan los niveles de Bloom, la dificultad de los ejercicios y los ejemplos en consecuencia.

**Nivel 2 — Adaptación de la experiencia (en tiempo real, barato):** Cada empleado ve el mismo curso de forma distinta según su perfil:

- Un principiante recibe más lecciones de teoría y ejemplos guiados
- Un empleado con experiencia salta a los ejercicios y recibe casos prácticos más difíciles
- El agente tutor ajusta sus explicaciones según el historial de conversación y el rendimiento pasado
- La repetición espaciada programa ejercicios de repaso en el momento óptimo

**Nivel 3 — Regeneración adaptativa (futuro, basado en datos):** Después de que un curso lo hayan hecho suficientes empleados, el sistema identifica patrones: qué módulos tienen tasas de aprobado bajas, qué ejercicios son demasiado fáciles o demasiado difíciles, qué temas generan más preguntas al tutor. Estos datos retroalimentan el pipeline de generación para regenerar módulos débiles automáticamente.

| Señal | Qué nos dice | Acción |
|--------|-----------------|--------|
| Tasa de aprobado baja en un módulo | El contenido no es claro o es demasiado difícil | Regenerar el módulo con explicaciones más sencillas |
| Muchas preguntas al tutor sobre un tema | Los empleados no lo entienden solo con el curso | Añadir ejemplos o una lección dedicada |
| Finalización rápida + puntuaciones altas | El contenido es demasiado fácil | Aumentar la dificultad de los ejercicios o añadir un módulo avanzado |
| Curso abandonado en un punto concreto | Fricción o desenganche | Investigar y ajustar esa sección |
| Fallos en la repetición espaciada | La retención es pobre | Ajustar los parámetros de FSRS o añadir refuerzo |

Cómo funciona la adaptación en la práctica queda abierto. El modelo de datos ya captura todas las señales necesarias (exercise_attempts con puntuaciones, marcas de tiempo, logs de chat del tutor, tabla spaced_repetition). No hace falta cambiar el esquema — solo la lógica para actuar sobre los datos.

## Bucle de aprendizaje

El sistema aprende de cada interacción:

```
El empleado hace el curso
    |
    v
Se registran los intentos de ejercicio (puntuación, tiempo, respuesta)
    |
    v
Se actualizan los niveles de habilidad
    |
    v
La repetición espaciada programa el próximo repaso
    |
    v
El chat del tutor registra preguntas y confusiones
    |
    v
El admin ve patrones: lagunas de habilidad, empleados con dificultades, módulos débiles
    |
    v
(Futuro) El sistema marca contenido para regeneración según datos reales
```

El bucle de aprendizaje no forma parte del MVP, pero orienta el desarrollo del producto. Todas las tablas del modelo de datos ya lo soportan: es una restricción de diseño, no una incorporación tardía.

## Contenido vivo

La documentación de la empresa cambia. Las políticas se actualizan, los procedimientos se revisan, aparecen nuevas normativas. SkillNet trata los documentos fuente como algo vivo, no estático:

- Cuando se vuelve a subir un documento, el sistema detecta qué ha cambiado
- Los cursos y manuales afectados se marcan para revisión
- El admin decide si regenerar o mantener la versión actual
- Los empleados ven un indicador de versión para saber si su formación está al día

Así, la formación puede mantenerse sincronizada con el conocimiento de la empresa en lugar de generarse una sola vez.
