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

## 3. Arquitectura de RAG y recuperación

Arquitectura de recuperación completa para SkillNet: ingesta de documentos, búsqueda multiestrategia, reranking, ensamblado de contexto, gestión de embeddings y estrategia de actualización.

Se apoya en: [[rag_condicional]] (cuándo usar RAG frente a texto completo), [[fuentes_contenido]] (fuentes de documentos) y la investigación en `07_ANFAIA/investigacion/graphify_pageindex/detalle.md` (búsqueda híbrida, patrón PageIndex, análisis de GraphRAG).

---

### 3.1 Pipeline de ingesta de documentos

#### 3.1.1 Flujo de extremo a extremo

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

#### 3.1.2 Librerías de parsing

| Formato | Librería | Por qué |
|--------|---------|-----|
| **PDF** | `pymupdf` (fitz) | Extracción rápida basada en C, preserva el layout/encabezados, texto a nivel de página. Fallback: `pdfplumber` para PDFs con muchas tablas (mejor detección de tablas vía `pdfminer`). |
| **DOCX** | `python-docx` | Acceso nativo a `document.paragraphs` y `paragraph.style.name` (Heading 1, Heading 2, Normal). Preserva la jerarquía estructural de forma nativa. |
| **Texto plano** | Integrado | `open().read()` con detección de codificación vía `charset-normalizer`. |

**Implementación del parsing:**

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

#### 3.1.3 Limpieza y normalización de texto

Se aplica tras el parsing, antes del chunking:

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

#### 3.1.4 Estrategia de chunking: semántica primero, con fallback de tamaño fijo

**Algoritmo:**

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

**Parámetros:**

| Parámetro | Valor | Justificación |
|-----------|-------|-----------|
| `MAX_CHUNK_TOKENS` | 512 | Punto óptimo para los modelos multilingual-e5 (entrenados con un máximo de 512). Cubre ~1 página de texto. |
| `MIN_CHUNK_TOKENS` | 50 | Evita fragmentos sin sentido (frases sueltas sin contexto). |
| `OVERLAP_SENTENCES` | 2 | Contexto suficiente para evitar respuestas cortadas en el límite del chunk sin duplicación excesiva. |
| `CONTEXTUAL_PREFIX` | Sí | Título del documento + encabezado de sección antepuestos. Mejora la recuperación un 35% (investigación de Anthropic). |

**Implementación:**

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

#### 3.1.5 Metadatos capturados por chunk

| Campo | Tipo | Origen | Uso |
|-------|------|--------|-----|
| `page_start` | int | Parser de PDF | Cita: "página 5" |
| `page_end` | int | Parser de PDF | Rango de páginas para secciones multipágina |
| `heading` | str | Detección de encabezados del parser | Mostrar en resultados, prefijo contextual |
| `heading_level` | int | Parser (1=H1, 2=H2...) | Navegación jerárquica (patrón PageIndex) |
| `position` | int | Contador secuencial | Reconstruir el orden del documento para el ensamblado de contexto |
| `section_type` | str | Chunker (`complete`, `split_N`) | Saber si el chunk es autocontenido o parcial |
| `char_count` | int | Calculado | Referencia rápida de tamaño |
| `language` | str | Detectado vía `langdetect` | Posible uso futuro para enrutamiento multilingüe |

Se almacenan en la columna JSONB `metadata` de `document_chunks`.

#### 3.1.6 Generación de embeddings

**Procesamiento por lotes para la ingesta:**

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

**Alternativa de embeddings vía API (DeepSeek / compatible con OpenAI):**

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

#### 3.1.7 Almacenamiento (PostgreSQL + pgvector)

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

**Contexto de la tabla padre `documents`:**

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

#### 3.1.8 Orquestador completo de ingesta

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

### 3.2 Estrategias de recuperación

SkillNet usa diferentes estrategias de recuperación según el caso de uso. Todas las estrategias operan dentro del aislamiento por tenant (el filtro `org_id` se aplica primero).

#### 3.2.1 Mapa de selección de estrategia

| Caso de uso | Estrategia | Fase |
|----------|----------|-------|
| El tutor responde desde un **documento pequeño** (<=3 páginas) | Texto completo en el prompt (sin recuperación) | MVP |
| El tutor responde desde un **documento grande** | Búsqueda semántica sobre `document_chunks` | MVP |
| El empleado busca dentro de **un curso** | SQL estructurado (patrón PageIndex sobre módulos/lecciones) | MVP |
| El empleado busca **entre cursos** | Híbrida (semántica + palabra clave) con RRF | Fase 2 |
| El admin busca un **término específico** en documentos | Búsqueda por palabra clave (texto completo) | Fase 1.5 |
| Generación de curso a partir de un **PDF grande** | Búsqueda semántica + recuperación ordenada | MVP |

#### 3.2.2 Búsqueda semántica (similitud coseno con pgvector)

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

**Parámetros y ajuste:**

| Parámetro | Valor por defecto | Justificación |
|-----------|---------|-----------|
| `match_count` (top-K) | 10 | Recuperar 10 y luego reordenar/filtrar a 3-5 para el prompt. Se sobre-recupera para compensar embeddings imperfectos. |
| `match_threshold` | 0.3 | Con embeddings E5 normalizados sobre distancia coseno, 0.3 filtra ruido manteniendo coincidencias relevantes. Ajustado empíricamente por dominio. |
| Operador `<=>` | distancia coseno | Los modelos E5 se entrenan con similitud coseno. `<=>` es la distancia coseno de pgvector (1 - similitud). |

#### 3.2.3 Búsqueda por palabra clave (búsqueda de texto completo de PostgreSQL)

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

**Por qué `plainto_tsquery` y no `to_tsquery`:**
- `plainto_tsquery` gestiona entradas en lenguaje natural sin requerir sintaxis booleana
- El usuario escribe "plazo devoluciones 30 dias" y funciona
- `to_tsquery` requiere operadores (`&`, `|`) — malo para la entrada del usuario final
- Para la búsqueda avanzada del admin: exponer `websearch_to_tsquery`, que admite frases entre comillas y negación con `-`

**Configuración del idioma español:**
```sql
-- PostgreSQL ships with 'spanish' text search config
-- Includes stemming: "devoluciones" matches "devolucion", "devolver"
-- Includes stopwords: "de", "la", "en", etc.
-- If custom dictionary needed (industry terms), create a custom config
```

#### 3.2.4 Búsqueda híbrida con Reciprocal Rank Fusion (RRF)

Combina resultados semánticos y por palabra clave. Se usa para la búsqueda entre cursos (Fase 2) y consultas ambiguas.

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

#### 3.2.5 Filtros estructurados (pre-filtrado antes de la búsqueda vectorial)

Todas las búsquedas están acotadas por tenant y, opcionalmente, por documento/curso. Esto se aplica a nivel de SQL (véase `WHERE d.org_id = match_org_id` en las funciones anteriores).

Filtros disponibles:

| Filtro | Columna | Se aplica a | Ejemplo |
|--------|--------|-----------|---------|
| `org_id` | `documents.org_id` | **Siempre** (aislamiento por tenant) | Obligatorio |
| `document_id` | `document_chunks.document_id` | El tutor responde desde un documento específico | "Responde desde este manual" |
| `course_id` | vía join con `course_documents` | Tutor dentro del curso | "Busca en el material de este curso" |
| `heading` | `metadata->>'heading'` | Búsqueda específica de sección | "Busca en 'Política de Devoluciones'" |
| `page_range` | `metadata->>'page_start'` | Recuperación acotada por página | "¿Qué dice la página 5?" |

**Orden de aplicación de filtros:**
1. `org_id` (RLS o WHERE explícito — innegociable)
2. `document_id` o `course_id` (acota el espacio de búsqueda — ayuda al rendimiento de IVFFlat)
3. Búsqueda vectorial/por palabra clave sobre el subconjunto filtrado
4. Umbral + top-K aplicados al final

#### 3.2.6 Patrón PageIndex (navegación en árbol basada en SQL)

Para la navegación de contenido **dentro de un curso** — cuando un empleado hace una pregunta mientras realiza un curso. No hacen falta embeddings porque el contenido ya está estructurado en PostgreSQL.

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

**Coste:** 2 consultas SQL + 1 llamada corta al LLM (~20 tokens de salida). Más barato y más preciso que la búsqueda vectorial para contenido estructurado.

**Cuándo usar PageIndex frente a búsqueda semántica:**

| Señal | Usar PageIndex | Usar búsqueda semántica |
|--------|--------------|-------------------|
| El usuario está dentro de un curso | Sí | No |
| Pregunta sobre un tema concreto en un documento conocido | Sí | No |
| Búsqueda de texto libre en todo el contenido | No | Sí |
| El usuario no sabe en qué documento está la respuesta | No | Sí |

---

### 3.3 Reranking

Reranking opcional con cross-encoder aplicado **después** de la recuperación, **antes** del ensamblado de contexto. Mejora la precisión a costa de latencia.

#### 3.3.1 Cuándo usarlo

| Escenario | ¿Rerank? | Por qué |
|----------|---------|-----|
| El tutor responde a la pregunta de un empleado | **No** (MVP), **Sí** (Fase 2) | La velocidad importa en el chat. Se añade cuando el presupuesto de latencia lo permite. |
| Generación de curso (en tiempo de ingesta) | **Sí** | No es en tiempo real. Mayor precisión = mejor contenido generado. |
| Búsqueda entre cursos | **Sí** | Los resultados de distintos documentos necesitan un ranking de calidad. |
| Documento pequeño (texto completo en el prompt) | **No** | Sin recuperación no hay nada que reordenar. |

#### 3.3.2 Implementación

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

#### 3.3.3 Alternativa de reranking vía API

Para despliegues sin GPU local, usar la API de Cohere Rerank o Jina Reranker:

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

### 3.4 Ensamblado de contexto

Cómo se ensamblan los chunks recuperados en el prompt final del LLM.

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

#### 3.4.2 Deduplicación

Los chunks pueden solaparse (solapamiento contextual del chunking) o aparecer tanto en resultados semánticos como por palabra clave.

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

#### 3.4.3 Estrategia de ordenación

Tras la deduplicación, los chunks se reordenan por **posición en el documento** (no por puntuación de relevancia). Esto preserva el flujo narrativo del documento fuente, lo que ayuda al LLM a generar respuestas coherentes.

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

#### 3.4.4 Gestión del presupuesto de tokens

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

#### 3.4.5 Inyección de metadatos de citación

Cada chunk del prompt recibe una etiqueta de citación. Se instruye al LLM para que referencie estas etiquetas en su respuesta.

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

> **SUSTITUIDO (2026-07-27).** La última instrucción es el bug, no el contrato. Medido
> en la organización de la demo: tres documentos, 6.710 caracteres de `full_text`, **cero**
> chunks y cero embeddings — porque un documento de 5 páginas o menos toma la rama
> `full_text` de `load_source_context` (§4.2) y nunca se trocea — así que esta rama
> saltaba en cada pregunta que se hacía y el tutor las rechazaba todas.
>
> Una recuperación vacía es ahora un *peldaño*, no un callejón sin salida. `ground_question`
> en `src/services/retrieval.py` recorre **chunks -> el documento matriculado completo ->
> conocimiento general** y devuelve en qué peldaño se quedó. Dos detalles que merece la pena
> arrastrar a cualquier revisión futura de este documento:
>
> - Un resultado por debajo de `SIMILARITY_FLOOR` (0,25) cuenta como no-resultado. Eso no es
>   un umbral de relevancia — los embeddings de frases reales nunca bajan tanto — es la forma
>   de distinguir un embedder no semántico de uno real. Medido con
>   `EMBEDDING_MODEL=fixture/local`, que es lo que configura `.env` en local: los cinco
>   mejores "resultados" para *"¿Qué son los alérgenos?"* puntuaron 0,107, 0,105, 0,070,
>   0,058, 0,053, es decir, al azar. Sin el suelo, el tutor responde una pregunta sobre
>   alérgenos con un chunk sobre el fondo de caja, lo cual es peor que la negativa porque
>   parece correcto.
> - El peldaño de documento completo ordena los documentos por un recuento léxico de
>   términos, con el acento normalizado. La pregunta más probable de la demo no comparte
>   ningún término literal con el documento que la responde (`alérgenos` frente a
>   `alergenos`), y sin esa normalización el ranking sería arbitrario.

---

### 3.5 Gestión del modelo de embeddings

#### 3.5.1 Configuración del modelo

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

#### 3.5.2 Cambio de modelo (cambio de dimensión = reindexado)

Pasar de `multilingual-e5-small` (384d) a `multilingual-e5-large` (1024d) requiere:

1. **Migración de esquema:** `ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1024);`
2. **Eliminar y recrear el índice IVFFlat** (no se pueden alterar las dimensiones del vector in situ)
3. **Reincrustar todos los chunks existentes** (trabajo por lotes)
4. **Actualizar `documents.embedding_model` y `documents.embedding_dim`** para todos los documentos afectados

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

#### 3.5.3 Embeddings locales frente a vía API

| Aspecto | Local (`sentence-transformers`) | API (DeepSeek / compatible con OpenAI) |
|--------|-------------------------------|--------------------------------------|
| **Latencia** | ~10ms por chunk (GPU), ~50ms (CPU) | ~100-300ms por lote (red) |
| **Coste** | Gratis (solo coste de hardware) | ~0,01-0,10 $ por 1M de tokens |
| **Privacidad** | Los datos nunca salen del servidor | Los datos se envían al proveedor de la API |
| **RAM** | ~500MB (e5-small), ~2GB (e5-large) | Ninguna |
| **Calidad** | Excelente para multilingüe | Varía según el proveedor |
| **Sin conexión** | Funciona sin internet | Requiere internet |
| **Recomendado** | Instancias autoalojadas (privacidad, sin conexión) | Instancias SaaS (sin GPU, menor mantenimiento) |

**Por defecto para el MVP:** `multilingual-e5-small` local (384d). Funciona en CPU, sin necesitar GPU a escala de pyme (~10K chunks).

#### 3.5.4 Embedding por lotes frente a individual

| Operación | Modo | Por qué |
|-----------|------|-----|
| Ingesta de documentos | **Por lotes** (64 chunks a la vez) | Rendimiento: paralelismo de GPU, límites de tasa de la API. |
| Consulta del usuario | **Individual** (1 embedding) | Latencia: el usuario está esperando. Una llamada, ~10ms. |
| Migración de modelo | **Por lotes** (64 chunks) | Igual que la ingesta — trabajo en segundo plano. |

---

### 3.6 Estrategia de actualización

Cuando los documentos fuente cambian (el admin sube una nueva versión, o edita contenido).

#### 3.6.1 Reingesta completa (por defecto)

**Cuándo:** El admin sube una nueva versión de un documento o reemplaza el fichero.

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

**Por qué la reingesta completa frente a la incremental:**
- Los documentos en el contexto pyme suelen tener <100 páginas (segundos para reprocesar)
- El diffing incremental de contenido PDF es frágil (cambios de layout = falsos diffs)
- Reordenar secciones en una nueva versión del documento corrompería los índices de chunk
- La reingesta completa es simple, correcta y suficientemente rápida para la escala esperada

#### 3.6.2 Cuándo NO reingerir

| Escenario | Acción | Por qué |
|----------|--------|-----|
| El admin edita metadatos (título, etiquetas) | Actualizar solo la fila de `documents` | El contenido del chunk no cambia |
| El admin edita un curso (no el documento fuente) | Sin reingesta del documento | El contenido del curso es independiente de los documentos fuente |
| El admin archiva un documento | Borrado suave (status = 'archived') | Preserva el historial, se excluye de la búsqueda |

#### 3.6.3 Consideraciones sobre el versionado de chunks

Para el MVP, SkillNet usa **sustitución en la actualización** (sin versionado). Esto implica:

- Los chunks antiguos se eliminan cuando se reingiere un documento
- Cualquier curso que referenciara IDs de chunk específicos podría quedar con referencias colgantes
- Mitigación: los cursos referencian `document_id` + `heading` (no `chunk_id`), así que sobreviven a la reingesta mientras se preserve la estructura de encabezados

**Consideración para la Fase 2:** Si se necesitan rastros de auditoría o comparaciones históricas:

```sql
-- Future: version tracking
ALTER TABLE document_chunks ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE document_chunks ADD COLUMN superseded_by UUID REFERENCES document_chunks(id);

-- On update: mark old chunks as superseded rather than deleting
-- Queries filter: WHERE superseded_by IS NULL
```

Esto se aplaza porque:
1. Las pymes rara vez necesitan un historial de versiones de los documentos de formación
2. Añade complejidad a las consultas (cada búsqueda debe filtrar por `superseded_by IS NULL`)
3. El almacenamiento crece con cada edición (los embeddings ocupan ~1,5KB por chunk a 384d)

#### 3.6.4 Actualizaciones en cascada al contenido generado

Cuando se actualiza un documento fuente, los cursos generados a partir de él pueden quedar desactualizados. SkillNet lo gestiona con notificaciones, no con regeneración automática:

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

El admin mantiene el control. SkillNet no regenera el contenido del curso silenciosamente.

---

### 3.7 Resumen de la arquitectura

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

### 3.8 Valores de configuración por defecto (MVP)

| Parámetro | Valor | Nota |
|-----------|-------|------|
| Modelo de embeddings | `multilingual-e5-small` | 384 dims, ~500MB RAM, adecuado para CPU |
| Tamaño de chunk | 512 tokens máx. | Alineado con la ventana de entrenamiento de E5 |
| Solapamiento de chunk | 2 frases | Evita respuestas cortadas en el límite |
| Prefijo contextual | Sí | Título del documento + encabezado de sección |
| Listas IVFFlat | 10 | Crecer a `sqrt(n)` cuando haya >10K chunks |
| Top-K semántico | 10 | Sobre-recuperar y luego filtrar a 3-5 |
| Umbral de similitud | 0,3 | Coseno, con embeddings normalizados |
| Constante K de RRF | 60 | Valor estándar de la literatura |
| Alpha híbrido | 0,5 | Autoajustado según la heurística de la consulta |
| Reranking | Deshabilitado (MVP) | Habilitar en la Fase 2 para búsqueda entre cursos |
| Configuración de búsqueda de texto completo | `spanish` | Integrada en PostgreSQL, incluye stemming |
| Presupuesto de tokens para el contexto | Depende del modelo | Conservador: 16K menos reservas |
| Tamaño de lote (embedding) | 64 (local), 32 (API) | Equilibrio entre rendimiento y memoria |

---

### 3.9 Despliegue por fases

| Fase | Qué | Estrategia de recuperación |
|-------|------|--------------------|
| **MVP** | Tutor de un solo documento, generación de cursos | Texto completo (docs pequeños) + búsqueda semántica (docs grandes) + PageIndex (dentro del curso) |
| **1.5** | Búsqueda por palabra clave en el panel de admin | + búsqueda de texto completo con `tsvector` |
| **2** | Búsqueda entre cursos, UI de búsqueda combinada | + RRF híbrido + reranking + etiquetas de origen |
| **2+** | Optimización de PDF grandes | + patrón PageIndex para la ingesta |
| **3** | Relaciones entre cursos | + consultas de metadatos estructurados + grafo de prerrequisitos |
| **3+** | GraphRAG (si hay >100 cursos) | + detección de comunidades para exploración temática |
