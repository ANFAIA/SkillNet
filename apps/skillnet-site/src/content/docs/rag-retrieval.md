---
title: "RAG y recuperación"
order: 8
section: "core"
---

---
tipo: arquitectura
tags: [rag, retrieval, embeddings, chunking, pgvector, reranking, skillnet]
fecha: 2026-07-14
---

## 3. RAG & Retrieval Architecture

Complete retrieval architecture for SkillNet: document ingestion, multi-strategy search, reranking, context assembly, embedding management, and update strategy.

Builds on top of: [[rag_condicional]] (when to use RAG vs full-text), [[fuentes_contenido]] (document sources), and the research in `07_ANFAIA/investigacion/graphify_pageindex/detalle.md` (hybrid search, PageIndex pattern, GraphRAG analysis).

---

### 3.1 Document Ingestion Pipeline

#### 3.1.1 End-to-End Flow

```
Upload (PDF/DOCX)
  |
  v
Parse & Extract Text
  |
  v
Clean & Normalize
  |
  v
Detect Structure (headings, sections, pages)
  |
  v
Decide Strategy:
  |-- pages <= 3 AND single doc --> Store as full_text (no chunking, no embeddings)
  |-- pages 4-5 AND single doc --> Configurable (default: full_text)
  |-- pages > 5 OR multiple docs --> Chunk + Embed + Store in document_chunks
  |
  v
(If chunking path):
  Semantic Chunking by Sections
    |
    v
  Fixed-size Fallback for Oversized Sections
    |
    v
  Batch Embed (multilingual-e5-small/large)
    |
    v
  Store: document_chunks + IVFFlat index
    |
    v
  Generate tsvector for Full-Text Search
```

#### 3.1.2 Parsing Libraries

| Format | Library | Why |
|--------|---------|-----|
| **PDF** | `pymupdf` (fitz) | Fast C-based extraction, preserves layout/headings, page-level text. Fallback: `pdfplumber` for table-heavy PDFs (better table detection via `pdfminer`). |
| **DOCX** | `python-docx` | Native access to `document.paragraphs` and `paragraph.style.name` (Heading 1, Heading 2, Normal). Preserves structural hierarchy natively. |
| **Plaintext** | Built-in | `open().read()` with encoding detection via `charset-normalizer`. |

**Parsing implementation:**

```python
# app/services/document_parser.py

from pathlib import Path
import fitz  # pymupdf
from docx import Document as DocxDocument

class ParsedSection:
    heading: str          # "" for body text
    level: int            # 0 = body, 1 = H1, 2 = H2, etc.
    content: str          # text content
    page_start: int       # 1-indexed
    page_end: int
    position: int         # ordinal within document

def parse_pdf(file_path: Path) -> list[ParsedSection]:
    """Extract text with structure from PDF.
    
    Strategy:
    1. Try font-size heuristic: text with font_size > median * 1.3 = heading
    2. Fall back to bold + larger font for heading detection
    3. Group contiguous non-heading text under preceding heading
    """
    doc = fitz.open(file_path)
    sections = []
    current_heading = ""
    current_level = 0
    current_content = []
    current_page_start = 1
    position = 0

    for page_num, page in enumerate(doc, 1):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                text = "".join(span["text"] for span in line["spans"]).strip()
                if not text:
                    continue
                
                # Heading detection: font size > threshold AND short line
                max_font_size = max(span["size"] for span in line["spans"])
                is_bold = any(span["flags"] & 2**4 for span in line["spans"])
                is_heading = (max_font_size > 13 or is_bold) and len(text) < 200

                if is_heading:
                    # Flush previous section
                    if current_content:
                        sections.append(ParsedSection(
                            heading=current_heading,
                            level=current_level,
                            content="\n".join(current_content),
                            page_start=current_page_start,
                            page_end=page_num,
                            position=position,
                        ))
                        position += 1
                    
                    current_heading = text
                    current_level = _estimate_heading_level(max_font_size)
                    current_content = []
                    current_page_start = page_num
                else:
                    current_content.append(text)

    # Flush final section
    if current_content:
        sections.append(ParsedSection(
            heading=current_heading,
            level=current_level,
            content="\n".join(current_content),
            page_start=current_page_start,
            page_end=len(doc),
            position=position,
        ))
    
    return sections


def parse_docx(file_path: Path) -> list[ParsedSection]:
    """Extract text with structure from DOCX.
    
    python-docx exposes paragraph.style.name directly:
    'Heading 1', 'Heading 2', 'Normal', 'List Paragraph', etc.
    """
    doc = DocxDocument(file_path)
    sections = []
    current_heading = ""
    current_level = 0
    current_content = []
    position = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        
        style = para.style.name  # e.g. "Heading 1", "Normal"
        
        if style.startswith("Heading"):
            # Flush
            if current_content:
                sections.append(ParsedSection(
                    heading=current_heading,
                    level=current_level,
                    content="\n".join(current_content),
                    page_start=0,  # DOCX doesn't have page numbers natively
                    page_end=0,
                    position=position,
                ))
                position += 1
            
            current_heading = text
            current_level = int(style.split()[-1])  # "Heading 2" -> 2
            current_content = []
        else:
            current_content.append(text)

    if current_content:
        sections.append(ParsedSection(
            heading=current_heading,
            level=current_level,
            content="\n".join(current_content),
            page_start=0,
            page_end=0,
            position=position,
        ))
    
    return sections
```

#### 3.1.3 Text Cleaning & Normalization

Applied after parsing, before chunking:

```python
def clean_text(text: str) -> str:
    """Normalize extracted text for embedding quality."""
    # 1. Collapse whitespace (PDF artifacts: multiple spaces, tabs)
    text = re.sub(r'[ \t]+', ' ', text)
    
    # 2. Normalize line breaks (keep paragraph breaks, collapse triple+)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 3. Remove header/footer artifacts (page numbers, repeated headers)
    text = re.sub(r'^\s*(?:Pagina|Page)\s+\d+\s*$', '', text, flags=re.MULTILINE)
    
    # 4. Fix hyphenation breaks from PDF column layout
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    
    # 5. Normalize unicode (NFD -> NFC for Spanish accented characters)
    text = unicodedata.normalize('NFC', text)
    
    # 6. Strip leading/trailing whitespace per line
    text = '\n'.join(line.strip() for line in text.split('\n'))
    
    return text.strip()
```

#### 3.1.4 Chunking Strategy: Semantic-First with Fixed-Size Fallback

**Algorithm:**

```
Input: list[ParsedSection] from parser
Output: list[Chunk] ready for embedding

1. For each ParsedSection:
   a. If len(tokens(section.content)) <= MAX_CHUNK_TOKENS (512):
      -> Emit as single chunk with metadata
   
   b. If len(tokens(section.content)) > MAX_CHUNK_TOKENS:
      -> Split by paragraph breaks (\n\n)
      -> Greedily merge consecutive paragraphs until approaching MAX_CHUNK_TOKENS
      -> Each sub-chunk inherits the section's heading + metadata
      -> Overlap: include last 2 sentences of previous sub-chunk as prefix (contextual overlap)
   
   c. If a single paragraph exceeds MAX_CHUNK_TOKENS:
      -> Split by sentence boundaries (regex: /[.!?]\s+/)
      -> Greedily merge sentences up to MAX_CHUNK_TOKENS
      -> 2-sentence overlap between sub-chunks

2. Minimum chunk size: 50 tokens. Chunks below this are merged with the previous chunk.

3. Every chunk gets contextual prefix:
   "[Documento: {document.title}] [Seccion: {section.heading}]\n\n{chunk_text}"
   This follows Anthropic's Contextual Retrieval pattern — the prefix helps
   the embedding model understand what the chunk is about.
```

**Parameters:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `MAX_CHUNK_TOKENS` | 512 | Sweet spot for multilingual-e5 models (trained on 512 max). Covers ~1 page of text. |
| `MIN_CHUNK_TOKENS` | 50 | Avoid meaningless fragments (single sentences with no context). |
| `OVERLAP_SENTENCES` | 2 | Enough context to avoid boundary-split answers without heavy duplication. |
| `CONTEXTUAL_PREFIX` | Yes | Document title + section heading prepended. Improves retrieval by 35% (Anthropic research). |

**Implementation:**

```python
# app/services/chunker.py

import tiktoken

MAX_CHUNK_TOKENS = 512
MIN_CHUNK_TOKENS = 50
OVERLAP_SENTENCES = 2

# Use cl100k_base as proxy for token counting (close enough for all models)
_enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_enc.encode(text))

def split_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles Spanish abbreviations."""
    # Negative lookbehind for common abbreviations (Sr., Dra., etc.)
    return re.split(r'(?<![A-Z][a-z]\.)(?<!\b(?:Sr|Sra|Dr|Dra|Ud|Uds|etc|pag|vol)\.)(?<=[.!?])\s+', text)

class Chunk:
    content: str              # The actual text
    document_id: uuid.UUID
    chunk_index: int          # Position within document
    metadata: dict            # page, section, heading, position

def chunk_sections(
    sections: list[ParsedSection],
    document_id: uuid.UUID,
    document_title: str,
) -> list[Chunk]:
    chunks = []
    chunk_index = 0

    for section in sections:
        cleaned = clean_text(section.content)
        prefix = f"[Documento: {document_title}] [Seccion: {section.heading}]"
        
        token_count = count_tokens(cleaned)

        if token_count <= MAX_CHUNK_TOKENS:
            # Section fits in one chunk
            chunks.append(Chunk(
                content=f"{prefix}\n\n{cleaned}",
                document_id=document_id,
                chunk_index=chunk_index,
                metadata={
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "heading": section.heading,
                    "heading_level": section.level,
                    "position": section.position,
                    "section_type": "complete",
                },
            ))
            chunk_index += 1
        else:
            # Split by paragraphs, then greedily merge
            paragraphs = cleaned.split("\n\n")
            current_parts = []
            current_tokens = 0
            overlap_text = ""

            for para in paragraphs:
                para_tokens = count_tokens(para)

                if para_tokens > MAX_CHUNK_TOKENS:
                    # Paragraph itself is too long — split by sentences
                    if current_parts:
                        _emit_chunk(chunks, prefix, current_parts, overlap_text,
                                    section, document_id, chunk_index)
                        overlap_text = _get_overlap(current_parts)
                        chunk_index += 1
                        current_parts = []
                        current_tokens = 0

                    sentences = split_sentences(para)
                    sent_parts = []
                    sent_tokens = 0
                    for sent in sentences:
                        st = count_tokens(sent)
                        if sent_tokens + st > MAX_CHUNK_TOKENS and sent_parts:
                            _emit_chunk(chunks, prefix, sent_parts, overlap_text,
                                        section, document_id, chunk_index)
                            overlap_text = _get_overlap(sent_parts)
                            chunk_index += 1
                            sent_parts = []
                            sent_tokens = 0
                        sent_parts.append(sent)
                        sent_tokens += st
                    if sent_parts:
                        current_parts = sent_parts
                        current_tokens = sent_tokens

                elif current_tokens + para_tokens > MAX_CHUNK_TOKENS and current_parts:
                    _emit_chunk(chunks, prefix, current_parts, overlap_text,
                                section, document_id, chunk_index)
                    overlap_text = _get_overlap(current_parts)
                    chunk_index += 1
                    current_parts = [para]
                    current_tokens = para_tokens
                else:
                    current_parts.append(para)
                    current_tokens += para_tokens

            if current_parts:
                # Merge tiny trailing chunk with previous if below minimum
                text = "\n\n".join(current_parts)
                if count_tokens(text) < MIN_CHUNK_TOKENS and chunks:
                    chunks[-1].content += "\n\n" + text
                else:
                    _emit_chunk(chunks, prefix, current_parts, overlap_text,
                                section, document_id, chunk_index)
                    chunk_index += 1

    return chunks
```

#### 3.1.5 Metadata Captured Per Chunk

| Field | Type | Source | Use |
|-------|------|--------|-----|
| `page_start` | int | PDF parser | Citation: "page 5" |
| `page_end` | int | PDF parser | Page range for multi-page sections |
| `heading` | str | Parser heading detection | Display in results, contextual prefix |
| `heading_level` | int | Parser (1=H1, 2=H2...) | Hierarchy navigation (PageIndex pattern) |
| `position` | int | Sequential counter | Reconstruct document order for context assembly |
| `section_type` | str | Chunker (`complete`, `split_N`) | Know if chunk is self-contained or partial |
| `char_count` | int | Computed | Quick size reference |
| `language` | str | Detected via `langdetect` | Potential future use for multilingual routing |

These are stored in the `metadata` JSONB column of `document_chunks`.

#### 3.1.6 Embedding Generation

**Batch processing for ingestion:**

```python
# app/services/embedder.py

from sentence_transformers import SentenceTransformer
import numpy as np

# Global model loaded once at startup
_model: SentenceTransformer | None = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("intfloat/multilingual-e5-small")
    return _model

EMBEDDING_DIM = 384  # multilingual-e5-small
BATCH_SIZE = 64      # Fits comfortably in 4GB VRAM or CPU
MAX_RETRIES = 3

async def embed_chunks(chunks: list[Chunk]) -> list[np.ndarray]:
    """Batch embed all chunks for a document.
    
    multilingual-e5 requires "passage: " prefix for documents
    and "query: " prefix for queries.
    """
    model = get_model()
    texts = [f"passage: {chunk.content}" for chunk in chunks]
    
    embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        for attempt in range(MAX_RETRIES):
            try:
                batch_embeddings = model.encode(
                    batch,
                    normalize_embeddings=True,  # L2 normalize for cosine similarity
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                # Validate dimensions
                for emb in batch_embeddings:
                    assert emb.shape == (EMBEDDING_DIM,), \
                        f"Expected dim {EMBEDDING_DIM}, got {emb.shape}"
                embeddings.extend(batch_embeddings)
                break
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(
                        f"Embedding failed after {MAX_RETRIES} attempts: {e}"
                    )
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    return embeddings


async def embed_query(query: str) -> np.ndarray:
    """Single embedding for a user query.
    
    Note the 'query: ' prefix — required by E5 models.
    """
    model = get_model()
    embedding = model.encode(
        f"query: {query}",
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    assert embedding.shape == (EMBEDDING_DIM,)
    return embedding
```

**API-based embeddings alternative (DeepSeek / OpenAI-compatible):**

```python
# app/services/embedder_api.py

import httpx

async def embed_chunks_api(
    chunks: list[Chunk],
    api_base: str,     # e.g. "https://api.deepseek.com/v1"
    api_key: str,
    model: str,         # e.g. "deepseek-embedding"
    batch_size: int = 32,
) -> list[list[float]]:
    """Embed via OpenAI-compatible API. Fallback for when local GPU is unavailable."""
    embeddings = []
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(chunks), batch_size):
            batch_texts = [f"passage: {c.content}" for c in chunks[i:i + batch_size]]
            resp = await client.post(
                f"{api_base}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"input": batch_texts, "model": model},
            )
            resp.raise_for_status()
            data = resp.json()
            batch_embs = [item["embedding"] for item in data["data"]]
            embeddings.extend(batch_embs)
    return embeddings
```

#### 3.1.7 Storage (PostgreSQL + pgvector)

```sql
-- Already decided: document_chunks table
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL,  -- or vector(1024) for e5-large
    chunk_index INTEGER NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    
    -- Full-text search column (populated on insert)
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('spanish', content)
    ) STORED,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(document_id, chunk_index)
);

-- Vector similarity index (IVFFlat, grows with data)
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);  -- Increase to sqrt(n_rows) when >10K chunks

-- Full-text search index
CREATE INDEX idx_chunks_search ON document_chunks USING GIN (search_vector);

-- Lookup by document
CREATE INDEX idx_chunks_document ON document_chunks (document_id);

-- JSONB metadata queries (e.g., filter by heading, page)
CREATE INDEX idx_chunks_metadata ON document_chunks USING GIN (metadata);
```

**Parent `documents` table context:**

```sql
-- documents table (part of the 15-table data model)
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    title TEXT NOT NULL,
    file_path TEXT,            -- S3/local path to original file
    file_type TEXT NOT NULL,   -- 'pdf', 'docx', 'txt'
    page_count INTEGER,
    full_text TEXT,            -- Stored for small docs (<=3 pages) — direct prompt path
    processing_status TEXT NOT NULL DEFAULT 'pending',  -- pending|processing|ready|failed
    embedding_model TEXT,      -- 'multilingual-e5-small' — tracks which model was used
    embedding_dim INTEGER,     -- 384 — for migration detection
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### 3.1.8 Complete Ingestion Orchestrator

```python
# app/services/ingestion.py

async def ingest_document(document_id: UUID, file_path: Path, db: AsyncSession):
    """Full pipeline: parse -> decide -> chunk -> embed -> store."""
    doc = await db.get(Document, document_id)
    doc.processing_status = "processing"
    await db.commit()

    try:
        # 1. Parse
        if file_path.suffix == ".pdf":
            sections = parse_pdf(file_path)
        elif file_path.suffix == ".docx":
            sections = parse_docx(file_path)
        else:
            sections = parse_plaintext(file_path)

        # 2. Estimate page count
        full_text = "\n\n".join(s.content for s in sections)
        estimated_pages = max(1, count_tokens(full_text) // 750)  # ~750 tokens/page
        doc.page_count = estimated_pages

        # 3. Decide strategy (RAG Conditional — see rag_condicional.md)
        if estimated_pages <= 3:
            # Small doc: store full text, no embeddings
            doc.full_text = full_text
            doc.processing_status = "ready"
            await db.commit()
            return

        # 4. Large doc: chunk + embed
        chunks = chunk_sections(sections, document_id, doc.title)

        # 5. Embed in batches
        embeddings = await embed_chunks(chunks)

        # 6. Store chunks
        for chunk, embedding in zip(chunks, embeddings):
            db_chunk = DocumentChunk(
                document_id=document_id,
                content=chunk.content,
                embedding=embedding.tolist(),
                chunk_index=chunk.chunk_index,
                metadata=chunk.metadata,
            )
            db.add(db_chunk)

        doc.embedding_model = "multilingual-e5-small"
        doc.embedding_dim = EMBEDDING_DIM
        doc.processing_status = "ready"
        await db.commit()

    except Exception as e:
        doc.processing_status = "failed"
        await db.commit()
        raise
```

---

### 3.2 Retrieval Strategies

SkillNet uses different retrieval strategies depending on the use case. All strategies operate within tenant isolation (`org_id` filter applied first).

#### 3.2.1 Strategy Selection Map

| Use Case | Strategy | Phase |
|----------|----------|-------|
| Tutor answers from **small doc** (<=3 pages) | Full text in prompt (no retrieval) | MVP |
| Tutor answers from **large doc** | Semantic search on `document_chunks` | MVP |
| Employee searches within **a course** | SQL structured (PageIndex pattern over modules/lessons) | MVP |
| Employee searches **across courses** | Hybrid (semantic + keyword) with RRF | Phase 2 |
| Admin finds **specific term** in documents | Keyword search (full-text) | Phase 1.5 |
| Course generation from **large PDF** | Semantic search + ordered retrieval | MVP |

#### 3.2.2 Semantic Search (pgvector cosine similarity)

```sql
-- Core semantic search function
CREATE OR REPLACE FUNCTION search_chunks_semantic(
    query_embedding vector(384),
    match_org_id UUID,
    match_document_id UUID DEFAULT NULL,  -- NULL = search all org docs
    match_course_id UUID DEFAULT NULL,
    match_count INT DEFAULT 10,
    match_threshold FLOAT DEFAULT 0.3     -- Minimum similarity (cosine)
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        dc.id AS chunk_id,
        dc.document_id,
        dc.content,
        dc.metadata,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM document_chunks dc
    JOIN documents d ON d.id = dc.document_id
    WHERE d.org_id = match_org_id
      AND (match_document_id IS NULL OR dc.document_id = match_document_id)
      AND (match_course_id IS NULL OR d.id IN (
          SELECT document_id FROM course_documents WHERE course_id = match_course_id
      ))
      AND 1 - (dc.embedding <=> query_embedding) > match_threshold
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
$$;
```

**Parameters and tuning:**

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `match_count` (top-K) | 10 | Retrieve 10, then rerank/filter to 3-5 for prompt. Over-retrieve to compensate for imperfect embeddings. |
| `match_threshold` | 0.3 | With normalized E5 embeddings on cosine distance, 0.3 filters noise while keeping relevant matches. Tuned empirically per domain. |
| `<=>` operator | cosine distance | E5 models are trained with cosine similarity. `<=>` is pgvector's cosine distance (1 - similarity). |

#### 3.2.3 Keyword Search (PostgreSQL Full-Text Search)

```sql
-- Full-text search with ranking
CREATE OR REPLACE FUNCTION search_chunks_keyword(
    search_query TEXT,
    match_org_id UUID,
    match_document_id UUID DEFAULT NULL,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    content TEXT,
    metadata JSONB,
    rank FLOAT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        dc.id AS chunk_id,
        dc.document_id,
        dc.content,
        dc.metadata,
        ts_rank_cd(dc.search_vector, query) AS rank
    FROM document_chunks dc
    JOIN documents d ON d.id = dc.document_id,
         plainto_tsquery('spanish', search_query) AS query
    WHERE d.org_id = match_org_id
      AND (match_document_id IS NULL OR dc.document_id = match_document_id)
      AND dc.search_vector @@ query
    ORDER BY ts_rank_cd(dc.search_vector, query) DESC
    LIMIT match_count;
$$;
```

**Why `plainto_tsquery` and not `to_tsquery`:**
- `plainto_tsquery` handles natural language input without requiring boolean syntax
- User types "plazo devoluciones 30 dias" and it works
- `to_tsquery` requires operators (`&`, `|`) — bad for end-user input
- For admin power-search: expose `websearch_to_tsquery` which supports quoted phrases and `-` negation

**Spanish language configuration:**
```sql
-- PostgreSQL ships with 'spanish' text search config
-- Includes stemming: "devoluciones" matches "devolucion", "devolver"
-- Includes stopwords: "de", "la", "en", etc.
-- If custom dictionary needed (industry terms), create a custom config
```

#### 3.2.4 Hybrid Search with Reciprocal Rank Fusion (RRF)

Combines semantic and keyword results. Used for cross-course search (Phase 2) and ambiguous queries.

```python
# app/services/retrieval.py

from dataclasses import dataclass

@dataclass
class RetrievalResult:
    chunk_id: UUID
    document_id: UUID
    content: str
    metadata: dict
    score: float
    source: str  # "semantic", "keyword", "hybrid"

RRF_K = 60  # Smoothing constant (standard: 60)

async def hybrid_search(
    query: str,
    org_id: UUID,
    document_id: UUID | None = None,
    course_id: UUID | None = None,
    top_k: int = 10,
    alpha: float = 0.5,  # 0 = keyword only, 1 = semantic only
) -> list[RetrievalResult]:
    """
    Reciprocal Rank Fusion combining semantic + keyword search.
    
    RRF formula: score(d) = sum( 1 / (K + rank_i(d)) ) for each ranker i
    
    Alpha controls the weight:
    - Automatic detection: if query has quoted terms or looks like
      exact search, shift alpha toward 0 (keyword). If question-like,
      shift toward 1 (semantic).
    """
    # 1. Detect query intent for alpha adjustment
    alpha = _adjust_alpha(query, alpha)

    # 2. Run both searches in parallel
    query_embedding = await embed_query(query)
    
    semantic_results = await db.execute(
        text("SELECT * FROM search_chunks_semantic(:emb, :org, :doc, :course, :k, 0.2)"),
        {"emb": query_embedding, "org": org_id, "doc": document_id,
         "course": course_id, "k": top_k * 2}  # Over-retrieve for fusion
    )
    
    keyword_results = await db.execute(
        text("SELECT * FROM search_chunks_keyword(:q, :org, :doc, :k)"),
        {"q": query, "org": org_id, "doc": document_id, "k": top_k * 2}
    )

    # 3. Build RRF scores
    rrf_scores: dict[UUID, float] = defaultdict(float)
    chunk_data: dict[UUID, dict] = {}

    for rank, row in enumerate(semantic_results, 1):
        rrf_scores[row.chunk_id] += alpha * (1.0 / (RRF_K + rank))
        chunk_data[row.chunk_id] = {
            "document_id": row.document_id,
            "content": row.content,
            "metadata": row.metadata,
        }

    for rank, row in enumerate(keyword_results, 1):
        rrf_scores[row.chunk_id] += (1 - alpha) * (1.0 / (RRF_K + rank))
        if row.chunk_id not in chunk_data:
            chunk_data[row.chunk_id] = {
                "document_id": row.document_id,
                "content": row.content,
                "metadata": row.metadata,
            }

    # 4. Sort by fused score, return top-K
    sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:top_k]

    return [
        RetrievalResult(
            chunk_id=cid,
            document_id=chunk_data[cid]["document_id"],
            content=chunk_data[cid]["content"],
            metadata=chunk_data[cid]["metadata"],
            score=rrf_scores[cid],
            source="hybrid",
        )
        for cid in sorted_ids
    ]


def _adjust_alpha(query: str, default: float) -> float:
    """Heuristic: shift alpha based on query pattern."""
    # Quoted terms -> keyword-heavy
    if '"' in query:
        return max(0.2, default - 0.3)
    # Question words -> semantic-heavy
    if re.match(r'^(que|como|por que|cuando|donde|cual|explicame|dime)\b', query, re.I):
        return min(0.8, default + 0.2)
    # Short (1-2 words) -> keyword-heavy
    if len(query.split()) <= 2:
        return max(0.3, default - 0.2)
    return default
```

#### 3.2.5 Structured Filters (Pre-filter before Vector Search)

All searches are scoped by tenant and optionally by document/course. This is enforced at the SQL level (see `WHERE d.org_id = match_org_id` in the functions above).

Available filters:

| Filter | Column | Applied To | Example |
|--------|--------|-----------|---------|
| `org_id` | `documents.org_id` | **Always** (tenant isolation) | Mandatory |
| `document_id` | `document_chunks.document_id` | Tutor answering from specific doc | "Answer from this manual" |
| `course_id` | via `course_documents` join | In-course tutor | "Find in this course's materials" |
| `heading` | `metadata->>'heading'` | Section-specific search | "Find in 'Politica de Devoluciones'" |
| `page_range` | `metadata->>'page_start'` | Page-scoped retrieval | "What does page 5 say?" |

**Filter application order:**
1. `org_id` (RLS or explicit WHERE — non-negotiable)
2. `document_id` or `course_id` (narrows the search space — helps IVFFlat performance)
3. Vector/keyword search on filtered subset
4. Threshold + top-K applied last

#### 3.2.6 PageIndex Pattern (SQL-based Tree Navigation)

For **in-course** content navigation — when an employee asks a question while taking a course. No embeddings needed because the content is already structured in PostgreSQL.

```python
# app/services/retrieval_course.py

async def retrieve_for_course_tutor(
    question: str,
    course_id: UUID,
    db: AsyncSession,
) -> str:
    """
    PageIndex pattern implemented with SQL.
    
    Step 1: Fetch module titles + summaries (the 'tree')
    Step 2: LLM reasons which module is relevant
    Step 3: Fetch that module's lesson content
    """
    # Step 1: Get the tree (cheap SQL query)
    modules = await db.execute(
        text("""
            SELECT id, title, summary, sort_order
            FROM modules
            WHERE course_id = :course_id
            ORDER BY sort_order
        """),
        {"course_id": course_id}
    )
    
    tree = "\n".join(
        f"- Modulo {m.sort_order}: {m.title} — {m.summary}"
        for m in modules
    )

    # Step 2: LLM picks the relevant module(s)
    selection_prompt = f"""Given this course structure:
{tree}

The employee asks: "{question}"

Which module number(s) contain the answer? Reply with just the number(s), comma-separated."""

    selected = await llm.generate(selection_prompt, max_tokens=20)
    module_ids = _parse_module_selection(selected, modules)

    # Step 3: Fetch content of selected module(s)
    lessons = await db.execute(
        text("""
            SELECT title, content
            FROM lessons
            WHERE module_id = ANY(:module_ids)
            ORDER BY sort_order
        """),
        {"module_ids": module_ids}
    )

    context = "\n\n".join(
        f"### {l.title}\n{l.content}" for l in lessons
    )
    
    return context
```

**Cost:** 2 SQL queries + 1 short LLM call (~20 tokens output). Cheaper and more precise than vector search for structured content.

**When to use PageIndex vs semantic search:**

| Signal | Use PageIndex | Use Semantic Search |
|--------|--------------|-------------------|
| User is inside a course | Yes | No |
| Question about specific topic in a known doc | Yes | No |
| Free-text search across all content | No | Yes |
| User doesn't know which doc has the answer | No | Yes |

---

### 3.3 Reranking

Optional cross-encoder reranking applied **after** retrieval, **before** context assembly. Improves precision at the cost of latency.

#### 3.3.1 When to Use

| Scenario | Rerank? | Why |
|----------|---------|-----|
| Tutor answering employee question | **No** (MVP), **Yes** (Phase 2) | Speed matters for chat. Add when latency budget allows. |
| Course generation (ingestion time) | **Yes** | Not real-time. Higher precision = better generated content. |
| Cross-course search | **Yes** | Results from different docs need quality ranking. |
| Small doc (full text in prompt) | **No** | No retrieval = nothing to rerank. |

#### 3.3.2 Implementation

```python
# app/services/reranker.py

from sentence_transformers import CrossEncoder

# Lazy-loaded, only when reranking is enabled
_reranker: CrossEncoder | None = None

def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        # ms-marco-MiniLM is small (66MB), fast, and good enough
        # For better multilingual: jeffwan/mmarco-mMiniLMv2-L12-H384-v1
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker

async def rerank(
    query: str,
    results: list[RetrievalResult],
    top_k: int = 5,
) -> list[RetrievalResult]:
    """
    Cross-encoder reranking.
    
    Unlike bi-encoder (embedding model), cross-encoder sees query+passage
    together, enabling deeper semantic matching at the cost of speed.
    
    Typical improvement: 15-30% precision gain over bi-encoder alone.
    Latency cost: ~50-100ms for 10 candidates on CPU.
    """
    if len(results) <= 1:
        return results

    reranker = get_reranker()
    pairs = [(query, r.content) for r in results]
    scores = reranker.predict(pairs)

    # Attach reranker scores
    for result, score in zip(results, scores):
        result.score = float(score)

    # Sort by reranker score and return top-K
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]
```

#### 3.3.3 API-based Reranking Alternative

For deployments without local GPU, use Cohere Rerank or Jina Reranker API:

```python
async def rerank_api(
    query: str,
    results: list[RetrievalResult],
    top_k: int = 5,
    api_key: str = None,
) -> list[RetrievalResult]:
    """Cohere Rerank API — pay-per-query, no local model needed."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.cohere.ai/v1/rerank",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "query": query,
                "documents": [r.content for r in results],
                "top_n": top_k,
                "model": "rerank-multilingual-v3.0",
            },
        )
        resp.raise_for_status()
        ranked = resp.json()["results"]
        
    reranked = []
    for item in ranked:
        idx = item["index"]
        results[idx].score = item["relevance_score"]
        reranked.append(results[idx])
    return reranked
```

---

### 3.4 Context Assembly

How retrieved chunks are assembled into the final LLM prompt.

#### 3.4.1 Pipeline

```
Retrieved chunks (10-20 from retrieval)
  |
  v
Rerank (optional) -> top 5
  |
  v
Deduplicate (by content hash + overlap detection)
  |
  v
Order (by document position, not relevance score)
  |
  v
Token budget check (fit within context window)
  |
  v
Inject citation metadata
  |
  v
Assemble prompt:
  [System prompt]
  [Context block with citations]
  [User question]
```

#### 3.4.2 Deduplication

Chunks may overlap (contextual overlap from chunking) or appear in both semantic and keyword results.

```python
def deduplicate_chunks(chunks: list[RetrievalResult]) -> list[RetrievalResult]:
    """Remove near-duplicate chunks. Keep highest-scored version."""
    seen_hashes: set[str] = set()
    deduplicated = []
    
    for chunk in sorted(chunks, key=lambda c: c.score, reverse=True):
        # Hash on first 200 chars (handles overlap prefixes)
        content_hash = hashlib.md5(chunk.content[:200].encode()).hexdigest()
        
        if content_hash in seen_hashes:
            continue
        
        # Check for high textual overlap with already-selected chunks
        is_duplicate = False
        for selected in deduplicated:
            overlap = _calculate_overlap(chunk.content, selected.content)
            if overlap > 0.7:  # 70% overlap threshold
                is_duplicate = True
                break
        
        if not is_duplicate:
            seen_hashes.add(content_hash)
            deduplicated.append(chunk)
    
    return deduplicated


def _calculate_overlap(a: str, b: str) -> float:
    """Jaccard similarity on word sets."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)
```

#### 3.4.3 Ordering Strategy

After deduplication, chunks are reordered by **document position** (not relevance score). This preserves the narrative flow of the source document, which helps the LLM generate coherent answers.

```python
def order_chunks(chunks: list[RetrievalResult]) -> list[RetrievalResult]:
    """
    Order by: document_id (group), then chunk position within document.
    
    Why document order instead of relevance order:
    - LLMs handle in-order context better than shuffled fragments
    - Avoids the "lost in the middle" problem (relevant info buried)
    - The user sees a coherent narrative, not disjointed snippets
    """
    return sorted(chunks, key=lambda c: (
        str(c.document_id),                      # Group by document
        c.metadata.get("position", 0),           # Then by position in doc
    ))
```

#### 3.4.4 Token Budget Management

```python
# Token budget allocation for the LLM prompt
BUDGET = {
    "system_prompt": 500,       # Fixed system instructions
    "context_chunks": None,     # Dynamic — fills remaining budget
    "user_question": 200,       # User input (rarely exceeds this)
    "response_reserve": 2000,   # Reserved for LLM response generation
}

# Total available depends on model
MODEL_CONTEXT_LIMITS = {
    "gpt-4o": 128_000,
    "claude-3.5-sonnet": 200_000,
    "deepseek-v3": 64_000,
    "default": 16_000,  # Conservative fallback
}

def fit_to_budget(
    chunks: list[RetrievalResult],
    model: str = "default",
) -> list[RetrievalResult]:
    """
    Greedily add chunks until token budget is exhausted.
    Chunks are already ordered by document position.
    """
    max_context_tokens = (
        MODEL_CONTEXT_LIMITS.get(model, MODEL_CONTEXT_LIMITS["default"])
        - BUDGET["system_prompt"]
        - BUDGET["user_question"]
        - BUDGET["response_reserve"]
    )
    
    selected = []
    total_tokens = 0
    
    for chunk in chunks:
        chunk_tokens = count_tokens(chunk.content)
        if total_tokens + chunk_tokens > max_context_tokens:
            break
        selected.append(chunk)
        total_tokens += chunk_tokens
    
    return selected
```

#### 3.4.5 Citation Metadata Injection

Each chunk in the prompt gets a citation tag. The LLM is instructed to reference these tags in its answer.

```python
def assemble_context_block(chunks: list[RetrievalResult]) -> str:
    """Build the context block for the LLM prompt with citation markers."""
    blocks = []
    
    for i, chunk in enumerate(chunks, 1):
        doc_title = chunk.metadata.get("document_title", "Documento")
        heading = chunk.metadata.get("heading", "")
        page = chunk.metadata.get("page_start", "")
        
        citation = f"[Fuente {i}: {doc_title}"
        if heading:
            citation += f" > {heading}"
        if page:
            citation += f", pag. {page}"
        citation += "]"
        
        blocks.append(f"{citation}\n{chunk.content}")
    
    return "\n\n---\n\n".join(blocks)


def build_prompt(
    system_prompt: str,
    context_block: str,
    user_question: str,
) -> list[dict]:
    """Assemble the final prompt for the LLM."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"""Contexto de la empresa (usa SOLO esta informacion para responder):

{context_block}

---

Pregunta del empleado: {user_question}

Instrucciones:
- Responde basandote SOLO en el contexto anterior.
- Cita la fuente usando [Fuente N] al final de cada afirmacion.
- Si la informacion no esta en el contexto, di "No tengo informacion sobre esto en los documentos disponibles."
- Responde en el mismo idioma que la pregunta."""},
    ]
```

> **SUPERSEDED (2026-07-27).** The last instruction is the bug, not the contract. Measured
> in the demo organization: three documents, 6 710 characters of `full_text`, **zero**
> chunks and zero embeddings — because a document at or under 5 pages takes the
> `full_text` branch of `load_source_context` (§4.2) and is never chunked — so this branch
> fired on every question ever asked and the tutor refused every one of them.
>
> An empty retrieval is now a *rung*, not a dead end. `ground_question` in
> `src/services/retrieval.py` walks **chunks -> the whole enrolled document -> general
> knowledge** and returns which rung it stood on. Two details worth carrying into any
> future revision of this document:
>
> - A hit below `SIMILARITY_FLOOR` (0.25) counts as no hit. That is not a relevance
>   threshold — real sentence embeddings never come back that low — it is how a
>   non-semantic embedder is told apart from a real one. Measured with
>   `EMBEDDING_MODEL=fixture/local`, which is what `.env` configures locally: the five
>   best "hits" for *"¿Qué son los alérgenos?"* scored 0.107, 0.105, 0.070, 0.058, 0.053,
>   i.e. random. Without the floor the tutor answers an allergen question from a chunk
>   about the cash float, which is worse than the refusal because it looks right.
> - The whole-document rung orders documents by a lexical term count, accent-folded. The
>   demo's most likely question shares zero literal terms with the document that answers
>   it (`alérgenos` vs `alergenos`), and without folding the ranking is arbitrary.

---

### 3.5 Embedding Model Management

#### 3.5.1 Model Configuration

```python
# app/config.py

from pydantic_settings import BaseSettings

class EmbeddingConfig(BaseSettings):
    # Model selection
    EMBEDDING_PROVIDER: str = "local"       # "local" | "api"
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"
    EMBEDDING_DIM: int = 384
    
    # API config (only if EMBEDDING_PROVIDER == "api")
    EMBEDDING_API_BASE: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_API_MODEL: str = ""
    
    # Processing
    EMBEDDING_BATCH_SIZE: int = 64          # Local: 64, API: 32
    EMBEDDING_MAX_RETRIES: int = 3
    
    # Prefixes (E5 models require these)
    EMBEDDING_PASSAGE_PREFIX: str = "passage: "
    EMBEDDING_QUERY_PREFIX: str = "query: "
```

#### 3.5.2 Model Switching (Dimension Change = Reindex)

Switching from `multilingual-e5-small` (384d) to `multilingual-e5-large` (1024d) requires:

1. **Schema migration:** `ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1024);`
2. **Drop + recreate IVFFlat index** (cannot alter vector dimensions in-place)
3. **Re-embed all existing chunks** (batch job)
4. **Update `documents.embedding_model` and `documents.embedding_dim`** for all affected docs

```python
# app/services/model_migration.py

async def migrate_embedding_model(
    old_model: str,
    new_model: str,
    new_dim: int,
    db: AsyncSession,
):
    """
    Full re-embedding migration.
    
    Strategy: create new column, populate in background, swap columns.
    This avoids downtime — old embeddings serve queries while new ones generate.
    """
    # 1. Add new column
    await db.execute(text(
        f"ALTER TABLE document_chunks ADD COLUMN embedding_new vector({new_dim})"
    ))
    
    # 2. Re-embed all chunks in batches
    chunks = await db.execute(text(
        "SELECT id, content FROM document_chunks ORDER BY id"
    ))
    
    batch = []
    for row in chunks:
        batch.append(row)
        if len(batch) >= 64:
            embeddings = await embed_chunks_with_model(batch, new_model)
            for chunk_row, emb in zip(batch, embeddings):
                await db.execute(text(
                    "UPDATE document_chunks SET embedding_new = :emb WHERE id = :id"
                ), {"emb": emb, "id": chunk_row.id})
            batch = []
    # Process remaining
    if batch:
        embeddings = await embed_chunks_with_model(batch, new_model)
        for chunk_row, emb in zip(batch, embeddings):
            await db.execute(text(
                "UPDATE document_chunks SET embedding_new = :emb WHERE id = :id"
            ), {"emb": emb, "id": chunk_row.id})
    
    # 3. Swap columns (atomic)
    await db.execute(text("ALTER TABLE document_chunks DROP COLUMN embedding"))
    await db.execute(text(
        "ALTER TABLE document_chunks RENAME COLUMN embedding_new TO embedding"
    ))
    
    # 4. Recreate index
    await db.execute(text("DROP INDEX IF EXISTS idx_chunks_embedding"))
    await db.execute(text(
        f"CREATE INDEX idx_chunks_embedding ON document_chunks "
        f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    ))
    
    # 5. Update all document records
    await db.execute(text(
        "UPDATE documents SET embedding_model = :model, embedding_dim = :dim "
        "WHERE embedding_model IS NOT NULL"
    ), {"model": new_model, "dim": new_dim})
    
    await db.commit()
```

#### 3.5.3 Local vs API Embeddings

| Aspect | Local (`sentence-transformers`) | API (DeepSeek / OpenAI-compatible) |
|--------|-------------------------------|--------------------------------------|
| **Latency** | ~10ms per chunk (GPU), ~50ms (CPU) | ~100-300ms per batch (network) |
| **Cost** | Free (hardware cost only) | ~$0.01-0.10 per 1M tokens |
| **Privacy** | Data never leaves server | Data sent to API provider |
| **RAM** | ~500MB (e5-small), ~2GB (e5-large) | None |
| **Quality** | Excellent for multilingual | Varies by provider |
| **Offline** | Works without internet | Requires internet |
| **Recommended** | Self-hosted instances (privacy, offline) | SaaS instances (no GPU, lower maintenance) |

**Default for MVP:** Local `multilingual-e5-small` (384d). Runs on CPU, no GPU needed for SME-scale (~10K chunks).

#### 3.5.4 Batch vs Single Embedding

| Operation | Mode | Why |
|-----------|------|-----|
| Document ingestion | **Batch** (64 chunks at a time) | Throughput: GPU parallelism, API rate limits. |
| User query | **Single** (1 embedding) | Latency: user is waiting. One call, ~10ms. |
| Model migration | **Batch** (64 chunks) | Same as ingestion — background job. |

---

### 3.6 Update Strategy

When source documents change (admin uploads new version, or edits content).

#### 3.6.1 Full Re-ingestion (Default)

**When:** Admin uploads a new version of a document or replaces the file.

```python
async def update_document(document_id: UUID, new_file_path: Path, db: AsyncSession):
    """Replace all chunks with new content. Atomic."""
    
    # 1. Delete old chunks
    await db.execute(
        text("DELETE FROM document_chunks WHERE document_id = :doc_id"),
        {"doc_id": document_id}
    )
    
    # 2. Clear old full_text if any
    await db.execute(
        text("UPDATE documents SET full_text = NULL WHERE id = :doc_id"),
        {"doc_id": document_id}
    )
    
    # 3. Re-run full ingestion pipeline
    await ingest_document(document_id, new_file_path, db)
```

**Why full re-ingestion over incremental:**
- Documents in SME context are typically <100 pages (seconds to re-process)
- Incremental diffing of PDF content is fragile (layout changes = false diffs)
- Section reordering in a new doc version would corrupt chunk indices
- Full re-ingestion is simple, correct, and fast enough for the expected scale

#### 3.6.2 When to NOT Re-ingest

| Scenario | Action | Why |
|----------|--------|-----|
| Admin edits metadata (title, tags) | Update `documents` row only | Chunk content unchanged |
| Admin edits a course (not the source doc) | No document re-ingestion | Course content is separate from source docs |
| Admin archives a document | Soft-delete (status = 'archived') | Preserves history, excludes from search |

#### 3.6.3 Chunk Versioning Considerations

For the MVP, SkillNet uses **replace-on-update** (no versioning). This means:

- Old chunks are deleted when a document is re-ingested
- Any course that referenced specific chunk IDs may have dangling references
- Mitigation: courses reference `document_id` + `heading` (not `chunk_id`), so they survive re-ingestion as long as the heading structure is preserved

**Phase 2 consideration:** If audit trails or historical comparisons are needed:

```sql
-- Future: version tracking
ALTER TABLE document_chunks ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE document_chunks ADD COLUMN superseded_by UUID REFERENCES document_chunks(id);

-- On update: mark old chunks as superseded rather than deleting
-- Queries filter: WHERE superseded_by IS NULL
```

This is deferred because:
1. SMEs rarely need version history of training documents
2. It adds query complexity (every search must filter `superseded_by IS NULL`)
3. Storage grows with every edit (embeddings are ~1.5KB per chunk at 384d)

#### 3.6.4 Cascading Updates to Generated Content

When a source document is updated, courses generated from it may be outdated. SkillNet handles this with notifications, not automatic regeneration:

```
Document updated
  |
  v
Re-ingest (new chunks + embeddings)
  |
  v
Check: any courses linked to this document?
  |-- Yes --> Mark course as "fuente actualizada — revisar"
  |           Notify admin: "El manual de devoluciones se actualizo.
  |                          El curso 'Devoluciones' podria necesitar revision."
  |           Admin decides: regenerate modules, or ignore.
  |-- No  --> Done
```

The admin stays in control. SkillNet does not silently regenerate course content.

---

### 3.7 Architecture Summary

```
                    INGESTION                              RETRIEVAL
                    =========                              =========

  PDF/DOCX                                    Employee question
     |                                              |
     v                                              v
  [Parser]                                    [Query Router]
  pymupdf / python-docx                            |
     |                                     +-------+--------+
     v                                     |       |        |
  [Cleaner]                          Small doc  In-course  Cross-content
  normalize, fix artifacts           (full text) (PageIndex) (Hybrid)
     |                                   |       |        |
     v                                   v       v        v
  [Chunker]                         Full text   SQL    Semantic +
  semantic sections +               to prompt  tree    Keyword
  fixed-size fallback                           nav    (RRF)
     |                                              |
     v                                              v
  [Embedder]                                  [Reranker] (optional)
  multilingual-e5-small                       cross-encoder
  batch of 64                                      |
     |                                              v
     v                                        [Deduplicator]
  [PostgreSQL]                                     |
  document_chunks table                            v
  + IVFFlat index                             [Orderer]
  + GIN index (tsvector)                      by doc position
                                                   |
                                                   v
                                              [Budget Manager]
                                              fit to context window
                                                   |
                                                   v
                                              [Prompt Assembler]
                                              citations + instructions
                                                   |
                                                   v
                                              [LLM] --> Response with [Fuente N]
```

---

### 3.8 Configuration Defaults (MVP)

| Parameter | Value | Note |
|-----------|-------|------|
| Embedding model | `multilingual-e5-small` | 384 dims, ~500MB RAM, CPU-friendly |
| Chunk size | 512 tokens max | Aligned with E5 training window |
| Chunk overlap | 2 sentences | Prevents boundary-split answers |
| Contextual prefix | Yes | Document title + section heading |
| IVFFlat lists | 10 | Grow to `sqrt(n)` when >10K chunks |
| Semantic top-K | 10 | Over-retrieve, then filter to 3-5 |
| Similarity threshold | 0.3 | Cosine, with normalized embeddings |
| RRF K constant | 60 | Standard value from literature |
| Hybrid alpha | 0.5 | Auto-adjusted by query heuristic |
| Reranking | Disabled (MVP) | Enable Phase 2 for cross-course search |
| Full-text search config | `spanish` | PostgreSQL built-in, includes stemming |
| Token budget for context | Model-dependent | Conservative: 16K minus reserves |
| Batch size (embedding) | 64 (local), 32 (API) | Balance throughput vs memory |

---

### 3.9 Phase Rollout

| Phase | What | Retrieval Strategy |
|-------|------|--------------------|
| **MVP** | Single-doc tutor, course generation | Full text (small docs) + semantic search (large docs) + PageIndex (in-course) |
| **1.5** | Keyword search in admin panel | + `tsvector` full-text search |
| **2** | Cross-course search, combined search UI | + Hybrid RRF + reranking + origin labels |
| **2+** | Large PDF optimization | + PageIndex pattern for ingestion |
| **3** | Inter-course relationships | + Structured metadata queries + prerequisite graph |
| **3+** | GraphRAG (if >100 courses) | + Community detection for thematic exploration |
