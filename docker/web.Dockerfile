# syntax=docker/dockerfile:1
# SkillNet Web — build the React SPA with pnpm, serve with nginx.
# Build context is the repo root.

# ── Stage 1: Build the SPA ───────────────────────────────────────────
FROM node:22-alpine AS builder

RUN corepack enable

WORKDIR /build

# Lockfile + manifest first for caching.
COPY apps/skillnet-web/package.json apps/skillnet-web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Source, then production build.
COPY apps/skillnet-web/ ./
RUN pnpm run build

# ── Stage 2: Serve with nginx ────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

RUN rm /etc/nginx/conf.d/default.conf
COPY docker/nginx.conf /etc/nginx/conf.d/skillnet.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
