# Running SkillNet

In order, top to bottom. Nothing to skip, and only one thing to decide (step 2).

If you are an AI agent and were asked to "start the project", this file is the whole answer.
Everything else is detail you do not need yet.

## Step 0 — What you need

Docker with Compose v2. `docker compose version` should print 2.x.

Nothing else: Python, Node and PostgreSQL all run inside the containers.

## Step 1 — Clone and copy the config

```bash
git clone https://github.com/ANFAIA/SkillNet.git
cd SkillNet
cp .env.example .env
```

## Step 2 — Decide what powers it

This is the only real decision, and everything else follows from it. Pick a row, put those
values in your `.env`, and move on.

| I want to use… | Put in `.env` | What it costs you |
|---|---|---|
| **An API key** *(recommended)* | `LLM_API_KEY=sk-…` — nothing else | Fast: seconds per screen, around 0.01 USD per generated course. The defaults `gpt-4o-mini` and `text-embedding-3-small` already match the database schema and both run off this one key. Any [litellm](https://docs.litellm.ai/docs/providers) provider works instead — set `LLM_MODEL=anthropic/claude-sonnet-4-20250514`, `deepseek/deepseek-chat`, `groq/llama-3.1-8b-instant`… |
| **A local model** | Nothing — use the overlay in step 3 | Free, private, offline. But **slow**: measured ~185 s to generate one lesson screen on CPU. Needs ~8 GB of RAM and ~5 GB of disk. Good for trying it without an account; not comfortable for real use. |
| **Nothing at all** | `LLM_MODEL=fixture/local` and `EMBEDDING_MODEL=fixture/local` | Free and instant, but only screens with a recorded response render. Enough to click through the interface; not enough to author a course. |

Whichever row you picked, two values are always required:

| Variable | How to fill it |
|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `POSTGRES_PASSWORD` | Same generator. **Letters, digits, `-` and `_` only** |

The password restriction is not a style preference. It is interpolated into a connection URL
without escaping, so a `@`, `:`, `/` or `#` — exactly what a password manager produces —
splits the URL, and the API then fails to reach the database with an error that never
mentions the password.

`.env.example` already ships working demo credentials (`admin@skillnet.dev` / `admin123`) and
turns dynamic courses on, so there is nothing else to set.

## Step 3 — Start it

```bash
docker compose up -d --build
```

Or, if you picked the local model in step 2:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d --build
```

A cold build takes a couple of minutes. The ollama overlay also downloads the models (a few
GB) before the API comes up, so give the first start time. See
[`docker-compose.ollama.yml`](docker-compose.ollama.yml) for what it does and which model ids
are valid.

## Step 4 — Load the demo data

**Do not skip this.**

```bash
docker compose exec api uv run python -m src.seed_demo_v2
```

Startup creates the organization and the admin user, but no courses, no documents and no
employees. Without this step you log in to an empty dashboard and there is nothing to look
at — which is not a failure, just an empty database.

This seed builds a complete Spanish SME (a bakery-café): 5 employees, 3 source documents
indexed for the tutor, and 2 validated dynamic courses of 3 and 7 nodes. It is idempotent, so
running it twice is safe, and it prints every account it created.

There is also a much smaller v1 seed, `src.seed_demo` (1 employee and 16 skills), which
predates dynamic courses and exists to compare the old static path.

## Step 5 — Open it

<http://localhost:3000>

| Role | Email | Password |
|------|-------|----------|
| **Admin** | `admin@skillnet.dev` | `admin123` |
| Employee — with a learning profile | `lucia.fernandez@laespiga.example` | `espiga2026` |
| Employee — **no** profile, to walk the onboarding wizard | `noa.pereira@laespiga.example` | `espiga2026` |

Log in as the admin to author courses, or as an employee to take them.

## Did it work?

```bash
curl http://localhost:3000/api/v1/health
```

`database` must say `connected` and `embeddings.status` must say `ok`.

If `embeddings.status` is `mismatch`, the response also states exactly what to change. Worth
checking, because a wrong embedding dimension is the one misconfiguration that otherwise
fails silently: documents look ingested but nothing can retrieve them, and the tutor answers
from weaker sources without saying so.

## When something is wrong

| Symptom | Cause |
|---|---|
| `docker compose up` complains about a missing variable | `SECRET_KEY` or `POSTGRES_PASSWORD` is empty in `.env` |
| API cannot reach the database, error does not mention the password | The password contains `@`, `:`, `/`, `#` or `?`. See step 2 |
| Dashboard is empty after logging in | Step 4 was skipped |
| `embeddings.status: mismatch` in `/health` | `EMBEDDING_DIMENSIONS` does not match the column. The message says what to do |
| Courses exist but open blank, using `fixture/local` | No recording for that prompt. Expected; use an API key or the local model |
| Something in `.env` seems to be ignored | Probably is. Only variables listed in `docker-compose.yml` reach the container — there is no `env_file`. Add it to the `environment:` block of `api` |

Logs: `docker compose logs -f api`.

## Ports

A default `docker compose up -d` publishes **only 3000**. The API and the database are
reachable only from inside the compose network, because nginx is where the security headers
and the upload limit live.

Everything optional binds to `127.0.0.1`: the development overlay's `8000` and `5432`, plus
`api-fixtures` (8001), `a2a` (5000) and `ollama` (11434). Do not change those to `0.0.0.0` on
a shared network — Docker publishes ports with DNAT rules that **bypass the host firewall**.

`web` on `3000` is the deliberate exception; it is the front door. If you serve it beyond
localhost over plain HTTP, note that `COOKIE_SECURE` defaults to `false`, so session cookies
travel unencrypted. Put it behind TLS and set `COOKIE_SECURE=true`.

## Stopping it

```bash
docker compose down       # stop, keep the data
docker compose down -v    # stop, destroy the database and uploads
```

---

**Next:** [`README.md`](README.md) for what SkillNet is and how it works,
[`AGENTS.md`](AGENTS.md) for conventions and boundaries when changing the code, and
[`docs/design/docker-deployment.md`](docs/design/docker-deployment.md) for why the deployment
is shaped this way.
