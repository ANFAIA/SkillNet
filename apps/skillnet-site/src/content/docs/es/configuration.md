---
title: "Configuración"
order: 2
section: "start"
---

# Referencia de configuración

Todas las variables de entorno que lee SkillNet, su valor por defecto y —la parte que es
fácil equivocar— si ponerlas en `.env` cambia algo de verdad.

## La regla que explica casi todas las sorpresas

**`.env` no llega solo a ningún contenedor.** `.dockerignore` lo deja fuera de la imagen y
ningún servicio de ningún fichero compose declara `env_file:`. El `pydantic-settings` de la
API sí dice `env_file=".env"`, pero dentro del contenedor ese fichero no existe.

Así que una variable surte efecto en Docker solo si el servicio que la necesita la lista en
su bloque `environment:`, como `VAR: ${VAR:-valor}`. Compose lee `.env` en la raíz del repo
al hacer `docker compose up` y la interpola ahí. Esa indirección es la razón de que un ajuste
pueda ser real en `src/config.py`, estar documentado, estar bien escrito en tu `.env` y aun
así no hacer nada.

La columna **Llega a Docker** registra exactamente eso, variable por variable:

| Valor | Significado |
|---|---|
| Sí | Está en el `environment:` de un servicio; tu valor de `.env` manda. |
| Solo overlay | Solo llega al contenedor con el overlay o perfil opcional indicado. |
| **No** | Ningún compose la pasa. Ponerla en `.env` no hace nada bajo Docker. |
| Fijada por compose | Compose pone un valor literal; una entrada en `.env` se ignora. |

Una variable marcada **No** sí funciona cuando la API corre fuera de Docker
(`uv run uvicorn …`), porque entonces `pydantic-settings` lee `.env` de verdad. Solo el
camino Docker la descarta.

---

## Obligatorias

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `SECRET_KEY` | placeholder de desarrollo | Firma las cookies de sesión y deriva la clave que cifra las credenciales de proveedor por organización. | Sí |
| `POSTGRES_PASSWORD` | ninguno — compose no arranca | Contraseña de la base de datos. **Solo letras, dígitos, `-` y `_`.** | Sí |
| `LLM_API_KEY` | vacío | Clave del proveedor para generación, tutor y evaluación. Vacía significa cursos vacíos. | Sí |

`POSTGRES_PASSWORD` se interpola en `postgresql+asyncpg://user:PASSWORD@db:5432/db` sin
escapar. Una `@`, `:`, `/`, `#` o `?` parte esa URL, y el error de conexión resultante nunca
menciona la contraseña.

## Modelos y proveedores

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `LLM_MODEL` | `gpt-4o-mini` | Modelo principal en forma litellm, `proveedor/modelo`. Sin prefijo se asume OpenAI. | Sí |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Endpoint para proveedores compatibles con OpenAI. Vacío para los que litellm ya conoce. | Sí |
| `LLM_GENERATION_MODEL` | cae a `LLM_MODEL` | Sustituye el modelo usado solo en la generación de cursos. | Sí |
| `LLM_TUTOR_MODEL` | cae a `LLM_MODEL` | Sustituye el modelo del tutor dentro del curso. | Sí |
| `LLM_EVAL_MODEL` | cae a `LLM_MODEL` | Sustituye el modelo que evalúa las respuestas del aprendiz. | Sí |
| `LLM_RUNTIME_FAST_MODEL` | cae a `LLM_MODEL` | Nivel rápido del router de runtime de v2 para cursos dinámicos. | Sí |
| `LLM_RUNTIME_HEAVY_MODEL` | cae a `LLM_MODEL` | Nivel pesado del router de runtime de v2. | Sí |
| `GEMINI_API_KEY` | vacío | La lee litellm para los modelos `gemini/*`. No es un campo de `src/config.py`. | Sí |
| `VISION_MODEL` | vacío | Modelo multimodal que describe imágenes dentro de PDF subidos. Vacío lo desactiva en silencio. | Sí |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Modelo de embeddings para RAG. Tiene que devolver 768 dimensiones. | Sí |
| `EMBEDDING_BASE_URL` | `https://api.openai.com/v1` | Endpoint cuando los embeddings vienen de otro proveedor que la generación. | Sí |
| `EMBEDDING_API_KEY` | vacío | Clave cuando los embeddings vienen de otra cuenta que la generación. | Sí |
| `EMBEDDING_DIMENSIONS` | `768` | Dimensiones pedidas al proveedor. Tiene que coincidir con la columna. **No la toques.** | Sí |

### El contrato de las 768 dimensiones

`document_chunks.embedding` es `vector(768)`, fijado a mano en la migración 0008. El ORM
declara `Vector()` sin tamaño a propósito, para que la base de datos sea el único sitio donde
vive ese número. `EMBEDDING_DIMENSIONS` no *decide* el esquema: le dice al proveedor cuántas
dimensiones devolver, y tiene que coincidir con la columna o falla cada inserción de chunk.

`services/embedding_check.py` compara ambos al arrancar y publica el resultado en
`GET /health`, porque si no el desajuste aparece por primera vez dentro de un `except` de
ingesta.

Tres casos:

- `text-embedding-3-small` / `-large` aceptan un parámetro `dimensions` y truncan por ti.
  SkillNet lo envía, así que devuelven 768. Nada que hacer.
- Un modelo cuya salida nativa ya es 768 —`nomic-embed-text`, `multilingual-e5-base`,
  `paraphrase-multilingual`— también encaja. Nada que hacer.
- Cualquier otra dimensión (`multilingual-e5-small` son 384, `e5-large` 1024) exige migrar la
  columna y reingerir todos los documentos. Eso no es una edición de `.env`.

## Cuenta propietaria y modo de espacio de trabajo

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `ADMIN_EMAIL` | vacío | Arranque sin navegador: crea la cuenta propietaria al primer inicio. En blanco elige el asistente `/setup`. | Sí |
| `ADMIN_PASSWORD` | vacío | Contraseña de esa cuenta. Se distribuye vacía; este repo no trae ninguna contraseña usable. | Sí |
| `ORG_NAME` | `SkillNet` | Nombre de la organización creada al primer inicio. | Sí |
| `WORKSPACE_MODE` | `organization` | `organization` o `individual`. Se lee solo al crear la organización. | Sí |
| `SETUP_WINDOW_MINUTES` | `30` | Minutos que el `/setup` público sigue abierto tras un arranque sin propietario. `0` quita el límite. | Sí |
| `ONBOARDING_ENABLED` | `true` | Fuerza el asistente de incorporación para aprendices sin perfil completo. | Sí |

`/setup` tiene que ser público —es como se crea la primera cuenta—, así que hasta que exista
un propietario, quien llegue primero se convierte en él. Bien en `localhost`, mal detrás de un
túnel arrancado antes de crear la cuenta. Cuando la ventana se cierra, reinicia el contenedor
`api` para obtener otra, o usa el `X-Setup-Token` que la API escribe en el log al arrancar.

## Servicio, sesiones y exposición

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `PORT` | `3000` | Puerto del host que publica el servicio `web`. No lo usa `docker-compose.dokploy.yml`. | Sí |
| `COOKIE_SECURE` | `false` en la base, `true` en los overlays de exposición | Marca la cookie de sesión como `Secure`. Ver la nota de precedencia abajo. | Sí |
| `SESSION_LIFETIME_SECONDS` | `604800` (7 días) | Cuánto vale una cookie de sesión. | Sí |
| `COOKIE_NAME` | `skillnet_session` | Nombre de la cookie de sesión. | **No** |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Array JSON de orígenes permitidos. Rara vez hace falta: el nginx incluido deja la SPA en el mismo origen. | Sí |
| `FORWARDED_ALLOW_IPS` | `*` | Proxies en los que uvicorn confía para `X-Forwarded-*`. `*` solo es seguro porque `api` no publica puerto. | Sí |
| `ENVIRONMENT` | `production` en compose | `production` activa las comprobaciones de fuerza de `SECRET_KEY`. | Sí |
| `LOG_LEVEL` | `info` | Nivel de log de uvicorn y de la aplicación. | Sí |
| `DEBUG` | `false` | `true` expone Swagger en `/api/docs`; si no, está oculto. | Sí |
| `MAX_UPLOAD_SIZE_MB` | `50` | Tope de subida en la API. nginx corta los cuerpos en 55m fijos, aparte. | Sí |
| `UPLOAD_DIR` | `./uploads` | Dónde se escriben las subidas. | Fijada por compose (`/data/uploads`) |
| `DATABASE_URL` | Postgres local | URL de SQLAlchemy. | Fijada por compose (a partir de `POSTGRES_*`) |
| `POSTGRES_USER` | `skillnet` | Rol de la base de datos, usado por `db` y por la URL que construye compose. | Sí |
| `POSTGRES_DB` | `skillnet` | Nombre de la base de datos, igual. | Sí |
| `DOMAIN` | ninguno | Hostname público para el que Caddy pide certificado. Obligatorio con el overlay caddy. | Solo overlay (`caddy.yml`) |
| `CADDY_EMAIL` | ninguno | Dirección de la cuenta de Let's Encrypt. Obligatoria: vacía es un error de sintaxis del Caddyfile. | Solo overlay (`caddy.yml`) |
| `CLOUDFLARE_TUNNEL_TOKEN` | ninguno | Token de un túnel con nombre creado en el panel Zero Trust de Cloudflare. | Solo overlay (`cloudflared.yml`) |

### `COOKIE_SECURE` y los overlays de exposición

`docker-compose.yml` lee `${COOKIE_SECURE:-false}`, porque la pila por defecto habla HTTP
plano en `localhost` y una cookie `Secure` no volvería nunca.

Los tres overlays de exposición —`docker/compose/caddy.yml`, `cloudflared.yml` y
`quicktunnel.yml`— leen `${COOKIE_SECURE:-true}`, porque cada uno pone TLS real delante.

El valor por defecto de `:-` solo se aplica cuando la variable está **sin definir**. Una línea
activa `COOKIE_SECURE=` en `.env` gana por tanto a los tres overlays, incluido un `false` que
copiaste de un ejemplo y olvidaste. Por eso `.env.example` la deja comentada: déjala así salvo
que quieras específicamente pisar un overlay.

## Iniciar sesión con Google

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | vacío | Client id de OAuth. Vacío desactiva la función entera; `/auth/google/*` responde 404. | Sí |
| `GOOGLE_CLIENT_SECRET` | vacío | Client secret de OAuth. Igual: vacío desactiva la función. | Sí |
| `GOOGLE_REDIRECT_URI` | vacío | URL de callback, comparada literalmente por Google. Vacía la deriva de la petición. | Sí |
| `GOOGLE_POST_LOGIN_PATH` | `/` | Ruta a la que aterriza el navegador tras un inicio correcto. Una ruta, nunca una URL. | Sí |
| `GOOGLE_LOGIN_ERROR_PATH` | `/login` | Ruta para un inicio rechazado, con un parámetro `google_error`. | Sí |

### Qué puede hacer Google, según el modo de espacio de trabajo

Las credenciales encienden la función. Lo que se le *permite* hacer viene del `workspace_mode`
de la organización, no de la configuración (`src/services/google_oauth.py`):

- **organization** — Google solo **inicia sesión** a gente que ya tiene cuenta creada por un
  administrador. Una dirección no invitada se rechaza y no se crea ninguna cuenta. SkillNet
  aísla los datos por organización, así que el registro abierto sería una puerta lateral a los
  datos de una empresa.
- **individual** — Google también puede **crear** la cuenta, porque en un espacio de una sola
  persona no hay nadie que invite.

En ambos modos Google tiene que declarar la dirección como verificada. Una sin verificar se
rechaza: emparejar por una afirmación que Google no respalda entregaría la cuenta a quien
escriba la dirección.

Las credenciales se sacan en <https://console.cloud.google.com/apis/credentials> → "Crear
credenciales" → "ID de cliente de OAuth" → "Aplicación web". Para la pila local por defecto la
URI de redirección es `http://localhost:3000/api/v1/auth/google/callback`; Google compara la
cadena entera, barra final incluida.

## Texto a voz

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `TTS_PROVIDER` | `disabled` | `openai`, `elevenlabs`, `google`, `azure` o `disabled`. | Sí |
| `TTS_API_KEY` | vacío | Clave de ese proveedor. | Sí |
| `TTS_VOICE` | vacío | Id de voz. Vacío elige la voz por defecto del proveedor (Azure: `es-ES-ElviraNeural`). | Sí |
| `TTS_LANGUAGE` | `es` | Idioma de síntesis. | Sí |
| `TTS_TIMEOUT_SECONDS` | `30` | Timeout por petición de síntesis. | Sí |
| `TTS_AZURE_REGION` | vacío | Región de Azure Speech. Nunca se infiere, para que sigan valiendo las nubes soberanas. | Sí |
| `TTS_AZURE_ENDPOINT` | vacío | URL completa del endpoint de síntesis de Azure. Tampoco se infiere. | Sí |
| `TTS_CACHE_DIR` | `data/tts_cache` | Caché direccionada por contenido del audio sintetizado. | Sí (compose la apunta al volumen `tts_cache`) |

Sin una clave que funcione, los dos consumidores degradan de forma distinta. La voz en vivo de
la mascota (`POST /api/v1/tts/synthesize`) falla con 500 y **no** cae a la voz offline; el
frontend se lo traga, así que el aprendiz simplemente no oye nada. La generación de podcast cae
ElevenLabs → Azure → eSpeak NG offline, así que siempre hay podcast, solo que robótico.

El multimedia se hornea en el seed y se guarda direccionado por contenido: los aprendices oyen
la voz que se generó cuando corrió el seed, no un render por usuario.

## Imágenes y artefactos multimedia

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `OPENROUTER_API_KEY` | vacío | Clave que litellm usa para los modelos `openrouter/*`, que son el motor de imagen por defecto. | Sí |
| `IMAGE_API_KEY` | vacío | Clave propia del proveedor de imagen, cuando la cuenta de imagen no es la de texto. | Sí |
| `IMAGE_MODEL` | `openrouter/google/gemini-2.5-flash-image` | Modelo de imagen principal para pósteres, infografías y arte de diapositivas. | Sí |
| `IMAGE_FALLBACK_MODEL` | `gpt-image-1` | Alternativa por llamada, facturada contra `LLM_API_KEY`. | Sí |
| `MEDIA_ASSETS_DIR` | `data/media_assets` | Dónde se guardan los mp3/png/mp4 generados, por hash de contenido. | Sí (compose lo apunta al volumen `media_assets`) |
| `PODCAST_SCRIPT_MODEL` | vacío → `LLM_MODEL` | Modelo del agente de guion del podcast. | **No** |
| `PODCAST_DIALOGUE_MODEL` | `eleven_v3` | Modelo Text-to-Dialogue de ElevenLabs para la voz a dos presentadores. | **No** |
| `PODCAST_VOICE_A` | "Sarah" de ElevenLabs | Id de voz del primer presentador. | **No** |
| `PODCAST_VOICE_B` | "Antoni" de ElevenLabs | Id de voz del segundo presentador. | **No** |
| `SLIDES_MODEL` | vacío → `LLM_MODEL` | Modelo del agente de contenido de diapositivas. | **No** |
| `INFOGRAPHIC_MODEL` | vacío → `LLM_MODEL` | Modelo del agente de contenido de la infografía. | **No** |
| `VIDEO_NARRATION_MODEL` | `gpt-4o-mini` | Modelo que escribe una línea de narración por diapositiva. | **No** |

`MEDIA_ASSETS_DIR` y `TTS_CACHE_DIR` apuntan por defecto a rutas relativas al directorio de
trabajo, que es sistema de ficheros de la imagen. Compose las redirige a `/data/...` para que
los volúmenes con nombre las sostengan; sin eso, cada `--build` tiraba el multimedia generado.

Sin clave de imagen la capacidad se rechaza de entrada con un motivo, en vez de aceptarse y
fallar después.

## Reintentos del proveedor y modelos de razonamiento

Ninguna de estas llega al contenedor. Aparecen porque son ajustes reales que funcionan fuera de
Docker, y porque conviene saber del hueco antes de perder una tarde con él.

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `LLM_MAX_ATTEMPTS` | `5` | Intentos antes de rendirse en una llamada al proveedor. Solo la lee `src/llm/client.py`. | **No** |
| `LLM_RETRY_BASE_SECONDS` | `4.0` | Base del retroceso, usada solo cuando el proveedor no dice cuánto esperar. | **No** |
| `LLM_RETRY_MAX_WAIT_SECONDS` | `90.0` | Techo de una espera. Por encima de un minuto la ventana de TPM ya se reinició. | **No** |
| `LLM_REASONING_EFFORT` | `low` | `none`, `low`, `medium`, `high`. `none` nunca envía el parámetro. | **No** |
| `LLM_REASONING_TOKEN_HEADROOM` | `2048` | Presupuesto extra para un modelo de razonamiento, además del que pidió la llamada. | **No** |

Un modelo de razonamiento factura su cadena de pensamiento contra el mismo `max_tokens` que la
respuesta, así que sin margen puede gastarse el presupuesto entero pensando y devolver contenido
vacío, que el runtime lee como un programa inválido.

## Cursos dinámicos y pipeline de render

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `ADAPTIVE_EPISODES` | `false` | Genera cada nodo dinámico como episodio de dominio anclado, en vez de la fórmula de pantallas antigua. | Sí |
| `MULTI_AGENT_RENDER` | `false` | Usa cuatro agentes especializados en vez de una sola llamada monolítica. | Sí |
| `SEMANTIC_ROUTER` | `false` | Añade una llamada corta de clasificación por delante de las reglas deterministas. | Sí |
| `RENDER_ALLOW_REACTIVE` | `false` | Permite la capa reactiva de OpenUI. El precio de activarla: `docs/design/openui-adoption.md` §3. | **No** |
| `RUNTIME_COMPONENT_SHORTLIST` | `true` | Expone solo los 3-5 candidatos seguros para el renderer al prompt de generación. | **No** |

Un curso se sirve por v2 cuando tiene `delivery_mode='dynamic'` **y**
`schema_status='validated'`. No hay flag global;
`src/services/course_delivery.resolve_delivery` es el único punto de decisión.

## Correr con un modelo local

Las usa `docker/compose/ollama.yml`, que es un overlay y no un perfil porque tiene que
reescribir el entorno de `api`, y un perfil no puede hacer eso.

```bash
docker compose -f docker-compose.yml -f docker/compose/ollama.yml up -d --build
```

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `OLLAMA_LLM_MODEL` | `qwen2.5:7b-instruct` | Modelo de chat que descarga el servicio `ollama` y que se le da a `api` como `ollama_chat/…`. | Solo overlay (`ollama.yml`) |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Modelo de embeddings, dado a `api` como `ollama/…`. Saca 768 dimensiones, así que no hay migración. | Solo overlay (`ollama.yml`) |

Los dos prefijos difieren a propósito. `ollama_chat/…` y `ollama/…` son los proveedores Ollama
nativos de litellm: litellm añade `/api/chat` o `/api/embeddings` por su cuenta, así que la base
URL no lleva `/v1`. Mezclar una base con `/v1` y un prefijo `ollama/` produce un 404.

En CPU esto es lento: unos 185 s para renderizar una pantalla de lección con un modelo de 7B,
medido el 2026-07-27. Útil sin conexión; no cómodo para uso real.

## Servicios opcionales

| Variable | Por defecto | Qué hace | Llega a Docker |
|---|---|---|---|
| `A2A_INTERNAL_API_KEY` | vacío | Clave con la que el servidor A2A llama a `/ext/v1`. Se crea sola en la base de datos si está puesta. | Sí |
| `A2A_AUTH_KEY` | vacío | Token bearer que deben presentar los agentes externos. El servidor no arranca sin él. | Solo perfil (`--profile a2a`) |
| `A2A_LLM_MODEL` | `gpt-4o-mini` | Modelo del orquestador A2A. | Solo perfil (`--profile a2a`) |
| `A2A_PORT` | `5000` | Puerto del host para el servidor A2A, publicado solo en `127.0.0.1`. | Solo perfil (`--profile a2a`) |
| `A2A_AGENT_URL` | `http://localhost:5000` | URL que la tarjeta de agente anuncia a quien la consulte. | Solo perfil (`--profile a2a`) |
| `SKILLNET_MCP_PORT` | `3001` | Puerto del host para el servidor MCP, publicado solo en `127.0.0.1`. | Solo perfil (`--profile mcp`) |
| `SKILLNET_MCP_API_KEY` | vacío | Clave SkillNet por defecto para clientes MCP que no envían su propio `Authorization`. | Solo perfil (`--profile mcp`) |
| `API_FIXTURES_PORT` | `8001` | Puerto del host para el servicio `api-fixtures` sin claves. | Solo perfil (`--profile fixtures`) |

`api-fixtures` comparte `SECRET_KEY` y base de datos con `api`, así que no es un sandbox: sus
cookies de sesión valen contra la API real. Por eso se publica en `127.0.0.1`. El nginx incluido
hace proxy a `api` sin condiciones, así que la SPA nunca lo usa: para dejar toda la pila sin
claves, pon `LLM_MODEL=fixture/local` y `EMBEDDING_MODEL=fixture/local`.

## No las pongas

Están en `src/config.py` y en algún fichero compose, y ponerlas en `.env` o bien no hace nada o
bien es una forma de romper la instalación. Están deliberadamente fuera de `.env.example`.

| Variable | Por qué no |
|---|---|
| `RENDER_BACKEND` | Tipada `Literal["openui"]`, y el registro de backends tiene exactamente una entrada. No hay otro valor válido. |
| `EMBEDDING_DIMENSIONS` | Tiene que ser 768. Cambiarla es una migración más una reingesta; compose ya le pone valor. |
| `LLM_FIXTURE_DIR` | Ruta dentro del paquete instalado (`src/llm/fixture_data`), para que las fixtures viajen en la imagen. |
| `LLM_FIXTURE_MODE` | `replay` (por defecto) o `record`. Solo para desarrollo: `record` llama al proveedor real y escribe los pares a disco. |
| `RUNTIME_SELECTION_STRATEGY` | Dial de investigación. `top5/v1` es el comportamiento del runtime; las demás estrategias están forzadas a sombra. |
| `RUNTIME_SELECTION_EXECUTION` | Dial de investigación, pareja del anterior. `live` es el valor que se distribuye. |
| `DATABASE_URL` | Compose la construye a partir de `POSTGRES_*`. Un valor en `.env` se ignora bajo Docker. |
| `UPLOAD_DIR` | Compose la fija a `/data/uploads`, el volumen montado. Un valor en `.env` se ignora. |

## Relacionado

- `RUNNING.md` — los cinco pasos para arrancar el proyecto.
- `docker-deployment.md` — los servicios y qué hace cada uno.
- `security.md` — el modelo de amenazas detrás de los valores por defecto de arriba.
- `tuning.md` — diales de calidad de generación, casi todos código y no variables de entorno.
