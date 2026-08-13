from src.personalization.novelty import ranking_collapse, useful_novelty_tiebreak
from src.personalization.plan import ComponentCandidate, Presentation, ProducerKind


def candidate(
    component_id: str,
    *,
    rank: int = 100,
    evidence: frozenset[str] = frozenset({"attempt"}),
) -> ComponentCandidate:
    return ComponentCandidate(
        component_id=component_id,
        version=1,
        presentation=Presentation.SIMULATION,
        producer_kind=ProducerKind.SIMULATION,
        affordances=frozenset({"manipulate"}),
        evidence_events=evidence,
        state_model_ref=None,
        rank=rank,
    )


def test_novelty_only_reorders_exactly_equivalent_candidates() -> None:
    best = candidate("best", rank=10)
    repeated = candidate("repeated")
    fresh = candidate("fresh")
    different_evidence = candidate("different", evidence=frozenset({"completion"}))

    result = useful_novelty_tiebreak(
        (best, repeated, fresh, different_evidence),
        prior_exposure={"best": 99, "repeated": 8, "fresh": 0, "different": 0},
    )

    assert [item.component_id for item in result] == [
        "best", "fresh", "repeated", "different"
    ]


def test_ranking_collapse_detects_dominant_top_component() -> None:
    rankings = [(candidate("same"), candidate(f"other-{index}")) for index in range(8)]

    result = ranking_collapse(rankings)

    assert result.collapsed is True
    assert result.dominant_component == "same"
    assert result.dominant_share == 1.0

