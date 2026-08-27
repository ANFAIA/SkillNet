"""The admin agent's tool catalog and confirmation gate.

No DB, no LLM: these test the two properties the whole design depends on and
that a live provider call would hide if they broke —

1. every tool in the registry actually follows the ``domain_verb`` naming
   convention (``ToolSpec.__post_init__`` enforces it per-tool; this asserts
   the *registered* set, catching a future domain module that slips past it
   only if it were ever bypassed), and provider schemas are well-formed;
2. a write tool never runs without a confirmation from the *user's* turn, and
   a read tool always runs regardless.
"""

from __future__ import annotations

import pytest

from src.services.admin_agent_service import _looks_like_confirmation, confirmation_error
from src.services.agent_tools import registry
from src.services.agent_tools.base import ToolSpec


def test_registry_has_no_duplicate_names() -> None:
    names = [tool.name for tool in registry.REGISTRY.values()]
    assert len(names) == len(set(names))


def test_every_tool_name_matches_domain_verb_convention() -> None:
    for tool in registry.REGISTRY.values():
        assert tool.name == f"{tool.domain}_{tool.verb}"


def test_provider_schemas_are_well_formed_function_specs() -> None:
    schemas = registry.provider_schemas()
    assert len(schemas) == len(registry.REGISTRY)
    for schema in schemas:
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"] in registry.REGISTRY
        assert isinstance(function["description"], str) and function["description"]
        assert function["parameters"]["type"] == "object"


def test_no_delete_style_tools_are_registered_for_documents_or_courses() -> None:
    """Destructive verbs on documents/courses stay UI-only (see the plan's
    explicit out-of-scope list); only the reviewed ``enrollment_delete`` exists."""
    destructive = {
        name for name, tool in registry.REGISTRY.items() if tool.verb == "delete"
    }
    assert destructive == {"enrollment_delete"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("si, adelante", True),
        ("vale, hazlo", True),
        ("yes, go ahead", True),
        ("confirm", True),
        ("no, espera", False),
        ("cuantos empleados hay", False),
        ("", False),
    ],
)
def test_looks_like_confirmation(text: str, expected: bool) -> None:
    assert _looks_like_confirmation(text) is expected


def test_read_tool_never_needs_confirmation() -> None:
    assert confirmation_error(False, confirmed=False) is None
    assert confirmation_error(False, confirmed=True) is None


def test_write_tool_without_confirmation_is_refused() -> None:
    error = confirmation_error(True, confirmed=False)
    assert error is not None
    assert "confirm" in error.lower()


def test_write_tool_with_confirmation_is_allowed() -> None:
    assert confirmation_error(True, confirmed=True) is None


def test_tool_spec_rejects_a_name_that_does_not_match_domain_verb() -> None:
    async def _handler(db, user, args):  # pragma: no cover - never called
        return {}

    with pytest.raises(ValueError):
        ToolSpec(
            name="wrong_name",
            domain="users",
            verb="list",
            description="x",
            parameters={"type": "object", "properties": {}},
            handler=_handler,
        )
