---
title: "Futuro: prerrequisitos"
order: 35
section: "v2"
---

# Futuro: gestión de prerrequisitos para el alumno

> Estado: idea, no planificada. Se documenta para cuando se revise la experiencia del alumno en runtime.

## Comportamiento actual

Cuando un nodo del curso tiene prerrequisitos, el alumno no puede acceder a él hasta que los
nodos prerrequisito estén completados. El sistema bloquea el acceso por completo.

## Alternativa propuesta

En lugar de bloquear, ofrecer al alumno una elección al llegar a un nodo con prerrequisitos
incumplidos:

1. **"Ya sé esto"** — El alumno marca los prerrequisitos como conocidos y los omite.
   El sistema podría verificarlo opcionalmente con una comprobación rápida (los elementos de
   comprobación ya existen en el modelo de nodo).

2. **"Quiero aprenderlo primero"** — El sistema genera un minicurso al vuelo
   que cubre los temas prerrequisito. Esto usa el mismo pipeline de render en runtime
   (POST /nodes/{id}/render) pero acotado sólo a los nodos prerrequisito.

3. **"Muéstrame un resumen"** — Una versión condensada de los prerrequisitos, no un curso
   completo. Contexto suficiente para continuar sin recorrer el camino de prerrequisitos entero.

## Por qué

- Un dueño de panadería que ya conoce la seguridad alimentaria no debería sentarse a ver lo
  básico porque el DAG lo diga así.
- Un empleado nuevo que de verdad no lo sabe debería recibir ayuda, no sólo un muro.
- Distintos alumnos tienen distintos puntos de partida. El grafo de prerrequisitos debería ser
  una guía, no una puerta cerrada.

## Dependencias

- El modelo de DAG de prerrequisitos se mantiene tal cual (sigue definiendo el orden
  recomendado).
- El sistema de comprobación (`course_nodes.probe_items`) podría servir como verificación de
  "¿ya sabes esto?".
- El pipeline de render en runtime ya genera contenido por nodo bajo demanda, así que generar
  un minicurso es simplemente renderizar los nodos prerrequisito.

## Preguntas abiertas

- ¿Debería "ya sé esto" requerir pasar una comprobación, o basta con la palabra del alumno?
- ¿Debería el admin poder configurar esto por curso (prerrequisitos estrictos frente a
  flexibles)?
- ¿Cómo afecta esto al seguimiento de mastery y a las métricas de finalización?
