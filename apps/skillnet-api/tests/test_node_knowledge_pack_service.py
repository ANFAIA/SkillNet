"""Prepared learning dossiers stay snapshot-safe before any LLM runner exists."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.models import NodeKnowledgePackStatus
from src.services.node_knowledge_pack_service import (
    CompletedKnowledgePack,
    KnowledgePackSnapshot,
    NodeKnowledgePackService,
    atoms_hash,
    markdown_hash,
)


class FakeStore:
    def __init__(self) -> None:
        self.claimed: list[dict] = []
        self.completed: list[tuple[uuid.UUID, dict]] = []
        self.failed: list[tuple[uuid.UUID, dict]] = []
        self.accept_completion = True

    async def claim_snapshot(self, **kwargs):
        self.claimed.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), status=NodeKnowledgePackStatus.PENDING)

    async def mark_completed_if_claimed(self, record_id, **kwargs):
        self.completed.append((record_id, kwargs))
        if not self.accept_completion:
            return None
        return SimpleNamespace(id=record_id, status=kwargs["status"])

    async def mark_failed_if_claimed(self, record_id, **kwargs):
        self.failed.append((record_id, kwargs))
        return SimpleNamespace(id=record_id, status=NodeKnowledgePackStatus.FAILED)


def snapshot() -> KnowledgePackSnapshot:
    return KnowledgePackSnapshot(
        org_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        source_fingerprint="source-sha-1",
        schema_version=3,
        generator_version="knowledge-pack/v1",
    )


def completed() -> CompletedKnowledgePack:
    return CompletedKnowledgePack(
        markdown="# Alergenos\n\nMarca el alergeno en la linea del plato.",
        pack_payload={
            "format": "node-knowledge-pack/1",
            "node_id": "node-1",
            "status": "ready",
        },
        pack_hash="a" * 64,
        atoms=[{"id": "invariant.allergen", "kind": "invariant"}],
        provenance={"invariant.allergen": ["c1"]},
        input_tokens=123,
        output_tokens=45,
        duration_ms=678,
    )


async def test_claim_forwards_a_complete_snapshot_identity() -> None:
    store = FakeStore()
    service = NodeKnowledgePackService(store)
    source = snapshot()

    await service.claim(source)

    assert store.claimed == [source.__dict__]


async def test_completion_hashes_content_and_records_generation_metrics() -> None:
    store = FakeStore()
    service = NodeKnowledgePackService(store)
    source = snapshot()
    record = await service.claim(source)
    pack = completed()

    result = await service.complete(record, snapshot=source, pack=pack)

    assert result is not None
    assert result.status == NodeKnowledgePackStatus.READY
    _, values = store.completed[0]
    assert values["markdown_hash"] == markdown_hash(pack.markdown)
    assert values["atoms_hash"] == atoms_hash(pack.atoms)
    assert values["pack_payload"] == pack.pack_payload
    assert values["pack_hash"] == pack.pack_hash
    assert values["input_tokens"] == 123
    assert values["duration_ms"] == 678
    assert values["source_fingerprint"] == source.source_fingerprint
    assert values["generator_version"] == source.generator_version


async def test_review_required_pack_is_persisted_honestly_not_as_ready() -> None:
    store = FakeStore()
    service = NodeKnowledgePackService(store)
    source = snapshot()
    record = await service.claim(source)
    pack = completed()
    pack.pack_payload["status"] = "review_required"

    result = await service.complete(record, snapshot=source, pack=pack)

    assert result is not None
    assert result.status == NodeKnowledgePackStatus.REVIEW_REQUIRED
    assert store.completed[0][1]["status"] == NodeKnowledgePackStatus.REVIEW_REQUIRED


async def test_late_completion_is_honestly_discarded_when_snapshot_was_staled() -> None:
    store = FakeStore()
    store.accept_completion = False
    service = NodeKnowledgePackService(store)
    source = snapshot()
    record = await service.claim(source)

    result = await service.complete(record, snapshot=source, pack=completed())

    # A repository returns None when its conditional UPDATE found a stale/non-pending row.
    # The runner must not retry that stale content into a newer snapshot.
    assert result is None
    assert len(store.completed) == 1


@pytest.mark.parametrize(
    ("pack", "message"),
    [
        (
            CompletedKnowledgePack(
                markdown=" ",
                pack_payload={"format": "node-knowledge-pack/1"},
                pack_hash="a" * 64,
                atoms=[],
                provenance={},
            ),
            "markdown",
        ),
        (
            CompletedKnowledgePack(
                markdown="# ok",
                pack_payload={"format": "node-knowledge-pack/1"},
                pack_hash="a" * 64,
                atoms=[],
                provenance={},
                duration_ms=-1,
            ),
            "duration_ms",
        ),
    ],
)
async def test_invalid_completed_payload_never_reaches_the_store(pack, message) -> None:
    store = FakeStore()
    service = NodeKnowledgePackService(store)
    source = snapshot()
    record = await service.claim(source)

    with pytest.raises(ValueError, match=message):
        await service.complete(record, snapshot=source, pack=pack)

    assert store.completed == []


def test_atoms_hash_is_stable_across_dict_insertion_order() -> None:
    first = [{"id": "x", "kind": "case"}]
    second = [{"kind": "case", "id": "x"}]
    assert atoms_hash(first) == atoms_hash(second)
