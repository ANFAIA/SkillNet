"""``ProbeService`` against in-memory fakes: no DB, no network (§12.2).

The three claims worth defending here are the ones that make mastery non-gameable:

1. A second ``POST /probe`` for the same ``(user, node, schema_version)`` serves the
   stored verdict and generates nothing.
2. A re-probe is refused unless the node is in ``needs_review`` *and* 7 days have passed.
3. The novice's diagnostic probe (``scored = false``) neither persists failures nor
   consumes the single scored attempt.

Plus the item-source order of §7.1 and the item contract, since the contract is what
makes the arithmetic of §7.2 true rather than aspirational.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import src.llm as llm_package
from src.core.exceptions import ConflictError, LLMError, ValidationError
from src.llm.client import LLMConfig
from src.llm.fixtures import FixtureLLMService
from src.llm.prompts.probe import PROBE_GENERATOR_SYSTEM, build_probe_prompt
from src.services.mastery_service import REPROBE_COOLDOWN_DAYS
from src.services.probe_service import (
    ITEM_A,
    ITEM_B,
    ITEM_C,
    ProbeService,
    is_diagnostic_probe,
    parse_probe_response,
    seed_probe_items,
    served_items,
    validate_probe_items,
)

NOW = datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc)

# --- the canonical scenario the shipped fixture is recorded against -----------
# Changing any of these strings changes the fixture key, and
# `test_generation_last_resort_uses_the_shipped_fixture` will say so out loud.

FIXTURE_DIR = Path(llm_package.__file__).parent / "fixture_data"
CANON_TITLE = "Plazo de devolucion"
CANON_SUMMARY = (
    "El cliente puede devolver un articulo en 30 dias naturales presentando el "
    "ticket de compra. Sin ticket se emite un vale por el importe."
)
CANON_OUTCOME = "Aplicar el plazo de devolucion correcto en mostrador"
CANON_SOURCE = (
    "Politica de devoluciones\n\n"
    "Plazo: 30 dias naturales desde la fecha de compra, presentando el ticket.\n"
    "Sin ticket: se emite un vale por el importe del articulo.\n"
    "Articulos personalizados: no se admiten devoluciones."
)


# --- fakes -------------------------------------------------------------------


def make_items(*, with_c: bool = True) -> tuple[list[dict], dict]:
    items = [
        {
            "item_id": ITEM_A,
            "item_type": "test",
            "bloom_level": "apply",
            "question": "Caso: 20 dias con ticket.",
            "options": ["no", "si, reembolso", "solo vale", "consultar"],
        },
        {
            "item_id": ITEM_B,
            "item_type": "test",
            "bloom_level": "understand",
            "question": "Con ticket vs sin ticket?",
            "options": ["igual", "7 dias", "vale", "nada"],
        },
    ]
    answer_key = {
        ITEM_A: {"correct": 1, "explanation": "30 dias con ticket."},
        ITEM_B: {"correct": 2, "explanation": "Sin ticket, vale."},
    }
    if with_c:
        items.append(
            {
                "item_id": ITEM_C,
                "item_type": "fill_blank",
                "bloom_level": "apply",
                "template": "Con ticket son ___ dias.",
            }
        )
        answer_key[ITEM_C] = {"blanks": ["30"], "explanation": "Treinta."}
    return items, answer_key


@dataclass
class FakeNode:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    title: str = CANON_TITLE
    summary: str = CANON_SUMMARY
    outcome: str | None = CANON_OUTCOME
    criticality: str = "recommended"
    mastery_threshold: float | None = None
    seed_lesson_id: uuid.UUID | None = None
    probe_items: list = field(default_factory=list)
    probe_answer_key: dict = field(default_factory=dict)


@dataclass
class FakeProbe:
    user_id: uuid.UUID
    node_id: uuid.UUID
    schema_version: int
    items: list
    answer_key: dict
    answers: list = field(default_factory=list)
    attempt_no: int = 1
    scored: bool = True
    tiebreak_used: bool = False
    score: float | None = None
    mastered: bool | None = None
    model: str | None = None
    completed_at: datetime | None = None
    created_at: datetime = NOW
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeState:
    user_id: uuid.UUID
    node_id: uuid.UUID
    state: str = "not_started"
    mastery: float = 0.0
    probe_score: float | None = None
    consecutive_correct: int = 0
    consecutive_failed: int = 0
    hints_used: int = 0
    attempts_count: int = 0
    last_error_kind: str | None = None
    scaffold_band: str = "neutral"
    first_seen_at: datetime | None = None
    mastered_at: datetime | None = None


@dataclass
class FakeProfile:
    experience_level: str = "unknown"
    nodes_completed: int = 0


@dataclass
class FakeExercise:
    type: str
    content: dict
    position: int = 0


class FakeProbeRepo:
    def __init__(self) -> None:
        self.rows: list[FakeProbe] = []
        self.creates = 0

    async def get_scored(self, *, user_id, node_id, schema_version):
        for row in self.rows:
            if (
                row.user_id == user_id
                and row.node_id == node_id
                and row.schema_version == schema_version
                and row.scored
            ):
                return row
        return None

    async def latest(self, *, user_id, node_id):
        matching = [r for r in self.rows if r.user_id == user_id and r.node_id == node_id]
        return matching[-1] if matching else None

    async def next_attempt_no(self, *, user_id, node_id):
        matching = [r for r in self.rows if r.user_id == user_id and r.node_id == node_id]
        return max((r.attempt_no for r in matching), default=0) + 1

    async def create(self, **kwargs):
        self.creates += 1
        row = FakeProbe(**kwargs)
        self.rows.append(row)
        return row

    async def supersede(self, probe):
        probe.scored = False
        return probe

    async def update(self, obj, **kwargs):
        for key, value in kwargs.items():
            setattr(obj, key, value)
        return obj


class FakeAttemptRepo:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def record(self, **kwargs):
        self.rows.append(kwargs)
        return kwargs

    async def count_failures_for_item(self, *, user_id, node_id, item_id):
        return sum(
            1
            for r in self.rows
            if r["user_id"] == user_id
            and r["node_id"] == node_id
            and r["item_id"] == item_id
            and not r["passed"]
        )


class FakeStateRepo:
    def __init__(self, state: FakeState | None = None) -> None:
        self.state = state
        self.applied: list[Any] = []

    async def get_or_create(self, *, user_id, node_id, mastery=0.0):
        if self.state is None:
            self.state = FakeState(user_id=user_id, node_id=node_id, mastery=mastery)
        return self.state

    async def apply_transition(self, state, transition, *, now=None):
        self.applied.append(transition)
        state.state = transition.to_state
        for column, value in transition.changes.items():
            setattr(state, column, value)
        if transition.attempts_delta:
            state.attempts_count += transition.attempts_delta
        if transition.stamp_first_seen_at and state.first_seen_at is None:
            state.first_seen_at = now or NOW
        if transition.stamp_mastered_at and state.mastered_at is None:
            state.mastered_at = now or NOW
        return state


class FakeExerciseRepo:
    def __init__(self, exercises: list[FakeExercise]) -> None:
        self.exercises = exercises

    async def list(self, **_kwargs):
        return self.exercises, len(self.exercises)


class RecordingLLM:
    """Counts calls, so "generated nothing" is an assertion and not a hope."""

    model = "fixture/local"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system_prompt, user_prompt, **_kwargs):
        self.calls.append((system_prompt, user_prompt))
        return self.response


def build_service(
    *,
    node: FakeNode,
    state: FakeState | None = None,
    llm: Any | None = None,
    exercises: list[FakeExercise] | None = None,
) -> tuple[ProbeService, FakeProbeRepo, FakeAttemptRepo, FakeStateRepo]:
    probe_repo = FakeProbeRepo()
    attempt_repo = FakeAttemptRepo()
    state_repo = FakeStateRepo(state)
    service = ProbeService(
        probe_repo=probe_repo,
        attempt_repo=attempt_repo,
        state_repo=state_repo,
        exercise_repo=FakeExerciseRepo(exercises) if exercises is not None else None,
        llm=llm,
    )
    return service, probe_repo, attempt_repo, state_repo


def canonical_node(**overrides: Any) -> FakeNode:
    return FakeNode(**overrides)


# --- the anti-retry rule (§3.4) ---------------------------------------------


async def test_second_probe_serves_the_stored_verdict_and_generates_nothing():
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    llm = RecordingLLM("{}")
    service, probe_repo, _attempts, _states = build_service(node=node, llm=llm)
    user_id = uuid.uuid4()

    first = await service.start_probe(user_id=user_id, node=node, schema_version=3, now=NOW)
    assert first.reused is False
    assert probe_repo.creates == 1

    # Answer both items perfectly -> mastered on a `recommended` node.
    await service.submit_answer(
        user_id=user_id, node=node, probe=first.probe, item_id=ITEM_A,
        answer={"selected": 1}, now=NOW,
    )
    final = await service.submit_answer(
        user_id=user_id, node=node, probe=first.probe, item_id=ITEM_B,
        answer={"selected": 2}, now=NOW,
    )
    assert final.verdict == "mastered"

    second = await service.start_probe(user_id=user_id, node=node, schema_version=3, now=NOW)
    assert second.reused is True
    assert second.verdict == "mastered"
    assert second.probe is first.probe
    assert probe_repo.creates == 1  # no new hand dealt
    assert llm.calls == []  # and no tokens spent


async def test_sixteen_reentries_cannot_brute_force_a_verdict():
    """The concrete attack: 2 items x 4 options is guessed 1 time in 16, so without the
    single-scored-probe rule ~16 re-entries would skip any node."""
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, probe_repo, _a, _s = build_service(node=node)
    user_id = uuid.uuid4()

    opened = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)
    await service.submit_answer(
        user_id=user_id, node=node, probe=opened.probe, item_id=ITEM_A,
        answer={"selected": 0}, now=NOW,
    )
    outcome = await service.submit_answer(
        user_id=user_id, node=node, probe=opened.probe, item_id=ITEM_B,
        answer={"selected": 0}, now=NOW,
    )
    assert outcome.verdict == "learning"

    for _ in range(16):
        again = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)
        assert again.reused is True
        assert again.verdict == "learning"
    assert probe_repo.creates == 1


async def test_a_new_schema_version_is_a_new_probe():
    """The scoped-by-version rule: editing the schema legitimately re-opens the probe."""
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, probe_repo, _a, _s = build_service(node=node)
    user_id = uuid.uuid4()

    await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)
    await service.start_probe(user_id=user_id, node=node, schema_version=2, now=NOW)
    assert probe_repo.creates == 2
    assert [row.attempt_no for row in probe_repo.rows] == [1, 2]


async def test_answering_the_same_item_twice_is_rejected():
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, _p, _a, _s = build_service(node=node)
    user_id = uuid.uuid4()
    opened = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)

    await service.submit_answer(
        user_id=user_id, node=node, probe=opened.probe, item_id=ITEM_A,
        answer={"selected": 1}, now=NOW,
    )
    with pytest.raises(ConflictError):
        await service.submit_answer(
            user_id=user_id, node=node, probe=opened.probe, item_id=ITEM_A,
            answer={"selected": 1}, now=NOW,
        )


async def test_answering_a_closed_probe_is_rejected():
    items, key = make_items(with_c=False)
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, _p, _a, _s = build_service(node=node)
    user_id = uuid.uuid4()
    opened = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)

    await service.submit_answer(
        user_id=user_id, node=node, probe=opened.probe, item_id=ITEM_A,
        answer={"selected": 1}, now=NOW,
    )
    await service.submit_answer(
        user_id=user_id, node=node, probe=opened.probe, item_id=ITEM_B,
        answer={"selected": 2}, now=NOW,
    )
    with pytest.raises(ConflictError):
        await service.submit_answer(
            user_id=user_id, node=node, probe=opened.probe, item_id=ITEM_A,
            answer={"selected": 1}, now=NOW,
        )


async def test_an_unknown_item_id_is_rejected():
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, _p, _a, _s = build_service(node=node)
    user_id = uuid.uuid4()
    opened = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)
    with pytest.raises(ValidationError):
        await service.submit_answer(
            user_id=user_id, node=node, probe=opened.probe, item_id="z",
            answer={"selected": 1}, now=NOW,
        )


# --- re-probe (§3.4) ---------------------------------------------------------


async def test_reprobe_is_refused_from_learning():
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    state = FakeState(user_id=uuid.uuid4(), node_id=node.id, state="learning")
    service, probe_repo, _a, _s = build_service(node=node, state=state)
    probe_repo.rows.append(
        FakeProbe(
            user_id=state.user_id,
            node_id=node.id,
            schema_version=1,
            items=items,
            answer_key=key,
            completed_at=NOW - timedelta(days=90),
        )
    )
    with pytest.raises(ConflictError):
        await service.start_probe(
            user_id=state.user_id, node=node, schema_version=1, reprobe=True, now=NOW
        )


async def test_reprobe_is_refused_before_seven_days():
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    state = FakeState(user_id=uuid.uuid4(), node_id=node.id, state="needs_review")
    service, probe_repo, _a, _s = build_service(node=node, state=state)
    probe_repo.rows.append(
        FakeProbe(
            user_id=state.user_id,
            node_id=node.id,
            schema_version=1,
            items=items,
            answer_key=key,
            completed_at=NOW - timedelta(days=REPROBE_COOLDOWN_DAYS - 1),
        )
    )
    with pytest.raises(ConflictError):
        await service.start_probe(
            user_id=state.user_id, node=node, schema_version=1, reprobe=True, now=NOW
        )


async def test_reprobe_from_needs_review_after_seven_days_supersedes_the_old_row():
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    state = FakeState(user_id=uuid.uuid4(), node_id=node.id, state="needs_review", mastery=0.4)
    service, probe_repo, _a, state_repo = build_service(node=node, state=state)
    old = FakeProbe(
        user_id=state.user_id,
        node_id=node.id,
        schema_version=1,
        items=items,
        answer_key=key,
        completed_at=NOW - timedelta(days=REPROBE_COOLDOWN_DAYS),
        score=0.4,
        mastered=False,
    )
    probe_repo.rows.append(old)

    session = await service.start_probe(
        user_id=state.user_id, node=node, schema_version=1, reprobe=True, now=NOW
    )
    assert session.reused is False
    assert old.scored is False  # the evidence is kept, the index is freed
    assert session.probe.scored is True
    assert session.probe.attempt_no == 2
    assert state.state == "probing"
    # The mastery already earned is not thrown away by re-opening the probe.
    assert state.mastery == pytest.approx(0.4)


# --- the diagnostic probe (§7.1) ---------------------------------------------


def test_is_diagnostic_probe_needs_both_conditions():
    assert is_diagnostic_probe(FakeProfile(experience_level="none", nodes_completed=0)) is True
    assert is_diagnostic_probe(FakeProfile(experience_level="none", nodes_completed=1)) is False
    assert is_diagnostic_probe(FakeProfile(experience_level="unknown", nodes_completed=0)) is False
    assert is_diagnostic_probe(None) is False


async def test_diagnostic_probe_neither_scores_nor_consumes_the_single_attempt():
    items, key = make_items(with_c=False)
    node = canonical_node(probe_items=items, probe_answer_key=key)
    profile = FakeProfile(experience_level="none", nodes_completed=0)
    service, probe_repo, attempt_repo, state_repo = build_service(node=node)
    user_id = uuid.uuid4()

    session = await service.start_probe(
        user_id=user_id, node=node, schema_version=1, profile=profile, now=NOW
    )
    assert session.diagnostic is True
    assert session.probe.scored is False

    await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_A,
        answer={"selected": 0}, profile=profile, now=NOW,
    )
    outcome = await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_B,
        answer={"selected": 0}, profile=profile, now=NOW,
    )

    # It reports a verdict, but it persists no failures and moves no state.
    assert outcome.verdict == "learning"
    assert outcome.transition is None
    assert attempt_repo.rows == []
    assert state_repo.state.probe_score is None
    assert state_repo.state.state == "probing"

    # And the single scored attempt is still available: nothing was consumed.
    profile.nodes_completed = 1
    second = await service.start_probe(
        user_id=user_id, node=node, schema_version=1, profile=profile, now=NOW
    )
    assert second.reused is False
    assert second.probe.scored is True
    assert probe_repo.creates == 2


async def test_reopening_a_diagnostic_probe_deals_the_same_hand():
    """A declared novice must not mint a ``node_probes`` row per page reload.

    ``get_scored`` mirrors the partial unique index, so it cannot see a diagnostic probe
    (§7.1 writes it with ``scored = false``) and the anti-retry rule of §3.4 never applied
    to one. ``ProbeRunner`` fires ``POST /probe`` from a mount effect, so every remount used
    to deal a fresh hand — unbounded, and paying ``runtime_fast`` for it in any course whose
    probe pre-generation had degraded.
    """
    items, key = make_items(with_c=False)
    node = canonical_node(probe_items=[], probe_answer_key={})
    llm = RecordingLLM(json.dumps({"items": items, "answer_key": key}))
    profile = FakeProfile(experience_level="none", nodes_completed=0)
    service, probe_repo, _attempts, _states = build_service(node=node, llm=llm)
    user_id = uuid.uuid4()

    dealt: list[dict] = []
    original_build = service.build_items

    async def counting_build(**kwargs):
        dealt.append(kwargs)
        return await original_build(**kwargs)

    service.build_items = counting_build  # type: ignore[method-assign]

    first = await service.start_probe(
        user_id=user_id, node=node, schema_version=1, profile=profile,
        source_context=CANON_SOURCE, now=NOW,
    )
    second = await service.start_probe(
        user_id=user_id, node=node, schema_version=1, profile=profile,
        source_context=CANON_SOURCE, now=NOW,
    )

    assert first.diagnostic is True and first.probe.scored is False
    assert second.probe is first.probe
    assert second.reused is True
    assert second.diagnostic is True
    # One row, one hand, one generation — whatever the client does on mount.
    assert probe_repo.creates == 1
    assert len(dealt) == 1
    assert len(llm.calls) == 1
    # The items are the same ones, not a re-roll under the same id.
    assert [item["item_id"] for item in second.items] == [
        item["item_id"] for item in first.items
    ]


async def test_an_open_probe_of_an_older_schema_version_is_not_reused():
    """The reuse guard is per ``schema_version``: editing the node re-deals."""
    items, key = make_items(with_c=False)
    node = canonical_node(probe_items=items, probe_answer_key=key)
    profile = FakeProfile(experience_level="none", nodes_completed=0)
    service, probe_repo, _attempts, _states = build_service(node=node)
    user_id = uuid.uuid4()

    await service.start_probe(
        user_id=user_id, node=node, schema_version=1, profile=profile, now=NOW
    )
    reopened = await service.start_probe(
        user_id=user_id, node=node, schema_version=2, profile=profile, now=NOW
    )

    assert reopened.reused is False
    assert probe_repo.creates == 2


# --- verdict flow -----------------------------------------------------------


async def test_critical_node_always_serves_the_tiebreak_item():
    items, key = make_items()
    node = canonical_node(criticality="critical", probe_items=items, probe_answer_key=key)
    service, _p, _a, state_repo = build_service(node=node)
    user_id = uuid.uuid4()

    session = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)
    assert [item["item_id"] for item in session.items] == [ITEM_A, ITEM_B, ITEM_C]

    await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_A,
        answer={"selected": 1}, now=NOW,
    )
    mid = await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_B,
        answer={"selected": 2}, now=NOW,
    )
    # 2/2 on a critical node is a candidate, not a verdict.
    assert mid.verdict is None
    assert mid.next_item_id == ITEM_C
    assert session.probe.tiebreak_used is True
    assert state_repo.state.state == "probing"

    final = await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_C,
        answer={"answers": ["30"]}, now=NOW,
    )
    assert final.verdict == "mastered"
    assert final.render_hint == "skip"
    assert state_repo.state.state == "mastered"
    assert state_repo.state.mastered_at == NOW
    assert session.probe.mastered is True


async def test_critical_node_with_a_failed_tiebreak_learns():
    items, key = make_items()
    node = canonical_node(criticality="critical", probe_items=items, probe_answer_key=key)
    service, _p, _a, state_repo = build_service(node=node)
    user_id = uuid.uuid4()
    session = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)

    for item_id, answer in ((ITEM_A, {"selected": 1}), (ITEM_B, {"selected": 2})):
        await service.submit_answer(
            user_id=user_id, node=node, probe=session.probe, item_id=item_id,
            answer=answer, now=NOW,
        )
    final = await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_C,
        answer={"answers": ["15"]}, now=NOW,
    )
    assert final.verdict == "learning"
    assert final.render_hint == "prefetch"
    assert state_repo.state.state == "learning"
    assert state_repo.state.probe_score == pytest.approx(0.60)


async def test_the_tiebreak_item_is_hidden_until_the_doubt_band_is_hit():
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)  # recommended
    service, _p, _a, _s = build_service(node=node)
    user_id = uuid.uuid4()

    session = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)
    assert [item["item_id"] for item in session.items] == [ITEM_A, ITEM_B]

    await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_A,
        answer={"selected": 1}, now=NOW,
    )
    mid = await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_B,
        answer={"selected": 0}, now=NOW,
    )
    assert mid.verdict is None
    assert mid.next_item_id == ITEM_C
    assert mid.estimate == pytest.approx(0.6)

    reopened = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)
    assert [item["item_id"] for item in reopened.items] == [ITEM_A, ITEM_B, ITEM_C]


async def test_doubt_band_without_a_tiebreak_item_resolves_to_learning():
    """Never to `mastered`: an unconfirmed 0.6 is exactly the doubt the rule exists for."""
    items, key = make_items(with_c=False)
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, _p, _a, state_repo = build_service(node=node)
    user_id = uuid.uuid4()
    session = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)

    await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_A,
        answer={"selected": 1}, now=NOW,
    )
    final = await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_B,
        answer={"selected": 0}, now=NOW,
    )
    assert final.verdict == "learning"
    assert state_repo.state.state == "learning"


async def test_failing_apply_prefetches_the_render_immediately():
    """§9.1: the render is fired in the background as soon as `mastered` is out of reach."""
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, _p, _a, _s = build_service(node=node)
    user_id = uuid.uuid4()
    session = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)

    outcome = await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_A,
        answer={"selected": 3}, now=NOW,
    )
    assert outcome.verdict is None
    assert outcome.render_hint == "prefetch"
    assert outcome.next_item_id == ITEM_B
    assert outcome.error_kind == "conceptual"


async def test_a_correct_apply_answer_does_not_prefetch_yet():
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, _p, _a, _s = build_service(node=node)
    user_id = uuid.uuid4()
    session = await service.start_probe(user_id=user_id, node=node, schema_version=1, now=NOW)

    outcome = await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_A,
        answer={"selected": 1}, now=NOW,
    )
    assert outcome.render_hint is None


async def test_probe_records_attempts_and_seeds_the_prior():
    items, key = make_items(with_c=False)
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, _p, attempt_repo, state_repo = build_service(node=node)
    user_id = uuid.uuid4()

    session = await service.start_probe(
        user_id=user_id, node=node, schema_version=1, user_skill_level="medium", now=NOW
    )
    assert state_repo.state.state == "probing"
    assert state_repo.state.mastery == pytest.approx(0.55)  # prior from user_skills
    assert state_repo.state.first_seen_at == NOW

    await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_A,
        answer={"selected": 1}, now=NOW,
    )
    assert len(attempt_repo.rows) == 1
    assert attempt_repo.rows[0]["probe_id"] == session.probe.id
    assert attempt_repo.rows[0]["bloom_level"] == "apply"

    final = await service.submit_answer(
        user_id=user_id, node=node, probe=session.probe, item_id=ITEM_B,
        answer={"selected": 0}, now=NOW,
    )
    # `learning` verdict keeps the prior; only probe_score is written.
    assert final.verdict == "learning"
    assert state_repo.state.mastery == pytest.approx(0.55)
    assert state_repo.state.probe_score == pytest.approx(0.6)


# --- item sources (§7.1) ----------------------------------------------------


async def test_pregenerated_items_cost_nothing():
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    llm = RecordingLLM("{}")
    service, _p, _a, _s = build_service(node=node, llm=llm)
    built, built_key, model = await service.build_items(node=node)
    assert built == items
    assert built_key == key
    assert model is None
    assert llm.calls == []


async def test_seed_lesson_is_preferred_over_the_llm():
    node = canonical_node(seed_lesson_id=uuid.uuid4())
    exercises = [
        FakeExercise(
            "test",
            {
                "question": "Caso practico.",
                "options": ["a", "b", "c", "d"],
                "correct": 2,
                "explanation": "porque",
            },
        ),
        FakeExercise(
            "test",
            {
                "question": "Comprension.",
                "options": ["a", "b", "c", "d"],
                "correct": 0,
                "explanation": "porque",
            },
        ),
        FakeExercise("fill_blank", {"template": "Son ___ dias.", "blanks": ["30"]}),
    ]
    llm = RecordingLLM("{}")
    service, _p, _a, _s = build_service(node=node, llm=llm, exercises=exercises)

    items, key, model = await service.build_items(node=node)
    assert [item["item_id"] for item in items] == [ITEM_A, ITEM_B, ITEM_C]
    assert [item["bloom_level"] for item in items[:2]] == ["apply", "understand"]
    assert key[ITEM_A]["correct"] == 2
    assert model is None
    assert llm.calls == []
    # ...and they are written back onto the node so nobody pays for it again.
    assert node.probe_items == items
    assert node.probe_answer_key == key


def test_seed_sampler_refuses_what_it_cannot_fill():
    # Only one usable test -> slots A and B cannot both be filled.
    assert seed_probe_items(
        [FakeExercise("test", {"question": "q", "options": ["a", "b", "c", "d"], "correct": 0})]
    ) == ([], {})
    # true_false is never usable as a probe item.
    assert seed_probe_items(
        [FakeExercise("true_false", {"statement": "s", "correct": True})] * 3
    ) == ([], {})
    # A critical node with no constructed exercise cannot be probed from the seed:
    # selected response alone can never master it, so the sample is refused.
    two_tests = [
        FakeExercise("test", {"question": "q1", "options": ["a", "b", "c", "d"], "correct": 0}),
        FakeExercise("test", {"question": "q2", "options": ["a", "b", "c", "d"], "correct": 1}),
    ]
    assert seed_probe_items(two_tests, criticality="critical") == ([], {})
    items, _key = seed_probe_items(two_tests, criticality="recommended")
    assert [item["item_id"] for item in items] == [ITEM_A, ITEM_B]


async def test_generation_last_resort_uses_the_shipped_fixture():
    """End to end through ``FixtureLLMService``: real prompt, recorded response, no network.

    If this fails with "No LLM fixture for key ...", the canonical prompt changed.
    Re-record ``src/llm/fixture_data/probe_generate/plazo_devolucion.json`` and update
    its key in ``index.json`` — do not weaken the assertion.
    """
    node = canonical_node(criticality="critical")
    llm = FixtureLLMService(
        LLMConfig(model="fixture/local", api_base=None, api_key=None),
        directory=FIXTURE_DIR,
    )
    service, _p, _a, _s = build_service(node=node, llm=llm)

    items, key, model = await service.build_items(node=node, source_context=CANON_SOURCE)
    assert [item["item_id"] for item in items] == [ITEM_A, ITEM_B, ITEM_C]
    assert key[ITEM_C]["blanks"] == ["30"]
    assert model == "fixture/local"
    # Written back onto the node: the next employee gets it for free.
    assert node.probe_items == items

    # And the fixture really is keyed on the prompt this module builds.
    expected_key = FixtureLLMService.key_for(
        PROBE_GENERATOR_SYSTEM,
        build_probe_prompt(
            title=CANON_TITLE,
            summary=CANON_SUMMARY,
            outcome=CANON_OUTCOME,
            criticality="critical",
            source_context=CANON_SOURCE,
        ),
    )
    index = json.loads((FIXTURE_DIR / "index.json").read_text(encoding="utf-8"))
    assert index[expected_key]["file"] == "probe_generate/plazo_devolucion.json"
    assert index[expected_key]["use_case"] == "probe_generate"


async def test_no_items_no_seed_and_no_llm_is_an_explicit_error():
    node = canonical_node()
    service, _p, _a, _s = build_service(node=node)
    with pytest.raises(LLMError) as excinfo:
        await service.build_items(node=node)
    assert "no pre-generated" in str(excinfo.value)


# --- the item contract ------------------------------------------------------


def test_validate_rejects_true_false():
    items, key = make_items(with_c=False)
    items[1]["item_type"] = "true_false"
    with pytest.raises(ValidationError) as excinfo:
        validate_probe_items(items, key)
    assert "12.5" in str(excinfo.value)


def test_validate_requires_four_options():
    items, key = make_items(with_c=False)
    items[0]["options"] = ["a", "b", "c"]
    with pytest.raises(ValidationError):
        validate_probe_items(items, key)


def test_validate_requires_the_right_bloom_levels():
    items, key = make_items(with_c=False)
    items[0]["bloom_level"] = "remember"
    with pytest.raises(ValidationError):
        validate_probe_items(items, key)


def test_validate_requires_a_usable_answer_key():
    items, key = make_items(with_c=False)
    del key[ITEM_A]["correct"]
    with pytest.raises(ValidationError):
        validate_probe_items(items, key)

    items, key = make_items(with_c=False)
    key[ITEM_B]["correct"] = 7
    with pytest.raises(ValidationError):
        validate_probe_items(items, key)

    items, key = make_items(with_c=False)
    key[ITEM_A]["correct"] = True  # a bool is not an option index
    with pytest.raises(ValidationError):
        validate_probe_items(items, key)


def test_validate_requires_the_tiebreak_on_a_critical_node():
    items, key = make_items(with_c=False)
    with pytest.raises(ValidationError) as excinfo:
        validate_probe_items(items, key, "critical")
    assert "critical" in str(excinfo.value)
    validate_probe_items(items, key, "recommended")  # fine without it


def test_validate_rejects_a_selected_response_tiebreak():
    items, key = make_items()
    items[2]["item_type"] = "test"
    items[2]["options"] = ["a", "b", "c", "d"]
    key[ITEM_C] = {"correct": 0}
    with pytest.raises(ValidationError):
        validate_probe_items(items, key, "critical")


def test_validate_requires_blanks_for_a_fill_blank_tiebreak():
    items, key = make_items()
    key[ITEM_C] = {"explanation": "sin blanks"}
    with pytest.raises(ValidationError):
        validate_probe_items(items, key, "critical")


def test_missing_items_are_rejected():
    items, key = make_items(with_c=False)
    with pytest.raises(ValidationError):
        validate_probe_items(items[:1], key)


def test_parse_probe_response_wraps_contract_failures_as_llm_errors():
    items, key = make_items()
    items[1]["item_type"] = "true_false"
    payload = json.dumps({"items": items, "answer_key": key})
    with pytest.raises(LLMError):
        parse_probe_response(payload)

    with pytest.raises(LLMError):
        parse_probe_response('{"nope": 1}')

    # A fenced response is recovered by `parse_json_response`, then validated.
    good_items, good_key = make_items()
    fenced = "```json\n" + json.dumps({"items": good_items, "answer_key": good_key}) + "\n```"
    parsed_items, parsed_key = parse_probe_response(fenced, criticality="critical")
    assert [item["item_id"] for item in parsed_items] == [ITEM_A, ITEM_B, ITEM_C]
    assert parsed_key == good_key


def test_served_items_never_carry_an_answer():
    items, key = make_items()
    items[0]["correct"] = 1  # a generator that misplaces the answer
    served = served_items(items, criticality="critical", tiebreak_used=False)
    assert all("correct" not in item for item in served)
    assert key[ITEM_A]["correct"] == 1  # the real key is untouched
