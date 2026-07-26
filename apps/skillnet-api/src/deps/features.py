"""Feature-flag route guards for v2 dynamic courses.

The three values of ``DYNAMIC_COURSES_MODE`` (§10.1):

| mode     | admin surface | employee surface |
|----------|---------------|------------------|
| `off`    | 404           | 404              |
| `shadow` | active        | 404              |
| `on`     | active        | active           |

``404`` rather than ``403`` on purpose: with the flag off the v2 routes must be
indistinguishable from routes that do not exist.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import Depends

from src.config import settings
from src.core.exceptions import AppError

Surface = Literal["admin", "employee"]

# Which modes expose which surface.
_ALLOWED_MODES: dict[Surface, frozenset[str]] = {
    "admin": frozenset({"shadow", "on"}),
    "employee": frozenset({"on"}),
}


def require_dynamic_courses(surface: Surface = "employee") -> Callable[[], str]:
    """Build a dependency that 404s unless ``surface`` is enabled by the flag.

    Returns the active mode, so a route may branch on ``shadow`` (e.g. only
    honouring ``?preview=1``) without reading the setting itself.
    """

    def _guard() -> str:
        mode = settings.DYNAMIC_COURSES_MODE
        if mode not in _ALLOWED_MODES[surface]:
            raise AppError(message="Not Found", code="NOT_FOUND", status_code=404)
        return mode

    return _guard


DynamicCoursesMode = Annotated[str, Depends(require_dynamic_courses("employee"))]
DynamicCoursesAdminMode = Annotated[str, Depends(require_dynamic_courses("admin"))]
