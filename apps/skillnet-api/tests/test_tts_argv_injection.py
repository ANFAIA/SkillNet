"""El texto y la voz del usuario no pueden convertirse en opciones de espeak-ng.

`espeak-ng` parsea con `getopt_long`, que PERMUTA argumentos: un texto que empieza por
guion se lee como opcion, no como palabras. Sin el terminador `--`, esto devolvia un mp3
leyendo en voz alta el fichero pedido:

    POST /api/v1/tts/synthesize  {"text": "-f/proc/self/environ"}

y ese fichero, en el contenedor `api`, contiene SECRET_KEY, LLM_API_KEY y la contrasena de
la base de datos. Alcanzable por cualquier usuario autenticado, porque este proveedor es el
respaldo automatico cuando el de pago falla.
"""

import re

from src.services.tts_service import _ESPEAK_VOICE_RE


def test_dash_leading_text_is_not_an_option():
    """El `--` va antes del texto en la linea de comandos real."""
    src = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src" / "services" / "tts_service.py"
    ).read_text(encoding="utf-8")
    call = re.search(r"\[espeak,[^\]]*\]", src, re.S)
    assert call, "no se encontro la invocacion de espeak"
    argv = call.group(0)
    assert '"--"' in argv, "falta el terminador `--` antes del texto"
    assert argv.index('"--"') < argv.index("text"), "el `--` tiene que ir ANTES del texto"


def test_voice_spec_accepts_real_voices():
    for good in ("es", "en", "es+m3", "en-us", "en-us+f2"):
        assert _ESPEAK_VOICE_RE.fullmatch(good), good


def test_voice_spec_rejects_anything_that_could_be_an_option():
    """`_resolve_voice` deja pasar valores desconocidos, asi que `voice` es del atacante."""
    for bad in ("-f/etc/passwd", "--stdin", "../../etc/passwd", "es;id", "es m3", ""):
        assert not _ESPEAK_VOICE_RE.fullmatch(bad), bad


def test_dev_secret_key_is_rejected_in_production():
    """La clave de desarrollo mide 47 caracteres, asi que pasaba el `len(value) < 32`.

    Esa clave deriva, via PBKDF2, la clave Fernet que cifra las credenciales de proveedor
    LLM de cada organizacion. Un despliegue fuera de Compose (uvicorn, k8s, systemd) podia
    arrancar en produccion con una clave publicada en este repositorio.
    """
    import pytest

    from src.config import _DEV_SECRET_KEY, Settings

    with pytest.raises(Exception) as err:
        Settings(ENVIRONMENT="production", SECRET_KEY=_DEV_SECRET_KEY)
    assert "development default" in str(err.value)

    # Una clave propia de longitud suficiente sigue valiendo.
    Settings(ENVIRONMENT="production", SECRET_KEY="x" * 40)
