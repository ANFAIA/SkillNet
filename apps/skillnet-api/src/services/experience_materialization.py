"""Materialize approved design-time baselines and their immutable bindings."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    ActivityDefinition,
    ActivityFamily,
    CourseNode,
    ImplementationBinding,
)
from src.personalization.didact_catalog import load_didact_catalog
from src.services.activity_authoring_validators import (
    validate_component_definition,
    validate_evaluation_definition,
)
from src.services.experience_planning import NodeExperiencePlan, PLANNER_VERSION
from src.services.probe_service import validate_probe_items

MATERIALIZER_VERSION = "neutral-experience-materializer/1"
TEXT_IMPLEMENTATION = "skillnet.text-content"
WORKED_EXAMPLE_IMPLEMENTATION = "didact.worked-example"
QUIZ_IMPLEMENTATION = "didact.quiz.single-choice"
_MATERIALIZATION_NAMESPACE = uuid.UUID("1111d6b8-2579-4f35-99d1-5480ac594401")


@dataclass(frozen=True, slots=True)
class MaterializationDecline:
    intent_key: str
    reason: str


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    materializer_version: str
    materialization_digest: str
    planned_definitions: int
    inserted_definitions: int
    planned_bindings: int
    inserted_bindings: int
    declined: tuple[MaterializationDecline, ...]


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_id(kind: str, natural_key: str, version: int) -> uuid.UUID:
    return uuid.uuid5(
        _MATERIALIZATION_NAMESPACE, f"{kind}:{natural_key}@{version}"
    )


def _rowcount(result: object) -> int:
    value = getattr(result, "rowcount", 0)
    return max(0, int(value)) if isinstance(value, int) else 0


def _probe_item(node: CourseNode) -> tuple[dict, dict] | None:
    """Return the apply-level selected-response probe, never a constructed answer."""

    try:
        validate_probe_items(
            list(node.probe_items or []),
            dict(node.probe_answer_key or {}),
            node.criticality,
        )
    except Exception:  # validation error is recorded as a decline by the caller
        return None
    item = next(
        (
            candidate
            for candidate in (node.probe_items or [])
            if candidate.get("item_id") == "a"
            and candidate.get("item_type") == "test"
        ),
        None,
    )
    key = (node.probe_answer_key or {}).get("a")
    if not isinstance(item, dict) or not isinstance(key, dict):
        return None
    options = item.get("options")
    correct = key.get("correct")
    if (
        not isinstance(options, list)
        or len(options) < 2
        or not all(isinstance(option, str) and option.strip() for option in options)
        or not isinstance(correct, int)
        or isinstance(correct, bool)
        or not 0 <= correct < len(options)
    ):
        return None
    return item, key


def _text_definition(node: CourseNode) -> tuple[dict, dict]:
    """Reviewed schema text is the honest fallback when no rich representation exists."""

    public = {
        "content": str(node.summary).strip(),
        "variant": "lead",
    }
    return public, {}


def _worked_example_definition(node: CourseNode) -> tuple[dict, dict] | None:
    """Use Didact only when the reviewed outcome actually describes an application."""

    outcome = str(node.outcome or "").strip()
    normalized = outcome.lower()
    procedural_terms = (
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
    if not outcome or not any(term in normalized for term in procedural_terms):
        return None
    return (
        {
            "problem": outcome,
            "steps": [
                {
                    "id": "reviewed-summary",
                    "title": str(node.title).strip(),
                    "explanation": str(node.summary).strip(),
                }
            ],
            "summary": str(node.summary).strip(),
            "mode": "progressive",
        },
        {},
    )


def _quiz_definition(item: Mapping[str, Any], key: Mapping[str, Any]) -> tuple[dict, dict]:
    options = [str(option).strip() for option in item["options"]]
    correct = int(key["correct"])
    public = {
        "question": str(item.get("question") or "").strip(),
        "options": [
            {"value": f"option-{index}", "label": label}
            for index, label in enumerate(options)
        ],
    }
    private = {
        "evaluation": {"mode": "exact", "expected": f"option-{correct}"}
    }
    validate_component_definition(QUIZ_IMPLEMENTATION, public)
    validate_evaluation_definition(QUIZ_IMPLEMENTATION, public, private)
    return public, private


class ExperienceMaterializer:
    """Create baselines only from reviewed text or a validated server-owned probe."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def materialize_course(
        self,
        *,
        org_id: uuid.UUID,
        course_id: uuid.UUID,
        schema_version: int,
        nodes: Sequence[CourseNode],
        plans: Sequence[NodeExperiencePlan],
    ) -> MaterializationResult:
        node_by_id = {node.id: node for node in nodes}
        catalog = load_didact_catalog()
        catalog_version = f"didact:{catalog.content_sha256}"
        declined: list[MaterializationDecline] = []
        definitions: list[dict[str, Any]] = []
        bindings: list[dict[str, Any]] = []

        for plan in plans:
            node = node_by_id[plan.node_id]
            variant_by_intent = {variant.intent_id: variant for variant in plan.variants}
            probe = _probe_item(node)
            for intent in plan.intents:
                variant = variant_by_intent[intent.id]
                if intent.intent == "explain":
                    worked_example = _worked_example_definition(node)
                    worked_example_available = (
                        catalog.by_type_id.get(WORKED_EXAMPLE_IMPLEMENTATION) is not None
                        and catalog.by_type_id[WORKED_EXAMPLE_IMPLEMENTATION].llm_emittable
                    )
                    if worked_example is not None and worked_example_available:
                        implementation_id = WORKED_EXAMPLE_IMPLEMENTATION
                        provider = "didact"
                        public, private = worked_example
                        catalog_ref = catalog_version
                        renderer_version = "didact-react/1"
                    else:
                        implementation_id = TEXT_IMPLEMENTATION
                        provider = "skillnet"
                        public, private = _text_definition(node)
                        catalog_ref = "skillnet-core/1"
                        renderer_version = "text-content/1"
                    family = ActivityFamily.ARTIFACT
                    required_ports: list[str] = []
                    evidence_adapter_version = None
                elif intent.intent in {"guided_practice", "knowledge_check"}:
                    if probe is None:
                        declined.append(
                            MaterializationDecline(intent.intent_key, "probe_not_compatible")
                        )
                        continue
                    implementation_id = QUIZ_IMPLEMENTATION
                    provider = "didact"
                    family = ActivityFamily.ASSESSMENT
                    try:
                        public, private = _quiz_definition(*probe)
                    except (TypeError, ValueError):
                        declined.append(
                            MaterializationDecline(
                                intent.intent_key, "probe_definition_incompatible"
                            )
                        )
                        continue
                    required_ports = ["evaluation"]
                    evidence_adapter_version = "didact.single-choice.evidence/1"
                    catalog_ref = catalog_version
                    renderer_version = "didact-react/1"
                else:
                    declined.append(
                        MaterializationDecline(
                            intent.intent_key, f"no_approved_producer:{intent.intent}"
                        )
                    )
                    continue

                definition_key = f"experience:{intent.intent_key}"
                definition_id = _stable_id("definition", definition_key, schema_version)
                definition_payload = {
                    "public": public,
                    "private": private,
                    "implementation_id": implementation_id,
                    "schema_version": schema_version,
                }
                definition_digest = _digest(definition_payload)
                definitions.append(
                    {
                        "id": definition_id,
                        "org_id": org_id,
                        "course_id": course_id,
                        "node_id": node.id,
                        "definition_key": definition_key,
                        "component_id": implementation_id,
                        "family": family,
                        "version": schema_version,
                        "public_definition": public,
                        "private_definition": private,
                        "required_ports": required_ports,
                        "provenance": {
                            "planner_version": PLANNER_VERSION,
                            "materializer_version": MATERIALIZER_VERSION,
                            "schema_version": schema_version,
                            "source": "reviewed_node_summary"
                            if intent.intent == "explain"
                            else "validated_probe:a",
                            "definition_digest": definition_digest,
                        },
                        "enabled": True,
                    }
                )
                binding_key = f"{variant.variant_key}:{implementation_id}"
                bindings.append(
                    {
                        "id": _stable_id("binding", binding_key, schema_version),
                        "org_id": org_id,
                        "variant_id": variant.id,
                        "binding_key": binding_key,
                        "version": schema_version,
                        "provider": provider,
                        "implementation_id": implementation_id,
                        "implementation_version": 1,
                        "definition_ref": str(definition_id),
                        "activity_definition_id": definition_id,
                        "definition_digest": definition_digest,
                        "assets_digest": None,
                        "catalog_version": catalog_ref,
                        "evidence_adapter_version": evidence_adapter_version,
                        "renderer_version": renderer_version,
                        "required_ports": required_ports,
                        "is_fallback": True,
                    }
                )

        inserted_definitions = 0
        for values in definitions:
            statement = (
                insert(ActivityDefinition)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_activity_definition_version")
            )
            inserted_definitions += _rowcount(await self.session.execute(statement))

        inserted_bindings = 0
        for values in bindings:
            statement = (
                insert(ImplementationBinding)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_implementation_binding_version")
            )
            inserted_bindings += _rowcount(await self.session.execute(statement))

        materialization_digest = _digest(
            {
                "materializer_version": MATERIALIZER_VERSION,
                "schema_version": schema_version,
                "definitions": definitions,
                "bindings": bindings,
                "declined": declined,
            }
        )
        return MaterializationResult(
            materializer_version=MATERIALIZER_VERSION,
            materialization_digest=materialization_digest,
            planned_definitions=len(definitions),
            inserted_definitions=inserted_definitions,
            planned_bindings=len(bindings),
            inserted_bindings=inserted_bindings,
            declined=tuple(declined),
        )


__all__ = [
    "ExperienceMaterializer",
    "MATERIALIZER_VERSION",
    "MaterializationDecline",
    "MaterializationResult",
    "QUIZ_IMPLEMENTATION",
    "TEXT_IMPLEMENTATION",
    "WORKED_EXAMPLE_IMPLEMENTATION",
]
