"""Unit tests for the learner-profile logic of §3.3 / §6.4.

No DB, no network: everything under test is a pure function over dataclasses, and
the service methods are exercised with a fake repo pair.

Coverage map required by §12.2 and the B3 entry of §13:

* decay over a fixture of events with fixed ``created_at``
* L1 normalization
* ``vector_bucket``
* calibration with ``nodes_completed < 3`` (and the cold-start default)
* ``tutor_notes`` pruning to 20
* **one test per trigger rule**: ``test_signal_reinforce``, ``test_signal_lower``,
  ``test_signal_raise``, ``test_signal_shorten``, ``test_signal_prereq``
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.models import FORMAT_VECTOR_DIMENSIONS, LearnerExperience, LearningProfile
from src.repositories.learning_event_repo import EventInput, EventSample
from src.services.learner_profile_service import (
    CALIBRATION_NODES,
    DECAY_FLOOR,
    EVENT_WEIGHTS,
    MAX_SIGNALS,
    TUTOR_ACTIONS,
    LearnerProfileService,
    NodeSignalContext,
    compute_format_vector,
    decay_factor,
    dominant_dimension,
    empty_format_vector,
    evaluate_signals,
    is_calibrating,
    merge_signals,
    normalize_notes,
    set_notes_context,
    vector_bucket,
    weight_for,
)

NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)


def sample(element: str, event_type: str, *, days_ago: float = 0.0) -> EventSample:
    return EventSample(
        element=element,
        weight=EVENT_WEIGHTS[event_type],
        created_at=NOW - timedelta(days=days_ago),
    )


# ---------------------------------------------------------------------------
# EVENT_WEIGHTS
# ---------------------------------------------------------------------------


def test_event_weights_has_exactly_seven_types():
    """Seven, not eight: ``resource_opened`` is removed (§3.3)."""
    assert len(EVENT_WEIGHTS) == 7
    assert "resource_opened" not in EVENT_WEIGHTS


def test_event_weights_exact_values():
    assert EVENT_WEIGHTS == {
        "explain_click": 0.30,
        "quiz_correct": 0.20,
        "expand": 0.15,
        "scroll_slow": 0.10,
        "quiz_wrong": 0.10,
        "view": 0.05,
        "scroll_fast": -0.05,
    }


def test_scroll_fast_is_the_only_negative_weight():
    negatives = [t for t, w in EVENT_WEIGHTS.items() if w < 0]
    assert negatives == ["scroll_fast"]


def test_weight_for_unknown_type_is_zero():
    assert weight_for("telepathy") == 0.0


# ---------------------------------------------------------------------------
# Decay
# ---------------------------------------------------------------------------


def test_decay_factor_is_one_for_a_fresh_event():
    assert decay_factor(0) == 1.0


def test_decay_factor_at_half_the_window():
    # 1.0 - 0.5 * 0.8 = 0.6
    assert decay_factor(15 * 86400) == pytest.approx(0.6)


def test_decay_factor_floors_at_two_tenths():
    assert decay_factor(30 * 86400) == pytest.approx(DECAY_FLOOR)
    assert decay_factor(365 * 86400) == pytest.approx(DECAY_FLOOR)


def test_decay_makes_a_fresh_event_outweigh_an_old_one_of_the_same_type():
    fresh = compute_format_vector(
        [sample("texto", "view"), sample("codigo", "view", days_ago=29)], now=NOW
    )
    assert fresh["texto"] > fresh["codigo"]


def test_events_outside_the_window_are_ignored():
    vector = compute_format_vector(
        [sample("texto", "view", days_ago=31), sample("dato", "view")], now=NOW
    )
    assert vector["texto"] == 0.0
    assert vector["dato"] == 1.0


# ---------------------------------------------------------------------------
# L1 normalization
# ---------------------------------------------------------------------------


def test_vector_is_l1_normalized():
    vector = compute_format_vector(
        [
            sample("texto", "explain_click"),
            sample("ejercicio", "quiz_correct"),
            sample("codigo", "expand"),
            sample("dato", "view"),
        ],
        now=NOW,
    )
    assert sum(vector.values()) == pytest.approx(1.0, abs=1e-6)


def test_vector_shares_follow_the_weights():
    """0.30 vs 0.10 with the same age → a 3:1 split."""
    vector = compute_format_vector(
        [sample("texto", "explain_click"), sample("dato", "scroll_slow")], now=NOW
    )
    assert vector["texto"] == pytest.approx(0.75)
    assert vector["dato"] == pytest.approx(0.25)


def test_vector_keys_are_exactly_the_four_frozen_dimensions():
    vector = compute_format_vector([sample("texto", "view")], now=NOW)
    assert tuple(vector) == FORMAT_VECTOR_DIMENSIONS


def test_unknown_element_is_dropped_not_added_as_a_dimension():
    vector = compute_format_vector(
        [
            EventSample(element="diagrama", weight=0.30, created_at=NOW),
            sample("texto", "view"),
        ],
        now=NOW,
    )
    assert "diagrama" not in vector
    assert vector["texto"] == 1.0


def test_a_net_negative_dimension_is_clamped_to_zero():
    """Without the clamp the denominator can approach zero and blow the vector up."""
    vector = compute_format_vector(
        [
            sample("codigo", "scroll_fast"),
            sample("codigo", "scroll_fast"),
            sample("texto", "view"),
        ],
        now=NOW,
    )
    assert vector["codigo"] == 0.0
    assert vector["texto"] == 1.0
    assert sum(vector.values()) == pytest.approx(1.0)


def test_only_negative_signal_yields_the_zero_vector():
    vector = compute_format_vector([sample("codigo", "scroll_fast")], now=NOW)
    assert vector == empty_format_vector()


def test_no_events_yields_the_zero_vector():
    assert compute_format_vector([], now=NOW) == empty_format_vector()


def test_naive_timestamps_are_treated_as_utc():
    naive = EventSample(
        element="texto", weight=0.05, created_at=NOW.replace(tzinfo=None)
    )
    assert compute_format_vector([naive], now=NOW)["texto"] == 1.0


# ---------------------------------------------------------------------------
# vector_bucket and calibration
# ---------------------------------------------------------------------------


def test_calibration_threshold_is_three_nodes():
    assert CALIBRATION_NODES == 3
    assert is_calibrating(0) and is_calibrating(2)
    assert not is_calibrating(3)


def test_vector_bucket_is_empty_during_calibration():
    """The events accumulate; the bucket does not enter the cache_key (§6.4)."""
    vector = {"texto": 1.0, "ejercicio": 0.0, "codigo": 0.0, "dato": 0.0}
    for completed in range(CALIBRATION_NODES):
        assert vector_bucket(vector, completed) == ""


def test_vector_bucket_format_after_calibration():
    vector = {"texto": 0.62, "ejercicio": 0.28, "codigo": 0.10, "dato": 0.0}
    assert vector_bucket(vector, 3) == "texto:0.6"


def test_vector_bucket_rounds_the_share_to_one_decimal():
    vector = {"texto": 0.0, "ejercicio": 0.849, "codigo": 0.151, "dato": 0.0}
    assert vector_bucket(vector, 10) == "ejercicio:0.8"


def test_cold_start_zero_vector_has_no_bucket_even_after_calibration():
    """Cold start has a defined default: no bucket, so no key fragmentation."""
    assert vector_bucket(empty_format_vector(), 99) == ""
    assert vector_bucket(None, 99) == ""
    assert dominant_dimension(empty_format_vector()) is None


def test_dominant_dimension_ties_break_on_declared_order():
    tied = {"texto": 0.5, "ejercicio": 0.5, "codigo": 0.0, "dato": 0.0}
    assert dominant_dimension(tied) == ("texto", 0.5)
    assert vector_bucket(tied, 5) == "texto:0.5"


# ---------------------------------------------------------------------------
# tutor_notes: shape, dedupe, pruning
# ---------------------------------------------------------------------------


def test_normalize_notes_accepts_the_empty_jsonb_default():
    assert normalize_notes({}) == {"version": 1, "context": {}, "signals": []}
    assert normalize_notes(None)["signals"] == []


def test_set_notes_context_stores_role_and_sector():
    notes = set_notes_context(
        {}, role_title="Dependiente", sector="retail", prior=["caja"]
    )
    assert notes["context"] == {
        "sector": "retail",
        "role": "Dependiente",
        "prior": ["caja"],
    }


def test_merge_signals_writes_the_documented_entry_shape():
    node_id = uuid.uuid4()
    notes = merge_signals(
        {}, node_id=node_id, actions=["reforzar_con_ejemplo"], at=NOW
    )
    assert notes["signals"] == [
        {
            "node_id": str(node_id),
            "action": "reforzar_con_ejemplo",
            "at": NOW.isoformat(),
        }
    ]


def test_repeated_node_action_pair_is_not_duplicated_but_refreshed():
    node_id = uuid.uuid4()
    later = NOW + timedelta(hours=1)
    notes = merge_signals({}, node_id=node_id, actions=["reducir_longitud_modulo"], at=NOW)
    notes = merge_signals(
        notes, node_id=node_id, actions=["reducir_longitud_modulo"], at=later
    )
    assert len(notes["signals"]) == 1
    assert notes["signals"][0]["at"] == later.isoformat()


def test_same_action_on_a_different_node_is_a_separate_entry():
    notes = merge_signals(
        {}, node_id=uuid.uuid4(), actions=["reducir_longitud_modulo"], at=NOW
    )
    notes = merge_signals(
        notes, node_id=uuid.uuid4(), actions=["reducir_longitud_modulo"], at=NOW
    )
    assert len(notes["signals"]) == 2


def test_signals_are_pruned_to_the_newest_twenty():
    notes: dict = {}
    node_ids = [uuid.uuid4() for _ in range(25)]
    for index, node_id in enumerate(node_ids):
        notes = merge_signals(
            notes,
            node_id=node_id,
            actions=["reforzar_con_ejemplo"],
            at=NOW + timedelta(minutes=index),
        )
    assert MAX_SIGNALS == 20
    assert len(notes["signals"]) == 20
    kept = [s["node_id"] for s in notes["signals"]]
    assert kept == [str(n) for n in node_ids[-20:]]


def test_merge_signals_rejects_an_action_outside_the_vocabulary():
    from src.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        merge_signals({}, node_id=uuid.uuid4(), actions=["sugerir_formato_audio"])


def test_vocabulary_is_exactly_the_three_surviving_actions_of_the_table():
    """§3.3 listed five; the two difficulty actions left with the feedback form.

    Self-reported difficulty was their only trigger and no client ever sent it, so this
    tuple is the guard that nothing writes them into ``tutor_notes`` again.
    """
    assert TUTOR_ACTIONS == (
        "reforzar_con_ejemplo",
        "reducir_longitud_modulo",
        "revisar_prerrequisito",
    )


# ---------------------------------------------------------------------------
# The three surviving trigger rules — one test each (§3.3)
# ---------------------------------------------------------------------------


def test_signal_reinforce():
    """``consecutive_failed >= 2`` → ``reforzar_con_ejemplo``."""
    node_id = uuid.uuid4()
    assert evaluate_signals(
        NodeSignalContext(node_id=node_id, consecutive_failed=2)
    ) == ["reforzar_con_ejemplo"]
    assert evaluate_signals(
        NodeSignalContext(node_id=node_id, consecutive_failed=1)
    ) == []


def test_signal_shorten():
    """Three consecutive ``scroll_fast`` on the same node."""
    node_id = uuid.uuid4()
    assert evaluate_signals(
        NodeSignalContext(
            node_id=node_id,
            recent_event_types=("scroll_fast", "scroll_fast", "scroll_fast"),
        )
    ) == ["reducir_longitud_modulo"]
    # Broken streak: the most recent three are not all scroll_fast.
    assert evaluate_signals(
        NodeSignalContext(
            node_id=node_id,
            recent_event_types=("scroll_fast", "view", "scroll_fast", "scroll_fast"),
        )
    ) == []
    # Fewer than three events yet.
    assert evaluate_signals(
        NodeSignalContext(
            node_id=node_id, recent_event_types=("scroll_fast", "scroll_fast")
        )
    ) == []


def test_signal_prereq():
    """``last_error_kind == 'conceptual'`` **and** >=1 unmastered prerequisite."""
    node_id = uuid.uuid4()
    assert evaluate_signals(
        NodeSignalContext(
            node_id=node_id,
            last_error_kind="conceptual",
            unmastered_prerequisites=1,
        )
    ) == ["revisar_prerrequisito"]
    # Conceptual error but every prerequisite mastered → nothing to revisit.
    assert evaluate_signals(
        NodeSignalContext(
            node_id=node_id,
            last_error_kind="conceptual",
            unmastered_prerequisites=0,
        )
    ) == []
    # A detail error is not a prerequisite problem.
    assert evaluate_signals(
        NodeSignalContext(
            node_id=node_id,
            last_error_kind="detail",
            unmastered_prerequisites=3,
        )
    ) == []


def test_error_kind_enum_member_behaves_like_its_value():
    from src.models import ErrorKind

    assert evaluate_signals(
        NodeSignalContext(
            node_id=uuid.uuid4(),
            last_error_kind=ErrorKind.CONCEPTUAL,
            unmastered_prerequisites=2,
        )
    ) == ["revisar_prerrequisito"]


def test_several_rules_can_fire_at_once_in_table_order():
    actions = evaluate_signals(
        NodeSignalContext(
            node_id=uuid.uuid4(),
            consecutive_failed=4,
            recent_event_types=("scroll_fast",) * 3,
            last_error_kind="conceptual",
            unmastered_prerequisites=2,
        )
    )
    assert actions == [
        "reforzar_con_ejemplo",
        "reducir_longitud_modulo",
        "revisar_prerrequisito",
    ]


def test_a_quiet_node_emits_nothing():
    assert evaluate_signals(NodeSignalContext(node_id=uuid.uuid4())) == []


# ---------------------------------------------------------------------------
# Service methods, against a fake repo pair
# ---------------------------------------------------------------------------


class FakeProfileRepo:
    """Just enough of ``LearnerProfileRepository`` for the service under test."""

    def __init__(self, profile=None) -> None:
        self.profile = profile
        self.session = AsyncMock()
        self.erased: list[uuid.UUID] = []

    async def get_by_user(self, user_id):
        return self.profile

    async def get_or_create(self, *, user_id, org_id):
        if self.profile is None:
            self.profile = make_profile(user_id=user_id, org_id=org_id)
        return self.profile

    async def erase_user_data(self, user_id):
        self.erased.append(user_id)
        self.profile = None
        return {
            "node_renders_anonymized": 1,
            "node_render_views": 2,
            "learner_node_states": 3,
            "learning_events": 42,
            "learner_profiles": 1,
        }


class FakeEventRepo:
    def __init__(self, samples=()) -> None:
        self.samples = list(samples)
        self.recorded: list[EventInput] = []

    async def record_many(self, *, user_id, events):
        self.recorded.extend(events)
        return list(events)

    async def window_samples(self, *, user_id, since):
        return [s for s in self.samples if s.created_at >= since]

    async def recent_types_for_node(self, *, user_id, node_id, limit=3):
        return []


def make_profile(*, user_id=None, org_id=None):
    return SimpleNamespace(
        user_id=user_id or uuid.uuid4(),
        org_id=org_id or uuid.uuid4(),
        role_title=None,
        sector=None,
        goal=None,
        experience_level=LearnerExperience.UNKNOWN,
        preset=LearningProfile.STANDARD,
        format_vector=empty_format_vector(),
        format_vector_updated_at=None,
        nodes_completed=0,
        tutor_notes={},
        onboarding_completed_at=None,
        onboarding_skipped=False,
        onboarding_version=1,
    )


def make_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        learning_profile=LearningProfile.STANDARD,
        accessibility={},
    )


def make_service(profile=None, samples=()):
    profiles = FakeProfileRepo(profile)
    events = FakeEventRepo(samples)
    return LearnerProfileService(profiles, events), profiles, events


async def test_complete_onboarding_writes_profile_and_mirrors_to_user():
    service, profiles, _ = make_service()
    user = make_user()

    profile = await service.complete_onboarding(
        user=user,
        role_title="  Dependiente  ",
        sector="retail",
        goal="onboarding",
        experience_level="some",
        preset="focus",
        accessibility={"short_blocks": True, "reduce_motion": False},
        now=NOW,
    )

    assert profile.role_title == "Dependiente"  # trimmed
    assert profile.experience_level is LearnerExperience.SOME
    assert profile.preset is LearningProfile.FOCUS
    assert profile.onboarding_completed_at == NOW
    assert profile.onboarding_skipped is False
    # users.learning_profile stays the v1 source of truth, written in the same tx.
    assert user.learning_profile is LearningProfile.FOCUS
    assert user.accessibility == {"short_blocks": True, "reduce_motion": False}
    assert profile.tutor_notes["context"]["role"] == "Dependiente"


async def test_complete_onboarding_without_experience_stays_unknown():
    """A partially answered wizard must not silently declare novice."""
    service, _, _ = make_service()
    profile = await service.complete_onboarding(user=make_user(), now=NOW)
    assert profile.experience_level is LearnerExperience.UNKNOWN


async def test_skip_onboarding_writes_unknown_not_none():
    service, _, _ = make_service()
    user = make_user()
    profile = await service.skip_onboarding(user=user, now=NOW)
    assert profile.experience_level is LearnerExperience.UNKNOWN
    assert profile.experience_level is not LearnerExperience.NONE
    assert profile.onboarding_skipped is True
    assert profile.onboarding_completed_at == NOW
    # Skipping declares nothing, so `users` is untouched.
    assert user.learning_profile is LearningProfile.STANDARD


async def test_update_profile_rejects_fields_outside_the_patch_allowlist():
    from src.core.exceptions import ValidationError

    profile = make_profile()
    service, _, _ = make_service(profile)
    with pytest.raises(ValidationError):
        await service.update_profile(
            user=make_user(), changes={"nodes_completed": 99}
        )


async def test_update_profile_mirrors_preset_to_the_user_row():
    profile = make_profile()
    service, _, _ = make_service(profile)
    user = make_user()
    await service.update_profile(user=user, changes={"preset": "fast"})
    assert profile.preset is LearningProfile.FAST
    assert user.learning_profile is LearningProfile.FAST


async def test_update_profile_applies_accessibility_atomically_and_advances_once():
    profile = make_profile()
    profile.personalization_revision = 4
    profile.learning_preferences = {
        "version": 1,
        "presentation": "balanced",
        "detail": "standard",
        "images": "when_useful",
    }
    service, profiles, _ = make_service(profile)
    user = make_user()

    await service.update_profile(
        user=user,
        changes={
            "learning_preferences": {
                "version": 1,
                "presentation": "visual",
                "detail": "detailed",
                "images": "prefer",
            },
            "accessibility": {"short_blocks": True},
        },
    )

    assert user.accessibility == {"short_blocks": True}
    assert profile.learning_preferences["version"] == 3
    assert profile.learning_preferences["web_presentation"] == "visual"
    assert profile.learning_preferences["modalities"] == []
    assert profile.personalization_revision == 5
    profiles.session.execute.assert_awaited_once()


async def test_update_profile_sets_learning_note_and_advances_personalization():
    """Setting the note stores it normalized and unpins renders (cache re-render)."""
    profile = make_profile()
    profile.personalization_revision = 2
    profile.learning_note = None
    service, profiles, _ = make_service(profile)
    user = make_user()

    await service.update_profile(
        user=user, changes={"learning_note": "  me gustan las   metaforas "}
    )

    assert profile.learning_note == "me gustan las metaforas"  # normalized
    # A changed note forces a fresh render for this learner.
    assert profile.personalization_revision == 3
    profiles.session.execute.assert_awaited_once()


async def test_update_profile_clears_learning_note_with_blank():
    profile = make_profile()
    profile.personalization_revision = 1
    profile.learning_note = "me gustan las metaforas"
    service, _, _ = make_service(profile)

    await service.update_profile(user=make_user(), changes={"learning_note": "   "})

    assert profile.learning_note is None
    assert profile.personalization_revision == 2


async def test_update_profile_note_unchanged_does_not_advance():
    """Re-submitting the same note (modulo whitespace) must not re-render."""
    profile = make_profile()
    profile.personalization_revision = 7
    profile.learning_note = "me gustan las metaforas"
    service, profiles, _ = make_service(profile)

    await service.update_profile(
        user=make_user(), changes={"learning_note": "me gustan  las metaforas"}
    )

    assert profile.personalization_revision == 7
    profiles.session.execute.assert_not_awaited()


def test_learner_profile_read_round_trips_the_note():
    from src.schemas.learner_profile import LearnerProfileRead, LearnerProfileUpdate

    profile = make_profile()
    profile.learning_note = "me gusta entender las bases"
    profile.nodes_completed = 5
    profile.onboarding_completed_at = None
    profile.onboarding_skipped = False
    read = LearnerProfileRead.from_profile(profile)
    assert read.learning_note == "me gusta entender las bases"

    # PATCH schema accepts the field and caps its length.
    from pydantic import ValidationError as PydValidationError

    assert LearnerProfileUpdate(learning_note="hola").learning_note == "hola"
    with pytest.raises(PydValidationError):
        LearnerProfileUpdate(learning_note="x" * 5000)


async def test_get_or_404_raises_when_there_is_no_profile():
    from src.core.exceptions import NotFoundError

    service, _, _ = make_service(None)
    with pytest.raises(NotFoundError):
        await service.get_or_404(uuid.uuid4())


async def test_erase_really_deletes_and_reports_what_it_deleted():
    """RGPD art. 17: a real delete, not a blanked row."""
    profile = make_profile()
    service, profiles, _ = make_service(profile)
    user_id = profile.user_id

    counts = await service.erase(user_id=user_id)

    assert profiles.erased == [user_id]
    assert counts["learner_profiles"] == 1
    assert counts["learning_events"] == 42
    # Shared renders survive; only the authorship link is dropped.
    assert counts["node_renders_anonymized"] == 1
    assert await service.get(user_id) is None


async def test_record_events_stamps_the_canonical_weight():
    service, _, events = make_service(make_profile())
    node_id = uuid.uuid4()

    count = await service.record_events(
        user_id=uuid.uuid4(),
        events=[
            EventInput(type="explain_click", element="texto", node_id=node_id),
            EventInput(type="scroll_fast", element="codigo", node_id=node_id),
            EventInput(type="telepathy", element="texto", node_id=node_id),
        ],
    )

    assert count == 3
    assert [e.weight for e in events.recorded] == [0.30, -0.05, 0.0]


async def test_refresh_format_vector_persists_the_normalized_vector():
    profile = make_profile()
    service, _, _ = make_service(
        profile,
        samples=[
            sample("texto", "explain_click"),
            sample("ejercicio", "quiz_correct", days_ago=1),
        ],
    )

    vector = await service.refresh_format_vector(profile=profile, now=NOW)

    assert sum(vector.values()) == pytest.approx(1.0, abs=1e-6)
    assert profile.format_vector == vector
    assert profile.format_vector_updated_at == NOW


async def test_bucket_for_is_empty_while_calibrating_even_with_a_full_vector():
    profile = make_profile()
    profile.format_vector = {
        "texto": 1.0,
        "ejercicio": 0.0,
        "codigo": 0.0,
        "dato": 0.0,
    }
    profile.nodes_completed = 2
    service, _, _ = make_service(profile)
    assert service.bucket_for(profile) == ""
    profile.nodes_completed = 3
    assert service.bucket_for(profile) == "texto:1.0"


async def test_increment_nodes_completed_counts_one_at_a_time():
    profile = make_profile()
    service, _, _ = make_service(profile)
    assert await service.increment_nodes_completed(profile=profile) == 1
    assert await service.increment_nodes_completed(profile=profile) == 2


async def test_apply_signals_merges_into_tutor_notes():
    profile = make_profile()
    service, _, _ = make_service(profile)
    node_id = uuid.uuid4()

    notes = await service.apply_signals(
        profile=profile,
        context=NodeSignalContext(node_id=node_id, consecutive_failed=3),
        now=NOW,
    )

    assert [s["action"] for s in notes["signals"]] == ["reforzar_con_ejemplo"]
    assert profile.tutor_notes == notes


async def test_apply_signals_leaves_notes_untouched_when_nothing_fires():
    profile = make_profile()
    service, _, _ = make_service(profile)
    notes = await service.apply_signals(
        profile=profile, context=NodeSignalContext(node_id=uuid.uuid4()), now=NOW
    )
    assert notes["signals"] == []
    assert profile.tutor_notes == {}
