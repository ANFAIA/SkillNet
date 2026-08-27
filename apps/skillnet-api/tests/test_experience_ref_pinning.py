"""The server's authority over ``LearningExperience`` refs, and the closers a repair may name.

Both regressions here were measured in local production on 2026-08-27, where half of all
``node_renders`` (17 of 34) were serving a flat fallback seed instead of the generated lesson:

* ``implementation_ref must pin a version`` was 11 of 13 gate rejections. The server has a
  net for exactly that (``_pin_authored_experience_refs``), but it read ``authored_activity``
  with different fallbacks than the prompt builder did, so on the legacy authoring path the
  net silently no-opped and the model was left copying an opaque versioned id by hand.
* A repair message named ``DragOrder`` as the way out of a screen where the Didact
  prohibition then rejected ``DragOrder`` — an unsatisfiable loop that burns every attempt.
"""

import uuid

from src.agents.runtime.nodes import (
    _allowed_closers,
    _authored_experience_refs,
    _forbidden_closers,
    _offerable_closers,
    _pin_authored_experience_refs,
    _source_with_authored_activity,
)
from src.render.spec import Component
from src.services.activity_authoring import MaterializedActivity

ACTIVITY_ID = uuid.UUID(int=7)
PROGRAM = 'cierre = LearningExperience("exp_inventado", "impl_ref", "def_ref")'


def legacy_authored() -> dict:
    """What the LLM-authoring path actually puts in state: ``activity_authoring_status='ready'``.

    ``MaterializedActivity`` is ``extra="forbid"`` with three fields and none of them is a
    ref, so anything reading ``implementation_ref`` off it gets nothing. Built through the
    real model on purpose: a hand-written dict would not catch the day someone adds the refs.
    """
    return MaterializedActivity(
        activity_id=ACTIVITY_ID,
        component_id="didact.matching",
        public_definition={"prompt": "empareja"},
    ).model_dump(mode="json")


def unpinnable_authored() -> dict:
    """A dict from which **no** triple can be derived, which is not the same as no dict.

    The legacy path stores a ``MaterializedActivity``; when its ``component_id`` never
    arrived there is no ``implementation_ref`` to build, so the server has nothing to pin
    even though ``authored_activity`` is populated. Asking "is it a dict?" instead of "can
    it be pinned?" is what made the gate contradict itself.
    """
    return {"activity_id": str(ACTIVITY_ID), "component_id": "", "public_definition": {}}


def prepared_authored() -> dict:
    """What the prepared path (migration 0016) puts in state: the three refs, explicit."""
    return {
        "activity_id": str(ACTIVITY_ID),
        "component_id": "didact.matching",
        "experience_id": "binding-1",
        "implementation_ref": "didact.matching@4",
        "definition_ref": "def-1",
        "intent_id": "intent-1",
    }


# --------------------------------------------------------------------------- #
# The derivation itself
# --------------------------------------------------------------------------- #
def test_legacy_materialized_activity_still_yields_a_pinned_triple() -> None:
    refs = _authored_experience_refs(legacy_authored())

    assert refs is not None, "the legacy path must still produce a pinnable triple"
    experience_id, implementation_ref, definition_ref = refs
    assert implementation_ref == "didact.matching@1"
    assert experience_id == str(ACTIVITY_ID)
    assert definition_ref == str(ACTIVITY_ID)


def test_prepared_refs_are_used_verbatim_and_not_re_derived() -> None:
    refs = _authored_experience_refs(prepared_authored())

    assert refs == ("binding-1", "didact.matching@4", "def-1")


def test_no_component_id_and_no_refs_means_nothing_to_pin() -> None:
    """The signal that the screen must close some other way, rather than a bogus ``@1``."""
    assert _authored_experience_refs({"activity_id": str(ACTIVITY_ID)}) is None
    assert _authored_experience_refs({}) is None


# --------------------------------------------------------------------------- #
# The net actually firing — the production regression
# --------------------------------------------------------------------------- #
def test_pinning_rewrites_invented_refs_on_the_legacy_path() -> None:
    """The regression: this used to be a no-op, so every such screen fell back."""
    pinned = _pin_authored_experience_refs(
        PROGRAM, {"authored_activity": legacy_authored()}
    )

    assert pinned != PROGRAM
    assert '"didact.matching@1"' in pinned
    assert "impl_ref" not in pinned
    assert "exp_inventado" not in pinned


def test_pinning_rewrites_invented_refs_on_the_prepared_path() -> None:
    pinned = _pin_authored_experience_refs(
        PROGRAM, {"authored_activity": prepared_authored()}
    )

    assert 'LearningExperience("binding-1", "didact.matching@4", "def-1")' in pinned


def test_a_pinned_program_passes_the_gate_rule_that_used_to_reject_it() -> None:
    """End of the loop: what the server pins must satisfy the validator, or nothing improved."""
    _, implementation_ref, _ = _authored_experience_refs(legacy_authored())

    assert _gate_errors(implementation_ref) == []


def test_the_gate_still_rejects_a_ref_with_no_version_and_says_how_to_fix_it() -> None:
    """The rule is not relaxed; it only became actionable. Models were sending
    ``impl_ref`` -> ``impl_ref_v1``, hunting a suffix instead of the ``@`` separator."""
    errors = _gate_errors("impl_ref_v1")

    assert len(errors) == 1
    assert "id@version" in errors[0]


def test_prompt_and_pinning_cannot_disagree_about_the_ref() -> None:
    """The root cause was two readers of one dict with different fallbacks. If they ever
    drift again, the prompt teaches one ref and the gate pins another, and this fails."""
    authored = legacy_authored()
    _, implementation_ref, _ = _authored_experience_refs(authored)

    prompt = _source_with_authored_activity(
        {"source_context": "fuente", "authored_activity": authored}
    )

    assert implementation_ref in prompt
    assert implementation_ref in _pin_authored_experience_refs(
        PROGRAM, {"authored_activity": authored}
    )


def test_prompt_offers_no_experience_when_none_can_be_pinned() -> None:
    """No derivable triple must not become an invented instruction the gate then refuses."""
    prompt = _source_with_authored_activity(
        {"source_context": "fuente", "authored_activity": {"activity_id": "x"}}
    )

    assert prompt == "fuente"
    assert "LearningExperience" not in prompt


# --------------------------------------------------------------------------- #
# A repair may only name a closer this screen is allowed to emit
# --------------------------------------------------------------------------- #
def test_declined_authoring_allows_a_dragorder_to_close_a_didact_screen() -> None:
    """The measured deadlock: ``screen_scheme`` instructed "cierra con DragOrder" for an
    ordered procedure while the Didact prohibition refused DragOrder, so an obedient model
    could not win and the node served a flat seed with no interaction at all. With no prepared
    experience the prohibition has nothing to guard, so a real answer-keyed interaction
    stands."""
    state = {"assessment_block": "DidactActivity"}

    assert _allowed_closers(state) == {"QuizItem", "DragOrder"}
    assert "DragOrder" in _offerable_closers(state)


def test_a_prepared_experience_still_cannot_be_swapped_for_an_invented_quiz() -> None:
    """The prohibition keeps its full teeth where its rationale applies: when the server
    prepared a tracked, server-corrected experience, the screen closes on THAT."""
    state = {
        "assessment_block": "DidactActivity",
        "authored_activity": prepared_authored(),
    }

    assert _allowed_closers(state) == {"LearningExperience"}
    assert "QuizItem" not in _allowed_closers(state)
    assert "DragOrder" not in _allowed_closers(state)


def test_didact_screen_with_an_experience_is_offered_the_experience() -> None:
    closers = _offerable_closers(
        {"assessment_block": "DidactActivity", "authored_activity": prepared_authored()}
    )

    assert closers == ("LearningExperience",)


def test_outside_didact_mode_both_real_closers_stay_available() -> None:
    """The narrowing is contextual, not a blanket ban: a plain screen keeps both options."""
    assert _offerable_closers({"assessment_block": "QuizItem"}) == (
        "QuizItem",
        "DragOrder",
    )
    assert _offerable_closers({}) == ("QuizItem", "DragOrder")


def test_an_activity_payload_that_cannot_be_pinned_counts_as_no_experience() -> None:
    """The second way into the "authoring declined" state, and the one that deadlocked.

    ``validate_ui`` refuses a ``LearningExperience`` whenever no full triple can be derived,
    so this state reaches the branch that tells the model to close some other way. The
    closer policy asked a different question — "is ``authored_activity`` a dict?" — answered
    ``{"LearningExperience"}``, and the repair message then read "NO uses LearningExperience
    ... cierra con un LearningExperience" while the prohibition one rule later forbade both
    real closers. Every closer forbidden, none offerable: the exact deadlock the fallback
    measurements of 2026-08-27 were about, through a second door.
    """
    state = {
        "assessment_block": "DidactActivity",
        "authored_activity": unpinnable_authored(),
    }

    assert _allowed_closers(state) == {"QuizItem", "DragOrder"}
    assert _forbidden_closers(state) == frozenset()
    assert _offerable_closers(state) == ("QuizItem", "DragOrder")
    assert "LearningExperience" not in _offerable_closers(state)


def test_every_offered_closer_is_one_the_didact_prohibition_accepts() -> None:
    """The invariant behind both message fixes, stated directly: what a repair proposes must
    survive the rule that runs right after it.

    Read from ``_forbidden_closers``, which is the derivation the gate itself uses —
    including its scope, so a screen the prohibition never runs on cannot look "forbidden"
    to one function and "allowed" to the other.
    """
    for state in (
        {"assessment_block": "DidactActivity"},
        {"assessment_block": "DidactActivity", "authored_activity": prepared_authored()},
        {"assessment_block": "DidactActivity", "authored_activity": legacy_authored()},
        {"assessment_block": "DidactActivity", "authored_activity": unpinnable_authored()},
        {"assessment_block": "DidactActivity", "authored_activity": {}},
        {"assessment_block": "DidactActivity", "authored_activity": None},
        {"assessment_block": "QuizItem"},
        {"assessment_block": "DragOrder", "authored_activity": unpinnable_authored()},
        {},
    ):
        offered = set(_offerable_closers(state))

        assert offered, state
        assert not offered & _forbidden_closers(state), state
        assert not offered & ({"QuizItem", "DragOrder"} - _allowed_closers(state)), state
        # And the one closer the server has to prepare is never proposed unless it exists.
        if "LearningExperience" in offered:
            assert _authored_experience_refs(
                state.get("authored_activity") or {}
            ) is not None, state


def _gate_errors(implementation_ref: str) -> list[str]:
    """Run the real gate rule by building the real ``Component``, not a stand-in.

    The check lives in ``Component``'s own model validator, so the only honest way to assert
    on it is to construct one and read what it refuses.
    """
    try:
        Component(
            id="cierre",
            type="LearningExperience",
            props={
                "experience_id": "e",
                "implementation_ref": implementation_ref,
                "definition_ref": "d",
            },
        )
    except ValueError as exc:
        return [str(exc)]
    return []
