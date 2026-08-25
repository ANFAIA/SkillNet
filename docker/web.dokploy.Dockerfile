# syntax=docker/dockerfile:1
# SkillNet Web for Dokploy — build the SPA with Vite, serve the static build on :3000.
# Build context is the repo root.
#
# Differs from docker/web.Dockerfile in the runtime stage only: no nginx, because on a
# Dokploy host Traefik is already the reverse proxy and a second one inside the container
# is a layer to keep in sync for nothing.
#
# ## What nginx was also doing, and where it has to go instead
#
# The SPA calls the API on RELATIVE paths (`/api/v1/...`, see apps/skillnet-web/src/api/
# client.ts) — there is no configurable API base URL. nginx used to proxy `/api/` and
# `/ext/` to the API container, so dropping it moves that job to Traefik. In Dokploy's
# Domains tab you need TWO entries on the same hostname:
#
#   host / path `/`     -> service skillnet-web, container port 3000
#   host / path `/api`  -> service skillnet-api, container port 8000
#
# (plus `/ext` -> skillnet-api:8000 if you use the external API). Traefik ranks routers by
# rule length, so the `/api` prefix wins over `/` without any manual priority. Without that
# second entry the app loads and then every request 404s into index.html — a white screen
# after login, not an error page.

# ── Stage 1: Build the SPA ───────────────────────────────────────────
FROM node:22-alpine AS builder

# pnpm from npm rather than `corepack enable`. Corepack downloads the version pinned in
# package.json#packageManager at first use and verifies its signature, which needs network
# and an up-to-date keyring at BUILD time — the failure mode is an opaque
# "Cannot find matching keyid" that has nothing to do with this project's code. Pinning
# the same version here keeps the lockfile honest without that moving part.
RUN npm install --global pnpm@11.9.0

WORKDIR /build

# Lockfile + manifests first, so a source-only change reuses the dependency layer.
COPY apps/skillnet-web/package.json apps/skillnet-web/pnpm-lock.yaml apps/skillnet-web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# Source, then production build.
COPY apps/skillnet-web/index.html apps/skillnet-web/vite.config.ts ./
COPY apps/skillnet-web/tsconfig.json apps/skillnet-web/tsconfig.app.json apps/skillnet-web/tsconfig.node.json ./
COPY apps/skillnet-web/src ./src
COPY apps/skillnet-web/vendor ./vendor
COPY apps/skillnet-web/public ./public

# `pnpm run build` is `tsc -b && vite build`. Both are memory-hungry on a repo this size,
# and a small VPS kills them with a bare "Killed" / exit 137 that reads like a broken
# build rather than an out-of-memory. 4 GB is the ceiling, not a reservation: V8 grows
# into it only if the build needs it.
ENV NODE_OPTIONS=--max-old-space-size=4096
RUN pnpm run build

# ── Stage 2: Serve the static build ──────────────────────────────────
FROM node:22-alpine AS runtime

# `serve` handles the two things a SPA needs from a static server: the history-API
# fallback (any unknown path returns index.html so React Router can take over) and
# per-path headers. Both are configured in serve.json, not on the command line.
RUN npm install --global serve@14

WORKDIR /app

COPY --from=builder /build/dist ./dist
# Kept OUTSIDE ./dist on purpose: anything inside the served directory is a public URL,
# and the config is nobody's business but the server's.
COPY docker/serve.json ./serve.json

# The image ships a `node` user; running the static server as root buys nothing.
USER node

EXPOSE 3000

CMD ["serve", "--listen", "3000", "--config", "/app/serve.json", "/app/dist"]
