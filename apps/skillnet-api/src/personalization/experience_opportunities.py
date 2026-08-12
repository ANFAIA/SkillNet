"""Pure contract for course-creation Didact opportunities.

This module is intentionally disconnected from the production graph.  It models a
durable, source-grounded *option set* prepared after a node knowledge pack exists.  It
does not choose a screen, freeze an activity configuration, or require a renderer to
be ready at course-creation time.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OPPORTUNITY_FORMAT = "didact-opportunities/1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OpportunityReadiness(StrEnum):
    READY = "ready"
    NEEDS_HOST_PORT = "needs_host_port"
    NEEDS_AUTHORING = "needs_authoring"


class AdaptationAxis(StrEnum):
    SUPPORT = "support"
    DENSITY = "density"
    PRESENTATION = "presentation"
    ERROR_RECOVERY = "error_recovery"
    CHALLENGE = "challenge"


class ExperienceOpportunity(_FrozenModel):
    """One pedagogically plausible component, without a rendered-screen decision."""

    opportunity_id: str = Field(min_length=1)
    component_type_id: str = Field(pattern=r"^didact\.[a-z0-9.-]+$")
    pedagogical_role: str = Field(min_length=1, max_length=240)
    grounding_atom_refs: tuple[str, ...] = Field(min_length=1)
    rationale_codes: tuple[str, ...] = Field(min_length=1)
    required_ports: tuple[str, ...] = ()
    adaptation_axes: tuple[AdaptationAxis, ...] = Field(min_length=1)
    readiness: OpportunityReadiness

    @field_validator(
        "grounding_atom_refs", "rationale_codes", "required_ports", "adaptation_axes"
    )
    @classmethod
    def _unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("must not contain duplicates")
        return value


class NodeExperienceOpportunities(_FrozenModel):
    """Reviewable hand-off between course creation and later personalization.

    ``catalog_type_ids`` deliberately records the complete 34-type universe that was
    considered.  ``opportunities`` is only a bounded working set; it is expandable and
    never claims that non-shortlisted types are unavailable.
    """

    format: str = OPPORTUNITY_FORMAT
    node_id: str = Field(min_length=1)
    schema_version: int = Field(ge=1)
    knowledge_pack_hash: str
    catalog_content_hash: str
    catalog_type_ids: tuple[str, ...] = Field(min_length=34, max_length=34)
    opportunities: tuple[ExperienceOpportunity, ...] = Field(min_length=3, max_length=8)
    strategy: str = Field(min_length=1)
    expandable: bool = True

    @field_validator("format")
    @classmethod
    def _format(cls, value: str) -> str:
        if value != OPPORTUNITY_FORMAT:
            raise ValueError(f"format must be {OPPORTUNITY_FORMAT}")
        return value

    @field_validator("knowledge_pack_hash", "catalog_content_hash")
    @classmethod
    def _hash(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be a lowercase SHA-256 digest")
        return value

    @field_validator("catalog_type_ids")
    @classmethod
    def _catalog(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("catalog_type_ids must contain 34 unique types")
        return value

    @model_validator(mode="after")
    def _cross_references(self) -> Self:
        ids = [item.opportunity_id for item in self.opportunities]
        components = [item.component_type_id for item in self.opportunities]
        if len(ids) != len(set(ids)):
            raise ValueError("opportunity ids must be unique")
        if len(components) != len(set(components)):
            raise ValueError("component suggestions must be unique")
        unknown = set(components) - set(self.catalog_type_ids)
        if unknown:
            raise ValueError(f"opportunities reference types outside the catalog: {unknown}")
        return self

    def canonical_json(self) -> str:
        payload = self.model_dump(mode="json")
        payload["catalog_type_ids"] = sorted(payload["catalog_type_ids"])
        payload["opportunities"] = sorted(
            payload["opportunities"], key=lambda item: item["opportunity_id"]
        )
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


__all__ = [
    "OPPORTUNITY_FORMAT",
    "AdaptationAxis",
    "ExperienceOpportunity",
    "NodeExperienceOpportunities",
    "OpportunityReadiness",
]
