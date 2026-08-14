from src.services.experience_resolver import (
    ExperienceCandidate,
    ExperienceRequirements,
    RuntimeExperienceContext,
    resolve_experience,
)


def candidate(ref: str, **changes) -> ExperienceCandidate:
    values = {
        "binding_id": f"binding-{ref}",
        "implementation_ref": ref,
        "provider": ref.split(".", 1)[0],
        "intents": frozenset({"guided_practice"}),
        "learner_actions": frozenset({"sequence"}),
        "representations": frozenset({"procedural"}),
        "evidence": frozenset({"correct_sequence"}),
        "required_ports": frozenset({"evaluation"}),
    }
    values.update(changes)
    return ExperienceCandidate(**values)


def test_hard_gates_run_before_ranking() -> None:
    requirements = ExperienceRequirements(
        intent="guided_practice",
        learner_actions=frozenset({"sequence"}),
        required_evidence=frozenset({"correct_sequence"}),
    )
    context = RuntimeExperienceContext(available_ports=frozenset({"evaluation"}))
    invalid = candidate(
        "video.passive@1",
        evidence=frozenset(),
        pedagogical_quality=1.0,
    )
    valid = candidate("didact.sort@1", pedagogical_quality=0.4)

    result = resolve_experience(requirements, [invalid, valid], context)

    assert result.selected == valid
    assert [(item.binding_id, item.reason) for item in result.rejected] == [
        (invalid.binding_id, "evidence")
    ]


def test_context_can_choose_between_equivalent_implementations() -> None:
    requirements = ExperienceRequirements(
        intent="guided_practice",
        learner_actions=frozenset({"sequence"}),
        required_evidence=frozenset({"correct_sequence"}),
    )
    context = RuntimeExperienceContext(
        available_ports=frozenset({"evaluation"}),
        preferred_representations=frozenset({"visual"}),
        recent_implementation_refs=("didact.sort@1",),
    )
    didact = candidate("didact.sort@1", pedagogical_quality=0.7)
    simulation = candidate(
        "simulation.sequence@1",
        representations=frozenset({"procedural", "visual"}),
        pedagogical_quality=0.7,
    )

    result = resolve_experience(requirements, [didact, simulation], context)

    assert result.selected == simulation


def test_runtime_selection_is_stable_and_has_no_provider_branch() -> None:
    requirements = ExperienceRequirements(intent="guided_practice")
    context = RuntimeExperienceContext(available_ports=frozenset({"evaluation"}))
    values = [
        candidate("video.checkpoint@1"),
        candidate("didact.sort@1"),
        candidate("game.sequence@1"),
    ]

    first = resolve_experience(requirements, values, context)
    second = resolve_experience(requirements, list(reversed(values)), context)

    assert [item.implementation_ref for item in first.candidates] == [
        item.implementation_ref for item in second.candidates
    ]


def test_accessibility_and_budget_fail_closed() -> None:
    requirements = ExperienceRequirements(intent="guided_practice")
    context = RuntimeExperienceContext(
        available_ports=frozenset({"evaluation"}),
        keyboard_required=True,
        low_bandwidth=True,
        max_latency_ms=100,
        max_cost_micros=0,
    )
    values = [
        candidate("game.drag@1", keyboard=False),
        candidate("video.large@1", low_bandwidth=False),
        candidate("simulation.remote@1", latency_ms=500),
        candidate("media.paid@1", cost_micros=1),
    ]

    result = resolve_experience(requirements, values, context)

    assert result.selected is None
    assert [item.reason for item in result.rejected] == [
        "keyboard",
        "bandwidth",
        "latency",
        "cost",
    ]
