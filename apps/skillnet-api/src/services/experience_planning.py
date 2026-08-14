"""Deterministic design-time planning for provider-neutral learning experiences.

This module prepares immutable intents and baseline variants when a course schema is
validated.  It deliberately stops before provider selection: producers may later add
bindings only after an implementation definition has passed its own approval gate.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import CourseNode, ExperienceIntent, ExperienceVariant, NodeCriticality, UiFormat

PLANNER_VERSION = "neutral-experience-plan/1"
_PLAN_NAMESPACE = uuid.UUID("4d4de2f7-9ad4-4d49-a6ab-86a3f5aeb83f")


@dataclass(frozen=True, slots=True)
class IntentDraft:
    id: uuid.UUID
    intent_key: str
    objective_id: str
    intent: str
    learner_actions: tuple[str, ...]
    representations: tuple[str, ...]
    required_evidence: tuple[str, ...]
    feedback_policy: str
    constraints: dict[str, Any]
    provenance: dict[str, Any]
    contract_digest: str


@dataclass(frozen=True, slots=True)
class VariantDraft:
    id: uuid.UUID
    intent_id: uuid.UUID
    variant_key: str
    representations: tuple[str, ...]
    learner_actions: tuple[str, ...]
    best_for: tuple[str, ...]
    required_capabilities: dict[str, Any]
    selection_policy: dict[str, Any]
    variant_digest: str


@dataclass(frozen=True, slots=True)
class NodeExperiencePlan:
    node_id: uuid.UUID
    rhythm: str
    intents: tuple[IntentDraft, ...]
    variants: tuple[VariantDraft, ...]


@dataclass(frozen=True, slots=True)
class NeutralPlanResult:
    planner_version: str
    plan_digest: str
    planned_intents: int
    planned_variants: int
    inserted_intents: int
    inserted_variants: int
    plans: tuple[NodeExperiencePlan, ...]


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_id(kind: str, natural_key: str, version: int) -> uuid.UUID:
    return uuid.uuid5(_PLAN_NAMESPACE, f"{kind}:{natural_key}@{version}")


def _representations(ui_format: object) -> tuple[str, ...]:
    return {
        UiFormat.EXPLANATION.value: ("textual", "conceptual"),
        UiFormat.EXERCISE.value: ("interactive", "procedural"),
        UiFormat.CHART.value: ("visual", "data"),
        UiFormat.MIXED.value: ("textual", "interactive"),
        UiFormat.SIMULATION.value: ("interactive", "procedural"),
    }.get(_value(ui_format), ("textual", "conceptual"))


def _application_intent(outcome: str | None) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    normalized = (outcome or "").lower()
    procedural = (
        "aplicar",
        "ejecutar",
        "realizar",
        "preparar",
        "gestionar",
        "demostrar",
        "apply",
        "perform",
        "prepare",
        "manage",
    )
    if any(term in normalized for term in procedural):
        return "guided_practice", ("apply",), ("successful_application",)
    return "knowledge_check", ("decide",), ("correct_decision",)


def build_node_experience_plan(node: CourseNode, *, schema_version: int) -> NodeExperiencePlan:
    """Build a brief-first but non-rigid sequence for one reviewed node."""

    criticality = _value(node.criticality)
    base_representations = _representations(node.default_ui_format)
    application_intent, application_actions, application_evidence = _application_intent(node.outcome)

    if criticality == NodeCriticality.CRITICAL.value:
        rhythm = "brief_explain_practice_transfer"
        steps = (
            ("explain", "explain", ("observe",), (), False),
            ("practice", application_intent, application_actions, application_evidence, False),
            ("transfer", "transfer", ("decide",), ("safe_transfer",), False),
        )
    elif criticality == NodeCriticality.CONTEXTUAL.value:
        rhythm = "summary_then_check"
        steps = (
            ("explain", "explain", ("observe",), (), True),
            ("check", "knowledge_check", ("decide",), ("correct_decision",), False),
        )
    else:
        rhythm = "brief_explain_then_apply"
        steps = (
            ("explain", "explain", ("observe",), (), True),
            ("apply", application_intent, application_actions, application_evidence, False),
        )

    intents: list[IntentDraft] = []
    variants: list[VariantDraft] = []
    for position, (step_key, intent, actions, evidence, skippable) in enumerate(steps, start=1):
        intent_key = f"{node.id}:{step_key}"
        intent_id = _stable_id("intent", intent_key, schema_version)
        representations = (
            ("textual", "conceptual") if intent == "explain" else base_representations
        )
        constraints = {
            "position": position,
            "brief": intent == "explain",
            "max_words": 90 if intent == "explain" else None,
            "required_before_attempt": intent == "explain" and not skippable,
            "skippable_when": "prior_mastery_or_experience" if skippable else None,
            "recovery_branch": intent != "explain",
        }
        provenance = {
            "planner_version": PLANNER_VERSION,
            "schema_version": schema_version,
            "node_id": str(node.id),
            "rhythm": rhythm,
        }
        contract_payload = {
            "intent_key": intent_key,
            "objective_id": str(node.id),
            "objective_version": schema_version,
            "intent": intent,
            "learner_actions": actions,
            "representations": representations,
            "required_evidence": evidence,
            "feedback_policy": "progressive" if intent == "explain" else "immediate",
            "constraints": constraints,
            "provenance": provenance,
        }
        contract_digest = _digest(contract_payload)
        draft = IntentDraft(
            id=intent_id,
            intent_key=intent_key,
            objective_id=str(node.id),
            intent=intent,
            learner_actions=actions,
            representations=representations,
            required_evidence=evidence,
            feedback_policy=contract_payload["feedback_policy"],
            constraints=constraints,
            provenance=provenance,
            contract_digest=contract_digest,
        )
        intents.append(draft)

        variant_key = f"{intent_key}:baseline"
        variant_payload = {
            "intent_digest": contract_digest,
            "variant_key": variant_key,
            "representations": representations,
            "learner_actions": actions,
            "best_for": ("default", "offline-safe"),
            "required_capabilities": {
                "intent": intent,
                "evidence": list(evidence),
                "feedback": draft.feedback_policy,
            },
            "selection_policy": {
                "kind": "baseline",
                "priority": 100,
                "fallback": True,
            },
        }
        variants.append(
            VariantDraft(
                id=_stable_id("variant", variant_key, schema_version),
                intent_id=intent_id,
                variant_key=variant_key,
                representations=representations,
                learner_actions=actions,
                best_for=("default", "offline-safe"),
                required_capabilities=variant_payload["required_capabilities"],
                selection_policy=variant_payload["selection_policy"],
                variant_digest=_digest(variant_payload),
            )
        )

    return NodeExperiencePlan(
        node_id=node.id,
        rhythm=rhythm,
        intents=tuple(intents),
        variants=tuple(variants),
    )


class NeutralExperiencePlanner:
    """Persist deterministic plan rows without authoring provider bindings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def plan_course(
        self,
        *,
        org_id: uuid.UUID,
        course_id: uuid.UUID,
        schema_version: int,
        nodes: Sequence[CourseNode],
    ) -> NeutralPlanResult:
        plans = [
            build_node_experience_plan(node, schema_version=schema_version)
            for node in sorted(nodes, key=lambda item: (item.position, str(item.id)))
        ]
        intents = [draft for plan in plans for draft in plan.intents]
        variants = [draft for plan in plans for draft in plan.variants]

        inserted_intents = 0
        for draft in intents:
            statement = (
                insert(ExperienceIntent)
                .values(
                    id=draft.id,
                    org_id=org_id,
                    course_id=course_id,
                    node_id=uuid.UUID(draft.objective_id),
                    intent_key=draft.intent_key,
                    version=schema_version,
                    objective_id=draft.objective_id,
                    objective_version=schema_version,
                    intent=draft.intent,
                    learner_actions=list(draft.learner_actions),
                    representations=list(draft.representations),
                    required_evidence=list(draft.required_evidence),
                    feedback_policy=draft.feedback_policy,
                    constraints=draft.constraints,
                    provenance=draft.provenance,
                    contract_digest=draft.contract_digest,
                )
                .on_conflict_do_nothing(constraint="uq_experience_intent_version")
            )
            inserted_intents += _rowcount(await self.session.execute(statement))

        inserted_variants = 0
        for draft in variants:
            statement = (
                insert(ExperienceVariant)
                .values(
                    id=draft.id,
                    org_id=org_id,
                    intent_id=draft.intent_id,
                    variant_key=draft.variant_key,
                    version=schema_version,
                    representations=list(draft.representations),
                    learner_actions=list(draft.learner_actions),
                    best_for=list(draft.best_for),
                    required_capabilities=draft.required_capabilities,
                    selection_policy=draft.selection_policy,
                    variant_digest=draft.variant_digest,
                )
                .on_conflict_do_nothing(constraint="uq_experience_variant_version")
            )
            inserted_variants += _rowcount(await self.session.execute(statement))

        plan_digest = _digest(
            {
                "planner_version": PLANNER_VERSION,
                "schema_version": schema_version,
                "nodes": [
                    {
                        "node_id": str(plan.node_id),
                        "rhythm": plan.rhythm,
                        "intents": [asdict(item) for item in plan.intents],
                        "variants": [asdict(item) for item in plan.variants],
                    }
                    for plan in plans
                ],
            }
        )
        return NeutralPlanResult(
            planner_version=PLANNER_VERSION,
            plan_digest=plan_digest,
            planned_intents=len(intents),
            planned_variants=len(variants),
            inserted_intents=inserted_intents,
            inserted_variants=inserted_variants,
            plans=tuple(plans),
        )


def _rowcount(result: object) -> int:
    value = getattr(result, "rowcount", 0)
    return max(0, int(value)) if isinstance(value, int) else 0


__all__ = [
    "IntentDraft",
    "NeutralExperiencePlanner",
    "NeutralPlanResult",
    "NodeExperiencePlan",
    "PLANNER_VERSION",
    "VariantDraft",
    "build_node_experience_plan",
]
