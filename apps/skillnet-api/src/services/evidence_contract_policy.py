"""Server-owned policy for evidence contracts supported by real evaluators.

This module does not decide an experience or manufacture an answer key.  It only
certifies that a required knowledge-pack evidence shape has a scorer already wired in
SkillNet.  Domain performance without an exact adapter declines; catalog presence or a
display-only rubric never counts as an oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal, Mapping

from src.knowledge_pack.contracts import (
    MustPreserveKind,
    NodeKnowledgePack,
    PackStatus,
)
from src.personalization.plan import CognitiveMission
from src.services.activity_authoring_validators import EVALUATED_COMPONENT_MODES
from src.services.activity_definitions import (
    BUILTIN_EVALUATION_MODES,
    BUILTIN_EVALUATION_VERSION,
)

EVIDENCE_CONTRACT_POLICY_VERSION = "evidence-contract-policy/2"

#: Components whose evidence is scored by a built-in deterministic oracle AND whose input can
#: be authored purely from grounded FACT atoms (text/selection recall, no numbers, coordinates
#: or diagrams). This is the family a RECOGNIZE mission may certify: the learner recognizes,
#: matches, classifies or completes grounded facts, and the server scores it locally with no
#: LLM judge. Widened on 2026-08-17 from the single true/false component so the rich
#: interactive Didact activities actually reach lessons.
#:
#: EXTENSION POINT: to make a new component certifiable it must (1) appear in the Didact
#: registry with ``renderer_mode`` ``activity_definition`` (or ``direct``), (2) declare a
#: built-in evaluation mode in ``EVALUATED_COMPONENT_MODES``, and (3) be listed here if it can
#: be grounded in plain facts. The import-time guard below rejects any id that is not actually
#: scorable, so this tuple can never drift from the runtime's real capabilities.
_FACT_RECOGNITION_COMPONENTS: tuple[str, ...] = (
    "didact.quiz.true-false",
    "didact.quiz.single-choice",
    "didact.quiz.multi-select",
    "didact.quiz.fill-in-the-blank",
    "didact.matching",
    "didact.categorize",
    "didact.word-bank",
    "didact.sort",
)

#: Guard: every certifiable component must be backed by a real deterministic scorer. If this
#: fails, the tuple above lists a component the runtime cannot actually grade — a fallback bug
#: waiting to happen — so we refuse to import rather than certify something we cannot score.
_UNSCORABLE = tuple(
    component_id
    for component_id in _FACT_RECOGNITION_COMPONENTS
    if EVALUATED_COMPONENT_MODES.get(component_id) not in BUILTIN_EVALUATION_MODES
)
if _UNSCORABLE:  # pragma: no cover - configuration guard
    raise RuntimeError(
        "evidence_contract_policy lists components with no built-in scorer: "
        + ", ".join(_UNSCORABLE)
    )

#: The representative oracle recorded on the contract. The chosen component's own mode
#: (from ``EVALUATED_COMPONENT_MODES``) drives the actual scoring at materialization time.
_RECOGNITION_COMPONENT = "didact.quiz.true-false"
_RECOGNITION_MODE = EVALUATED_COMPONENT_MODES[_RECOGNITION_COMPONENT]


class EvidencePolicyDeclineReason(StrEnum):
    PACK_NOT_READY = "pack_not_ready"
    NO_REQUIRED_EVIDENCE = "no_required_evidence"
    CRITICAL_ORACLE_UNAVAILABLE = "critical_oracle_unavailable"
    EXECUTION_ORACLE_UNAVAILABLE = "execution_oracle_unavailable"
    RUBRIC_ORACLE_UNAVAILABLE = "rubric_oracle_unavailable"
    REQUIRED_EVIDENCE_UNSUPPORTED = "required_evidence_unsupported"


@dataclass(frozen=True, slots=True)
class EvidencePolicyDeclined:
    policy_version: str
    reason: EvidencePolicyDeclineReason
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidencePolicyAccepted:
    policy_version: str
    evidence_contracts: Mapping[str, Mapping[str, Any]]


EvidencePolicyResult = EvidencePolicyAccepted | EvidencePolicyDeclined


def _criticality(value: object) -> Literal["critical", "recommended", "contextual"]:
    normalized = str(getattr(value, "value", value)).strip().casefold()
    if normalized in {"critical", "recommended", "contextual"}:
        return normalized  # type: ignore[return-value]
    return "recommended"


def _decline(
    reason: EvidencePolicyDeclineReason, evidence_ids: tuple[str, ...]
) -> EvidencePolicyDeclined:
    return EvidencePolicyDeclined(
        policy_version=EVIDENCE_CONTRACT_POLICY_VERSION,
        reason=reason,
        evidence_ids=evidence_ids,
    )


def _recognition_is_supported(pack: NodeKnowledgePack) -> bool:
    """Recognizing grounded facts is the sole currently safe generic mapping.

    The existing true/false Didact authoring contract validates a private exact answer,
    and ``ActivityDefinitionService`` scores that mode locally.  No LLM judge or
    external port is needed.  This does not claim the learner can perform the task.
    """

    if pack.objective.mission is not CognitiveMission.RECOGNIZE:
        return False
    atoms = {item.atom_id: item for item in pack.must_preserve}
    required = tuple(item for item in pack.evidence_specs if item.required)
    return bool(required) and all(
        spec.atom_refs
        and all(
            atom_ref in atoms and atoms[atom_ref].kind is MustPreserveKind.FACT
            for atom_ref in spec.atom_refs
        )
        for spec in required
    )


def evidence_contracts_for_pack(
    pack: NodeKnowledgePack,
    *,
    criticality: object,
) -> EvidencePolicyResult:
    """Return versioned contracts only for evaluator capabilities present today."""

    if pack.status is not PackStatus.READY:
        return _decline(EvidencePolicyDeclineReason.PACK_NOT_READY, ())
    required = tuple(item for item in pack.evidence_specs if item.required)
    evidence_ids = tuple(sorted(item.evidence_id for item in required))
    if not required:
        return _decline(EvidencePolicyDeclineReason.NO_REQUIRED_EVIDENCE, ())

    # A generic selected-response scorer cannot establish safe operational competence.
    # No exact ticket simulator/evaluator is wired into ActivityPortRegistry today.
    if _criticality(criticality) == "critical":
        return _decline(
            EvidencePolicyDeclineReason.CRITICAL_ORACLE_UNAVAILABLE, evidence_ids
        )

    requirements = set(pack.objective.available_requirements)
    if "execution" in requirements:
        # didact.code-exercise is blocked and the default registry has no execution port.
        return _decline(
            EvidencePolicyDeclineReason.EXECUTION_ORACLE_UNAVAILABLE, evidence_ids
        )

    if _recognition_is_supported(pack):
        contracts = {
            spec.evidence_id: MappingProxyType(
                {
                    "version": 1,
                    "evidence_type": "grounded_fact_recognition",
                    "oracle_ref": (
                        f"{BUILTIN_EVALUATION_VERSION}:"
                        f"{_RECOGNITION_COMPONENT}:{_RECOGNITION_MODE}"
                    ),
                    "adapter_version": BUILTIN_EVALUATION_VERSION,
                    "evaluation_mode": _RECOGNITION_MODE,
                    "supported_component_ids": _FACT_RECOGNITION_COMPONENTS,
                    "source_atom_refs": tuple(sorted(spec.atom_refs)),
                    "policy_version": EVIDENCE_CONTRACT_POLICY_VERSION,
                }
            )
            for spec in required
        }
        return EvidencePolicyAccepted(
            policy_version=EVIDENCE_CONTRACT_POLICY_VERSION,
            evidence_contracts=MappingProxyType(contracts),
        )

    if pack.objective.mission in {CognitiveMission.DECIDE, CognitiveMission.EXPLAIN}:
        # Didact's rubric shell is mounted, but no built-in rubric scoring mode exists;
        # legacy LLM grading is not an ActivityDefinition EvaluationPort.
        return _decline(
            EvidencePolicyDeclineReason.RUBRIC_ORACLE_UNAVAILABLE, evidence_ids
        )
    return _decline(
        EvidencePolicyDeclineReason.REQUIRED_EVIDENCE_UNSUPPORTED, evidence_ids
    )


__all__ = [
    "EVIDENCE_CONTRACT_POLICY_VERSION",
    "EvidencePolicyAccepted",
    "EvidencePolicyDeclineReason",
    "EvidencePolicyDeclined",
    "EvidencePolicyResult",
    "evidence_contracts_for_pack",
]
