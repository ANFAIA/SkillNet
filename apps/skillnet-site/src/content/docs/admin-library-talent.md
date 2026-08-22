---
title: "Biblioteca y talento (admin)"
order: 19
section: "extensibility"
---

# Biblioteca administrativa y registro de talento

**Estado:** decisión de producto e implementación inicial
**Ámbito:** organización de cursos y trazabilidad básica de formación
**Fuera de alcance:** personalización, puestos, recomendación de candidatos y grafos de competencias

## Objetivo

SkillNet separa dos preguntas administrativas:

- **Biblioteca:** qué cursos tiene la organización y cómo se encuentran.
- **Talento:** qué cursos tiene asignados o completados cada persona y qué habilidades ha obtenido.

Esta primera versión es deliberadamente registral. No pretende inferir rendimiento laboral ni
decidir si una persona es adecuada para un puesto.

## Biblioteca

Los cursos pueden pertenecer a una carpeta administrativa opcional. Las carpetas son planas en la
primera versión y no controlan permisos, generación, publicación ni matrícula.

La pantalla de contenido ofrece:

- búsqueda por título o descripción;
- filtro por carpeta y estado;
- vistas virtuales «Todos» y «Sin organizar»;
- creación, renombrado y eliminación segura de carpetas;
- traslado de un curso entre carpetas.

Una carpeta que contiene cursos no se elimina implícitamente ni elimina sus cursos.

## Habilidades del curso

Durante la pregeneración del esquema, la misma respuesta rápida que propone sus nodos devuelve entre
dos y seis habilidades observables del curso. Una habilidad se expresa como una acción («Configurar
una taquilla»), no como un tema («Taquilla»).

Las sugerencias son editables y no crean taxonomía hasta que el administrador confirma el curso. Al
persistirlas:

1. se reutiliza una habilidad existente de la organización cuando coincide su nombre normalizado;
2. se crea una nueva cuando no existe;
3. se reemplaza atómicamente la relación `course_skills` del curso.

En esta fase las habilidades pertenecen al curso, no a nodos individuales. `course_nodes.skill_id`
se conserva por compatibilidad, pero no forma parte de este flujo de producto.

## Registro de talento

La finalización del curso concede al usuario sus `course_skills` mediante el mecanismo existente de
`user_skills`. La interfaz inicial puede presentar la posesión de la habilidad sin convertir los
niveles internos `low | medium | high` en una afirmación de medición precisa.

El administrador puede consultar:

- **Personas:** asignados, en curso, completados, progreso y habilidades.
- **Detalle de persona:** cursos con estado/progreso y habilidades con su curso de procedencia cuando
  el origen sea una finalización.
- **Cursos:** participantes y estado agregado.
- **Habilidades:** personas y cursos relacionados.

No se añade un segundo sistema de progreso. Talento proyecta inscripciones, progreso dinámico y
`user_skills` existentes.

## Límites arquitectónicos

- Las carpetas organizan cursos; no organizan ni conceden habilidades.
- Las habilidades describen lo que concede un curso; no modifican la personalización del render.
- Talento es una proyección de datos existentes; no escribe progreso ni mastery.
- Las rutas aplican siempre el ámbito de la organización autenticada.
- La resolución y creación de habilidades vive en el servicio, no en componentes React ni rutas.
- La sustitución de habilidades de un curso es una operación completa y atómica para evitar estados
  parciales.

## Evolución aplazada

Pueden añadirse posteriormente criterios, evidencias, relaciones, vigencia, perfiles de puesto o
consultas explicables. Ninguno de esos conceptos debe anticiparse mediante campos genéricos en esta
versión. Una necesidad futura se modelará como una capa separada sobre el registro actual.
