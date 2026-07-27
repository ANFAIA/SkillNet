"""Render backend registry (§5.4).

One dialect in this PR. The seam exists so a second one is a new module plus one
entry here; no caller outside this package names a dialect.
"""

from __future__ import annotations

from src.config import settings
from src.render.backends.base import RenderBackend
from src.render.backends.openui import OpenUiLangBackend
from src.render.errors import RenderError

_BACKENDS: dict[str, RenderBackend] = {"openui": OpenUiLangBackend()}


def get_render_backend(name: str | None = None) -> RenderBackend:
    """Resolve a backend by name, defaulting to ``settings.RENDER_BACKEND``."""
    key = name or settings.RENDER_BACKEND
    backend = _BACKENDS.get(key)
    if backend is None:
        available = ", ".join(sorted(_BACKENDS))
        raise RenderError(
            f"unknown render backend {key!r}; available: {available}",
            code="RENDER_BACKEND_UNKNOWN",
            status_code=500,
        )
    return backend


def available_backends() -> tuple[str, ...]:
    return tuple(sorted(_BACKENDS))


__all__ = [
    "OpenUiLangBackend",
    "RenderBackend",
    "available_backends",
    "get_render_backend",
]
