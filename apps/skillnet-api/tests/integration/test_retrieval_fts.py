"""The lexical rung of the grounding ladder, against a real Postgres.

Needs a live database because the thing under test *is* the SQL: a Spanish ``tsvector``,
``websearch_to_tsquery``, and ``ts_rank_cd``. There is nothing to assert in Python.

Why the rung exists at all, measured on the seeded corpus before it was written: with
``EMBEDDING_MODEL=fixture/local`` every vector is a hashed random unit vector, so for
*"cuales son los 14 alergenos de declaracion obligatoria"* the five nearest chunks scored
0.099 / 0.075 / 0.073 / 0.066 / 0.049 against a floor of 0.25 — and the nearest of them was
about counting the cash float while the allergen manual came last. Zero survived, and the
ladder fell through to pasting whole documents.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable
from typing import TypeVar

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.config import settings
from src.deps.db import async_session_factory, engine
from src.llm.embedding import resolve_embedding_config
from src.llm.fixtures import maybe_fixture_embedder
from src.models import Document, DocumentChunk, Organization
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.services.retrieval import (
    chunk_score,
    ground_question,
    retrieve_context_fts,
)

pytestmark = pytest.mark.integration

T = TypeVar("T")


def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


async def _probe() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


@pytest.fixture(scope="module", autouse=True)
def _database() -> None:
    try:
        _run(_probe())
    except Exception as exc:  # noqa: BLE001 - a missing DB is a skip, not a failure
        pytest.skip(f"No Postgres at DATABASE_URL ({type(exc).__name__}: {exc}).")
    _run(engine.dispose())


@pytest.fixture(autouse=True)
def _fixture_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the deterministic embedder, exactly as ``test_dynamic_flow`` does.

    Not merely convenient: the config default is ``multilingual-e5-small``, and
    ``SettingsConfigDict(env_file=".env")`` resolves relative to the *process* directory,
    so a host pytest run never sees the repository-root ``.env`` that docker-compose
    reads. Without this the embedder tries a real provider and litellm raises before a
    single row is inserted.

    It also keeps the premise of these tests true: the lexical rung matters *because* the
    vectors carry no semantics, so the fixture embedder is the condition under test, not a
    shortcut around it.
    """
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "fixture/local")


#: Two documents whose vocabularies barely overlap, so a wrong hit is unambiguous.
ALERGENOS = [
    ("Los catorce alergenos", "El gluten, la lactosa y los frutos de cascara se declaran."),
    ("Contaminacion cruzada", "Separar utensilios del obrador para evitar restos de gluten."),
    ("Reaccion alergica", "Avisar al responsable y llamar al telefono de emergencias."),
]
CAJA = [
    ("Arqueo diario", "Contar el efectivo del cajon y cuadrar con el ticket Z."),
    ("Fondo de caja", "Dejar el fondo preparado para el turno de la manana siguiente."),
]


class World:
    def __init__(self, org_id: uuid.UUID, alergenos_id: uuid.UUID, caja_id: uuid.UUID) -> None:
        self.org_id = org_id
        self.alergenos_id = alergenos_id
        self.caja_id = caja_id


@pytest_asyncio.fixture
async def world() -> AsyncIterator[World]:
    suffix = uuid.uuid4().hex[:8]
    embedder = maybe_fixture_embedder(resolve_embedding_config({}))

    async with async_session_factory() as db:
        org = Organization(name=f"FTS {suffix}", slug=f"fts-{suffix}", settings={})
        db.add(org)
        await db.flush()

        ids: dict[str, uuid.UUID] = {}
        for key, title, sections in (
            ("alergenos", f"Manual de alergenos {suffix}", ALERGENOS),
            ("caja", f"Manejo de caja {suffix}", CAJA),
        ):
            document = Document(
                org_id=org.id,
                title=title,
                file_type="md",
                storage_path=f"/tmp/{key}-{suffix}.md",
                full_text="\n\n".join(body for _, body in sections),
            )
            db.add(document)
            await db.flush()
            ids[key] = document.id

            # The chunker's contextual prefix, verbatim from `chunker._prefix`. Not
            # decoration: `search_vector` is generated from `content` alone, so the
            # heading is only searchable because it is *inside* the chunk. Which is also
            # why extracting real headings out of a PDF raises lexical recall and not
            # just citation quality — a section title is the densest description of what
            # its passage is about.
            bodies = [
                f"[Documento: {title}] [Seccion: {heading}] {body}"
                for heading, body in sections
            ]
            vectors = await embedder.embed_texts(bodies, prefix="passage: ")
            for index, ((heading, _), content, vector) in enumerate(
                zip(sections, bodies, vectors, strict=True)
            ):
                db.add(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=index,
                        content=content,
                        chunk_metadata={
                            "heading": heading,
                            "position": index,
                            "page_start": index + 1,
                        },
                        embedding=vector,
                    )
                )
        await db.commit()
        world = World(org.id, ids["alergenos"], ids["caja"])

    yield world

    async with async_session_factory() as db:
        await db.execute(
            text(
                "DELETE FROM document_chunks WHERE document_id IN "
                "(SELECT id FROM documents WHERE org_id = :org)"
            ),
            {"org": world.org_id},
        )
        await db.execute(text("DELETE FROM documents WHERE org_id = :org"), {"org": world.org_id})
        await db.execute(text("DELETE FROM organizations WHERE id = :org"), {"org": world.org_id})
        await db.commit()


async def _fts(world: World, query: str, top_k: int = 5) -> list[dict]:
    from src.services.retrieval import query_terms

    async with async_session_factory() as db:
        return await DocumentChunkRepository(db).search_chunks_fts(
            org_id=world.org_id, terms=sorted(query_terms(query)), top_k=top_k
        )


class TestTheQuestionRetrievesAnything:
    async def test_a_whole_question_finds_the_right_passage(self, world: World):
        """The bug this rung was written around.

        ``websearch_to_tsquery`` joins words with ``&``, so the raw question compiles to
        ``'cual' & '14' & 'alergen' & ...`` and matches nothing. The terms are OR-ed and
        ``ts_rank_cd`` discriminates instead.
        """
        rows = await _fts(world, "Cuales son los 14 alergenos de declaracion obligatoria?")

        assert rows, "the question retrieved nothing at all"
        assert rows[0]["metadata"]["heading"] == "Los catorce alergenos"

    async def test_the_raw_question_ANDed_would_have_found_nothing(self, world: World):
        """Pins the reason, so nobody 'simplifies' the OR back into the obvious version."""
        async with async_session_factory() as db:
            matched = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM document_chunks c JOIN documents d "
                        "ON d.id = c.document_id WHERE d.org_id = :org AND c.search_vector "
                        "@@ websearch_to_tsquery('spanish', :q)"
                    ),
                    {"org": world.org_id, "q": "Cuales son los 14 alergenos de declaracion"},
                )
            ).scalar_one()

        assert matched == 0

    async def test_an_accented_question_matches_an_unaccented_corpus(self, world: World):
        """The corpus is written without accents and a learner types them."""
        rows = await _fts(world, "¿Qué hago ante una reacción alérgica?")

        assert rows
        assert rows[0]["metadata"]["heading"] == "Reaccion alergica"

    async def test_it_does_not_cross_into_an_unrelated_document(self, world: World):
        rows = await _fts(world, "Como se hace el arqueo del efectivo?")

        assert rows
        assert all(row["document_id"] == world.caja_id for row in rows)


class TestScopeAndShape:
    async def test_never_leaves_the_organization(self, world: World):
        async with async_session_factory() as db:
            rows = await DocumentChunkRepository(db).search_chunks_fts(
                org_id=uuid.uuid4(), terms=["alergenos"], top_k=5
            )

        assert rows == []

    async def test_document_ids_narrow_the_search(self, world: World):
        from src.services.retrieval import query_terms

        async with async_session_factory() as db:
            rows = await DocumentChunkRepository(db).search_chunks_fts(
                org_id=world.org_id,
                terms=sorted(query_terms("gluten efectivo cajon")),
                top_k=5,
                document_ids=[world.caja_id],
            )

        assert rows
        assert all(row["document_id"] == world.caja_id for row in rows)

    async def test_no_terms_is_not_a_query(self, world: World):
        """A question of nothing but stopwords must not match the whole corpus."""
        rows = await _fts(world, "de la y el en")

        assert rows == []

    async def test_scores_land_under_rank_not_similarity(self, world: World):
        """``ts_rank_cd`` in ``similarity`` would meet a cosine floor of 0.25 and vanish."""
        rows = await _fts(world, "gluten")

        assert rows
        assert "similarity" not in rows[0]
        assert rows[0]["rank"] > 0
        assert chunk_score(rows[0]) == rows[0]["rank"]

    async def test_top_k_is_respected(self, world: World):
        rows = await _fts(world, "gluten lactosa cascara utensilios obrador restos", top_k=2)

        assert len(rows) == 2


class TestTheLadder:
    async def test_the_lexical_rung_beats_pasting_whole_documents(self, world: World):
        """With fixture embeddings the vector rung is dead, and this is what runs."""
        async with async_session_factory() as db:
            grounded = await ground_question(
                db,
                user_id=uuid.uuid4(),  # enrolled in nothing: rung 3 cannot rescue this
                org_id=world.org_id,
                embedding_service=maybe_fixture_embedder(resolve_embedding_config({})),
                query="Cuales son los alergenos de declaracion obligatoria?",
            )

        assert grounded.grounding == "chunks_fts"
        assert "gluten" in grounded.context

    async def test_it_cites_a_section_and_a_page_not_a_whole_document(self, world: World):
        """The gain over rung 3: a located passage the reader can go and check."""
        async with async_session_factory() as db:
            grounded = await ground_question(
                db,
                user_id=uuid.uuid4(),
                org_id=world.org_id,
                embedding_service=maybe_fixture_embedder(resolve_embedding_config({})),
                query="Que hago ante una reaccion alergica?",
            )

        sections = [citation["section"] for citation in grounded.citations]
        assert "documento completo" not in sections
        assert "Reaccion alergica" in sections

    async def test_a_question_the_corpus_does_not_cover_still_falls_through(self, world: World):
        async with async_session_factory() as db:
            grounded = await ground_question(
                db,
                user_id=uuid.uuid4(),
                org_id=world.org_id,
                embedding_service=maybe_fixture_embedder(resolve_embedding_config({})),
                query="Cuanto pesa Jupiter en toneladas metricas?",
            )

        assert grounded.grounding == "general"

    async def test_context_is_smaller_than_the_whole_document_rung(self, world: World):
        """Prompt budget, not aesthetics: rung 3 pastes up to 8 000 characters."""
        async with async_session_factory() as db:
            embedder = maybe_fixture_embedder(resolve_embedding_config({}))
            lexical, _ = await retrieve_context_fts(
                db, org_id=world.org_id, query="alergenos gluten"
            )
            grounded = await ground_question(
                db,
                user_id=uuid.uuid4(),
                org_id=world.org_id,
                embedding_service=embedder,
                query="alergenos gluten",
            )

        assert grounded.grounding == "chunks_fts"
        assert len(lexical) < 8_000
