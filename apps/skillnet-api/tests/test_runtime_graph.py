"""The runtime render graph of §4.2, driven end to end without a database or the network.

The seams that are faked are exactly two: the session factory and the LLM. Everything else
is production code — the compiled graph, every node body, the error wrapper, the router, the
gate, the OpenUI parser and serializer, the cache-key function.

What each group of tests is for:

* **Wiring.** ``build_node_graph`` fans out conditional edges by hand, so a single wrong
  mapping would silently reroute the repair loop or lose the fallback. The structural test
  pins the real graph of §4.2, including "every step has a way out to ``fallback_seed``".
* **The happy path, for real.** Two LLM calls through ``FixtureLLMService`` with the packaged
  fixtures: ``decide_formato`` and ``genera_ui``. The keys are derived from the prompts the
  nodes must build, so a node that stopped threading ``role_title`` or ``effective_density``
  into its prompt hashes to a different key and fails loudly instead of quietly.
* **The repair loop.** Malformed output -> the retry carries the **validator's own messages**
  -> valid program. This is the test that would catch a repair prompt that forgot the errors.
* **The fallback.** Invalid twice -> ``fallback_seed`` -> the v1 seed lesson served as
  ``Markdown``, ``status='fallback'``. §9.3 level 4: without an LLM the course degrades
  instead of breaking.
* **The gate.** ``answer_key`` never enters ``ui_spec``, and what is persisted as ``dialect``
  is the **re-serialization**, not the model's bytes.
* **The calibration rule of §6.4**, which is a hard rule: with ``nodes_completed < 3`` there
  is *no* ``decide_formato`` call at all, and ``vector_bucket`` stays out of the key.
* **The cache.** A second learner of the same bucket gets ``cached=True`` and **no graph is
  spawned**, which is the operational meaning of "pays no tokens".
* **Cancellation.** §9.1: the in-flight render is cancelled when the probe closes as
  ``mastered``, and ``CancelledError`` is never swallowed by the node wrapper.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import src.llm as llm_package
from src.agents.runtime import errors as runtime_errors
from src.agents.runtime import nodes as runtime_nodes
from src.agents.runtime.graph import (
    build_node_graph,
    route_after_gate,
    route_after_validate,
)
from src.agents.runtime.nodes import (
    build_fallback_spec,
    missing_answer_keys,
    prune_answer_key,
    split_answer_key,
)
from src.config import settings
from src.llm.client import LLMConfig, Usage
from src.agents.runtime.assessment import plan_assessment
from src.agents.runtime.shape import analyze_shape
from src.llm.fixtures import FixtureLLMService, write_fixture
from src.llm.prompts.runtime import (
    ANSWER_KEY_SENTINEL,
    FORMAT_DECIDER_SYSTEM,
    MAX_UI_RETRIES,
    build_format_prompt,
    build_repair_prompt,
    build_ui_prompt,
    clip_source,
    ui_generator_system,
    ui_repair_system,
)
from src.models import (
    Course,
    CourseDeliveryMode,
    CourseNode,
    CourseSchemaStatus,
    LearnerExperience,
    LearnerNodeState,
    LearnerProfile,
    Lesson,
    LlmUsageLog,
    NodeCriticality,
    NodeRender,
    NodeRenderStatus,
    NodeState,
    UiFormat,
    UserRole,
)
from src.render.backends import get_render_backend
from src.render.errors import RenderError
from src.render.gate import canonicalize
from src.services.node_render_service import build_render_key

# Located off the package, not off the working directory: the same trick
# ``tests/test_probe_reuse.py`` uses, so the suite does not depend on where pytest was run.
FIXTURE_DIR = Path(llm_package.__file__).parent / "fixture_data"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
OTHER_USER_ID = uuid.UUID("2222dddd-2222-2222-2222-222222222222")
COURSE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NODE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
DOC_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
LESSON_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")

# --- the canonical context. The packaged fixtures are keyed on the prompts these produce. --
CANON_TITLE = "Plazo de devolucion"
CANON_SUMMARY = "Las devoluciones se aceptan durante 30 dias naturales desde la entrega."
CANON_OUTCOME = "Aplicar el plazo de devolucion en caja"
CANON_CRITICALITY = "recommended"
CANON_ROLE = "Dependiente"
CANON_SECTOR = "retail"
CANON_PRESET = "standard"
CANON_EXPERIENCE = "some"
CANON_DENSITY = 3
CANON_BAND = "neutral"
CANON_BUCKET = "texto:0.7"
CANON_FORMAT_VECTOR = {"texto": 0.7, "ejercicio": 0.3, "codigo": 0.0, "dato": 0.0}
CANON_FULL_TEXT = (
    "Politica de devoluciones.\n\n"
    "El plazo para devolver un producto es de 30 dias naturales desde la entrega. "
    "Es imprescindible presentar el ticket de compra y que el producto este sin usar.\n\n"
    "Pasado el plazo la devolucion no se admite y solo queda la garantia del fabricante."
)
CANON_SOURCE = clip_source(CANON_FULL_TEXT)
SEED_LESSON_CONTENT = (
    "# Plazo de devolucion\n\nSon **30 dias naturales**.\n\n"
    "Hace falta el ticket y el producto sin usar."
)

FIXTURE_MODEL = "fixture/local"
#: What ``runtime_model_key`` produces once both tiers resolve to the fixture model.
FIXTURE_MODEL_KEY = f"{FIXTURE_MODEL}|{FIXTURE_MODEL}"


# --------------------------------------------------------------------------------------
# The canonical prompts, rebuilt exactly as the nodes must build them
# --------------------------------------------------------------------------------------
def canonical_format_prompt() -> str:
    return build_format_prompt(
        title=CANON_TITLE,
        summary=CANON_SUMMARY,
        outcome=CANON_OUTCOME,
        criticality=CANON_CRITICALITY,
        default_ui_format="explanation",
        role_title=CANON_ROLE,
        sector=CANON_SECTOR,
        experience_level=CANON_EXPERIENCE,
        preset=CANON_PRESET,
        effective_density=CANON_DENSITY,
        scaffold_band=CANON_BAND,
        vector_bucket=CANON_BUCKET,
        mastery=0.0,
        consecutive_failed=0,
        last_error_kind=None,
        source_has_numbers=True,
    )


def canonical_assessment_hint(ui_format: str = "explanation") -> str:
    """The ``CÓMO VERIFICAR`` line the graph injects, rebuilt exactly as ``decide_formato``
    does so the fixture key matches the real prompt (§ variedad-evaluacion-diagnostico.md).

    Depends only on the canonical source shape and ``NODE_ID`` — both deterministic — so the
    canonical prompt stays reproducible even though the hint now varies per node."""
    plan = analyze_shape(source_context=CANON_SOURCE, summary=CANON_SUMMARY, headings=[])
    return plan_assessment(plan, ui_format=ui_format, node_id=str(NODE_ID)).instruction()


def canonical_ui_prompt(ui_format: str = "explanation") -> str:
    return build_ui_prompt(
        title=CANON_TITLE,
        summary=CANON_SUMMARY,
        outcome=CANON_OUTCOME,
        criticality=CANON_CRITICALITY,
        ui_format=ui_format,
        effective_density=CANON_DENSITY,
        scaffold_band=CANON_BAND,
        role_title=CANON_ROLE,
        sector=CANON_SECTOR,
        experience_level=CANON_EXPERIENCE,
        preset=CANON_PRESET,
        # mastery 0.0 with an 0.80 threshold is the `shu` phase -> `understand` (§3.3).
        target_bloom="understand",
        last_error_kind=None,
        consecutive_failed=0,
        consecutive_correct=0,
        tutor_signals=(),
        source_context=CANON_SOURCE,
        assessment_hint=canonical_assessment_hint(ui_format),
    )


def packaged(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def validation_errors_of(raw: str, ui_format: str = "explanation") -> list[str]:
    """The messages ``validate_ui`` will produce for a bad program.

    Rebuilt here for the same reason the prompts are: the repair fixture is keyed on them, so
    a repair prompt that stopped carrying the validator's messages would hash to a different
    key and fail loudly.
    """
    program, _key = split_answer_key(raw)
    try:
        canonicalize(program, ui_format=ui_format, backend=get_render_backend("openui"))
    except RenderError as exc:
        return list(exc.errors)
    raise AssertionError(f"{raw!r} was expected to be rejected")


def register_packaged_fixtures(directory: Path) -> dict[str, str]:
    """Register the packaged ``decide_formato`` / ``genera_ui`` files under the real keys.

    Called by the tests against ``tmp_path`` and by the maintenance path against
    ``src/llm/fixture_data`` itself, so the ``fixtures`` compose profile can run the canonical
    node with no API key. Returns ``{relative_path: key}``.
    """
    keys = {
        "decide_formato/explanation.json": write_fixture(
            system_prompt=FORMAT_DECIDER_SYSTEM,
            user_prompt=canonical_format_prompt(),
            response=packaged("decide_formato/explanation.json"),
            relative_path="decide_formato/explanation.json",
            use_case="decide_formato",
            directory=directory,
        ),
        "genera_ui/openui_explanation.txt": write_fixture(
            system_prompt=ui_generator_system(),
            user_prompt=canonical_ui_prompt("explanation"),
            response=packaged("genera_ui/openui_explanation.txt"),
            relative_path="genera_ui/openui_explanation.txt",
            use_case="genera_ui",
            directory=directory,
        ),
    }
    return keys


# --------------------------------------------------------------------------------------
# Fakes: a session that behaves like one
# --------------------------------------------------------------------------------------
@dataclass
class FakeUser:
    """Only what the runtime reads off ``users``."""

    id: uuid.UUID
    org_id: uuid.UUID
    accessibility: dict = field(default_factory=dict)
    role: str = UserRole.EMPLOYEE.value


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

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._rows[0] if self._rows else 0


def _params(query: Any) -> dict:
    try:
        return dict(query.compile().params)
    except Exception:  # pragma: no cover - only for exotic constructs
        return {}


@dataclass
class FakeSession:
    """Answers by inspecting the SQL, so a query against the wrong table is visible.

    ``flush`` mints primary keys the way ``gen_random_uuid()`` does and registers the object,
    which is what lets ``persist_render`` find by id the row ``load_context`` claimed.
    """

    node: CourseNode
    course: Course
    user: FakeUser
    #: Las OTRAS pantallas del curso, que `load_context` lee para que un nodo no repita
    #: lo que cubren sus hermanos. Vacio por defecto: un curso de un solo nodo.
    siblings: list[CourseNode] = field(default_factory=list)
    profile: LearnerProfile | None = None
    node_state: LearnerNodeState | None = None
    document: FakeDocument | None = None
    lesson: Lesson | None = None
    knowledge_packs: list[Any] = field(default_factory=list)
    learning_events: list[tuple[Any, str, dict]] = field(default_factory=list)
    renders: list[NodeRender] = field(default_factory=list)
    usage: list[LlmUsageLog] = field(default_factory=list)
    added: list[Any] = field(default_factory=list)
    statements: list[str] = field(default_factory=list)
    commits: int = 0

    async def execute(self, query):
        sql = str(query)
        self.statements.append(sql)
        if "FROM organizations" in sql:
            return FakeResult([])
        if "FROM learner_profiles" in sql:
            return FakeResult([self.profile] if self.profile is not None else [])
        if "FROM learner_node_states" in sql:
            return FakeResult([self.node_state] if self.node_state is not None else [])
        if "FROM learning_events" in sql:
            return FakeResult(list(self.learning_events))
        if "FROM node_knowledge_packs" in sql:
            return FakeResult(list(self.knowledge_packs))
        if "FROM node_renders" in sql:
            rows = list(self.renders)
            wanted = {value for value in _params(query).values() if isinstance(value, str)}
            if wanted:
                rows = [row for row in rows if row.cache_key in wanted]
            if "node_renders.status = " in sql:
                rows = [
                    row
                    for row in rows
                    if row.status == NodeRenderStatus.READY and not row.is_preview
                ]
            return FakeResult(rows)
        if "FROM document_chunks" in sql:
            return FakeResult([])
        if "FROM course_nodes" in sql:
            return FakeResult(list(self.siblings))
        raise AssertionError(f"unexpected query: {sql}")

    async def get(self, model, pk):
        if model is CourseNode:
            return self.node if pk == self.node.id else None
        if model is Course:
            return self.course if pk == self.course.id else None
        if model is Lesson:
            return self.lesson if self.lesson is not None and pk == LESSON_ID else None
        if model is NodeRender:
            for row in self.renders:
                if row.id == pk:
                    return row
            return None
        if model.__name__ == "User":
            return self.user if pk == self.user.id else None
        if model.__name__ == "Document":
            return self.document if self.document and pk == self.document.id else None
        raise AssertionError(f"unexpected get({model!r}, {pk})")

    def add(self, obj) -> None:
        self.added.append(obj)

    def add_all(self, objs) -> None:
        self.added.extend(objs)

    async def delete(self, obj) -> None:  # pragma: no cover - unused by the runtime
        raise AssertionError("the runtime graph deletes nothing")

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if isinstance(obj, NodeRender) and obj not in self.renders:
                self.renders.append(obj)
            if isinstance(obj, LlmUsageLog) and obj not in self.usage:
                self.usage.append(obj)

    async def commit(self) -> None:
        await self.flush()
        self.commits += 1

    async def rollback(self) -> None:  # pragma: no cover - only on an integrity race
        pass

    # -- usable as the async_session_factory itself --------------------------------
    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class ExplodingSessionFactory:
    """A machine with no database (§12.2)."""

    def __call__(self):
        return self

    async def __aenter__(self):
        raise RuntimeError("no database in this environment")

    async def __aexit__(self, *exc_info):
        return False


# --------------------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------------------
def make_node(**overrides) -> CourseNode:
    node = CourseNode(
        org_id=ORG_ID,
        course_id=COURSE_ID,
        title=CANON_TITLE,
        summary=CANON_SUMMARY,
        outcome=CANON_OUTCOME,
        criticality=NodeCriticality.RECOMMENDED,
        position=1,
        source_document_id=DOC_ID,
        source_headings=["Devoluciones"],
        mastery_threshold=0.80,
        default_ui_format=UiFormat.EXPLANATION,
        seed_lesson_id=LESSON_ID,
        probe_items=[],
        probe_answer_key={},
        estimated_minutes=5,
    )
    node.id = NODE_ID
    node.archived = False
    for key, value in overrides.items():
        setattr(node, key, value)
    return node


def make_course(**overrides) -> Course:
    course = Course(
        org_id=ORG_ID,
        title="Devoluciones",
        outcome="Gestionar devoluciones sin errores",
        delivery_mode=CourseDeliveryMode.DYNAMIC,
        schema_status=CourseSchemaStatus.VALIDATED,
        schema_version=3,
        intent_density=CANON_DENSITY,
    )
    course.id = COURSE_ID
    for key, value in overrides.items():
        setattr(course, key, value)
    return course


def make_profile(*, nodes_completed: int = 7, user_id: uuid.UUID = USER_ID) -> LearnerProfile:
    profile = LearnerProfile(
        org_id=ORG_ID,
        user_id=user_id,
        role_title=CANON_ROLE,
        sector=CANON_SECTOR,
        goal="dejar de preguntar al encargado",
        experience_level=LearnerExperience.SOME,
        format_vector=dict(CANON_FORMAT_VECTOR),
        nodes_completed=nodes_completed,
        tutor_notes={},
    )
    profile.id = uuid.uuid4()
    return profile


def make_state(state: NodeState = NodeState.LEARNING, **overrides) -> LearnerNodeState:
    row = LearnerNodeState(
        user_id=USER_ID,
        node_id=NODE_ID,
        state=state,
        mastery=0.0,
        scaffold_band=CANON_BAND,
    )
    row.id = uuid.uuid4()
    row.consecutive_correct = 0
    row.consecutive_failed = 0
    row.last_error_kind = None
    row.active_render_id = None
    row.render_pinned = True
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def make_lesson() -> Lesson:
    lesson = Lesson(
        module_id=uuid.uuid4(),
        title=CANON_TITLE,
        content=SEED_LESSON_CONTENT,
        position=1,
    )
    lesson.id = LESSON_ID
    return lesson


@dataclass
class Harness:
    session: FakeSession
    events: list[tuple[str, str, dict]]
    fixture_dir: Path

    def event_types(self) -> list[str]:
        return [event_type for _, event_type, _ in self.events]

    def steps(self) -> list[str]:
        return [
            data.get("step")
            for _, event_type, data in self.events
            if event_type == "render_step"
        ]

    def payloads(self, event_type: str) -> list[dict]:
        return [data for _, kind, data in self.events if kind == event_type]

    def render(self) -> NodeRender:
        assert self.session.renders, "no node_renders row was claimed"
        return self.session.renders[-1]


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Harness:
    """Real nodes, real graph, real gate; only the session factory and the LLM are fakes."""
    monkeypatch.setattr(settings, "LLM_MODEL", FIXTURE_MODEL)
    monkeypatch.setattr(settings, "LLM_RUNTIME_FAST_MODEL", None)
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", None)
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", FIXTURE_MODEL)
    monkeypatch.setattr(settings, "MULTI_AGENT_RENDER", False)
    # These golden fixtures intentionally pin the legacy/full-catalogue arm. The
    # shortlist arm has focused prompt/trace tests with its own deterministic digest.
    monkeypatch.setattr(settings, "RUNTIME_COMPONENT_SHORTLIST", False)
    monkeypatch.setattr(settings, "SEMANTIC_ROUTER", False)

    session = FakeSession(
        node=make_node(),
        course=make_course(),
        user=FakeUser(id=USER_ID, org_id=ORG_ID),
        profile=make_profile(),
        node_state=make_state(),
        document=FakeDocument(id=DOC_ID, title="Manual", full_text=CANON_FULL_TEXT),
        lesson=make_lesson(),
    )

    events: list[tuple[str, str, dict]] = []

    async def fake_publish(channel: str, event_type: str, data: dict) -> None:
        events.append((channel, event_type, data))

    monkeypatch.setattr("src.core.sse.publish", fake_publish)
    monkeypatch.setattr(runtime_nodes, "async_session_factory", session)
    monkeypatch.setattr(runtime_errors, "async_session_factory", session)

    def fake_tier_llm(org_settings, tier):
        return FixtureLLMService(
            LLMConfig(model=FIXTURE_MODEL, api_base=None, api_key=None),
            directory=tmp_path,
        )

    monkeypatch.setattr(runtime_nodes, "tier_llm", fake_tier_llm)

    register_packaged_fixtures(tmp_path)
    return Harness(session=session, events=events, fixture_dir=tmp_path)


def make_request_state(**overrides) -> dict:
    state: dict[str, Any] = {
        "request_id": "req-1",
        "org_id": str(ORG_ID),
        "user_id": str(USER_ID),
        "course_id": str(COURSE_ID),
        "node_id": str(NODE_ID),
        "is_preview": False,
        "schema_version": 3,
        "retry_count": 0,
        "validation_errors": [],
        "answer_key": {},
        "error": None,
        "current_step": "pending",
    }
    state.update(overrides)
    return state


async def run_graph(state: dict) -> dict:
    graph = build_node_graph()
    return await graph.ainvoke(
        state, config={"configurable": {"thread_id": state["request_id"]}}
    )


# --------------------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------------------
def test_the_graph_is_the_pipeline_of_4_2() -> None:
    drawn = build_node_graph().get_graph()

    assert set(drawn.nodes) == {
        "__start__",
        "load_context",
        "probe_gate",
        "decide_formato",
        "author_activity",
        "genera_ui",
        "validate_ui",
        "persist_render",
        "fallback_seed",
        "skip_node",
        "__end__",
    }
    edges = {(edge.source, edge.data or "", edge.target) for edge in drawn.edges}
    assert ("__start__", "", "load_context") in edges
    assert ("load_context", "ok", "probe_gate") in edges
    assert ("probe_gate", "skip", "skip_node") in edges
    assert ("probe_gate", "generate", "decide_formato") in edges
    assert ("decide_formato", "ok", "author_activity") in edges
    assert ("author_activity", "", "genera_ui") in edges
    assert ("genera_ui", "ok", "validate_ui") in edges
    assert ("validate_ui", "ok", "persist_render") in edges
    # The repair loop and the safety net, the two edges §4.2 draws explicitly.
    assert ("validate_ui", "retry", "genera_ui") in edges
    assert ("validate_ui", "fallback", "fallback_seed") in edges
    assert ("skip_node", "", "__end__") in edges
    assert ("fallback_seed", "", "__end__") in edges
    # Every generating step has a way out that still serves the learner something.
    for step in ("load_context", "probe_gate", "decide_formato", "genera_ui"):
        assert (step, "error", "fallback_seed") in edges, f"{step} has no escape"
    # fallback_seed is terminal: it must never feed back into the pipeline.
    assert [e.target for e in drawn.edges if e.source == "fallback_seed"] == ["__end__"]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"ui_spec": {"root": "root"}}, "ok"),
        ({"ui_spec": None, "retry_count": 1}, "retry"),
        ({"ui_spec": None, "retry_count": MAX_UI_RETRIES + 1}, "fallback"),
        ({"error": "boom"}, "fallback"),
    ],
)
def test_route_after_validate_is_exactly_one_repair_attempt(
    state: dict, expected: str
) -> None:
    assert route_after_validate(state) == expected  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------------------
async def test_the_graph_renders_a_node_end_to_end(harness: Harness) -> None:
    final = await run_graph(make_request_state())

    assert final["error"] is None
    assert final["current_step"] == "persist_render"
    assert final["ui_format"] == "explanation"
    assert final["tier"] == "fast"
    assert harness.steps() == [
        "load_context",
        "probe_gate",
        "decide_formato",
        "genera_ui",
        "validate_ui",
        "persist_render",
    ]
    assert "ui_done" in harness.event_types()


async def test_the_persisted_row_is_the_canonical_program_not_the_model_bytes(
    harness: Harness, tmp_path: Path
) -> None:
    """The security property of §5.1, asserted on the row that actually gets served.

    The fixture is deliberately *noisy* — wrapped in a markdown fence, with stray spaces and a
    blank line — because a fixture that is already canonical proves nothing: the two strings
    would be equal for the wrong reason. What is persisted has to be ``serialize(spec)``, so
    the fence and the spacing must be gone.
    """
    noisy = packaged("genera_ui/openui_explanation_fenced.txt")
    write_fixture(
        system_prompt=ui_generator_system(),
        user_prompt=canonical_ui_prompt("explanation"),
        response=noisy,
        relative_path="genera_ui/openui_explanation_fenced.txt",
        directory=tmp_path,
    )

    final = await run_graph(make_request_state())
    render = harness.render()

    assert render.status is NodeRenderStatus.READY
    assert render.ui_format is UiFormat.EXPLANATION
    assert render.dialect
    # Re-serialized from the spec, not passed through.
    assert final["raw_dsl"] == noisy
    assert render.dialect != noisy
    assert "```" not in render.dialect
    backend = get_render_backend("openui")
    expected = backend.serialize(backend.parse(render.dialect, ui_format="explanation"))
    assert render.dialect == expected
    assert render.catalog_version and render.library_version
    assert render.cache_key == final["cache_key"]
    assert render.generated_by == USER_ID
    assert render.is_preview is False


async def test_the_spec_never_carries_an_answer_and_the_key_has_its_own_column(
    harness: Harness, tmp_path: Path
) -> None:
    """Rule 5 of §5.2, end to end on the ``exercise`` fixture that *has* a quiz."""
    raw = packaged("genera_ui/openui_mixed.txt")
    write_fixture(
        system_prompt=ui_generator_system(),
        user_prompt=canonical_ui_prompt("explanation"),
        response=raw,
        relative_path="genera_ui/openui_mixed.txt",
        directory=tmp_path,
    )

    final = await run_graph(make_request_state())
    render = harness.render()

    serialized = json.dumps(render.ui_spec, ensure_ascii=False)
    assert "correct" not in serialized
    assert "explanation\": \"Pasados" not in serialized
    assert render.answer_key == {
        "q1": {
            "correct": 1,
            "explanation": (
                "Pasados 30 dias el plazo ha vencido, asi que la devolucion no se admite; "
                "lo que queda es la garantia del fabricante."
            ),
        }
    }
    # The sentinel and the JSON never reach the servable text.
    assert ANSWER_KEY_SENTINEL not in (render.dialect or "")
    assert "{" not in (render.dialect or "")
    assert final["error"] is None


async def test_the_finished_render_is_pinned_for_the_learner_who_asked(
    harness: Harness,
) -> None:
    """The last step of a render is being reachable.

    ``NodeRenderService`` pins only on a *cache hit* and ``GET /nodes/{id}/render``
    recomputes nothing on purpose (the "Estable" row of §5.5), so if the graph does not pin
    what it just wrote, the learner whose request paid for the generation polls ``202``
    forever while everybody who arrives afterwards gets the render for free. It is also the
    only way back to a forced refresh, whose ``cache_key`` is salted and therefore
    un-lookupable by design.
    """
    harness.session.node_state.active_render_id = None
    harness.session.node_state.render_pinned = False

    await run_graph(make_request_state())
    render = harness.render()

    assert harness.session.node_state.active_render_id == render.id
    assert harness.session.node_state.render_pinned is True


async def test_a_preview_pins_nothing(harness: Harness) -> None:
    """§11.3: a preview generates with the admin's profile and must not touch
    ``learner_node_states`` — that is half of what makes ``shadow`` mode safe."""
    harness.session.node_state.active_render_id = None
    harness.session.node_state.render_pinned = False

    await run_graph(make_request_state(is_preview=True))

    assert harness.render().is_preview is True
    assert harness.session.node_state.active_render_id is None
    assert harness.session.node_state.render_pinned is False


async def test_the_usage_of_both_calls_is_logged_with_its_tier(harness: Harness) -> None:
    """``llm_usage_log`` is what settles the fast/heavy ratio with data (§3.5, §14.2 #1)."""
    await run_graph(make_request_state())

    logged = {(row.use_case, row.purpose, row.tier) for row in harness.session.usage}
    assert ("decide_formato", "runtime_fast", "fast") in logged
    assert ("genera_ui", "runtime_fast", "fast") in logged
    assert all(row.model == FIXTURE_MODEL for row in harness.session.usage)


class UsageReportingLLM(FixtureLLMService):
    """A fixture LLM that also reports usage, standing in for a real provider.

    The fixtures themselves cannot report tokens (no call was made), so without this the
    only thing the suite could assert about §9.3's cost model is that the columns exist.
    """

    async def complete_with_usage(self, system_prompt, user_prompt, **kwargs):
        text, _usage = await super().complete_with_usage(
            system_prompt, user_prompt, **kwargs
        )
        return text, Usage(tokens_in=11, tokens_out=22)

    async def stream(self, messages, *, usage_out=None, **kwargs):
        if usage_out is not None:
            usage_out.update({"tokens_in": 100, "tokens_out": 200, "reason": None})
        async for piece in super().stream(messages, **kwargs):
            yield piece


async def test_the_provider_token_counts_reach_both_tables(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§9.3 cannot be settled with latency: without tokens, ``llm_usage_log`` measures
    nothing about money and the shared ``cache_key`` stays an unverified hypothesis.

    Both calls count towards the render: ``node_renders.tokens_*`` is the cost of the
    screen, not of one of the two calls that produced it.
    """
    monkeypatch.setattr(
        runtime_nodes,
        "tier_llm",
        lambda org_settings, tier: UsageReportingLLM(
            LLMConfig(model=FIXTURE_MODEL, api_base=None, api_key=None),
            directory=harness.fixture_dir,
        ),
    )

    await run_graph(make_request_state())
    render = harness.render()

    assert render.tokens_in == 111
    assert render.tokens_out == 222
    by_use_case = {row.use_case: row for row in harness.session.usage}
    assert (by_use_case["decide_formato"].tokens_in, by_use_case["decide_formato"].tokens_out) == (11, 22)
    assert (by_use_case["genera_ui"].tokens_in, by_use_case["genera_ui"].tokens_out) == (100, 200)


async def test_a_provider_that_reports_nothing_leaves_null_not_zero(
    harness: Harness,
) -> None:
    """``0`` claims the call was free; ``None`` says nobody counted. Coalescing the second
    into the first is what would make the ratio *look* measured."""
    await run_graph(make_request_state())
    render = harness.render()

    assert render.tokens_in is None
    assert render.tokens_out is None
    assert all(row.tokens_in is None for row in harness.session.usage)


async def test_streaming_announces_each_block_as_it_completes(harness: Harness) -> None:
    """§9.2: one ``ui_block`` per completed component, so the skeleton can be replaced
    progressively instead of all at once."""
    await run_graph(make_request_state())

    blocks = harness.payloads("ui_block")
    types = [block["component"]["type"] for block in blocks]
    assert types[:1] == ["Stack"], "the root must stream first (prompt rule)"
    assert {"TextContent", "StepSequence", "Callout"} <= set(types)
    formats = harness.payloads("ui_format")
    assert formats and formats[0] == {"format": "explanation", "tier": "fast"}


# --------------------------------------------------------------------------------------
# The repair loop
# --------------------------------------------------------------------------------------
async def test_malformed_output_is_repaired_with_the_validator_messages(
    harness: Harness, tmp_path: Path
) -> None:
    """The single retry of §4.2, and the reason it is worth having: the model gets told
    *which* line and *which* rule, not "invalid program"."""
    malformed = packaged("genera_ui/malformed_unclosed_array.txt")
    errors = validation_errors_of(malformed)
    assert any("expected ']'" in error for error in errors)

    write_fixture(
        system_prompt=ui_generator_system(),
        user_prompt=canonical_ui_prompt("explanation"),
        response=malformed,
        relative_path="genera_ui/malformed_unclosed_array.txt",
        directory=tmp_path,
    )
    write_fixture(
        system_prompt=ui_repair_system(),
        user_prompt=build_repair_prompt(
            previous=malformed, errors=errors, ui_format="explanation"
        ),
        response=packaged("genera_ui/repaired_after_retry.txt"),
        relative_path="genera_ui/repaired_after_retry.txt",
        directory=tmp_path,
    )

    final = await run_graph(make_request_state())

    assert final["error"] is None
    assert final["current_step"] == "persist_render"
    assert final["retry_count"] == 1
    # genera_ui and validate_ui ran twice; the fallback never did.
    assert harness.steps().count("genera_ui") == 2
    assert harness.steps().count("validate_ui") == 2
    assert "fallback_seed" not in harness.steps()
    assert harness.render().status is NodeRenderStatus.READY
    assert "StepSequence" in json.dumps(harness.render().ui_spec)


async def test_a_missing_answer_key_is_itself_a_repairable_error(
    harness: Harness, tmp_path: Path
) -> None:
    """A ``QuizItem`` with no key would grade every answer 0.0, so the learner could never
    pass the node. That is worth the repair attempt, not worth serving."""
    program, _ = split_answer_key(packaged("genera_ui/openui_mixed.txt"))
    spec = get_render_backend("openui").parse(program, ui_format="explanation")
    # The error list comes from the production function, so a reworded message cannot make
    # this test pass against a repair prompt that no longer carries the real complaint.
    errors = missing_answer_keys(spec, {})
    assert errors and ANSWER_KEY_SENTINEL in errors[0]

    write_fixture(
        system_prompt=ui_generator_system(),
        user_prompt=canonical_ui_prompt("explanation"),
        response=program,
        relative_path="genera_ui/quiz_without_key.txt",
        directory=tmp_path,
    )
    write_fixture(
        system_prompt=ui_repair_system(),
        user_prompt=build_repair_prompt(
            previous=program, errors=errors, ui_format="explanation"
        ),
        response=packaged("genera_ui/openui_mixed.txt"),
        relative_path="genera_ui/openui_mixed.txt",
        directory=tmp_path,
    )

    final = await run_graph(make_request_state())

    assert final["current_step"] == "persist_render"
    assert harness.render().answer_key["q1"]["correct"] == 1


# --------------------------------------------------------------------------------------
# The fallback
# --------------------------------------------------------------------------------------
async def test_two_invalid_attempts_fall_back_to_the_seed_lesson(
    harness: Harness, tmp_path: Path
) -> None:
    """§9.3 level 4: without usable generation the course keeps working in degraded v1 mode."""
    invalid = packaged("genera_ui/invalid_unknown_component.txt")
    errors = validation_errors_of(invalid)
    write_fixture(
        system_prompt=ui_generator_system(),
        user_prompt=canonical_ui_prompt("explanation"),
        response=invalid,
        relative_path="genera_ui/invalid_unknown_component.txt",
        directory=tmp_path,
    )
    write_fixture(
        system_prompt=ui_repair_system(),
        user_prompt=build_repair_prompt(
            previous=invalid, errors=errors, ui_format="explanation"
        ),
        response=invalid,
        relative_path="genera_ui/invalid_again.txt",
        directory=tmp_path,
    )

    final = await run_graph(make_request_state())
    render = harness.render()

    assert final["current_step"] == "fallback_seed"
    assert render.status is NodeRenderStatus.FALLBACK
    assert render.answer_key == {}
    types = [c["type"] for c in render.ui_spec["components"]]
    assert types[0] == "Stack" and "Markdown" in types
    assert "30 dias naturales" in render.dialect
    # The provenance constraint of §3.4 holds for a fallback row too.
    assert render.dialect and render.catalog_version and render.library_version
    assert "ui_done" in harness.event_types()


async def test_a_failure_with_no_llm_at_all_still_serves_the_seed(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The offline / no-API-key case: ``genera_ui`` explodes, the learner still gets a lesson."""

    def exploding_llm(org_settings, tier):
        raise RuntimeError("no LLM configured")

    monkeypatch.setattr(runtime_nodes, "tier_llm", exploding_llm)

    final = await run_graph(make_request_state())
    render = harness.render()

    assert final["current_step"] == "fallback_seed"
    assert render.status is NodeRenderStatus.FALLBACK
    # The wrapper announced the failure with the contract §9.2 fixes.
    failures = harness.payloads("error")
    assert failures and failures[0]["fallback"] is True
    assert failures[0]["step"] == "decide_formato"


async def test_load_context_failing_says_so_once_and_promises_nothing(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no row claimed there is nothing to serve, so ``fallback`` must be **false**:
    telling the client to re-request would loop it against a blank screen."""
    monkeypatch.setattr(runtime_nodes, "async_session_factory", ExplodingSessionFactory())
    monkeypatch.setattr(runtime_errors, "async_session_factory", ExplodingSessionFactory())

    final = await run_graph(make_request_state())

    assert final["current_step"] == "failed"
    assert "RuntimeError" in final["error"]
    assert harness.session.renders == []
    flags = [payload["fallback"] for payload in harness.payloads("error")]
    assert flags == [True, False]


# --------------------------------------------------------------------------------------
# The gate: currently bypassed, so mastered nodes cost exactly what fresh ones do
# --------------------------------------------------------------------------------------
async def test_a_mastered_node_is_generated_anyway_because_the_gate_is_bypassed(
    harness: Harness,
) -> None:
    """The gate of §2/§7.3 is **off** since ``b9a06c3`` ("bypass pre-assessment gate",
    2026-07-28): ``probe_gate`` hardcodes ``mastered = False`` and the frontend starts every
    node in the content phase, so there is no probe left to reach ``mastered`` before the
    lesson exists either.

    This test used to assert the opposite — a mastered node skipped without a single token —
    and was one of the six that stopped running when the suite needed ``--ignore``. It is
    not restored to the old assertion, because turning the gate back on is a product
    decision that has to be taken on both sides at once (see the note on ``probe_gate``).
    What it pins instead is the price of the bypass, stated out loud: the two LLM calls that
    §2 promised a returning learner would not pay.
    """
    harness.session.node_state = make_state(NodeState.MASTERED)

    final = await run_graph(make_request_state())

    assert final["mastered"] is False
    assert final["current_step"] == "persist_render"
    assert harness.payloads("node_skipped") == []
    # The cost of the bypass, in the currency §2 was written in.
    assert [row.use_case for row in harness.session.usage] == ["decide_formato", "genera_ui"]
    assert harness.render().status is NodeRenderStatus.READY


def test_the_skip_route_is_still_wired_for_the_day_the_gate_comes_back() -> None:
    """``probe_gate`` is bypassed; the router it feeds is not modified.

    Worth its own assertion precisely because the test above no longer exercises the skip
    branch: without this, re-enabling the gate would be a one-line change into code with no
    coverage at all.
    """
    assert route_after_gate({"mastered": True}) == "skip"
    assert route_after_gate({"mastered": False}) == "generate"
    assert route_after_gate({"mastered": True, "error": "boom"}) == "error"


async def test_skip_node_hands_the_claimed_key_back_instead_of_parking_it(
    harness: Harness,
) -> None:
    """The other half of the dormant skip path: ``skip_node`` released the row it claimed.

    Driven directly rather than through the graph, because the bypassed gate can no longer
    route to it. Leaving a ``generating`` row behind would read like a crashed worker for
    the cheapest outcome the pipeline has.
    """
    claimed = await run_graph(make_request_state())
    render_id = claimed["render_id"]
    harness.render().status = NodeRenderStatus.GENERATING

    result = await runtime_nodes.skip_node(
        make_request_state(render_id=render_id)  # type: ignore[arg-type]
    )

    assert result["current_step"] == "skip_node"
    assert harness.payloads("node_skipped") == [{"reason": "mastered"}]
    assert harness.render().status is NodeRenderStatus.PENDING
    assert "already mastered" in (harness.render().error_message or "")


# --------------------------------------------------------------------------------------
# §6.4 the calibration period, as a hard rule
# --------------------------------------------------------------------------------------
async def test_during_calibration_decide_formato_never_calls_the_model(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The proof is the absence of a fixture: the ``decide_formato`` recording is deleted, so
    a call would raise ``LLMError``. The graph must still render, using
    ``node.default_ui_format`` (§6.4).
    """
    harness.session.profile = make_profile(nodes_completed=2)
    (tmp_path / "decide_formato" / "explanation.json").unlink()

    final = await run_graph(make_request_state())

    assert final["error"] is None
    assert final["current_step"] == "persist_render"
    assert final["ui_format"] == "explanation"  # node.default_ui_format
    assert "calibracion" in final["format_rationale"]
    # No decide_formato row in the usage log: no call was made.
    assert [row.use_case for row in harness.session.usage] == ["genera_ui"]


async def test_the_default_ui_format_column_is_what_calibration_reads(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """§3.2: the column exists precisely so §6.4's instruction has somewhere to read from."""
    harness.session.profile = make_profile(nodes_completed=0)
    harness.session.node = make_node(default_ui_format=UiFormat.MIXED)
    (tmp_path / "decide_formato" / "explanation.json").unlink()
    write_fixture(
        system_prompt=ui_generator_system(),
        user_prompt=canonical_ui_prompt("mixed"),
        response=packaged("genera_ui/openui_mixed.txt"),
        relative_path="genera_ui/openui_mixed.txt",
        directory=tmp_path,
    )

    final = await run_graph(make_request_state())

    assert final["ui_format"] == "mixed"
    # `mixed` is a HEAVY format, so the router moved the tier even without an LLM decision.
    assert final["tier"] == "heavy"
    assert harness.render().tier == "heavy"


def test_during_calibration_the_vector_bucket_stays_out_of_the_key() -> None:
    """§6.4 second row: the events accumulate and are **not** used.

    Two learners with wildly different interaction histories share a key while either of them
    is still calibrating, and the key only starts to diverge once they are out of it.
    """
    node, course = make_node(), make_course()
    calibrating = build_render_key(
        node=node,
        course=course,
        profile=make_profile(nodes_completed=2),
        node_state=make_state(),
        model_key=FIXTURE_MODEL_KEY,
    )
    assert calibrating.calibrating is True
    assert calibrating.vector_bucket == ""

    other_history = make_profile(nodes_completed=2)
    other_history.format_vector = {
        "texto": 0.1,
        "ejercicio": 0.9,
        "codigo": 0.0,
        "dato": 0.0,
    }
    same_key = build_render_key(
        node=node,
        course=course,
        profile=other_history,
        node_state=make_state(),
        model_key=FIXTURE_MODEL_KEY,
    )
    assert same_key.cache_key == calibrating.cache_key

    out_of_calibration = build_render_key(
        node=node,
        course=course,
        profile=make_profile(nodes_completed=3),
        node_state=make_state(),
        model_key=FIXTURE_MODEL_KEY,
    )
    assert out_of_calibration.calibrating is False
    assert out_of_calibration.vector_bucket == CANON_BUCKET
    assert out_of_calibration.cache_key != calibrating.cache_key


def test_longitudinal_support_changes_next_prompt_band_without_mutating_state() -> None:
    state = {
        "scaffold_band": "advanced",
        "longitudinal_history": {
            "applied": True,
            "support_level": "worked-example",
        },
    }
    before = {
        "scaffold_band": state["scaffold_band"],
        "longitudinal_history": dict(state["longitudinal_history"]),
    }

    assert runtime_nodes._effective_scaffold_band(state) == "novice"
    assert state == before

    state["longitudinal_history"]["applied"] = False
    assert runtime_nodes._effective_scaffold_band(state) == "advanced"


# --------------------------------------------------------------------------------------
# The cache (§9.3 level 1)
# --------------------------------------------------------------------------------------
def test_two_learners_of_the_same_bucket_share_a_key_and_a_different_role_does_not() -> None:
    node, course = make_node(), make_course()
    first = build_render_key(
        node=node,
        course=course,
        profile=make_profile(user_id=USER_ID),
        node_state=make_state(),
        model_key=FIXTURE_MODEL_KEY,
    )
    second = build_render_key(
        node=node,
        course=course,
        profile=make_profile(user_id=OTHER_USER_ID),
        node_state=make_state(),
        model_key=FIXTURE_MODEL_KEY,
    )
    assert first.cache_key == second.cache_key, "user_id must not be in the key (§9.3)"

    manager = make_profile()
    manager.role_title = "Encargado de turno"
    framed_differently = build_render_key(
        node=node,
        course=course,
        profile=manager,
        node_state=make_state(),
        model_key=FIXTURE_MODEL_KEY,
    )
    assert framed_differently.cache_key != first.cache_key
    assert framed_differently.role_bucket == "encargado-de-turno"


async def test_the_second_learner_of_a_bucket_never_starts_a_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operational meaning of the cache: ``cached=True`` and **no graph spawned**.

    Asserted through ``spawn_node_render``, because "0 tokens" is not a property of the LLM
    client — it is the property that the pipeline that would call it never runs.
    """
    from src.services import node_render_service
    from src.services.node_render_service import NodeRenderService

    monkeypatch.setattr(settings, "LLM_MODEL", FIXTURE_MODEL)
    monkeypatch.setattr(settings, "LLM_RUNTIME_FAST_MODEL", None)
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", None)

    node = make_node(reviewed_at=_now())
    course = make_course()
    first_user = FakeUser(id=USER_ID, org_id=ORG_ID)
    second_user = FakeUser(id=OTHER_USER_ID, org_id=ORG_ID)

    session = FakeSession(
        node=node,
        course=course,
        user=first_user,
        profile=make_profile(user_id=USER_ID),
        node_state=None,
    )

    spawned: list[dict] = []

    def fake_spawn(state):
        spawned.append(dict(state))
        return None

    monkeypatch.setattr(
        "src.agents.runtime.runner.spawn_node_render", fake_spawn
    )
    node_render_service._INFLIGHT.clear()

    service = NodeRenderService(session)
    first = await service.request_render(user=first_user, node=node, course=course)
    assert first.cached is False
    assert len(spawned) == 1
    cache_key = spawned[0]["cache_key"]

    # The first render finishes and lands in the shared row.
    ready = NodeRender(
        org_id=ORG_ID,
        node_id=NODE_ID,
        cache_key=cache_key,
        ui_format=UiFormat.EXPLANATION,
        ui_spec={"components": []},
        answer_key={},
        dialect='root = Stack([], "md")\n',
        catalog_version="skillnet-ui/1+abc",
        library_version="@openuidev/lang-core@0.2.10",
        backend="openui",
        model=FIXTURE_MODEL,
        tier="fast",
        status=NodeRenderStatus.READY,
        generated_by=USER_ID,
    )
    ready.id = uuid.uuid4()
    ready.is_preview = False
    session.renders.append(ready)
    node_render_service._INFLIGHT.clear()

    # Second learner, same declared bucket, brand-new state row.
    session.user = second_user
    session.profile = make_profile(user_id=OTHER_USER_ID)
    second = await service.request_render(user=second_user, node=node, course=course)

    assert second.cached is True
    assert second.render_id == ready.id
    assert second.request_id == ""
    assert len(spawned) == 1, "the cache hit must not start a second generation"


async def test_force_regenerates_instead_of_returning_the_cached_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"Actualizar esta leccion" (§5.5) has to *cost* something, or it is decoration.

    Nothing in the ``cache_key`` moves when the button is pressed — ``mastery`` is excluded
    by design and ``scaffold_band`` was frozen when the probe closed — so the recomputed key
    is the same key, and a cache read with it hands back the very render the learner asked
    to replace. This asserts the two halves of the fix together: a second generation *is*
    started, and the row the rest of the bucket is reading survives untouched.
    """
    from src.services import node_render_service
    from src.services.node_render_service import NodeRenderService

    monkeypatch.setattr(settings, "LLM_MODEL", FIXTURE_MODEL)
    monkeypatch.setattr(settings, "LLM_RUNTIME_FAST_MODEL", None)
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", None)

    node = make_node(reviewed_at=_now())
    course = make_course()
    user = FakeUser(id=USER_ID, org_id=ORG_ID)
    session = FakeSession(
        node=node,
        course=course,
        user=user,
        profile=make_profile(user_id=USER_ID),
        node_state=None,
    )

    spawned: list[dict] = []
    monkeypatch.setattr(
        "src.agents.runtime.runner.spawn_node_render",
        lambda state: spawned.append(dict(state)),
    )
    node_render_service._INFLIGHT.clear()

    service = NodeRenderService(session)
    first = await service.request_render(user=user, node=node, course=course)
    assert first.cached is False
    cache_key = spawned[0]["cache_key"]

    ready = NodeRender(
        org_id=ORG_ID,
        node_id=NODE_ID,
        cache_key=cache_key,
        ui_format=UiFormat.EXPLANATION,
        ui_spec={"components": []},
        answer_key={},
        dialect='root = Stack([], "md")\n',
        catalog_version="skillnet-ui/1+abc",
        library_version="@openuidev/lang-core@0.2.10",
        backend="openui",
        model=FIXTURE_MODEL,
        tier="fast",
        status=NodeRenderStatus.READY,
        generated_by=USER_ID,
    )
    ready.id = uuid.uuid4()
    ready.is_preview = False
    session.renders.append(ready)
    node_render_service._INFLIGHT.clear()

    # Without the force, the same request is the cache hit that pins the shared row.
    cached = await service.request_render(user=user, node=node, course=course)
    assert cached.cached is True
    assert cached.render_id == ready.id
    assert len(spawned) == 1

    forced = await service.request_render(
        user=user, node=node, course=course, force=True
    )

    assert forced.cached is False, "force must not answer from the cache"
    assert forced.request_id != ""
    assert len(spawned) == 2, "force must start a second generation"

    refreshed_key = spawned[1]["cache_key"]
    assert refreshed_key.startswith("refresh:")
    assert refreshed_key != cache_key, (
        "reusing the key would make `claim` return the served row and the graph would "
        "overwrite what the rest of the bucket has open"
    )
    # The previous render is still there, so `GET /nodes/{id}/renders` keeps telling the
    # truth about what this learner was served.
    assert ready in session.renders
    assert ready.status is NodeRenderStatus.READY
    assert ready.dialect == 'root = Stack([], "md")\n'

    # Two refreshes are two rows, never a collision on the globally UNIQUE key.
    await service.request_render(user=user, node=node, course=course, force=True)
    assert spawned[2]["cache_key"] != refreshed_key


async def test_force_on_a_node_with_nothing_cached_keeps_the_shared_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The salt is a collision fix, not a policy: with no row under the base key there is
    nothing to collide with, and salting anyway would quietly opt this learner out of the
    shared cache for the rest of the node's life."""
    from src.services import node_render_service
    from src.services.node_render_service import NodeRenderService

    monkeypatch.setattr(settings, "LLM_MODEL", FIXTURE_MODEL)
    monkeypatch.setattr(settings, "LLM_RUNTIME_FAST_MODEL", None)
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", None)

    node = make_node(reviewed_at=_now())
    course = make_course()
    user = FakeUser(id=USER_ID, org_id=ORG_ID)
    session = FakeSession(
        node=node, course=course, user=user,
        profile=make_profile(user_id=USER_ID), node_state=None,
    )
    spawned: list[dict] = []
    monkeypatch.setattr(
        "src.agents.runtime.runner.spawn_node_render",
        lambda state: spawned.append(dict(state)),
    )
    node_render_service._INFLIGHT.clear()

    forced = await NodeRenderService(session).request_render(
        user=user, node=node, course=course, force=True
    )
    assert forced.cached is False
    assert not spawned[0]["cache_key"].startswith("refresh:")


async def test_a_preview_is_salted_out_of_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§11.3: a preview is persisted for review and excluded from the cache, so it cannot be
    served to an employee of the same bucket. ``cache_key`` is globally ``UNIQUE``, so the
    exclusion has to be a different key, not a filtered lookup."""
    node = make_node()
    course = make_course()
    profile = make_profile()
    plain = build_render_key(
        node=node, course=course, profile=profile, node_state=make_state(),
        model_key=FIXTURE_MODEL_KEY,
    )
    preview = build_render_key(
        node=node, course=course, profile=profile, node_state=make_state(),
        model_key=FIXTURE_MODEL_KEY, is_preview=True,
    )
    another_preview = build_render_key(
        node=node, course=course, profile=profile, node_state=make_state(),
        model_key=FIXTURE_MODEL_KEY, is_preview=True,
    )
    assert preview.cache_key != plain.cache_key
    assert preview.cache_key.startswith("preview:")
    assert preview.cache_key != another_preview.cache_key, "two previews must not collide"


# --------------------------------------------------------------------------------------
# Cancellation (§9.1)
# --------------------------------------------------------------------------------------
async def test_cancelling_an_in_flight_render_cancels_its_task() -> None:
    from src.services import node_render_service
    from src.services.node_render_service import (
        InFlight,
        NodeRenderService,
        in_flight_for,
        register_in_flight,
    )

    node_render_service._INFLIGHT.clear()
    started = asyncio.Event()

    async def long_render() -> None:
        started.set()
        await asyncio.sleep(30)

    task = asyncio.create_task(long_render())
    register_in_flight(
        InFlight(request_id="req-x", user_id=USER_ID, node_id=NODE_ID, task=task)
    )
    await started.wait()

    assert in_flight_for(USER_ID, NODE_ID) is not None
    assert NodeRenderService.cancel(USER_ID, NODE_ID) is True
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    assert in_flight_for(USER_ID, NODE_ID) is None
    # Cancelling nothing is not an error, it is the common case.
    assert NodeRenderService.cancel(USER_ID, NODE_ID) is False


async def test_the_node_wrapper_never_swallows_a_cancellation() -> None:
    """A cancelled render is the designed outcome of §9.1, not a failure. Swallowing it would
    publish a phantom ``error`` event and report success for work that did not happen."""
    from src.agents.runtime.errors import runtime_node_error_wrapper

    @runtime_node_error_wrapper("genera_ui")
    async def cancelled_node(state):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await cancelled_node({"request_id": "req-y"})


# --------------------------------------------------------------------------------------
# The pure pieces the graph depends on
# --------------------------------------------------------------------------------------
def test_split_answer_key_keeps_the_braces_away_from_the_gate() -> None:
    program, key = split_answer_key(packaged("genera_ui/openui_exercise.txt"))
    assert "{" not in program
    assert key["q1"]["correct"] == 1

    # No sentinel: everything is program and there is no key.
    plain = packaged("genera_ui/openui_explanation.txt")
    assert split_answer_key(plain) == (plain, {})


def test_a_broken_answer_key_json_is_not_a_crash() -> None:
    raw = f'root = Stack([], "md")\n{ANSWER_KEY_SENTINEL}\n{{"q1": '
    program, key = split_answer_key(raw)
    assert program.strip() == 'root = Stack([], "md")'
    assert key == {}


def test_missing_and_invented_answer_keys_are_both_handled() -> None:
    program, key = split_answer_key(packaged("genera_ui/openui_exercise.txt"))
    spec = get_render_backend("openui").parse(program, ui_format="exercise")

    assert missing_answer_keys(spec, key) == []
    assert missing_answer_keys(spec, {}) and "q1" in missing_answer_keys(spec, {})[0]
    # An entry with no solution at all is as good as absent: it would grade 0.0 forever.
    assert missing_answer_keys(spec, {"q1": {"explanation": "porque"}})
    # And an entry for an item the model never emitted is dropped.
    pruned = prune_answer_key(spec, {**key, "ghost": {"correct": 0}})
    assert set(pruned) == {"q1"}


def test_a_missing_key_and_a_misaddressed_one_get_different_remedies() -> None:
    """Two different mistakes, measured on 2026-07-27, that used to get one complaint.

    The key was *absent* on ``higiene-alimentaria`` and ``alergenos-hosteleria``, and
    *present but indexed by the question text* on ``atencion-reclamaciones``. "No llega su
    solucion" is true of both and tells neither of them what to change, and the repair
    loop replays it verbatim.
    """
    program, _ = split_answer_key(packaged("genera_ui/openui_exercise.txt"))
    spec = get_render_backend("openui").parse(program, ui_format="exercise")

    absent = missing_answer_keys(spec, {})[0]
    assert "No has escrito el bloque" in absent
    assert ANSWER_KEY_SENTINEL in absent
    assert '"q1"' in absent  # the id it has to use, spelled out

    misaddressed = missing_answer_keys(
        spec, {"Un cliente vuelve el dia 32. Que haces?": {"correct": 0}}
    )[0]
    assert "indexa por" in misaddressed
    assert "PRIMER argumento" in misaddressed
    assert "No has escrito el bloque" not in misaddressed


def test_the_user_prompt_never_contradicts_the_answer_key_protocol() -> None:
    """``atencion-reclamaciones`` r2 obeyed "solo con el programa" literally and smuggled
    the key in as ``clave = {...}``, which the gate then refused for the braces. The
    closing line is the last instruction the model reads; it may not fight the first."""
    system = ui_generator_system()
    assert ANSWER_KEY_SENTINEL in system

    for ui_format in ("exercise", "mixed"):
        prompt = build_ui_prompt(title="T", summary="S", ui_format=ui_format)
        assert ANSWER_KEY_SENTINEL in prompt, ui_format
        assert "Responde solo con el programa." not in prompt, ui_format

    for ui_format in ("explanation", "chart"):
        prompt = build_ui_prompt(title="T", summary="S", ui_format=ui_format)
        assert prompt.rstrip().endswith("Responde solo con el programa."), ui_format


def test_the_repair_prompt_closes_the_same_way_the_generation_one_does() -> None:
    """The repair turn had the contradiction too, including on the turn whose only
    complaint was a missing key: "arregla la clave" followed by "solo el programa"."""
    errors = ["QuizItem 'q1' tiene enunciado pero no llega su solucion"]
    for ui_format in ("exercise", "mixed"):
        prompt = build_repair_prompt(previous="x", errors=errors, ui_format=ui_format)
        assert ANSWER_KEY_SENTINEL in prompt.rsplit("\n", 1)[-1], ui_format

    plain = build_repair_prompt(previous="x", errors=errors, ui_format="explanation")
    assert plain.rstrip().endswith("Responde solo con el programa.")


def test_no_length_budget_asks_for_more_blocks_than_rule_6_allows() -> None:
    """The prompt asked density 5 for "5-7 bloques" while the validator capped the root
    level at 5. Measured: 2 of the 14 fallbacks of 2026-07-27 were "got 6" and "got 7"."""
    from src.render.spec import MAX_ROOT_CHILDREN

    for density in range(1, 6):
        budget = build_ui_prompt(
            title="T", summary="S", effective_density=density
        )
        asked = [int(n) for n in re.findall(r"\b(\d+)\s*bloques?", budget)]
        assert asked, density
        assert max(asked) <= MAX_ROOT_CHILDREN, (density, asked)


def test_the_fallback_spec_satisfies_the_contract_rules() -> None:
    """A lone ``Markdown`` block cannot be a valid ``explanation`` spec: rule 7 needs a lead
    slot. That is why the fallback is ``Stack([lead, md...])`` and not one component."""
    spec = build_fallback_spec(summary=CANON_SUMMARY, content=SEED_LESSON_CONTENT)

    assert spec.format == "explanation"
    assert spec.root == "root"
    first = spec.by_id[spec.by_id["root"].children[0]]
    assert first.type == "TextContent" and first.props["variant"] == "lead"
    assert "Markdown" in spec.types
    # Serializable, and the serialization survives the gate on the way out.
    program = get_render_backend("openui").serialize(spec)
    assert "Markdown(" in program


def test_a_long_seed_lesson_is_split_instead_of_breaking_the_line_cap() -> None:
    """One component is one line and ``MAX_LINE_BYTES`` is 4096, so a real lesson does not fit
    on one line. Splitting keeps the whole gate applicable."""
    long_content = "\n\n".join(f"Parrafo {i}. " + "texto " * 200 for i in range(20))
    spec = build_fallback_spec(summary=CANON_SUMMARY, content=long_content)

    markdown_blocks = [c for c in spec.components if c.type == "Markdown"]
    assert 1 < len(markdown_blocks) <= runtime_nodes.FALLBACK_MAX_BLOCKS
    assert len(spec.by_id["root"].children) <= 5  # rule 4: root fan-out
    program = get_render_backend("openui").serialize(spec)
    for line in program.splitlines():
        assert len(line.encode("utf-8")) <= 4096


# --------------------------------------------------------------------------------------
# The shipped fixtures really are keyed on the prompts this batch builds
# --------------------------------------------------------------------------------------
def test_the_packaged_fixtures_are_registered_under_the_canonical_keys() -> None:
    """If this fails with a key mismatch, a prompt changed. Re-register the packaged
    fixtures (``register_packaged_fixtures(FIXTURE_DIR)``) — do not weaken the assertion."""
    index = json.loads((FIXTURE_DIR / "index.json").read_text(encoding="utf-8"))

    decide_key = FixtureLLMService.key_for(
        FORMAT_DECIDER_SYSTEM, canonical_format_prompt()
    )
    ui_key = FixtureLLMService.key_for(ui_generator_system(), canonical_ui_prompt())

    assert index[decide_key]["file"] == "decide_formato/explanation.json"
    assert index[decide_key]["use_case"] == "decide_formato"
    assert index[ui_key]["file"] == "genera_ui/openui_explanation.txt"
    assert index[ui_key]["use_case"] == "genera_ui"


def test_the_ui_generator_prompt_is_the_generated_artefact_not_a_copy() -> None:
    """§5.4: the dialect is taught by ``library.prompt()``. Hand-copying the signatures is the
    drift ``tests/test_render_prompt_artifact.py`` exists to catch, so this asserts the prompt
    really is the artefact plus the answer-key protocol — and that no reactive syntax is
    taught anywhere in it."""
    from src.render.prompt import render_prompt

    system = ui_generator_system()
    assert system.startswith(render_prompt().rstrip("\n")[:200])
    assert ANSWER_KEY_SENTINEL in system
    for forbidden in ("$state", "Query(", "Mutation(", "refreshInterval", "@ToAssistant"):
        assert forbidden not in system.replace("ni Query(...)", "").replace(
            "ni Mutation(...)", ""
        )


#: The corrected halves of the MAL/BIEN block in ``_UI_REPAIR_HEADER``. Every one of them
#: has to be a program the validator accepts, or the repair turn is teaching the mistake
#: it is trying to fix.
_REPAIR_GOOD = (
    'root = Stack([intro], "md")',
    'aviso = Callout("info", "Dijo \\"no\\" y colgo.")',
    'conclusion = TextContent("Aquí sí van tildes.", "body")',
    'root = Stack([TextContent("Hola.", "lead")], "md")',
)

#: The wrong halves. Each is a real failure mode measured against a real model, and each
#: must still be rejected — a counterexample that quietly became legal would be worse than
#: no counterexample. That is not hypothetical: "a call split over several lines" was in
#: this tuple until 2026-07-27, and it became legal the day the parser started splitting
#: statements at bracket depth 0 the way lang-core does.
_REPAIR_BAD = (
    'root = Stack(children = [intro], gap = "md")',
    'aviso = Callout("info", "Dijo "no" y colgo.")',
    'clave = {"q1": {"correct": 1}}',
)


def test_the_repair_prompt_pairs_every_mistake_with_its_correction() -> None:
    """A named counterexample beats a rule in prose for a small model (§4.2).

    Counted exactly rather than as ``>= 1``: an unpaired MAL is a counterexample that
    teaches the mistake and never shows the fix, and it is the kind of thing that survives
    a careless edit. The repair system prompt is the header **plus the whole generator
    tail**, so the total spans both — four in the header (the three of ``_REPAIR_BAD`` and
    the accented id), one in the tail (SkillNet 17's bare array declaration), and one in
    the BeforeAfter worked example (``"MAL"`` / ``"BIEN"`` as labels, not counterexamples).
    """
    system = ui_repair_system()
    assert system.count("MAL") == len(_REPAIR_BAD) + 3
    assert system.count("BIEN") == system.count("MAL")
    assert "argumentos con nombre" in system
    assert "tilde en el id" in system
    assert "la clave como declaracion" in system


def test_the_generator_prompt_forbids_the_two_habits_the_baseline_measured() -> None:
    """SkillNet 17 and 18, and that they are not merely asserted but demonstrated.

    Both come from the 30-render baseline of 2026-07-28: three rejections of
    ``expected a component name after '=', found '['`` (a bare ``opciones = [...]``
    declaration) and five of ``duplicate component id``.
    """
    backend = get_render_backend("openui")
    system = ui_generator_system()

    assert 'opciones = ["A", "B"]' in system
    assert "Cada id se declara UNA sola vez" in system

    # The MAL half really is refused...
    with pytest.raises(RenderError):
        canonicalize(
            'root = Stack([q1], "md")\n'
            'opciones = ["A", "B"]\n'
            'q1 = QuizItem("q1", "test", "apply", "Cual?", opciones)\n',
            ui_format="exercise",
            backend=backend,
        )
    # ...and the BIEN half really is accepted.
    spec = backend.parse(
        'root = Stack([q1], "md")\n'
        'q1 = QuizItem("q1", "test", "apply", "Cual?", ["A", "B"])\n',
        ui_format="exercise",
    )
    assert spec.root == "root"


def test_the_node_criticality_never_travels_as_its_enum_token() -> None:
    """The largest single failure class of the 2026-07-28 baseline, and its cause.

    Eight renders were refused for ``prop 'tone' must be one of: info, warn, success``
    having received ``'critical'``, ``'recommended'`` or ``'contextual'`` — the
    ``NodeCriticality`` values, which the prompt was printing verbatim on a line reading
    ``- Criticidad: critical``. The model copied the only enum-shaped word it could see
    into the only enum slot it had. ``SkillNet 16`` forbade it in words and did not stop
    it; deleting the token did.
    """
    for criticality in ("critical", "recommended", "contextual"):
        prompt = build_ui_prompt(
            title="T", summary="S", criticality=criticality, ui_format="explanation"
        )
        assert f"Criticidad: {criticality}" not in prompt
        assert criticality not in prompt

    # It still travels — as behaviour, which is the whole point of removing the label.
    critical = build_ui_prompt(
        title="T", summary="S", criticality="critical", ui_format="explanation"
    )
    assert "cumplimiento obligatorio" in critical
    assert 'Callout("warn"' in critical


def test_the_repair_prompt_no_longer_teaches_the_one_line_rule() -> None:
    """It was never OpenUI Lang's rule, and it is not this parser's either since
    ``src/render/lines.py``. Teaching it burns the single retry on a reformat."""
    system = ui_repair_system()
    assert "partida en varias lineas" not in system
    assert "intro = TextContent(\n" not in system
    # And the model is told plainly that the construction is fine.
    assert "mientras haya un corchete abierto" in system


def test_every_corrected_example_in_the_repair_prompt_is_valid_dialect() -> None:
    system = ui_repair_system()
    backend = get_render_backend("openui")
    for good in _REPAIR_GOOD:
        assert good in system, good
    assert (
        backend.parse(
            f'{_REPAIR_GOOD[0]}\nintro = TextContent("Hola.", "lead")\n'
        ).root
        == "root"
    )
    assert backend.parse(f'root = Stack([aviso], "md")\n{_REPAIR_GOOD[1]}\n').root == "root"
    assert (
        backend.parse(
            f'root = Stack([intro, conclusion], "md")\n'
            f'intro = TextContent("Hola.", "lead")\n{_REPAIR_GOOD[2]}\n'
        ).root
        == "root"
    )
    # The inline form, which the parser accepts since 2026-07-27 and the prompt says so.
    assert len(backend.parse(f"{_REPAIR_GOOD[3]}\n").components) == 2


def test_every_wrong_example_in_the_repair_prompt_is_still_rejected() -> None:
    backend = get_render_backend("openui")
    for bad in _REPAIR_BAD:
        assert bad in ui_repair_system(), bad
        with pytest.raises(RenderError):
            canonicalize(
                f'{bad}\nintro = TextContent("H.", "lead")\n',
                backend=backend,
            )


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
