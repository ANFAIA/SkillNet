from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.didact_course_creation_opportunities import run_experiment
from src.personalization.didact_catalog import load_didact_catalog
from src.personalization.experience_opportunities import (
    AdaptationAxis,
    ExperienceOpportunity,
    NodeExperienceOpportunities,
    OpportunityReadiness,
)

FIXTURE = Path(__file__).parent / "fixtures" / "didact-selection-v1.json"


def _opportunity(type_id: str, suffix: int) -> ExperienceOpportunity:
    return ExperienceOpportunity(
        opportunity_id=f"node:{suffix}",
        component_type_id=type_id,
        pedagogical_role="practice safely",
        grounding_atom_refs=("atom:1",),
        rationale_codes=("mission-fit",),
        adaptation_axes=(AdaptationAxis.SUPPORT,),
        readiness=OpportunityReadiness.NEEDS_AUTHORING,
    )


def _artifact(count: int = 3) -> NodeExperienceOpportunities:
    catalog = load_didact_catalog()
    return NodeExperienceOpportunities(
        node_id="node",
        schema_version=1,
        knowledge_pack_hash="1" * 64,
        catalog_content_hash=catalog.content_sha256,
        catalog_type_ids=tuple(item.type_id for item in catalog.components),
        opportunities=tuple(
            _opportunity(item.type_id, index)
            for index, item in enumerate(catalog.components[:count])
        ),
        strategy="test",
    )


def test_contract_preserves_complete_catalog_but_only_three_to_eight_options() -> None:
    artifact = _artifact()
    assert len(artifact.catalog_type_ids) == 34
    assert len(artifact.opportunities) == 3
    assert artifact.expandable is True

    with pytest.raises(ValidationError):
        _artifact(2)


def test_opportunities_must_be_grounded_and_reference_the_catalog() -> None:
    with pytest.raises(ValidationError):
        ExperienceOpportunity(
            opportunity_id="x",
            component_type_id="didact.unknown",
            pedagogical_role="practice",
            grounding_atom_refs=(),
            rationale_codes=("fit",),
            adaptation_axes=(AdaptationAxis.SUPPORT,),
            readiness=OpportunityReadiness.NEEDS_AUTHORING,
        )

    payload = _artifact().model_dump()
    payload["opportunities"][0]["component_type_id"] = "didact.unknown"
    with pytest.raises(ValidationError, match="outside the catalog"):
        NodeExperienceOpportunities.model_validate(payload)


def test_canonical_hash_is_independent_of_catalog_declaration_order() -> None:
    artifact = _artifact()
    payload = artifact.model_dump()
    payload["catalog_type_ids"] = tuple(reversed(payload["catalog_type_ids"]))
    assert NodeExperienceOpportunities.model_validate(payload).canonical_hash == artifact.canonical_hash


def test_bench_considers_all_34_and_measures_deferred_personalization() -> None:
    report = run_experiment(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert report["catalog_size"] == 34
    assert report["strategies"] == ["relevance-k5", "balanced-k5", "exploratory-k8"]
    assert len(report["results"]) == 30
    assert all(row["considered_catalog_size"] == 34 for row in report["results"])
    assert all(row["grounding_rate"] == 1 for row in report["results"])
    assert all(3 <= len(row["selected"]) <= 8 for row in report["results"])
    assert any(row["later_personalization_delta"] > 0 for row in report["results"])


def test_balancing_improves_variety_and_k8_preserves_more_adaptation_room() -> None:
    report = run_experiment(json.loads(FIXTURE.read_text(encoding="utf-8")))
    summaries = report["summaries"]
    assert summaries["balanced-k5"]["mean_semantic_diversity"] > summaries["relevance-k5"]["mean_semantic_diversity"]
    assert summaries["exploratory-k8"]["mean_later_personalization_delta"] > summaries["balanced-k5"]["mean_later_personalization_delta"]
    assert summaries["exploratory-k8"]["mean_estimated_context_tokens"] < 2500
