# syntax=docker/dockerfile:1
# SkillNet API — multi-stage build with uv. Build context is the repo root.

# ── Stage 1: Dependencies + project install ──────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ffmpeg: the media pipeline (podcast/video) concatenates per-turn TTS segments with it
# when the single-call dialogue path is unavailable. The dev image targets this `builder`
# stage, so it must live here as well as in runtime.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

# `PYTHONUNBUFFERED` and `PYTHONDONTWRITEBYTECODE` are set in the *builder* stage on
# purpose, so `runtime` inherits them too. They used to live only in `runtime`, and
# `docker/compose/dev.yml` builds `target: builder` — so development lost two things:
# anything written to `stdout` (uvicorn's access log, arriving in 8 KB blocks, and every
# `print()`, which is how the seed scripts talk when run without a TTY), and `.pyc` files
# were written into the bind-mounted host source tree.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

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

# ffmpeg for audio concatenation in the media (podcast/video) pipeline; espeak-ng is the
# offline, no-key/no-quota TTS safety net beneath the cloud voice providers.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

# `uv` in runtime too, and it is not a 30 MB indulgence: without it `uv run ...` works
# only in the development image and bare `python ...` only in the production one, because
# the venv `PATH` is added just below. Every documented command was therefore valid in
# exactly one of the two modes — including the two the README prints three lines apart.
# With this, `docker compose exec api uv run python -m src.seed_learning_demo` works in both.
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

ENV PATH="/app/.venv/bin:$PATH" \
    UPLOAD_DIR=/data/uploads

# All THREE mount points the compose files declare, not just uploads.
#
# A named volume takes its ownership from whatever the image has at the mount point: a
# directory that exists here is copied in with its owner, and one that does NOT is created
# by Docker as root:root, mode 755 — unwritable for the `skillnet` user this image runs as.
# So `uploads` worked and `media_assets` / `tts_cache` did not, which meant every podcast
# and every infographic died on `PermissionError: [Errno 13] Permission denied:
# '/data/media_assets/...'` in a clean `docker compose up`. Measured: 14 of 14 artifacts of
# the demo seed. Creating them here is what makes the volumes inherit the right owner.
RUN mkdir -p /data/uploads /data/media_assets /data/tts_cache \
    && chown -R skillnet:skillnet /data /app

USER skillnet

EXPOSE 8000

# Migrations run on startup via the app lifespan (alembic upgrade head).
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
