# syntax=docker/dockerfile:1
# skillnet-mcp — MCP server, thin Streamable HTTP wrapper over /ext/v1.
# Build context is the repo root (matches docker/a2a.Dockerfile's convention).

FROM node:20-slim AS builder
WORKDIR /app
COPY packages/skillnet-mcp/package.json packages/skillnet-mcp/package-lock.json* ./
RUN npm install
COPY packages/skillnet-mcp/tsconfig.json ./
COPY packages/skillnet-mcp/src ./src
RUN npm run build

FROM node:20-slim AS runtime
RUN groupadd -r skillnet && useradd -r -g skillnet -d /app -s /sbin/nologin skillnet
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/package.json /app/package-lock.json* ./
RUN npm install --omit=dev
COPY --from=builder /app/dist ./dist
RUN chown -R skillnet:skillnet /app
USER skillnet
EXPOSE 3001
CMD ["node", "dist/index.js"]
