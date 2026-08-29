"""Video Overview **narration agent** — a deck in, one spoken line per slide out (§2b).

The Video Overview is *narrated slides*, not a real video model (roadmap §2b + §3 trap).
Its second stage, after the slide deck is written, turns each slide into a short
**1-2 sentence narration line** the single host speaks over that slide. One provider-agnostic
-via-litellm call writes every line at once (cross-slide coherence, one round trip), held
to the same strict-JSON discipline as the podcast/slides agents: the model emits JSON, we
parse it, and Pydantic is the contract.

Grounding rule (the NotebookLM contract, same as the podcast/slides): citations do **not**
go in the spoken text. Each narration line carries ``citation_ids`` instead, filtered to
the ids that actually exist in the bundle — a hallucinated ``c9`` is dropped, never spoken,
never shown. The captions strip under the player is where provenance lives.

Robustness: the number of lines the model returns is aligned to the number of slides in
:func:`align_narration` — a missing or empty line falls back to a narration derived from the
slide itself (its subtitle, first text block, or title), so a stray count mismatch never
leaves a silent slide. All the logic lives in pure functions (:func:`build_prompts`,
:func:`parse_lines`, :func:`align_narration`) that are unit-tested without a network.
"""

from __future__ import annotations

import json
import math

from pydantic import BaseModel, Field, ValidationError, field_validator

from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.llm.client import LLMService, resolve_llm_config
from src.services.media.grounding import GroundedBundle
from src.services.media.slides.spec import Slide, SlideDeck

logger = get_logger(__name__)

#: Rough spoken pace, shared with the podcast agent, used to size the word budget hint.
_WORDS_PER_SECOND = 2.4
#: A narration line is one or two sentences — a soft word ceiling keeps it that way.
_MAX_WORDS_PER_LINE = 45


class NarrationLine(BaseModel):
    """One slide's spoken line. ``text`` is what the host says; citations live beside it."""

    text: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("narration text is empty after stripping")
        return stripped


class NarrationScript(BaseModel):
    """The validated narration — exactly one line per slide, in slide order."""

    lines: list[NarrationLine] = Field(min_length=1)
    language: str = "es"


# --------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------
def _slide_summary(slide: Slide) -> str:
    """A compact textual summary of a slide for the narration prompt. Pure.

    The narrator needs to know what is *on* each slide to speak over it, but not the full
    kit-block JSON: title, subtitle, and the text-bearing bits of each block are enough.
    """
    parts: list[str] = [slide.title]
    if slide.subtitle:
        parts.append(slide.subtitle)
    for block in slide.blocks:
        kind = block.type
        if kind in {"text", "callout"}:
            parts.append(getattr(block, "text", ""))
        elif kind == "steps":
            parts.append(f"{block.title}: " + "; ".join(block.steps))
        elif kind == "table":
            parts.append("Tabla: " + ", ".join(block.headers))
        elif kind == "chart":
            pairs = ", ".join(
                f"{label}={value}" for label, value in zip(block.labels, block.values)
            )
            parts.append(f"{block.title} ({pairs})")
    return " — ".join(p for p in parts if p)


def fallback_narration(slide: Slide) -> str:
    """A narration line derived from the slide itself, when the model gave none. Pure.

    Prefers the subtitle, then the first text/callout block, then the title — always
    something speakable, so a count mismatch never yields a silent slide.
    """
    if slide.subtitle:
        return slide.subtitle.strip()
    for block in slide.blocks:
        if block.type in {"text", "callout"}:
            text = getattr(block, "text", "").strip()
            if text:
                return text
    return slide.title.strip()


def estimate_seconds(text: str) -> int:
    """A rough spoken duration for one line, floored to a few seconds. Pure.

    Only used to size the one-turn podcast script the TTS path expects; the real duration
    comes from the audio the player measures, so a rough estimate is fine.
    """
    words = len(text.split())
    return max(4, min(60, math.ceil(words / _WORDS_PER_SECOND)))


# --------------------------------------------------------------------------------------
# Prompt building (pure)
# --------------------------------------------------------------------------------------
def build_prompts(
    deck: SlideDeck,
    bundle: GroundedBundle,
    *,
    language: str,
    steering: str | None = None,
) -> tuple[str, str]:
    """Assemble the (system, user) prompt pair for the whole narration. Pure — no I/O.

    The system prompt fixes the one-line-per-slide discipline, the single-host tone, the
    language, and the two hard rules (strict JSON only; citations in ``citation_ids``, never
    in the spoken text). The user prompt carries the slide summaries in order plus the
    grounded context block and the caller's optional steering note.
    """
    lang_name = "espanol" if language.startswith("es") else language
    n = len(deck.slides)

    valid_ids = bundle.citation_ids()
    ids_line = (
        f"Los unicos citation_ids validos son: {', '.join(valid_ids)}. No inventes otros."
        if valid_ids
        else "No hay fuentes citables; deja citation_ids vacio en cada linea."
    )

    system = (
        "Eres el narrador de un video-resumen educativo (diapositivas narradas). Un unico "
        f"presentador locuta en {lang_name}, una frase por diapositiva.\n\n"
        "PRINCIPIOS:\n"
        f"- Escribe EXACTAMENTE {n} lineas de narracion, una por diapositiva y en el mismo "
        "orden.\n"
        f"- Cada linea es 1-2 frases (maximo ~{_MAX_WORDS_PER_LINE} palabras): lo que se "
        "dice en voz alta sobre esa diapositiva. Natural, hablado, sin leer literalmente el "
        "titulo.\n"
        "- Hila las diapositivas: la narracion se escucha seguida.\n\n"
        "REGLAS ESTRICTAS:\n"
        "1. Responde SOLO con JSON valido, sin texto antes ni despues, sin ```.\n"
        "2. Esquema exacto: "
        '{"lines":[{"text":str,"citation_ids":[str,...]},...],"language":str}.\n'
        "3. Las citas NUNCA van dentro de 'text' (nada de [Fuente c1] locutado). El texto "
        "es lo que se pronuncia. Las citas van en 'citation_ids' de cada linea.\n"
        f"4. {ids_line}\n"
        f'5. Devuelve language="{language}" y {n} lineas.'
    )

    summaries = "\n".join(
        f"[Diapositiva {i}] {_slide_summary(slide)}" for i, slide in enumerate(deck.slides, start=1)
    )
    context = bundle.as_prompt_context() or "(No hay material de origen; habla en general.)"
    user_parts = [
        f"DIAPOSITIVAS ({n}, en orden):",
        summaries,
        "\nMATERIAL DE ORIGEN (cada bloque empieza con su marcador [Fuente cN: ...]):",
        context,
    ]
    if steering:
        user_parts.append(f"\nINDICACION ADICIONAL DEL USUARIO:\n{steering.strip()}")
    user_parts.append("\nEscribe ahora la narracion en JSON.")
    return system, "\n\n".join(user_parts)


# --------------------------------------------------------------------------------------
# Parsing + alignment (pure)
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


def parse_lines(raw: str, *, valid_ids: list[str]) -> list[NarrationLine]:
    """Turn a raw model reply into the validated, citation-filtered lines it holds. Pure.

    Drops any single malformed line rather than failing the whole batch (alignment fills
    the gap from the slide). Raises only when the reply is not JSON or has no ``lines`` at
    all — a batch that produced nothing usable.
    """
    payload = _extract_json(raw)
    raw_lines = payload.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValueError("narration has no lines")

    valid = set(valid_ids)
    lines: list[NarrationLine] = []
    for item in raw_lines:
        if not isinstance(item, dict):
            continue
        try:
            line = NarrationLine.model_validate(item)
        except ValidationError:
            continue
        lines.append(
            line.model_copy(update={"citation_ids": _filter_ids(line.citation_ids, valid)})
        )
    if not lines:
        raise ValueError("narration has no usable lines")
    return lines


def align_narration(deck: SlideDeck, lines: list[NarrationLine]) -> list[NarrationLine]:
    """Map lines to slides one-to-one, filling any gap from the slide itself. Pure.

    Exactly ``len(deck.slides)`` lines come out. A slide with no (or an empty) model line
    gets a :func:`fallback_narration` line carrying that slide's own ``citation_ids``, so
    the narration is never silent and never longer than the deck.
    """
    aligned: list[NarrationLine] = []
    for index, slide in enumerate(deck.slides):
        if index < len(lines) and lines[index].text.strip():
            aligned.append(lines[index])
        else:
            aligned.append(
                NarrationLine(
                    text=fallback_narration(slide),
                    citation_ids=list(slide.citation_ids),
                )
            )
    return aligned


async def generate_narration(
    deck: SlideDeck,
    bundle: GroundedBundle,
    *,
    language: str = "es",
    steering: str | None = None,
    llm: LLMService | None = None,
) -> NarrationScript:
    """Run the narration agent: build prompts, call the model, parse and align.

    ``llm`` is injectable for tests; by default it resolves the app's LLM config and forces
    ``VIDEO_NARRATION_MODEL`` when configured, otherwise the app's main model. json_mode is
    on; :func:`parse_lines` stays defensive because not every provider honours it.
    """
    from src.config import settings

    system, user = build_prompts(deck, bundle, language=language, steering=steering)

    service = llm or LLMService(resolve_llm_config())
    reply = await service.complete(
        system,
        user,
        model=settings.VIDEO_NARRATION_MODEL or None,
        temperature=0.6,
        max_tokens=1536,
        json_mode=True,
    )
    if not reply.strip():
        raise LLMError("Narration agent returned an empty completion")

    lines = parse_lines(reply, valid_ids=bundle.citation_ids())
    aligned = align_narration(deck, lines)
    return NarrationScript(lines=aligned, language=language)


__all__ = [
    "NarrationLine",
    "NarrationScript",
    "fallback_narration",
    "estimate_seconds",
    "build_prompts",
    "parse_lines",
    "align_narration",
    "generate_narration",
]
