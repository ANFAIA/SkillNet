"""Domain exceptions mapped to HTTP responses by the global handlers in main.py."""


class AppError(Exception):
    """Base class for all domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "APP_ERROR",
        status_code: int = 400,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.field = field


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


class LLMError(AppError):
    def __init__(self, message: str = "LLM error", field: str | None = None) -> None:
        super().__init__(message=message, code="LLM_ERROR", status_code=502, field=field)
