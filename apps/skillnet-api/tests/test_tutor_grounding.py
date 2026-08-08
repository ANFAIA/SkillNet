"""The grounding ladder: chunks -> the whole document -> general. Pure, no DB, no network.

The bug these tests exist for, in one line: three seeded documents with ``full_text`` and
zero ``document_chunks`` made the tutor answer *"No tengo informacion sobre esto en los
documentos disponibles."* to every question ever asked. Every assertion below is about a
rung of the ladder that stops that from being possible again.
"""

from __future__ import annotations

import uuid

import pytest

from src.llm.prompts.tutor import (
    NO_UI_SENTINEL,
    admin_system_prompt,
    build_user_turn,
    tutor_system_prompt,
)
from src.services import retrieval
from src.services.retrieval import (
    SIMILARITY_FLOOR,
    GroundedContext,
    assemble_document_context,
    clip_document,
    fold,
    ground_question,
    query_terms,
    rank_documents,
    usable_chunks,
)

ALERGENOS = {
    "id": uuid.uuid4(),
    "title": "Manual de alergenos e informacion al cliente",
    "full_text": "Los catorce alergenos de declaracion obligatoria. Cereales con gluten.",
}
CAJA = {
    "id": uuid.uuid4(),
    "title": "Manejo de caja y arqueo diario",
    "full_text": "El fondo de caja es de 150 euros en cambio.",
}


# -- the floor ---------------------------------------------------------------------
def test_floor_drops_signal_free_hits() -> None:
    """A fixture-embedded org retrieves random passages; they must not become context."""
    rows = [
        {"content": "ruido", "similarity": 0.02},
        {"content": "ruido", "similarity": -0.11},
    ]
    assert usable_chunks(rows) == []


def test_floor_keeps_anything_a_real_embedder_returns() -> None:
    # multilingual-e5 puts even loosely related pairs well above this.
    rows = [{"content": "relevante", "similarity": 0.71}]
    assert usable_chunks(rows) == rows


def test_floor_keeps_rows_with_no_similarity_at_all() -> None:
    rows = [{"content": "construido a mano"}]
    assert usable_chunks(rows) == rows


def test_floor_is_far_below_any_real_similarity() -> None:
    assert 0.0 < SIMILARITY_FLOOR < 0.5


# -- ranking whole documents -------------------------------------------------------
def test_fold_strips_accents_so_the_demo_question_matches() -> None:
    assert fold("¿Qué son los alérgenos?") == "¿que son los alergenos?"


def test_query_terms_drops_stopwords_and_short_words() -> None:
    assert query_terms("¿Que son los alergenos y el gluten?") == {"alergenos", "gluten"}


def test_rank_puts_the_document_that_answers_first() -> None:
    ranked = rank_documents([CAJA, ALERGENOS], "¿Qué son los alérgenos?")
    assert ranked[0] is ALERGENOS


def test_rank_is_stable_when_nothing_matches() -> None:
    ranked = rank_documents([CAJA, ALERGENOS], "???")
    assert ranked == [CAJA, ALERGENOS]


def test_clip_document_cuts_at_a_boundary_never_mid_word() -> None:
    text = "palabra " * 100
    clipped = clip_document(text, 50)
    assert clipped.endswith("[...]")
    assert "palab\n" not in clipped


# -- the document context block ----------------------------------------------------
def test_document_context_cites_the_document_and_says_it_is_whole() -> None:
    block, citations = assemble_document_context([ALERGENOS])

    assert "[Fuente 1: Manual de alergenos e informacion al cliente (documento completo)]" in block
    assert "catorce alergenos" in block
    # The honesty that separates rung 2 from rung 1: no page, and the section says so.
    assert citations == [
        {
            "document": "Manual de alergenos e informacion al cliente",
            "section": "documento completo",
            "page": None,
        }
    ]


def test_document_context_respects_the_total_budget() -> None:
    big = {"id": uuid.uuid4(), "title": "Grande", "full_text": "x" * 9_000}
    block, citations = assemble_document_context([big], total_chars=500)
    assert len(block) < 1_000
    assert len(citations) == 1


def test_document_context_skips_documents_with_no_text() -> None:
    block, citations = assemble_document_context([{"title": "Vacio", "full_text": "  "}])
    assert block == ""
    assert citations == []


# -- the ladder --------------------------------------------------------------------
class _FakeDB:
    async def commit(self) -> None: ...


async def _ground(monkeypatch, *, chunks, documents, whole="enrolled") -> GroundedContext:
    async def fake_retrieve(*_args, **_kwargs):
        return chunks

    async def fake_documents(*_args, **_kwargs):
        return documents

    monkeypatch.setattr(retrieval, "retrieve_context", fake_retrieve)
    monkeypatch.setattr(retrieval, "enrolled_documents", fake_documents)
    monkeypatch.setattr(retrieval, "org_documents", fake_documents)
    return await ground_question(
        _FakeDB(),  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        embedding_service=object(),  # type: ignore[arg-type]
        query="¿Qué son los alérgenos?",
        whole_documents=whole,
    )


async def test_rung_1_chunks_win_when_retrieval_has_something(monkeypatch) -> None:
    grounded = await _ground(
        monkeypatch,
        chunks=("[Fuente 1: Manual] gluten", [{"document": "Manual"}]),
        documents=[ALERGENOS],
    )
    assert grounded.grounding == "chunks"
    assert "gluten" in grounded.context


async def test_rung_2_the_whole_document_when_there_are_no_chunks(monkeypatch) -> None:
    """The measured bug: 0 chunks, 0 embeddings, and the answer sitting in full_text."""
    grounded = await _ground(monkeypatch, chunks=("", []), documents=[CAJA, ALERGENOS])

    assert grounded.grounding == "document"
    assert "catorce alergenos" in grounded.context
    assert grounded.citations[0]["document"].startswith("Manual de alergenos")


async def test_rung_3_general_for_a_user_with_no_enrolments(monkeypatch) -> None:
    grounded = await _ground(monkeypatch, chunks=("", []), documents=[])

    assert grounded.grounding == "general"
    assert grounded.context == ""
    assert grounded.citations == []


async def test_a_dead_embedder_demotes_to_rung_2_instead_of_failing(monkeypatch) -> None:
    async def exploding_retrieve(*_args, **_kwargs):
        raise RuntimeError("embedding provider is down")

    async def fake_documents(*_args, **_kwargs):
        return [ALERGENOS]

    monkeypatch.setattr(retrieval, "retrieve_context", exploding_retrieve)
    monkeypatch.setattr(retrieval, "enrolled_documents", fake_documents)

    grounded = await ground_question(
        _FakeDB(),  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        embedding_service=object(),  # type: ignore[arg-type]
        query="alergenos",
    )
    assert grounded.grounding == "document"


async def test_admin_reads_the_whole_org_not_enrolments(monkeypatch) -> None:
    seen: list[str] = []

    async def fake_retrieve(*_args, **_kwargs):
        return "", []

    async def fake_enrolled(*_args, **_kwargs):
        seen.append("enrolled")
        return []

    async def fake_org(*_args, **_kwargs):
        seen.append("org")
        return [CAJA]

    monkeypatch.setattr(retrieval, "retrieve_context", fake_retrieve)
    monkeypatch.setattr(retrieval, "enrolled_documents", fake_enrolled)
    monkeypatch.setattr(retrieval, "org_documents", fake_org)

    grounded = await ground_question(
        _FakeDB(),  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        embedding_service=object(),  # type: ignore[arg-type]
        query="fondo de caja",
        whole_documents="org",
    )
    assert seen == ["org"]
    assert grounded.grounding == "document"


# -- the prompts -------------------------------------------------------------------
@pytest.mark.parametrize("grounding", ["chunks", "chunks_fts", "document", "general"])
def test_no_grounding_mode_can_produce_the_refusal(grounding: str) -> None:
    """The sentence that started all of this is not in any prompt any more."""
    for prompt in (tutor_system_prompt(grounding), admin_system_prompt(grounding)):
        assert "No tengo informacion" not in prompt
        assert "di exactamente" not in prompt


@pytest.mark.parametrize("grounding", ["chunks", "chunks_fts", "document", "general"])
def test_every_mode_carries_the_persona(grounding: str) -> None:
    prompt = tutor_system_prompt(grounding)
    assert "tutor de SkillNet" in prompt
    assert "Tuteas" in prompt


def test_general_mode_orders_the_answer_to_be_labelled() -> None:
    prompt = tutor_system_prompt("general")
    assert "conocimiento general" in prompt.lower()
    assert "[Fuente N]" in prompt  # ...as the thing NOT to write
    assert "negarte no es una opcion" in prompt.lower()


def test_general_user_turn_has_no_empty_context_placeholder() -> None:
    """The old builder pasted "(No hay contexto disponible.)" and got a refusal back."""
    turn = build_user_turn("general", "", "¿Qué son los alérgenos?")
    assert "No hay contexto disponible" not in turn
    assert "Contexto de la empresa" not in turn
    assert "¿Qué son los alérgenos?" in turn


def test_context_modes_paste_the_context_and_the_question() -> None:
    turn = build_user_turn("document", "[Fuente 1: Manual (documento completo)]\ngluten", "¿y?")
    assert "gluten" in turn
    assert "¿y?" in turn


def test_chunks_fts_uses_the_same_prompt_as_chunks() -> None:
    """Lexical chunks and vector chunks use the same prompt blocks."""
    assert tutor_system_prompt("chunks_fts") == tutor_system_prompt("chunks")
    turn_fts = build_user_turn("chunks_fts", "contexto fts", "¿pregunta?")
    turn_vec = build_user_turn("chunks", "contexto fts", "¿pregunta?")
    assert turn_fts == turn_vec


def test_no_ui_sentinel_is_a_bare_token() -> None:
    """It is compared against a whole line, so a sentinel with spaces would never match."""
    assert NO_UI_SENTINEL.isupper()
    assert " " not in NO_UI_SENTINEL
