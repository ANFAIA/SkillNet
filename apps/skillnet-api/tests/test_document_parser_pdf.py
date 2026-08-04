"""PDF extraction: the section structure the rest of the RAG depends on.

Every case here is something the previous ``pypdf.extract_text()`` implementation got
wrong, and the third one is why it mattered beyond cosmetics: with ``heading=""`` on every
PDF section, ``similarity_search_by_headings`` — the query the v2 runtime uses to scope
retrieval to ``course_nodes.source_headings`` — could not match a single row, and did so
without any error.

The PDFs are built here as raw bytes rather than committed as binary fixtures, because the
thing under test *is* the typography: heading detection reads the font size of each
character, so a test has to be able to state "this line is 18 pt and that one is 11 pt" and
have it be true in the file.
"""

from __future__ import annotations

import pytest

from src.services.document_parser import (
    _markdown_table,
    _norm_repeat,
    parse_document,
)

# ── a minimal PDF writer ────────────────────────────────────────────────────────────

#: (y, font size, font key, text). Font key "F1" is Helvetica, "F2" Helvetica-Bold.
Line = tuple[float, float, str, str]


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: list[Line]) -> bytes:
    parts = [
        f"BT /{font} {size} Tf 72 {y} Td ({_escape(text)}) Tj ET"
        for y, size, font, text in lines
    ]
    return "\n".join(parts).encode("latin-1")


def build_pdf(pages: list[list[Line]]) -> bytes:
    """Assemble a valid single-byte-encoded PDF with an accurate xref table."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)  # 1-indexed object number

    # Reserve 1 = catalog, 2 = page tree; fonts and pages follow.
    objects.append(b"")  # placeholder for 1
    objects.append(b"")  # placeholder for 2
    font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    page_numbers: list[int] = []
    for lines in pages:
        stream = _content_stream(lines)
        contents = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        page_numbers.append(
            add(
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font "
                b"<< /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                % (font_regular, font_bold, contents)
            )
        )

    kids = b" ".join(b"%d 0 R" % n for n in page_numbers)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_numbers))

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    return bytes(out)


HEADER = (740.0, 11.0, "F1", "Manual interno de La Espiga")


def _footer(page: int) -> Line:
    return (60.0, 9.0, "F1", f"Pagina {page}")


#: Three pages, a running header and footer on each, an 18 pt heading, a 13 pt heading,
#: a bold body-size heading, and a section whose text runs from page 1 onto page 2.
SAMPLE = [
    [
        HEADER,
        (700.0, 18.0, "F1", "Los 14 alergenos"),
        (680.0, 11.0, "F1", "El gluten aparece en el pan y en la bolleria."),
        (660.0, 11.0, "F1", "La lactosa aparece en la leche y en la nata."),
        _footer(1),
    ],
    [
        HEADER,
        (700.0, 11.0, "F1", "Los frutos de cascara incluyen almendra y avellana."),
        (660.0, 13.0, "F1", "Como informar al cliente"),
        (640.0, 11.0, "F1", "Preguntar siempre antes de servir el plato."),
        _footer(2),
    ],
    [
        HEADER,
        (700.0, 11.0, "F2", "Registro de incidencias"),
        (680.0, 11.0, "F1", "Anotar la fecha y el turno responsable."),
        _footer(3),
    ],
]


@pytest.fixture
def sample_pdf(tmp_path):
    path = tmp_path / "manual.pdf"
    path.write_bytes(build_pdf(SAMPLE))
    return path


def _by_heading(sections) -> dict[str, object]:
    return {section.heading: section for section in sections}


# ── the regressions ─────────────────────────────────────────────────────────────────


class TestHeadings:
    def test_extracts_real_headings_instead_of_empty_strings(self, sample_pdf):
        sections, _, _ = parse_document(sample_pdf, "pdf")

        headings = [s.heading for s in sections if s.heading]
        assert "Los 14 alergenos" in headings
        assert "Como informar al cliente" in headings

    def test_a_bold_body_size_line_is_a_heading_too(self, sample_pdf):
        """The very common PDF that marks sections with bold rather than a larger font."""
        sections, _, _ = parse_document(sample_pdf, "pdf")

        assert "Registro de incidencias" in [s.heading for s in sections]

    def test_levels_follow_font_size_largest_first(self, sample_pdf):
        sections, _, _ = parse_document(sample_pdf, "pdf")
        found = _by_heading(sections)

        assert found["Los 14 alergenos"].level == 1  # 18 pt, the largest
        assert found["Como informar al cliente"].level == 2  # 13 pt

    def test_headings_are_not_swallowed_into_the_body(self, sample_pdf):
        sections, _, _ = parse_document(sample_pdf, "pdf")
        found = _by_heading(sections)

        assert "Los 14 alergenos" not in found["Los 14 alergenos"].content


class TestSectionsSpanPages:
    def test_a_section_continues_onto_the_next_page(self, sample_pdf):
        """A page is a printing artifact. Cutting there split sections mid-sentence."""
        sections, _, _ = parse_document(sample_pdf, "pdf")
        alergenos = _by_heading(sections)["Los 14 alergenos"]

        assert "bolleria" in alergenos.content
        assert "almendra" in alergenos.content, "page 2 continuation was dropped"
        assert alergenos.page_start == 1
        assert alergenos.page_end == 2

    def test_page_count_is_the_real_count(self, sample_pdf):
        _, _, page_count = parse_document(sample_pdf, "pdf")

        assert page_count == 3


class TestBoilerplate:
    def test_running_header_is_stripped_from_every_section(self, sample_pdf):
        sections, full_text, _ = parse_document(sample_pdf, "pdf")

        assert "Manual interno" not in full_text
        for section in sections:
            assert "Manual interno" not in section.content

    def test_running_footer_is_stripped_despite_changing_digits(self, sample_pdf):
        """``Pagina 1`` and ``Pagina 2`` are the same footer; digit folding sees that."""
        _, full_text, _ = parse_document(sample_pdf, "pdf")

        assert "Pagina" not in full_text

    def test_two_page_documents_keep_their_edges(self, tmp_path):
        """Below three pages, "repeated on most pages" carries no signal."""
        path = tmp_path / "corto.pdf"
        repeated = (700.0, 11.0, "F1", "Frase que abre las dos paginas.")
        path.write_bytes(build_pdf([[repeated], [repeated]]))

        _, full_text, _ = parse_document(path, "pdf")

        assert "Frase que abre" in full_text


class TestScannedPdf:
    def test_a_pdf_with_no_extractable_text_fails_loudly(self, tmp_path):
        """The silent one. Before, every empty page was skipped and ingestion reported
        success, so a course was generated and grounded on an empty document."""
        path = tmp_path / "escaneo.pdf"
        path.write_bytes(build_pdf([[], []]))

        with pytest.raises(ValueError, match="no contiene texto extraible"):
            parse_document(path, "pdf")

    def test_the_error_names_OCR_so_it_is_actionable(self, tmp_path):
        path = tmp_path / "escaneo.pdf"
        path.write_bytes(build_pdf([[]]))

        with pytest.raises(ValueError, match="OCR"):
            parse_document(path, "pdf")


# ── pure helpers ────────────────────────────────────────────────────────────────────


class TestMarkdownTable:
    def test_renders_a_pipe_table_with_a_header_rule(self):
        out = _markdown_table([["Turno", "Responsable"], ["Manana", "Noa"]])

        assert out.splitlines() == [
            "| Turno | Responsable |",
            "| --- | --- |",
            "| Manana | Noa |",
        ]

    def test_pads_ragged_rows_so_columns_stay_aligned(self):
        out = _markdown_table([["a", "b", "c"], ["solo"]])

        assert out.splitlines()[-1] == "| solo |  |  |"

    def test_escapes_pipes_that_would_break_the_table(self):
        out = _markdown_table([["a|b"], ["c"]])

        assert r"a\|b" in out

    def test_none_cells_become_empty_and_blank_rows_vanish(self):
        out = _markdown_table([["a", None], [None, None], ["b", "c"]])

        assert out.splitlines() == ["| a |  |", "| --- | --- |", "| b | c |"]

    def test_a_table_with_nothing_in_it_renders_nothing(self):
        assert _markdown_table([[None], ["  "]]) == ""


class TestNormRepeat:
    def test_blanks_digits_so_paged_footers_collapse(self):
        assert _norm_repeat("Pagina 3") == _norm_repeat("Pagina 12")

    def test_is_case_insensitive_and_trims(self):
        assert _norm_repeat("  Titulo  ") == _norm_repeat("titulo")
