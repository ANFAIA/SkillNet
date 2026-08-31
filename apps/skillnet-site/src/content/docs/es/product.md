---
title: "Producto"
order: 21
section: "start"
---

# Producto

> **Estado: base actual y dirección de producto.** Este documento separa el comportamiento
> implementado del trabajo posterior.
>
> El actual producto orientado a empresa sigue siendo la base implementada. El futuro
> modelo de audiencia para despliegues de organización e individual se define en
> [audience-modes.md](/docs/audience-modes).

---

## Qué es SkillNet

SkillNet convierte una idea o conocimiento existente en formación fundamentada y trazable que puede
tomar una forma distinta para cada persona.

No es solo un catálogo de cursos ni un LMS estático con un chatbot. Lee manuales, procedimientos,
protocolos o una fuente generada, construye el curso y mantiene separada la experiencia del aprendiz
del conocimiento y el objetivo que deben permanecer estables.

Es de código abierto y autoalojado. Un despliegue puede comenzar como espacio de organización o como
espacio individual.

**La idea central:** una misma fuente y un mismo objetivo pueden producir explicaciones, actividades,
medios e interfaces diferentes. El sistema usa el contexto actual y evidencias revisables sobre la
persona; no afirma conocer un estilo de aprendizaje fijo.

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

Vías actuales de creación:

- **Desde documentos** — sube PDF, DOCX, Markdown o TXT y genera un curso fundamentado.
- **Desde una idea** — SkillNet crea una fuente generada con procedencia y construye desde ella.
- **Desde clientes externos** — la web, `/ext/v1`, A2A y MCP usan los mismos servicios de creación.

El pipeline estático v1 y el esquema dinámico v2 conviven, y la entrega se decide por curso. Ver
[alcance v1](/docs/course-scope), [cursos dinámicos](/docs/dynamic-courses) y
[diseño de cursos con IA](/docs/ai-course-design).

## Ejercicios

Múltiples tipos, definidos por el propio contenido. Ejemplos incluyen tests, casos prácticos, tareas del mundo real ("haz esto y dime si funcionó"), y otros por determinar según evolucione el producto.

Todo ejercicio incluye una explicación que cita el material fuente. Las respuestas se evalúan de forma determinista (test, verdadero/falso, rellenar hueco) o mediante un LLM con rúbrica (caso práctico, diálogo).

## Seguimiento

Las personas completan cursos. El sistema registra la evidencia que realmente puede observar:

- Matrículas y progreso del curso
- Finalización y dominio de nodos
- Intentos de ejercicios y actividades
- Eventos de aprendizaje y la experiencia que vio la persona
- Habilidades registradas mediante el trabajo del curso

Las superficies de talento muestran personas, cursos asignados, progreso y habilidades registradas.
Finalización, dominio y habilidad permanecen como afirmaciones distintas.

## Adaptación

SkillNet separa el contrato estable del curso de la experiencia que recibe una persona.

**Entrega estática:** el Markdown generado y los ejercicios siguen siendo el camino de compatibilidad.

**Entrega dinámica:** un esquema validado puede producir episodios por nodo usando conocimiento
fundamentado, perfil, estado actual y un catálogo aprobado de componentes. El runtime puede adaptar
explicación, ejemplo, actividad, apoyo, medio e interfaz sin cambiar el objetivo ni la evidencia
exigida.

**Adaptación a largo plazo:** la memoria puede usar preferencias declaradas y resultados observados
entre sesiones. Es distinta de la intención inmediata y toda hipótesis conservada debe poder
inspeccionarse y corregirse.

**Regeneración adaptativa:** detectar contenido débil entre muchas personas y proponer una revisión
fundamentada sigue siendo trabajo futuro.

## Bucle de aprendizaje

El bucle implementado registra evidencia de cada interacción:

```
La persona hace el curso
    |
    v
Se registran la experiencia y los intentos
    |
    v
Progreso, dominio y habilidades se actualizan con reglas separadas
    |
    v
Tutor y explicaciones usan el contexto fundamentado del curso
    |
    v
El admin ve progreso y habilidades registradas
    |
    v
(Futuro) la evidencia sostiene cambios revisados de experiencia o contenido
```

El registro de eventos está implementado. Demostrar que una adaptación mejora el aprendizaje y
cambiar automáticamente el curso a partir de evidencia agregada son resultados distintos del roadmap.

## Contenido vivo

La documentación de la empresa cambia. SkillNet está diseñado para tratar las fuentes como algo vivo.
El siguiente comportamiento es un horizonte de producto, no el flujo completo disponible hoy:

- Cuando se vuelve a subir un documento, el sistema detecta qué ha cambiado
- Los cursos y manuales afectados se marcan para revisión
- El admin decide si regenerar o mantener la versión actual
- Los empleados ven un indicador de versión para saber si su formación está al día

Así, la formación puede mantenerse sincronizada con el conocimiento de la empresa en lugar de generarse una sola vez.
