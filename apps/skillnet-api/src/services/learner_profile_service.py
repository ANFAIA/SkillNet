"""Learner-profile service: the *inferred* half of the v2 learner profile.

Three independent sources live in three places (§3.3): declared
(``learner_profiles``), inferred (``learning_events`` → ``format_vector``) and by
competence (``learner_node_states``). This module owns the first two.

Everything above ``LearnerProfileService`` is a **pure function**: no session, no
network. That is what makes ``tests/test_profile_service.py`` runnable without a
database, which the environment this repo is developed in requires.

Two rules that are load-bearing and easy to break by accident:

* ``tutor_notes`` is a **controlled vocabulary** (:data:`TUTOR_ACTIONS`), written
  only by :func:`evaluate_signals` / :meth:`LearnerProfileService.apply_signals`.
  An LLM never writes here — that is what makes the notebook auditable and
  erasable.
* During the calibration period (``nodes_completed < 3``) the inferred vector is
  accumulated but **not used**: :func:`vector_bucket` returns ``""`` so it never
  enters the ``cache_key`` nor the prompt (§6.4).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from src.core.exceptions import NotFoundError, ValidationError
from src.models import (
    FORMAT_VECTOR_DIMENSIONS,
    LearnerExperience,
    LearnerProfile,
    LearningProfile,
    User,
)
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.learning_event_repo import EventInput, EventSample, LearningEventRepository

# ---------------------------------------------------------------------------
# Constants fixed by the spec
# ---------------------------------------------------------------------------

#: Fixed weights per ``learning_events.type`` (§3.3). Exactly seven types:
#: ``resource_opened`` is deliberately absent — no component of the frozen UI kit
#: (§5.3) can emit a resource, so it could never fire and would only distort the
#: L1 normalization.
EVENT_WEIGHTS: dict[str, float] = {
    "explain_click": 0.30,
    "quiz_correct": 0.20,
    "expand": 0.15,
    "scroll_slow": 0.10,
    "quiz_wrong": 0.10,
    "view": 0.05,
    "scroll_fast": -0.05,
}

#: Sliding window of the inferred vector, in days.
VECTOR_WINDOW_DAYS = 30
#: ``weight_effective = weight * GREATEST(0.2, 1.0 - (age/window) * 0.8)``
DECAY_FLOOR = 0.2
DECAY_SPAN = 0.8

#: ``nodes_completed < CALIBRATION_NODES`` → the vector is accumulated, not used.
CALIBRATION_NODES = 3

#: ``tutor_notes.signals`` keeps only the newest 20 entries.
MAX_SIGNALS = 20
TUTOR_NOTES_VERSION = 1

#: ``learner_profiles.onboarding_version``. Bump it when the five questions of
#: §6.2 change, so an old answer set is recognisable.
ONBOARDING_VERSION = 1

#: Consecutive ``scroll_fast`` events on the same node that emit
#: ``reducir_longitud_modulo``.
SCROLL_FAST_STREAK = 3

TutorAction = Literal[
    "reforzar_con_ejemplo",
    "bajar_dificultad",
    "subir_dificultad",
    "reducir_longitud_modulo",
    "revisar_prerrequisito",
]

#: The whole permitted vocabulary, in the emission order of the table in §3.3.
TUTOR_ACTIONS: tuple[TutorAction, ...] = (
    "reforzar_con_ejemplo",
    "bajar_dificultad",
    "subir_dificultad",
    "reducir_longitud_modulo",
    "revisar_prerrequisito",
)

#: Fields ``PATCH /users/me/learner-profile`` may touch (§11.2).
PATCHABLE_FIELDS: frozenset[str] = frozenset({"preset", "role_title", "sector", "goal"})


# ---------------------------------------------------------------------------
# Pure helpers: the inferred vector
# ---------------------------------------------------------------------------


def weight_for(event_type: str) -> float:
    """Weight of an event type; ``0.0`` for anything not in the vocabulary."""
    return EVENT_WEIGHTS.get(event_type, 0.0)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def decay_factor(age_seconds: float) -> float:
    """``GREATEST(0.2, 1.0 - (age_seconds / (30*86400)) * 0.8)``.

    Clamped to ``1.0`` for non-positive ages so a clock skew of a few ms cannot
    make a brand-new event count for *more* than a fresh one.
    """
    if age_seconds <= 0:
        return 1.0
    window = VECTOR_WINDOW_DAYS * 86400
    return max(DECAY_FLOOR, 1.0 - (age_seconds / window) * DECAY_SPAN)


def empty_format_vector() -> dict[str, float]:
    """A fresh all-zero vector over the four frozen dimensions."""
    return {dim: 0.0 for dim in FORMAT_VECTOR_DIMENSIONS}


def compute_format_vector(
    samples: Iterable[EventSample], *, now: datetime | None = None
) -> dict[str, float]:
    """L1-normalized vector over the four dimensions, with 30-day decay.

    Samples outside the window, with an unknown ``element`` or with a zero
    effective contribution are ignored. A dimension whose *signed* sum comes out
    negative (only ``scroll_fast`` can do that) is clamped to ``0.0`` before
    normalizing: without the clamp the denominator could approach zero and a
    single fast scroll would blow the vector up.

    With no usable signal the result is the all-zero vector, which is exactly the
    cold-start state — :func:`vector_bucket` maps it to ``""``.
    """
    reference = _as_utc(now or datetime.now(timezone.utc))
    cutoff = reference - timedelta(days=VECTOR_WINDOW_DAYS)
    totals = empty_format_vector()

    for sample in samples:
        if sample.element not in totals:
            continue
        created_at = _as_utc(sample.created_at)
        if created_at < cutoff:
            continue
        age = (reference - created_at).total_seconds()
        totals[sample.element] += sample.weight * decay_factor(age)

    clamped = {dim: value if value > 0 else 0.0 for dim, value in totals.items()}
    denominator = sum(clamped.values())
    if denominator <= 0:
        return empty_format_vector()
    return {dim: round(value / denominator, 6) for dim, value in clamped.items()}


def dominant_dimension(
    format_vector: Mapping[str, float] | None,
) -> tuple[str, float] | None:
    """Largest dimension and its share, or ``None`` when there is no signal.

    Ties break on the declared order of :data:`FORMAT_VECTOR_DIMENSIONS` so the
    bucket — and therefore the ``cache_key`` — is deterministic.
    """
    if not format_vector:
        return None
    best: tuple[str, float] | None = None
    for dim in FORMAT_VECTOR_DIMENSIONS:
        share = float(format_vector.get(dim, 0.0) or 0.0)
        if share <= 0:
            continue
        if best is None or share > best[1]:
            best = (dim, share)
    return best


def is_calibrating(nodes_completed: int) -> bool:
    """True while the learner has worked fewer than three nodes (§6.4)."""
    return nodes_completed < CALIBRATION_NODES


def vector_bucket(
    format_vector: Mapping[str, float] | None, nodes_completed: int
) -> str:
    """``"{dominant}:{share_to_1dp}"``, or ``""`` when it must not be used.

    Empty during calibration and empty with no signal — in both cases the bucket
    drops out of the ``cache_key`` instead of pinning everyone to ``texto:0.0``.
    """
    if is_calibrating(nodes_completed):
        return ""
    best = dominant_dimension(format_vector)
    if best is None:
        return ""
    dominant, share = best
    return f"{dominant}:{round(share, 1)}"


# ---------------------------------------------------------------------------
# Pure helpers: the tutor notebook
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeSignalContext:
    """Everything the five trigger rules of §3.3 need, and nothing else.

    A plain frozen dataclass on purpose: the rules are evaluated in tests without
    a database, and the caller (the ``answer``/``feedback`` routes of B5) is the
    only place that knows how to read these values out of Postgres.

    ``recent_event_types`` is ordered **most recent first** and scoped to
    ``node_id``.
    """

    node_id: uuid.UUID
    consecutive_failed: int = 0
    consecutive_correct: int = 0
    last_error_kind: str | None = None
    difficulty: str | None = None
    recent_event_types: tuple[str, ...] = ()
    unmastered_prerequisites: int = 0


def evaluate_signals(context: NodeSignalContext) -> list[TutorAction]:
    """The five rules of §3.3, verbatim, in table order.

    ============================  ==========================================
    Action                        Condition
    ============================  ==========================================
    ``reforzar_con_ejemplo``      ``consecutive_failed >= 2``
    ``bajar_dificultad``          ``difficulty == 'hard'``
    ``subir_dificultad``          ``difficulty == 'easy'`` and
                                  ``consecutive_correct >= 3``
    ``reducir_longitud_modulo``   3 consecutive ``scroll_fast`` on the node
    ``revisar_prerrequisito``     ``last_error_kind == 'conceptual'`` and >=1
                                  prerequisite not ``mastered``
    ============================  ==========================================
    """
    actions: list[TutorAction] = []

    if context.consecutive_failed >= 2:
        actions.append("reforzar_con_ejemplo")

    difficulty = _plain(context.difficulty)
    if difficulty == "hard":
        actions.append("bajar_dificultad")
    elif difficulty == "easy" and context.consecutive_correct >= 3:
        actions.append("subir_dificultad")

    streak = context.recent_event_types[:SCROLL_FAST_STREAK]
    if len(streak) == SCROLL_FAST_STREAK and all(t == "scroll_fast" for t in streak):
        actions.append("reducir_longitud_modulo")

    if (
        _plain(context.last_error_kind) == "conceptual"
        and context.unmastered_prerequisites >= 1
    ):
        actions.append("revisar_prerrequisito")

    return actions


def _plain(value: object) -> str | None:
    """Enum-or-string → plain string, mirroring ``deps.auth._role_value``."""
    if value is None:
        return None
    inner = getattr(value, "value", value)
    return str(inner)


def normalize_notes(notes: Mapping[str, Any] | None) -> dict[str, Any]:
    """Coerce whatever is stored into the documented shape without losing data."""
    source: Mapping[str, Any] = notes or {}
    raw_signals = source.get("signals")
    signals = [s for s in raw_signals if isinstance(s, dict)] if isinstance(raw_signals, list) else []
    raw_context = source.get("context")
    context = dict(raw_context) if isinstance(raw_context, dict) else {}
    return {
        "version": int(source.get("version") or TUTOR_NOTES_VERSION),
        "context": context,
        "signals": signals,
    }


def set_notes_context(
    notes: Mapping[str, Any] | None,
    *,
    role_title: str | None,
    sector: str | None,
    prior: Sequence[str] = (),
) -> dict[str, Any]:
    """Write the ``context`` block of the notebook (onboarding, and nowhere else)."""
    merged = normalize_notes(notes)
    merged["context"] = {
        "sector": sector,
        "role": role_title,
        "prior": list(prior),
    }
    return merged


def merge_signals(
    notes: Mapping[str, Any] | None,
    *,
    node_id: uuid.UUID | str,
    actions: Sequence[str],
    at: datetime | None = None,
) -> dict[str, Any]:
    """Append ``actions`` for ``node_id``, de-duplicating and pruning to 20.

    A repeated ``(node_id, action)`` is **not** duplicated: its ``at`` is
    refreshed and it moves to the end of the list, so the list stays in
    chronological order and ``signals[-20:]`` really is "the newest 20".
    """
    merged = normalize_notes(notes)
    timestamp = _as_utc(at or datetime.now(timezone.utc)).isoformat()
    node_key = str(node_id)
    signals: list[dict[str, Any]] = merged["signals"]

    for action in actions:
        if action not in TUTOR_ACTIONS:
            raise ValidationError(f"Unknown tutor action: {action}", field="action")
        kept = [
            s
            for s in signals
            if not (str(s.get("node_id")) == node_key and s.get("action") == action)
        ]
        kept.append({"node_id": node_key, "action": action, "at": timestamp})
        signals = kept

    merged["signals"] = signals[-MAX_SIGNALS:]
    return merged


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class LearnerProfileService:
    """Onboarding, profile reads/writes, the inferred vector and the notebook.

    Repositories flush; the route owns the transaction (repo convention of this
    repo). ``complete_onboarding`` mutates ``users`` too, so the caller must
    commit exactly once for the three writes of §11.2 to land together.
    """

    def __init__(
        self,
        profiles: LearnerProfileRepository,
        events: LearningEventRepository,
    ) -> None:
        self.profiles = profiles
        self.events = events

    # -- reads ------------------------------------------------------------

    async def get(self, user_id: uuid.UUID) -> LearnerProfile | None:
        return await self.profiles.get_by_user(user_id)

    async def get_or_404(self, user_id: uuid.UUID) -> LearnerProfile:
        profile = await self.profiles.get_by_user(user_id)
        if profile is None:
            raise NotFoundError("learner_profile", str(user_id))
        return profile

    # -- onboarding -------------------------------------------------------

    async def complete_onboarding(
        self,
        *,
        user: User,
        role_title: str | None = None,
        sector: str | None = None,
        goal: str | None = None,
        experience_level: str | None = None,
        preset: str | None = None,
        accessibility: Mapping[str, bool] | None = None,
        now: datetime | None = None,
    ) -> LearnerProfile:
        """Write ``learner_profiles`` **and** ``users.learning_profile`` **and**
        ``users.accessibility`` (§11.2). One transaction, owned by the route.

        An unanswered question 3 stays ``unknown`` rather than falling to
        ``none``: ``none`` means "declares being a novice" and forces novice
        scaffolding, which is the case that hurts the expert (§3.3).
        """
        timestamp = _as_utc(now or datetime.now(timezone.utc))
        profile = await self.profiles.get_or_create(
            user_id=user.id, org_id=user.org_id
        )
        resolved_preset = _coerce_preset(preset) or LearningProfile.STANDARD

        profile.role_title = _clean(role_title)
        profile.sector = _clean(sector)
        profile.goal = _clean(goal)
        profile.experience_level = _coerce_experience(experience_level)
        profile.preset = resolved_preset
        profile.tutor_notes = set_notes_context(
            profile.tutor_notes,
            role_title=profile.role_title,
            sector=profile.sector,
            prior=_prior_of(profile.tutor_notes),
        )
        profile.onboarding_completed_at = timestamp
        profile.onboarding_skipped = False
        profile.onboarding_version = ONBOARDING_VERSION

        # users.learning_profile stays the source of truth for the v1 frontend.
        user.learning_profile = resolved_preset
        if accessibility is not None:
            user.accessibility = {k: bool(v) for k, v in accessibility.items()}

        await self.profiles.session.flush()
        return profile

    async def skip_onboarding(
        self, *, user: User, now: datetime | None = None
    ) -> LearnerProfile:
        """"Lo hago luego": asked once, never again (§6.1).

        Writes ``experience_level = 'unknown'``, **not** ``'none'``: whoever
        skips has declared nothing. ``users`` is not touched.
        """
        timestamp = _as_utc(now or datetime.now(timezone.utc))
        profile = await self.profiles.get_or_create(
            user_id=user.id, org_id=user.org_id
        )
        profile.experience_level = LearnerExperience.UNKNOWN
        profile.onboarding_completed_at = timestamp
        profile.onboarding_skipped = True
        await self.profiles.session.flush()
        return profile

    async def update_profile(
        self, *, user: User, changes: Mapping[str, Any]
    ) -> LearnerProfile:
        """``PATCH`` over the four editable fields; unknown keys are rejected."""
        unknown = set(changes) - PATCHABLE_FIELDS
        if unknown:
            raise ValidationError(
                f"Not editable: {', '.join(sorted(unknown))}",
                field=sorted(unknown)[0],
            )
        profile = await self.get_or_404(user.id)

        if "preset" in changes:
            resolved = _coerce_preset(changes["preset"])
            if resolved is None:
                raise ValidationError("Unknown preset", field="preset")
            profile.preset = resolved
            user.learning_profile = resolved
        for field_name in ("role_title", "sector", "goal"):
            if field_name in changes:
                setattr(profile, field_name, _clean(changes[field_name]))

        if "role_title" in changes or "sector" in changes:
            profile.tutor_notes = set_notes_context(
                profile.tutor_notes,
                role_title=profile.role_title,
                sector=profile.sector,
                prior=_prior_of(profile.tutor_notes),
            )

        await self.profiles.session.flush()
        return profile

    # -- GDPR -------------------------------------------------------------

    async def erase(self, *, user_id: uuid.UUID) -> dict[str, int]:
        """Art. 17 erasure: really delete, do not just blank fields (§3.3)."""
        return await self.profiles.erase_user_data(user_id)

    # -- inferred vector --------------------------------------------------

    async def record_events(
        self, *, user_id: uuid.UUID, events: Sequence[EventInput]
    ) -> int:
        """Append events with their canonical weight. Unknown types get ``0.0``.

        Unknown types are stored rather than rejected so a frontend one release
        ahead cannot 4xx; a zero weight simply never reaches the vector.
        """
        weighted = [
            EventInput(
                type=event.type,
                element=event.element,
                node_id=event.node_id,
                weight=weight_for(event.type),
                element_id=event.element_id,
                ms=event.ms,
            )
            for event in events
        ]
        rows = await self.events.record_many(user_id=user_id, events=weighted)
        return len(rows)

    async def refresh_format_vector(
        self, *, profile: LearnerProfile, now: datetime | None = None
    ) -> dict[str, float]:
        """Recompute ``format_vector`` from the 30-day window and store it."""
        reference = _as_utc(now or datetime.now(timezone.utc))
        since = reference - timedelta(days=VECTOR_WINDOW_DAYS)
        samples = await self.events.window_samples(
            user_id=profile.user_id, since=since
        )
        vector = compute_format_vector(samples, now=reference)
        profile.format_vector = vector
        profile.format_vector_updated_at = reference
        await self.profiles.session.flush()
        return vector

    def bucket_for(self, profile: LearnerProfile) -> str:
        """``vector_bucket`` of a loaded profile — ``""`` while calibrating."""
        return vector_bucket(profile.format_vector, profile.nodes_completed)

    async def increment_nodes_completed(self, *, profile: LearnerProfile) -> int:
        """``+1`` only on ``learning -> mastered`` (§3.3); the caller enforces that.

        A node skipped by the probe (``probing -> mastered``) must **not** call
        this: it produced no interaction event, so counting it would take the
        learner out of calibration with an empty vector.
        """
        profile.nodes_completed = (profile.nodes_completed or 0) + 1
        await self.profiles.session.flush()
        return profile.nodes_completed

    # -- tutor notebook ---------------------------------------------------

    async def apply_signals(
        self,
        *,
        profile: LearnerProfile,
        context: NodeSignalContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Evaluate the five rules and merge the result into ``tutor_notes``.

        Called after every ``answer``/``feedback``. Never from an LLM.
        """
        actions = evaluate_signals(context)
        notes = merge_signals(
            profile.tutor_notes,
            node_id=context.node_id,
            actions=actions,
            at=now,
        )
        if actions:
            profile.tutor_notes = notes
            await self.profiles.session.flush()
        return notes


# ---------------------------------------------------------------------------
# Small coercions
# ---------------------------------------------------------------------------


def _prior_of(notes: Mapping[str, Any] | None) -> list[str]:
    """Existing ``context.prior``, so redoing the onboarding does not wipe it."""
    prior = normalize_notes(notes)["context"].get("prior")
    return [str(item) for item in prior] if isinstance(prior, list) else []


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _coerce_experience(value: Any) -> LearnerExperience:
    """Anything unrecognised (including ``None``) becomes ``unknown``."""
    plain = _plain(value)
    if plain is None:
        return LearnerExperience.UNKNOWN
    try:
        return LearnerExperience(plain)
    except ValueError:
        return LearnerExperience.UNKNOWN


def _coerce_preset(value: Any) -> LearningProfile | None:
    plain = _plain(value)
    if plain is None:
        return None
    try:
        return LearningProfile(plain)
    except ValueError:
        return None
