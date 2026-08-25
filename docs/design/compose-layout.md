# Why the Docker Compose files are laid out this way

Written after a real deployment failed on 2026-08-25 and three plausible designs were tried
and discarded. The point of this page is that the next person — or the next agent — does not
spend a day rediscovering the same three dead ends.

## What the layout is

```
docker-compose.yml            a machine you control: publishes ports, runs nginx
docker-compose.dokploy.yml    a PaaS that fronts containers with its own Traefik
docker/compose/
  dev.yml                     hot reload: API in Docker, Vite on the host
  caddy.yml                   your own domain, your own certificate
  cloudflared.yml             a stable hostname on a Cloudflare domain
  quicktunnel.yml             a throwaway public URL, no account
  ollama.yml                  everything local, no API key
  embed.yml                   local embeddings, cloud generation
```

Two entry points in the root, and the file name says which is yours. The overlays are
optional and out of the way; nobody needs to read them to install the thing.

## Decision 1: two entry points, not one

**Forced by evidence, not chosen.** Three separate constraints, each verified:

1. **Dokploy loads exactly one compose file.** No `-f`, no `profiles`, no `include`, no
   `docker-compose.override.yml`. Coolify is the same. Every one of those has an open issue.
2. **Dokploy parses and rewrites the file before running it** — that is how it injects its
   own labels — and the rewrite **drops YAML tags**. Measured: `depends_on: !override` came
   back as a plain `depends_on` that MERGED with the inherited one, and the deploy died on
   `service "skillnet-api" depends on undefined service "db"`. That failure cannot be
   reproduced locally, where the file reaches Compose untouched.
3. **The web-facing service must join the external `dokploy-network`** or Traefik cannot see
   it and the domain 404s. An external network cannot be declared in a file that also has to
   run on a laptop, where it does not exist, and Compose has no conditional for it.

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

## Decision 2: the PaaS file keeps nginx

The alternative — dropping nginx and letting Traefik split the paths — works, and was tried.
It costs a **second domain entry** for `/api`, and forgetting that entry produces the failure
that started all this: the app loads, then `GET /api/v1/setup/status` returns 200 with
`index.html`, the SPA parses HTML as JSON, and you get "invalid response" on login with no
setup wizard. It reads like a frontend bug and is a missing route.

Keeping the existing image means Traefik needs to know about exactly one thing, and one entry
cannot be half-configured. It also removes two duplications that version had: a second web
image and a second copy of the header and cache policy.

Cost: one more container per deployment. A container does not get forgotten; a route in a
control panel does — and did.

### Why nginx is not a redundant proxy

It is a web server that happens to proxy. It serves the built SPA, does the history-API
fallback React Router needs, merges `/api` into the same origin as the frontend, carries the
security headers, enforces the upload limit, and turns off proxy buffering so the streaming
chat arrives token by token. Traefik does none of those: it routes to a backend, it cannot be
one.

Removing it is possible — serve the SPA from FastAPI with `StaticFiles` plus a catch-all — but
it relocates six responsibilities, so it is a change and not a deletion. That deletion has
already been attempted once and left the deployment with no interface at all.

## Decision 3: the one duplication is policed by a test

`skillnet-api.environment` in the PaaS file is a copy of `api.environment` in the base. It has
to be, per constraint 2. Copies drift, and drift here is the most repeated deployment bug in
this repository's history: a key added on one side only, an operator filling in a setting that
does nothing, and no error anywhere because `${VAR:-}` resolves to empty just as happily as to
a value.

`apps/skillnet-api/tests/test_compose_env_parity.py` fails the build when the two lists stop
matching, and also asserts that the PaaS file publishes no ports and carries no YAML tags.
Add a key to one file, add it to both.

## What is deliberately not here

- **A file per PaaS.** One file for the platform actually in use. Naming it `dokploy` is
  honest; generalising to Coolify and CapRover without a host to test on would be inventing.
- **`expose:`** on anything. It is informative only in modern Compose and buys nothing. All
  the official PaaS templates for comparable projects carry neither `ports:` nor `expose:`.
- **Traefik labels in the compose file.** Dokploy writes its own for whatever is added in its
  UI, and two routers claiming the same `Host()` rule is a coin flip. One owner: the UI.
