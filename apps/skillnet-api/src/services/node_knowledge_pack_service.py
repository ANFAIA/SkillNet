"""Application service for immutable ``NodeKnowledgePackRecord`` snapshots.

There is deliberately no LLM call, runtime prompt or OpenUI dependency here. A future
background generator can claim a source snapshot, hand its completed Markdown/atoms here,
and safely lose the result if the source changed in the meantime.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from src.models import NodeKnowledgePackRecord, NodeKnowledgePackStatus


def _canonical_json_hash(value: object) -> str:
    """Hash JSON independently of dict insertion order for reproducible audit records."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def markdown_hash(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def atoms_hash(atoms: list) -> str:
    return _canonical_json_hash(atoms)


@dataclass(frozen=True)
class KnowledgePackSnapshot:
    org_id: uuid.UUID
    course_id: uuid.UUID
    node_id: uuid.UUID
    source_fingerprint: str
    schema_version: int
    generator_version: str


@dataclass(frozen=True)
class CompletedKnowledgePack:
    markdown: str
    pack_payload: dict[str, Any]
    pack_hash: str
    atoms: list[dict[str, Any]]
    provenance: dict[str, Any]
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None


class KnowledgePackStore(Protocol):
    async def claim_snapshot(self, **kwargs: Any) -> NodeKnowledgePackRecord: ...

    async def mark_completed_if_claimed(
        self, record_id: uuid.UUID, **kwargs: Any
    ) -> NodeKnowledgePackRecord | None: ...

    async def mark_failed_if_claimed(
        self, record_id: uuid.UUID, **kwargs: Any
    ) -> NodeKnowledgePackRecord | None: ...


class NodeKnowledgePackService:
    """Own pack payload validation and the snapshot-safe terminal-write contract."""

    def __init__(self, store: KnowledgePackStore) -> None:
        self.store = store

    async def claim(self, snapshot: KnowledgePackSnapshot) -> NodeKnowledgePackRecord:
        if not snapshot.source_fingerprint:
            raise ValueError("source_fingerprint is required")
        if not snapshot.generator_version:
            raise ValueError("generator_version is required")
        if snapshot.schema_version < 1:
            raise ValueError("schema_version must be positive")
        return await self.store.claim_snapshot(**snapshot.__dict__)

    async def complete(
        self,
        record: NodeKnowledgePackRecord,
        *,
        snapshot: KnowledgePackSnapshot,
        pack: CompletedKnowledgePack,
    ) -> NodeKnowledgePackRecord | None:
        _validate_completed_pack(pack)
        raw_status = str(pack.pack_payload.get("status") or "")
        try:
            terminal_status = NodeKnowledgePackStatus(raw_status)
        except ValueError as exc:
            raise ValueError("knowledge-pack payload has no valid terminal status") from exc
        if terminal_status not in (
            NodeKnowledgePackStatus.READY,
            NodeKnowledgePackStatus.REVIEW_REQUIRED,
        ):
            raise ValueError("knowledge-pack payload is not terminal")
        return await self.store.mark_completed_if_claimed(
            record.id,
            source_fingerprint=snapshot.source_fingerprint,
            generator_version=snapshot.generator_version,
            markdown=pack.markdown,
            pack_payload=pack.pack_payload,
            pack_hash=pack.pack_hash,
            atoms=pack.atoms,
            provenance=pack.provenance,
            markdown_hash=markdown_hash(pack.markdown),
            atoms_hash=atoms_hash(pack.atoms),
            input_tokens=pack.input_tokens,
            output_tokens=pack.output_tokens,
            duration_ms=pack.duration_ms,
            status=terminal_status,
        )

    async def fail(
        self,
        record: NodeKnowledgePackRecord,
        *,
        snapshot: KnowledgePackSnapshot,
        error_message: str,
    ) -> NodeKnowledgePackRecord | None:
        return await self.store.mark_failed_if_claimed(
            record.id,
            source_fingerprint=snapshot.source_fingerprint,
            generator_version=snapshot.generator_version,
            error_message=error_message,
        )


def _validate_completed_pack(pack: CompletedKnowledgePack) -> None:
    if not pack.markdown.strip():
        raise ValueError("knowledge-pack markdown cannot be empty")
    if not isinstance(pack.pack_payload, dict) or not pack.pack_payload:
        raise ValueError("knowledge-pack payload must be a non-empty object")
    if len(pack.pack_hash) != 64 or any(c not in "0123456789abcdef" for c in pack.pack_hash):
        raise ValueError("knowledge-pack hash must be a lowercase SHA-256 digest")
    if not isinstance(pack.atoms, list):
        raise ValueError("knowledge-pack atoms must be a list")
    if not isinstance(pack.provenance, dict):
        raise ValueError("knowledge-pack provenance must be an object")
    for field_name in ("input_tokens", "output_tokens", "duration_ms"):
        value = getattr(pack, field_name)
        if value is not None and value < 0:
            raise ValueError(f"{field_name} cannot be negative")


__all__ = [
    "CompletedKnowledgePack",
    "KnowledgePackSnapshot",
    "NodeKnowledgePackService",
    "atoms_hash",
    "markdown_hash",
]
