# Plan de Podcast Studio agnóstico

> **Estado: plan futuro, no compromiso de implementación inmediata.**

## Objetivo

Tomar Audio Overviews de NotebookLM como referencia de producto para generar podcasts
basados en fuentes, pero implementar la capacidad como una tubería abierta, modular y
configurable. Ningún formato, modelo, proveedor ni número de voces forma parte fija del
núcleo de SkillNet.

## Experiencia de partida

La primera experiencia puede mantener los controles reconocibles de NotebookLM:

- selección de fuentes;
- indicación opcional sobre el enfoque;
- formato;
- duración;
- idioma;
- generación en segundo plano;
- reproducción con transcripción y fuentes asociadas.

NotebookLM es la referencia inicial, no una dependencia ni un límite del producto. Su
documentación pública describe esos controles y la generación de Audio Overviews desde
fuentes: [Generate Audio Overview in NotebookLM](https://support.google.com/notebooklm/answer/16212820).

## Arquitectura

```text
PodcastRequest
  -> SourceGrounder
  -> EditorialPlanner
  -> ScriptGenerator
  -> ScriptReviewer
  -> VoiceRenderer
  -> AudioPostProcessor
  -> PodcastArtifact
```

Cada etapa tiene un contrato propio y puede cambiarse sin modificar las demás. El flujo no
debe llamar directamente a un proveedor desde la lógica de producto.

### Solicitud común

```text
PodcastRequest
  sources
  focus?
  format?
  duration?
  language?
  cast?
```

La solicitud expresa qué resultado quiere la persona. No incluye nombres de modelos,
identificadores de voces ni parámetros particulares de una API.

### Proveedores por capacidad

Un adaptador de voz declara lo que realmente puede hacer:

```text
VoiceCapabilities
  max_speakers
  native_dialogue
  available_voices
  max_input_length
```

El renderizador adapta el plan a esas capacidades:

- una voz disponible: narración;
- dos voces disponibles: conversación;
- más voces disponibles y solicitadas: formato con reparto mayor;
- diálogo nativo: el proveedor recibe el diálogo;
- TTS simple: SkillNet sintetiza intervenciones y construye el resultado.

La ausencia de una capacidad reduce el formato; no impide generar el podcast.

## Calidad del contenido

La mejora principal frente al flujo actual es separar preparación, escritura y revisión:

```text
fuentes -> mapa editorial -> estructura -> guion -> revisión -> audio
```

- El mapa editorial recoge qué ideas deben aparecer y su relación con las fuentes.
- La estructura decide el orden y el desarrollo del episodio.
- El generador escribe el guion para el reparto disponible.
- El revisor detecta falta de fundamento, repetición y diálogo poco natural y solicita una
  corrección antes de sintetizar.

Estas etapas también son reemplazables. Una instalación puede usar el mismo modelo para
todas, modelos distintos o implementaciones locales.

## Configuración

SkillNet ofrece un diseño predeterminado para que la función opere sin configuración
detallada. Como punto de partida:

```text
formato: deep dive
duración: media
idioma: el configurado
reparto: dos voces cuando el proveedor pueda; una cuando no
```

La configuración puede sobrescribirse en el despliegue y en cada generación. Los valores
predeterminados nunca deben convertirse en supuestos internos del pipeline.

## Relación con lo existente

El productor actual ya dispone de grounding, formatos, guion validado, Text-to-Dialogue y
fallback por intervenciones. La evolución debe conservar ese productor detrás del contrato
nuevo y separar progresivamente sus responsabilidades; no requiere descartarlo.

La modalidad sigue generándose bajo demanda y en segundo plano según
[delivery-modalities.md](delivery-modalities.md). El podcast continúa separado del chat,
Realtime y la mascota según
[conversational-modalities.md](conversational-modalities.md).

## Fases

1. Introducir los contratos de solicitud, plan y capacidades sin cambiar el resultado
   actual.
2. Separar mapa editorial, guion y revisión.
3. Adaptar automáticamente el reparto a las capacidades del proveedor.
4. Exponer los controles de fuentes, enfoque, formato, duración e idioma.
5. Mejorar síntesis y acabado mediante módulos opcionales.

## Criterios del diseño

- funciona con uno o varios hablantes;
- ningún proveedor es obligatorio;
- cada etapa puede sustituirse;
- existe una configuración predeterminada utilizable;
- las fuentes se conservan durante la planificación y escritura;
- la generación sigue siendo asíncrona;
- cambiar de proveedor no modifica cursos ni artefactos ya creados.

## No decidido todavía

- proveedores y modelos predeterminados;
- voces concretas;
- parámetros exactos de cada formato;
- controles avanzados de edición;
- coste o límites de generación por instalación.
