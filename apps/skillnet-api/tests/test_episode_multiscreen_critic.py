"""Multi-screen episode prompt + lean pedagogy critic.

Two guarantees this batch must not lose:

* The worked multi-screen example baked into the episode generator prompt is COMPLETE and
  gate-valid, so a small model copying its structure does not fall back (the Phase-1
  lesson: a malformed program tanks live renders).
* The critic is advisory and fail-open: malformed or empty output never forces a revision
  and never breaks the render.
"""

from __future__ import annotations

import re

import pytest

from src.agents.runtime.agents.episode_critic import CriticVerdict, run_episode_critic
from src.agents.runtime.nodes import (
    _root_child_count,
    missing_answer_keys,
    split_answer_key,
)
from src.llm.prompts.runtime import (
    EPISODE_PROMPT_VERSION,
    episode_ui_generator_system,
)
from src.render.backends import get_render_backend
from src.render.gate import canonicalize


def _extract_programs(text: str) -> list[str]:
    """Every ``root = Stack(...)`` block (through its blank-line terminator) in the prompt."""

    programs: list[str] = []
    for match in re.finditer(r"^root = Stack\(.*?(?=\n\n|\Z)", text, re.DOTALL | re.MULTILINE):
        programs.append(match.group(0))
    return programs


def test_episode_prompt_advertises_multiscreen_flow() -> None:
    system = episode_ui_generator_system()
    assert EPISODE_PROMPT_VERSION == "episode/8"
    assert "FLUJO de PANTALLAS" in system


def test_every_worked_example_in_the_episode_prompt_is_gate_valid() -> None:
    system = episode_ui_generator_system()
    backend = get_render_backend("openui")
    programs = _extract_programs(system)
    # The multiscreen section adds at least the 3-screen and the 2-screen examples.
    multi = [p for p in programs if "pantallaChequeo" in p or "practica = Flashcard" in p]
    assert len(multi) >= 2, "multi-screen worked examples missing from the prompt"

    for program in multi:
        text, answer_key = split_answer_key(program)
        spec, _canonical = canonicalize(text, ui_format="explanation", backend=backend)
        # Rule 7 holds (first root child is a lead), and any QuizItem has its key.
        assert _root_child_count(spec.model_dump()) >= 1
        assert missing_answer_keys(spec, answer_key) == []


def test_root_child_count_reads_screens_from_the_spec() -> None:
    spec = {
        "root": "root",
        "components": [
            {"id": "root", "type": "Stack", "children": ["a", "b", "c"]},
            {"id": "a", "type": "TextContent"},
        ],
    }
    assert _root_child_count(spec) == 3
    assert _root_child_count({}) == 0
    assert _root_child_count(None) == 0


class _FakeLLM:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.model = "fake"

    async def complete_with_usage(self, system, user, **kwargs):  # noqa: ANN001
        from types import SimpleNamespace

        return self.raw, SimpleNamespace(tokens_in=1, tokens_out=1, reason=None)


@pytest.mark.asyncio
async def test_critic_parses_actionable_verdict() -> None:
    llm = _FakeLLM('{"revise": true, "notes": ["Demasiado test; anade una practica."]}')
    verdict = await run_episode_critic(
        title="t", summary="s", domain="boxeo", program="root = Stack([a], \"md\")",
        screen_count=1, assessment_mode="none", llm=llm,
    )
    assert isinstance(verdict, CriticVerdict)
    assert verdict.actionable is True
    assert verdict.notes


@pytest.mark.asyncio
async def test_critic_is_fail_open_on_garbage_and_on_no_revision() -> None:
    # Unparseable output -> no revision, no raise.
    bad = await run_episode_critic(
        title="t", summary="s", domain="", program="p",
        screen_count=2, assessment_mode="none", llm=_FakeLLM("not json at all"),
    )
    assert bad.actionable is False

    # Explicit "revise false" -> not actionable even if notes are present.
    ok = await run_episode_critic(
        title="t", summary="s", domain="", program="p",
        screen_count=2, assessment_mode="none",
        llm=_FakeLLM('{"revise": false, "notes": ["nit"]}'),
    )
    assert ok.actionable is False
