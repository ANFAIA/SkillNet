## 5. Docker & Deployment

### 5.1 Docker Compose Services

Three services. Each one has exactly one job.

| Service | Image | Role | Port |
|---------|-------|------|------|
| `web` | Custom (Node build + nginx) | Serves the React SPA, reverse-proxies `/api` to the backend | `3000:80` |
| `api` | Custom (Python + uvicorn) | FastAPI application server | `8000` (internal only) |
| `db` | `pgvector/pgvector:pg16` | PostgreSQL 16 with pgvector extension pre-installed | `5432` (internal only) |

> **Background jobs run in-process via the JobCoordinator (see background-processing.md). No separate worker process needed for MVP scale.** The JobCoordinator uses a PostgreSQL-backed job runner with LangGraph persistence, keeping the architecture simple. A separate worker service can be introduced later for SaaS scale if needed.

**Why `web` proxies to `api`.** The nginx config in the web container handles `/api/*` routes and forwards them to the `api` service. This means:
- No CORS configuration needed (same origin).
- A single exposed port (3000) for the admin to open.
- SSL termination in one place (nginx, when configured).

**Optional services, behind compose profiles.** None of these start with a plain `docker compose up`:

| Profile | Service | What it is |
|---------|---------|------------|
| `fixtures` | `api-fixtures` | A keyless copy of the API. Same image as `api`, but `LLM_MODEL=fixture/local` and `EMBEDDING_MODEL=fixture/local`, so every LLM and embedding call is served from the recorded fixtures in `src/llm/fixture_data`. `DYNAMIC_COURSES_MODE` is forced to `on`. |
| `ollama` | `ollama` | Local embedding/LLM inference. |
| `a2a` | `a2a` | Agent-to-agent server for external agents (`A2A_PORT`, default `5000`). |

```bash
docker compose --profile fixtures up -d db api-fixtures   # http://localhost:8001
```

`api-fixtures` publishes its **own** port — `API_FIXTURES_PORT`, default `8001` — rather than
sharing 3000, because the bundled nginx SPA proxies to `api` and nothing else. That is the whole
reason it is a separate service instead of an environment override: you get a keyless API to poke
at with `curl` or the Swagger docs while the normal stack keeps running. To make the *entire*
stack keyless, including the SPA, set the two `fixture/local` values in `.env` instead of using
this profile.

The fixtures ship inside `src`, so the production Dockerfile needs no change to support this.

---

### 5.2 docker-compose.yml

```yaml
# SkillNet — Production Docker Compose
# One command: docker compose up -d
# Docs: https://github.com/ANFAIA/SkillNet

services:
  # ── Database ────────────────────────────────────────────────
  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-skillnet}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: ${POSTGRES_DB:-skillnet}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-skillnet}"]
      interval: 5s
      timeout: 3s
      retries: 5
    # Not exposed to host by default. Uncomment to access directly:
    # ports:
    #   - "5432:5432"

  # ── Backend API ─────────────────────────────────────────────
  api:
    build:
      context: .
      dockerfile: docker/api.Dockerfile
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-skillnet}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-skillnet}
      SECRET_KEY: ${SECRET_KEY:?Set SECRET_KEY in .env}
      LLM_BASE_URL: ${LLM_BASE_URL:-}
      LLM_API_KEY: ${LLM_API_KEY:-}
      LLM_MODEL: ${LLM_MODEL:-}
      # Optional per-purpose model overrides (fall back to LLM_MODEL):
      # LLM_GENERATION_MODEL: ${LLM_GENERATION_MODEL:-}
      # LLM_TUTOR_MODEL: ${LLM_TUTOR_MODEL:-}
      # LLM_EVAL_MODEL: ${LLM_EVAL_MODEL:-}
      EMBEDDING_BASE_URL: ${EMBEDDING_BASE_URL:-}
      EMBEDDING_API_KEY: ${EMBEDDING_API_KEY:-}
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-}
      UPLOAD_DIR: /data/uploads
      LOG_LEVEL: ${LOG_LEVEL:-info}
      ENVIRONMENT: ${ENVIRONMENT:-production}
    volumes:
      - uploads:/data/uploads
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    # Not exposed to host — nginx proxies to it.

  # ── Frontend (nginx + React SPA) ───────────────────────────
  web:
    build:
      context: .
      dockerfile: docker/web.Dockerfile
    restart: unless-stopped
    ports:
      - "${PORT:-3000}:80"
    depends_on:
      api:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80/"]
      interval: 10s
      timeout: 3s
      retries: 3

volumes:
  pgdata:
    driver: local
  uploads:
    driver: local
```

---

### 5.3 Dockerfiles

#### 5.3.1 Backend — `docker/api.Dockerfile`

Multi-stage build. Uses `uv` for fast dependency resolution. The final image has no build tools.

```dockerfile
# ── Stage 1: Dependencies ────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Copy dependency files first (Docker layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY apps/skillnet-api/ ./apps/skillnet-api/

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: non-root user
RUN groupadd -r skillnet && useradd -r -g skillnet -d /app -s /sbin/nologin skillnet

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv

# Copy application code
COPY --from=builder /build/apps/skillnet-api /app

# Ensure venv is on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create upload directory
RUN mkdir -p /data/uploads && chown -R skillnet:skillnet /data/uploads

USER skillnet

EXPOSE 8000

# Default command: run the API server
# Workers: 1 per container. Scale by running more containers.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**Design decisions:**

- **`python:3.12-slim`** not `alpine`. Alpine uses musl libc which causes issues with some Python scientific packages and pgvector bindings. Slim is ~50 MB larger but avoids hours of debugging.
- **`uv sync --frozen`** installs exactly what's in `uv.lock`. Reproducible builds.
- **`--no-dev`** excludes test dependencies (pytest, etc.) from the production image.
- **1 worker per container.** Uvicorn with `--workers 1` is simplest for single-tenant. The async event loop handles concurrency. If someone needs more throughput, they scale the service in Compose.
- **Non-root user.** The `skillnet` user owns the app and upload directory. Nothing runs as root at runtime.

#### 5.3.2 Frontend — `docker/web.Dockerfile`

Two stages: Node builds the SPA, nginx serves it.

```dockerfile
# ── Stage 1: Build the React SPA ─────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /build

# Copy package files first (Docker layer caching)
COPY apps/skillnet-web/package.json apps/skillnet-web/package-lock.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY apps/skillnet-web/ ./

# Build the production bundle
RUN npm run build

# ── Stage 2: Serve with nginx ────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY docker/nginx.conf /etc/nginx/conf.d/skillnet.conf

# Copy built SPA from builder
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

# nginx runs as its own user by default. No changes needed.
CMD ["nginx", "-g", "daemon off;"]
```

#### 5.3.3 Nginx config — `docker/nginx.conf`

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # ── API reverse proxy ────────────────────────────────────
    location /api/ {
        proxy_pass http://api:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support (streaming responses from LLM)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;  # Long-running generation requests
    }

    # ── Health endpoint for the web service itself ───────────
    location /health {
        proxy_pass http://api:8000/health;
    }

    # ── SPA fallback ─────────────────────────────────────────
    # All unmatched routes serve index.html (React Router handles them)
    location / {
        try_files $uri $uri/ /index.html;
    }

    # ── Security headers (single source — must match security.md) ──
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # ── Compression ──────────────────────────────────────────
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 256;

    # ── Static asset caching ─────────────────────────────────
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

---

### 5.4 Environment Configuration

#### 5.4.1 `.env.example`

```bash
# SkillNet — Environment Configuration
# Copy this file to .env and fill in the required values.
# Docs: https://github.com/ANFAIA/SkillNet

# ══════════════════════════════════════════════════════════════
# REQUIRED — SkillNet won't start without these
# ══════════════════════════════════════════════════════════════

# Secret key for signing sessions and tokens.
# Generate one: python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=

# Database password. Pick something strong.
POSTGRES_PASSWORD=

# ══════════════════════════════════════════════════════════════
# LLM PROVIDER — Configure at least one for content generation
# ══════════════════════════════════════════════════════════════

# Any OpenAI-compatible API works (OpenAI, DeepSeek, Groq, Together, Ollama, etc.)
# These can also be set later via the admin settings page.

# Base URL of the LLM API (e.g., https://api.deepseek.com/v1)
LLM_BASE_URL=

# API key for the LLM provider
LLM_API_KEY=

# Model name (e.g., deepseek-chat, gpt-4o, llama3)
LLM_MODEL=

# Optional per-purpose model overrides (fall back to LLM_MODEL if not set):
# LLM_GENERATION_MODEL=
# LLM_TUTOR_MODEL=
# LLM_EVAL_MODEL=

# ══════════════════════════════════════════════════════════════
# EMBEDDINGS — For RAG / vector search (optional, falls back to LLM provider)
# ══════════════════════════════════════════════════════════════

# If different from LLM provider. Leave blank to use LLM_BASE_URL.
# EMBEDDING_BASE_URL=
# EMBEDDING_API_KEY=
# EMBEDDING_MODEL=text-embedding-3-small

# ══════════════════════════════════════════════════════════════
# OPTIONAL — Defaults are fine for most deployments
# ══════════════════════════════════════════════════════════════

# Port where SkillNet is accessible (default: 3000)
# PORT=3000

# Database config (defaults match the db service in docker-compose.yml)
# POSTGRES_USER=skillnet
# POSTGRES_DB=skillnet

# Logging level: debug, info, warning, error (default: info)
# LOG_LEVEL=info

# Environment: production, development (default: production)
# ENVIRONMENT=production

# ══════════════════════════════════════════════════════════════
# ADMIN ACCOUNT — First-run only
# ══════════════════════════════════════════════════════════════

# If set, creates an admin account on first startup instead of
# showing the setup wizard. Useful for automated deployments.
# ADMIN_EMAIL=admin@yourcompany.com
# ADMIN_PASSWORD=

# Organization name shown in the UI
# ORG_NAME=Your Company
```

#### 5.4.2 Variable classification

| Variable | Required | Default | Where used |
|----------|----------|---------|------------|
| `SECRET_KEY` | Yes | None | API (session signing) |
| `POSTGRES_PASSWORD` | Yes | None | db, API |
| `LLM_BASE_URL` | Soft* | None | API |
| `LLM_API_KEY` | Soft* | None | API |
| `LLM_MODEL` | Soft* | None | API |
| `LLM_GENERATION_MODEL` | No | Falls back to `LLM_MODEL` | API |
| `LLM_TUTOR_MODEL` | No | Falls back to `LLM_MODEL` | API |
| `LLM_EVAL_MODEL` | No | Falls back to `LLM_MODEL` | API |
| `EMBEDDING_BASE_URL` | No | Falls back to `LLM_BASE_URL` | API |
| `EMBEDDING_API_KEY` | No | Falls back to `LLM_API_KEY` | API |
| `EMBEDDING_MODEL` | No | Provider default | API |
| `PORT` | No | `3000` | web |
| `POSTGRES_USER` | No | `skillnet` | db, API |
| `POSTGRES_DB` | No | `skillnet` | db, API |
| `LOG_LEVEL` | No | `info` | API |
| `ENVIRONMENT` | No | `production` | API |
| `ADMIN_EMAIL` | No | None (wizard) | API (first run) |
| `ADMIN_PASSWORD` | No | None (wizard) | API (first run) |
| `ORG_NAME` | No | None (wizard) | API (first run) |

*Soft required: SkillNet starts without them, but content generation won't work. The admin can configure them via the setup wizard or the settings page.

#### 5.4.3 Secrets management

**For self-hosted single-tenant deployments, `.env` is sufficient.** The file lives on the admin's server, never committed to Git.

Rules:
- `.env` is in `.gitignore`. Always.
- `.env.example` is committed with empty values and comments.
- `SECRET_KEY` must be at least 32 characters. The API refuses to start if it's shorter.
- `POSTGRES_PASSWORD` is set once and never changed (changing it requires recreating the volume or manual DB update).
- `LLM_API_KEY` can be rotated anytime via the settings page without restarting.

**Docker secrets (future).** For SaaS or enterprise deployments, Docker secrets or a vault (HashiCorp, Infisical) can replace `.env` for sensitive values. The API reads from `os.environ` regardless of how the value gets there.

---

### 5.5 Development vs Production

#### 5.5.1 `docker-compose.dev.yml`

Override file for local development. Run with:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

```yaml
# SkillNet — Development Overrides
# Adds hot reload, debug logging, exposed ports.

services:
  api:
    build:
      context: .
      dockerfile: docker/api.Dockerfile
      target: builder  # Use builder stage (has uv for installs)
    command: ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    environment:
      LOG_LEVEL: debug
      ENVIRONMENT: development
    volumes:
      # Mount source code for hot reload
      - ./apps/skillnet-api:/app
    ports:
      - "8000:8000"  # Expose API directly for debugging

  web:
    # In dev, skip the nginx container entirely.
    # Use Vite's dev server directly (faster, HMR, better errors).
    build: !reset null
    image: node:22-alpine
    working_dir: /app
    command: ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "80"]
    volumes:
      - ./apps/skillnet-web:/app
      - /app/node_modules  # Anonymous volume to preserve container's node_modules
    environment:
      VITE_API_URL: http://localhost:8000  # Direct to API in dev (no proxy)

  db:
    ports:
      - "5432:5432"  # Expose DB for direct access (pgAdmin, psql, etc.)
```

**Dev workflow without Docker (recommended for frontend):**

Most frontend developers will run Vite directly on their machine (`npm run dev` in `apps/skillnet-web/`) and only Dockerize the backend services. For this:

```bash
# Start only backend services
docker compose -f docker-compose.yml -f docker-compose.dev.yml up db api

# In another terminal — frontend with HMR
cd apps/skillnet-web && npm run dev
```

#### 5.5.2 Production hardening

The base `docker-compose.yml` is already production-oriented. Key differences from dev:

| Concern | Development | Production |
|---------|-------------|------------|
| **Restart** | Not set | `unless-stopped` on all services |
| **Debug** | `LOG_LEVEL=debug` | `LOG_LEVEL=info` |
| **Hot reload** | Source mounted, `--reload` | Code baked into image |
| **Ports** | All services exposed | Only port 3000 (web) |
| **Frontend** | Vite dev server | nginx serving static build |
| **Build target** | `builder` stage (has dev tools) | `runtime` stage (minimal) |

**Additional production recommendations (not in Compose):**

- **SSL termination.** Use a reverse proxy in front (Caddy, Traefik, or the host's nginx) with Let's Encrypt. SkillNet's nginx speaks HTTP internally; the outer proxy handles HTTPS.
- **Log aggregation.** Docker's json-file log driver with `max-size: 10m` and `max-file: 3`. Add to each service:
  ```yaml
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
  ```
- **Resource limits.** For constrained hosts:
  ```yaml
  api:
    deploy:
      resources:
        limits:
          memory: 512M
  ```

---

### 5.6 Data Persistence

#### 5.6.1 Named volumes

| Volume | Mount point | Contains | Backup priority |
|--------|-------------|----------|-----------------|
| `pgdata` | `/var/lib/postgresql/data` | All PostgreSQL data (users, courses, skills, embeddings) | Critical |
| `uploads` | `/data/uploads` | Uploaded PDFs and documents | Critical |

**Why named volumes, not bind mounts.** Named volumes are managed by Docker, work across OS (Linux, macOS, Windows), and avoid permission issues. Bind mounts (`./data:/data`) break on Windows where UID/GID don't map and cause PostgreSQL to fail.

The admin can inspect volumes with `docker volume inspect skillnet_pgdata` to find the host path if they need direct access.

#### 5.6.2 Upload storage

Uploaded documents (PDFs, Markdown files) go to the `uploads` volume, organized as:

```
/data/uploads/
  {org_id}/
    {document_id}/
      original.pdf          # The file as uploaded
      extracted.md           # Parsed text content
```

The `api` service owns this volume. It handles both uploads and in-process background ingestion via the JobCoordinator.

#### 5.6.3 Backup strategy

**Database backup — `scripts/backup.sh`:**

```bash
#!/usr/bin/env bash
# SkillNet database backup script.
# Run manually or via cron: 0 3 * * * /path/to/skillnet/scripts/backup.sh

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/skillnet_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Backing up SkillNet database..."
docker compose exec -T db pg_dump \
  -U "${POSTGRES_USER:-skillnet}" \
  "${POSTGRES_DB:-skillnet}" \
  --clean --if-exists \
  | gzip > "$BACKUP_FILE"

echo "Backup saved to: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"

# Keep last 7 daily backups
find "$BACKUP_DIR" -name "skillnet_*.sql.gz" -mtime +7 -delete 2>/dev/null || true
echo "Old backups cleaned (kept last 7 days)."
```

**Restore:**

```bash
gunzip -c backups/skillnet_20260714_030000.sql.gz | \
  docker compose exec -T db psql -U skillnet skillnet
```

**Full backup (DB + uploads):**

```bash
# Stop services to ensure consistency
docker compose stop api

# Backup database
./scripts/backup.sh

# Backup uploads
tar -czf backups/uploads_$(date +%Y%m%d).tar.gz \
  $(docker volume inspect skillnet_uploads --format '{{.Mountpoint}}')

# Restart services
docker compose start api
```

**What we DON'T promise.** No automated scheduled backups, no cloud sync, no point-in-time recovery. This is self-hosted — the admin is responsible. The README documents how to back up and restore. Automated backups are a SaaS feature (future).

---

### 5.7 First-Run Experience

What happens when someone runs `docker compose up` for the first time.

#### 5.7.1 Startup sequence

```
docker compose up -d
  │
  ├─ db starts → PostgreSQL initializes empty database
  │
  ├─ api starts (waits for db healthy)
  │   ├─ Creates upload directory
  │   ├─ Runs Alembic migrations automatically
  │   │   ├─ Creates all tables (users, courses, skills, etc.)
  │   │   ├─ CREATE EXTENSION IF NOT EXISTS pgcrypto;
  │   │   └─ CREATE EXTENSION IF NOT EXISTS vector;
  │   ├─ Checks: does any user exist?
  │   │   ├─ No users + ADMIN_EMAIL set → creates admin account from env vars
  │   │   └─ No users + no ADMIN_EMAIL → first request to UI triggers /setup wizard
  │   ├─ Validates embedding configuration
  │   ├─ Starts JobCoordinator (in-process background task runner)
  │   └─ Healthcheck passes → ready
  │
  └─ web starts (waits for api healthy)
      └─ nginx begins serving on port 3000
```

#### 5.7.2 Database initialization

Migrations run on every API startup via Alembic. The entrypoint logic:

```python
# src/main.py — lifespan event
# Canonical definition in backend-api.md. Summary of startup steps:
#   1. Create upload directory
#   2. Run Alembic migrations (alembic upgrade head)
#   3. Maybe create admin account from env vars
#   4. Validate embedding configuration
#   5. Start JobCoordinator (in-process background task runner)
@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_upload_dir()
    run_migrations()  # alembic upgrade head
    await maybe_create_admin()
    validate_embedding_config()
    job_coordinator = JobCoordinator()
    await job_coordinator.start()
    yield
    await job_coordinator.stop()
```

This is idempotent. Running `docker compose up` ten times changes nothing after the first run. Alembic tracks which migrations have been applied.

**Extensions are created in the first migration:**

```python
# alembic/versions/001_initial.py
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    # ... create tables
```

No seed data beyond the optional admin account. SkillNet starts empty — the admin uploads their first document.

#### 5.7.3 Admin account creation

Two paths:

**Path A — Environment variables (headless, for scripted deployments):**

If `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set in `.env`, the API creates the admin account on first startup. No browser interaction needed. Useful for CI/CD, Terraform, Ansible deployments.

**Path B — Setup wizard (default, for humans):**

If no admin account exists and no `ADMIN_EMAIL` is set, the frontend shows `/setup` on first visit. The wizard:

1. **Create admin account** — email + password form.
2. **Name your organization** — company name, optional logo upload.
3. **Connect your AI** — choose provider, paste API key, test connection.
4. **Upload a document** (optional) — drag & drop a PDF to see the system in action.

After the wizard, the `/setup` route becomes inaccessible (returns 404). The admin lands on the company panel.

The wizard is a React route guarded by a backend check (`GET /api/v1/setup/status` returns `{ "needs_setup": true/false }`). The backend only allows setup operations when no users exist in the database.

---

### 5.8 Optional: Local LLM with Ollama

For fully offline deployments (healthcare, defense, air-gapped networks), Ollama runs as an additional service.

#### 5.8.1 `docker-compose.local-llm.yml`

```yaml
# SkillNet — Local LLM Override (Ollama)
# Usage: docker compose -f docker-compose.yml -f docker-compose.local-llm.yml up -d
#
# After starting, pull a model:
#   docker compose exec ollama ollama pull llama3.1
#   docker compose exec ollama ollama pull nomic-embed-text

services:
  ollama:
    image: ollama/ollama:latest
    restart: unless-stopped
    volumes:
      - ollama_models:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    # Uncomment for NVIDIA GPU support:
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]

  # Override API to point at Ollama
  api:
    environment:
      LLM_BASE_URL: http://ollama:11434/v1
      LLM_API_KEY: ollama  # Ollama ignores this but the client requires a value
      LLM_MODEL: ${LLM_MODEL:-llama3.1}
      EMBEDDING_BASE_URL: http://ollama:11434/v1
      EMBEDDING_API_KEY: ollama
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-nomic-embed-text}
    depends_on:
      ollama:
        condition: service_healthy

volumes:
  ollama_models:
    driver: local
```

#### 5.8.2 Usage

```bash
# Start with local LLM
docker compose -f docker-compose.yml -f docker-compose.local-llm.yml up -d

# Pull models (one-time, ~4 GB for llama3.1, ~270 MB for nomic-embed-text)
docker compose exec ollama ollama pull llama3.1
docker compose exec ollama ollama pull nomic-embed-text

# Verify
docker compose exec ollama ollama list
```

#### 5.8.3 Hardware requirements

| Setup | RAM | Disk | GPU | Notes |
|-------|-----|------|-----|-------|
| API-only (no local LLM) | 2 GB | 5 GB | None | External LLM via API key |
| Ollama + 7B model | 8 GB | 10 GB | Optional | CPU works, slow (~5 tok/s) |
| Ollama + 7B model + GPU | 8 GB | 10 GB | 6 GB+ VRAM | Fast (~40 tok/s) |
| Ollama + 70B model | 64 GB | 50 GB | 48 GB+ VRAM | Not recommended for SMEs |

**Recommendation for SMEs going offline:** Use a 7B-8B parameter model (Llama 3.1 8B, Mistral 7B). Quality is lower than cloud APIs but adequate for generating training content in structured formats. The admin can test quality during setup wizard step 3 (test connection).

### Optional: MCP Server

The MCP server (see mcp-external-api.md) is a Phase 2 feature. When ready, add it as a separate service via docker-compose.mcp.yml override.

---

### 5.9 Project file structure

Where all Docker-related files live in the repository:

```
SkillNet/
├── docker-compose.yml              # Production (the default)
├── docker-compose.dev.yml           # Development overrides
├── docker-compose.local-llm.yml     # Ollama override
├── .env.example                     # Template for .env
├── .env                             # Actual config (gitignored)
├── docker/
│   ├── api.Dockerfile               # Backend multi-stage build
│   ├── web.Dockerfile               # Frontend multi-stage build
│   └── nginx.conf                   # Nginx config for web service
├── scripts/
│   └── backup.sh                    # Database backup script
├── apps/
│   ├── skillnet-api/                # FastAPI backend source
│   └── skillnet-web/                # React frontend source
└── ...
```

---

### 5.10 Quick reference

```bash
# ── First time ───────────────────────────────────────────────
git clone https://github.com/ANFAIA/SkillNet.git
cd SkillNet
cp .env.example .env
nano .env                    # Set SECRET_KEY and POSTGRES_PASSWORD
docker compose up -d         # Everything starts
# Open http://localhost:3000 → setup wizard

# ── Daily operations ─────────────────────────────────────────
docker compose up -d         # Start
docker compose down          # Stop (data preserved in volumes)
docker compose logs -f api   # Watch API logs
docker compose restart api   # Restart a single service

# ── Updates ──────────────────────────────────────────────────
git pull
docker compose build         # Rebuild images with new code
docker compose up -d         # Restart with new images (migrations run automatically)

# ── Backup ───────────────────────────────────────────────────
./scripts/backup.sh          # Dumps DB to backups/ directory

# ── Development ──────────────────────────────────────────────
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
#   `--build` is not optional: the dev file overrides `target` to `builder`, and
#   without a build the api service reuses the `runtime` image, whose PATH has no
#   `uv`, and dies with `exec: "uv": executable file not found in $PATH`.
#   Sets DYNAMIC_COURSES_MODE=shadow by default.

# ── No API key at all (recorded fixtures, v2 on) ─────────────
docker compose --profile fixtures up -d db api-fixtures   # http://localhost:8001

# ── Demo data ────────────────────────────────────────────────
docker compose exec api python -m src.seed_demo             # v1
docker compose exec api uv run python -m src.seed_demo_v2   # v2 (bakery-café org)

# ── Offline mode (Ollama) ────────────────────────────────────
# There is no docker-compose.local-llm.yml; ollama is a profile in the main file.
docker compose --profile ollama up -d
docker compose exec ollama ollama pull llama3.1
```
