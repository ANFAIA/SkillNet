"""Request/response schemas for stateless AI endpoints (/ai/)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SchemaProposalRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    intent_density: int = Field(default=3, ge=1, le=5)


class ProposedNode(BaseModel):
    title: str
    summary: str
    outcome: str | None = None
    criticality: str = "recommended"
    default_ui_format: str = "explanation"
    estimated_minutes: int = 10
    source_headings: list[str] = []
    prerequisites: list[int] = []


class SchemaProposalResponse(BaseModel):
    nodes: list[ProposedNode]
