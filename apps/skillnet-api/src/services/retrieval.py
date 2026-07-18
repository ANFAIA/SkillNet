"""RAG retrieval: embed query, semantic search, assemble cited context.

The dedupe / order / citation-format steps are pure functions operating on plain
chunk dicts so they can be unit-tested without a DB or network.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.llm.embedding import EmbeddingService
from src.repositories.document_chunk_repo import DocumentChunkRepository

_HASH_PREFIX_CHARS = 200


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
    if not rows:
        return "", []
    return assemble_context(order_chunks(dedupe_chunks(rows)))
