"""Look at an image extracted from a PDF, and say both *what it is* and *what it taught*.

Two jobs, and the first one used to not exist. The old prompt here asked for "2-3
sentences describing what this image shows", which produces a caption: enough to make the
picture findable by RAG, useless for anything else. What the product actually needs is a
verdict it can act on, because the same image gets one of two incompatible treatments:

* a **screenshot** is kept and shown, because its information is *spatial* — which corner
  the button is in — and every prose rewrite of that is worse than the picture;
* a **diagram** or a **photo** can usually be rebuilt as something a learner can touch.

So the model is asked to classify first (:class:`~src.models.source_image.SourceImageKind`)
and then to write a description dense enough that a lesson could teach the same thing
without showing the image: every legible label *with its position on screen*, the steps
of a procedure in order, what connects to what in a diagram. "Ve aqui y pulsa aqui" has
to survive as "el boton *Devolver*, arriba a la derecha, junto a la caja de busqueda", or
the manual's instruction is silently lost.

The classification is biased toward ``screenshot``, and so is every fallback: keeping an
image that could have been rebuilt costs some screen space, while rebuilding one that
should have been kept deletes what the document was saying and says nothing about it.
``unknown`` reads the same way downstream — cannot be rebuilt, keep the original — which
is why an unparseable answer can degrade to it safely.

Best-effort throughout: if the configured model does not support vision, or the call
fails, or the answer ignores the requested shape, the image is described worse or not at
all and ingestion continues. Document ingestion must never fail because of an image.

Requires ``VISION_MODEL`` in the environment (or org settings). When absent, image
description is disabled entirely — no LLM call is attempted, no description exists, and
the row's ``kind`` stays ``unknown``. The bytes are kept either way; that part needs no
model at all.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import litellm

from src.config import settings
from src.core.logging import get_logger
from src.llm.client import LLMConfig, resolve_llm_config
from src.llm.parsing import try_parse_json_response
from src.models.source_image import SourceImageKind

logger = get_logger(__name__)

#: Images smaller than this are likely decorative (icons, bullets, borders).
MIN_IMAGE_BYTES = 5_000

#: Ceiling on the stored prose. This text is injected into section content (and from
#: there into chunks, retrieval and generation prompts), so it is a budget, not a
#: formatting preference: a model that decides to transcribe an entire screen would
#: otherwise push the actual source text out of every prompt that quotes the section.
MAX_DESCRIPTION_CHARS = 1200

#: Room for the JSON envelope plus roughly ``MAX_DESCRIPTION_CHARS`` of Spanish prose.
#: The old value was 200, which is a caption's budget and truncated anything richer.
DESCRIBE_MAX_TOKENS = 700

#: Spellings a model reaches for despite being handed the four English values. The
#: prompt is Spanish, so ``"captura"`` and ``"esquema"`` are the *likely* answers, not
#: exotic ones, and mapping them is worth more than a re-prompt. Anything not here is
#: ``unknown``, which is the conservative verdict rather than a guess.
_KIND_SYNONYMS: dict[str, str] = {
    "captura": SourceImageKind.SCREENSHOT.value,
    "captura de pantalla": SourceImageKind.SCREENSHOT.value,
    "pantalla": SourceImageKind.SCREENSHOT.value,
    "pantallazo": SourceImageKind.SCREENSHOT.value,
    "interfaz": SourceImageKind.SCREENSHOT.value,
    "ui": SourceImageKind.SCREENSHOT.value,
    "screen": SourceImageKind.SCREENSHOT.value,
    "diagrama": SourceImageKind.DIAGRAM.value,
    "esquema": SourceImageKind.DIAGRAM.value,
    "grafico": SourceImageKind.DIAGRAM.value,
    "gráfico": SourceImageKind.DIAGRAM.value,
    "flowchart": SourceImageKind.DIAGRAM.value,
    "chart": SourceImageKind.DIAGRAM.value,
    "foto": SourceImageKind.PHOTO.value,
    "fotografia": SourceImageKind.PHOTO.value,
    "fotografía": SourceImageKind.PHOTO.value,
    "photograph": SourceImageKind.PHOTO.value,
    "imagen real": SourceImageKind.PHOTO.value,
}

_DESCRIBE_PROMPT = """\
Analiza esta imagen extraida de un documento de formacion de una empresa. El objetivo
no es describirla por encima: es que una leccion pueda ensenar lo mismo que ensena la
imagen SIN mostrarla.

Primero clasifica la imagen en "kind", con uno de estos tres valores:
- "screenshot": una captura de una interfaz (aplicacion de escritorio, web o movil).
  Hay ventanas, menus, pestanas, botones, campos de formulario, tablas o cursores.
- "diagram": diagrama de flujo, esquema, organigrama, grafico de datos o dibujo
  conceptual. Formas y flechas, no una fotografia.
- "photo": algo real fotografiado: una maquina, una pieza, un lugar, una persona o un
  documento en papel.
Si dudas entre "screenshot" y cualquier otra cosa, elige "screenshot".

Despues escribe "description" en espanol, en prosa continua, e incluye TODO esto:
- Que es y para que sirve, en una frase.
- Cada texto legible (rotulos, botones, titulos, campos, leyendas, valores) entre
  comillas y CON SU POSICION: "arriba a la derecha", "en la columna izquierda", "bajo
  el titulo", "en la fila inferior de la tabla". La posicion no es un adorno: sin ella
  la instruccion "ve aqui y pulsa aqui" se pierde.
- Si la imagen muestra un procedimiento, los pasos en orden, numerados.
- Si es un diagrama, que se conecta con que y en que sentido va cada flecha.
- Si hay cifras o unidades, transcribelas tal cual.
No comentes la calidad, la resolucion ni el estilo. Los colores solo si distinguen un
control o un estado. Maximo 8 frases.

Responde en JSON valido con la forma:
{"kind": "screenshot|diagram|photo", "description": str}
"""


@dataclass(frozen=True)
class VisionDescription:
    """What one vision call produced: the verdict and the prose, kept apart.

    Apart, because the consumer of each is different. ``kind`` decides how the image may
    be used and is read by code; ``text`` is injected into the section content behind the
    ``[Imagen: ...]`` marker and is read by RAG and by the generation prompts. Returning
    a single blob would force every caller to re-derive the classification from prose.
    """

    kind: str
    text: str


@dataclass
class ImageDescription:
    """One description, tied to the page whose section text it will be injected into."""

    page: int
    description: str


def resolve_vision_config(
    org_settings: dict | None = None,
) -> LLMConfig | None:
    """Return vision LLM config, or ``None`` if no vision model is configured.

    Precedence: org_settings['vision_model'] > VISION_MODEL env var.
    Falls back to the main LLM_MODEL only if VISION_MODEL is explicitly set
    to the same value — we never assume the default LLM supports vision.
    """
    org_settings = org_settings or {}

    model = org_settings.get("vision_model") or getattr(settings, "VISION_MODEL", None)
    if not model:
        return None

    # Reuse the main LLM connection settings (api_key, base_url) unless
    # the org overrides them specifically for vision.
    base = resolve_llm_config(org_settings)
    return LLMConfig(
        model=str(model),
        api_base=org_settings.get("vision_base_url") or base.api_base,
        api_key=org_settings.get("vision_api_key") or base.api_key,
    )


def normalize_kind(value: object) -> str:
    """Map whatever the model called it onto a :class:`SourceImageKind` value.

    Never raises and never guesses upward: an exact value wins, a known synonym wins,
    and everything else — a missing key, a list, a sentence, a kind invented on the
    spot — is ``unknown``, which downstream means "keep the original image". Getting
    this wrong in the other direction would authorise rebuilding a screenshot from
    prose, which is the one outcome that loses information silently.
    """
    if not isinstance(value, str):
        return SourceImageKind.UNKNOWN.value
    cleaned = value.strip().strip('".').lower()
    if cleaned in SourceImageKind.values():
        return cleaned
    return _KIND_SYNONYMS.get(cleaned, SourceImageKind.UNKNOWN.value)


#: Keys the answer's two fields have been seen under. English is what the prompt asks
#: for; the Spanish spellings are what a model writing Spanish prose reaches for anyway.
_DESCRIPTION_KEYS: tuple[str, ...] = ("description", "descripcion", "descripción", "texto")
_KIND_KEYS: tuple[str, ...] = ("kind", "tipo", "type", "clase")


def _first_string(payload: dict, keys: tuple[str, ...]) -> str | None:
    """The first of ``keys`` present in ``payload`` with a non-empty string value."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _cap(text: str) -> str:
    """Trim to :data:`MAX_DESCRIPTION_CHARS`, at a word boundary when there is one."""
    if len(text) <= MAX_DESCRIPTION_CHARS:
        return text
    cut = text[:MAX_DESCRIPTION_CHARS]
    boundary = cut.rfind(" ")
    if boundary > MAX_DESCRIPTION_CHARS // 2:
        cut = cut[:boundary]
    return cut.rstrip(" ,;:.") + "..."


def parse_vision_response(raw: str | None) -> VisionDescription | None:
    """Turn a raw vision answer into a :class:`VisionDescription`, or ``None``.

    Pure and total — this is the half worth testing, and it is the half that decides how
    badly a misbehaving model can hurt. Four inputs, four outcomes:

    * well-formed JSON -> the declared kind (normalised) and its description;
    * an answer that ignores the format -> the whole answer as prose, kind ``unknown``,
      because a paragraph about the image is still worth indexing;
    * an unrecognised kind -> the prose is kept, the kind degrades to ``unknown``;
    * empty, or JSON with no description at all -> ``None``, meaning "no caption".

    It never raises. An image description failing must cost the description and nothing
    else; the bytes are already stored by the time this is called.
    """
    if raw is None or not raw.strip():
        return None

    parsed = try_parse_json_response(raw, context="image_describe")

    if isinstance(parsed, dict):
        described = _first_string(parsed, _DESCRIPTION_KEYS)
        if described is None:
            # It answered in the right shape but said nothing usable. Returning the raw
            # JSON as prose would inject braces into the section text and from there
            # into every prompt that quotes it; no caption is better than that.
            return None
        return VisionDescription(
            kind=normalize_kind(_first_string(parsed, _KIND_KEYS)),
            text=_cap(described),
        )

    return VisionDescription(kind=SourceImageKind.UNKNOWN.value, text=_cap(raw.strip()))


def _encode_image(image_bytes: bytes) -> str:
    """Build a data URL from raw image bytes."""
    if image_bytes[:4] == b"\x89PNG":
        mime = "image/png"
    elif image_bytes[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"


async def describe_image(
    image_bytes: bytes,
    config: LLMConfig,
) -> VisionDescription | None:
    """Send one image to the vision model. Returns its classification + prose, or None."""
    try:
        response = await litellm.acompletion(
            model=config.model,
            api_base=config.api_base,
            api_key=config.api_key,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _DESCRIBE_PROMPT},
                        {"type": "image_url", "image_url": {"url": _encode_image(image_bytes)}},
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=DESCRIBE_MAX_TOKENS,
        )
        choices = getattr(response, "choices", None) or ()
        if not choices:
            return None
        content = getattr(choices[0].message, "content", None)
        return parse_vision_response(content)
    except Exception as exc:  # noqa: BLE001 — best effort
        logger.warning("Vision description failed (%s): %s", config.model, exc)
        return None
