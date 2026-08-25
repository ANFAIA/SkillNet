"""Unit tests for `services.ingestion._decode_pdf_image` (no network, no DB).

pdfplumber 0.11.x has no `page.extract_image()` — the correct way to reach the pixel
data is the image dict's own `stream`, and for a FlateDecode image that data is raw,
headerless pixels that must be reconstructed with PIL before any vision model can read
them. These cover the three shapes that stream can come back as.
"""

import io

from PIL import Image

from src.services.ingestion import _decode_pdf_image


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
