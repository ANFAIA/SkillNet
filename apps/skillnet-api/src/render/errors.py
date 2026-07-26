"""Errors raised by the render layer (§5).

``RenderValidationError`` deliberately subclasses ``RenderParseError``: §5.4 freezes
``RenderBackend.parse`` as "lanza RenderParseError", and a program can be
grammatically perfect yet break one of the seven contract rules of §5.2. A single
``except RenderParseError`` therefore catches both, which is what
``validate_ui`` (§4.2) needs in order to fill ``validation_errors`` and take the
repair path.

All of them carry ``errors: list[str]`` — the exact strings that go into
``NodeRuntimeState.validation_errors`` and into the ``UI_REPAIR_SYSTEM`` prompt.
"""

from __future__ import annotations

from src.core.exceptions import AppError


class RenderError(AppError):
    """Base class for render-layer failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "RENDER_ERROR",
        status_code: int = 422,
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code)
        self.errors: list[str] = list(errors) if errors else [message]


class RenderParseError(RenderError):
    """The dialect could not be turned into a ``UISpec``."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "RENDER_PARSE_ERROR",
        line_no: int | None = None,
        line: str | None = None,
        errors: list[str] | None = None,
    ) -> None:
        prefixed = f"line {line_no}: {message}" if line_no is not None else message
        super().__init__(prefixed, code=code, errors=errors or [prefixed])
        self.line_no = line_no
        self.line = line


class RenderValidationError(RenderParseError):
    """The spec parsed but broke one or more of the seven contract rules of §5.2."""

    def __init__(self, errors: list[str], message: str | None = None) -> None:
        detail = message or "; ".join(errors) or "invalid UI spec"
        super().__init__(detail, code="RENDER_VALIDATION_ERROR", errors=errors)
