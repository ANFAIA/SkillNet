# syntax=docker/dockerfile:1
# SkillNet API — multi-stage build with uv. Build context is the repo root.

# ── Stage 1: Dependencies + project install ──────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependency layer first for caching: only the lock + manifest.
COPY apps/skillnet-api/pyproject.toml apps/skillnet-api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Application source, then install the project itself.
COPY apps/skillnet-api/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Stage 2: Runtime ─────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN groupadd -r skillnet && \
    useradd -r -g skillnet -d /app -s /sbin/nologin skillnet

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UPLOAD_DIR=/data/uploads

RUN mkdir -p /data/uploads && chown -R skillnet:skillnet /data /app

USER skillnet

EXPOSE 8000

# Migrations run on startup via the app lifespan (alembic upgrade head).
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
