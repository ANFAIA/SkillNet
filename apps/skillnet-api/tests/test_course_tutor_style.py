"""Per-course tutor style (socratic/direct): auto-detection parsing, prompt wiring,
and the admin-editable validation path.

Three independent properties, one file because they are all small and about the
same feature:

1. the schema designer's ``tutor_style`` pick is parsed defensively — absent or
   invalid never reaches the DB, it falls back to ``"socratic"``;
2. the tutor's system prompt actually changes text depending on the style, for
   both the plain and single-phase-GenUI variants;
3. ``CourseService.update`` validates a ``tutor_style`` change the same way it
   already validates ``artifact_generate_policy`` — bad value -> ``ValidationError``,
   good value -> cast to the enum and persisted.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.schema.nodes import _nodes_from_response, _tutor_style_from_response
from src.core.exceptions import ValidationError
from src.llm.prompts.tutor import tutor_genui_system_prompt, tutor_system_prompt
from src.models import ArtifactGeneratePolicy, CourseTutorStyle
from src.services.course_service import CourseService


# --------------------------------------------------------------------------------------
# 1. Parsing the designer's response
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"tutor_style": "direct"}, "direct"),
        ({"tutor_style": "socratic"}, "socratic"),
        ({"nodes": []}, "socratic"),  # absent -> default
        ({"tutor_style": "chaotic"}, "socratic"),  # invalid value -> default
        ({"tutor_style": None}, "socratic"),
        ([], "socratic"),  # bare list response, no top-level dict at all
    ],
)
def test_tutor_style_from_response(raw, expected) -> None:
    assert _tutor_style_from_response(raw) == expected


def test_nodes_from_response_is_unaffected_by_the_new_field() -> None:
    parsed = {
        "nodes": [{"title": "x", "summary": "y"}],
        "tutor_style": "direct",
        "notes": [],
    }
    assert _nodes_from_response(parsed) == [{"title": "x", "summary": "y"}]


# --------------------------------------------------------------------------------------
# 2. The tutor prompt actually changes with the style
# --------------------------------------------------------------------------------------
def test_tutor_system_prompt_differs_by_style() -> None:
    socratic = tutor_system_prompt("general", "socratic")
    direct = tutor_system_prompt("general", "direct")
    assert socratic != direct
    assert "pregunta" in socratic.lower()
    assert "directo" in direct.lower()


def test_tutor_system_prompt_defaults_to_socratic() -> None:
    assert tutor_system_prompt("general") == tutor_system_prompt("general", "socratic")


def test_tutor_system_prompt_falls_back_on_an_unknown_style() -> None:
    """A stale/garbage value read off the DB degrades to the default block,
    never a ``KeyError`` mid-stream."""
    assert tutor_system_prompt("general", "chaotic") == tutor_system_prompt(
        "general", "socratic"
    )


def test_tutor_genui_system_prompt_differs_by_style() -> None:
    socratic = tutor_genui_system_prompt("general", "socratic")
    direct = tutor_genui_system_prompt("general", "direct")
    assert socratic != direct


# --------------------------------------------------------------------------------------
# 3. CourseService.update validates tutor_style like artifact_generate_policy
# --------------------------------------------------------------------------------------
def _repo(**overrides):
    defaults = dict(
        get_scoped=AsyncMock(),
        update=AsyncMock(side_effect=lambda course, **kwargs: course),
    )
    defaults.update(overrides)
    return SimpleNamespace(session=SimpleNamespace(), **defaults)


@pytest.mark.asyncio
async def test_update_rejects_an_invalid_tutor_style() -> None:
    course = SimpleNamespace(
        id=uuid.uuid4(),
        tutor_style=CourseTutorStyle.SOCRATIC,
        artifact_generate_policy=ArtifactGeneratePolicy.ADMIN,
    )
    repo = _repo(get_scoped=AsyncMock(return_value=course))

    with pytest.raises(ValidationError):
        await CourseService(repo).update(
            course_id=course.id,
            org_id=uuid.uuid4(),
            changes={"tutor_style": "chaotic"},
        )


@pytest.mark.asyncio
async def test_update_accepts_a_valid_tutor_style() -> None:
    course = SimpleNamespace(
        id=uuid.uuid4(),
        tutor_style=CourseTutorStyle.SOCRATIC,
        artifact_generate_policy=ArtifactGeneratePolicy.ADMIN,
    )
    repo = _repo(get_scoped=AsyncMock(return_value=course))

    updated = await CourseService(repo).update(
        course_id=course.id,
        org_id=uuid.uuid4(),
        changes={"tutor_style": "direct"},
    )

    assert updated is course
    repo.update.assert_awaited_once_with(course, tutor_style=CourseTutorStyle.DIRECT)
