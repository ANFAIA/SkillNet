---
title: "Docker y despliegue"
order: 24
section: "core"
---

## 5. Docker y despliegue

**Cómo arrancarlo está en [`README.md`](../../README.md).** Este documento registra *por qué*
el despliegue tiene la forma que tiene, y las trampas que no son obvias leyendo los ficheros.

Antes incluía copias completas de `docker-compose.yml`, ambos Dockerfiles, `.env.example` y
`docker-compose.dev.yml`. Esas copias se desincronizaban: para el 2026-08-04 el healthcheck de
`db` aquí difería del real, el override de dev describía un servicio `web` basado en Vite que
no existe, y dos secciones documentaban un fichero que nunca existió. Un documento de diseño
cuyo cuerpo es una copia obsoleta de la fuente es peor que ningún documento, porque está
seguro de sí mismo y equivocado. Así que los ficheros se enlazan, no se pegan.

- [`docker-compose.yml`](../../docker-compose.yml) — la pila
- [`docker-compose.dev.yml`](../../docker-compose.dev.yml) — capa de hot-reload
- [`docker-compose.ollama.yml`](../../docker-compose.ollama.yml) — capa de modelo local
- [`docker/api.Dockerfile`](../../docker/api.Dockerfile), [`docker/web.Dockerfile`](../../docker/web.Dockerfile), [`docker/nginx.conf`](../../docker/nginx.conf)
- [`.env.example`](../../.env.example) — todas las variables, con el razonamiento en línea

---

### 5.1 Los servicios

| Servicio | Arranca por defecto | Propósito |
|---|---|---|
| `db` | sí | PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`) |
| `api` | sí | FastAPI + uvicorn. Ejecuta `alembic upgrade head` en su lifespan |
| `web` | sí | nginx sirviendo la SPA construida, con proxy inverso de `/api`, `/ext` y `/health` |
| `api-fixtures` | perfil `fixtures` | segunda API que responde desde fixtures grabadas — ver §5.9 |
| `a2a` | perfil `a2a` | servidor agente-a-agente para agentes externos |
| `ollama` | fichero overlay | servidor de modelo local — ver §5.8 |

Los trabajos en segundo plano corren dentro del proceso a través del JobCoordinator
([`background-processing.md`](background-processing.md)), respaldado por PostgreSQL con
persistencia de LangGraph. No hay contenedor worker a esta escala, y añadir uno más adelante
no cambia nada de lo descrito aquí.

**Por qué `web` hace proxy hacia `api` en vez de que la SPA la llame directamente.** Mismo
origen, así que no hay configuración de CORS que estropear; un solo puerto que un admin tiene
que abrir; y un único lugar para la terminación TLS. También significa que nginx es la única
puerta de entrada, que es lo que hace posible el §5.2.

### 5.2 Puertos publicados, y por qué casi ninguno

Un `docker compose up -d` por defecto publica **solo el 3000**. `api` y `db` solo son
alcanzables desde dentro de la red de compose.

Eso no es minimalismo por sí mismo. Las cabeceras de seguridad y el límite de subida de 55 MB
viven en [`docker/nginx.conf`](../../docker/nginx.conf), así que un puerto de `api` expuesto es
una forma de saltarse ambas cosas.

Todo lo opcional se enlaza a `127.0.0.1`. **Docker publica puertos con reglas DNAT que
atraviesan el cortafuegos del host**, tanto en Windows como en Linux, así que un `0.0.0.0:5432`
es un Postgres ofrecido a cualquier máquina de la red sin importar cómo esté configurado el
cortafuegos. Hasta el 2026-08-04 el overlay de dev publicaba `8000` y `5432` exactamente así, y
`api-fixtures` publicaba `8001` — que es peor de lo que parece, porque ese servicio comparte
`SECRET_KEY` y la base de datos con la API real, así que sus cookies de sesión son válidas
contra ella.

`web` en `0.0.0.0:3000` es la única excepción deliberada: es la puerta principal. Nótese que
`COOKIE_SECURE` es `false` por defecto, así que las cookies de sesión viajan sin cifrar por
HTTP plano. Detrás de TLS, ponerlo a `true`.

### 5.3 Las dos fases de la imagen, y la trampa entre ellas

[`docker/api.Dockerfile`](../../docker/api.Dockerfile) construye `builder` (dependencias, `uv`,
root) y `runtime` (venv en el `PATH`, usuario no root `skillnet`, mínimo). El overlay de dev
construye `target: builder` a propósito: el hot reload necesita `uv` y el código montado.

Dos asimetrías mordieron repetidamente y ahora están arregladas:

1. **`uv` solo existía en `builder`, el `PATH` del venv solo en `runtime`.** Así que
   `uv run python -m …` solo funcionaba en desarrollo y `python -m …` a secas solo en
   producción — y el README imprimía una de cada, con tres líneas de diferencia, y ninguna
   válida en ambos. `runtime` ahora copia `uv` también, así que un único comando documentado
   funciona en todas partes.
2. **`PYTHONUNBUFFERED` y `PYTHONDONTWRITEBYTECODE` solo estaban puestos en `runtime`.**
   El desarrollo por tanto perdía todo lo escrito en `stdout` — el log de acceso de uvicorn, y
   cada `print()`, que es como hablan los scripts de seed — y escribía ficheros `.pyc` en el
   árbol de código del host montado como bind mount. Ambas viven ahora en `builder`, de donde
   `runtime` las hereda.

Una sigue abierta: `builder` corre como root, así que el contenedor de dev escribe en tu árbol
de código como root. En Linux y WSL eso deja `__pycache__` y revisiones de alembic propiedad de
root en el repo, que luego rompen `git clean` y el editor. `docker-compose.dev.yml` ya resuelve
la misma clase de problema para `.venv` con un volumen anónimo; el resto del árbol no está
cubierto.

### 5.4 El `.env` solo llega a medias

**Ningún servicio declara `env_file`**, y [`.dockerignore`](../../.dockerignore) mantiene el
`.env` fuera de la imagen, así que el `env_file=".env"` de pydantic no encuentra nada dentro del
contenedor. Solo las variables listadas explícitamente en el bloque `environment:` de un
servicio llegan a la API.

Añadir una variable al `.env` y no ver ningún efecto es por tanto el resultado esperado, no un
bug. La mayoría de diales en [`tuning.md`](tuning.md) son inalcanzables en Docker por esta
razón — para usar uno, añadirlo primero al bloque `environment:` de `api`.

Relacionado, y con la misma causa raíz: los modelos por defecto viven en el fichero compose, no
en `src/config.py`. `${LLM_MODEL:-}` deja la variable *puesta y vacía*, y una cadena vacía gana
al valor por defecto de Python, así que el valor por defecto del código nunca se aplicaba dentro
de Docker. Poner solo `LLM_API_KEY` no arrancaba nada.

### 5.5 Desarrollo frente a producción

```bash
docker compose up -d --build                                                # producción
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build   # hot reload
```

El overlay cambia `api` a `target: builder`, ejecuta uvicorn con `--reload --reload-dir src`,
publica `8000` y `5432` en loopback, y pone `LOG_LEVEL=debug`. **No** sobreescribe `web`; para
trabajar en frontend, ejecutar Vite en el host (`npm run dev` en `apps/skillnet-web`, que hace
proxy de `/api` a `localhost:8000`).

Dos cosas de ese fichero son estructurales y están comentadas como tal:

- **`--build` no es decoración.** El overlay cambia `target`, y sin reconstruir compose reusa
  la imagen `runtime`, cuyo comando no tiene `uv` — el contenedor muere con
  `exec: "uv": executable file not found in $PATH`.
- **El volumen anónimo en `/app/.venv`.** El bind mount del código eclipsa el venv de la imagen
  con el del host, que en Windows y macOS está lleno de binarios ajenos. `uv run` entonces
  decide que el entorno está roto, **lo borra**, y lo reconstruye dentro del contenedor —
  destruyendo el venv desde el que corre la suite de tests del host. Medido, no teórico.

| Aspecto | Desarrollo | Producción |
|---|---|---|
| Política de reinicio | sin fijar | `unless-stopped` |
| Nivel de log | `debug` | `info` |
| Código | montado, `--reload` | horneado en la imagen |
| Puertos publicados | `3000`, más `8000` y `5432` en loopback | solo `3000` |
| Frontend | Vite en el host | nginx sirviendo el build estático |
| Objetivo de build | `builder` (root, tiene `uv`) | `runtime` (no root, mínimo) |
| Flag v2 | `shadow` | lo que diga el `.env` (`on` si se copió del ejemplo) |

**Fuera de compose, y dejado deliberadamente al host:** terminación TLS (poner Caddy, Traefik o
el nginx del host delante; el nginx de SkillNet habla HTTP internamente), rotación de logs
(`logging: driver: json-file` con `max-size: 10m`, `max-file: "3"`), y límites de memoria
(`deploy.resources.limits.memory`). La imagen `builder` es un artefacto de desarrollo — lleva
`uv`, la caché de build y root; nada la marca como no desplegable, así que no enviar el overlay
de dev a un servidor.

### 5.6 Persistencia de datos

Dos volúmenes nombrados: `pgdata` (`/var/lib/postgresql/data`) y `uploads`
(`/data/uploads`, los documentos fuente). Ambos son críticos de respaldar. `docker compose down`
los conserva; `down -v` los destruye.

**Volúmenes nombrados en vez de bind mounts** porque los gestiona Docker y funcionan igual en
Linux, macOS y Windows. Un bind mount como `./data:/data` se rompe en Windows, donde UID y GID
no se mapean y PostgreSQL se niega a arrancar. `docker volume inspect skillnet_pgdata` encuentra
la ruta del host cuando hace falta acceso directo.

Los uploads están organizados como `/data/uploads/{org_id}/{document_id}/`, guardando el
fichero tal como se subió y su texto extraído. Los ficheros y sus filas en `documents` no son
transaccionales entre sí: una fila puede sobrevivir a su fichero, y la ingesta marca el
documento como `error` en vez de fingir lo contrario.

Backup y restauración: [`scripts/backup.sh`](../../scripts/backup.sh) (`pg_dump` a través de
gzip, conservando los últimos siete días). Restaurar con
`gunzip -c backups/skillnet_*.sql.gz | docker compose exec -T db psql -U skillnet skillnet`.
Para un backup completo consistente, primero `docker compose stop api`, luego volcar la base de
datos y empaquetar el volumen de uploads con tar. **Lo que no está prometido:** no hay backups
programados, ni sincronización en la nube, ni recuperación a un punto en el tiempo. Esto es
autoalojado; el operador es el dueño.

**La suite de integración vacía `document_chunks`.** `test_migration_0005` recorre
upgrade → downgrade → upgrade, el downgrade pasa por la migración 0008, y 0008 cambia la
dimensión del vector — no hay forma de conservar vectores de 768 componentes al volver a una
columna de 384. El esquema vuelve correcto; los chunks no. Relanzar el seed.

### 5.7 Primer arranque

El lifespan en [`src/main.py`](../../apps/skillnet-api/src/main.py) crea el directorio de
uploads, ejecuta `alembic upgrade head` (que también crea las extensiones `pgcrypto` y
`vector`), y luego crea la organización y — solo si `ADMIN_EMAIL` y `ADMIN_PASSWORD` están
puestos — el usuario admin y la clave de API A2A.

No crea **ningún** curso, documento o empleado. Un primer login por tanto llega a un dashboard
vacío, que es por lo que cargar los datos de demo es un paso numerado en el README en vez de
una ocurrencia tardía.

No hay asistente de configuración. Un borrador anterior de este documento describía `/setup` y
`GET /api/v1/setup/status`; ninguna de las dos rutas se registró nunca en `src/main.py`. El
arranque sin interfaz reemplazó la idea y la sección sobrevivió a ella.

El arranque también verifica que `EMBEDDING_DIMENSIONS` coincide con la columna real
([`embedding_check.py`](../../apps/skillnet-api/src/services/embedding_check.py)), porque un
desajuste es, si no, invisible: la inserción falla dentro del `except` de la ingesta, el
documento se marca `READY` solo con `full_text`, y el tutor responde en silencio desde los
peldaños inferiores de la escalera de recuperación. Lo registra y lo reporta en `GET /health`;
no aborta, porque autenticación, cursos, lecciones y progreso siguen funcionando todos sin
embeddings.

### 5.8 Corriendo sobre un modelo local

Usar [`docker-compose.ollama.yml`](../../docker-compose.ollama.yml):

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d --build
```

**Por qué un fichero overlay y no una entrada `profiles:`.** Fue un perfil hasta el 2026-08-04,
y precisamente por eso nunca funcionó: un perfil puede encender un servicio, pero no puede
alcanzar *otro* servicio y cambiar su entorno, así que nada le decía nunca a `api` que existía
un host `ollama`. Tampoco publicaba ningún puerto, no descargaba ningún modelo, y su
healthcheck (`ollama list`) sale con código 0 aunque haya cero modelos — así que se reportaba
saludable mientras cada petición fallaba con `model not found`.

Dos detalles que el overlay codifica, ambos fáciles de equivocar a mano:

- **La URL base y el prefijo del modelo tienen que coincidir.** `ollama_chat/…` y `ollama/…`
  son los proveedores nativos de litellm y añaden `/api/chat` por sí mismos, así que la URL base
  **no** lleva `/v1`. La ruta compatible con OpenAI quiere `/v1` y un id de modelo sin prefijo.
  Mezclarlos produce `http://ollama:11434/v1/api/chat`, un 404 — y ese era exactamente el par
  que el README y este documento solían sugerir entre sí.
- **El modelo de embeddings debe fijarse explícitamente.** `EMBEDDING_BASE_URL` cae por defecto
  a `LLM_BASE_URL`, así que apuntar solo el LLM a ollama deja a SkillNet pidiéndole a *ollama*
  `text-embedding-3-small`, que no tiene — y cada ingesta falla entonces en silencio (§5.7).
  `nomic-embed-text` es el valor por defecto aquí porque genera 768 dimensiones, que es lo que
  fija la migración 0008: sin migración, no hay reingesta.

**Esperar que sea lento.** Medido el 2026-07-27 en CPU: ~185 s por pantalla de lección renderizada
con un modelo de 7B, y `llama3.2:3b` produce UI generativa inválida y cae a prosa. Genuinamente
útil para desarrollo sin conexión; no es una forma cómoda de usar el producto. Con una clave de
API la misma pantalla tarda segundos.

### 5.9 Corriendo sin ninguna clave

```
LLM_MODEL=fixture/local
EMBEDDING_MODEL=fixture/local
```

en `.env`, y arrancar normal. Cada llamada de LLM y embeddings se sirve desde
`apps/skillnet-api/src/llm/fixture_data`, SPA incluida. Las fixtures van dentro de `src`, así
que la imagen de producción no necesita ningún cambio para soportar esto.

Dos límites que vale la pena decir sin rodeos. Solo funcionan los prompts con una respuesta
grabada — un fallo lanza un `LLMError` explícito nombrando la clave que buscaba, y el índice
empaquetado cubre muchos menos prompts de los que necesitan los cursos sembrados, así que abrir
un nodo dinámico arbitrario fallará. Y `resolve_llm_config` da prioridad a los ajustes de la
organización sobre el entorno, así que una organización con un `llm_model` guardado sigue
llamando a su proveedor sin importar estas dos líneas.

El **perfil** `fixtures` es otra cosa distinta, y no es el camino sin claves para la aplicación
web:

```bash
docker compose --profile fixtures up -d db api-fixtures   # http://127.0.0.1:8001
```

`docker/nginx.conf` hace proxy hacia `api` incondicionalmente, sin ninguna variable que cambiar,
así que la SPA nunca alcanza `api-fixtures`. Es una segunda API sin claves para `curl` y Swagger
(`LLM_MODEL=fixture/local`, `EMBEDDING_MODEL=fixture/local`), y comparte `SECRET_KEY` y la base
de datos con la real. Una herramienta de depuración, no un sandbox.

### 5.10 Referencia rápida

```bash
docker compose up -d --build                                 # arrancar
docker compose logs -f api                                   # seguir la API
docker compose exec api uv run python -m src.seed_learning_demo  # datos de demo (recomendado)
curl http://localhost:3000/api/v1/health                     # db + embeddings + flags
docker compose down                                          # parar, conservar datos
docker compose down -v                                       # parar, destruir datos
```
