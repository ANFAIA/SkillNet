"""The shadow knowledge-pack runner is testable without a database or LLM."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from src.knowledge_pack.runner import (
    KnowledgePackRunnerDependencies,
    run_packs_for_schema,
    source_fingerprint,
)
from src.models import NodeKnowledgePackStatus
from src.services.node_knowledge_pack_service import CompletedKnowledgePack


@dataclass
class FakeCourse:
    id: uuid.UUID
    org_id: uuid.UUID
    schema_version: int = 4


@dataclass
class FakeNode:
    id: uuid.UUID
    org_id: uuid.UUID
    course_id: uuid.UUID
    title: str
    summary: str = "Resumen"
    outcome: str | None = "Aplicar el procedimiento"
    criticality: str = "recommended"
    position: int = 1
    source_document_id: uuid.UUID | None = None
    source_headings: list[str] | None = None
    mastery_threshold: float = 0.8
    default_ui_format: str = "explanation"
    archived: bool = False


class FakeSession:
    def __init__(self, nodes: dict[uuid.UUID, FakeNode]) -> None:
        self.nodes = nodes
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, model, value):
        del model
        return self.nodes.get(value)

    async def commit(self):
        self.commits += 1


class FakeSessionFactory:
    def __init__(self, nodes: list[FakeNode]) -> None:
        self.nodes = {node.id: node for node in nodes}
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = FakeSession(self.nodes)
        self.sessions.append(session)
        return session


class FakeService:
    def __init__(self, *, ready_node_ids: set[uuid.UUID] = (), stale: bool = False) -> None:
        self.ready_node_ids = ready_node_ids
        self.stale = stale
        self.claims = []
        self.completed = []
        self.failed = []

    async def claim(self, snapshot):
        self.claims.append(snapshot)
        status = (
            NodeKnowledgePackStatus.READY
            if snapshot.node_id in self.ready_node_ids
            else NodeKnowledgePackStatus.PENDING
        )
        return SimpleNamespace(id=uuid.uuid4(), status=status)

    async def complete(self, record, *, snapshot, pack):
        self.completed.append((record, snapshot, pack))
        if self.stale:
            return None
        return SimpleNamespace(id=record.id, status=NodeKnowledgePackStatus.READY)

    async def fail(self, record, *, snapshot, error_message):
        self.failed.append((record, snapshot, error_message))
        return SimpleNamespace(id=record.id, status=NodeKnowledgePackStatus.FAILED)


class FakeGenerator:
    def __init__(self, *, fail_titles: set[str] = (), delay: float = 0) -> None:
        self.fail_titles = fail_titles
        self.delay = delay
        self.calls: list[tuple[FakeCourse, FakeNode, str]] = []
        self.running = 0
        self.max_running = 0

    async def generate(self, *, course, node, source_context, snapshot):
        del snapshot
        self.calls.append((course, node, source_context))
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if node.title in self.fail_titles:
                raise RuntimeError(f"bad node: {node.title}")
            return CompletedKnowledgePack(
                markdown=f"# {node.title}",
                pack_payload={"format": "node-knowledge-pack/1", "node": node.title},
                pack_hash="a" * 64,
                atoms=[{"id": node.title, "kind": "fact"}],
                provenance={node.title: ["source"]},
                input_tokens=11,
                output_tokens=7,
                duration_ms=3,
            )
        finally:
            self.running -= 1


def make_dependencies(
    course: FakeCourse,
    nodes: list[FakeNode],
    generator: FakeGenerator,
    service: FakeService,
    **changes,
) -> KnowledgePackRunnerDependencies:
    sessions = FakeSessionFactory(nodes)

    async def load_course(_db, course_id):
        return course if course_id == course.id else None

    async def load_nodes(_db, course_id, org_id):
        return [node for node in nodes if node.course_id == course_id and node.org_id == org_id]

    async def load_source(_db, node, _org_id):
        return f"documento para {node.title}"

    values = {
        "concurrency": 2,
        "timeout_seconds": 1,
        "load_source": load_source,
        **changes,
    }
    return KnowledgePackRunnerDependencies(
        generator=generator,
        session_factory=sessions,
        load_course=load_course,
        load_nodes=load_nodes,
        service_for_session=lambda _db: service,
        **values,
    )


def fixtures():
    org_id = uuid.uuid4()
    course = FakeCourse(id=uuid.uuid4(), org_id=org_id)
    nodes = [
        FakeNode(uuid.uuid4(), org_id, course.id, "Apertura", position=1),
        FakeNode(uuid.uuid4(), org_id, course.id, "Comanda", position=2),
        FakeNode(uuid.uuid4(), org_id, course.id, "Queja", position=3),
    ]
    return org_id, course, nodes


async def test_runner_isolates_node_failures_and_limits_concurrency() -> None:
    org_id, course, nodes = fixtures()
    generator = FakeGenerator(fail_titles={"Comanda"}, delay=0.01)
    service = FakeService()
    dependencies = make_dependencies(course, nodes, generator, service)

    metrics = await run_packs_for_schema(course.id, org_id, 4, dependencies=dependencies)

    assert metrics.ready == 2
    assert metrics.failed == 1
    assert metrics.input_tokens == 22
    assert metrics.output_tokens == 14
    assert generator.max_running == 2
    assert len(service.claims) == 3
    assert len(service.completed) == 2
    assert len(service.failed) == 1
    assert "bad node: Comanda" in service.failed[0][2]


async def test_runner_marks_a_timeout_failed_without_stopping_other_nodes() -> None:
    org_id, course, nodes = fixtures()
    generator = FakeGenerator(delay=0.02)
    service = FakeService()
    dependencies = make_dependencies(
        course, nodes[:2], generator, service, timeout_seconds=0.001
    )

    metrics = await run_packs_for_schema(course.id, org_id, 4, dependencies=dependencies)

    assert metrics.failed == 2
    assert all("TimeoutError" in result.error for result in metrics.results)
    assert len(service.failed) == 2


async def test_runner_skips_a_ready_snapshot_and_discards_late_completion() -> None:
    org_id, course, nodes = fixtures()
    generator = FakeGenerator()
    service = FakeService(ready_node_ids={nodes[0].id}, stale=True)
    dependencies = make_dependencies(course, nodes[:2], generator, service)

    metrics = await run_packs_for_schema(course.id, org_id, 4, dependencies=dependencies)

    assert metrics.skipped == 1
    assert metrics.stale == 1
    assert metrics.failed == 0
    assert [node.title for _, node, _ in generator.calls] == ["Comanda"]
    assert len(service.completed) == 1


async def test_runner_drafts_and_persists_a_source_when_the_node_has_none() -> None:
    org_id, course, nodes = fixtures()
    course.title = "Devoluciones"
    course.description = "Plazos de la tienda"
    generator = FakeGenerator()
    service = FakeService()
    drafted: list[str] = []
    persisted: list[tuple[uuid.UUID, str]] = []

    async def load_source(_db, _node, _org_id):
        return ""

    async def draft_source(*, course, node):
        del course
        text = f"## {node.title}\nEl cliente tiene 14 dias naturales desde la entrega."
        drafted.append(text)
        return text

    async def persist_source(_db, node, text, _course):
        persisted.append((node.id, text))
        node.source_document_id = uuid.uuid4()

    dependencies = make_dependencies(
        course,
        nodes[:1],
        generator,
        service,
        load_source=load_source,
        draft_source=draft_source,
        persist_source=persist_source,
    )

    metrics = await run_packs_for_schema(course.id, org_id, 4, dependencies=dependencies)

    assert metrics.ready == 1
    assert drafted
    assert persisted == [(nodes[0].id, drafted[0])]
    assert generator.calls[0][2] == drafted[0]


async def test_runner_uses_the_schema_briefing_when_there_is_no_drafter() -> None:
    org_id, course, nodes = fixtures()
    course.title = "Devoluciones"
    generator = FakeGenerator()
    service = FakeService()

    async def load_source(_db, _node, _org_id):
        return ""

    dependencies = make_dependencies(
        course, nodes[:1], generator, service, load_source=load_source
    )

    metrics = await run_packs_for_schema(course.id, org_id, 4, dependencies=dependencies)

    assert metrics.ready == 1
    source = generator.calls[0][2]
    assert nodes[0].title in source
    assert "Resultado" in source or nodes[0].summary in source


async def test_runner_keeps_an_uploaded_excerpt_and_skips_the_drafter() -> None:
    org_id, course, nodes = fixtures()
    generator = FakeGenerator()
    drafted = []

    async def draft_source(*, course, node):
        del course, node
        drafted.append("should not run")
        return "## Inventado"

    dependencies = make_dependencies(
        course, nodes[:1], generator, FakeService(), draft_source=draft_source
    )

    await run_packs_for_schema(course.id, org_id, 4, dependencies=dependencies)

    assert drafted == []
    assert generator.calls[0][2] == f"documento para {nodes[0].title}"


async def test_runner_refuses_a_schema_version_that_is_no_longer_current() -> None:
    org_id, course, nodes = fixtures()
    dependencies = make_dependencies(course, nodes, FakeGenerator(), FakeService())

    with pytest.raises(ValueError, match="schema_version does not match"):
        await run_packs_for_schema(course.id, org_id, 3, dependencies=dependencies)


def test_source_fingerprint_changes_for_source_or_node_contract_not_dict_order() -> None:
    org_id, course, nodes = fixtures()
    node = nodes[0]
    first = source_fingerprint(node=node, source_context="A", schema_version=4)
    same = source_fingerprint(node=node, source_context="A", schema_version=4)
    changed_source = source_fingerprint(node=node, source_context="B", schema_version=4)
    node.title = "Apertura revisada"
    changed_node = source_fingerprint(node=node, source_context="A", schema_version=4)

    assert first == same
    assert first != changed_source
    assert first != changed_node
