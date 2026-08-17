"""Podcast **script agent** — grounded bundle in, strict-JSON dialogue out (roadmap §2a).

A single ``gpt-4o-mini``-via-litellm call, held to the same discipline as the kit DSL: the
model must emit **strict JSON**, we parse it, and :class:`PodcastScript` (Pydantic) is the
contract that decides whether the output is usable. Nothing downstream ever sees a shape
the validator did not bless.

Four show formats, exactly NotebookLM's, are prompt presets:

* **Deep Dive** — two hosts, the default conversational summary.
* **The Brief** — one host, under two minutes, a tight monologue.
* **Critique** — two hosts, one steelmans the material and the other pushes back on it.
* **Debate** — two hosts taking genuinely opposed positions.

Grounding rule (the NotebookLM contract): citations do **not** go in the spoken text. The
model attaches ``citation_ids`` to each turn instead, and we keep only the ids that
actually exist in the bundle — a hallucinated ``c9`` against a five-passage bundle is
dropped, never spoken, never shown. The spoken ``text`` must never contain a bracketed
marker; the parallel panel is where provenance lives.

The LLM call (:func:`generate_script`) is a thin wrapper over two pure functions that carry
all the logic and all the tests: :func:`build_prompts` (preset -> system/user prompts) and
:func:`parse_script` (raw model string -> validated, citation-filtered script).
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError, field_validator

from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.llm.client import LLMService, resolve_llm_config
from src.services.media.grounding import GroundedBundle

logger = get_logger(__name__)


class PodcastFormat(str, enum.Enum):
    """The four NotebookLM show formats, as prompt presets."""

    DEEP_DIVE = "deep_dive"
    THE_BRIEF = "the_brief"
    CRITIQUE = "critique"
    DEBATE = "debate"


class PodcastTurn(BaseModel):
    """One spoken turn. ``speaker`` is a stable label ("A"/"B"), never a real name."""

    speaker: str = Field(pattern=r"^[AB]$")
    text: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("turn text is empty after stripping")
        return stripped


class PodcastScript(BaseModel):
    """The validated dialogue script — the contract everything downstream depends on."""

    turns: list[PodcastTurn] = Field(min_length=1)
    format: PodcastFormat
    language: str = "es"
    target_seconds: int = Field(gt=0, le=1800)


@dataclass(frozen=True)
class FormatPreset:
    """A show format's fixed shape: how many hosts, how long, and how it behaves."""

    speakers: int
    target_seconds: int
    guidance: str


# Two Spanish hosts. Names are steering for the model's tone only; they are NOT spoken as
# labels and never reach the audio path (voices maps "A"/"B" to voice ids).
_HOST_A = "Lucia"
_HOST_B = "Marcos"

PODCAST_FORMATS: dict[PodcastFormat, FormatPreset] = {
    PodcastFormat.DEEP_DIVE: FormatPreset(
        speakers=2,
        target_seconds=240,
        guidance=(
            f"Formato Analisis a Fondo (Deep Dive): dos presentadores, {_HOST_A} (A) que "
            f"guia con curiosidad y {_HOST_B} (B) que aporta el detalle experto. "
            "Conversacion natural, se turnan, se hacen preguntas, conectan ideas. "
            "Cubre lo esencial del material con ejemplos concretos."
        ),
    ),
    PodcastFormat.THE_BRIEF: FormatPreset(
        speakers=1,
        target_seconds=100,
        guidance=(
            f"Formato Resumen Breve (The Brief): un solo presentador, {_HOST_A} (A), "
            "en menos de dos minutos. Monologo directo y denso, sin relleno ni saludos "
            'largos. TODOS los turnos deben tener speaker "A".'
        ),
    ),
    PodcastFormat.CRITIQUE: FormatPreset(
        speakers=2,
        target_seconds=240,
        guidance=(
            f"Formato Critica (Critique): {_HOST_A} (A) defiende y explica el material "
            f"con su mejor version, y {_HOST_B} (B) senala limitaciones, huecos y riesgos "
            "de forma constructiva. Rigurosos, no destructivos."
        ),
    ),
    PodcastFormat.DEBATE: FormatPreset(
        speakers=2,
        target_seconds=240,
        guidance=(
            f"Formato Debate: {_HOST_A} (A) y {_HOST_B} (B) sostienen posturas realmente "
            "opuestas sobre el material y las argumentan por turnos. Cada uno se apoya en "
            "el material para su lado. Tono vivo pero respetuoso."
        ),
    ),
}

_DEFAULT_FORMAT = PodcastFormat.DEEP_DIVE

#: Rough spoken pace for turning ``target_seconds`` into a word budget for the prompt.
_WORDS_PER_SECOND = 2.4


def coerce_format(value: object) -> PodcastFormat:
    """A caller's ``spec['format']`` -> a known preset, defaulting to Deep Dive.

    Accepts the enum value strings and a few friendly aliases so the admin UI and curl are
    both forgiving; anything unrecognised falls back to the default rather than failing.
    """
    if isinstance(value, PodcastFormat):
        return value
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "deep_dive": PodcastFormat.DEEP_DIVE,
        "deepdive": PodcastFormat.DEEP_DIVE,
        "brief": PodcastFormat.THE_BRIEF,
        "the_brief": PodcastFormat.THE_BRIEF,
        "critique": PodcastFormat.CRITIQUE,
        "debate": PodcastFormat.DEBATE,
    }
    try:
        return PodcastFormat(text)
    except ValueError:
        return aliases.get(text, _DEFAULT_FORMAT)


def build_prompts(
    bundle: GroundedBundle,
    *,
    fmt: PodcastFormat,
    language: str,
    target_seconds: int,
    steering: str | None = None,
) -> tuple[str, str]:
    """Assemble the (system, user) prompt pair for one script. Pure — no I/O.

    The system prompt fixes the personas, the show format, the language, and the two hard
    rules (strict JSON only; citations in ``citation_ids``, never in ``text``). The user
    prompt carries the grounded context block and the caller's optional steering note.
    """
    preset = PODCAST_FORMATS[fmt]
    word_budget = int(target_seconds * _WORDS_PER_SECOND)
    lang_name = "espanol" if language.startswith("es") else language

    valid_ids = bundle.citation_ids()
    ids_line = (
        f"Los unicos citation_ids validos son: {', '.join(valid_ids)}. "
        "No inventes otros."
        if valid_ids
        else "No hay fuentes citables; deja citation_ids vacio en cada turno."
    )

    system = (
        "Eres un guionista de podcasts educativos al nivel de NotebookLM. Produces el guion "
        f"de un episodio en {lang_name} a partir del material aportado.\n\n"
        f"{preset.guidance}\n\n"
        "CALIDAD DEL DIALOGO (haz que suene a conversacion real, no a locucion):\n"
        "- Arranca con un gancho concreto (una situacion, una pregunta, un dato que sorprende), "
        "nada de '¡Hola y bienvenidos!' generico.\n"
        "- Turnos cortos y desiguales: se interrumpen con matices, reformulan con sus palabras, "
        "encadenan con '(claro)', '(exacto)', '(a ver)', hacen preguntas de seguimiento reales.\n"
        "- Aterriza cada idea abstracta en un ejemplo concreto del material (un caso, una cifra, "
        "una escena de trabajo). Explica el porque, no solo el que.\n"
        "- Progresion: enganche -> desarrollo con ejemplos -> una idea contraintuitiva o un error "
        "comun -> cierre con la conclusion practica que el oyente se lleva.\n"
        "- Nada de relleno, ni resumir '(en resumen)' cada dos turnos, ni leer listas de corrido. "
        "Suena humano: humor ligero puntual, curiosidad genuina, sin cliches de locutor.\n\n"
        "REGLAS ESTRICTAS:\n"
        '1. Responde SOLO con JSON valido, sin texto antes ni despues, sin ```.\n'
        "2. Esquema exacto: "
        '{"turns": [{"speaker": "A"|"B", "text": str, "citation_ids": [str]}], '
        '"format": str, "language": str, "target_seconds": int}.\n'
        "3. Las citas NUNCA van dentro de 'text' (nada de [Fuente c1] hablado). El texto es "
        "lo que se pronuncia en voz alta. Las citas van en 'citation_ids' de cada turno, "
        "referenciando el pasaje del material en que se apoya ese turno.\n"
        f"4. {ids_line}\n"
        f"5. Apunta a unas {word_budget} palabras en total (~{target_seconds} s de audio).\n"
        f"6. Devuelve format=\"{fmt.value}\", language=\"{language}\", "
        f"target_seconds={target_seconds}."
    )

    context = bundle.as_prompt_context() or "(No hay material de origen; habla en general.)"
    user_parts = [
        "MATERIAL DE ORIGEN (cada bloque empieza con su marcador [Fuente cN: ...]):",
        context,
    ]
    if steering:
        user_parts.append(f"\nINDICACION ADICIONAL DEL USUARIO:\n{steering.strip()}")
    user_parts.append("\nGenera ahora el guion en JSON.")
    return system, "\n\n".join(user_parts)


def _extract_json(raw: str) -> dict:
    """Best-effort parse of a model reply into a dict.

    json_mode should already yield clean JSON, but the model occasionally wraps it in a
    fence or adds a stray sentence; we slice to the outermost braces before giving up.
    """
    text = (raw or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("model reply was not JSON")


def filter_citations(turns: list[PodcastTurn], valid_ids: set[str]) -> list[PodcastTurn]:
    """Drop any ``citation_id`` a turn claims that is not in the bundle. Pure.

    De-dupes while preserving order and never invents; a turn with only invalid ids ends up
    with an empty list, which is legitimate (a linking or framing turn cites nothing).
    """
    cleaned: list[PodcastTurn] = []
    for turn in turns:
        seen: list[str] = []
        for cid in turn.citation_ids:
            if cid in valid_ids and cid not in seen:
                seen.append(cid)
        cleaned.append(turn.model_copy(update={"citation_ids": seen}))
    return cleaned


def parse_script(
    raw: str,
    *,
    fmt: PodcastFormat,
    valid_ids: list[str],
    language: str = "es",
    target_seconds: int | None = None,
) -> PodcastScript:
    """Turn a raw model reply into a validated, citation-filtered :class:`PodcastScript`.

    Pure and fully unit-testable without a network. Enforces the format's speaker count
    (a single-host format is coerced to all-A rather than rejected), filters citation ids
    against the bundle, and pins ``format``/``language``/``target_seconds`` to what the
    caller asked for rather than trusting the model's echo of them.
    """
    payload = _extract_json(raw)
    preset = PODCAST_FORMATS[fmt]

    raw_turns = payload.get("turns")
    if not isinstance(raw_turns, list) or not raw_turns:
        raise ValueError("script has no turns")

    turns: list[PodcastTurn] = []
    for item in raw_turns:
        try:
            turn = PodcastTurn.model_validate(item)
        except ValidationError as exc:
            raise ValueError(f"invalid turn: {exc}") from exc
        # A single-host format never has a B: fold any stray B back onto A so the voice
        # path stays monologue rather than the validator rejecting an otherwise fine script.
        if preset.speakers == 1 and turn.speaker != "A":
            turn = turn.model_copy(update={"speaker": "A"})
        turns.append(turn)

    turns = filter_citations(turns, set(valid_ids))

    return PodcastScript(
        turns=turns,
        format=fmt,
        language=language,
        target_seconds=target_seconds or preset.target_seconds,
    )


async def generate_script(
    bundle: GroundedBundle,
    *,
    fmt: PodcastFormat = _DEFAULT_FORMAT,
    language: str = "es",
    target_seconds: int | None = None,
    steering: str | None = None,
    llm: LLMService | None = None,
) -> PodcastScript:
    """Run the script agent: build prompts, call the model, parse and validate.

    ``llm`` is injectable for tests; by default it resolves the app's LLM config and forces
    the small ``PODCAST_SCRIPT_MODEL``. json_mode is on so the provider is asked for a JSON
    object; :func:`parse_script` is still defensive because not every provider honours it.
    """
    from src.config import settings

    preset = PODCAST_FORMATS[fmt]
    seconds = target_seconds or preset.target_seconds
    system, user = build_prompts(
        bundle, fmt=fmt, language=language, target_seconds=seconds, steering=steering
    )

    service = llm or LLMService(resolve_llm_config())
    reply = await service.complete(
        system,
        user,
        model=settings.PODCAST_SCRIPT_MODEL or None,
        temperature=0.7,
        max_tokens=2048,
        json_mode=True,
    )
    if not reply.strip():
        raise LLMError("Script agent returned an empty completion")

    return parse_script(
        reply,
        fmt=fmt,
        valid_ids=bundle.citation_ids(),
        language=language,
        target_seconds=seconds,
    )


__all__ = [
    "PodcastFormat",
    "PodcastTurn",
    "PodcastScript",
    "FormatPreset",
    "PODCAST_FORMATS",
    "coerce_format",
    "build_prompts",
    "filter_citations",
    "parse_script",
    "generate_script",
]
