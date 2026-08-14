# Direcciones futuras acordadas

> **Estado: índice de ideas y planes de producto surgidos en la conversación.** No es un
> roadmap fechado ni convierte estas direcciones en alcance de la versión actual.

## 1. Ampliar la audiencia sin dividir el producto

Un único SkillNet descargable con dos modos futuros:

- `organization`: empresa, clase, academia, equipo u otro grupo con responsable y
  participantes;
- `individual`: una persona administra su espacio y estudia sus propios cursos, sin
  empleados ni funciones de talento.

`class` no es un tercer modo y `user` no se usa como nombre de modo. El producto actual de
empresa y empleado se conserva. Diseño completo:
[audience-modes.md](audience-modes.md).

## 2. Producto horizontal y marketing vertical

SkillNet puede cubrir varias audiencias con el mismo núcleo y mantener campañas o landings
distintas para empresa, clases e individual. Las verticales cambian el mensaje y los
ejemplos, no crean aplicaciones diferentes.

La web comercial no es una prioridad actual. Cuando se retome, la última dirección visual
acordada es más minimalista, con imágenes y movimiento que dé vida al scroll, evitando que
la propuesta dependa de capturas de pantalla. Esta dirección aún no tiene un diseño final.

Si se construye con Astro, será un único sitio con componentes compartidos y páginas por
audiencia, no un proyecto o fork distinto para cada vertical.

Referencia de producto y storytelling:
[audience-modes.md](audience-modes.md).

## 3. Sustituir y mejorar la mascota

La mascota actual se cambiará en el futuro. Debe ser una capa visual sustituible y no
contener dentro la lógica de chat, voz o lectura de nodos.

También queda pendiente mejorar cómo comprende el estado del nodo y cuándo interviene,
porque el comportamiento actual no funciona bien. La solución concreta debe validarse
antes de fijarla. El acompañante de Brilliant puede servir como referencia puntual para
investigar ese comportamiento, no como dirección general para los cursos.

Frontera acordada:
[conversational-modalities.md](conversational-modalities.md).

## 4. Podcast Studio con calidad tipo NotebookLM

Partir de la experiencia de Audio Overviews: fuentes, enfoque, formato, duración, idioma,
generación en segundo plano, transcripción y referencias. La implementación será agnóstica,
modular y configurable.

El diseño predeterminado puede usar dos voces, pero funcionará con una o más según las
capacidades del proveedor. Grounding, planificación editorial, guion, revisión, voces y
acabado serán etapas sustituibles.

Plan completo: [podcast-studio-plan.md](podcast-studio-plan.md).

## 5. Audio como entrada del chat

La persona podrá enviar una nota de voz al chat. SkillNet la transcribe y responde en
texto. No activa TTS ni abre una llamada.

```text
audio -> transcripción -> chat -> texto
```

Frontera acordada:
[conversational-modalities.md](conversational-modalities.md).

## 6. Conversaciones de voz en directo

Realtime será una función distinta para conversar por voz. Aunque GPT Realtime sea una
opción, la integración debe permanecer detrás de una abstracción para admitir otros
proveedores.

Todavía no se han fijado su interfaz, casos de uso concretos ni prioridad de
implementación. Frontera acordada:
[conversational-modalities.md](conversational-modalities.md).

## 7. Separación de modalidades

Web, audio y vídeo son modalidades acumulables y no variantes excluyentes de una pantalla.
La generación multimedia permanece bajo demanda y separada de la composición OpenUI.

Diseño de arquitectura:
[delivery-modalities.md](delivery-modalities.md).

## Resumen de estado

| Dirección | Estado |
|---|---|
| `organization` e `individual` | Dirección documentada; no implementada |
| Marketing vertical y nuevas landings | Futuro; sin diseño final |
| Nueva mascota y mejor lectura del nodo | Dirección definida; solución pendiente |
| Podcast Studio agnóstico | Plan documentado |
| Audio en chat con respuesta textual | Comportamiento acordado; futuro |
| Conversación Realtime agnóstica | Dirección acordada; futuro |
| Modalidades web/audio/vídeo | Arquitectura documentada; implementación parcial |

Este índice debe actualizarse cuando una dirección se descarte, cambie o pase a una fase de
implementación. No debe utilizarse como lista automática de funcionalidades prometidas.
