"""Unit tests for the media grounding-context builder (no DB, no network).

The bundle assembly is pure and tested directly; the ladder in ``build_grounding_bundle``
is tested against a stub session that answers by table name, because the decisions worth
protecting there are about *which table is reached at all*.
"""

import uuid
from types import SimpleNamespace

from src.services.media.grounding import (
    GroundedBundle,
    GroundedPassage,
    build_grounding_bundle,
    bundle_from_chunks,
    bundle_from_course_material,
    bundle_from_documents,
)


def _chunk(
    *,
    content: str,
    document_id: uuid.UUID,
    title: str = "Manual Alergenos",
    heading: str = "Los catorce alergenos",
    page: int = 2,
    position: int = 0,
    similarity: float = 0.9,
) -> dict:
    return {
        "chunk_id": uuid.uuid4(),
        "document_id": document_id,
        "content": content,
        "document_title": title,
        "similarity": similarity,
        "metadata": {"heading": heading, "page_start": page, "position": position},
    }


def test_chunk_bundle_assigns_stable_sequential_citation_ids() -> None:
    doc = uuid.uuid4()
    rows = [
        _chunk(content="El gluten es un alergeno.", document_id=doc, position=0),
        _chunk(content="El apio tambien.", document_id=doc, position=1, heading="Apio"),
    ]

    bundle = bundle_from_chunks(rows, mode="chunks")

    assert bundle.mode == "chunks"
    assert bundle.citation_ids() == ["c1", "c2"]
    # Ordered by document then in-document position (reused from retrieval.order_chunks).
    assert bundle.passages[0].text == "El gluten es un alergeno."
    assert bundle.passages[1].text == "El apio tambien."


def test_chunk_bundle_dedupes_keeping_highest_score() -> None:
    doc = uuid.uuid4()
    shared = "El gluten es un alergeno de declaracion obligatoria."
    rows = [
        _chunk(content=shared, document_id=doc, similarity=0.4),
        _chunk(content=shared, document_id=doc, similarity=0.95),
    ]

    bundle = bundle_from_chunks(rows, mode="chunks")

    # Dedup (from retrieval.dedupe_chunks) collapses to one, and ids stay contiguous.
    assert len(bundle.passages) == 1
    assert bundle.citation_ids() == ["c1"]


def test_prompt_context_carries_citation_markers() -> None:
    doc = uuid.uuid4()
    bundle = bundle_from_chunks(
        [_chunk(content="El gluten es un alergeno.", document_id=doc)], mode="chunks"
    )

    context = bundle.as_prompt_context()

    assert "[Fuente c1: Manual Alergenos > Los catorce alergenos, pag. 2]" in context
    assert "El gluten es un alergeno." in context


def test_citations_payload_shape() -> None:
    doc = uuid.uuid4()
    bundle = bundle_from_chunks([_chunk(content="x", document_id=doc)], mode="chunks_fts")

    payload = bundle.citations_payload()

    assert payload == [
        {
            "citation_id": "c1",
            "document": "Manual Alergenos",
            "section": "Los catorce alergenos",
            "page": 2,
            "document_id": str(doc),
        }
    ]


def test_document_bundle_marks_whole_document_and_caps_count() -> None:
    documents = [
        {"id": uuid.uuid4(), "title": f"Doc {i}", "full_text": f"cuerpo {i}"}
        for i in range(6)
    ]

    bundle = bundle_from_documents(documents)

    # Capped at _MAX_DOCUMENT_PASSAGES (4), sequential ids, honest "documento completo".
    assert len(bundle.passages) == 4
    assert bundle.mode == "document"
    assert bundle.citation_ids() == ["c1", "c2", "c3", "c4"]
    assert all(p.section == "documento completo" for p in bundle.passages)
    assert all(p.page is None for p in bundle.passages)


def test_document_bundle_skips_empty_full_text() -> None:
    documents = [
        {"id": uuid.uuid4(), "title": "Vacio", "full_text": "   "},
        {"id": uuid.uuid4(), "title": "Lleno", "full_text": "contenido real"},
    ]

    bundle = bundle_from_documents(documents)

    assert len(bundle.passages) == 1
    assert bundle.passages[0].source_title == "Lleno"
    assert bundle.passages[0].citation_id == "c1"


def test_empty_bundle_reports_empty() -> None:
    bundle = GroundedBundle(mode="empty", passages=[])

    assert bundle.is_empty()
    assert bundle.as_prompt_context() == ""
    assert bundle.citations_payload() == []


def test_passage_marker_without_section_or_page() -> None:
    passage = GroundedPassage(citation_id="c1", text="t", source_title="Solo Titulo")

    assert passage.marker() == "[Fuente c1: Solo Titulo]"


# --------------------------------------------------------------------------------------
# The course-material rung: a course created from an idea has no document, and used to
# leave the generator writing "in general" — a boxing course got an infographic titled
# "Claves para una vida saludable". Its own nodes and knowledge packs were in the database.
# --------------------------------------------------------------------------------------
def _node(
    *,
    title: str = "La guardia",
    summary: str = "Como colocar los pies y las manos.",
    outcome: str | None = "Mantener la guardia alta durante un asalto.",
    atoms: list[dict] | None = None,
) -> dict:
    return {
        "title": title,
        "summary": summary,
        "outcome": outcome,
        "atoms": atoms if atoms is not None else [],
    }


def _atom(text: str, *, atom_id: str = "a1", category: str = "must_preserve") -> dict:
    return {"category": category, "atom_id": atom_id, "text": text}


def test_course_material_bundle_uses_pack_atoms() -> None:
    nodes = [
        _node(
            atoms=[
                _atom("El menton va pegado al pecho.", atom_id="a2"),
                _atom("Los codos protegen el higado.", atom_id="a1"),
            ]
        )
    ]

    bundle = bundle_from_course_material(nodes, course_title="Boxeo desde cero")

    assert bundle.mode == "course_pack"
    assert bundle.citation_ids() == ["c1"]
    text = bundle.passages[0].text
    # must_preserve atoms sorted by atom_id, so the ids are the same next time.
    assert text.index("Los codos") < text.index("El menton")
    assert "Objetivo: Mantener la guardia alta" in text


def test_course_material_bundle_without_packs_is_honest_about_it() -> None:
    bundle = bundle_from_course_material([_node()], course_title="Boxeo desde cero")

    assert bundle.mode == "course_outline"
    assert "Como colocar los pies" in bundle.passages[0].text


def test_course_material_one_node_without_pack_downgrades_the_whole_bundle() -> None:
    nodes = [
        _node(atoms=[_atom("El menton va pegado al pecho.")]),
        _node(title="El jab", summary="El golpe recto de la mano adelantada."),
    ]

    bundle = bundle_from_course_material(nodes, course_title="Boxeo desde cero")

    # The stronger label must not over-promise for a bundle that is partly just titles.
    assert bundle.mode == "course_outline"
    assert bundle.citation_ids() == ["c1", "c2"]


def test_course_material_marker_names_the_course_and_the_node() -> None:
    bundle = bundle_from_course_material([_node()], course_title="Boxeo desde cero")

    marker = bundle.passages[0].marker()

    assert marker == "[Fuente c1: Boxeo desde cero > La guardia]"
    # No document exists behind this passage, and inventing an id would send the citations
    # panel looking for a row that is not there.
    assert bundle.citations_payload()[0]["document_id"] is None


def test_course_material_caps_nodes_and_atoms() -> None:
    nodes = [
        _node(
            title=f"Nodo {index}",
            atoms=[_atom(f"Dato {i}", atom_id=f"a{i:02d}") for i in range(30)],
        )
        for index in range(20)
    ]

    bundle = bundle_from_course_material(nodes, course_title="Boxeo desde cero")

    assert len(bundle.passages) == 8
    assert bundle.passages[0].text.count("- Dato") == 12


def test_course_material_bundle_is_empty_when_there_is_nothing_to_say() -> None:
    bundle = bundle_from_course_material(
        [{"title": "", "summary": "", "outcome": "", "atoms": []}],
        course_title="Boxeo desde cero",
    )

    assert bundle.mode == "empty"
    assert bundle.is_empty()


# --------------------------------------------------------------------------------------
# The ladder itself. The session is a stub that answers by table name, so these still run
# without a database — but they exercise the real ``build_grounding_bundle``, which is
# where the scoping decisions live.
# --------------------------------------------------------------------------------------
class _Result:
    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    def all(self) -> list:
        return list(self._rows)

    def scalars(self) -> "_Result":
        return self


class _FakeDb:
    """Answers by table name and records which tables were queried.

    ``chunks`` is populated with somebody else's passage on purpose: the failure this
    guards against is a course with no documents reaching ``document_chunks`` at all.
    """

    def __init__(self, *, documents: list, nodes: list, packs: list) -> None:
        self.documents = documents
        self.nodes = nodes
        self.packs = packs
        self.tables: list[str] = []

    async def execute(self, statement):  # noqa: ANN001 - a stub, shape is the point
        sql = str(statement)
        if "node_knowledge_packs" in sql:
            self.tables.append("node_knowledge_packs")
            return _Result(self.packs)
        if "UNION" in sql:
            self.tables.append("document_links")
            return _Result([(document.id,) for document in self.documents])
        if "FROM course_nodes" in sql:
            self.tables.append("course_nodes")
            return _Result(self.nodes)
        if "FROM documents" in sql:
            self.tables.append("documents")
            return _Result(self.documents)
        if "document_chunks" in sql:
            self.tables.append("document_chunks")
            return _Result(
                [
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        document_id=uuid.uuid4(),
                        content="Manual de otro curso.",
                        chunk_metadata={},
                        document_title="Manual ajeno",
                        similarity=0.95,
                        rank=0.95,
                    )
                ]
            )
        raise AssertionError(f"unexpected query: {sql}")


def _orm_node(
    *, course_id: uuid.UUID, org_id: uuid.UUID, title: str, position: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        course_id=course_id,
        org_id=org_id,
        title=title,
        summary=f"Resumen de {title}.",
        outcome=None,
        position=position,
        source_document_id=None,
    )


async def test_course_without_documents_grounds_on_its_own_nodes() -> None:
    org_id = uuid.uuid4()
    course = SimpleNamespace(id=uuid.uuid4(), org_id=org_id, title="Boxeo desde cero")
    node = _orm_node(course_id=course.id, org_id=org_id, title="La guardia")
    db = _FakeDb(
        documents=[],
        nodes=[node],
        packs=[
            SimpleNamespace(
                node_id=node.id,
                atoms=[{"category": "must_preserve", "atom_id": "a1", "text": "Guardia alta."}],
            )
        ],
    )

    bundle = await build_grounding_bundle(db, course=course)

    assert not bundle.is_empty()
    assert bundle.mode == "course_pack"
    assert "Guardia alta." in bundle.as_prompt_context()
    assert bundle.passages[0].source_title == "Boxeo desde cero"
    # The corpusless course never touched the chunk tables, so no other course's manual
    # could have reached it.
    assert "document_chunks" not in db.tables


async def test_node_scope_never_reaches_a_sibling_node() -> None:
    org_id = uuid.uuid4()
    course = SimpleNamespace(id=uuid.uuid4(), org_id=org_id, title="Boxeo desde cero")
    asked = _orm_node(course_id=course.id, org_id=org_id, title="La guardia")
    sibling = _orm_node(course_id=course.id, org_id=org_id, title="El jab", position=1)
    db = _FakeDb(documents=[], nodes=[asked, sibling], packs=[])

    bundle = await build_grounding_bundle(db, course=course, node=asked)

    assert [passage.section for passage in bundle.passages] == ["La guardia"]
    # The node was handed in, so the list of nodes was never queried at all.
    assert "course_nodes" not in db.tables


async def test_node_from_another_course_grounds_on_nothing() -> None:
    org_id = uuid.uuid4()
    course = SimpleNamespace(id=uuid.uuid4(), org_id=org_id, title="Boxeo desde cero")
    intruder = _orm_node(course_id=uuid.uuid4(), org_id=org_id, title="Reposteria")
    db = _FakeDb(documents=[], nodes=[intruder], packs=[])

    bundle = await build_grounding_bundle(db, course=course, node=intruder)

    assert bundle.mode == "empty"
    assert bundle.is_empty()


async def test_course_with_documents_still_grounds_on_its_chunks() -> None:
    """The documentary rungs are unchanged; the new one only runs when they cannot."""
    org_id = uuid.uuid4()
    course = SimpleNamespace(id=uuid.uuid4(), org_id=org_id, title="Alergenos")
    document = SimpleNamespace(
        id=uuid.uuid4(), title="Manual Alergenos", full_text="cuerpo"
    )
    db = _FakeDb(documents=[document], nodes=[], packs=[])

    bundle = await build_grounding_bundle(db, course=course, query="alergenos")

    assert bundle.mode == "chunks_fts"
    assert "document_chunks" in db.tables


async def test_corpusless_course_never_pays_for_an_embedding() -> None:
    """No documents means no chunk to find, so the embedder is not worth calling.

    The bite is narrow on purpose: with the repository's empty-filter guard in place the
    query would have returned nothing anyway. What this protects is the *cost* — and the
    fact that the ladder knows it has no corpus before it starts spending.
    """
    org_id = uuid.uuid4()
    course = SimpleNamespace(id=uuid.uuid4(), org_id=org_id, title="Boxeo desde cero")
    node = _orm_node(course_id=course.id, org_id=org_id, title="La guardia")
    db = _FakeDb(documents=[], nodes=[node], packs=[])

    # A BaseException and not an AssertionError: the vector rung catches ``Exception`` by
    # design (a dead embedder must not cost the bundle), so a plain assert inside the
    # embedder would be swallowed and this test would pass without testing anything.
    class _EmbedderCalled(BaseException):
        pass

    class _ExplodingEmbedder:
        async def embed_query(self, text: str) -> list[float]:
            raise _EmbedderCalled("embedded a query for a course with no documents")

    bundle = await build_grounding_bundle(
        db, course=course, embedding_service=_ExplodingEmbedder()
    )

    assert bundle.mode == "course_outline"
