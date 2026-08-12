"""RAG retrieval: embed query, semantic search, assemble cited context.

The dedupe / order / citation-format steps are pure functions operating on plain
chunk dicts so they can be unit-tested without a DB or network.

Since 2026-07-27 this module also owns the **grounding ladder** the tutor answers from,
because "what did we find" and "what do we do when we found nothing" are the same
decision and splitting them is how the second half gets forgotten:

    vector chunks  >  lexical chunks  >  the whole document  >  general knowledge

**Which rung actually runs, measured rather than assumed.** With the local default
``EMBEDDING_MODEL=fixture/local`` the first rung is dead: ``FixtureEmbeddingService``
hashes each text into a random unit vector, so query and passage are orthogonal in
expectation. On the seeded corpus, *"cuales son los 14 alergenos de declaracion
obligatoria"* scores 0.099 / 0.075 / 0.073 / 0.066 / 0.049 against
:data:`SIMILARITY_FLOOR` = 0.25 — and the *best* of those five is a passage about
counting the cash float while the allergen manual ranks last. Zero of five survive, which
is the floor doing exactly its job.

Rung 2 is why the lexical rung exists at all. ``document_chunks.search_vector`` (a Spanish
``tsvector``) and its GIN index were created with the table and then queried by nothing,
while this module reimplemented a worse version of the same idea in Python — see
:func:`rank_documents`, counting terms over whole documents. Rung 2 hands that job back to
Postgres, at chunk granularity, with stemming, and yields a located passage carrying a
heading and a page instead of 8 000 characters of pasted document.

Rung 3 is still needed: a document too small to have been chunked is a legitimate
production state (``src/seed_demo_v2.py`` keeps documents at or under 5 pages so they take
the ``full_text`` branch of ``load_source_context``, §4.2), and it is also what an org gets
when the embedding provider was down during ingestion — ``src/services/ingestion.py`` logs
that and stores ``full_text`` alone.

The bottom rung is not a failure mode either: a user with no enrolments at all must still
get an answer. What never happens again is a refusal.
"""

from __future__ import annotations

import hashlib
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.llm.embedding import EmbeddingService
from src.models import Course, CourseNode, Document, Enrollment
from src.repositories.document_chunk_repo import DocumentChunkRepository

logger = get_logger(__name__)

_HASH_PREFIX_CHARS = 200

#: Below this cosine similarity a "hit" carries no signal and is treated as no hit at all.
#:
#: This is **not** a relevance threshold, and it is set an order of magnitude below one on
#: purpose. Real sentence embeddings (the shipped default is multilingual-e5-small) put
#: even loosely related pairs around 0.7-0.9, so nothing a real provider returns is ever
#: filtered by this. What it does filter is vectors with no semantics in them: the
#: deterministic ``FixtureEmbeddingService`` hashes each text into a random unit vector, so
#: query and passage are orthogonal in expectation and land at |cos| < 0.15 for 384
#: dimensions. Without the floor, a fixture-embedded org (which is what ``.env`` configures
#: for local runs, ``EMBEDDING_MODEL=fixture/local``) retrieves five random passages,
#: the ladder never falls through, and the tutor answers a question about allergens from a
#: chunk about the cash float — a worse failure than the refusal, because it looks right.
SIMILARITY_FLOOR = 0.25

#: How many whole documents may be pasted into one turn, and how much of each. A seeded
#: demo document is 700-3600 characters, so three of them fit inside the total with room
#: to spare; the caps exist for the org whose "small" document is 40 pages of appendix.
MAX_CONTEXT_DOCUMENTS = 3
MAX_DOCUMENT_CHARS = 4_000
MAX_DOCUMENTS_TOTAL_CHARS = 8_000

#: Words carrying no topical signal, so the lexical ranker below does not score a document
#: for sharing "de" with the question. Deliberately short: this is a tie-breaker over a
#: handful of documents, not an IR system.
_STOPWORDS: frozenset[str] = frozenset(
    """a al algo alguna algunas alguno algunos ante antes aqui aquel aquella aquello asi
    aun bajo bien cada como con contra cual cuales cuando cuanto de del desde donde dos el
    ella ellas ellos en entre era eran es esa esas ese eso esos esta estan estas este esto
    estos fue fueron ha habia han hasta hay la las le les lo los mas me mi mis mucho muy
    ni no nos nuestra nuestro o os otra otras otro otros para pero poco por porque que
    quien se segun ser si sin sobre solo son su sus tan te tiene tienen todo todos tu tus
    un una uno unas unos y ya""".split()
)


@dataclass(frozen=True)
class GroundedContext:
    """What the tutor was given to answer with, and where it came from.

    ``grounding`` travels to the browser (an SSE event) and into
    ``chat_messages.metadata``. The user is entitled to know whether the answer is a cited
    passage, a whole document or the model's own knowledge, and asking the model to say so
    is a request, not a guarantee — this field is the guarantee.
    """

    grounding: Literal["chunks", "chunks_fts", "document", "general"]
    context: str = ""
    citations: list[dict] = field(default_factory=list)
    #: False means retrieval was intentionally skipped by the general-chat router, not
    #: that a search ran and found nothing. The public grounding value stays compatible.
    retrieval_attempted: bool = True


def chunk_score(chunk: dict) -> float:
    """The chunk's own score, whichever retriever produced it.

    Vector hits carry ``similarity`` (cosine), lexical hits carry ``rank``
    (``ts_rank_cd``). Never both, and the two are not comparable — this only has to order
    a list that came from one retriever, not reconcile the two.
    """
    if "similarity" in chunk:
        return float(chunk["similarity"])
    return float(chunk.get("rank", 0.0))


def dedupe_chunks(chunks: list[dict]) -> list[dict]:
    """Drop near-duplicate chunks, keeping the highest-scoring version."""
    ordered = sorted(chunks, key=chunk_score, reverse=True)
    seen: set[str] = set()
    result: list[dict] = []
    for chunk in ordered:
        content = chunk.get("content", "")
        digest = hashlib.md5(content[:_HASH_PREFIX_CHARS].encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        result.append(chunk)
    return result


def order_chunks(chunks: list[dict]) -> list[dict]:
    """Reorder by document then in-document position for narrative coherence."""
    return sorted(
        chunks,
        key=lambda c: (
            str(c.get("document_id", "")),
            (c.get("metadata") or {}).get("position", 0),
        ),
    )


def assemble_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    """Build the cited context block and the citation list for the frontend."""
    blocks: list[str] = []
    citations: list[dict] = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata") or {}
        title = chunk.get("document_title") or meta.get("document_title") or "Documento"
        heading = meta.get("heading") or ""
        page = meta.get("page_start")

        marker = f"[Fuente {i}: {title}"
        if heading:
            marker += f" > {heading}"
        if page:
            marker += f", pag. {page}"
        marker += "]"

        blocks.append(f"{marker}\n{chunk.get('content', '')}")
        citations.append({"document": title, "section": heading, "page": page})

    return "\n\n---\n\n".join(blocks), citations


def usable_chunks(rows: list[dict], floor: float = SIMILARITY_FLOOR) -> list[dict]:
    """Drop hits whose similarity says the vectors carry no signal.

    See :data:`SIMILARITY_FLOOR` for why the number is so low and what it is really for.
    A row with no ``similarity`` key at all is kept: the caller built it by hand.
    """
    return [row for row in rows if float(row.get("similarity", 1.0)) >= floor]


async def retrieve_context(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    embedding_service: EmbeddingService,
    query: str,
    top_k: int = 5,
    document_ids: Sequence[uuid.UUID] | None = None,
) -> tuple[str, list[dict]]:
    """Embed the query, run semantic search, and assemble a cited context block."""
    query_embedding = await embedding_service.embed_query(query)
    repo = DocumentChunkRepository(db)
    rows = await repo.similarity_search(
        org_id=org_id,
        query_embedding=query_embedding,
        top_k=top_k,
        document_ids=document_ids,
    )
    rows = usable_chunks(rows)
    if not rows:
        return "", []
    return assemble_context(order_chunks(dedupe_chunks(rows)))


async def retrieve_context_fts(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    query: str,
    top_k: int = 5,
    document_ids: Sequence[uuid.UUID] | None = None,
) -> tuple[str, list[dict]]:
    """Lexical sibling of :func:`retrieve_context`: same assembly, no embeddings.

    No ``usable_chunks`` call, and that is not an omission. The floor exists to detect
    vectors with no semantics in them; a row is here precisely *because* Postgres matched
    the query's lexemes against the passage's, which is signal by construction.

    :func:`query_terms` does the preprocessing, so accent folding and the Spanish stopword
    list live in exactly one place — the same one :func:`rank_documents` already used. It
    matters twice here: the corpus is written without accents while a learner types them,
    and without stripping stopwords the OR query would match every chunk containing "de".
    """
    terms = sorted(query_terms(query))
    if not terms:
        return "", []
    repo = DocumentChunkRepository(db)
    rows = await repo.search_chunks_fts(
        org_id=org_id, terms=terms, top_k=top_k, document_ids=document_ids
    )
    if not rows:
        return "", []
    return assemble_context(order_chunks(dedupe_chunks(rows)))


# --------------------------------------------------------------------------------------
# Rung 2: the whole document. Pure functions first, then the two queries.
# --------------------------------------------------------------------------------------
def fold(text: str) -> str:
    """Lower-case and strip accents, so ``alérgenos`` and ``alergenos`` are one word.

    Not cosmetic. The seeded corpus is written without accents (the whole repository is),
    and a learner types them: without folding, the single most likely question in the demo
    — *"¿Qué son los alérgenos?"* — shares **zero** terms with the document that answers
    it, and the ranker below would order the three documents by nothing at all.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def query_terms(query: str) -> set[str]:
    """The topical words of a question: folded, de-punctuated, stopwords removed."""
    cleaned = "".join(char if char.isalnum() or char.isspace() else " " for char in fold(query))
    return {word for word in cleaned.split() if len(word) > 2 and word not in _STOPWORDS}


def rank_documents(documents: list[dict], query: str) -> list[dict]:
    """Order whole documents by how many of the question's terms they contain.

    A lexical count, and deliberately nothing cleverer. This rung exists precisely
    *because* there are no usable embeddings, so anything vector-shaped here would be
    circular; and the input is three documents, not three million. Ties keep the incoming
    order, which is the caller's ``ORDER BY``, so the result is deterministic.

    Scoring is by **distinct term hit**, not by frequency: a document that says
    "alergenos" forty times is not four times more relevant than one that says it ten
    times, but one that matches both "alergenos" and "cliente" is more relevant than one
    that matches either alone.
    """
    terms = query_terms(query)
    if not terms:
        return list(documents)
    scored = []
    for position, document in enumerate(documents):
        haystack = fold(f"{document.get('title', '')}\n{document.get('full_text', '')}")
        score = sum(1 for term in terms if term in haystack)
        scored.append((-score, position, document))
    return [document for _, _, document in sorted(scored, key=lambda item: item[:2])]


def clip_document(text: str, limit: int = MAX_DOCUMENT_CHARS) -> str:
    """Trim a document at a paragraph or word boundary, never mid-word."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = head.rfind("\n\n")
    if cut < limit // 2:
        cut = head.rfind("\n")
    if cut < limit // 2:
        cut = head.rfind(" ")
    if cut <= 0:
        cut = limit
    return head[:cut].rstrip() + "\n[...]"


def assemble_document_context(
    documents: list[dict],
    *,
    max_documents: int = MAX_CONTEXT_DOCUMENTS,
    total_chars: int = MAX_DOCUMENTS_TOTAL_CHARS,
) -> tuple[str, list[dict]]:
    """Build a cited context block out of whole documents.

    Same ``[Fuente N]`` shape as :func:`assemble_context`, because the tutor is told to
    cite the same way in both modes and two citation dialects in one persona is one too
    many. The marker says ``documento completo`` and the citation carries no page: the
    honesty this preserves is that a whole-document answer is **not** a located passage,
    and the browser prints exactly what the citation says.
    """
    blocks: list[str] = []
    citations: list[dict] = []
    budget = total_chars
    for document in documents[:max_documents]:
        text = (document.get("full_text") or "").strip()
        if not text or budget <= 0:
            continue
        body = clip_document(text, min(MAX_DOCUMENT_CHARS, budget))
        budget -= len(body)
        title = document.get("title") or "Documento"
        blocks.append(f"[Fuente {len(blocks) + 1}: {title} (documento completo)]\n{body}")
        citations.append({"document": title, "section": "documento completo", "page": None})
    return "\n\n---\n\n".join(blocks), citations


async def enrolled_documents(
    db: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID
) -> list[dict]:
    """Documents behind the courses this user is enrolled in, newest course first.

    Both sources of a course's documents are followed: ``courses.source_document_id`` (v1
    and the course-level link) and ``course_nodes.source_document_id`` (v2 nodes, which may
    each point somewhere else). ``org_id`` is in the ``WHERE`` as well as the enrolment
    join — the join already implies it, and defence in depth on a query that decides what
    text goes into a prompt is worth one redundant predicate.
    """
    course_ids = (
        select(Enrollment.course_id).where(Enrollment.user_id == user_id).scalar_subquery()
    )
    document_ids = select(Course.source_document_id).where(
        Course.id.in_(course_ids), Course.source_document_id.is_not(None)
    ).union(
        select(CourseNode.source_document_id).where(
            CourseNode.course_id.in_(course_ids), CourseNode.source_document_id.is_not(None)
        )
    )
    query = (
        select(Document.id, Document.title, Document.full_text)
        .where(
            Document.org_id == org_id,
            Document.id.in_(document_ids),
            Document.full_text.is_not(None),
        )
        .order_by(Document.created_at.desc())
    )
    rows = (await db.execute(query)).all()
    return [
        {"id": row.id, "title": row.title, "full_text": row.full_text} for row in rows
    ]


async def org_documents(db: AsyncSession, *, org_id: uuid.UUID) -> list[dict]:
    """Every readable document of the organization. The admin assistant's rung 2."""
    query = (
        select(Document.id, Document.title, Document.full_text)
        .where(Document.org_id == org_id, Document.full_text.is_not(None))
        .order_by(Document.created_at.desc())
    )
    rows = (await db.execute(query)).all()
    return [
        {"id": row.id, "title": row.title, "full_text": row.full_text} for row in rows
    ]


# --------------------------------------------------------------------------------------
# The ladder
# --------------------------------------------------------------------------------------
async def ground_question(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    embedding_service: EmbeddingService,
    query: str,
    top_k: int = 5,
    document_ids: Sequence[uuid.UUID] | None = None,
    whole_documents: str = "enrolled",
) -> GroundedContext:
    """Walk ``chunks -> whole document -> general`` and return the first rung that has text.

    Retrieval failing is **not** an error here. An org with no embedding provider, or a
    document too small to have been chunked, is a normal state, and one bad rung must not
    cost the answer: an exception from the vector path is logged and demoted to rung 2,
    which is the rung that would have been used had the search simply come back empty.
    """
    try:
        context, citations = await retrieve_context(
            db,
            org_id=org_id,
            embedding_service=embedding_service,
            query=query,
            top_k=top_k,
            document_ids=document_ids,
        )
        if context:
            return GroundedContext("chunks", context, citations)
    except Exception as exc:  # noqa: BLE001 - a dead embedder must not cost the answer
        logger.warning("Chunk retrieval failed, falling back to lexical search: %s", exc)

    # Rung 1.5: the same chunks, found lexically. Tried before whole documents because a
    # located passage with a heading and a page beats 8 000 characters of pasted document
    # on every axis that matters — prompt budget, citation precision, and the reader's
    # ability to check the answer.
    try:
        context, citations = await retrieve_context_fts(
            db, org_id=org_id, query=query, top_k=top_k, document_ids=document_ids
        )
        if context:
            return GroundedContext("chunks_fts", context, citations)
    except Exception as exc:  # noqa: BLE001 - same contract as the vector rung above
        logger.warning("Lexical retrieval failed, falling back to whole documents: %s", exc)

    if whole_documents == "org":
        documents = await org_documents(db, org_id=org_id)
    else:
        documents = await enrolled_documents(db, user_id=user_id, org_id=org_id)
    if documents:
        context, citations = assemble_document_context(rank_documents(documents, query))
        if context:
            return GroundedContext("document", context, citations)

    return GroundedContext("general")
