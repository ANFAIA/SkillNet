"""Domain exceptions mapped to HTTP responses by the global handlers in main.py."""

from typing import Any


class AppError(Exception):
    """Base class for all domain errors.

    ``details`` is an optional, machine-readable payload for errors whose cause needs more
    than a code and a field name — it is serialized under ``details`` by the handler in
    ``main.py`` and omitted entirely when unset, so the existing
    ``{detail, code, field}`` envelope is unchanged for every error that does not use it.
    It must contain only values the client is allowed to see.
    """

    def __init__(
        self,
        message: str,
        code: str = "APP_ERROR",
        status_code: int = 400,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.field = field
        self.details = details


class NotFoundError(AppError):
    def __init__(self, resource: str, id: str) -> None:
        super().__init__(
            message=f"{resource} with id {id} not found",
            code="NOT_FOUND",
            status_code=404,
        )
        self.resource = resource
        self.id = id


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden", field: str | None = None) -> None:
        super().__init__(message=message, code="FORBIDDEN", status_code=403, field=field)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", field: str | None = None) -> None:
        super().__init__(message=message, code="CONFLICT", status_code=409, field=field)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation error", field: str | None = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            field=field,
        )


class CapabilityBlockedError(AppError):
    """The deployment cannot do what was asked, and no retry will change that.

    Raised *before* any work is enqueued (``POST /media/artifacts``): the alternative,
    accepting the job and failing it half a minute later, is what made a missing image key
    look like a bug in the generator. ``409`` because the request is perfectly well formed
    — it is the deployment's state that conflicts with it, so there is nothing for the
    caller to correct in the body.

    ``message`` is what a learner may read, so it never names an environment variable or a
    provider; the actionable version is the capability's admin-only ``hint``.

    The code is lower-case where every older code in this module is upper-case. That is
    deliberate and not a slip: it is the string the media contract was written around and
    the one the SPA already matches on, and the two halves agreeing matters more than the
    casing. Renaming it means renaming it on both sides in the same commit.
    """

    def __init__(
        self,
        *,
        capability: str,
        reason: str | None,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="capability_blocked",
            status_code=409,
            field=capability,
            details={"capability": capability, "reason": reason, **(details or {})},
        )
        self.capability = capability
        self.reason = reason


class LLMError(AppError):
    def __init__(self, message: str = "LLM error", field: str | None = None) -> None:
        super().__init__(message=message, code="LLM_ERROR", status_code=502, field=field)
