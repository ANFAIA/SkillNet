"""Unit tests for `services.ingestion._decode_pdf_image` (no network, no DB).

pdfplumber 0.11.x has no `page.extract_image()` — the correct way to reach the pixel
data is the image dict's own `stream`, and for a FlateDecode image that data is raw,
headerless pixels that must be reconstructed with PIL before any vision model can read
them. These cover the three shapes that stream can come back as.

The second half covers what happens to those bytes now that they are KEPT rather than
described-and-discarded: the content-addressed store they land in, and the deterministic
rules that decide which of them are furniture. Those rules are pure functions over
metadata precisely so they can be tested as arithmetic — no PDF, no disk, no model.
"""

import io
import uuid
from pathlib import Path

import pytest
from PIL import Image

from src.models import SourceImageKind
from src.services.image_describer import (
    MAX_DESCRIPTION_CHARS,
    VisionDescription,
    normalize_kind,
    parse_vision_response,
)
from src.services.ingestion import _decode_pdf_image
from src.services.source_images import (
    MAX_ASPECT_RATIO,
    MIN_IMAGE_SIDE,
    REPEAT_MIN_PAGES,
    ImageCandidate,
    SourceImageStore,
    content_hash,
    decorative_flags,
    has_extreme_aspect,
    image_extension,
    is_undersized,
    repeat_threshold,
    repeated_hashes,
)


class _FakeStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def get_data(self) -> bytes:
        return self._data


def test_passes_through_already_valid_jpeg() -> None:
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    img = {"stream": _FakeStream(jpeg_bytes), "srcsize": (10, 10), "colorspace": None}
    assert _decode_pdf_image(img) == jpeg_bytes


def test_reconstructs_raw_rgb_pixels_into_a_real_png() -> None:
    width, height = 4, 3
    raw = bytes(range(width * height * 3))[: width * height * 3]
    img = {"stream": _FakeStream(raw), "srcsize": (width, height), "colorspace": None}

    result = _decode_pdf_image(img)

    assert result is not None
    decoded = Image.open(io.BytesIO(result))
    assert decoded.format == "PNG"
    assert decoded.size == (width, height)


def test_reconstructs_grayscale_pixels() -> None:
    width, height = 3, 2
    raw = bytes([10, 20, 30, 40, 50, 60])
    img = {
        "stream": _FakeStream(raw),
        "srcsize": (width, height),
        "colorspace": ["/DeviceGray"],
    }

    result = _decode_pdf_image(img)

    assert result is not None
    decoded = Image.open(io.BytesIO(result))
    assert decoded.mode == "L"
    assert decoded.size == (width, height)


def test_returns_none_when_stream_is_too_short_for_declared_size() -> None:
    img = {"stream": _FakeStream(b"\x00\x00"), "srcsize": (100, 100), "colorspace": None}
    assert _decode_pdf_image(img) is None


def test_returns_none_without_srcsize() -> None:
    img = {"stream": _FakeStream(b"\x00" * 10), "srcsize": None, "colorspace": None}
    assert _decode_pdf_image(img) is None


# --------------------------------------------------------------------------------------
# The bytes are now KEPT, not discarded, and the junk filter that decides which of them
# are worth reusing is pure arithmetic over metadata. These cover both.
# --------------------------------------------------------------------------------------

def _candidate(page: int, digest: str = "a" * 64, width: int = 800, height: int = 600):
    return ImageCandidate(page=page, content_hash=digest, width=width, height=height)


# --- rule 1: the pixel floor -----------------------------------------------------------

def test_a_figure_above_the_pixel_floor_is_content() -> None:
    assert is_undersized(MIN_IMAGE_SIDE, MIN_IMAGE_SIDE) is False


@pytest.mark.parametrize(
    ("width", "height"),
    [(MIN_IMAGE_SIDE - 1, 900), (900, MIN_IMAGE_SIDE - 1), (16, 16)],
)
def test_either_side_below_the_floor_is_decorative(width: int, height: int) -> None:
    """An icon is an icon whichever of its sides is the small one."""
    assert is_undersized(width, height) is True


# --- rule 2: the aspect guard ----------------------------------------------------------

def test_an_ordinary_figure_passes_the_aspect_guard() -> None:
    assert has_extreme_aspect(800, 600) is False


def test_a_banner_strip_is_decorative_in_both_orientations() -> None:
    wide = int(MAX_ASPECT_RATIO * 200) + 200
    assert has_extreme_aspect(wide, 200) is True
    assert has_extreme_aspect(200, wide) is True


def test_a_zero_side_counts_as_extreme_rather_than_dividing_by_zero() -> None:
    assert has_extreme_aspect(0, 500) is True
    assert has_extreme_aspect(500, 0) is True


# --- rule 3: repeat across pages -------------------------------------------------------

def test_short_documents_never_trigger_the_repeat_rule() -> None:
    """In a two-page handout "on half the pages" is one repetition, which proves nothing."""
    assert repeat_threshold(2) == REPEAT_MIN_PAGES
    assert repeat_threshold(4) == REPEAT_MIN_PAGES


def test_the_repeat_threshold_scales_with_the_document() -> None:
    assert repeat_threshold(20) == 10
    assert repeat_threshold(41) == 21


def test_a_logo_on_every_page_header_is_furniture() -> None:
    logo = "b" * 64
    candidates = [_candidate(page, logo) for page in range(1, 11)]
    assert repeated_hashes(candidates, page_count=10) == {logo}


def test_the_same_image_twice_on_one_page_is_not_a_repeat() -> None:
    """The rule counts distinct PAGES; two copies side by side on page 1 are one page."""
    twice = "c" * 64
    candidates = [_candidate(1, twice), _candidate(1, twice), _candidate(1, twice)]
    assert repeated_hashes(candidates, page_count=10) == set()


def test_a_diagram_that_appears_once_survives_a_long_document() -> None:
    diagram = "d" * 64
    candidates = [_candidate(7, diagram)]
    assert repeated_hashes(candidates, page_count=40) == set()


# --- the three rules together ----------------------------------------------------------

def test_decorative_flags_keeps_the_diagram_and_marks_the_furniture() -> None:
    logo, diagram, rule = "e" * 64, "f" * 64, "0" * 64
    candidates = [
        *[_candidate(page, logo, 300, 300) for page in range(1, 7)],
        _candidate(3, diagram, 900, 700),
        _candidate(4, rule, 1200, 40),
    ]

    flags = decorative_flags(candidates, page_count=6)

    assert flags[:6] == [True] * 6  # repeated on every page
    assert flags[6] is False  # the one figure worth reusing
    assert flags[7] is True  # a horizontal rule


def test_decorative_flags_returns_one_verdict_per_candidate_in_order() -> None:
    candidates = [_candidate(1, "1" * 64), _candidate(2, "2" * 64, 10, 10)]
    assert decorative_flags(candidates, page_count=9) == [False, True]


def test_no_candidates_means_no_flags() -> None:
    assert decorative_flags([], page_count=12) == []


# --- the store -------------------------------------------------------------------------

def test_the_store_is_content_addressed_and_dedups(tmp_path) -> None:
    store = SourceImageStore(tmp_path)
    org, doc = uuid.uuid4(), uuid.uuid4()
    data = b"\x89PNG" + b"pixels" * 40

    first = store.store(org, doc, data, "png")
    second = store.store(org, doc, data, "png")

    assert first == second
    assert first.name == f"{content_hash(data)}.png"
    assert store.read(first) == data
    assert list(store.document_dir(org, doc).iterdir()) == [first]


def test_the_store_separates_documents_so_deleting_one_is_total(tmp_path) -> None:
    store = SourceImageStore(tmp_path)
    org, doc_a, doc_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    data = b"\x89PNG" + b"shared" * 40
    kept = store.store(org, doc_b, data, "png")
    store.store(org, doc_a, data, "png")

    store.clear_document(org, doc_a)

    assert not store.document_dir(org, doc_a).exists()
    assert kept.exists(), "another document's copy must survive"


def test_clearing_a_document_that_never_had_images_is_silent(tmp_path) -> None:
    store = SourceImageStore(tmp_path)
    store.clear_document(uuid.uuid4(), uuid.uuid4())  # must not raise


@pytest.mark.parametrize(
    "digest",
    ["../../etc/passwd", "a" * 63, "A" * 64, "g" * 64, "", "a" * 64 + "/x"],
)
def test_a_path_cannot_be_built_from_anything_but_a_hex_digest(tmp_path, digest) -> None:
    """The asset route rebuilds its path from a stored row, so the row is not trusted."""
    store = SourceImageStore(tmp_path)
    with pytest.raises(ValueError):
        store.path_for(uuid.uuid4(), uuid.uuid4(), digest, "png")


def test_only_the_two_extensions_the_decoder_produces_are_addressable(tmp_path) -> None:
    store = SourceImageStore(tmp_path)
    with pytest.raises(ValueError):
        store.path_for(uuid.uuid4(), uuid.uuid4(), "a" * 64, "svg")


def test_image_extension_reads_the_magic_bytes() -> None:
    assert image_extension(b"\xff\xd8\xff\xe0rest") == "jpg"
    assert image_extension(b"\x89PNG\r\n\x1a\n") == "png"
    # Anything the decoder re-encoded with PIL is a PNG; PNG is also the safe fallback.
    assert image_extension(b"unrecognised") == "png"


# --------------------------------------------------------------------------------------
# The behaviour change itself: the loop used to return immediately unless VISION_MODEL was
# set — which it is not, by default — so nothing was ever kept. These drive the real
# `_extract_pdf_images` with a fake pdfplumber and a recording session.
# --------------------------------------------------------------------------------------


class _FakePage:
    def __init__(self, images: list[dict]) -> None:
        self.images = images


class _FakePdf:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> "_FakePdf":
        return self

    def __exit__(self, *exc) -> bool:
        return False


class _RecordingSession:
    """Enough session for ``SourceImageRepository``: add + flush + execute(delete)."""

    def __init__(self) -> None:
        self.added: list = []
        self.executed: list[str] = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def execute(self, statement):
        self.executed.append(str(statement))
        return None


def _png(width: int, height: int, tag: bytes) -> bytes:
    """A real PNG of the requested size, padded so it clears MIN_IMAGE_BYTES."""
    image = Image.new("RGB", (width, height), color=(200, 30, 30))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue() + b"\x00" + tag + b"\x00" * 6000


def _pdf_image(data: bytes, width: int, height: int) -> dict:
    return {"stream": _FakeStream(data), "srcsize": (width, height), "colorspace": None}


def _install_fake_pdfplumber(monkeypatch, pages: list[_FakePage]) -> None:
    import sys
    import types

    module = types.ModuleType("pdfplumber")
    module.open = lambda _path: _FakePdf(pages)  # noqa: ARG005
    monkeypatch.setitem(sys.modules, "pdfplumber", module)


def _document(origin=None):
    from src.models import Document, DocumentOrigin

    return Document(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        title="manual.pdf",
        storage_path="manual.pdf",
        file_type="pdf",
        origin=origin or DocumentOrigin.UPLOADED,
    )


def _section(heading: str, page_start: int, page_end: int):
    from src.services.document_parser import ParsedSection

    return ParsedSection(
        heading=heading,
        level=2,
        content="body",
        page_start=page_start,
        page_end=page_end,
        position=0,
    )


@pytest.mark.asyncio
async def test_images_are_kept_even_with_no_vision_model(monkeypatch, tmp_path) -> None:
    """The whole point: VISION_MODEL is unset by default, and the bytes must survive anyway."""
    monkeypatch.setattr("src.config.settings.VISION_MODEL", None, raising=False)
    monkeypatch.setattr("src.config.settings.SOURCE_IMAGES_DIR", str(tmp_path), raising=False)
    data = _png(900, 700, b"diagram")
    _install_fake_pdfplumber(monkeypatch, [_FakePage([_pdf_image(data, 900, 700)])])

    from src.services.ingestion import _extract_pdf_images

    doc, session = _document(), _RecordingSession()
    sections = [_section("Mantenimiento", 1, 1)]

    await _extract_pdf_images(session, doc, Path("manual.pdf"), sections, {})

    assert len(session.added) == 1
    row = session.added[0]
    assert row.description is None, "no vision model configured -> no caption, but a row"
    assert row.kind == SourceImageKind.UNKNOWN.value, (
        "nobody looked, so the row says so -- downstream reads that as 'keep the original'"
    )
    assert row.is_decorative is False
    assert row.page == 1
    assert row.heading == "Mantenimiento"
    assert row.width == 900 and row.height == 700
    assert row.content_hash == content_hash(data)
    assert Path(row.asset_path).read_bytes() == data
    assert sections[0].content == "body", "no description -> no [Imagen: ...] injection"


@pytest.mark.asyncio
async def test_a_repeated_logo_is_stored_once_and_marked_decorative(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr("src.config.settings.VISION_MODEL", None, raising=False)
    monkeypatch.setattr("src.config.settings.SOURCE_IMAGES_DIR", str(tmp_path), raising=False)
    logo = _png(300, 300, b"logo")
    figure = _png(900, 700, b"figure")
    pages = [_FakePage([_pdf_image(logo, 300, 300)]) for _ in range(4)]
    pages[2].images.append(_pdf_image(figure, 900, 700))
    _install_fake_pdfplumber(monkeypatch, pages)

    from src.services.ingestion import _extract_pdf_images

    doc, session = _document(), _RecordingSession()

    await _extract_pdf_images(session, doc, Path("manual.pdf"), [_section("", 1, 4)], {})

    by_hash = {row.content_hash: row for row in session.added}
    assert len(session.added) == 5, "one row per occurrence, so a human can override each"
    assert all(row.is_decorative for row in session.added if row.content_hash == content_hash(logo))
    assert by_hash[content_hash(figure)].is_decorative is False
    stored = sorted(p.name for p in Path(session.added[0].asset_path).parent.iterdir())
    assert stored == sorted([f"{content_hash(logo)}.png", f"{content_hash(figure)}.png"]), (
        "content-addressed: four copies of the logo are one file"
    )


@pytest.mark.asyncio
async def test_a_generated_document_is_never_mined_for_images(monkeypatch, tmp_path) -> None:
    """A model-written source has no customer material in it to launder."""
    from src.models import DocumentOrigin

    monkeypatch.setattr("src.config.settings.SOURCE_IMAGES_DIR", str(tmp_path), raising=False)
    _install_fake_pdfplumber(
        monkeypatch, [_FakePage([_pdf_image(_png(900, 700, b"x"), 900, 700)])]
    )

    from src.services.ingestion import _extract_pdf_images

    doc = _document(origin=DocumentOrigin.GENERATED)
    doc.file_type = "pdf"
    session = _RecordingSession()

    await _extract_pdf_images(session, doc, Path("manual.pdf"), [_section("", 1, 1)], {})

    assert session.added == []
    assert session.executed == [], "not even the delete: the document is out of scope"


@pytest.mark.asyncio
async def test_a_described_image_still_injects_the_imagen_marker(
    monkeypatch, tmp_path
) -> None:
    """RAG finds images through this exact text. Storing bytes must not have changed it."""
    monkeypatch.setattr("src.config.settings.SOURCE_IMAGES_DIR", str(tmp_path), raising=False)
    data = _png(900, 700, b"diagram")
    _install_fake_pdfplumber(monkeypatch, [_FakePage([_pdf_image(data, 900, 700)])])

    from src.llm.client import LLMConfig
    from src.services import image_describer

    calls: list[bytes] = []

    async def _fake_describe(image_bytes, config):  # noqa: ARG001
        calls.append(image_bytes)
        return VisionDescription(kind="diagram", text="Un esquema del circuito")

    monkeypatch.setattr(image_describer, "describe_image", _fake_describe)
    monkeypatch.setattr(
        image_describer,
        "resolve_vision_config",
        lambda _org_settings=None: LLMConfig(model="fake/vision", api_base=None, api_key="k"),
    )

    from src.services.ingestion import _extract_pdf_images

    doc, session = _document(), _RecordingSession()
    sections = [_section("Circuito", 1, 1)]

    await _extract_pdf_images(session, doc, Path("manual.pdf"), sections, {})

    assert calls == [data]
    assert sections[0].content == "body\n\n[Imagen: Un esquema del circuito]"
    assert session.added[0].description == "Un esquema del circuito"
    assert session.added[0].kind == "diagram"


@pytest.mark.asyncio
async def test_the_same_image_on_three_pages_costs_one_vision_call(
    monkeypatch, tmp_path
) -> None:
    """One vision call per distinct image, not per occurrence -- every row still gets the verdict."""
    monkeypatch.setattr("src.config.settings.SOURCE_IMAGES_DIR", str(tmp_path), raising=False)
    figure = _png(900, 700, b"repeated-figure")
    # Eight pages so three occurrences stay under the repeat threshold and remain content.
    pages = [_FakePage([]) for _ in range(8)]
    for index in (0, 3, 6):
        pages[index].images.append(_pdf_image(figure, 900, 700))
    _install_fake_pdfplumber(monkeypatch, pages)

    from src.llm.client import LLMConfig
    from src.services import image_describer

    calls: list[bytes] = []

    async def _fake_describe(image_bytes, config):  # noqa: ARG001
        calls.append(image_bytes)
        return VisionDescription(kind="screenshot", text="La pantalla de devoluciones")

    monkeypatch.setattr(image_describer, "describe_image", _fake_describe)
    monkeypatch.setattr(
        image_describer,
        "resolve_vision_config",
        lambda _org_settings=None: LLMConfig(model="fake/vision", api_base=None, api_key="k"),
    )

    from src.services.ingestion import _extract_pdf_images

    doc, session = _document(), _RecordingSession()

    await _extract_pdf_images(session, doc, Path("manual.pdf"), [_section("", 1, 8)], {})

    assert len(calls) == 1, "content-addressed: three occurrences, one distinct image"
    assert len(session.added) == 3
    assert all(row.kind == "screenshot" for row in session.added)


@pytest.mark.asyncio
async def test_a_decorative_image_is_never_described_and_stays_unknown(
    monkeypatch, tmp_path
) -> None:
    """Furniture never reaches the model, so its kind is the one that keeps the original."""
    monkeypatch.setattr("src.config.settings.SOURCE_IMAGES_DIR", str(tmp_path), raising=False)
    rule = _png(1200, 40, b"divider")
    _install_fake_pdfplumber(monkeypatch, [_FakePage([_pdf_image(rule, 1200, 40)])])

    from src.llm.client import LLMConfig
    from src.services import image_describer

    async def _explode(image_bytes, config):  # noqa: ARG001
        raise AssertionError("a decorative image must never reach the vision model")

    monkeypatch.setattr(image_describer, "describe_image", _explode)
    monkeypatch.setattr(
        image_describer,
        "resolve_vision_config",
        lambda _org_settings=None: LLMConfig(model="fake/vision", api_base=None, api_key="k"),
    )

    from src.services.ingestion import _extract_pdf_images

    doc, session = _document(), _RecordingSession()

    await _extract_pdf_images(session, doc, Path("manual.pdf"), [_section("", 1, 1)], {})

    assert session.added[0].is_decorative is True
    assert session.added[0].kind == SourceImageKind.UNKNOWN.value
    assert session.added[0].description is None


# --------------------------------------------------------------------------------------
# Deletion. The rows leave with the document through the FK (migration 0026,
# ``ON DELETE CASCADE``); the FILES need a call, and a copy of a customer's diagram that
# outlives the record saying where it came from is the one leftover that matters.
# --------------------------------------------------------------------------------------


class _FakeDocumentRepo:
    def __init__(self, document) -> None:
        self.document = document
        self.deleted: list = []

    async def get_scoped(self, doc_id, org_id):
        if doc_id != self.document.id or org_id != self.document.org_id:
            return None
        return self.document

    async def delete(self, obj) -> None:
        self.deleted.append(obj)


@pytest.mark.asyncio
async def test_deleting_a_document_takes_its_source_images_off_the_disk(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        "src.config.settings.SOURCE_IMAGES_DIR", str(tmp_path / "images"), raising=False
    )
    from src.services.document_service import DocumentService

    doc = _document()
    original = tmp_path / "uploads" / "original.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"%PDF-1.4")
    doc.storage_path = str(original)

    store = SourceImageStore(tmp_path / "images")
    kept_elsewhere = store.store(doc.org_id, uuid.uuid4(), _png(400, 400, b"other"), "png")
    store.store(doc.org_id, doc.id, _png(900, 700, b"mine"), "png")
    assert store.document_dir(doc.org_id, doc.id).exists()

    repo = _FakeDocumentRepo(doc)
    await DocumentService(repo).delete_document(doc.id, doc.org_id)

    assert repo.deleted == [doc]
    assert not store.document_dir(doc.org_id, doc.id).exists()
    assert not original.exists()
    assert kept_elsewhere.exists(), "another document's images must survive"


# --------------------------------------------------------------------------------------
# The classification, as a pure function. `describe_image` is a network call; everything
# that decides how badly a misbehaving model can hurt lives in `parse_vision_response`,
# which is why that is what is tested. The rule it enforces: an answer we cannot read
# degrades to "unknown", never to an exception and never to a confident "diagram" --
# because "unknown" means keep the original image, and rebuilding a screenshot from prose
# is the one outcome that loses information without saying so.
# --------------------------------------------------------------------------------------


def test_a_well_formed_answer_gives_the_kind_and_the_prose_apart() -> None:
    raw = (
        '{"kind": "screenshot", "description": "La pantalla de ventas. El boton '
        '\\"Devolver\\" esta arriba a la derecha, junto a la caja de busqueda."}'
    )

    parsed = parse_vision_response(raw)

    assert parsed is not None
    assert parsed.kind == "screenshot"
    assert parsed.text.startswith("La pantalla de ventas.")
    assert "arriba a la derecha" in parsed.text
    assert "{" not in parsed.text, "the consumer gets prose, not the envelope"


def test_the_three_content_kinds_survive_a_round_trip() -> None:
    for kind in ("screenshot", "diagram", "photo"):
        parsed = parse_vision_response('{"kind": "%s", "description": "algo"}' % kind)
        assert parsed is not None
        assert parsed.kind == kind


def test_an_answer_that_ignores_the_format_is_kept_as_prose() -> None:
    """A model that just describes the image still produced something worth indexing."""
    raw = "Es un esquema del circuito de frenado, con la bomba a la izquierda."

    parsed = parse_vision_response(raw)

    assert parsed is not None
    assert parsed.text == raw
    assert parsed.kind == SourceImageKind.UNKNOWN.value


def test_json_wrapped_in_prose_or_fences_is_still_recovered() -> None:
    """The house parser handles this; the point is that this caller uses it."""
    fenced = '```json\n{"kind": "diagram", "description": "Un diagrama de flujo."}\n```'
    chatty = 'Claro, aqui tienes: {"kind": "photo", "description": "Una prensa."}'

    assert parse_vision_response(fenced).kind == "diagram"
    assert parse_vision_response(chatty).kind == "photo"
    assert parse_vision_response(chatty).text == "Una prensa."


@pytest.mark.parametrize("raw", ["", "   ", "\n\n", None])
def test_an_empty_answer_is_no_description_at_all(raw) -> None:
    assert parse_vision_response(raw) is None


def test_a_kind_nobody_recognises_keeps_the_prose_and_loses_only_the_verdict() -> None:
    raw = '{"kind": "infografia interactiva", "description": "Un cuadro de mandos."}'

    parsed = parse_vision_response(raw)

    assert parsed is not None
    assert parsed.text == "Un cuadro de mandos."
    assert parsed.kind == SourceImageKind.UNKNOWN.value


def test_the_right_shape_with_nothing_in_it_is_no_description() -> None:
    """Returning the raw JSON as prose would inject braces into the section text."""
    assert parse_vision_response('{"kind": "photo"}') is None
    assert parse_vision_response('{"kind": "photo", "description": "   "}') is None


def test_a_spanish_answer_is_read_rather_than_thrown_away() -> None:
    """The prompt is Spanish, so Spanish keys and Spanish values are the likely mistake."""
    raw = '{"tipo": "captura de pantalla", "descripcion": "El menu de ajustes."}'

    parsed = parse_vision_response(raw)

    assert parsed is not None
    assert parsed.kind == "screenshot"
    assert parsed.text == "El menu de ajustes."


def test_the_description_is_capped_because_it_ends_up_in_a_prompt() -> None:
    long_prose = "palabra " * 400
    raw = '{"kind": "diagram", "description": "%s"}' % long_prose

    parsed = parse_vision_response(raw)

    assert parsed is not None
    assert len(parsed.text) <= MAX_DESCRIPTION_CHARS + 3  # the ellipsis
    assert parsed.text.endswith("...")


def test_an_uncapped_description_is_left_exactly_as_written() -> None:
    parsed = parse_vision_response('{"kind": "photo", "description": "Una valvula."}')
    assert parsed is not None
    assert parsed.text == "Una valvula."


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("screenshot", "screenshot"),
        ("  SCREENSHOT  ", "screenshot"),
        ('"diagram".', "diagram"),
        ("captura", "screenshot"),
        ("pantallazo", "screenshot"),
        ("esquema", "diagram"),
        ("fotografia", "photo"),
        ("unknown", "unknown"),
        ("collage", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
        (["screenshot"], "unknown"),
        (7, "unknown"),
    ],
)
def test_normalize_kind_never_guesses_upward(given, expected) -> None:
    assert normalize_kind(given) == expected
