# Artefactos multimedia

**Estado:** en producción (podcast e infografía integrados en el episodio; slides y vídeo
generables)
**Relacionado:** [`personalization.md`](personalization.md),
[`podcast-studio-plan.md`](podcast-studio-plan.md),
[`llm-integration.md`](llm-integration.md), [`backend-api.md`](backend-api.md)

> Un **artefacto multimedia** es una pieza de medios generada y *grounded* en el contenido de
> un curso: un podcast (audio overview), una infografía, una baraja de diapositivas o un vídeo
> narrado. Se generan de forma asíncrona, se guardan por organización y algunos se inyectan
> dentro del episodio como componentes de la UI cuando la preferencia del aprendiz los pide.

## 1. Los cuatro generadores

Todos bajo `src/services/media/`. Cada uno declara su `MediaKind`, emite pasos por SSE y
persiste un `spec_json` con citas.

| Generador | `MediaKind` | Qué produce | Fichero |
|---|---|---|---|
| Podcast | `PODCAST` | Audio overview a una o dos voces: bundle grounded → guion validado → un mp3 | `podcast/generator.py` |
| Infografía | `INFOGRAPHIC` | Póster vertical estilo NotebookLM (PNG): agente de contenido → modelo de imagen | `infographic/generator.py` |
| Slides | `SLIDES` | Baraja de diapositivas (bloques del kit por slide) + una ilustración apaisada por slide | `slides/generator.py` |
| Vídeo | `VIDEO` | Slides narradas servidas como HTML (no un modelo de vídeo generativo): deck → narración por slide → un mp3 por slide | `video/generator.py` |

Detalles grounded:

- **Podcast** (`podcast/generator.py`): pipeline `grounded bundle → script → voices → mp3`.
  Pasos SSE `guion`/`voz`/`listo`. `spec_json` lleva `turns` con `citation_ids` por turno; el
  `data` es el mp3. Runtime por defecto para el ámbito de curso subido a 600 s.
- **Infografía** (`infographic/generator.py`): dos etapas (agente de contenido con hechos como
  datos, luego modelo de imagen), tamaño `1024x1536`. La imagen es *best-effort*: si falla,
  degrada a spec sin imagen (`has_image=False`). Pasos `datos`/`imagen`/`listo`.
- **Slides** (`slides/generator.py`): deck validado + una ilustración por slide (`1536x1024`,
  portada `1024x1024`), guardadas en `AssetStore` y referenciadas por hash de contenido
  (`image_ref`/`image_ext`). Ilustraciones best-effort por slide; portada decorativa opcional.
- **Vídeo** (`video/generator.py`): "narrated slides shipped as HTML, never a real generative
  video model". Tres etapas (deck → una línea de narración por slide → un mp3 por slide vía la
  ruta TTS del podcast). No se une nada en un fichero de vídeo: el front encadena los clips.

## 2. Ruta `src/routes/media.py`

Router bajo `/media`.

| Método | Ruta | Devuelve | Notas |
|---|---|---|---|
| POST | `/media/artifacts` | `202 {artifact_id, status}` | Encola un job. Permiso vía `can_generate_artifacts`. La fila se hace commit antes de lanzar la tarea |
| GET | `/media/artifacts` | `list[MediaArtifactRead]` | Query `course_id` (obligatorio), `node_id`, `include_nodes`. Tres formas: un nodo / todos los del curso / solo nivel-curso |
| GET | `/media/artifacts/{id}` | `MediaArtifactRead` | Uno |
| GET | `/media/artifacts/{id}/stream` | SSE | Canal `media:{id}`; eventos `media_step` y terminal `media_done`/`media_error` |
| GET | `/media/artifacts/{id}/asset` | bytes | El asset renderizado o 404 |
| GET | `/media/artifacts/{id}/asset/{ref}` | bytes | Un sub-asset por hash de contenido (`ref` debe ser un sha256 que el spec liste) |

### Ámbito (scope) y nota de personalización

- **Scope** — enum `MediaScope` en `src/schemas/media.py`: `NODE="node"`, `COURSE="course"`,
  `STANDALONE="standalone"`. El contrato se valida: `node` exige `node_id`; `course` y
  `standalone` no pueden llevarlo. Se resuelve en la ruta y se escribe en `spec["scope"]`.
- **Nota de personalización** — `body.note` se pliega en `spec["note"]` y siembra el `prompt`
  (y el `query` cuando es standalone). Para empleados se persiste *verbatim* en la memoria del
  aprendiz (`_remember_media_steering`, best-effort):
  `Pidió enfoque: «...» al generar {kind}`.

## 3. Modelos de datos

**`src/models/media_artifact.py`** — org-scoped, no por usuario.

- `MediaKind`: `PODCAST, SLIDES, INFOGRAPHIC, VIDEO, MINDMAP, REPORT, COVER_IMAGE`.
- `MediaArtifactStatus`: `PENDING → RUNNING → DONE | ERROR` (el runner recorre
  `pending → running → done|error`; nótese que el estado de fallo es `error`, no "failed").
- Campos: `org_id`, `course_id`, `node_id` (nullable), `kind`, `status`, `spec_json` (JSONB),
  `asset_path` (nullable), `content_hash` (sha256, clave de dedup), `error`. **No hay columna
  `scope`**: el ámbito vive dentro de `spec_json`.

**`src/models/course_artifact_generator.py`** — tabla `course_artifact_generators`, PK
compuesta `(course_id, user_id)`. Registra *quién*, además de los admins, puede generar medios
a nivel de curso. No lleva enums de kind/status/scope.

## 4. Los componentes in-lesson y el broker

`src/agents/runtime/media_broker.py` decide si un artefacto se convierte en componente dentro
del episodio. `MEDIA_COMPONENT_BY_KIND` mapea `PODCAST → "PodcastPlayer"` e
`INFOGRAPHIC → "InfographicImage"` (los dos componentes *broker-scoped* del kit — ver
[`didact-components.md`](didact-components.md)).

La inyección exige **tres condiciones a la vez**:

1. **Artefacto READY** — `ready_media_for_node` solo devuelve filas `status == DONE`, de kind
   PODCAST/INFOGRAPHIC, org-scoped, la más reciente gana, y descarta filas sin `asset_path`.
2. **La modalidad del aprendiz coincide** — `gate_offers` es un filtro puro: `podcast` solo si
   `_prefers_audio(prefs)`, `infographic` solo si `_prefers_visual(prefs)` (ver
   [`personalization.md`](personalization.md) §2).
3. **Está grounded** en el contenido del nodo.

Cuando pasa el filtro, `offers_prompt_addendum` inyecta una lista blanca *grounded* en el
prompt: "existe material multimedia ya generado y verificado, elegido porque coincide con la
preferencia de modalidad de este aprendiz... Usa EXACTAMENTE el artifact_id indicado (nunca lo
inventes ni lo modifiques)", y emite firmas como `PodcastPlayer("{artifact_id}", "{title}")` /
`InfographicImage("{artifact_id}", "{title}")`. La oferta **solo ensancha** lo que se puede
emitir: no debilita la validación. Su huella entra en la clave de render, de modo que un
aprendiz con medios habilitados obtiene un render distinto.

## 5. Proveedores: cadena TTS y modelo de imagen

**TTS** (`src/services/media/podcast/voices.py`) — "richest first, ending in an offline safety
net". `_build_fallback_chain`:

1. **ElevenLabs** (Text-to-Dialogue, una llamada → un mp3), `model_id = PODCAST_DIALOGUE_MODEL`
   (`"eleven_v3"`), voces `PODCAST_VOICE_A`/`_B`. Proveedor configurado por `TTS_PROVIDER`
   (default `"disabled"`).
2. **Azure AI Speech** — solo si región + endpoint + clave configurados; voces
   `es-ES-AlvaroNeural` / `es-ES-ElviraNeural`.
3. **eSpeak NG offline** — "no key, no quota, always last"; voces `es+m3` / `es+f3`.

Entrada pública `synthesize_podcast`: caché → diálogo → fallback. Si el TTS no está
disponible, la resolución de modalidad degrada audio → texto (`fallback_reason="tts_disabled"`).

**Modelo de imagen** (`src/services/media/images.py`) — `generate_image` vía litellm; primario
`IMAGE_MODEL = "openrouter/google/gemini-2.5-flash-image"` (la "Nano Banana" de NotebookLM vía
OpenRouter), fallback `IMAGE_FALLBACK_MODEL = "gpt-image-1"` (un intento). Claves: `openrouter/*`
usa `OPENROUTER_API_KEY`, en otro caso `LLM_API_KEY`. Sin clave la imagen es *best-effort*:
degrada a `has_image=False` (infografía sin póster) sin romper el trabajo.

### Dependencia de claves y "baked at seed time"

Dos consecuencias prácticas de esta cadena, importantes para demos y para el UX:

1. **La calidad del audio/imagen es la de las claves de quien corrió el seed.** Los artefactos
   (podcast mp3, póster PNG) se generan **en el seed**, se guardan direccionados por contenido
   en `data/media_assets` y se sirven a **todos** los aprendices desde almacenamiento; no se
   regeneran por usuario. Un aprendiz sobre una BD ya sembrada oye/ve lo que se generó entonces.
2. **Hueco conocido en la voz en vivo del mascota.** A diferencia del podcast (que degrada a
   eSpeak offline), la ruta `POST /api/v1/tts/synthesize` **falla en duro con 500** cuando
   ElevenLabs no tiene clave/crédito — no cae al proveedor offline. El frontend ya lo traga en
   silencio (`MascotaCompanion.tsx`), pero la superficie de admin/settings no lo indica.

El plan para exponer estos estados degradados en la interfaz (banner de admin, `/health`
ampliado, onboarding) está en [`degraded-mode-ux.md`](degraded-mode-ux.md).
