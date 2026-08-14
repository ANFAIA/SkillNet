# Conversación, voz y acompañamiento

> **Estado: idea futura, no compromiso de implementación.**

## Dirección

SkillNet podrá incorporar varias funciones relacionadas con audio y acompañamiento. Deben
mantenerse separadas para poder mejorarlas o sustituirlas sin acoplar toda la aplicación.

## Audio en el chat

La persona puede enviar un mensaje de audio al chat. SkillNet lo transcribe y el chat
responde en texto.

```text
audio -> transcripción -> chat -> respuesta textual
```

No implica que el chat responda con voz ni que se inicie una conversación en directo.

## Conversación Realtime

Realtime es una función distinta para mantener una conversación por voz en directo. Su
integración debe quedar detrás de una abstracción para no acoplar el resto de SkillNet a
GPT Realtime ni a un proveedor concreto.

## Mascota

La mascota representa visualmente al acompañante de aprendizaje. No debe contener dentro
la lógica del chat, la voz o la lectura de nodos. Recibe señales simples del sistema y su
aspecto puede cambiar sin modificar esas funciones.

La forma concreta de mejorar cómo interpreta y acompaña los nodos queda pendiente de
diseño y validación.

## Podcasts

La generación de podcasts continúa siendo una función separada. Se mejorarán tanto el
estudio de generación como la calidad del resultado, sin convertir el podcast en parte del
chat o de Realtime.

## Relación con los modos de audiencia

Estas funciones pueden formar parte del núcleo común de SkillNet cuando resulten útiles en
un curso. El modo `organization` conserva el enfoque actual de empresa y empleado. El modo
`individual`, si se implementa en el futuro, reutilizará las mismas funciones sin gestión
de empleados o talento.

Este documento no define todavía casos de uso adicionales, flujos de evaluación, memoria,
prioridades de implementación ni comportamiento detallado de interfaz.
