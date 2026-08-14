from collections.abc import Iterable

import pytest

from src.personalization.capability_broker import (
    CapabilityBroker,
    CapabilityDescriptor,
    CapabilityGate,
    CapabilityRequest,
    CapabilityShortlist,
    Declined,
    GateFailure,
    descriptors_from_didact,
    request_from_episode,
)
from src.personalization.didact_catalog import load_didact_catalog
from src.schemas.episode_contracts import (
    CompetencyContract,
    DominantAction,
    EpisodeBrief,
    EpisodeBudget,
    EvidenceGate,
    SourceAffordance,
    SourceAffordanceMap,
)


def capability(ref: str, **changes: object) -> CapabilityDescriptor:
    values: dict[str, object] = {
        "implementation_ref": ref,
        "provider": ref.split(".", 1)[0],
        "learner_actions": frozenset({"decide"}),
        "evidence": frozenset({"decision"}),
        "affordances": frozenset({"choose"}),
        "accessibility": frozenset({"keyboard", "screen_reader"}),
        "safety": frozenset({"source_grounded"}),
        "required_ports": frozenset({"evaluation"}),
        "latency_ms": 100,
    }
    values.update(changes)
    return CapabilityDescriptor(**values)  # type: ignore[arg-type]


def test_gestion_tickets_and_sql_require_radically_different_capabilities() -> None:
    ticket_options = [
        capability(
            f"operations.ticket-recovery-{index}@1",
            learner_actions=frozenset({"diagnose", "navigate", "decide"}),
            evidence=frozenset({"resolved_case"}),
            affordances=frozenset({"inspect_source_ui", "choose_recovery_path"}),
            safety=frozenset({"source_grounded", "customer_data_redacted"}),
            required_ports=frozenset({"evaluation", "simulation"}),
        )
        for index in range(3)
    ]
    sql_options = [
        capability(
            f"sandbox.sql-query-{index}@1",
            learner_actions=frozenset({"construct_query", "debug"}),
            evidence=frozenset({"executable_query"}),
            affordances=frozenset({"edit_code", "execute_code", "inspect_error"}),
            safety=frozenset({"sandboxed_execution"}),
            required_ports=frozenset({"evaluation", "execution"}),
        )
        for index in range(3)
    ]
    broker = CapabilityBroker([*ticket_options, *sql_options])

    tickets = broker.resolve(
        CapabilityRequest(
            learner_actions=frozenset({"diagnose", "navigate"}),
            evidence=frozenset({"resolved_case"}),
            affordances=frozenset({"inspect_source_ui"}),
            accessibility=frozenset({"keyboard", "screen_reader"}),
            safety=frozenset({"source_grounded", "customer_data_redacted"}),
            available_ports=frozenset({"evaluation", "simulation"}),
        )
    )
    sql = broker.resolve(
        CapabilityRequest(
            learner_actions=frozenset({"construct_query", "debug"}),
            evidence=frozenset({"executable_query"}),
            affordances=frozenset({"edit_code", "execute_code"}),
            accessibility=frozenset({"keyboard"}),
            safety=frozenset({"sandboxed_execution"}),
            available_ports=frozenset({"evaluation", "execution"}),
        )
    )

    assert isinstance(tickets, CapabilityShortlist)
    assert isinstance(sql, CapabilityShortlist)
    assert {item.provider for item in tickets.candidates} == {"operations"}
    assert {item.provider for item in sql.candidates} == {"sandbox"}
    assert not set(tickets.candidates) & set(sql.candidates)


@pytest.mark.parametrize(
    ("change", "gate"),
    [
        ({"learner_actions": frozenset()}, CapabilityGate.LEARNER_ACTION),
        ({"evidence": frozenset()}, CapabilityGate.EVIDENCE),
        ({"affordances": frozenset()}, CapabilityGate.AFFORDANCE),
        ({"accessibility": frozenset()}, CapabilityGate.ACCESSIBILITY),
        ({"safety": frozenset()}, CapabilityGate.SAFETY),
        ({"required_ports": frozenset({"execution"})}, CapabilityGate.PORTS),
        ({"latency_ms": 501}, CapabilityGate.LATENCY),
    ],
)
def test_every_constraint_is_a_hard_gate(
    change: dict[str, object], gate: CapabilityGate
) -> None:
    request = CapabilityRequest(
        learner_actions=frozenset({"decide"}),
        evidence=frozenset({"decision"}),
        affordances=frozenset({"choose"}),
        accessibility=frozenset({"keyboard"}),
        safety=frozenset({"source_grounded"}),
        available_ports=frozenset({"evaluation"}),
        latency_budget_ms=500,
    )

    result = CapabilityBroker([capability("provider.invalid@1", **change)]).resolve(request)

    assert isinstance(result, Declined)
    assert gate in {failure.gate for failure in result.failures}


def test_ranking_is_deterministic_and_shortlist_is_bounded() -> None:
    request = CapabilityRequest(
        available_ports=frozenset({"evaluation"}),
        preferred_affordances=frozenset({"explain_choice"}),
        shortlist_size=3,
    )
    values = [
        capability("provider.c@1", quality_rank=20),
        capability("provider.b@1", quality_rank=10),
        capability(
            "provider.preferred@1",
            affordances=frozenset({"choose", "explain_choice"}),
            quality_rank=50,
        ),
        capability("provider.a@1", quality_rank=10),
        capability("provider.slower@1", quality_rank=10, latency_ms=200),
        capability("provider.omitted@1", quality_rank=30),
    ]

    first = CapabilityBroker(values).resolve(request)
    second = CapabilityBroker(reversed(values)).resolve(request)

    assert isinstance(first, CapabilityShortlist)
    assert isinstance(second, CapabilityShortlist)
    expected = [
        "provider.preferred@1",
        "provider.a@1",
        "provider.b@1",
    ]
    assert [item.implementation_ref for item in first.candidates] == expected
    assert [item.implementation_ref for item in second.candidates] == expected


def test_expansion_runs_once_without_relaxing_gates() -> None:
    calls = 0

    def expand() -> Iterable[CapabilityDescriptor]:
        nonlocal calls
        calls += 1
        return (
            capability("expanded.valid-a@1"),
            capability("expanded.valid-b@1"),
            capability("expanded.unsafe@1", safety=frozenset()),
        )

    request = CapabilityRequest(
        evidence=frozenset({"decision"}),
        safety=frozenset({"source_grounded"}),
        available_ports=frozenset({"evaluation"}),
    )
    result = CapabilityBroker(
        [capability("primary.unsafe@1", safety=frozenset())], expand_once=expand
    ).resolve(request)

    assert isinstance(result, CapabilityShortlist)
    assert result.expanded is True
    assert calls == 1
    assert {item.implementation_ref for item in result.candidates} == {
        "expanded.valid-a@1",
        "expanded.valid-b@1",
    }


def test_one_valid_primary_candidate_is_an_honest_shortlist_without_expansion() -> None:
    calls = 0

    def expand() -> Iterable[CapabilityDescriptor]:
        nonlocal calls
        calls += 1
        return (capability("expanded.unneeded@1"),)

    result = CapabilityBroker(
        [capability("primary.only-valid@1")], expand_once=expand
    ).resolve(CapabilityRequest(available_ports=frozenset({"evaluation"})))

    assert isinstance(result, CapabilityShortlist)
    assert [item.implementation_ref for item in result.candidates] == [
        "primary.only-valid@1"
    ]
    assert result.expanded is False
    assert calls == 0


def test_declines_when_one_expansion_still_has_no_valid_candidate() -> None:
    result = CapabilityBroker(
        [capability("primary.unsafe@1", safety=frozenset())],
        expand_once=lambda: [capability("expanded.unsafe@1", safety=frozenset())],
    ).resolve(
        CapabilityRequest(
            safety=frozenset({"source_grounded"}),
            available_ports=frozenset({"evaluation"}),
        )
    )

    assert isinstance(result, Declined)
    assert result.expanded is True
    assert result.eligible_count == 0
    assert result.failures == (GateFailure(CapabilityGate.SAFETY, 2),)


def test_duplicate_catalog_entries_cannot_fake_a_minimum_shortlist() -> None:
    duplicate = capability("provider.same@1")

    with pytest.raises(ValueError, match="duplicate implementation_ref"):
        CapabilityBroker([duplicate, duplicate, duplicate])


def test_didact_projection_uses_existing_catalog_and_fails_closed_on_safety() -> None:
    descriptors = descriptors_from_didact(load_didact_catalog())
    quiz = next(
        item for item in descriptors if item.implementation_ref.startswith("didact.quiz.single")
    )

    assert "select" in quiz.learner_actions
    assert "result:scored" in quiz.evidence
    assert "keyboard" in quiz.accessibility
    assert "evaluation" in quiz.required_ports
    assert quiz.safety == frozenset()


def test_episode_contract_projects_truth_without_provider_or_screen_vocabulary() -> None:
    competency = CompetencyContract.model_construct(
        evidence_gates=(
            EvidenceGate.model_construct(
                gate_id="complete-case", evidence_type="operational_case_result"
            ),
        )
    )
    sources = SourceAffordanceMap.model_construct(
        affordances=(
            SourceAffordance.model_construct(
                affordance_id="recovery-case", kind="operational_case"
            ),
        )
    )
    episode = EpisodeBrief.model_construct(
        dominant_action=DominantAction.model_construct(verb="recover_ticket"),
        evidence_gate_refs=("complete-case",),
        affordance_refs=("recovery-case",),
        budget=EpisodeBudget(
            max_content_units=3,
            max_interaction_steps=8,
            latency_budget_ms=2500,
        ),
    )

    request = request_from_episode(
        competency,
        sources,
        episode,
        accessibility=frozenset({"keyboard"}),
        safety=frozenset({"customer_data_redacted"}),
        available_ports=frozenset({"simulation", "evaluation"}),
    )

    assert request.learner_actions == frozenset({"recover_ticket"})
    assert request.evidence == frozenset({"operational_case_result"})
    assert request.affordances == frozenset({"operational_case"})
    assert request.latency_budget_ms == 2500


@pytest.mark.parametrize("size", [0, 4])
def test_shortlist_contract_rejects_sizes_outside_one_to_three(size: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 3"):
        CapabilityRequest(shortlist_size=size)
