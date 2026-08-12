"""The design-time schema graph of §4.1, driven end to end without a DB or network.

Three things are worth testing here and one thing is not.

Worth testing:

* **The wiring.** ``build_schema_graph`` builds its edges in a loop, so a single
  off-by-one in ``_STEPS`` would silently reorder the pipeline. The structural test
  pins the real sequence and the fact that *every* step has an escape hatch to
  ``handle_error``.
* **The happy path, for real.** The two LLM calls go through ``FixtureLLMService``
  (§12.1) and the database through a fake session that behaves like one (``flush``
  mints ids, ``get`` resolves by model). That makes the whole chain observable:
  ``load_source``'s closed heading list reaches ``persist_schema`` and an invented
  heading is dropped; index prerequisites become real FK rows; a cyclic arrow is
  pruned instead of fatal; the persisted nodes carry ``reviewed_at = None``.
* **The error path.** The graph's promise is that a failing node short-circuits
  rather than letting the next one run on an empty state — because
  ``persist_schema`` running after a failure would overwrite a real schema with an
  empty one. Both a failure at the first node and a failure in the middle are
  exercised, and both assert the *absence* of the downstream writes.

Not worth testing: that ``StateGraph.add_node`` adds a node. The stubs here replace
I/O seams only; every node body, the error wrapper, the router and the compiled
graph are the production ones.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from src.agents.schema import nodes as schema_nodes
from src.agents.schema.graph import build_schema_graph, route_on_error
from src.agents.schema.nodes import distinct_headings, select_headings
from src.agents.schema.runner import DEFAULT_INTENT_DENSITY, initial_state
from src.agents.schema.state import SchemaState
from src.llm.client import LLMConfig
from src.llm.fixtures import FixtureLLMService, write_fixture
from src.llm.prompts import THEME_EXTRACTOR_SYSTEM, build_extraction_prompt
from src.llm.prompts.schema import SCHEMA_DESIGNER_SYSTEM, build_schema_prompt
from src.models import (
    Course,
    CourseNode,
    CourseNodePrerequisite,
    CourseSchemaStatus,
    GenerationJob,
    GenerationStep,
    NodeCriticality,
)

JOB_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
DOC_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
COURSE_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

FULL_TEXT = "Politica de devoluciones. El plazo es de 14 dias naturales."
DOC_TITLE = "Manual de devoluciones"
COURSE_TITLE = "Politica de devoluciones"
COURSE_OUTCOME = "Gestionar devoluciones sin errores"

# Two real headings and three rows that must not survive: a non-dict, a non-string
# heading and a blank one.
CHUNK_METADATAS: list[Any] = [
    {"heading": "Devoluciones"},
    {"heading": "Plazo"},
    {"heading": "Devoluciones"},
    None,
    {"heading": "   "},
    {"heading": 7},
]
AVAILABLE_HEADINGS = ["Devoluciones", "Plazo"]

THEMES_RESPONSE = json.dumps(
    {"themes": [{"name": "Devoluciones", "description": "Plazos y excepciones"}]},
    ensure_ascii=False,
)
THEMES = [{"name": "Devoluciones", "description": "Plazos y excepciones"}]

# The proposal deliberately carries every recoverable defect §4.1 says must be
# survived rather than fatal: a cyclic arrow, an invented heading, and a node with
# no summary.
DESIGN_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "title": "Excepciones al plazo",
                "summary": "Cuando no se admite la devolucion.",
                "outcome": "Reconocer una excepcion",
                "criticality": "recommended",
                "default_ui_format": "explanation",
                "estimated_minutes": 5,
                "source_headings": ["Plazo"],
                "prerequisites": [1],
            },
            {
                "title": "Plazo de devolucion",
                "summary": "Son 14 dias naturales desde la entrega.",
                "outcome": "Aplicar el plazo",
                "criticality": "critical",
                "default_ui_format": "explanation",
                "estimated_minutes": 4,
                "source_headings": ["Devoluciones", "Politica inventada"],
                # Closes a cycle with node 0: must be pruned, not fatal.
                "prerequisites": [0],
            },
            {
                "title": "Nodo sin resumen",
                "summary": "   ",
                "criticality": "critical",
                "prerequisites": [],
            },
        ]
    },
    ensure_ascii=False,
)

SOURCE_METADATA = {
    "total_pages": 2,
    "doc_count": 1,
    "doc_titles": [DOC_TITLE],
}


# --------------------------------------------------------------------------- #
# Fakes: a session that behaves like one, and a document row
# --------------------------------------------------------------------------- #
@dataclass
class FakeDocument:
    id: uuid.UUID
    title: str
    full_text: str
    page_count: int | None = 2


class FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


@dataclass
class FakeSession:
    """Answers by inspecting the SQL, so a query for the wrong table is visible.

    ``flush`` mints primary keys the way ``gen_random_uuid()`` does, which is what
    makes the prerequisite FK rows assertable: ``persist_schema`` reads
    ``created[i].id`` after flushing.
    """

    course: Course
    job: GenerationJob
    documents: list[FakeDocument] = field(default_factory=list)
    metadatas: list[Any] = field(default_factory=list)
    added: list[Any] = field(default_factory=list)
    deleted: list[Any] = field(default_factory=list)
    statements: list[str] = field(default_factory=list)
    commits: int = 0

    async def execute(self, query):
        sql = str(query)
        self.statements.append(sql)
        if "FROM document_chunks" in sql:
            return FakeResult(self.metadatas)
        if "FROM documents" in sql:
            return FakeResult(self.documents)
        if "SET CONSTRAINTS" in sql:
            return FakeResult([])
        if "FROM course_nodes" in sql:
            return FakeResult([])  # no previous proposal to replace
        if "FROM organizations" in sql:
            return FakeResult([])
        raise AssertionError(f"unexpected query: {sql}")

    async def get(self, model, pk):
        if model is Course:
            return self.course if pk == self.course.id else None
        if model is GenerationJob:
            return self.job if pk == self.job.id else None
        raise AssertionError(f"unexpected get({model!r}, {pk})")

    def add(self, obj) -> None:
        self.added.append(obj)

    async def delete(self, obj) -> None:
        self.deleted.append(obj)

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self) -> None:
        self.commits += 1

    # -- used as the async_session_factory itself --------------------------- #
    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class ExplodingSessionFactory:
    """A session factory for a machine with no database (§12.2)."""

    def __init__(self, message: str = "no database in this environment") -> None:
        self.message = message

    def __call__(self):
        return self

    async def __aenter__(self):
        raise RuntimeError(self.message)

    async def __aexit__(self, *exc_info):
        return False


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
def make_course() -> Course:
    course = Course(
        org_id=ORG_ID,
        title=COURSE_TITLE,
        outcome=COURSE_OUTCOME,
        source_document_id=DOC_ID,
        schema_status=CourseSchemaStatus.DRAFT,
        intent_density=3,
    )
    course.id = COURSE_ID
    return course


def make_job() -> GenerationJob:
    job = GenerationJob(
        org_id=ORG_ID,
        triggered_by=USER_ID,
        source_document_id=DOC_ID,
        status=GenerationStep.SCHEMA_PROPOSING,
        result_course_id=COURSE_ID,
        progress={"intent_density": 3},
    )
    job.id = JOB_ID
    return job


def make_state(**overrides) -> SchemaState:
    state: SchemaState = {
        "job_id": str(JOB_ID),
        "org_id": str(ORG_ID),
        "triggered_by": str(USER_ID),
        "source_document_ids": [str(DOC_ID)],
        "course_id": str(COURSE_ID),
        "intent_density": 3,
        "proposed_nodes": [],
        "schema_warnings": [],
        "current_step": "pending",
        "error": None,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def seed_fixtures(directory) -> None:
    """Record the two responses the graph's two LLM calls will look up.

    The keys are derived from the prompts the nodes must build, so a node that
    stopped threading ``available_headings`` or ``intent_density`` into its prompt
    would hash to a different key and fail loudly instead of quietly.
    """
    write_fixture(
        system_prompt=THEME_EXTRACTOR_SYSTEM,
        user_prompt=build_extraction_prompt(FULL_TEXT),
        response=THEMES_RESPONSE,
        relative_path="schema/themes.json",
        directory=directory,
    )
    write_fixture(
        system_prompt=SCHEMA_DESIGNER_SYSTEM,
        user_prompt=build_schema_prompt(
            THEMES,
            SOURCE_METADATA,
            AVAILABLE_HEADINGS,
            intent_density=3,
            course_title=COURSE_TITLE,
            course_outcome=COURSE_OUTCOME,
        ),
        response=DESIGN_RESPONSE,
        relative_path="schema/design.json",
        directory=directory,
    )


@dataclass
class Harness:
    session: FakeSession
    course: Course
    job: GenerationJob
    events: list[tuple[str, str, dict]]
    job_updates: list[dict]
    pack_spawns: list[tuple[uuid.UUID, uuid.UUID, int, int]]

    def event_types(self) -> list[str]:
        return [event_type for _, event_type, _ in self.events]

    def steps(self) -> list[str]:
        return [
            data.get("step")
            for _, event_type, data in self.events
            if event_type == "schema_step"
        ]

    def nodes_added(self) -> list[CourseNode]:
        return [obj for obj in self.session.added if isinstance(obj, CourseNode)]

    def edges_added(self) -> list[CourseNodePrerequisite]:
        return [
            obj
            for obj in self.session.added
            if isinstance(obj, CourseNodePrerequisite)
        ]


@pytest.fixture
def harness(monkeypatch, tmp_path) -> Harness:
    """Real nodes, real graph, real error wrapper; only the I/O seams are fakes."""
    seed_fixtures(tmp_path)
    course = make_course()
    job = make_job()
    session = FakeSession(
        course=course,
        job=job,
        documents=[
            FakeDocument(id=DOC_ID, title=DOC_TITLE, full_text=FULL_TEXT)
        ],
        metadatas=CHUNK_METADATAS,
    )

    events: list[tuple[str, str, dict]] = []
    job_updates: list[dict] = []
    pack_spawns: list[tuple[uuid.UUID, uuid.UUID, int, int]] = []

    async def fake_publish(channel: str, event_type: str, data: dict) -> None:
        events.append((channel, event_type, data))

    async def fake_set_job(job_id: str, **fields: Any) -> None:
        job_updates.append({"job_id": job_id, **fields})

    async def fake_make_llm(org_id: uuid.UUID) -> FixtureLLMService:
        return FixtureLLMService(
            LLMConfig(model="fixture/local", api_base=None, api_key=None),
            directory=tmp_path,
        )

    async def fake_mark_job_failed(job_id: str, message: str) -> None:
        job_updates.append({"job_id": job_id, "marked_failed": message})

    def fake_spawn_pack(
        course_id: uuid.UUID, org_id: uuid.UUID, schema_version: int
    ) -> None:
        pack_spawns.append((course_id, org_id, schema_version, session.commits))

    monkeypatch.setattr("src.core.sse.publish", fake_publish)
    monkeypatch.setattr(schema_nodes, "async_session_factory", session)
    monkeypatch.setattr(schema_nodes, "_set_job", fake_set_job)
    monkeypatch.setattr(schema_nodes, "_make_llm", fake_make_llm)
    monkeypatch.setattr(schema_nodes, "_spawn_knowledge_pack_shadow", fake_spawn_pack)
    monkeypatch.setattr(
        "src.agents.schema.errors.mark_job_failed", fake_mark_job_failed
    )

    return Harness(
        session=session,
        course=course,
        job=job,
        events=events,
        job_updates=job_updates,
        pack_spawns=pack_spawns,
    )


async def run_graph(state: SchemaState) -> dict:
    graph = build_schema_graph()
    return await graph.ainvoke(
        state, config={"configurable": {"thread_id": str(JOB_ID)}}
    )


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #
def test_the_graph_is_the_pipeline_of_4_1() -> None:
    """The exact chain of §4.1, with an error escape from every step."""
    drawn = build_schema_graph().get_graph()

    assert set(drawn.nodes) == {
        "__start__",
        "load_source",
        "extract_themes_schema",
        "design_schema",
        "persist_schema",
        "handle_error",
        "__end__",
    }

    edges = {(edge.source, edge.data or "", edge.target) for edge in drawn.edges}
    assert ("__start__", "", "load_source") in edges
    chain = [
        ("load_source", "extract_themes_schema"),
        ("extract_themes_schema", "design_schema"),
        ("design_schema", "persist_schema"),
        ("persist_schema", "__end__"),
    ]
    for source, target in chain:
        assert (source, "ok", target) in edges, f"{source} -> {target} missing"
        assert (source, "error", "handle_error") in edges, f"{source} has no escape"
    assert ("handle_error", "", "__end__") in edges
    # handle_error is terminal: it must never feed back into the pipeline.
    assert [e.target for e in drawn.edges if e.source == "handle_error"] == ["__end__"]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({}, "ok"),
        ({"error": None}, "ok"),
        ({"error": ""}, "ok"),
        ({"error": "[load_source] boom"}, "error"),
    ],
)
def test_route_on_error_branches(state: dict, expected: str) -> None:
    assert route_on_error(state) == expected  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# The happy path, end to end
# --------------------------------------------------------------------------- #
async def test_the_graph_proposes_a_schema_end_to_end(harness: Harness) -> None:
    final = await run_graph(make_state())

    assert final["error"] is None
    assert final["current_step"] == "schema_proposed"
    # Every step ran, in order, and the terminal event closed the stream.
    assert harness.steps() == [
        "loading_source",
        "extracting_themes",
        "designing_schema",
    ]
    assert harness.event_types()[-2:] == ["schema_progress", "schema_ready"]
    assert harness.session.commits == 1


async def test_pack_generation_is_scheduled_only_after_the_schema_commit(
    harness: Harness,
) -> None:
    await run_graph(make_state())

    assert harness.pack_spawns == [(COURSE_ID, ORG_ID, 1, 1)]
    assert harness.event_types()[-1] == "schema_ready"


async def test_the_state_carries_the_shape_4_1_declares(harness: Harness) -> None:
    final = await run_graph(make_state())

    assert final["rag_mode"] == "full_text"  # one short document
    assert final["full_texts"] == {str(DOC_ID): FULL_TEXT}
    assert final["source_metadata"] == SOURCE_METADATA
    assert final["available_headings"] == AVAILABLE_HEADINGS
    assert final["extracted_themes"] == THEMES
    # The node with a blank summary never reaches persistence.
    assert [node["title"] for node in final["proposed_nodes"]] == [
        "Excepciones al plazo",
        "Plazo de devolucion",
        "Nodo sin resumen",
    ]


async def test_persisted_nodes_are_topologically_positioned(harness: Harness) -> None:
    await run_graph(make_state())

    persisted = harness.nodes_added()
    assert [(node.title, node.position) for node in persisted] == [
        ("Plazo de devolucion", 1),
        ("Excepciones al plazo", 2),
    ]
    plazo, excepciones = persisted
    assert plazo.criticality is NodeCriticality.CRITICAL
    assert plazo.mastery_threshold == pytest.approx(0.90)
    assert excepciones.criticality is NodeCriticality.RECOMMENDED
    assert excepciones.mastery_threshold == pytest.approx(0.80)
    # §11.1 rule 2: a proposal is never pre-approved.
    assert all(node.reviewed_at is None and node.reviewed_by is None for node in persisted)
    assert all(node.org_id == ORG_ID and node.course_id == COURSE_ID for node in persisted)


async def test_index_prerequisites_become_real_edges(harness: Harness) -> None:
    """The LLM speaks indices; the database only understands uuids (§4.1)."""
    await run_graph(make_state())

    plazo, excepciones = harness.nodes_added()
    edges = harness.edges_added()
    assert len(edges) == 1
    assert edges[0].node_id == excepciones.id
    assert edges[0].prerequisite_node_id == plazo.id
    assert plazo.id is not None and plazo.id != excepciones.id


async def test_recoverable_defects_become_warnings_not_failures(
    harness: Harness,
) -> None:
    final = await run_graph(make_state())
    warnings = " | ".join(final["schema_warnings"])

    assert "ciclico" in warnings, "the cyclic arrow must be pruned, not fatal"
    assert "sin titulo o sin summary" in warnings
    assert "Politica inventada" in warnings
    assert final["error"] is None


async def test_an_invented_heading_never_reaches_the_database(
    harness: Harness,
) -> None:
    """A heading matching no chunk would hand the runtime an empty source (§4.1)."""
    await run_graph(make_state())

    plazo, excepciones = harness.nodes_added()
    assert plazo.source_headings == ["Devoluciones"]
    assert excepciones.source_headings == ["Plazo"]


async def test_the_job_row_records_the_proposal_for_the_later_diff(
    harness: Harness,
) -> None:
    """``validate`` reads this back to log a proposed -> validated diff (§3.5)."""
    await run_graph(make_state())

    assert harness.job.status is GenerationStep.SCHEMA_PROPOSED
    assert harness.job.result_course_id == COURSE_ID
    progress = harness.job.progress
    assert progress["node_count"] == 2
    assert [item["title"] for item in progress["proposed_nodes"]] == [
        "Plazo de devolucion",
        "Excepciones al plazo",
    ]
    assert any("Politica inventada" in w for w in progress["schema_warnings"])


async def test_the_course_lands_in_proposed_never_validated(harness: Harness) -> None:
    """The gate: the pipeline can only ever produce a schema awaiting review."""
    await run_graph(make_state())

    assert harness.course.schema_status is CourseSchemaStatus.PROPOSED
    assert harness.course.intent_density == 3
    ready = [data for _, event_type, data in harness.events if event_type == "schema_ready"]
    assert ready and ready[0]["node_count"] == 2
    assert "Revisalo y validalo" in ready[0]["message"]


# --------------------------------------------------------------------------- #
# The error path
# --------------------------------------------------------------------------- #
async def test_a_failure_in_the_first_node_short_circuits_the_pipeline(
    harness: Harness, monkeypatch
) -> None:
    monkeypatch.setattr(schema_nodes, "async_session_factory", ExplodingSessionFactory())

    async def never(org_id):  # pragma: no cover - must not be reached
        raise AssertionError("the pipeline kept going after load_source failed")

    monkeypatch.setattr(schema_nodes, "_make_llm", never)

    final = await run_graph(make_state())

    assert final["current_step"] == "failed"
    assert final["error"].startswith("[load_source] RuntimeError")
    assert "no database" in final["error"]
    assert harness.nodes_added() == []
    assert harness.steps() == []  # not even the first step was announced
    # One "error" from the node wrapper, one from the terminal handler.
    assert harness.event_types() == ["error", "error"]
    assert any("marked_failed" in update for update in harness.job_updates)
    assert not any(
        update.get("status") is GenerationStep.SCHEMA_PROPOSED
        for update in harness.job_updates
    )


async def test_a_failure_in_the_middle_never_persists_an_empty_schema(
    harness: Harness, tmp_path
) -> None:
    """Overwriting a real schema with an empty one is the failure mode §4.1 fears."""
    # Remove the designer's recording: the fixture LLM then raises LLMError, which
    # is exactly how a provider failure surfaces in this environment.
    (tmp_path / "schema" / "design.json").unlink()

    final = await run_graph(make_state())

    assert final["current_step"] == "failed"
    assert final["error"].startswith("[design_schema] LLMError")
    # The two nodes before it did run; the one after it did not.
    assert harness.steps() == ["loading_source", "extracting_themes"]
    assert harness.nodes_added() == []
    assert harness.edges_added() == []
    assert harness.session.commits == 0
    assert harness.course.schema_status is CourseSchemaStatus.DRAFT
    assert harness.job.status is GenerationStep.SCHEMA_PROPOSING
    assert "schema_ready" not in harness.event_types()


async def test_handle_error_reports_the_step_that_failed(
    harness: Harness, tmp_path
) -> None:
    (tmp_path / "schema" / "design.json").unlink()
    await run_graph(make_state())

    failures = [data for _, event_type, data in harness.events if event_type == "error"]
    # One from the node wrapper, one from the terminal handler.
    assert len(failures) == 2
    assert failures[0]["step"] == "design_schema"  # the wrapper knows the node name
    assert failures[1]["step"] == "failed"  # the terminal handler reports the state
    terminal = [u for u in harness.job_updates if u.get("status") is GenerationStep.FAILED]
    assert terminal and terminal[0]["job_id"] == str(JOB_ID)


async def test_an_oversized_proposal_is_truncated_not_rejected(
    harness: Harness, tmp_path
) -> None:
    """A model that returns 300 "nodes" misread the task; the panel must survive it."""
    oversized = {
        "nodes": [
            {
                "title": f"Nodo {i}",
                "summary": f"Resumen {i}",
                "criticality": "critical",
                "source_headings": ["Devoluciones"],
                "prerequisites": [],
            }
            for i in range(schema_nodes.MAX_PROPOSED_NODES + 7)
        ]
    }
    write_fixture(
        system_prompt=SCHEMA_DESIGNER_SYSTEM,
        user_prompt=build_schema_prompt(
            THEMES,
            SOURCE_METADATA,
            AVAILABLE_HEADINGS,
            intent_density=3,
            course_title=COURSE_TITLE,
            course_outcome=COURSE_OUTCOME,
        ),
        response=json.dumps(oversized, ensure_ascii=False),
        relative_path="schema/design.json",
        directory=tmp_path,
    )

    final = await run_graph(make_state())

    assert final["error"] is None
    assert len(final["proposed_nodes"]) == schema_nodes.MAX_PROPOSED_NODES
    assert len(harness.nodes_added()) == schema_nodes.MAX_PROPOSED_NODES
    assert any("se conservaron los primeros" in w for w in final["schema_warnings"])


# --------------------------------------------------------------------------- #
# The pure pieces the graph depends on
# --------------------------------------------------------------------------- #
def test_distinct_headings_is_order_preserving_and_hostile_to_junk() -> None:
    assert distinct_headings(CHUNK_METADATAS) == AVAILABLE_HEADINGS


def test_select_headings_forgives_case_but_not_invention() -> None:
    kept, warnings = select_headings(
        ["  devoluciones ", "Politica inventada", "Plazo", "Plazo"],
        AVAILABLE_HEADINGS,
        node_title="Plazo de devolucion",
    )
    assert kept == ["Devoluciones", "Plazo"]
    assert len(warnings) == 1 and "Politica inventada" in warnings[0]


def test_select_headings_keeps_nothing_when_the_document_has_no_headings() -> None:
    kept, warnings = select_headings(["Cualquiera"], [], node_title="X")
    assert kept == [] and warnings == []


# --------------------------------------------------------------------------- #
# The state the runner hands the graph
# --------------------------------------------------------------------------- #
def test_initial_state_matches_the_graph_contract() -> None:
    state = initial_state(make_job())
    assert state["job_id"] == str(JOB_ID)
    assert state["course_id"] == str(COURSE_ID)
    assert state["source_document_ids"] == [str(DOC_ID)]
    assert state["intent_density"] == 3
    assert state["error"] is None
    assert state["current_step"] == "pending"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (-2, 1),
        (9, 5),
        ("4", 4),
        ("nonsense", DEFAULT_INTENT_DENSITY),
        (None, DEFAULT_INTENT_DENSITY),
        (0, DEFAULT_INTENT_DENSITY),
    ],
)
def test_initial_state_clamps_intent_density(stored, expected: int) -> None:
    job = make_job()
    job.progress = {"intent_density": stored}
    assert initial_state(job)["intent_density"] == expected


def test_initial_state_survives_a_job_with_no_course() -> None:
    job = make_job()
    job.result_course_id = None
    job.source_document_id = None
    state = initial_state(job)
    assert state["course_id"] == ""
    assert state["source_document_ids"] == []
