## 5. Docker & Deployment

**How to run it is in [`README.md`](../../README.md).** This document records *why* the
deployment looks the way it does, and the traps that are not obvious from reading the files.

It used to inline full copies of `docker-compose.yml`, both Dockerfiles, `.env.example` and
`docker-compose.dev.yml`. Those copies drifted: by 2026-08-04 the `db` healthcheck here
differed from the real one, the dev override described a Vite-based `web` service that does
not exist, and two sections documented a file that never existed at all. A design document
whose body is a stale duplicate of the source is worse than no document, because it is
confidently wrong. So the files are linked, not pasted.

- [`docker-compose.yml`](../../docker-compose.yml) — the stack
- [`docker-compose.dev.yml`](../../docker-compose.dev.yml) — hot-reload overlay
- [`docker-compose.ollama.yml`](../../docker-compose.ollama.yml) — local-model overlay
- [`docker/api.Dockerfile`](../../docker/api.Dockerfile), [`docker/web.Dockerfile`](../../docker/web.Dockerfile), [`docker/nginx.conf`](../../docker/nginx.conf)
- [`.env.example`](../../.env.example) — every variable, with the reasoning inline

---

### 5.1 The services

| Service | Starts by default | Purpose |
|---|---|---|
| `db` | yes | PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`) |
| `api` | yes | FastAPI + uvicorn. Runs `alembic upgrade head` in its lifespan |
| `web` | yes | nginx serving the built SPA, reverse-proxying `/api`, `/ext` and `/health` |
| `api-fixtures` | profile `fixtures` | second API answering from recorded fixtures — see §5.9 |
| `a2a` | profile `a2a` | agent-to-agent server for external agents |
| `ollama` | overlay file | local model server — see §5.8 |

Background jobs run in-process through the JobCoordinator
([`background-processing.md`](background-processing.md)), backed by PostgreSQL with LangGraph
persistence. There is no worker container at this scale, and adding one later does not change
anything described here.

**Why `web` proxies to `api` instead of the SPA calling it directly.** Same origin, so no
CORS configuration to get wrong; one port for an admin to open; and one place for TLS
termination. It also means nginx is the only path in, which is what makes §5.2 possible.

### 5.2 Published ports, and why almost none

A default `docker compose up -d` publishes **only 3000**. `api` and `db` are reachable only
from inside the compose network.

That is not minimalism for its own sake. The security headers and the 55 MB upload limit live
in [`docker/nginx.conf`](../../docker/nginx.conf), so an exposed `api` port is a way around
both.

Everything optional binds to `127.0.0.1`. **Docker publishes ports with DNAT rules that
bypass the host firewall**, on Windows and on Linux, so `0.0.0.0:5432` is a Postgres offered
to every machine on the network however the firewall is configured. Until 2026-08-04 the dev
overlay published `8000` and `5432` exactly that way, and `api-fixtures` published `8001` —
which is worse than it sounds, because that service shares `SECRET_KEY` and the database with
the real API, so its session cookies are valid against it.

`web` on `0.0.0.0:3000` is the one deliberate exception: it is the front door. Note that
`COOKIE_SECURE` defaults to `false`, so session cookies travel unencrypted over plain HTTP.
Behind TLS, set it to `true`.

### 5.3 The two image stages, and the trap between them

[`docker/api.Dockerfile`](../../docker/api.Dockerfile) builds `builder` (dependencies, `uv`,
root) and `runtime` (venv on `PATH`, non-root `skillnet` user, minimal). The dev overlay
builds `target: builder` on purpose: hot reload needs `uv` and the mounted source.

Two asymmetries bit repeatedly and are now fixed:

1. **`uv` existed only in `builder`, the venv `PATH` only in `runtime`.** So
   `uv run python -m …` worked only in development and bare `python -m …` only in production
   — and the README printed one of each three lines apart, neither valid in both. `runtime`
   now copies `uv` too, so a single documented command works everywhere.
2. **`PYTHONUNBUFFERED` and `PYTHONDONTWRITEBYTECODE` were set only in `runtime`.**
   Development therefore lost everything written to `stdout` — uvicorn's access log, and every
   `print()`, which is how the seed scripts talk — and wrote `.pyc` files into the
   bind-mounted host source tree. Both now live in `builder`, which `runtime` inherits.

One still open: `builder` runs as root, so the dev container writes to your source tree as
root. On Linux and WSL that leaves root-owned `__pycache__` and alembic revisions in the repo,
which then break `git clean` and the editor. `docker-compose.dev.yml` already solves the same
class of problem for `.venv` with an anonymous volume; the rest of the tree is not covered.

### 5.4 The `.env` only half arrives

**No service declares `env_file`**, and [`.dockerignore`](../../.dockerignore) keeps `.env`
out of the image, so pydantic's `env_file=".env"` finds nothing inside the container. Only the
variables listed explicitly in a service's `environment:` block reach the API.

Adding a variable to `.env` and seeing no effect is therefore the expected outcome, not a bug.
Most dials in [`tuning.md`](tuning.md) are unreachable in Docker for this reason — to use one,
add it to the `environment:` block of `api` first.

Related, and the same root cause: model defaults live in the compose file, not in
`src/config.py`. `${LLM_MODEL:-}` leaves the variable *set and empty*, and an empty string
beats a Python default, so the code's default never applied inside Docker at all. Setting only
`LLM_API_KEY` used to start nothing.

### 5.5 Development vs production

```bash
docker compose up -d --build                                                # production
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build   # hot reload
```

The overlay switches `api` to `target: builder`, runs uvicorn with
`--reload --reload-dir src`, publishes `8000` and `5432` on loopback, and sets
`LOG_LEVEL=debug`. It does **not** override `web`; for frontend work,
run Vite on the host instead (`npm run dev` in `apps/skillnet-web`, which proxies `/api` to
`localhost:8000`).

Two things in that file are load-bearing and commented as such:

- **`--build` is not decoration.** The overlay changes `target`, and without a rebuild compose
  reuses the `runtime` image, whose command has no `uv` — the container dies with
  `exec: "uv": executable file not found in $PATH`.
- **The anonymous volume on `/app/.venv`.** The source bind mount shadows the image's venv
  with the host's, which on Windows and macOS is full of foreign binaries. `uv run` then
  decides the environment is broken, **deletes it**, and rebuilds it inside the container —
  destroying the venv the host test suite runs from. Measured, not theoretical.

| Concern | Development | Production |
|---|---|---|
| Restart policy | not set | `unless-stopped` |
| Log level | `debug` | `info` |
| Code | mounted, `--reload` | baked into the image |
| Published ports | `3000`, plus `8000` and `5432` on loopback | `3000` only |
| Frontend | Vite on the host | nginx serving the static build |
| Build target | `builder` (root, has `uv`) | `runtime` (non-root, minimal) |
| v2 flag | `shadow` | whatever `.env` says (`on` if copied from the example) |

**Not in compose, and deliberately left to the host:** TLS termination (put Caddy, Traefik or
the host nginx in front; SkillNet's nginx speaks HTTP internally), log rotation
(`logging: driver: json-file` with `max-size: 10m`, `max-file: "3"`), and memory limits
(`deploy.resources.limits.memory`). The `builder` image is a development artifact — it carries
`uv`, the build cache and root; nothing marks it as non-deployable, so do not ship the dev
overlay to a server.

### 5.6 Data persistence

Two named volumes: `pgdata` (`/var/lib/postgresql/data`) and `uploads` (`/data/uploads`, the
source documents). Both are critical to back up. `docker compose down` keeps them; `down -v`
destroys them.

**Named volumes rather than bind mounts** because they are managed by Docker and work the same
on Linux, macOS and Windows. A bind mount like `./data:/data` breaks on Windows, where UID and
GID do not map and PostgreSQL refuses to start. `docker volume inspect skillnet_pgdata` finds
the host path when direct access is needed.

Uploads are laid out as `/data/uploads/{org_id}/{document_id}/`, holding the file as uploaded
and its extracted text. Files and their rows in `documents` are not transactional with each
other: a row can outlive its file, and the ingestion marks the document `error` rather than
pretending otherwise.

Backup and restore: [`scripts/backup.sh`](../../scripts/backup.sh) (`pg_dump` piped through
gzip, keeping the last seven days). Restore with
`gunzip -c backups/skillnet_*.sql.gz | docker compose exec -T db psql -U skillnet skillnet`.
For a consistent full backup, `docker compose stop api` first, then dump the database and tar
the uploads volume. **What is not promised:** no scheduled backups, no cloud sync, no
point-in-time recovery. This is self-hosted; the operator owns it.

**The integration suite empties `document_chunks`.** `test_migration_0005` walks
upgrade → downgrade → upgrade, the downgrade passes through migration 0008, and 0008 changes
the vector dimension — there is no way to keep 768-component vectors when returning to a 384
column. The schema comes back correct; the chunks do not. Re-run the seed.

### 5.7 First run

The lifespan in [`src/main.py`](../../apps/skillnet-api/src/main.py) creates the upload
directory, runs `alembic upgrade head` (which also creates the `pgcrypto` and `vector`
extensions), then creates the organization and — only if `ADMIN_EMAIL` and `ADMIN_PASSWORD`
are set — the admin user and the A2A API key.

It creates **no** courses, documents or employees. A first login therefore lands on an empty
dashboard, which is why loading the demo data is a numbered step in the README rather than an
afterthought.

There is no setup wizard. An earlier draft of this document described `/setup` and
`GET /api/v1/setup/status`; neither route was ever registered in `src/main.py`. The headless
bootstrap replaced the idea and the section outlived it.

Startup also verifies that `EMBEDDING_DIMENSIONS` matches the actual column
([`embedding_check.py`](../../apps/skillnet-api/src/services/embedding_check.py)), because a
mismatch is otherwise invisible: the insert fails inside the ingestion `except`, the document
is marked `READY` with only `full_text`, and the tutor quietly answers from the lower rungs of
the retrieval ladder. It logs and reports in `GET /health`; it does not abort, because
authentication, courses, lessons and progress all still work without embeddings.

### 5.8 Running on a local model

Use [`docker-compose.ollama.yml`](../../docker-compose.ollama.yml):

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d --build
```

**Why an overlay file and not a `profiles:` entry.** It was a profile until 2026-08-04, and
that is precisely why it never worked: a profile can switch a service on, but it cannot reach
into *another* service and change its environment, so nothing ever told `api` that an `ollama`
host existed. It also published no port, pulled no model, and its healthcheck (`ollama list`)
exits 0 with zero models — so it reported itself healthy while every request failed with
`model not found`.

Two details the overlay encodes, both easy to get wrong by hand:

- **Base URL and model prefix have to agree.** `ollama_chat/…` and `ollama/…` are litellm's
  native providers and append `/api/chat` themselves, so the base URL carries **no** `/v1`.
  The OpenAI-compatible route wants `/v1` and an unprefixed model id. Mixing them produces
  `http://ollama:11434/v1/api/chat`, a 404 — and that was exactly the pair the README and this
  document used to suggest between them.
- **The embedding model must be set explicitly.** `EMBEDDING_BASE_URL` falls back to
  `LLM_BASE_URL`, so pointing only the LLM at ollama leaves SkillNet asking *ollama* for
  `text-embedding-3-small`, which it does not have — and every ingestion then fails quietly
  (§5.7). `nomic-embed-text` is the default here because it outputs 768 dimensions, which is
  what migration 0008 pins: no migration, no re-ingestion.

**Expect it to be slow.** Measured 2026-07-27 on CPU: ~185 s per rendered lesson screen with a
7B model, and `llama3.2:3b` produces invalid generative UI and falls back to prose. Genuinely
useful for offline development; not a comfortable way to use the product. With an API key the
same screen takes seconds.

### 5.9 Running with no keys at all

```
LLM_MODEL=fixture/local
EMBEDDING_MODEL=fixture/local
```

in `.env`, then start normally. Every LLM and embedding call is served from
`apps/skillnet-api/src/llm/fixture_data`, SPA included. The fixtures ship inside `src`, so the
production image needs no change to support this.

Two limits worth stating plainly. Only prompts with a recorded response work — a miss raises
an explicit `LLMError` naming the key it wanted, and the packaged index covers far fewer
prompts than the seeded courses need, so opening an arbitrary dynamic node will fail. And
`resolve_llm_config` gives organization settings priority over the environment, so an
organization with a stored `llm_model` keeps calling its provider regardless of these two
lines.

The `fixtures` **profile** is a different thing, and it is not the keyless path for the web
app:

```bash
docker compose --profile fixtures up -d db api-fixtures   # http://127.0.0.1:8001
```

`docker/nginx.conf` proxies to `api` unconditionally, with no variable to change, so the SPA
never reaches `api-fixtures`. It is a second, keyless API for `curl` and Swagger
(`LLM_MODEL=fixture/local`, `EMBEDDING_MODEL=fixture/local`), and it shares `SECRET_KEY` and
the database with the real one. A debugging tool, not a sandbox.

### 5.10 Quick reference

```bash
docker compose up -d --build                                 # start
docker compose logs -f api                                   # follow the API
docker compose exec api python -m src.seed_learning_demo  # demo data (recommended)
curl http://localhost:3000/api/v1/health                     # db + embeddings + flags
docker compose down                                          # stop, keep data
docker compose down -v                                       # stop, destroy data
```
