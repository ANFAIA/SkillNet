"""Grounding-context builder for media generators (roadmap §2, spine item #2).

Every artifact generator — podcast, slides, infographic, ... — is fed the **same** unit:
a bundle of source passages, each carrying a **stable ``citation_id``**. The generator is
then instructed to emit those ids alongside its output, so the parallel citations panel
(the feature every open-source NotebookLM replica failed to ship) can render the exact
hover/click-to-passage affordance for free.

This module does **not** reimplement retrieval. It reuses the pure building blocks of
``src/services/retrieval.py`` — ``usable_chunks`` (the similarity floor), ``dedupe_chunks``,
``order_chunks`` for the vector/lexical rungs, and ``rank_documents`` / ``clip_document``
for the whole-document rung — and the ``DocumentChunkRepository`` queries behind them. It
walks the same ladder the tutor answers from, plus one rung the tutor does not need:

    vector chunks  >  lexical chunks  >  whole documents  >  course material  >  (empty)

The last rung before ``empty`` exists because a course created **from an idea** has no
document at all — no ``courses.source_document_id``, no ``course_nodes.source_document_id``
— and every documentary rung therefore comes back with nothing. It used to end there, and
the generator was then asked to write "in general": a boxing course produced an infographic
titled *"Claves para una vida saludable"*. The course's own prepared material was in the
database the whole time.

The only thing it adds is the ``citation_id``: ``c1``, ``c2``, ... assigned in final
passage order, deterministic, so the same corpus always yields the same ids and a spec
persisted today still resolves against the bundle rebuilt tomorrow.

The assembly is split into **pure** functions (``bundle_from_chunks``,
``bundle_from_documents``, ``bundle_from_course_material``) operating on plain dicts,
tested without a DB, and one async orchestrator (``build_grounding_bundle``) that does the
queries.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select, union
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.llm.embedding import EmbeddingService
from src.models import (
    Course,
    CourseNode,
    Document,
    NodeKnowledgePackRecord,
    NodeKnowledgePackStatus,
)
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.services.retrieval import (
    clip_document,
    dedupe_chunks,
    order_chunks,
    query_terms,
    rank_documents,
    usable_chunks,
)

logger = get_logger(__name__)

GroundingMode = Literal[
    "chunks",
    "chunks_fts",
    "document",
    # The course's own material, when it has no documentary corpus. Two values rather than
    # one because the two are not the same evidence: ``course_pack`` carries the reviewed
    # claims of a node knowledge pack, ``course_outline`` carries only the titles and
    # summaries the schema designer wrote. A generator handed the second is working from a
    # sentence per node, and ``mode`` is the field that says so.
    "course_pack",
    "course_outline",
    "empty",
]

#: How much of a whole document becomes a single passage when no chunks exist. Mirrors the
#: retrieval ladder's whole-document rung; kept modest so a bundle stays promptable.
_DOCUMENT_PASSAGE_CHARS = 2_000
#: Cap on whole-document passages, so a media prompt is not swamped by one big appendix.
_MAX_DOCUMENT_PASSAGES = 4
#: One passage per node, so a long course does not swamp the prompt. Course-level artifacts
#: are overviews; eight nodes of material is already more than a podcast script can use.
_MAX_COURSE_PASSAGES = 8
#: Per-node clip, applied after the atoms are joined.
_COURSE_PASSAGE_CHARS = 1_500
#: Atoms per node. ``must_preserve`` first, so the cut falls on the optional material.
_MAX_PACK_ATOMS_PER_NODE = 12


@dataclass(frozen=True)
class GroundedPassage:
    """One citable source passage. ``citation_id`` is the stable handle a generator emits."""

    citation_id: str
    text: str
    source_title: str
    section: str | None = None
    page: int | None = None
    document_id: str | None = None

    def marker(self) -> str:
        """The ``[Fuente cN: Title > Section, pag. P]`` header, same dialect as retrieval."""
        marker = f"[Fuente {self.citation_id}: {self.source_title}"
        if self.section:
            marker += f" > {self.section}"
        if self.page:
            marker += f", pag. {self.page}"
        return marker + "]"

    def as_payload(self) -> dict:
        """The citation as it travels to the client / into ``spec_json``."""
        return {
            "citation_id": self.citation_id,
            "document": self.source_title,
            "section": self.section,
            "page": self.page,
            "document_id": self.document_id,
        }


@dataclass(frozen=True)
class GroundedBundle:
    """What a generator is handed: cited passages plus which rung produced them.

    ``mode`` is the honesty field, exactly like ``GroundedContext.grounding``: a bundle
    built from located chunks is not the same evidence as one built from a whole document
    or from nothing, and a generator (or an auditor) is entitled to know which.
    """

    mode: GroundingMode
    passages: list[GroundedPassage] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.passages

    def as_prompt_context(self) -> str:
        """The cited context block fed to the generator's LLM call."""
        return "\n\n---\n\n".join(
            f"{passage.marker()}\n{passage.text}" for passage in self.passages
        )

    def citations_payload(self) -> list[dict]:
        """The citation list persisted in ``spec_json`` and shown beside the artifact."""
        return [passage.as_payload() for passage in self.passages]

    def citation_ids(self) -> list[str]:
        return [passage.citation_id for passage in self.passages]


def _citation_id(index: int) -> str:
    """``c1``, ``c2``, ... — assigned in final passage order."""
    return f"c{index}"


def bundle_from_chunks(rows: list[dict], *, mode: GroundingMode) -> GroundedBundle:
    """Turn retrieved chunk rows into a cited bundle (pure).

    Reuses retrieval's ``dedupe_chunks`` + ``order_chunks`` so the ordering and de-duping
    are identical to what the tutor sees; then stamps citation ids in that final order.
    ``usable_chunks`` (the similarity floor) is applied by the caller for the vector rung
    only — a lexical hit is signal by construction and must not be floored, same rule as
    ``retrieval.retrieve_context_fts``.
    """
    passages: list[GroundedPassage] = []
    for index, chunk in enumerate(order_chunks(dedupe_chunks(rows)), start=1):
        meta = chunk.get("metadata") or {}
        title = (
            chunk.get("document_title")
            or meta.get("document_title")
            or "Documento"
        )
        document_id = chunk.get("document_id")
        passages.append(
            GroundedPassage(
                citation_id=_citation_id(index),
                text=str(chunk.get("content", "")),
                source_title=str(title),
                section=meta.get("heading") or None,
                page=meta.get("page_start"),
                document_id=str(document_id) if document_id else None,
            )
        )
    return GroundedBundle(mode=mode, passages=passages)


def bundle_from_documents(documents: list[dict]) -> GroundedBundle:
    """Turn whole documents into a cited bundle (pure), one clipped passage each.

    The whole-document rung: used when nothing was chunked. Honest about it — the section
    reads ``documento completo`` and there is no page, exactly like
    ``retrieval.assemble_document_context``.
    """
    passages: list[GroundedPassage] = []
    for document in documents[:_MAX_DOCUMENT_PASSAGES]:
        text = (document.get("full_text") or "").strip()
        if not text:
            continue
        passages.append(
            GroundedPassage(
                citation_id=_citation_id(len(passages) + 1),
                text=clip_document(text, _DOCUMENT_PASSAGE_CHARS),
                source_title=str(document.get("title") or "Documento"),
                section="documento completo",
                page=None,
                document_id=(
                    str(document["id"]) if document.get("id") else None
                ),
            )
        )
    return GroundedBundle(mode="document", passages=passages)


def _atom_lines(atoms: Sequence[dict]) -> list[str]:
    """The citable sentences of a knowledge pack, ordered deterministically.

    ``must_preserve`` before ``selectable``: the first are the claims the pack says a
    learner experience may not drop, the second are optional colour, so when the cap bites
    it should bite the colour. Ties break on ``atom_id`` rather than on list order because
    citation ids are handed out in final passage order and must survive a regeneration of
    the same pack.
    """
    ordered = sorted(
        (atom for atom in atoms if str(atom.get("text") or "").strip()),
        key=lambda atom: (
            0 if atom.get("category") == "must_preserve" else 1,
            str(atom.get("atom_id") or ""),
        ),
    )
    return [
        " ".join(str(atom["text"]).split())
        for atom in ordered[:_MAX_PACK_ATOMS_PER_NODE]
    ]


def bundle_from_course_material(
    nodes: Sequence[dict], *, course_title: str
) -> GroundedBundle:
    """Turn the course's own material into a cited bundle (pure), one passage per node.

    The rung for a course with no documents. Each node contributes one passage, cited as
    ``[Fuente cN: <course title> > <node title>]`` — the course is the source here, and
    naming it in the marker is also what keeps a generator on topic.

    The text comes from the node's **knowledge pack atoms** when there is a ready pack, and
    from the node's own ``outcome``/``summary`` otherwise. Packs and not ``node_renders``:
    a render is an OpenUI *program*, and mining prose out of it would mean reimplementing
    the inverse of the serializer here and then keeping it in step with the catalogue; a
    pack is already reviewed prose, has no per-learner personalization baked in, and exists
    for every validated v2 course because the pack runner writes one per node.

    ``mode`` is ``course_pack`` only when **every** emitted passage carries pack material.
    One node without a pack drops the whole bundle to ``course_outline``, so the stronger
    label never over-promises for a bundle that is partly just titles.
    """
    passages: list[GroundedPassage] = []
    all_from_packs = True
    for node in nodes[:_MAX_COURSE_PASSAGES]:
        title = str(node.get("title") or "").strip()
        lines: list[str] = [title] if title else []
        outcome = str(node.get("outcome") or "").strip()
        if outcome:
            lines.append(f"Objetivo: {outcome}")
        summary = str(node.get("summary") or "").strip()
        if summary:
            lines.append(summary)
        atom_lines = _atom_lines(node.get("atoms") or [])
        lines.extend(f"- {line}" for line in atom_lines)
        if not atom_lines:
            all_from_packs = False
        body = "\n".join(lines).strip()
        if not body:
            continue
        passages.append(
            GroundedPassage(
                citation_id=_citation_id(len(passages) + 1),
                text=clip_document(body, _COURSE_PASSAGE_CHARS),
                source_title=course_title.strip() or "Curso",
                section=title or None,
                page=None,
                # There is no document behind this passage, and saying so is the point:
                # a citation that invented a document_id would send the citations panel
                # looking for a row that does not exist.
                document_id=None,
            )
        )
    if not passages:
        return GroundedBundle(mode="empty", passages=[])
    return GroundedBundle(
        mode="course_pack" if all_from_packs else "course_outline", passages=passages
    )


async def course_document_ids(
    db: AsyncSession, *, course: Course, node: CourseNode | None = None
) -> list[uuid.UUID]:
    """Documents behind a course (or a single node): the corpus a bundle draws from.

    Both link points, same union as ``retrieval.enrolled_documents`` but scoped to one
    course rather than to a user's enrolments: ``courses.source_document_id`` (the
    course-level link) and ``course_nodes.source_document_id`` (each v2 node may point
    elsewhere). When ``node`` is given, only that node's document is used — a node-level
    artifact should ground on the node's own source, not the whole course.
    """
    if node is not None:
        return [node.source_document_id] if node.source_document_id else []

    course_link = select(Course.source_document_id).where(
        Course.id == course.id, Course.source_document_id.is_not(None)
    )
    node_links = select(CourseNode.source_document_id).where(
        CourseNode.course_id == course.id,
        CourseNode.source_document_id.is_not(None),
    )
    rows = (await db.execute(union(course_link, node_links))).all()
    return [row[0] for row in rows]


async def _load_documents(
    db: AsyncSession, *, org_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
) -> list[dict]:
    """Whole-document fallback source: title + full_text for the corpus."""
    if not document_ids:
        return []
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
        {"id": row.id, "title": row.title, "full_text": row.full_text}
        for row in rows
    ]


async def _load_course_material(
    db: AsyncSession, *, course: Course, node: CourseNode | None = None
) -> list[dict]:
    """The course's own nodes, each with the atoms of its latest ready knowledge pack.

    Scope is the whole point of this function. A node request is answered with that node
    and nothing else; a course request with that course's live nodes, in reading order.
    Every query is filtered by ``course_id`` **and** ``org_id`` — ``node_id`` alone would
    already imply the course, but this is the query that runs precisely when a course has
    no corpus of its own, which is the situation that used to spill into the org's.

    Only ``ready`` packs. ``review_required`` rows also carry atoms, but a reviewer flagged
    them, and the rest of the runtime (``node_render_service``, ``runtime_selection``)
    reads ready-only; a bundle is not the place to start disagreeing.
    """
    if node is not None:
        # A node from another course would ground an artifact on material its own course
        # never had. Cheap to check, and the alternative is silent.
        if node.course_id != course.id or node.org_id != course.org_id:
            return []
        nodes = [node]
    else:
        query = (
            select(CourseNode)
            .where(
                CourseNode.course_id == course.id,
                CourseNode.org_id == course.org_id,
                CourseNode.archived.is_(False),
            )
            .order_by(CourseNode.position)
            .limit(_MAX_COURSE_PASSAGES)
        )
        nodes = list((await db.execute(query)).scalars().all())
    if not nodes:
        return []

    pack_query = (
        select(
            NodeKnowledgePackRecord.node_id,
            NodeKnowledgePackRecord.atoms,
        )
        .where(
            NodeKnowledgePackRecord.org_id == course.org_id,
            NodeKnowledgePackRecord.course_id == course.id,
            NodeKnowledgePackRecord.node_id.in_([item.id for item in nodes]),
            NodeKnowledgePackRecord.status == NodeKnowledgePackStatus.READY,
        )
        .order_by(
            NodeKnowledgePackRecord.node_id,
            NodeKnowledgePackRecord.created_at.desc(),
        )
    )
    atoms_by_node: dict[uuid.UUID, list] = {}
    for row in (await db.execute(pack_query)).all():
        # First row per node wins: the ORDER BY puts the newest snapshot first.
        atoms_by_node.setdefault(row.node_id, list(row.atoms or []))

    return [
        {
            "title": item.title,
            "summary": item.summary,
            "outcome": item.outcome,
            "atoms": atoms_by_node.get(item.id, []),
        }
        for item in nodes
    ]


async def build_grounding_bundle(
    db: AsyncSession,
    *,
    course: Course,
    node: CourseNode | None = None,
    embedding_service: EmbeddingService | None = None,
    query: str | None = None,
    top_k: int = 8,
) -> GroundedBundle:
    """Assemble the grounded context bundle for a course/node.

    Walks the retrieval ladder and returns the first rung that yields passages:

    1. **Vector chunks** — when an ``embedding_service`` and a ``query`` are given. A dead
       embedder is demoted, never fatal (same contract as ``retrieval.ground_question``).
    2. **Lexical chunks** — Postgres FTS over the same corpus; needs no embeddings, so it
       is the rung that actually works under ``EMBEDDING_MODEL=fixture/local``.
    3. **Whole documents** — clipped, when nothing was chunked.
    4. **Course material** — the course's own nodes and their knowledge packs, when the
       course has no documents at all. A course written from an idea lives on this rung.
    5. **Empty** — only when even the course has nothing to say; the generator decides
       what to do with an ungrounded bundle.

    The three documentary rungs are **skipped outright** when the course has no documents.
    Not an optimization: ``document_ids`` is then ``[]``, and until the repository learned
    to tell an empty filter from no filter, those rungs answered with whatever else the
    organization had uploaded. Skipping them also saves an embedding call that could only
    ever have returned another course's passages.

    ``query`` defaults to the course/node title so a generator that just wants "the most
    relevant passages of this course" need not invent one.
    """
    org_id = course.org_id
    document_ids = await course_document_ids(db, course=course, node=node)
    topic = query or (node.title if node else course.title) or ""

    if document_ids:
        repo = DocumentChunkRepository(db)
        if embedding_service is not None and topic:
            try:
                embedding = await embedding_service.embed_query(topic)
                rows = await repo.similarity_search(
                    org_id=org_id,
                    query_embedding=embedding,
                    top_k=top_k,
                    document_ids=document_ids,
                )
                rows = usable_chunks(rows)
                if rows:
                    return bundle_from_chunks(rows, mode="chunks")
            except Exception as exc:  # noqa: BLE001 - a dead embedder must not cost the bundle
                logger.warning("Media grounding: vector rung failed, trying FTS: %s", exc)

        terms = sorted(query_terms(topic))
        if terms:
            try:
                rows = await repo.search_chunks_fts(
                    org_id=org_id, terms=terms, top_k=top_k, document_ids=document_ids
                )
                if rows:
                    return bundle_from_chunks(rows, mode="chunks_fts")
            except Exception as exc:  # noqa: BLE001 - same contract as the vector rung
                logger.warning(
                    "Media grounding: FTS rung failed, trying documents: %s", exc
                )

        documents = await _load_documents(db, org_id=org_id, document_ids=document_ids)
        if documents:
            bundle = bundle_from_documents(rank_documents(documents, topic))
            if not bundle.is_empty():
                return bundle

    material = await _load_course_material(db, course=course, node=node)
    bundle = bundle_from_course_material(material, course_title=course.title or "")
    if not bundle.is_empty():
        return bundle

    return GroundedBundle(mode="empty", passages=[])


__all__ = [
    "GroundingMode",
    "GroundedPassage",
    "GroundedBundle",
    "bundle_from_chunks",
    "bundle_from_course_material",
    "bundle_from_documents",
    "course_document_ids",
    "build_grounding_bundle",
]
