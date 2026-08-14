FROM node:24-alpine AS build

ARG BUILD_SHA=not-provided
ENV ASTRO_TELEMETRY_DISABLED=1
ENV BUILD_SHA=${BUILD_SHA}

WORKDIR /site

RUN corepack enable && corepack prepare pnpm@11.9.0 --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts --ignore-workspace

COPY . .
RUN pnpm run check && pnpm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /site/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q -O - http://127.0.0.1:8080/healthz.json | grep -q '"status":"ok"' || exit 1
