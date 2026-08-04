# CLAUDE.md — SkillNet

Orientacion rapida del repo tal como esta hoy (2026-08-04). **Para arrancarlo, `RUNNING.md`.**
Para las reglas de estilo y las fronteras del proyecto, `AGENTS.md`. Para el diseno de v2,
`docs/design/v2-dynamic-courses.md`.

Este fichero **va al repo**, asi que aqui solo cabe lo que es cierto en cualquier maquina.
Rutas absolutas, servidores de modelos locales y apanos de sistema operativo van en
`CLAUDE.local.md`, que esta en el `.gitignore`.

**Idioma:** el codigo y sus comentarios, `README.md`, `RUNNING.md` y `.env.example` van en
**ingles**. En castellano solo este fichero, `AGENTS.md` y `scripts/` (los bancos de calidad).

## 1. Donde esta todo

- Backend: `apps/skillnet-api/` (FastAPI + LangGraph + pgvector)
- Frontend: `apps/skillnet-web/` (React 19 + TanStack Query)
- Docker: `docker-compose.yml` (db + api + web), `docker-compose.dev.yml` (hot reload),
  `docker-compose.ollama.yml` (todo con un modelo local, sin clave)

## 2. Docker

```bash
# Produccion. v2 queda en `on` si copiaste el .env.example; el default del codigo es `off`.
docker compose up -d --build                                              # http://localhost:3000

# Desarrollo: hot reload, logs en debug, v2 en `shadow`
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Todo con un modelo local, sin clave. La primera vez descarga los modelos.
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d --build

# Perfil `fixtures`: una segunda API sin claves, solo para curl. La SPA NO la usa.
docker compose --profile fixtures up -d db api-fixtures                   # http://127.0.0.1:8001
```

**Puertos publicados.** Produccion publica **solo el 3000** (`web`); `api` y `db` viven en la
red interna. El override de dev anade `8000` y `5432`, y `api-fixtures`, `a2a` y `ollama` sus
puertos — todos en `127.0.0.1`, nunca en `0.0.0.0`: Docker publica con reglas DNAT que
**atraviesan el cortafuegos**, asi que un `0.0.0.0:5432` es Postgres abierto a la red.

El perfil `fixtures` levanta la misma imagen que `api` pero con `LLM_MODEL=fixture/local` y
`EMBEDDING_MODEL=fixture/local`. Va en su propio puerto porque el nginx que sirve la SPA
apunta a `api` sin variable que cambiar, asi que **la interfaz web no lo usa**: sirve para
`curl` y Swagger. Para dejar *toda* la pila sin claves, poner esos dos valores en el `.env` y
arrancar normal. Ojo: comparte `SECRET_KEY` y base de datos con `api`, no es un sandbox.

`docker-compose.dev.yml` monta el repo del host sobre `/app` y ademas declara un volumen
anonimo en `/app/.venv`. Ese volumen es imprescindible: sin el, `uv run` dentro del
contenedor ve un virtualenv con binarios del host, decide que esta roto y **borra el `.venv`
del host** para reconstruirlo. Medido, no teorico.

## 3. Datos de prueba

```bash
docker compose exec api python -m src.seed_demo               # v1: empleado + 16 skills
docker compose exec api uv run python -m src.seed_demo_v2     # v2: panaderia-cafeteria
```

`seed_demo_v2` crea una pyme espanola completa: 5 empleados (4 con perfil de aprendizaje
poblado, 1 a proposito sin el, para recorrer el wizard de onboarding), 3 documentos y 2 cursos
dinamicos validados de 3 y 7 nodos. Contrasena de todos los empleados: `espiga2026`. El admin
usa el `ADMIN_EMAIL`/`ADMIN_PASSWORD` del `.env`.

**`uv run pytest -m integration` deja `document_chunks` vacia.** `test_migration_0005`
hace upgrade -> downgrade -> upgrade, el downgrade pasa por la migracion 0008, y esa
cambia la dimension del vector: no hay forma de conservar vectores de 768 componentes
al volver a una columna de 384, asi que los borra. El esquema vuelve solo y correcto;
los chunks no. Se recuperan relanzando el seed, y hasta entonces el tutor responde por
los peldanos de abajo de la escalera (`src/services/retrieval.py`) sin citar pasajes.

Es idempotente. `--refresh` es el bucle de calidad de contenido: se editan las especificaciones
de los nodos en `src/seed_demo_v2.py`, se relanza con `--refresh`, y los campos de diseno de los
nodos existentes se reescriben, `courses.schema_version` sube (invalida la cache de renders) y
se sueltan los renders fijados. El progreso del aprendiz se conserva.

## 4. Tests y calidad de generacion

```bash
cd apps/skillnet-api
uv run pytest -m "not integration"    # unitarios: sin base de datos ni claves
uv run pytest -m integration          # necesitan un PostgreSQL vivo
uv run ruff check src tests

uv run python scripts/quality_bench.py --offline    # banco de calidad, sin clave
uv run python scripts/quality_bench.py --repeat 3   # contra el proveedor del .env

uv run python scripts/retrieval_bench.py            # banco de RECUPERACION (RAG)
uv run python scripts/retrieval_bench.py --verbose  # + volcado de cada fallo
```

El banco corre el pipeline real sobre 10 encargos fijos y saca aciertos a la primera /
reparados / fallback / errores, p50 y p95, tokens y coste, mas el volcado de cada salida
fallida con el motivo del validador. Los diales que se tocan estan en `docs/design/tuning.md`.

Medido el 2026-07-27 contra Groq (`llama-3.1-8b-instant` / `openai/gpt-oss-120b`): de menos de
un segundo a ~3 s por render, ~0.0008 USD por render. El problema de "20-30 segundos por
generacion" que asumia la fase de investigacion **no existe en esta pila** — aquellas cifras
de 60-150 s eran de un 7B en CPU local. El plan gratuito de Groq si da 429 con facilidad, asi
que cualquier medicion necesita retroceso exponencial (el banco ya lo trae).

## 5. Estado

- v1 implementado y es lo que sirve produccion.
- v2 (cursos dinamicos) implementado **detras de `DYNAMIC_COURSES_MODE`**, que por defecto esta
  en `off`: todas las rutas v2 devuelven 404 y `delivery_mode` se ignora. `shadow` = solo la
  superficie de admin; `on` = v2 completo, y aun asi solo para cursos
  `delivery_mode='dynamic'` **y** `schema_status='validated'`.
- La regresion de v1 con el flag apagado es la invariante que no se rompe:
  `tests/integration/test_v1_regression.py`.

## 6. Git

- **Una sola rama: `main`.** No hay ramas de larga duracion. `feat/dynamic-courses` existio
  hasta el 2026-08-04 y se borro ya fusionada, cuando llevaba 34 commits por detras de
  `main`; esta linea decia que era "la rama de trabajo actual" mucho despues de dejar de
  serlo, que es como una rama muerta sobrevive.
- Formato de commit: `type: descripcion` (feat, fix, docs, refactor, test, chore).
- **Autoria solo de Jose. Sin `Co-Authored-By`.**
