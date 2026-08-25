"""NUL en el texto extraido: PostgreSQL no puede almacenarlo, asi que hay que quitarlo."""

from src.services.document_parser import clean_text


def test_nul_byte_is_stripped():
    """Un solo 0x00 abortaba la ingesta ENTERA del documento.

    PostgreSQL rechaza 0x00 en una columna de texto —"invalid byte sequence for encoding
    UTF8"—, la transaccion caia, y el usuario recibia "Error processing document. Check
    the server logs for details.", que no menciona el byte por ningun sitio. Medido sobre
    un corpus real: 3 de 99 PDF de ofimatica corriente traian uno.
    """
    assert "\x00" not in clean_text("hola\x00mundo")
    assert clean_text("hola\x00mundo") == "holamundo"


def test_other_c0_controls_are_stripped():
    """Misma familia, mismo problema potencial: no aportan texto."""
    for ch in ("\x01", "\x08", "\x0b", "\x0c", "\x1f"):
        assert ch not in clean_text(f"antes{ch}despues")


def test_tab_newline_and_cr_survive():
    """El resto de `clean_text` depende de ellos: colapsa espacios y parte por lineas."""
    assert clean_text("a\tb") == "a b"          # el tabulador se colapsa a espacio
    assert clean_text("linea1\nlinea2") == "linea1\nlinea2"
