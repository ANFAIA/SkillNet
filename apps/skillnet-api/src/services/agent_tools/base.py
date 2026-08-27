"""The ``ToolSpec`` contract every admin-agent tool is registered with.

Kept deliberately provider-agnostic: :meth:`ToolSpec.as_provider_schema` is the
only place that knows what litellm's ``tools=[...]`` wants, so a different
function-calling shape only touches one method.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.models import User

#: A handler is a plain async function, never a bound method on some service — it
#: is handed its own DB session, the admin invoking it (for org-scoping *and* for
#: audit fields like ``assigned_by``), and the model's parsed arguments. Returns
#: whatever JSON-serializable payload the model should read back as the result.
ToolHandler = Callable[[AsyncSession, "User", dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class ToolSpec:
    """One tool in the admin-agent catalog.

    ``name`` is ``{domain}_{verb}`` (``users_list``, ``enrollment_create``) —
    the namespace-by-prefix convention MCP tool catalogs use, so a model
    scanning many tool names can group them by domain before reading a single
    schema. ``domain``/``verb`` are kept as separate fields (not re-parsed from
    ``name``) so a future dynamic-loading layer can filter the registry by
    either axis without a string split.
    """

    name: str
    domain: str
    verb: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    requires_confirmation: bool = False

    def __post_init__(self) -> None:
        expected = f"{self.domain}_{self.verb}"
        if self.name != expected:
            raise ValueError(
                f"ToolSpec name '{self.name}' must equal '{expected}' "
                "(domain_verb convention)"
            )

    def as_provider_schema(self) -> dict[str, Any]:
        """The ``{"type": "function", "function": {...}}`` shape litellm expects."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
