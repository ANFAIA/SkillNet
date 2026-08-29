# Why the Docker Compose files are laid out this way

Written after a real deployment failed on 2026-08-25 and three plausible designs were tried
and discarded. The point of this page is that the next person — or the next agent — does not
spend a day rediscovering the same three dead ends.

**Decision 2 was rewritten on 2026-08-27.** The first version of this page argued for keeping
nginx in the PaaS image — and it was written (`5fc276d`) *after* the commit that removed it
(`1696c28`), so it defended the discarded option from the day it was committed. The argument
below is the one the code implements. What the old version said is kept as the discarded
alternative, because the failure it was afraid of is real and is why the routing section is
so insistent.

## What the layout is

```
docker-compose.yml              a machine you control: publishes ports, runs nginx
docker-compose.dokploy.yml      a PaaS that fronts containers with its own Traefik
docker-compose.dev-api-only.yml an overlay, not an entry point: API with hot reload on
                                :8000 and NO db port, for a host with a native Postgres
docker/compose/
  dev.yml                       hot reload: API in Docker, Vite on the host
  caddy.yml                     your own domain, your own certificate
  cloudflared.yml               a stable hostname on a Cloudflare domain
  quicktunnel.yml               a throwaway public URL, no account
  ollama.yml                    everything local, no API key
  embed.yml                     local embeddings, cloud generation
```

Two entry points in the root, and the file name says which is yours. The overlays are
optional and out of the way; nobody needs to read them to install the thing.

`docker-compose.dev-api-only.yml` is the one exception to "overlays live under
`docker/compose/`", and it earns no principle: it is a `dev.yml` minus the `db` port
mapping, for a host that already has PostgreSQL on `127.0.0.1:5432`. It sits in the root
only because it arrived that way (`07ea2b5`, the same day as everything else here).

## Decision 1: two entry points, not one

**Forced by evidence, not chosen.** Three separate constraints, each verified:

1. **Dokploy loads exactly one compose file.** No `-f`, no `profiles`, no `include`, no
   `docker-compose.override.yml`. Coolify is the same. Every one of those has an open issue.
2. **Dokploy parses and rewrites the file before running it** — that is how it injects its
   own labels — and the rewrite **drops YAML tags**. Measured: `depends_on: !override` came
   back as a plain `depends_on` that MERGED with the inherited one, and the deploy died on
   `service "skillnet-api" depends on undefined service "db"`. That failure cannot be
   reproduced locally, where the file reaches Compose untouched.
3. **Every service Traefik has to reach must join the external `dokploy-network`** or the
   domain 404s. Since Decision 2 that is *two* services, `skillnet-web` and `skillnet-api`,
   not just the web one. An external network cannot be declared in a file that also has to
   run on a laptop, where it does not exist, and Compose has no conditional for it. Note
   also that naming any network opts a service out of the implicit `default`, so both
   services have to list `default: {}` back in — that is how they still reach PostgreSQL.

Constraint 3 is the one that closes the question: **one file cannot serve both cases.**

### Discarded: convert the exposure overlays to profiles

A profile switches services on and off. It **cannot rewrite an attribute of a service that
already exists**, and the exposure overlays exist precisely to replace `web.ports`. Not
convertible. This was tried first and is wrong.

### Discarded: make the bind address a variable

`ports: ["${WEB_BIND:-0.0.0.0}:${PORT:-3000}:80"]` is legal, and it would have let the
exposure services become profiles. It was rejected for a security reason, not a technical
one: today `!override` **couples** two decisions that must go together — start the tunnel and
`web` stops publishing, by construction. A variable separates them, so someone can activate
the tunnel, forget the variable, and end up with the tunnel open *and* the port open, with
nothing saying so. Trading a delicate mechanism that is safe by construction for an easy one
that is easy to forget is not an improvement.

### Discarded: persist the file list in `COMPOSE_FILE`

This is what Supabase does, and it is the right answer to "the docs make you repeat every
`-f`". It does not survive Dokploy, which reads the YAML directly rather than going through
`docker compose config`. Kept as a note for anyone who only self-hosts.

## Decision 2: the PaaS image drops nginx, and Traefik owns the routing

`docker/web.dokploy.Dockerfile` builds the same Vite bundle as `docker/web.Dockerfile` and
then diverges in the runtime stage only: `serve@14` on port 3000, configured by
`docker/serve.json`, no nginx. Shipped in `1696c28`.

**The reason is that on a Dokploy host Traefik already exists and is already a reverse
proxy.** nginx inside the container is then a *second* one, in the request path of every
response, configured in a different file, in a different language, with no test over it. The
question is not "is nginx useful" — it is useful, see below — but "is a proxy behind a proxy
worth what it costs to keep the two in agreement", and on this host it is not.

### What nginx was doing, and where each job went

`docker/nginx.conf` did eight things, and only one of them — proxying `/api` — is what
Traefik does. The other seven had to land somewhere, so the interesting column is the second
one:

| Job | Where it lives now |
|---|---|
| Serve the built SPA | `serve` over `/app/dist` |
| History-API fallback for React Router | `serve.json` → `rewrites: ** → /index.html` |
| Security headers | `serve.json` → `headers`, the same three as `docker/security-headers.conf` |
| Cache policy | `serve.json` → `immutable` on `assets/**`, `no-store` on `index.html` |
| Merge `/api` (and `/ext`) into the SPA's origin | **Traefik**, and this is the whole cost of the decision |
| `proxy_buffering off` for SSE | nothing to do: Traefik does not buffer responses |
| Proxy `/health` to the API | gone, and the web healthcheck now probes `/` — the honest check for a container whose only job is serving `index.html` |
| `client_max_body_size` and `gzip` | nowhere. See below. |

The last row is the one that bites, so spelled out:

- **`client_max_body_size 55m`.** Nothing declares a body cap in front of the API any more,
  so `MAX_UPLOAD_SIZE_MB` in FastAPI is the only limit — the request now reaches the
  application before it is refused. Add a Traefik `buffering` middleware if that matters.
- **`gzip on`.** Not declared in `serve.json`, so compression depends on `serve`'s own
  defaults rather than on anything in this repo, and Traefik's `compress` middleware is
  opt-in.

### The cost, named: `/api` needs a second domain entry

The SPA calls the API on **relative** paths (`/api/v1/...`,
`apps/skillnet-web/src/api/client.ts`) and has no configurable base URL. So the Domains tab
needs both halves on the same hostname:

```
host / path `/`     -> service skillnet-web, container port 3000
host / path `/api`  -> service skillnet-api, container port 8000
host / path `/ext`  -> service skillnet-api, container port 8000   (external API only)
```

Traefik ranks routers by rule length, so the prefix wins over `/` with no manual priority.
Two ways to get it wrong, and both look like a frontend bug:

1. **Miss the `/api` entry** and you reproduce the failure that started all of this: the app
   loads, `GET /api/v1/setup/status` returns 200 with `index.html`, the SPA parses HTML as
   JSON, and login says "invalid response" with no setup wizard.
2. **Leave "Strip Path" on** and the API receives `/v1/setup/status` and answers 404 —
   `/api/v1` is where FastAPI mounts (`src/main.py`), not a routing prefix to peel off. Same
   broken login, different cause.

That is why `skillnet-api` joins `dokploy-network` in the PaaS file. The paths Traefik now
exposes are the ones nginx already forwarded, so this is a shorter route to the same public
surface, not a wider one.

### The two duplications this creates

Naming them, because the discarded argument was right that they exist:

- **A second web image.** `docker/web.Dockerfile` and `docker/web.dokploy.Dockerfile` share
  the builder stage by copy, not by inheritance.
- **A second copy of the header and cache policy.** `docker/serve.json` restates
  `docker/security-headers.conf` and the `/assets` / `index.html` cache split. Unlike the
  environment block of Decision 3, **nothing fails the build when these two drift** — a
  header dropped on one side is a silent difference between two deployments of the same app.

Both are the price of the decision, not arguments against it: they are drift in files that
change roughly never, whereas keeping nginx was drift in the request path of every response.

### Discarded: keep nginx and give Traefik one entry

This is what the first version of this page argued, and it is not a bad argument: one domain
entry cannot be half-configured, whereas a route in a control panel gets forgotten — and did.
Its cost is one more container per deployment plus a proxy chain to keep in agreement.

It lost to the two failure modes above being *documented in three places* — the Dockerfile
header, the compose file header, and this page — which is what a control-panel step needs to
be reliable, and to the second proxy being permanent while adding a domain entry is a
one-time setup step.

### Why nginx stays in the self-hosted image

`docker-compose.yml` keeps `docker/web.Dockerfile`, and none of the above applies to it: on a
machine you control there is no Traefik, so nginx is the only thing that can merge `/api`
into the frontend's origin. It is a web server that happens to proxy, and dropping it there
would relocate the whole table above onto nothing.

The version of that deletion that keeps coming up — serve the SPA from FastAPI with
`StaticFiles` plus a catch-all — remains discarded and has never been in the code
(`src/main.py` mounts no `StaticFiles`). It is a change, not a deletion, and it puts the
static-file path inside the process whose slowness it would then share.

## Decision 3: the one duplication is policed by a test

`skillnet-api.environment` in the PaaS file is a copy of `api.environment` in the base. It has
to be, per constraint 2. Copies drift, and drift here is the most repeated deployment bug in
this repository's history: a key added on one side only, an operator filling in a setting that
does nothing, and no error anywhere because `${VAR:-}` resolves to empty just as happily as to
a value.

`apps/skillnet-api/tests/test_compose_env_parity.py` fails the build when the two lists stop
matching, and also asserts that the PaaS file publishes no ports and survives a YAML
round-trip (no tags). Add a key to one file, add it to both.

One lesson from that test worth carrying: it locates the environment block by scanning
between two comment anchors, and it anchored on `# The front door`, a phrase that described
nginx. Decision 2 deleted the phrase and the test failed with `no encontre el servicio
skillnet-api` — which reads like a broken compose file and was a broken anchor. It anchors on
the `# ── Frontend` section heading now, which survives changes to what follows it.

## What is deliberately not here

- **A file per PaaS.** One file for the platform actually in use. Naming it `dokploy` is
  honest; generalising to Coolify and CapRover without a host to test on would be inventing.
- **`expose:`** on anything. It is informative only in modern Compose and buys nothing. All
  the official PaaS templates for comparable projects carry neither `ports:` nor `expose:`.
- **Traefik labels in the compose file.** Dokploy writes its own for whatever is added in its
  UI, and two routers claiming the same `Host()` rule is a coin flip. One owner: the UI.
