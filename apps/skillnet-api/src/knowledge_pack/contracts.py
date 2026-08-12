"""Strict, side-effect-free contract for a prepared node knowledge pack.

This is intentionally *not* a lesson format.  It contains source-backed claims and
possibilities which a later adapter may compose into an OpenUI experience.  ``extra``
fields are rejected so that a generated pack cannot smuggle screen order, a DSL, or a
free-form ``lesson_body`` across this boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.personalization.plan import CognitiveMission, LearningObjective, Presentation

PACK_FORMAT = "node-knowledge-pack/1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class _StrictFrozenModel(BaseModel):
    """Base policy shared by every persisted pack value."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _required_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


def _identifier(value: str) -> str:
    value = _required_text(value)
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError("must be a stable identifier")
    return value


def _hash(value: str) -> str:
    value = _required_text(value).lower()
    if not _SHA256.fullmatch(value):
        raise ValueError("must be a lowercase SHA-256 digest")
    return value


class PackStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class MustPreserveKind(StrEnum):
    FACT = "fact"
    SAFETY_RULE = "safety_rule"
    PROCEDURE_STEP = "procedure_step"
    CONSTRAINT = "constraint"
    CRITERION = "criterion"


class SelectableKind(StrEnum):
    CASE = "case"
    COMMON_ERROR = "common_error"
    DECISION = "decision"
    CONTRAST = "contrast"
    WORKED_EXAMPLE = "worked_example"
    REPRESENTATION_HINT = "representation_hint"


class MissingDataArea(StrEnum):
    EVIDENCE = "evidence"
    SIMULATION = "simulation"
    MEDIA = "media"
    SAFETY = "safety"


class SourceRef(_StrictFrozenModel):
    """A compact, immutable pointer to source material; no source body is copied."""

    ref_id: str
    document_id: str
    heading_path: tuple[str, ...] = ()
    locator: str
    excerpt_hash: str
    source_revision: str
    coverage_unit_ids: tuple[str, ...] = ()

    _validate_ref_id = field_validator("ref_id")(_identifier)
    _validate_document_id = field_validator("document_id")(_identifier)
    _validate_locator = field_validator("locator")(_required_text)
    _validate_excerpt_hash = field_validator("excerpt_hash")(_hash)
    _validate_source_revision = field_validator("source_revision")(_required_text)

    @field_validator("heading_path")
    @classmethod
    def _validate_heading_path(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_required_text(item) for item in value)

    @field_validator("coverage_unit_ids")
    @classmethod
    def _validate_coverage_unit_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        refs = tuple(_identifier(item) for item in value)
        if len(set(refs)) != len(refs):
            raise ValueError("must not contain duplicate coverage units")
        return refs


class EvidenceSpec(_StrictFrozenModel):
    """Evidence that the experience must collect or preserve for this node."""

    evidence_id: str
    description: str
    atom_refs: tuple[str, ...] = ()
    required: bool = True

    _validate_evidence_id = field_validator("evidence_id")(_identifier)
    _validate_description = field_validator("description")(_required_text)

    @field_validator("atom_refs")
    @classmethod
    def _validate_atom_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        refs = tuple(_identifier(item) for item in value)
        if len(set(refs)) != len(refs):
            raise ValueError("must not contain duplicate references")
        return refs

    @model_validator(mode="after")
    def _required_evidence_needs_atoms(self) -> Self:
        if self.required and not self.atom_refs:
            raise ValueError("required evidence must reference at least one atom")
        return self


class MustPreserveAtom(_StrictFrozenModel):
    """A source-backed claim that every adaptation must retain."""

    atom_id: str
    kind: MustPreserveKind
    text: str
    sources: tuple[str, ...]
    source_units: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    critical: bool = False

    _validate_atom_id = field_validator("atom_id")(_identifier)
    _validate_text = field_validator("text")(_required_text)

    @field_validator("sources")
    @classmethod
    def _validate_sources(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        refs = tuple(_identifier(item) for item in value)
        if not refs:
            raise ValueError("must cite at least one source")
        if len(set(refs)) != len(refs):
            raise ValueError("must not contain duplicate references")
        return refs

    @field_validator("evidence", "source_units")
    @classmethod
    def _validate_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        refs = tuple(_identifier(item) for item in value)
        if len(set(refs)) != len(refs):
            raise ValueError("must not contain duplicate references")
        return refs


class SelectableAtom(_StrictFrozenModel):
    """A source-backed learning option, never a pre-composed screen block."""

    atom_id: str
    kind: SelectableKind
    text: str
    sources: tuple[str, ...]
    source_units: tuple[str, ...] = ()
    missions: tuple[CognitiveMission, ...] = ()
    presentations: tuple[Presentation, ...] = ()
    evidence: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    prereqs: tuple[str, ...] = ()

    _validate_atom_id = field_validator("atom_id")(_identifier)
    _validate_text = field_validator("text")(_required_text)

    @field_validator("sources", "source_units", "evidence", "prereqs")
    @classmethod
    def _validate_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        refs = tuple(_identifier(item) for item in value)
        if len(set(refs)) != len(refs):
            raise ValueError("must not contain duplicate references")
        return refs

    @field_validator("sources")
    @classmethod
    def _require_sources(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("must cite at least one source")
        return value

    @field_validator("missions", "presentations", "tags")
    @classmethod
    def _unique_values(cls, value: tuple[Any, ...]) -> tuple[Any, ...]:
        if len(set(value)) != len(value):
            raise ValueError("must not contain duplicates")
        return value


class GenerableSlot(_StrictFrozenModel):
    """A bounded place where the runtime may create wording or a small example."""

    slot_id: str
    purpose: str
    allowed_atom_refs: tuple[str, ...]
    forbidden_claims: tuple[str, ...] = ()
    max_items: int = Field(default=1, ge=1, le=8)

    _validate_slot_id = field_validator("slot_id")(_identifier)
    _validate_purpose = field_validator("purpose")(_required_text)

    @field_validator("allowed_atom_refs")
    @classmethod
    def _validate_allowed_atom_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        refs = tuple(_identifier(item) for item in value)
        if not refs:
            raise ValueError("must reference at least one atom")
        if len(set(refs)) != len(refs):
            raise ValueError("must not contain duplicate references")
        return refs

    @field_validator("forbidden_claims")
    @classmethod
    def _validate_forbidden_claims(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        claims = tuple(_required_text(item) for item in value)
        if len(set(claims)) != len(claims):
            raise ValueError("must not contain duplicates")
        return claims


class MissingData(_StrictFrozenModel):
    """Known absence which can force an honest decline instead of invented content."""

    data_id: str
    description: str
    affects: tuple[MissingDataArea, ...]
    blocking: bool
    fallback: str

    _validate_data_id = field_validator("data_id")(_identifier)
    _validate_description = field_validator("description")(_required_text)
    _validate_fallback = field_validator("fallback")(_required_text)

    @field_validator("affects")
    @classmethod
    def _validate_affects(cls, value: tuple[MissingDataArea, ...]) -> tuple[MissingDataArea, ...]:
        if not value:
            raise ValueError("must affect at least one area")
        if len(set(value)) != len(value):
            raise ValueError("must not contain duplicates")
        return value


class PackProvenance(_StrictFrozenModel):
    """Versioned origin data needed to audit and invalidate a pack."""

    node_id: str
    schema_version: int = Field(ge=1)
    source_bundle_hash: str
    semantic_hash: str
    generator: str
    reviewer: str | None = None

    _validate_node_id = field_validator("node_id")(_identifier)
    _validate_source_bundle_hash = field_validator("source_bundle_hash")(_hash)
    _validate_semantic_hash = field_validator("semantic_hash")(_hash)
    _validate_generator = field_validator("generator")(_required_text)

    @field_validator("reviewer")
    @classmethod
    def _validate_reviewer(cls, value: str | None) -> str | None:
        return _required_text(value) if value is not None else None


def _canonicalize(value: Any) -> Any:
    """Return JSON data with unordered contract collections sorted by stable IDs."""

    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return value


class NodeKnowledgePack(_StrictFrozenModel):
    """Prepared material for one graph node, with no screen layout or lesson prose."""

    format: str = PACK_FORMAT
    status: PackStatus = PackStatus.DRAFT
    node_id: str
    title: str
    objective: LearningObjective
    source_refs: tuple[SourceRef, ...]
    evidence_specs: tuple[EvidenceSpec, ...]
    must_preserve: tuple[MustPreserveAtom, ...]
    selectable: tuple[SelectableAtom, ...] = ()
    generable_slots: tuple[GenerableSlot, ...] = ()
    missing_data: tuple[MissingData, ...] = ()
    provenance: PackProvenance

    _validate_node_id = field_validator("node_id")(_identifier)
    _validate_title = field_validator("title")(_required_text)

    @field_validator("format")
    @classmethod
    def _validate_format(cls, value: str) -> str:
        if value != PACK_FORMAT:
            raise ValueError(f"format must be {PACK_FORMAT}")
        return value

    @model_validator(mode="after")
    def _validate_cross_references(self) -> Self:
        if self.objective.objective_id != self.node_id:
            raise ValueError("objective.objective_id must equal node_id")
        if self.provenance.node_id != self.node_id:
            raise ValueError("provenance.node_id must equal node_id")
        if self.provenance.schema_version != self.objective.objective_version:
            raise ValueError("provenance.schema_version must equal objective.objective_version")

        source_ids = [item.ref_id for item in self.source_refs]
        evidence_ids = [item.evidence_id for item in self.evidence_specs]
        preserve_ids = [item.atom_id for item in self.must_preserve]
        selectable_ids = [item.atom_id for item in self.selectable]
        slot_ids = [item.slot_id for item in self.generable_slots]
        missing_ids = [item.data_id for item in self.missing_data]
        for label, values in (
            ("source_refs", source_ids),
            ("evidence_specs", evidence_ids),
            ("atoms", preserve_ids + selectable_ids),
            ("generable_slots", slot_ids),
            ("missing_data", missing_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must have unique identifiers")

        sources = set(source_ids)
        source_units = {
            unit_id
            for source in self.source_refs
            for unit_id in source.coverage_unit_ids
        }
        evidence = set(evidence_ids)
        atoms = set(preserve_ids + selectable_ids)
        for item in (*self.must_preserve, *self.selectable):
            unknown_sources = set(item.sources) - sources
            if unknown_sources:
                raise ValueError(
                    f"atom {item.atom_id} references unknown sources: "
                    f"{sorted(unknown_sources)}"
                )
            unknown_units = set(item.source_units) - source_units
            if unknown_units:
                raise ValueError(
                    f"atom {item.atom_id} references unknown source units: "
                    f"{sorted(unknown_units)}"
                )
            unknown_evidence = set(item.evidence) - evidence
            if unknown_evidence:
                raise ValueError(f"atom {item.atom_id} references unknown evidence")
        for item in self.evidence_specs:
            unknown_atoms = set(item.atom_refs) - atoms
            if unknown_atoms:
                raise ValueError(f"evidence {item.evidence_id} references unknown atoms")
        for item in self.selectable:
            unknown_prereqs = set(item.prereqs) - atoms
            if unknown_prereqs:
                raise ValueError(f"atom {item.atom_id} references unknown prerequisites")
            if item.atom_id in item.prereqs:
                raise ValueError(f"atom {item.atom_id} cannot require itself")
        for item in self.generable_slots:
            unknown_atoms = set(item.allowed_atom_refs) - atoms
            if unknown_atoms:
                raise ValueError(f"slot {item.slot_id} references unknown atoms")

        self._assert_acyclic_prerequisites()
        return self

    def _assert_acyclic_prerequisites(self) -> None:
        prerequisites = {item.atom_id: item.prereqs for item in self.selectable}
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(atom_id: str) -> None:
            if atom_id in visited:
                return
            if atom_id in visiting:
                raise ValueError("selectable atom prerequisites must not contain a cycle")
            visiting.add(atom_id)
            for prerequisite in prerequisites.get(atom_id, ()):
                visit(prerequisite)
            visiting.remove(atom_id)
            visited.add(atom_id)

        for atom_id in prerequisites:
            visit(atom_id)

    def canonical_payload(self) -> dict[str, Any]:
        """Stable JSON-safe representation for cache keys and audit comparisons.

        Atom/source declaration order is not instructional order and is normalized by
        stable identifier.  Order inside an individual atom is retained because it can
        describe a procedure or bounded generation rule.
        """

        payload = self.model_dump(mode="json", exclude_none=True)
        for key, identifier in (
            ("source_refs", "ref_id"),
            ("evidence_specs", "evidence_id"),
            ("must_preserve", "atom_id"),
            ("selectable", "atom_id"),
            ("generable_slots", "slot_id"),
            ("missing_data", "data_id"),
        ):
            payload[key] = sorted(payload[key], key=lambda item: item[identifier])
        payload["objective"]["source_functions"] = sorted(
            payload["objective"]["source_functions"]
        )
        for atom in (*payload["must_preserve"], *payload["selectable"]):
            for key in ("sources", "evidence"):
                atom[key] = sorted(atom[key])
        for atom in payload["selectable"]:
            for key in ("missions", "presentations", "tags", "prereqs"):
                atom[key] = sorted(atom[key])
        for item in payload["evidence_specs"]:
            item["atom_refs"] = sorted(item["atom_refs"])
        for slot in payload["generable_slots"]:
            slot["allowed_atom_refs"] = sorted(slot["allowed_atom_refs"])
            slot["forbidden_claims"] = sorted(slot["forbidden_claims"])
        for item in payload["missing_data"]:
            item["affects"] = sorted(item["affects"])
        return _canonicalize(payload)

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @property
    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
