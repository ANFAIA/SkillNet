# Modo degradado: exponerlo en la interfaz

**Estado:** implementado (2026-08-26). Este fichero describe lo que hay en el código.
**Relacionado:** [`onboarding.md`](onboarding.md) §2, [`media-artifacts.md`](media-artifacts.md) §5,
[`configuration.md`](configuration.md), [`security.md`](security.md)

> SkillNet degrada de formas concretas cuando falta una clave externa o el proveedor
> devuelve cuota. Esas degradaciones eran **invisibles**: la interfaz aceptaba el trabajo,
> lo ejecutaba y treinta segundos después enseñaba la excepción cruda del proveedor. Ahora
> cada capacidad dice en qué estado está y por qué, y quien mira decide.

## 1. Tres estados, no dos

Una capacidad ya no es un booleano. Es `{status, reason, hint}` con
`status ∈ {ready, degraded, blocked}` (`src/schemas/capabilities.py`).

| Estado | Qué significa | Qué hace la interfaz |
|---|---|---|
| `ready` | Funciona | Nada especial |
| `degraded` | Funciona con menos | Deja lanzarlo y avisa de que va a salir reducido |
| `blocked` | No puede funcionar | Control visible, inerte y con el motivo |

La distinción no es cosmética. El podcast lleva la voz offline de eSpeak al final de su
cadena (`src/services/media/podcast/voices.py`), así que `tts` **degrada y nunca bloquea**:
apagar el botón quitaría algo que hoy funciona. `images`, en cambio, sí bloquea — decisión
deliberada del producto, ver §4.

`reason` es un enum (`missing_api_key`, `not_configured`, `provider_quota`,
`provider_down`), nunca una frase: el texto lo pone i18n en el cliente.

## 2. De dónde sale: configuración y runtime

`derive_capabilities()` (`src/services/capabilities.py`) cruza dos capas:

- **Configuración**, pura: lee `settings`, no llama a nadie, no puede fallar. Es lo que
  permite servirla en un endpoint público.
- **Runtime**: `src/services/provider_health.py`, un registro en memoria con TTL que las
  rutas de fallo reales alimentan (429/402 → `quota`, lo demás → `down`). Solo puede
  **empeorar** el estado, nunca mejorarlo, y se cura solo al expirar el TTL.

Suposición de un solo worker, la misma que ya hace `_INFLIGHT` en `node_render_service`.
Es una pista para la interfaz, no una fuente de verdad: perderla al reiniciar es correcto.

No hay sondas activas contra el proveedor. Gastan cuota y mienten igual de rápido.

## 3. Quién ve qué

`GET /setup/status` es **público y previo a la autenticación**. Lleva `status` y `reason`;
`hint` viaja siempre a `null`. Nombrar la variable de entorno que arregla el problema es un
inventario de la configuración del despliegue entregado a un anónimo.

`GET /settings/capabilities` (`src/routes/settings.py`) sirve lo mismo **con** `hint`,
detrás de la dependencia de admin. Una sola derivación, dos audiencias.

En el cliente, el texto también es por rol (`src/lib/capabilityCopy.ts`): al aprendiz se le
dice que no está disponible en esta instalación y nada más — la forma del `.env` no es asunto
suyo y no puede hacer nada con ella; al admin se le da la acción que lo arregla.

## 4. Rechazar en la puerta

`MEDIA_KIND_REQUIREMENTS` (`src/services/media/requirements.py`) declara qué capacidades
necesita cada tipo de medio, y `enqueue_artifact` lo comprueba. Está ahí, en la única puerta
por la que pasan todos los que arrancan un trabajo, y no en la ruta que resulta ser la del
admin: el botón de audio/vídeo del reproductor de lecciones no pasaba por la ruta del estudio.

Solo `blocked` rechaza (409, `code: capability_blocked`); `degraded` pasa. Los que crean
artefactos en modo best-effort (el seed, el orquestador de curso completo) lo capturan y
siguen.

**Decision de producto, no reparación de un fallo:** sin clave de imagen, la infografía y las
slides quedan **bloqueadas**. Antes degradaban a hoja estructurada sin poster (`has_image=false`)
y seguían siendo útiles. Se prefiere no ofrecer lo que no se puede cumplir. Queda escrito aquí
porque es una función que se pierde, no una que se gana.

## 5. Qué ve el aprendiz en un control bloqueado

`<Gated mode="explain">` (`src/components/CapabilityExplain.tsx`) pinta el control **visible
e inerte**:

- **`aria-disabled`, nunca el atributo `disabled`.** `disabled` lo saca del orden de
  tabulación, y un control al que nadie llega es un control cuya explicación nadie lee. Como
  `aria-disabled` no bloquea nada por sí solo, la activación se suprime a mano: el clic, y el
  Enter/Espacio que un botón convierte en clic.
- **La frase vive siempre en el DOM**, en un `sr-only` al que apunta `aria-describedby`. La
  burbuja que sale al pasar el ratón, al enfocar o al tocar es una segunda copia `aria-hidden`.
  Un lector de pantalla no pasa el ratón por encima.
- Sin `z-index`: el envoltorio es `relative` solo mientras está abierta.

El banner de `CapabilityHealthBanner` sigue siendo el resumen a nivel de despliegue y
complementa esto; no lo repite.

## 6. Lo que ya no es cierto de la versión anterior de este documento

- El hueco de la voz del mascota (500 sin clave) **esta cerrado**: `src/routes/tts.py` cae a
  eSpeak y devuelve 204.
- No se amplió `GET /health` ni se creó `GET /settings/media-status`. La información viaja en
  la carga de capacidades.
- No existe `tts.configured` ni el bloque `"media": {...}` que este fichero proponía.
