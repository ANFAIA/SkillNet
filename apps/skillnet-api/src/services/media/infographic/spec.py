"""Infographic **content agent** — grounded bundle in, strict-JSON sheet out (roadmap §2d).

A single ``gpt-4o-mini``-via-litellm call, same discipline as the podcast and slides
agents: the model emits **strict JSON**, we parse it, and the Pydantic :class:`Infographic`
is the contract that decides whether the output is usable.

**The key rule of §2d and the build-order traps:** image models cannot be trusted with
facts — they garble text and numbers. So this stage is where the grounding lives: the
facts, stats and one-liners are **extracted as data** and verified against the passages
here, and the frontend renders them as crisp HTML/SVG text we control. Image generation is
used only for a decorative backdrop, never for any factual label. Nothing in this module
produces or asks for an image; it produces data.

Grounding rule (same contract as the rest): citations attach to each section as
``citation_ids``, filtered against the bundle so a hallucinated id is dropped.

The LLM call (:func:`generate_infographic`) is a thin wrapper over two pure functions that
carry all the logic and all the tests: :func:`build_prompts` and :func:`parse_infographic`.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.llm.client import LLMService, resolve_llm_config
from src.services.media.grounding import GroundedBundle
from src.services.media.subject import MediaSubject, build_user_context, topic_rule
from src.llm.prompts.language import language_name

logger = get_logger(__name__)

#: Section bounds: a single sheet, not a report. A floor of one keeps an empty sheet from
#: validating; a ceiling keeps it a glanceable infographic rather than a document.
_MIN_SECTIONS = 1
_MAX_SECTIONS = 6

InfographicLayout = Literal["auto", "flow", "comparison", "grid", "hierarchy"]


class InfographicSection(BaseModel):
    """One section/stat of the sheet.

    ``stat`` is the big glanceable figure or label (``"30 dias"``, ``"3x"``, ``"98%"``) and
    is optional — not every section is a number. ``one_line`` is the single supporting
    sentence. Both are plain text rendered by us, never baked into an image.
    """

    heading: str = Field(min_length=1)
    stat: str | None = None
    one_line: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list)


class Infographic(BaseModel):
    """The validated infographic — the contract everything downstream depends on."""

    title: str = Field(min_length=1)
    subtitle: str | None = None
    sections: list[InfographicSection] = Field(min_length=_MIN_SECTIONS, max_length=_MAX_SECTIONS)
    orientation: Literal["portrait", "landscape"] = "portrait"
    layout: InfographicLayout = "auto"
    style: str = "default"
    language: str = "es"


# --------------------------------------------------------------------------------------
# Prompt building (pure)
# --------------------------------------------------------------------------------------
def build_prompts(
    bundle: GroundedBundle,
    *,
    subject: MediaSubject | None,
    language: str,
    style: str,
    orientation: str,
    steering: str | None = None,
    max_sections: int = _MAX_SECTIONS,
) -> tuple[str, str]:
    """Assemble the (system, user) prompt pair for one infographic. Pure — no I/O.

    ``subject`` (which course, which lesson) is keyword-only and has no default so that no
    call site can forget it by omission. Passing ``None`` is allowed but is then a
    deliberate statement, and it makes an empty bundle fatal
    (:class:`~src.services.media.subject.MediaContextError`) rather than yielding a sheet
    about whatever the model felt like.
    """
    lang_name = language_name(language)

    valid_ids = bundle.citation_ids()
    ids_line = (
        f"Los unicos citation_ids validos son: {', '.join(valid_ids)}. No inventes otros."
        if valid_ids
        else "No hay fuentes citables; deja citation_ids vacio en cada seccion."
    )

    system = (
        "Eres un disenador de infografias educativas. Produces UNA hoja infografica en "
        f"{lang_name} a partir del material aportado: un titulo y una serie de secciones "
        "glanceables y una composicion semantica.\n\n"
        f"{topic_rule(subject)}"
        "PRINCIPIOS:\n"
        f"- Entre 3 y {max_sections} secciones. Cada seccion es UNA idea.\n"
        "- El titulo tiene entre 4 y 9 palabras.\n"
        "- 'stat' es la cifra o dato destacado (ej. '30 dias', '3x', '98%'); es opcional, "
        "solo cuando hay un numero o dato corto que destacar.\n"
        "- 'one_line' es UNA frase de apoyo de 8-18 palabras, concreta y sin relleno.\n"
        "- Elige layout='flow' para pasos o secuencias; 'comparison' para dos alternativas; "
        "'grid' para categorias equivalentes; 'hierarchy' para una idea principal con ramas; "
        "y 'auto' solo si ninguna estructura anterior encaja.\n"
        "- Extrae los datos del material. Las cifras deben salir de las fuentes.\n\n"
        "REGLAS ESTRICTAS:\n"
        "1. Responde SOLO con JSON valido, sin texto antes ni despues, sin ```.\n"
        "2. Esquema exacto: "
        '{"title":str,"subtitle":str|null,"sections":[{"heading":str,"stat":str|null,'
        '"one_line":str,"citation_ids":[str,...]}],"orientation":"portrait"|"landscape",'
        '"layout":"auto"|"flow"|"comparison"|"grid"|"hierarchy",'
        '"style":str,"language":str}.\n'
        "3. Los datos y cifras van SIEMPRE como texto en los campos. NUNCA se incrustan en "
        "una imagen: la hoja se dibuja con texto real. Aqui solo se extraen datos.\n"
        "4. Las citas NUNCA van dentro del texto visible. Cada seccion lleva en "
        "'citation_ids' los ids de los pasajes en que se apoya su dato.\n"
        f"5. {ids_line}\n"
        f'6. Devuelve language="{language}", style="{style}", orientation="{orientation}".'
    )

    user_parts = [build_user_context(bundle, subject)]
    if steering:
        user_parts.append(f"\nINDICACION ADICIONAL DEL USUARIO:\n{steering.strip()}")
    user_parts.append("\nGenera ahora la infografia en JSON.")
    return system, "\n\n".join(user_parts)


# --------------------------------------------------------------------------------------
# Parsing + validation (pure)
# --------------------------------------------------------------------------------------
def _extract_json(raw: str) -> dict:
    """Best-effort parse of a model reply into a dict (same dialect as the other agents)."""
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


def filter_infographic_citations(infographic: Infographic, valid_ids: set[str]) -> Infographic:
    """Drop any ``citation_id`` a section claims that is not in the bundle. Pure."""
    sections = [
        section.model_copy(update={"citation_ids": _filter_ids(section.citation_ids, valid_ids)})
        for section in infographic.sections
    ]
    return infographic.model_copy(update={"sections": sections})


def parse_infographic(
    raw: str,
    *,
    valid_ids: list[str],
    language: str = "es",
    style: str = "default",
    orientation: str = "portrait",
) -> Infographic:
    """Turn a raw model reply into a validated, citation-filtered :class:`Infographic`.

    Pure and fully unit-testable without a network. Validates the sheet, filters citation
    ids against the bundle, and pins ``language``/``style``/``orientation`` to what the
    caller asked for rather than trusting the model's echo.
    """
    payload = _extract_json(raw)

    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError("infographic has no sections")

    try:
        infographic = Infographic.model_validate(
            {
                "title": payload.get("title"),
                "subtitle": payload.get("subtitle"),
                "sections": raw_sections,
                "orientation": orientation,
                "layout": payload.get("layout", "auto"),
                "style": style,
                "language": language,
            }
        )
    except ValidationError as exc:
        raise ValueError(f"invalid infographic: {exc}") from exc

    return filter_infographic_citations(infographic, set(valid_ids))


async def generate_infographic(
    bundle: GroundedBundle,
    *,
    subject: MediaSubject | None = None,
    language: str = "es",
    style: str = "default",
    orientation: str = "portrait",
    steering: str | None = None,
    llm: LLMService | None = None,
) -> Infographic:
    """Run the infographic content agent: build prompts, call the model, parse and validate.

    ``llm`` is injectable for tests; by default it resolves the app's LLM config and forces
    the small ``INFOGRAPHIC_MODEL``. json_mode is on; :func:`parse_infographic` is still
    defensive because not every provider honours it.
    """
    from src.config import settings

    system, user = build_prompts(
        bundle,
        subject=subject,
        language=language,
        style=style,
        orientation=orientation,
        steering=steering,
    )

    service = llm or LLMService(resolve_llm_config())
    reply = await service.complete(
        system,
        user,
        model=settings.INFOGRAPHIC_MODEL or None,
        temperature=0.4,
        max_tokens=2048,
        json_mode=True,
    )
    if not reply.strip():
        raise LLMError("Infographic agent returned an empty completion")

    return parse_infographic(
        reply,
        valid_ids=bundle.citation_ids(),
        language=language,
        style=style,
        orientation=orientation,
    )


__all__ = [
    "InfographicSection",
    "InfographicLayout",
    "Infographic",
    "build_prompts",
    "filter_infographic_citations",
    "parse_infographic",
    "generate_infographic",
]
