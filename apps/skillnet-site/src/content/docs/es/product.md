---
title: "Producto"
order: 21
section: "start"
---

# Producto

> **Estado: base actual y dirección de producto.** Este documento separa el comportamiento
> implementado del trabajo posterior.
>
> La configuración admite espacios de organización e individuales. Sus límites de producto y
> evolución futura se definen en [audience-modes.md](/docs/audience-modes).

---

## Qué es SkillNet

SkillNet convierte una idea o conocimiento existente en formación fundamentada y trazable que puede
tomar formas distintas según el perfil y el estado de quien aprende.

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
| **Empleado** | Aprende, practica y pregunta. La experiencia puede responder a su perfil, estado actual y necesidades de apoyo |

## Superficies actuales de aprendizaje

| Superficie | Propósito |
|------|-----------|
| **Curso** | Módulos + ejercicios + evaluación. Camino de aprendizaje estructurado, generado a partir de documentos de empresa |
| **Tutor del curso** | Tutor asociado a un curso o matrícula. Recupera material para preguntas específicas y puede responder preguntas generales sin citas del curso |
| **Medios generados** | Podcasts, infografías, presentaciones y vídeos narrados de diapositivas cuando están configurados los proveedores necesarios |

## Generación de contenido

Vías actuales de creación:

- **Desde documentos** — sube PDF, DOCX, Markdown o TXT y genera un curso fundamentado.
- **Desde una idea** — SkillNet crea una fuente generada por el modelo, claramente marcada y con
  procedencia, y construye desde ella. No equivale a fundamentarse en material de empresa subido.
- **Desde clientes externos** — la web y `/ext/v1` usan los mismos servicios. Los adaptadores
  opcionales A2A y MCP llaman a `/ext/v1` cuando se habilitan sus perfiles de Compose.

El pipeline estático v1 y el esquema dinámico v2 conviven, y la entrega se decide por curso. Los
esquemas dinámicos pasan por propuesta, revisión de nodos y validación antes de llegar al aprendiz.
Ver [alcance v1](/docs/course-scope), [cursos dinámicos](/docs/dynamic-courses) y [diseño de cursos
con IA](/docs/ai-course-design).

## Ejercicios

El propio contenido define distintos tipos, como tests, casos prácticos y tareas del mundo real
("haz esto y dime si funcionó").

A los ejercicios cerrados generados se les pide una explicación. Las actividades dinámicas de
Didact conservan referencias de fuente controladas por el servidor. La cobertura de citas todavía
no es universal en los ejercicios v1. Las respuestas se evalúan de forma determinista (test,
verdadero/falso, rellenar hueco) o mediante un LLM con rúbrica (caso práctico, diálogo).

## Seguimiento

Las personas completan cursos. El sistema registra la evidencia que realmente puede observar:

- Matrículas y progreso del curso
- Finalización y dominio de nodos
- Intentos de ejercicios y actividades
- Eventos de aprendizaje y la experiencia que vio la persona
- Niveles de habilidad registrados desde el dominio del curso o mediante verificación explícita

Las superficies de talento muestran personas, cursos asignados, progreso y habilidades registradas
con sus cursos de origen. Finalización, dominio y habilidad permanecen como afirmaciones distintas.
El linaje completo desde una habilidad hasta intento, material renderizado y fuente sigue en curso.

## Adaptación

SkillNet separa el contrato estable del curso de la experiencia que recibe una persona.

**Entrega estática:** el Markdown generado y los ejercicios siguen siendo el camino de compatibilidad.

**Entrega dinámica:** un esquema validado puede producir episodios por nodo usando conocimiento
fundamentado, perfil, estado actual y un catálogo aprobado de componentes. El runtime controlado
puede variar explicación, ejemplo, actividad, apoyo, medio e interfaz sin cambiar el objetivo ni la
evidencia exigida. Entradas equivalentes pueden compartir un render; los episodios adaptativos y la
revisión multiagente son opcionales y están desactivados por defecto.

**Memoria del aprendiz:** la memoria editable personaliza hoy el tutor. La generación de lecciones
usa preferencias declaradas, estado y proyecciones acotadas de eventos. Usar la memoria libre para
dirigir renders compartidos sigue siendo trabajo futuro. Es algo distinto de la intención inmediata.

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
Tutor y explicaciones específicas recuperan contexto del curso
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
- Los cursos afectados se marcan para revisión
- El admin decide si regenerar o mantener la versión actual
- Los empleados ven un indicador de versión para saber si su formación está al día

Así, la formación puede mantenerse sincronizada con el conocimiento de la empresa en lugar de generarse una sola vez.
