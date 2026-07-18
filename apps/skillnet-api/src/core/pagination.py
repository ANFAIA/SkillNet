"""Pagination helpers."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

MAX_LIMIT = 100
DEFAULT_LIMIT = 50


@dataclass(frozen=True)
class Page:
    """Bounded offset/limit pair."""

    offset: int
    limit: int


def paginate(offset: int, limit: int) -> Page:
    """Clamp offset/limit into safe bounds."""
    safe_offset = max(0, offset)
    safe_limit = min(max(1, limit), MAX_LIMIT)
    return Page(offset=safe_offset, limit=safe_limit)


class PaginationParams(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)

    def to_page(self) -> Page:
        return paginate(self.offset, self.limit)
