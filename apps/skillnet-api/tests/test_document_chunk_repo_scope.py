"""An empty document filter must select nothing, not everything (no DB, no network).

The regression these tests exist for: ``services/media/grounding`` asks for the documents
behind one course, a course created from an idea has none, and the resulting ``[]`` was
read by the repository as a falsy "no filter". The ``WHERE`` was dropped and the search
widened to the whole organization, so an artifact for one course could be built — with
citations — out of another course's manual.
"""

import uuid
from types import SimpleNamespace

import pytest

from src.repositories.document_chunk_repo import DocumentChunkRepository

ORG_ID = uuid.uuid4()
EMBEDDING = [0.1, 0.2, 0.3, 0.4]


class _Result:
    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    def all(self) -> list:
        return list(self._rows)


class _OrgWideSession:
    """Answers *any* query with a chunk from an unrelated document.

    Deliberately not an empty stub: the bug was a query that ran and came back with the
    organization's other material, so the fake has to be able to reproduce that.
    """

    def __init__(self) -> None:
        self.executed = 0

    async def execute(self, statement):  # noqa: ANN001 - a stub, shape is the point
        self.executed += 1
        return _Result(
            [
                SimpleNamespace(
                    id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    content="Manual de otro curso.",
                    chunk_metadata={"heading": "Otra cosa"},
                    document_title="Manual ajeno",
                    similarity=0.9,
                    rank=0.9,
                )
            ]
        )


@pytest.fixture
def session() -> _OrgWideSession:
    return _OrgWideSession()


async def test_empty_document_filter_returns_no_chunks_from_vector_search(
    session: _OrgWideSession,
) -> None:
    repo = DocumentChunkRepository(session)

    rows = await repo.similarity_search(
        org_id=ORG_ID, query_embedding=EMBEDDING, document_ids=[]
    )

    assert rows == []
    assert session.executed == 0


async def test_empty_document_filter_returns_no_chunks_from_lexical_search(
    session: _OrgWideSession,
) -> None:
    repo = DocumentChunkRepository(session)

    rows = await repo.search_chunks_fts(
        org_id=ORG_ID, terms=["boxeo", "guardia"], document_ids=[]
    )

    assert rows == []
    assert session.executed == 0


async def test_empty_document_filter_returns_no_chunks_from_heading_search(
    session: _OrgWideSession,
) -> None:
    repo = DocumentChunkRepository(session)

    rows = await repo.similarity_search_by_headings(
        org_id=ORG_ID, query_embedding=EMBEDDING, document_ids=[], headings=["La guardia"]
    )

    assert rows == []
    assert session.executed == 0


async def test_none_document_filter_still_searches_the_whole_org(
    session: _OrgWideSession,
) -> None:
    """The other half of the contract: ``None`` means "no filter" and must keep working."""
    repo = DocumentChunkRepository(session)

    rows = await repo.similarity_search(
        org_id=ORG_ID, query_embedding=EMBEDDING, document_ids=None
    )

    assert len(rows) == 1
    assert rows[0]["document_title"] == "Manual ajeno"
    assert session.executed == 1
