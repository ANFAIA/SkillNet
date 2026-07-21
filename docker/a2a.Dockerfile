# syntax=docker/dockerfile:1
# SkillNet A2A Server — multi-stage build with uv. Build context is the repo root.

# ── Stage 1: Dependencies + project install ──────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependency layer first for caching: only the manifest.
COPY apps/skillnet-a2a/pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project || uv pip install -r pyproject.toml

# Application source, then install the project itself.
COPY apps/skillnet-a2a/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev || true

# ── Stage 2: Runtime ─────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN groupadd -r skillnet && \
    useradd -r -g skillnet -d /app -s /sbin/nologin skillnet

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chown -R skillnet:skillnet /app

USER skillnet

EXPOSE 5000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
