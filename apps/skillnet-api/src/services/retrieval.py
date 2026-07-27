"""RAG retrieval: embed query, semantic search, assemble cited context.

The dedupe / order / citation-format steps are pure functions operating on plain
chunk dicts so they can be unit-tested without a DB or network.

Since 2026-07-27 this module also owns the **grounding ladder** the tutor answers from,
because "what did we find" and "what do we do when we found nothing" are the same
decision and splitting them is how the second half gets forgotten:

    retrieved chunks  >  the whole document of an enrolled course  >  general knowledge

The middle rung is the one the demo needed. ``src/seed_demo_v2.py`` keeps every document
at or under 5 pages on purpose — that is the ``full_text`` branch of ``load_source_context``
(§4.2), which needs no embeddings — so the three seeded documents have ``full_text`` and
**zero** ``document_chunks``. RAG retrieved nothing and the tutor refused, with the answer
sitting in a column nobody read. A small document with no chunks is a legitimate
production state (it is also what an org gets when the embedding provider was down during
ingestion: ``src/services/ingestion.py`` logs it and stores ``full_text`` alone), so the
fix belongs here and not only in the seed.

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

    grounding: Literal["chunks", "document", "general"]
    context: str = ""
    citations: list[dict] = field(default_factory=list)


def dedupe_chunks(chunks: list[dict]) -> list[dict]:
    """Drop near-duplicate chunks, keeping the highest-similarity version."""
    ordered = sorted(chunks, key=lambda c: c.get("similarity", 0.0), reverse=True)
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
        logger.warning("Chunk retrieval failed, falling back to whole documents: %s", exc)

    if whole_documents == "org":
        documents = await org_documents(db, org_id=org_id)
    else:
        documents = await enrolled_documents(db, user_id=user_id, org_id=org_id)
    if documents:
        context, citations = assemble_document_context(rank_documents(documents, query))
        if context:
            return GroundedContext("document", context, citations)

    return GroundedContext("general")
