# Modalidades de entrega y estructura de la experiencia

**Estado:** decisión de arquitectura. La separación web/audio/vídeo está implementada;
videojuego y UI libre quedan como extensiones futuras, sin superficie productiva.

## Decisión

Una **modalidad** es el medio completo por el que una persona cursa una experiencia:
web, audio, vídeo y, en el futuro, videojuego. Una **estructura** es la composición dentro
de una modalidad. En web puede ser explicación breve, ejemplo resuelto, práctica,
comprobación o transferencia.

No son alternativas en una sola lista. Elegir una estructura web no puede eliminar audio
o vídeo si la persona los ha pedido. El contrato conceptual es:

```text
LearningExperience
  pedagogical intent
  delivery bundle
    web: runtime structure selected from a bounded slice
    audio?: prepared companion artifact
    video?: prepared companion artifact
    game?: future implementation
```

La web es la modalidad primaria actual. Audio y vídeo son acompañantes acumulables. Las
preferencias declaradas por el usuario son aditivas: puede seleccionar ambas. Si una
modalidad solicitada aún no está preparada, la interfaz la mantiene visible como pendiente;
no la infiere ni la sustituye silenciosamente.

## Frontera con OpenUI

OpenUI compone exclusivamente la **estructura de la modalidad web**. Recibe un subconjunto
pequeño y compatible con el intent, el estado pedagógico, accesibilidad y capacidades del
cliente. No recibe todo el catálogo global y no decide qué modalidades existen.

El shell fijo del reproductor, fuera del programa generado, ofrece audio y vídeo. Así un
fallo, una repetición o una decisión del agente de runtime no puede ocultar una modalidad
preferida. El catálogo global puede crecer sin aumentar de forma proporcional el prompt:

```text
catálogo global -> filtro de modalidad web -> shortlist por intent -> OpenUI runtime
artefactos audio/vídeo ---------------------------------------> shell del reproductor
```

La generación de curso puede dedicar más tiempo a producir definiciones y bindings. El
runtime sólo resuelve referencias ya aprobadas y selecciona una shortlist; no genera audio
o vídeo ni llama a otro modelo para decidir cómo reproducirlos.

## Preferencias versionadas

El contrato v3 separa:

- `web_presentation`: `balanced | text | visual | data`;
- `modalities`: conjunto de `audio | video`;
- `interaction`, `detail` e `images`: ajustes de la estructura web.

Los valores v1 y v2 se normalizan a v3. El antiguo valor único `audio` se migra a
`modalities=[audio]` y deja la presentación web en `balanced`.

## Artefactos compartidos

No se introduce ahora una capa de artefactos intermedios compartidos entre modalidades.
Cada productor conserva su definición inmutable y su binding. Esta decisión evita acoplar
prematuramente audio, vídeo y web a un formato común que todavía no tiene casos suficientes.
Se podrá añadir más adelante detrás de un contrato de entrada versionado, sin cambiar
`LearningExperience` ni la frontera del reproductor.

## Extensión futura: UI libre y videojuego

El nivel 3 no será “añadir cientos de componentes al prompt”. Será una implementación
genérica, por ejemplo `sandboxed.generated-ui@1`, seleccionable por el mismo binding que
cualquier otra experiencia. Se genera en design-time y se sirve como artefacto inmutable.
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
- permitir que OpenUI seleccione o suprima modalidades;
- añadir audio/vídeo a la shortlist web sólo por ser preferencias del usuario.
