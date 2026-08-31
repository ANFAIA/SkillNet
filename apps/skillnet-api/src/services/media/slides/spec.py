"""Slide Deck **content agent** — grounded bundle in, strict-JSON deck out (roadmap §2c).

A single ``gpt-4o-mini``-via-litellm call, held to the same discipline as the podcast
script agent and the kit DSL: the model must emit **strict JSON**, we parse it, and the
Pydantic :class:`SlideDeck` is the contract that decides whether the output is usable.
Nothing downstream ever sees a shape the validator did not bless.

The "vocabulary-unfreezing move" of §2c: a slide is just **kit blocks in a slide frame**.
Each slide's ``blocks`` reuse a subset of the existing kit block vocabulary
(``TextContent``, ``Callout``, ``StepSequence``, ``Table``, ``Chart``) as a small
discriminated union — the same components the lesson surface already renders. The deck is
per-slide structured, so a later revision edits one slide's JSON, and the frontend renders
each block with the component it already has.

Grounding rule (the NotebookLM contract, same as the podcast): citations do **not** go in
the visible text. The model attaches ``citation_ids`` to each slide, and we keep only the
ids that actually exist in the bundle — a hallucinated ``c9`` against a five-passage bundle
is dropped, never shown. The footnote-style citation chips are where provenance lives.

The LLM call (:func:`generate_deck`) is a thin wrapper over two pure functions that carry
all the logic and all the tests: :func:`build_prompts` (bundle -> system/user prompts) and
:func:`parse_deck` (raw model string -> validated, citation-filtered deck).
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, ValidationError

from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.llm.client import LLMService, resolve_llm_config
from src.services.media.grounding import GroundedBundle
from src.services.media.subject import MediaSubject, build_user_context, topic_rule
from src.llm.prompts.language import language_name

logger = get_logger(__name__)

#: How many slides a deck may hold. A tight ceiling keeps "one idea per slide" honest and
#: the prompt/token budget bounded; a floor of one keeps an empty deck from validating.
_MIN_SLIDES = 1
_MAX_SLIDES = 12
#: How many blocks a single slide may hold — enough to develop one idea as a compact,
#: self-contained card without turning it into a document page.
_MAX_BLOCKS_PER_SLIDE = 4

#: Semantic compositions understood by the shared web renderer. ``auto`` keeps old
#: artifacts valid and lets the renderer infer a sensible arrangement from their blocks.
SlideComposition = Literal[
    "auto",
    "cover",
    "statement",
    "split",
    "process",
    "timeline",
    "grid",
    "comparison",
    "data",
]


# --------------------------------------------------------------------------------------
# The block vocabulary — a subset of the kit, as a discriminated union on ``type``
# --------------------------------------------------------------------------------------
class TextBlock(BaseModel):
    """A paragraph, mapping to the kit ``TextContent`` block."""

    type: Literal["text"] = "text"
    text: str = Field(min_length=1)
    variant: Literal["body", "lead", "caption"] = "body"


class CalloutBlock(BaseModel):
    """A highlighted aside, mapping to the kit ``Callout`` block."""

    type: Literal["callout"] = "callout"
    tone: Literal["info", "warn", "success"] = "info"
    text: str = Field(min_length=1)


class StepsBlock(BaseModel):
    """An ordered procedure, mapping to the kit ``StepSequence`` block."""

    type: Literal["steps"] = "steps"
    title: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1, max_length=8)


class TimelineBlock(BaseModel):
    """A sequence whose stages each carry a short explanation."""

    type: Literal["timeline"] = "timeline"
    label: str = Field(min_length=1)
    steps: list[str] = Field(min_length=2, max_length=6)
    details: list[str] = Field(min_length=2, max_length=6)


class CardBlock(BaseModel):
    """One titled concept module used in a two- or four-column grid."""

    type: Literal["card"] = "card"
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


class TableBlock(BaseModel):
    """A small data table, mapping to the kit ``Table`` block."""

    type: Literal["table"] = "table"
    headers: list[str] = Field(min_length=1, max_length=6)
    rows: list[list[str]] = Field(min_length=1, max_length=8)


class ChartBlock(BaseModel):
    """A bar/line chart, mapping to the kit ``Chart`` block.

    ``labels`` and ``values`` must be the same length; a chart whose axes disagree is not a
    chart. ``values`` are plain numbers — the facts, as data, never baked into an image.
    """

    type: Literal["chart"] = "chart"
    kind: Literal["bar", "line"] = "bar"
    title: str = Field(min_length=1)
    labels: list[str] = Field(min_length=1, max_length=8)
    values: list[float] = Field(min_length=1, max_length=8)


#: The discriminated union the parser resolves against ``type``. Any unknown type fails
#: validation rather than rendering as an empty box.
SlideBlock = Annotated[
    Union[
        TextBlock,
        CalloutBlock,
        StepsBlock,
        TimelineBlock,
        CardBlock,
        TableBlock,
        ChartBlock,
    ],
    Field(discriminator="type"),
]

#: The block ``type`` strings the model is allowed to emit — used in the prompt and to
#: pre-filter obviously-wrong blocks before Pydantic sees them.
_KNOWN_BLOCK_TYPES = {
    "text",
    "callout",
    "steps",
    "timeline",
    "card",
    "table",
    "chart",
}


class Slide(BaseModel):
    """One slide: structured content plus a semantic composition hint.

    ``composition`` is deliberately not a pixel-level template. It says what the card is
    trying to communicate; the frontend owns spacing and responsive layout. ``visual_brief``
    is retained only for compatibility with previously persisted artifacts.
    """

    title: str = Field(min_length=1)
    subtitle: str | None = None
    composition: SlideComposition = "auto"
    visual_brief: str | None = None
    blocks: list[SlideBlock] = Field(default_factory=list, max_length=_MAX_BLOCKS_PER_SLIDE)
    citation_ids: list[str] = Field(default_factory=list)


class SlideDeck(BaseModel):
    """The validated deck — the contract everything downstream depends on."""

    slides: list[Slide] = Field(min_length=_MIN_SLIDES, max_length=_MAX_SLIDES)
    theme: str = "default"
    language: str = "es"


# --------------------------------------------------------------------------------------
# Prompt building (pure)
# --------------------------------------------------------------------------------------
def build_prompts(
    bundle: GroundedBundle,
    *,
    subject: MediaSubject | None,
    language: str,
    theme: str,
    steering: str | None = None,
    max_slides: int = _MAX_SLIDES,
) -> tuple[str, str]:
    """Assemble the (system, user) prompt pair for one deck. Pure — no I/O.

    The system prompt fixes the deck discipline (one idea per slide), the block vocabulary,
    the language, and the two hard rules (strict JSON only; citations in ``citation_ids``,
    never in visible text). The user prompt carries the subject (which course, which
    lesson), the grounded context block and the caller's optional steering note.

    ``subject`` is keyword-only and has no default so that no call site can forget it by
    omission; passing ``None`` is allowed but is then a deliberate statement, and it makes
    an empty bundle fatal (:class:`~src.services.media.subject.MediaContextError`) instead
    of yielding a deck about whatever the model felt like.
    """
    lang_name = language_name(language)

    valid_ids = bundle.citation_ids()
    ids_line = (
        f"Los unicos citation_ids validos son: {', '.join(valid_ids)}. No inventes otros."
        if valid_ids
        else "No hay fuentes citables; deja citation_ids vacio en cada slide."
    )

    system = (
        "Eres un disenador de presentaciones educativas. Produces una plataforma de "
        f"diapositivas (slide deck) en {lang_name} a partir del material aportado.\n\n"
        f"{topic_rule(subject)}"
        "PRINCIPIOS:\n"
        "- Una idea central por diapositiva, desarrollada hasta que pueda entenderse sin "
        "un presentador. Titulos cortos y concretos.\n"
        f"- Entre 3 y {max_slides} diapositivas. La primera es de portada (titulo del tema "
        "y una frase gancho).\n"
        "- Excepto portada y statement, cada diapositiva usa 2-4 bloques y contiene "
        "aproximadamente 60-120 palabras visibles. Evita tanto el muro de texto como la "
        "tarjeta vacia.\n"
        "- Todas las diapositivas se renderizan en un marco 16:9 fijo. Prioriza y sintetiza: "
        "el contenido debe caber sin scroll, sin reducir la tipografia y sin depender de una "
        "altura variable.\n"
        "- Cada bloque aporta una funcion distinta: contexto, concepto, ejemplo, dato, "
        "advertencia o conclusion. No repitas la misma frase con otras palabras.\n"
        "- Construye una narracion completa: contexto -> ideas esenciales -> aplicacion o cierre.\n"
        "- Elige la composicion por la funcion de la slide, no para decorar: cover para portada; "
        "statement para una idea contundente; split para contenido + apoyo visual; process para "
        "instrucciones breves; timeline para etapas explicadas; grid para 2-4 conceptos paralelos; "
        "comparison para contrastar; data para tablas o graficos. Usa auto solo si ninguna encaja.\n"
        "- La presentacion se construye solo con tipografia y componentes. No propongas ni "
        "describas imagenes decorativas.\n\n"
        "BLOQUES DISPONIBLES (cada bloque es un objeto con un campo 'type'):\n"
        '- {"type":"text","text":str,"variant":"body"|"lead"|"caption"} — un parrafo.\n'
        '- {"type":"callout","tone":"info"|"warn"|"success","text":str} — un aviso.\n'
        '- {"type":"steps","title":str,"steps":[str,...]} — un procedimiento ordenado.\n'
        '- {"type":"timeline","label":str,"steps":[str,...],"details":[str,...]} — '
        "etapas con una breve explicacion por etapa.\n"
        '- {"type":"card","title":str,"text":str} — un concepto titulado; usa 2-4 juntos '
        'en composition="grid".\n'
        '- {"type":"table","headers":[str,...],"rows":[[str,...],...]} — una tabla pequena.\n'
        '- {"type":"chart","kind":"bar"|"line","title":str,"labels":[str,...],'
        '"values":[num,...]} — un grafico (labels y values del mismo tamano).\n\n'
        "REGLAS ESTRICTAS:\n"
        "1. Responde SOLO con JSON valido, sin texto antes ni despues, sin ```.\n"
        "2. Esquema exacto: "
        '{"slides":[{"title":str,"subtitle":str|null,"composition":"auto"|"cover"|'
        '"statement"|"split"|"process"|"timeline"|"grid"|"comparison"|"data",'
        '"blocks":[bloque,...],'
        '"citation_ids":[str,...]}],"theme":str,"language":str}.\n'
        "3. Las cifras y los datos van SIEMPRE como texto/numeros dentro de los bloques, "
        "NUNCA incrustados en una imagen. Aqui no se generan imagenes.\n"
        "4. Las citas NUNCA van dentro del texto visible. Cada diapositiva lleva en "
        "'citation_ids' los ids de los pasajes en que se apoya.\n"
        f"5. {ids_line}\n"
        f'6. Devuelve language="{language}", theme="{theme}".'
    )

    user_parts = [build_user_context(bundle, subject)]
    if steering:
        user_parts.append(f"\nINDICACION ADICIONAL DEL USUARIO:\n{steering.strip()}")
    user_parts.append("\nGenera ahora la plataforma de diapositivas en JSON.")
    return system, "\n\n".join(user_parts)


# --------------------------------------------------------------------------------------
# Parsing + validation (pure)
# --------------------------------------------------------------------------------------
def _extract_json(raw: str) -> dict:
    """Best-effort parse of a model reply into a dict (same dialect as the podcast agent)."""
    text = (raw or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("model reply was not JSON")


def _filter_ids(ids: object, valid_ids: set[str]) -> list[str]:
    """Keep only real citation ids, de-duped, order-preserving. Pure."""
    if not isinstance(ids, list):
        return []
    seen: list[str] = []
    for cid in ids:
        if isinstance(cid, str) and cid in valid_ids and cid not in seen:
            seen.append(cid)
    return seen


def filter_deck_citations(deck: SlideDeck, valid_ids: set[str]) -> SlideDeck:
    """Drop any ``citation_id`` a slide claims that is not in the bundle. Pure.

    A slide with only invalid ids ends up with an empty list, which is legitimate (a cover
    or a framing slide cites nothing).
    """
    slides = [
        slide.model_copy(update={"citation_ids": _filter_ids(slide.citation_ids, valid_ids)})
        for slide in deck.slides
    ]
    return deck.model_copy(update={"slides": slides})


def parse_deck(
    raw: str,
    *,
    valid_ids: list[str],
    language: str = "es",
    theme: str = "default",
) -> SlideDeck:
    """Turn a raw model reply into a validated, citation-filtered :class:`SlideDeck`.

    Pure and fully unit-testable without a network. Drops blocks whose ``type`` is unknown
    before validation (so one stray block does not sink an otherwise-fine slide), validates
    the whole deck, filters citation ids against the bundle, and pins ``language``/``theme``
    to what the caller asked for rather than trusting the model's echo.
    """
    payload = _extract_json(raw)

    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list) or not raw_slides:
        raise ValueError("deck has no slides")

    # Pre-filter unknown block types: a single hallucinated block type must not fail the
    # whole deck, so we drop it here rather than letting the discriminated union raise.
    for slide in raw_slides:
        if isinstance(slide, dict) and isinstance(slide.get("blocks"), list):
            slide["blocks"] = [
                block
                for block in slide["blocks"]
                if isinstance(block, dict) and block.get("type") in _KNOWN_BLOCK_TYPES
            ]

    try:
        deck = SlideDeck.model_validate(
            {"slides": raw_slides, "theme": theme, "language": language}
        )
    except ValidationError as exc:
        raise ValueError(f"invalid deck: {exc}") from exc

    return filter_deck_citations(deck, set(valid_ids))


async def generate_deck(
    bundle: GroundedBundle,
    *,
    subject: MediaSubject | None = None,
    language: str = "es",
    theme: str = "default",
    steering: str | None = None,
    llm: LLMService | None = None,
) -> SlideDeck:
    """Run the deck agent: build prompts, call the model, parse and validate.

    ``llm`` is injectable for tests; by default it resolves the app's LLM config and forces
    the small ``SLIDES_MODEL``. json_mode is on so the provider is asked for a JSON object;
    :func:`parse_deck` is still defensive because not every provider honours it.
    """
    from src.config import settings

    system, user = build_prompts(
        bundle, subject=subject, language=language, theme=theme, steering=steering
    )

    service = llm or LLMService(resolve_llm_config())
    reply = await service.complete(
        system,
        user,
        model=settings.SLIDES_MODEL,
        temperature=0.5,
        max_tokens=3072,
        json_mode=True,
    )
    if not reply.strip():
        raise LLMError("Slide deck agent returned an empty completion")

    return parse_deck(reply, valid_ids=bundle.citation_ids(), language=language, theme=theme)


__all__ = [
    "TextBlock",
    "CalloutBlock",
    "StepsBlock",
    "TimelineBlock",
    "CardBlock",
    "TableBlock",
    "ChartBlock",
    "SlideBlock",
    "SlideComposition",
    "Slide",
    "SlideDeck",
    "build_prompts",
    "filter_deck_citations",
    "parse_deck",
    "generate_deck",
]
