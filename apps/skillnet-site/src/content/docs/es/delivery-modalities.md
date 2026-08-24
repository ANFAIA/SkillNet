---
title: "Modalidades de entrega"
order: 34
section: "v2"
---

# Modalidades de entrega y estructura de la experiencia

**Estado:** decisión de arquitectura. La selección invisible de una única experiencia es la
dirección vigente; videojuego y UI libre quedan como extensiones futuras.

## Decisión

Una **modalidad** es el medio completo por el que una persona cursa una experiencia:
web, audio, vídeo y, en el futuro, videojuego. Una **estructura** es la composición dentro
de una modalidad. En web puede ser explicación breve, ejemplo resuelto, práctica,
comprobación o transferencia.

No son pestañas ni opciones que la persona deba gestionar durante el curso. Las preferencias,
el objetivo, el estado pedagógico y las capacidades disponibles forman la entrada privada del
agente. Éste elige una sola experiencia para ese momento. El contrato conceptual es:

```text
LearningExperience
  pedagogical intent
  candidate capabilities
    web structures: bounded slice
    audio?: when preferred and available
    video?: when preferred and available
    game?: future capability
  runtime decision -> one selected experience
```

La web es el fallback primario actual. Las preferencias de audio y vídeo son aditivas como
señales: ambas pueden ampliar el conjunto de candidatos, pero no fuerzan dos salidas ni se muestran
como navegación. La pantalla queda fijada mientras está abierta. Si una selección de media no puede
servirse, el runtime cae a la siguiente variante aprobada y finalmente a web.

## Frontera con OpenUI

OpenUI recibe un subconjunto pequeño de implementaciones compatibles con el intent, el estado
pedagógico, la accesibilidad, las preferencias y las capacidades del cliente. No recibe todo el
catálogo global. El resolver reduce primero el espacio y el agente decide dentro de esa frontera;
el frontend sólo representa el resultado fijado.

No existe un shell con pestañas Web/Audio/Vídeo. El catálogo global puede crecer sin aumentar de
forma proporcional el prompt:

```text
catálogo global -> capacidades/preferencias -> shortlist por intent -> agente runtime
                                                               -> una experiencia
```

La generación del curso prepara contratos pedagógicos, definiciones y bindings que agilizan la
experiencia, pero no adjunta audio o vídeo precreados al curso. Si el agente elige una experiencia
de media, el runtime genera la representación on-time; el productor correspondiente resuelve su
salida y el fallback permanece aprobado de antemano.

## Generación on-time

Audio y vídeo no se descubren consultando la biblioteca de artefactos del curso y tampoco forman
parte del schema del curso. La selección server-side pasa por la misma autorización de nodo y
matrícula que el render web. El endpoint de modalidad es infraestructura interna; no constituye
una acción ni un selector expuesto al alumno.

La infraestructura de media persiste el resultado final como caché para polling, reintentos
y reutilización tras recargar. Esa fila es un detalle interno del runtime: no es
un bloque de autoría, no aparece como decisión pedagógica y no permite que el reproductor
mezcle resultados del panel general del curso.

## Preferencias versionadas

El contrato v3 separa:

- `web_presentation`: `balanced | text | visual | data`;
- `modalities`: conjunto de `audio | video`;
- `interaction`, `detail` e `images`: ajustes de la estructura web.

Los valores v1 y v2 se normalizan a v3. El antiguo valor único `audio` se migra a
`modalities=[audio]` y deja la presentación web en `balanced`.

## Artefactos intermedios compartidos

No se introduce ahora una capa de artefactos intermedios compartidos entre modalidades.
Cada productor conserva su definición inmutable y su binding. Esta decisión evita acoplar
prematuramente audio, vídeo y web a un formato común que todavía no tiene casos suficientes.
Se podrá añadir más adelante detrás de un contrato de entrada versionado, sin cambiar
`LearningExperience` ni la frontera del reproductor.

## Extensión futura: UI libre y videojuego

El nivel 3 no será "añadir cientos de componentes al prompt". Será una implementación
genérica, por ejemplo `sandboxed.generated-ui@1`, seleccionable por el mismo binding que
cualquier otra experiencia. Su política de generación on-time o anticipada deberá ser
explícita; en ambos casos se sirve como salida inmutable y aislada.
No está registrado ni permitido actualmente.

Antes de activarlo deberá cumplir como mínimo:

- ejecución aislada, sin cookies ni red por defecto;
- manifiesto explícito de capacidades y límites de CPU, memoria y tiempo;
- digest, procedencia y versión inmutables;
- puerto de evidencia normalizada hacia mastery, sin escrituras directas;
- accesibilidad verificable y navegación por teclado;
- fallback a una experiencia estructurada si falla validación o ejecución;
- política de revisión y publicación equivalente a las demás definiciones.

Un videojuego será otra modalidad o implementación que use ese contrato, no una excepción
en el agente OpenUI. Esto permite evolucionar de componentes cerrados a experiencias libres
sin romper intent, evidencia, historial, personalización ni fallback.

## Fuera de alcance ahora

- generar videojuegos;
- ejecutar código generado libremente;
- compartir guiones o representaciones intermedias entre productores;
- mostrar un selector Web/Audio/Vídeo al alumno;
- obligar a producir audio o vídeo sólo por ser preferencias del usuario;
- usar la biblioteca de artefactos generales del curso como fuente del reproductor.
