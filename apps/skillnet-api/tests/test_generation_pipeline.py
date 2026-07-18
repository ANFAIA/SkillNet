"""Unit tests for the generation pipeline (no network, no DB).

Covers quality-review routing, module-JSON parsing, graph compilation, and
LLM-based open-answer grading with a stubbed LLM.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.content.routing import route_after_quality_review
from src.llm.parsing import parse_json_response
from src.services.llm_grading import grade_open_answer


# --------------------------------------------------------------------------- #
# route_after_quality_review — every branch
# --------------------------------------------------------------------------- #
def test_route_no_report_fails() -> None:
    assert route_after_quality_review({}) == "fail"
    assert route_after_quality_review({"review_report": None}) == "fail"


def test_route_passed_report() -> None:
    state = {"review_report": {"passed": True, "issues": []}}
    assert route_after_quality_review(state) == "pass"


def test_route_budget_exhausted_passes() -> None:
    state = {
        "review_report": {
            "passed": False,
            "issues": [{"severity": "critical"}],
        },
        "refinement_count": 2,
    }
    assert route_after_quality_review(state) == "pass"


def test_route_critical_issue_refines() -> None:
    state = {
        "review_report": {
            "passed": False,
            "issues": [{"severity": "minor"}, {"severity": "critical"}],
        },
        "refinement_count": 0,
    }
    assert route_after_quality_review(state) == "refine"


def test_route_all_minor_passes() -> None:
    state = {
        "review_report": {
            "passed": False,
            "issues": [{"severity": "minor"}, {"severity": "minor"}],
        },
        "refinement_count": 0,
    }
    assert route_after_quality_review(state) == "pass"


def test_route_major_issue_refines() -> None:
    state = {
        "review_report": {
            "passed": False,
            "issues": [{"severity": "major"}],
        },
        "refinement_count": 0,
    }
    assert route_after_quality_review(state) == "refine"


# --------------------------------------------------------------------------- #
# parse a module-generator JSON response
# --------------------------------------------------------------------------- #
def test_parse_module_generator_json() -> None:
    raw = """```json
    {
      "lessons": [
        {"title": "Intro", "position": 1, "content": "# Hola", "citations": []}
      ],
      "exercises": [
        {"type": "test", "content": {"question": "q", "options": ["a", "b"],
         "correct": 0, "explanation": "e"}, "position": 1}
      ]
    }
    ```"""
    data = parse_json_response(raw)
    assert data["lessons"][0]["title"] == "Intro"
    assert data["exercises"][0]["type"] == "test"
    assert data["exercises"][0]["content"]["correct"] == 0


# --------------------------------------------------------------------------- #
# graph compiles
# --------------------------------------------------------------------------- #
def test_build_content_graph_compiles() -> None:
    from src.agents.content.graph import build_content_graph

    graph = build_content_graph()
    assert graph is not None


# --------------------------------------------------------------------------- #
# grade_open_answer with a stubbed LLM
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_grade_open_answer_with_stubbed_llm() -> None:
    llm = SimpleNamespace(
        complete=AsyncMock(return_value='{"score": 0.9, "passed": true, "feedback": "ok"}')
    )
    content = {
        "context": "ctx",
        "question": "q",
        "rubric": [{"criteria": "menciona politica", "required": True}],
    }
    result = await grade_open_answer(llm, "practical_case", content, {"response": "text"})
    assert result.score == 0.9
    assert result.passed is True
    assert result.feedback == "ok"
    llm.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_grade_open_answer_clamps_and_thresholds() -> None:
    llm = SimpleNamespace(
        complete=AsyncMock(return_value='{"score": 1.9, "feedback": "x"}')
    )
    result = await grade_open_answer(llm, "dialogue", {"evaluation_criteria": []}, "hi")
    assert result.score == 1.0
    assert result.passed is True


@pytest.mark.asyncio
async def test_grade_open_answer_llm_error_returns_pending() -> None:
    from src.core.exceptions import LLMError

    llm = SimpleNamespace(complete=AsyncMock(side_effect=LLMError("boom")))
    result = await grade_open_answer(llm, "practical_case", {"rubric": []}, "x")
    assert result.score == 0.5
    assert result.passed is False
    assert result.feedback == "Respuesta registrada. Pendiente de evaluacion."
