# syntax=docker/dockerfile:1
# SkillNet bug-report relay. Build context is the repo root.

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY apps/skillnet-relay/pyproject.toml apps/skillnet-relay/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY apps/skillnet-relay/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

RUN groupadd -r skillnet && \
    useradd -r -g skillnet -d /app -s /sbin/nologin skillnet && \
    mkdir /data && chown skillnet:skillnet /data

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_PATH=/data/relay.db

USER skillnet

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# One worker on purpose: reports are queued in the process and counted in one SQLite file.
CMD ["uvicorn", "src.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
