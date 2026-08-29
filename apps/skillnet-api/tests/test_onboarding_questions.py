"""The onboarding questionnaire as a contract, checkable without a database.

``tests/integration/test_dynamic_flow.py`` pins the same list, but it needs a live
Postgres, so a drift between the questions and the fields they write survived
until someone had a database at hand — which is how its expected list ended up
one question behind ``build_questions`` (``learning_preferences``). These tests
are the fast half of that guard: the ids and their order, and the fact that every
option value the wizard offers is one ``POST /onboarding`` will accept.
"""

from typing import get_args

from src.schemas.learning_preferences import (
    AccessibilitySubmit,
    LearningPreferencesV2,
)
from src.schemas.onboarding import (
    ACCESSIBILITY_KEYS,
    ROLE_SUGGESTIONS,
    build_questions,
)

#: The order the client mirrors in its own ``KNOWN_STEP_IDS`` and the integration
#: flow asserts on. ``learning_preferences`` before ``accessibility``: how the
#: learner wants to be taught, then what they need in order to read at all.
EXPECTED_IDS = [
    "role_title",
    "goal",
    "experience_level",
    "preset",
    "learning_preferences",
    "accessibility",
]


def question(questions: list, question_id: str) -> object:
    return next(item for item in questions if item.id == question_id)


def test_the_questions_ship_in_the_documented_order_with_no_duplicates() -> None:
    ids = [item.id for item in build_questions()]

    assert ids == EXPECTED_IDS
    assert len(set(ids)) == len(ids)


def test_only_the_two_preference_screens_are_skippable() -> None:
    optional = {item.id for item in build_questions() if item.optional}

    assert optional == {"learning_preferences", "accessibility"}


def test_the_sector_only_changes_the_role_suggestions() -> None:
    generic = build_questions()
    retail = build_questions(sector="retail")

    assert [item.id for item in retail] == [item.id for item in generic]
    assert question(retail, "role_title").suggestions == list(
        ROLE_SUGGESTIONS["retail"]
    )
    # An unknown sector falls back rather than shipping an empty screen.
    assert question(build_questions(sector="astronautica"), "role_title").suggestions


def test_every_offered_modality_is_one_the_submit_schema_accepts() -> None:
    """The drift this catches is real: the wizard offered ``textual`` and
    ``interactive`` while the stored contract had renamed them."""
    offered = [
        option.value
        for option in question(build_questions(), "learning_preferences").options
    ]
    accepted = get_args(LearningPreferencesV2.model_fields["modality"].annotation)

    assert set(offered) <= set(accepted), sorted(set(offered) - set(accepted))


def test_the_accessibility_options_are_exactly_the_stored_flags() -> None:
    offered = [
        option.value for option in question(build_questions(), "accessibility").options
    ]

    assert offered == list(ACCESSIBILITY_KEYS)
    assert set(offered) == set(AccessibilitySubmit.model_fields)


def test_the_audio_hint_says_so_when_the_deployment_has_no_tts() -> None:
    def audio_hint(*, audio_available: bool) -> str:
        options = question(
            build_questions(audio_available=audio_available), "learning_preferences"
        ).options
        return next(option.hint for option in options if option.value == "audio")

    assert audio_hint(audio_available=False) != audio_hint(audio_available=True)
    assert "despliegue" in audio_hint(audio_available=False)
