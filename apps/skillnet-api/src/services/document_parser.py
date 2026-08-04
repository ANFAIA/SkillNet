"""Document parsing: extract structured sections and clean text.

Dispatches by file type (pdf/txt/md/docx), returning ordered ``ParsedSection``
objects, the concatenated full text, and a page count. Pure of any DB/network
I/O so the ingestion pipeline can drive it and unit tests can exercise it.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.core.logging import get_logger
from src.services.chunker import count_tokens

logger = get_logger(__name__)

_TOKENS_PER_PAGE = 750
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# ── PDF layout heuristics ───────────────────────────────────────────────────────────
#: Two words belong to the same visual line when their tops are within this many points.
#: Generous enough for a superscript or a slightly taller glyph, tight enough not to
#: swallow the next line of 11 pt text set solid.
_LINE_TOLERANCE = 2.5

#: A line is a heading when its font is at least this much larger than the body font.
#: 1.15 catches a 13 pt heading over 11 pt body, which is the tightest pair worth
#: treating as a hierarchy; below that the difference is usually emphasis, not structure.
_HEADING_SIZE_RATIO = 1.15

#: Headings are short. A long line in a big font is a pull-quote or a title page blurb,
#: and promoting it would start a section that swallows the real ones.
_HEADING_MAX_CHARS = 120

#: Deepest heading level, matching the ``#{1,6}`` the markdown path can express.
_MAX_HEADING_LEVEL = 6

#: How many lines at each edge of a page are candidates for a running header/footer.
_EDGE_LINES = 2

#: A line repeated on at least this share of the pages is boilerplate, not content.
_BOILERPLATE_SHARE = 0.6

#: Below this many pages "repeated on most pages" carries no signal — a 2-page document
#: can legitimately open both pages with the same sentence.
_BOILERPLATE_MIN_PAGES = 3


@dataclass
class ParsedSection:
    heading: str
    level: int
    content: str
    page_start: int
    page_end: int
    position: int


def clean_text(text: str) -> str:
    """Normalize extracted text for embedding quality."""
    # Collapse horizontal whitespace.
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse 3+ line breaks into a paragraph break.
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Drop standalone page-number artifacts.
    text = re.sub(r"^\s*(?:Pagina|Page)\s+\d+\s*$", "", text, flags=re.MULTILINE)
    # Repair hyphenation breaks from column/line wrapping.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Unicode NFC (Spanish accents).
    text = unicodedata.normalize("NFC", text)
    # Trim each line.
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


def _estimate_pages(full_text: str) -> int:
    return max(1, count_tokens(full_text) // _TOKENS_PER_PAGE)


def _normalize_ext(file_type: str, path: Path) -> str:
    ext = (file_type or "").lower().lstrip(".")
    return ext or path.suffix.lower().lstrip(".")


def parse_document(
    path: Path, file_type: str
) -> tuple[list[ParsedSection], str, int]:
    """Parse a file into (sections, full_text, page_count)."""
    ext = _normalize_ext(file_type, path)
    if ext == "pdf":
        return _parse_pdf(path)
    if ext == "docx":
        return _parse_docx(path)
    if ext in {"txt", "md", "markdown"}:
        return _parse_text(path)
    raise ValueError(f"Unsupported document type: {ext or '(none)'}")


@dataclass
class _Line:
    """One visual line of a PDF, with the typography needed to classify it."""

    text: str
    size: float
    bold: bool
    page: int
    top: float
    is_table: bool = False


def _norm_repeat(text: str) -> str:
    """Fold a line for repeat detection: lower-cased, digits blanked.

    Digits are blanked so ``Pagina 3`` and ``Pagina 4`` are recognised as the *same*
    running footer. Without that, per-page numbering defeats the detector entirely,
    which is the common case rather than the exotic one.
    """
    return re.sub(r"\d+", "#", text.lower().strip())


def _markdown_table(rows: list[list[str | None]]) -> str:
    """Render an extracted table as a pipe table.

    Worth the twenty lines: a table flattened into running text is one of the most
    damaging things that can reach a chunk, because the numbers survive but every
    association between a number and its column is lost — and the model will still answer
    confidently from it. A pipe table keeps rows and columns legible to the reader and to
    the model, and it survives the markdown renderer the chat already uses.
    """
    cleaned = [
        [(cell or "").replace("\n", " ").replace("|", "\\|").strip() for cell in row]
        for row in rows
        if row and any((cell or "").strip() for cell in row)
    ]
    if not cleaned:
        return ""
    width = max(len(row) for row in cleaned)
    padded = [row + [""] * (width - len(row)) for row in cleaned]
    header, *body = padded
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _inside(word: dict, bbox: tuple[float, float, float, float]) -> bool:
    """True when a word's centre falls inside a bounding box."""
    x0, top, x1, bottom = bbox
    cx = (float(word["x0"]) + float(word["x1"])) / 2
    cy = (float(word["top"]) + float(word["bottom"])) / 2
    return x0 <= cx <= x1 and top <= cy <= bottom


def _page_lines(page, page_num: int) -> list[_Line]:
    """Group a page's words into visual lines, keeping tables out of the text flow.

    Tables are emitted as single pseudo-lines holding their markdown, and the words that
    live inside a table's bounding box are dropped from the ordinary flow. Doing both is
    the point: emitting the table *and* its loose words would duplicate every cell, which
    is worse for retrieval than the scrambled text this replaces.
    """
    try:
        tables = page.find_tables()
    except Exception:  # noqa: BLE001 - a table detector failure must not cost the page
        tables = []
    boxes = [tuple(float(v) for v in t.bbox) for t in tables]

    words = page.extract_words(extra_attrs=["size", "fontname"])
    grouped: list[dict] = []
    for word in words:
        if any(_inside(word, box) for box in boxes):
            continue
        for row in grouped:
            if abs(row["top"] - float(word["top"])) <= _LINE_TOLERANCE:
                row["words"].append(word)
                break
        else:
            grouped.append({"top": float(word["top"]), "words": [word]})

    lines: list[_Line] = []
    for row in grouped:
        ordered = sorted(row["words"], key=lambda w: float(w["x0"]))
        text = " ".join(str(w["text"]) for w in ordered).strip()
        if not text:
            continue
        sizes = [float(w.get("size") or 0.0) for w in ordered]
        fonts = [str(w.get("fontname") or "") for w in ordered]
        lines.append(
            _Line(
                text=text,
                size=max(sizes) if sizes else 0.0,
                # Every run bold, not merely one: a sentence with one bold term is prose.
                bold=bool(fonts) and all("bold" in f.lower() for f in fonts),
                page=page_num,
                top=row["top"],
            )
        )

    for table, box in zip(tables, boxes, strict=True):
        try:
            markdown = _markdown_table(table.extract())
        except Exception:  # noqa: BLE001
            continue
        if markdown:
            lines.append(
                _Line(text=markdown, size=0.0, bold=False, page=page_num, top=box[1], is_table=True)
            )

    lines.sort(key=lambda line: line.top)
    return lines


def _body_size(pages: list[list[_Line]]) -> float:
    """The document's body font size: the most common size, weighted by characters.

    Weighted by length rather than by line count, because a title page can hold more
    *lines* of large type than of body type while holding far fewer characters.
    """
    weights: Counter[float] = Counter()
    for lines in pages:
        for line in lines:
            if line.is_table or not line.size:
                continue
            weights[round(line.size, 1)] += len(line.text)
    return weights.most_common(1)[0][0] if weights else 0.0


def _boilerplate(pages: list[list[_Line]]) -> set[str]:
    """Normalized lines that repeat at the edge of most pages: running headers/footers.

    These poison every chunk they land in — the document's title arriving inside a chunk
    about something else is a term the vector and the FTS index both score on.
    """
    if len(pages) < _BOILERPLATE_MIN_PAGES:
        return set()
    counts: Counter[str] = Counter()
    for lines in pages:
        text_lines = [line for line in lines if not line.is_table]
        edges = text_lines[:_EDGE_LINES] + text_lines[-_EDGE_LINES:]
        for candidate in {_norm_repeat(line.text) for line in edges}:
            counts[candidate] += 1
    needed = max(_BOILERPLATE_MIN_PAGES, int(len(pages) * _BOILERPLATE_SHARE))
    return {text for text, count in counts.items() if count >= needed}


def _heading_levels(pages: list[list[_Line]], body: float) -> dict[float, int]:
    """Map each heading font size to a level, largest size becoming level 1."""
    sizes = {
        round(line.size, 1)
        for lines in pages
        for line in lines
        if _looks_like_heading(line, body) and line.size > body
    }
    ordered = sorted(sizes, reverse=True)
    return {size: min(index + 1, _MAX_HEADING_LEVEL) for index, size in enumerate(ordered)}


def _looks_like_heading(line: _Line, body: float) -> bool:
    """Whether a line is a section heading rather than prose."""
    text = line.text.strip()
    if line.is_table or not text or len(text) > _HEADING_MAX_CHARS:
        return False
    if body and line.size >= body * _HEADING_SIZE_RATIO:
        return True
    # A fully bold short line that does not end like a sentence. Catches the very common
    # PDF that marks sections with bold body-size type instead of a larger font.
    return line.bold and not text.endswith((".", ":", ";", ",", "?", "!"))


def _parse_pdf(path: Path) -> tuple[list[ParsedSection], str, int]:
    """Extract section-aware text from a PDF.

    Replaces a ``pypdf.extract_text()`` per page, which produced one section per page with
    ``heading=""`` always. Three consequences, the last one silent:

    * A citation could never name a section, only a page.
    * ``chunker._prefix`` had no heading to prepend, so a chunk lost the one piece of
      context that tells the model *where in the document* it is.
    * ``similarity_search_by_headings`` filters on ``chunk_metadata->>'heading'``, and the
      v2 runtime scopes node retrieval to ``course_nodes.source_headings``. Against a PDF
      that filter matched **nothing, ever** — retrieval silently fell back to unscoped
      search and nobody saw a failure.

    A page is also the wrong unit: it is a printing artifact, not a semantic boundary, so a
    section spanning pages 3-4 was cut mid-sentence and the chunker's "one chunk per
    section" design was defeated before it ran.
    """
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        page_count = len(pdf.pages)
        pages = [_page_lines(page, number) for number, page in enumerate(pdf.pages, 1)]

    if not any(line.text for lines in pages for line in lines):
        # Loud on purpose. `ingest_document` turns this into `documents.status = error`
        # with the message attached, which an admin can see and act on. The previous code
        # skipped every empty page and reported success with an empty document — a course
        # then got generated, and grounded, on nothing at all.
        raise ValueError(
            f"El PDF no contiene texto extraible ({page_count} "
            f"{'pagina' if page_count == 1 else 'paginas'}). Suele ser un escaneo o "
            "imagenes: hay que pasarlo por OCR antes de subirlo."
        )

    skip = _boilerplate(pages)
    body = _body_size(pages)
    levels = _heading_levels(pages, body)

    sections: list[ParsedSection] = []
    heading = ""
    level = 0
    buffer: list[str] = []
    page_start = 1
    page_end = 1
    position = 0

    def flush() -> None:
        nonlocal position
        content = clean_text("\n".join(buffer))
        if not content:
            return
        sections.append(
            ParsedSection(
                heading=heading,
                level=level,
                content=content,
                page_start=page_start,
                page_end=page_end,
                position=position,
            )
        )
        position += 1

    for lines in pages:
        for line in lines:
            if not line.is_table and _norm_repeat(line.text) in skip:
                continue
            if _looks_like_heading(line, body):
                flush()
                buffer = []
                heading = line.text.strip()
                level = levels.get(round(line.size, 1), 1)
                page_start = page_end = line.page
                continue
            if not buffer:
                # First body line of the section decides where it starts, so a heading at
                # the foot of page 2 whose text runs on page 3 is not reported as page 2.
                page_start = line.page
            buffer.append(line.text)
            page_end = line.page
    flush()

    full_text = clean_text("\n\n".join(section.content for section in sections))
    return sections, full_text, max(1, page_count)


def _sections_from_lines(
    lines: list[str], page_count: int
) -> tuple[list[ParsedSection], int]:
    """Build sections from markdown-style ``#`` headings (works for plain txt too)."""
    sections: list[ParsedSection] = []
    heading = ""
    level = 0
    buffer: list[str] = []
    position = 0

    def flush() -> None:
        nonlocal position
        content = clean_text("\n".join(buffer))
        if content:
            sections.append(
                ParsedSection(
                    heading=heading,
                    level=level,
                    content=content,
                    page_start=1,
                    page_end=page_count,
                    position=position,
                )
            )
            position += 1

    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            flush()
            heading = match.group(2).strip()
            level = len(match.group(1))
            buffer = []
        else:
            buffer.append(line)
    flush()
    return sections, position


def _parse_text(path: Path) -> tuple[list[ParsedSection], str, int]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    full_text = clean_text(raw)
    page_count = _estimate_pages(full_text)
    sections, _ = _sections_from_lines(raw.split("\n"), page_count)
    if not sections and full_text:
        sections = [
            ParsedSection(
                heading="",
                level=0,
                content=full_text,
                page_start=1,
                page_end=page_count,
                position=0,
            )
        ]
    return sections, full_text, page_count


def _parse_docx(path: Path) -> tuple[list[ParsedSection], str, int]:
    from docx import Document as DocxDocument

    doc = DocxDocument(str(path))
    sections: list[ParsedSection] = []
    heading = ""
    level = 0
    buffer: list[str] = []
    position = 0

    def flush() -> None:
        nonlocal position
        content = clean_text("\n".join(buffer))
        if content:
            sections.append(
                ParsedSection(
                    heading=heading,
                    level=level,
                    content=content,
                    page_start=0,
                    page_end=0,
                    position=position,
                )
            )
            position += 1

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else "Normal"
        if style.startswith("Heading"):
            flush()
            heading = text
            tail = style.split()[-1]
            level = int(tail) if tail.isdigit() else 1
            buffer = []
        else:
            buffer.append(text)
    flush()

    full_text = "\n\n".join(s.content for s in sections)
    page_count = _estimate_pages(full_text)
    for section in sections:
        section.page_end = page_count if section.page_end == 0 else section.page_end
    return sections, full_text, page_count
