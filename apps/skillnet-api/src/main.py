"""FastAPI application factory, lifespan, and global exception handlers."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import settings
from src.core.bootstrap import (
    ensure_organization,
    maybe_create_a2a_api_key,
    maybe_create_admin,
    run_migrations,
)
from src.core.exceptions import AppError
from src.core.logging import configure_logging, get_logger
from src.deps.auth import require_organization_workspace
from src.deps.db import async_session_factory, engine
from src.routes import (
    activities,
    ai,
    auth,
    chat,
    course_folders,
    course_schema,
    courses,
    documents,
    enrollments,
    exercises,
    explain,
    generation_jobs,
    health,
    learner_memory,
    learner_profile,
    lessons,
    media,
    nodes,
    onboarding,
    setup,
    skills,
    stats,
    talent,
    tts,
    users,
)
from src.routes import (
    settings as settings_routes,
)
from src.routes.ext import skills as ext_skills
from src.services.embedding_check import check_embedding_dimensions
from src.services.media import infographic as _infographic  # noqa: F401

# Importing the media generator packages registers each MediaGenerator under its kind,
# overriding the echo default (media spine, roadmap §2). Kept as explicit side-effect
# imports so the registry is populated wherever the app is imported, tests included:
# podcast (§2a), slides (§2c), infographic (§2d), video (§2b).
from src.services.media import podcast as _podcast  # noqa: F401
from src.services.media import slides as _slides  # noqa: F401
from src.services.media import video as _video  # noqa: F401

configure_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create upload dir %s: %s", settings.UPLOAD_DIR, exc)

    run_migrations()

    try:
        async with async_session_factory() as session:
            org = await ensure_organization(session)
            await maybe_create_admin(session)
            await maybe_create_a2a_api_key(session, org)
            # Despues de `run_migrations`, que es lo que fija la dimension de la columna.
            # Solo avisa: sin embeddings el resto del producto sigue en pie, asi que
            # tumbar el arranque seria peor que el fallo que se quiere hacer visible.
            await check_embedding_dimensions(session)
    except Exception as exc:  # noqa: BLE001
        logger.error("Bootstrap (org/admin) failed: %s", exc)

    yield

    await engine.dispose()


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, "field": exc.field},
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({"field": field, "message": error["msg"]})
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation failed",
            "code": "VALIDATION_ERROR",
            "errors": errors,
        },
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="SkillNet API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    prefix = "/api/v1"
    # Health at the app root for the Docker healthcheck, and under /api/v1.
    app.include_router(health.router)
    app.include_router(health.router, prefix=prefix)
    app.include_router(ai.router, prefix=prefix)
    app.include_router(activities.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    # Public, single-shot first-boot setup (closes once a user exists).
    app.include_router(setup.router, prefix=prefix)
    app.include_router(users.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(courses.router, prefix=prefix)
    app.include_router(course_folders.router, prefix=prefix)
    # Collective, organization-only surfaces: 404 in an individual workspace.
    # See docs/design/audience-modes.md and deps.auth.require_organization_workspace.
    org_only = [Depends(require_organization_workspace)]
    # skills: the standalone /skills catalogue is a talent concept and is gated
    # per-endpoint inside the router, but the course-authoring endpoints
    # (/courses/{id}/skills) are NOT — an individual owner still authors courses.
    app.include_router(skills.router, prefix=prefix)
    app.include_router(talent.router, prefix=prefix, dependencies=org_only)
    app.include_router(exercises.router, prefix=prefix)
    app.include_router(lessons.router, prefix=prefix)
    app.include_router(enrollments.router, prefix=prefix)
    app.include_router(generation_jobs.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix, tags=["Chat"])
    app.include_router(stats.router, prefix=prefix, dependencies=org_only)
    app.include_router(settings_routes.router, prefix=prefix)
    app.include_router(tts.router, prefix=prefix)
    # Rich-media artifacts (NotebookLM spine). Additive, own /media prefix.
    app.include_router(media.router, prefix=prefix)
    # v2 click-to-explain (B7). Its own guard 404s the route unless the flag is `on`.
    app.include_router(explain.router, prefix=prefix)
    # v2 onboarding and learner profile (B3). Both routers carry the employee-surface
    # flag guard, so every path is a 404 unless the flag is `on`.
    app.include_router(onboarding.router, prefix=prefix)
    app.include_router(learner_profile.router, prefix=prefix)
    # The learner's own narrative memory ("user.md"): GDPR self-service, employee-only. The
    # extra /memory segment cannot be shadowed by /users/{user_id} — same reasoning as
    # learner_profile above.
    app.include_router(learner_memory.router, prefix=prefix)
    # v2 admin course schema (B2). Registered after `courses` so the more specific
    # /courses/{id}/schema* paths are matched by their own router; the admin-surface
    # guard 404s every path unless the flag is `shadow` or `on`.
    app.include_router(course_schema.router, prefix=prefix)
    # v2 runtime employee surface (B5). Registered after `courses` so the more specific
    # /courses/{id}/nodes path is matched by its own router; both routers carry the
    # employee-surface guard, so every path 404s unless the flag is `on`.
    app.include_router(nodes.router, prefix=prefix)
    app.include_router(nodes.course_nodes_router, prefix=prefix)
    app.include_router(nodes.render_kit_router, prefix=prefix)

    ext_prefix = "/ext/v1"
    app.include_router(ext_skills.router, prefix=ext_prefix)
    app.include_router(ext_skills.user_router, prefix=ext_prefix)

    return app


app = create_app()
