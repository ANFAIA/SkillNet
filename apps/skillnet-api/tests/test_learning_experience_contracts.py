"""Unit-level contract tests for the additive neutral experience model."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import UniqueConstraint

from src.models.learning_experience import (
    ExperienceAttempt,
    ExperienceIntent,
    ExperienceVariant,
    ImplementationBinding,
    NormalizedEvidence,
)
from src.schemas.learning_experience import (
    ExperienceAttemptCreate,
    ExperienceIntentCreate,
    ExperienceVariantCreate,
    ImplementationBindingCreate,
    NormalizedEvidenceCreate,
)

ZERO_DIGEST = "0" * 64


def intent(**overrides) -> ExperienceIntentCreate:
    values = {
        "course_id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "intent_key": "node-4/practice",
        "objective_id": "avoid-cross-contamination",
        "objective_version": 3,
        "intent": "guided_practice",
        "learner_actions": ["sequence"],
        "representations": ["procedural"],
        "required_evidence": ["correct_sequence"],
        "feedback_policy": "immediate",
        "contract_digest": ZERO_DIGEST,
    }
    values.update(overrides)
    return ExperienceIntentCreate(**values)


def binding(**overrides) -> ImplementationBindingCreate:
    values = {
        "variant_id": uuid.uuid4(),
        "binding_key": "node-4/practice/didact-sort",
        "provider": "Didact",
        "implementation_id": "Didact.Sort",
        "implementation_version": 1,
        "definition_ref": "definition-44@1",
        "definition_digest": ZERO_DIGEST,
        "catalog_version": "didact/1",
        "evidence_adapter_version": "didact.sort.evidence/1",
        "renderer_version": "didact-react/1",
        "required_ports": ["evaluation"],
    }
    values.update(overrides)
    return ImplementationBindingCreate(**values)


def test_intent_is_provider_neutral_and_frozen() -> None:
    contract = intent()
    assert contract.intent == "guided_practice"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        intent(provider="didact")
    with pytest.raises(ValidationError, match="frozen"):
        contract.intent = "assessment"


def test_lists_reject_duplicates_and_empty_values() -> None:
    with pytest.raises(ValidationError, match="unique"):
        intent(learner_actions=["sequence", "sequence"])
    with pytest.raises(ValidationError, match="non-empty"):
        intent(required_evidence=[" "])


def test_variant_is_provider_free_and_digest_is_versioned() -> None:
    variant = ExperienceVariantCreate(
        intent_id=uuid.uuid4(),
        variant_key="concise-steps",
        representations=["textual", "procedural"],
        learner_actions=["observe"],
        best_for=["review", "low-bandwidth"],
        variant_digest=ZERO_DIGEST,
    )
    assert variant.version == 1
    with pytest.raises(ValidationError, match="String should match pattern"):
        ExperienceVariantCreate(
            intent_id=uuid.uuid4(),
            variant_key="bad-digest",
            variant_digest="not-a-digest",
        )


def test_binding_can_pin_legacy_activity_definition_without_leaking_upstream() -> None:
    activity_id = uuid.uuid4()
    contract = binding(activity_definition_id=activity_id)
    assert contract.provider == "didact"
    assert contract.implementation_id == "didact.sort"
    assert contract.activity_definition_id == activity_id


def test_neutral_graph_allows_explicit_tenant_erasure_to_cascade() -> None:
    for model, column_name in (
        (ExperienceVariant, "intent_id"),
        (ImplementationBinding, "variant_id"),
        (ExperienceAttempt, "binding_id"),
        (NormalizedEvidence, "attempt_id"),
    ):
        foreign_key = next(iter(model.__table__.columns[column_name].foreign_keys))
        assert foreign_key.ondelete == "CASCADE"


def test_normalized_evidence_rejects_client_like_invalid_scoring() -> None:
    with pytest.raises(ValidationError, match="unscored evidence cannot carry a score"):
        NormalizedEvidenceCreate(
            evidence_key="safe-decision",
            objective_id="avoid-cross-contamination",
            objective_version=3,
            evidence_type="safe_decision",
            outcome="unscored",
            score=0.8,
            implementation_ref="didact.single-choice@1",
            evidence_digest=ZERO_DIGEST,
        )


def test_attempt_uses_the_wire_attempt_id_as_global_idempotency_key() -> None:
    attempt_id = uuid.uuid4()
    command = ExperienceAttemptCreate(
        attempt_id=attempt_id,
        course_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        intent_id=uuid.uuid4(),
        variant_id=uuid.uuid4(),
        binding_id=uuid.uuid4(),
        request_digest=ZERO_DIGEST,
        outcome="correct",
        score=1.0,
        passed=True,
    )
    assert command.attempt_id == attempt_id
    assert command.evidence == []


@pytest.mark.parametrize(
    "model",
    [ExperienceIntent, ExperienceVariant, ImplementationBinding, ExperienceAttempt, NormalizedEvidence],
)
def test_neutral_records_are_append_only_in_the_orm_shape(model: type) -> None:
    assert "created_at" in model.__table__.columns
    assert "updated_at" not in model.__table__.columns


@pytest.mark.parametrize(
    ("model", "constraint_name"),
    [
        (ExperienceIntent, "uq_experience_intent_version"),
        (ExperienceVariant, "uq_experience_variant_version"),
        (ImplementationBinding, "uq_implementation_binding_version"),
    ],
)
def test_versioned_records_have_a_natural_version_uniqueness(model: type, constraint_name: str) -> None:
    constraints = {
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert constraint_name in constraints
