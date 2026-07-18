"""Document parsing: extract structured sections and clean text.

Dispatches by file type (pdf/txt/md/docx), returning ordered ``ParsedSection``
objects, the concatenated full text, and a page count. Pure of any DB/network
I/O so the ingestion pipeline can drive it and unit tests can exercise it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from src.core.logging import get_logger
from src.services.chunker import count_tokens

logger = get_logger(__name__)

_TOKENS_PER_PAGE = 750
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


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


def _parse_pdf(path: Path) -> tuple[list[ParsedSection], str, int]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    sections: list[ParsedSection] = []
    page_texts: list[str] = []
    position = 0
    for page_num, page in enumerate(reader.pages, 1):
        raw = page.extract_text() or ""
        content = clean_text(raw)
        if not content:
            continue
        page_texts.append(content)
        sections.append(
            ParsedSection(
                heading="",
                level=0,
                content=content,
                page_start=page_num,
                page_end=page_num,
                position=position,
            )
        )
        position += 1
    full_text = "\n\n".join(page_texts)
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
