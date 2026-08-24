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

`.env.example` already ships working demo credentials (`admin@skillnet.dev` / `admin123`), so
there is nothing else to set. Dynamic courses (v2) need no flag — the seed data already
includes a validated dynamic course, and any new course can opt in per-course.

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

**This step is for *exploring* the demo.** A real deployment skips it: you create your own
content in the app — upload a document or describe a topic and let it generate a course. Run
this only if you want the ready-made example to click around.

```bash
docker compose exec api uv run python -m src.seed_learning_demo
```

Startup creates the organization and the admin user, but no courses, no documents and no
employees. Without this seed you log in to an empty dashboard — which is exactly right for a
fresh install, and just an empty database if you meant to try the demo.

This seed is the public, self-branded SkillNet demo, on the meta theme of **how we learn**:
four short, Brilliant-style courses ("Cómo aprende tu cerebro", "Sesgos cognitivos", "La
ciencia de los hábitos", "Memoria y olvido"), all generated and validated at seed time, plus
three demo learners with different declared learning styles. The showcase course carries a
podcast and an infographic per node so the in-lesson media components appear; the other three
carry a course-level podcast. It is idempotent and re-runnable (it reuses an already-validated
course of the same title), and it prints every account and per-course result. Generation is
LLM-backed, so a full run is slow — that is expected.

> The previous demo (a Spanish bakery-café) has been retired and removed from the codebase.
> `seed_learning_demo` is the public default; when it runs it also cleans up any leftover
> bakery-café data from the default org on dev databases that still carry it.

There is also a much smaller v1 seed, `src.seed_demo` (1 employee and 16 skills), which
predates dynamic courses and exists to compare the old static path.

### Individual workspace mode

By default a deployment runs in `organization` mode (a company/team/class, the flow above).
The other mode is `individual`: one person who installs SkillNet for themselves and both
administers and learns — no employees, talent, assignments or org reports. See
[`docs/design/audience-modes.md`](docs/design/audience-modes.md).

The mode is a stable per-deployment setting, chosen one of two ways:

- **First-boot wizard (UI).** If you leave `ADMIN_EMAIL`/`ADMIN_PASSWORD` unset, the first
  time you open the app it shows a `/setup` screen: pick the mode (Organization / Just me),
  create the owner, and you are signed in. The wizard closes for good once an owner exists.
- **Headless (`.env`).** Set the owner and mode before the first boot (the mode is read only
  when the organization row is first created):

  ```bash
  WORKSPACE_MODE=individual   # in your .env, alongside ADMIN_EMAIL / ADMIN_PASSWORD
  ```

## Step 5 — Open it

<http://localhost:3000>

| Role | Email | Password |
|------|-------|----------|
| **Admin** | `admin@skillnet.dev` | `admin123` |
| Learner — metaphors + audio (sees the in-lesson podcast) | `ana@skillnet.dev` | `aprender2026` |
| Learner — definitions-first + visual (sees the in-lesson infographic) | `bruno@skillnet.dev` | `aprender2026` |
| Learner — **no** profile, to walk the onboarding wizard | `carla@skillnet.dev` | `aprender2026` |

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

## Developing the frontend (hot reload)

The `web` container on `:3000` is the **production** build — an nginx image baked at
`docker compose build`. Rebuilding it for every CSS tweak is the slow way and is **not** how
you develop the UI. For frontend work, run the API and database in Docker and the frontend
with **Vite on the host**, which hot-reloads on save:

```bash
# 1. API + DB in Docker (the dev overlay publishes the API on 127.0.0.1:8000)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db api

# 2. Frontend on the host — the one thing that needs Node (≥20) + pnpm locally
pnpm --dir apps/skillnet-web install      # first time only
pnpm --dir apps/skillnet-web dev          # Vite dev server
```

Then open **<http://localhost:5173>** (Vite's port), **not** 3000. Vite proxies `/api` to
`http://127.0.0.1:8000`, so it talks to the dockerized API; point it elsewhere with
`SKILLNET_API_PROXY`. Edit anything under `apps/skillnet-web/src` and the change appears
instantly — **no `docker compose build web`**.

Rebuild the `web` container only to check the real production bundle:
`docker compose build web && docker compose up -d web` → served on `:3000`.

## When something is wrong

| Symptom | Cause |
|---|---|
| `docker compose up` complains about a missing variable | `SECRET_KEY` or `POSTGRES_PASSWORD` is empty in `.env` |
| API cannot reach the database, error does not mention the password | The password contains `@`, `:`, `/`, `#` or `?`. See step 2 |
| Dashboard is empty after logging in | Step 4 was skipped |
| `embeddings.status: mismatch` in `/health` | `EMBEDDING_DIMENSIONS` does not match the column. The message says what to do |
| Courses exist but open blank, using `fixture/local` | No recording for that prompt. Expected; use an API key or the local model |
| Something in `.env` seems to be ignored | Probably is. Only variables listed in `docker-compose.yml` reach the container — there is no `env_file`. Add it to the `environment:` block of `api` |
| `port is already allocated` when `web` starts | Something else on the host holds port 3000 — often an earlier SkillNet still running (`docker compose ps`). Either stop it, or set `PORT=3100` in `.env` and open that port instead |
| `git clone` on Windows ends in `Filename too long` / `unable to checkout working tree` | Windows caps a path at 260 characters unless told otherwise, and the clone leaves a half-written tree. Run `git config --global core.longpaths true`, delete the broken folder and clone again — or clone somewhere shorter, like `C:\SkillNet` |

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

## Exposing SkillNet on your own domain

The default stack is loopback-friendly, not internet-friendly: `web` speaks plain HTTP, which
is fine on `localhost` but not something to hand a real domain. `docker-compose.caddy.yml` is
an optional overlay that puts [Caddy](https://caddyserver.com/) in front of `web` as a
reverse proxy with automatic Let's Encrypt TLS.

**Prerequisites:**

- A domain (or subdomain) you control.
- Its DNS **A record** already pointing at this host's public IP.
- Ports **80** and **443** open and forwarded to this host on the router/firewall — Caddy
  needs 80 to answer Let's Encrypt's HTTP-01 challenge, and 443 to serve over TLS afterward.

**Run it:**

```bash
# in .env
DOMAIN=courses.example.com
CADDY_EMAIL=you@example.com   # required — Caddy's `email` directive can't be blank

docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
```

This overlay also takes `web` off its own public port — Caddy becomes the only public
entrypoint, and `web` falls back to `127.0.0.1:${PORT:-3000}` like the rest of the internal
services (see [Ports](#ports) above).

Once this is live, set `COOKIE_SECURE=true` in `.env` and restart `api` — session cookies
should not travel unencrypted once there is a real TLS front door.

### Exposing SkillNet without opening a port

The Caddy path above needs a domain, DNS pointed at your public IP, and 80/443 open on
your router. If any of that isn't possible — you're behind CGNAT, on a laptop that
changes networks, or just don't want to touch the firewall — a Cloudflare Tunnel gets you
a public HTTPS URL with none of it: `cloudflared` makes an outbound-only connection to
Cloudflare's edge, and Cloudflare forwards public traffic back down it. No inbound port,
no public IP required.

**Prerequisites:** a free Cloudflare account, and a domain added to it (Cloudflare manages
its DNS). The token-based flow used here is the durable, named-tunnel kind meant for a
real deployment — it does not support the free `*.trycloudflare.com` "quick tunnel"
option, since that mode skips the dashboard/token setup entirely and hands you a
random hostname that changes on every restart. A domain in Cloudflare is required.

**1. Create the tunnel:**
- Cloudflare Zero Trust dashboard → Networks → Tunnels → Create a tunnel.
- Choose **Docker** as the connector. Cloudflare shows a `docker run cloudflared ... --token <TOKEN>` command — copy just the token.
- Add a public hostname for the tunnel (e.g. `skillnet.yourdomain.com`) pointing at service `http://web:80`.

**2. Configure and run:**

```bash
# .env
CLOUDFLARE_TUNNEL_TOKEN=<the token from the dashboard>

docker compose -f docker-compose.yml -f docker-compose.cloudflared.yml up -d --build
```

No router or firewall changes of any kind — unlike the Caddy path, there is nothing to
open on 80/443. Once the tunnel connects (check with `docker compose logs cloudflared`),
the hostname you set in step 1 serves SkillNet over HTTPS, TLS handled entirely by
Cloudflare. Set `COOKIE_SECURE=true` once traffic is genuinely arriving over HTTPS through
the tunnel — see the `COOKIE_SECURE` note next to `DOMAIN` in `.env.example`.

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
