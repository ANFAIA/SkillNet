"""Unit tests for the pure exercise grader (no DB, no LLM)."""

from src.services.exercise_service import grade


def test_grade_test_correct() -> None:
    result = grade("test", {"correct": 1, "explanation": "because"}, {"selected": 1})
    assert result.score == 1.0
    assert result.passed is True
    assert result.explanation == "because"


def test_grade_test_bare_int_and_wrong() -> None:
    assert grade("test", {"correct": 2}, 2).passed is True
    assert grade("test", {"correct": 2}, 0).score == 0.0


def test_grade_true_false() -> None:
    assert grade("true_false", {"correct": True}, {"answer": True}).passed is True
    result = grade("true_false", {"correct": True}, {"answer": False})
    assert result.score == 0.0
    assert result.passed is False


def test_grade_fill_blank_case_insensitive() -> None:
    content = {"blanks": ["Return", " Refund "]}
    assert grade("fill_blank", content, {"answers": ["return", "refund"]}).passed is True
    assert grade("fill_blank", content, {"answers": ["return", "wrong"]}).score == 0.0
    assert grade("fill_blank", content, {"answers": ["only-one"]}).score == 0.0


def test_grade_order_steps() -> None:
    content = {"correct_order": [0, 1, 2]}
    assert grade("order_steps", content, {"order": [0, 1, 2]}).passed is True
    assert grade("order_steps", content, {"order": [0, 2, 1]}).passed is False


def test_grade_open_answer_fallback() -> None:
    """The LLM-free fallback for the open types **passes** and says why.

    Updated for ``c68d045`` ("open exercise types now pass by default", 2026-07-21), which
    flipped ``passed`` to ``True`` and added "manual" to the feedback. The distinction the
    two halves of this suite keep is worth stating: this is ``grade``'s deterministic
    fallback, which lets a learner past an exercise nobody has read yet. The *LLM* grader's
    pending result (``src/services/llm_grading._pending``) still has ``passed=False`` and
    the shorter message — it is a grading attempt that failed, not a submission accepted on
    trust. ``tests/test_generation_pipeline.py`` pins that one.
    """
    for open_type in ("practical_case", "dialogue"):
        result = grade(open_type, {"rubric": "..."}, {"response": "text"})
        assert result.score == 0.5
        assert result.passed is True
        assert result.feedback == "Respuesta registrada. Pendiente de evaluacion manual."
        assert result.explanation is None
