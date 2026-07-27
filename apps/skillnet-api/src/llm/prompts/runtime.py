"""Prompts and budgets for the runtime node graph (§4.2, §9).

Three calls, three prompts:

* :data:`FORMAT_DECIDER_SYSTEM` — ``decide_formato``. ``json_mode``, ``max_tokens=256``,
  ``temperature=0.0``. Picks one of :data:`~src.agents.runtime.router.ALLOWED_UI_FORMATS`.
* :data:`UI_GENERATOR_SYSTEM` — ``genera_ui``. ``max_tokens`` 1200 (fast) / 2400 (heavy),
  ``temperature=0.4``.
* :data:`UI_REPAIR_SYSTEM` — the single retry of the repair loop (``MAX_UI_RETRIES = 1``).

**The dialect fragment is never written by hand here.** It is
:func:`src.render.prompt.render_prompt`, the artefact ``library.prompt()`` generates from
the frontend kit, and this module only appends the SkillNet-specific half (what the node
is, what the learner is, what the length budget is). Hand-copying the signatures is the
one thing that would silently re-introduce the drift ``tests/test_render_prompt_artifact.py``
exists to catch, so the two uppercase names are resolved **lazily** through the module's
``__getattr__``: the constant is the real prompt, and importing this module never needs
the artefacts to be present (the router tests do not).

Two things this module deliberately never puts in a prompt:

* **Reactivity.** No ``$state``, no ``Query``, no tools, no ``refreshInterval`` — not even
  as a "do not use it" example beyond the negative rules the generated artefact already
  carries. Teaching the syntax is what turns it on (``docs/design/openui-adoption.md`` §3).
* **Personal data the design excludes.** ``goal`` does not travel (§3.3: the opening line
  is composed deterministically in the frontend) and ``users.accessibility`` never travels
  — ``short_blocks`` reaches the model only as a smaller ``effective_density`` (§3.1).

``PROMPT_VERSION`` is part of the ``cache_key`` (§3.4): bumping it invalidates every
cached render without touching the database.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache
from typing import Any

from src.render.prompt import render_prompt

#: Bumped whenever any prompt in this module changes in a way that changes output.
#: Enters the ``cache_key`` (§3.4).
PROMPT_VERSION = "runtime/1"

# --- budgets (§4.2) ----------------------------------------------------------------

DECIDE_MAX_TOKENS = 256
DECIDE_TEMPERATURE = 0.0
DECIDE_USE_CASE = "decide_formato"

UI_TEMPERATURE = 0.4
UI_USE_CASE = "genera_ui"
#: ``max_tokens`` per tier. A ``chart``/``mixed`` screen needs the room; a plain
#: explanation does not, and paying for it on 90 % of renders is the whole point of the
#: two-tier router.
UI_MAX_TOKENS: dict[str, int] = {"fast": 1200, "heavy": 2400}

#: One repair attempt, then the seed fallback. A second retry costs another full
#: generation for a model that has already failed twice on the same instructions.
MAX_UI_RETRIES = 1

#: How much of the source text travels with ``genera_ui``. Above this the prompt stops
#: being about the node and starts being about the document.
SOURCE_CONTEXT_MAX_CHARS = 6000

#: The line that separates the program from its answer key in the raw completion.
#:
#: The frozen grammar of §5.4 has no production for an answer, and rule 5/9 forbids one
#: inside ``QuizItem`` — but ``POST /nodes/{id}/answer`` has to grade something. So the
#: model emits the program, this sentinel, and a JSON object; ``validate_ui`` splits on it
#: **before** the gate runs, so the JSON braces never reach ``check_static_only`` and the
#: key never reaches the browser. That is what "separa answer_key" means in §4.2.
ANSWER_KEY_SENTINEL = "---ANSWER-KEY---"

#: Length budget wording per ``effective_density`` (1 = condensed, 5 = expanded).
_DENSITY_BUDGET: dict[int, str] = {
    1: "2-3 bloques y frases muy cortas. Solo lo imprescindible.",
    2: "3 bloques como maximo y frases cortas.",
    3: "3-5 bloques. Explicacion normal, sin relleno.",
    4: "4-6 bloques. Puedes desarrollar con un ejemplo mas.",
    5: "5-7 bloques. Desarrolla con ejemplos y matices.",
}

#: What each scaffolding band changes, stated as behaviour and not as a label.
_SCAFFOLD_RULES: dict[str, str] = {
    "novice": (
        "ANDAMIAJE ALTO: incluye un ejemplo resuelto paso a paso antes de pedir nada. "
        "Nombra cada paso. No des por sabido ningun termino del dominio."
    ),
    "neutral": (
        "ANDAMIAJE NEUTRO: ni ejemplos resueltos extra ni supresion de apoyos. "
        "Explica y pasa al caso concreto."
    ),
    "advanced": (
        "ANDAMIAJE BAJO: ve al caso limite y a las excepciones. No expliques lo basico "
        "ni repitas definiciones; esta persona ya demostro que lo domina."
    ),
}

#: How ``last_error_kind`` changes the next screen (§7.4).
_ERROR_RULES: dict[str, str] = {
    "detail": (
        "El ultimo fallo fue de detalle (forma, no fondo): corrige la forma en una linea "
        "y sigue adelante. No repitas la explicacion entera."
    ),
    "procedural": (
        "El ultimo fallo fue de procedimiento: senala el paso exacto que se hizo mal y "
        "vuelve a plantear ese paso, no el tema completo."
    ),
    "conceptual": (
        "El ultimo fallo fue conceptual: plantea UNA sola pregunta socratica sobre la "
        "parte equivocada antes de volver a explicar."
    ),
}

#: ``tutor_notes.signals`` action -> the instruction it becomes. Closed vocabulary, so a
#: signal can never turn into free-form prose injected into a prompt (§3.3).
_SIGNAL_RULES: dict[str, str] = {
    "reforzar_con_ejemplo": "Anade un ejemplo concreto del ambito de esta persona.",
    "bajar_dificultad": "Baja la dificultad: un paso menos por bloque.",
    "subir_dificultad": "Sube la dificultad: plantea un caso menos evidente.",
    "reducir_longitud_modulo": "Acorta: menos bloques y frases mas breves.",
    "revisar_prerrequisito": (
        "Recuerda en una linea el concepto previo del que depende este nodo, sin "
        "convertirlo en el tema."
    ),
}


# --- decide_formato ----------------------------------------------------------------

FORMAT_DECIDER_SYSTEM = """\
Eres el selector de formato de SkillNet, una plataforma de formacion en el puesto de
trabajo. Recibes la ficha de un nodo de aprendizaje y el perfil del aprendiz, y decides
con QUE FORMA se le presenta ese nodo. No escribes el contenido: solo eliges la forma.

Responde EXACTAMENTE con este JSON, sin texto alrededor y sin bloques de codigo:

{"ui_format": "explanation" | "exercise" | "chart" | "mixed", "rationale": "<1 frase>"}

Que significa cada formato:
- "explanation": prosa y avisos. La opcion por defecto cuando hay que entender algo.
- "exercise": el nodo se aprende practicando; la pantalla es un ejercicio con su enunciado.
- "chart": el nodo ES un dato cuantitativo (evolucion, reparto, comparacion numerica) que
  se entiende mejor visto que leido.
- "mixed": explicacion breve MAS un ejercicio, cuando lo uno sin lo otro se queda corto.

Reglas duras:
- "chart" solo si la fuente contiene cifras reales que se puedan representar. Si no hay
  cifras en la fuente, NO elijas "chart": no se inventan datos.
- "exercise" solo si el resultado esperado del nodo es una accion, no una comprension.
- Un nodo de criticidad "critical" nunca se presenta solo como "chart".
- Si dudas, elige "explanation". Es la forma que menos supuestos hace.
- No existe ningun otro valor. "simulation" no esta disponible.
"""


def build_format_prompt(
    *,
    title: str,
    summary: str,
    outcome: str | None = None,
    criticality: str = "recommended",
    default_ui_format: str = "explanation",
    role_title: str | None = None,
    sector: str | None = None,
    experience_level: str = "unknown",
    preset: str = "standard",
    effective_density: int = 3,
    scaffold_band: str = "neutral",
    vector_bucket: str = "",
    mastery: float = 0.0,
    consecutive_failed: int = 0,
    last_error_kind: str | None = None,
    source_has_numbers: bool = False,
) -> str:
    """The user prompt for ``decide_formato``.

    Only reached **after** the calibration period: with ``nodes_completed < 3`` the format
    is ``node.default_ui_format`` and no call happens at all (§6.4). ``default_ui_format``
    still travels, as the declared fallback the creator chose for this node.
    """
    parts = [
        "NODO",
        f"- Titulo: {title}",
        f"- Resumen: {summary}",
    ]
    if outcome:
        parts.append(f"- Resultado esperado: {outcome}")
    parts.extend(
        [
            f"- Criticidad: {criticality}",
            f"- Formato por defecto que eligio el creador: {default_ui_format}",
            f"- La fuente contiene cifras representables: {'si' if source_has_numbers else 'no'}",
            "",
            "APRENDIZ",
            f"- Puesto: {role_title or 'sin declarar'}",
            f"- Sector: {sector or 'sin declarar'}",
            f"- Experiencia declarada: {experience_level}",
            f"- Preset de lectura: {preset}",
            f"- Presupuesto de longitud (1 condensado - 5 expandido): {effective_density}",
            f"- Banda de andamiaje: {scaffold_band}",
            f"- Dominio actual del nodo (0-1): {round(float(mastery), 2)}",
        ]
    )
    if vector_bucket:
        parts.append(f"- Formato con el que mas interactua: {vector_bucket}")
    if consecutive_failed:
        parts.append(f"- Fallos consecutivos en este nodo: {consecutive_failed}")
    if last_error_kind:
        parts.append(f"- Tipo del ultimo error: {last_error_kind}")
    parts.append("")
    parts.append("Responde solo con el JSON especificado.")
    return "\n".join(parts)


# --- genera_ui ---------------------------------------------------------------------

_UI_GENERATOR_TAIL = f"""

## SkillNet: la clave de respuestas

Si el programa incluye algun QuizItem, DESPUES del programa escribes una linea con
exactamente {ANSWER_KEY_SENTINEL} y a continuacion un unico objeto JSON con la solucion de
cada QuizItem, indexado por su item_id:

{ANSWER_KEY_SENTINEL}
{{"q1": {{"correct": 2, "explanation": "Por que esa y no otra, 1-2 frases."}}}}

Forma de cada entrada, segun item_type:
- "test": {{"correct": <indice 0-based de la opcion correcta>, "explanation": "..."}}
- "true_false": {{"correct": true|false, "explanation": "..."}}
- "fill_blank": {{"blanks": ["<texto exacto de cada hueco, en orden>"], "explanation": "..."}}
- "order_steps": {{"correct_order": [<indices en el orden correcto>], "explanation": "..."}}

Reglas duras de la clave:
- Va SIEMPRE despues del programa, nunca antes, y nunca dentro de una llamada.
- Todo QuizItem del programa tiene su entrada. Un QuizItem sin entrada invalida la respuesta.
- El JSON de la clave es la unica parte de tu respuesta donde puede aparecer {{ o }}.
- Si el programa no lleva ningun QuizItem, no escribas la linea {ANSWER_KEY_SENTINEL}.
"""


@cache
def ui_generator_system() -> str:
    """``library.prompt()`` (the artefact) plus the answer-key protocol.

    Cached: the artefact is immutable at runtime and this string is hashed on every
    fixture lookup.
    """
    return render_prompt().rstrip("\n") + _UI_GENERATOR_TAIL


_UI_REPAIR_HEADER = """\
Tu respuesta anterior fue RECHAZADA por el validador de SkillNet. Vuelve a emitir el
programa completo, corregido. No expliques el error, no te disculpes y no comentes nada:
responde solo con el programa (y su clave de respuestas si lleva QuizItem).

Reglas del dialecto y catalogo de bloques: los mismos de abajo, sin excepciones.
"""


@cache
def ui_repair_system() -> str:
    """The repair system prompt: the same dialect, plus "you were rejected, emit again".

    A separate system prompt rather than an extra user turn, because the model has to be
    told that its previous output is not a starting point to patch but something to
    re-emit whole: the parser is line-oriented and a half-fixed program fails again.
    """
    return _UI_REPAIR_HEADER + "\n" + ui_generator_system()


def build_ui_prompt(
    *,
    title: str,
    summary: str,
    outcome: str | None = None,
    criticality: str = "recommended",
    ui_format: str = "explanation",
    effective_density: int = 3,
    scaffold_band: str = "neutral",
    role_title: str | None = None,
    sector: str | None = None,
    experience_level: str = "unknown",
    preset: str = "standard",
    target_bloom: str = "understand",
    last_error_kind: str | None = None,
    consecutive_failed: int = 0,
    consecutive_correct: int = 0,
    tutor_signals: Sequence[str] = (),
    source_context: str = "",
) -> str:
    """The user prompt for ``genera_ui``.

    ``role_title`` and ``sector`` are the only learner-declared strings that travel
    literally (§3.3, §6.2): they are what the examples get framed around, and the reason
    ``role_bucket`` is part of the ``cache_key``. ``goal`` and ``accessibility`` do not
    travel, by design.
    """
    parts = [
        f"FORMATO QUE DEBES PRODUCIR: {ui_format}",
        "",
        "NODO",
        f"- Titulo: {title}",
        f"- Resumen: {summary}",
    ]
    if outcome:
        parts.append(f"- Resultado esperado: {outcome}")
    parts.append(f"- Criticidad: {criticality}")

    parts.extend(
        [
            "",
            "PARA QUIEN ESCRIBES",
            f"- Puesto: {role_title or 'sin declarar'}",
            f"- Sector: {sector or 'sin declarar'}",
            f"- Experiencia declarada: {experience_level}",
            f"- Preset de lectura: {preset}",
            "",
            "COMO LO ESCRIBES",
            f"- Presupuesto de longitud: {_density_budget(effective_density)}",
            f"- {_SCAFFOLD_RULES.get(scaffold_band, _SCAFFOLD_RULES['neutral'])}",
            f"- Nivel cognitivo del ejercicio, si lo hay: {target_bloom}",
        ]
    )
    if role_title:
        parts.append(
            f"- Los ejemplos son situaciones reales de un/una {role_title}"
            + (f" del sector {sector}." if sector else ".")
        )
    if last_error_kind and last_error_kind in _ERROR_RULES:
        parts.append(f"- {_ERROR_RULES[last_error_kind]}")
    if consecutive_correct >= 1 and not consecutive_failed:
        # §7.4: "no intervenir por defecto". Silence is the default option.
        parts.append(
            "- Esta persona viene acertando: NO anadas andamiaje extra ni explicaciones "
            "de mas. El silencio es la opcion por defecto."
        )
    for signal in tutor_signals:
        rule = _SIGNAL_RULES.get(str(signal))
        if rule:
            parts.append(f"- {rule}")

    parts.append("")
    if source_context.strip():
        parts.append("FUENTE (es la unica verdad; no anadas datos que no esten aqui)")
        parts.append(clip_source(source_context))
    else:
        parts.append(
            "NO HAY EXTRACTO DE LA FUENTE. Limitate a lo que afirma el resumen del nodo "
            "y no anadas ni una cifra, plazo o nombre de norma nuevos."
        )
    parts.append("")
    parts.append("Responde solo con el programa.")
    return "\n".join(parts)


def build_repair_prompt(
    *, previous: str, errors: Sequence[str], ui_format: str = "explanation"
) -> str:
    """The user prompt for the single repair attempt.

    The validator's messages travel verbatim: they name the line, the component and the
    rule, which is exactly what an 8B model needs to fix an escaping mistake instead of
    rewriting the lesson.
    """
    listed = "\n".join(f"- {error}" for error in errors) or "- programa invalido"
    return (
        f"FORMATO QUE DEBES PRODUCIR: {ui_format}\n\n"
        "ERRORES DEL VALIDADOR:\n"
        f"{listed}\n\n"
        "TU RESPUESTA ANTERIOR:\n"
        f"{previous}\n\n"
        "Vuelve a emitir el programa completo y corregido. Solo el programa."
    )


# --- small helpers -----------------------------------------------------------------


def _density_budget(effective_density: int) -> str:
    try:
        level = int(effective_density)
    except (TypeError, ValueError):
        level = 3
    return _DENSITY_BUDGET.get(max(1, min(level, 5)), _DENSITY_BUDGET[3])


def clip_source(text: str, limit: int = SOURCE_CONTEXT_MAX_CHARS) -> str:
    """Trim the source extract at a whitespace boundary, never mid-word."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = head.rfind("\n")
    if cut < limit // 2:
        cut = head.rfind(" ")
    if cut < limit // 2:
        cut = limit
    return head[:cut].rstrip() + "\n[...]"


def ui_max_tokens(tier: str) -> int:
    """``max_tokens`` for ``genera_ui`` at ``tier`` (§4.2)."""
    return UI_MAX_TOKENS.get(tier, UI_MAX_TOKENS["fast"])


def signal_actions_for_node(tutor_notes: Any, node_id: Any) -> tuple[str, ...]:
    """The ``tutor_notes.signals`` actions recorded for one node, oldest first.

    Reads the notebook defensively: it is jsonb written by
    ``LearnerProfileService.apply_signals`` and nothing here may assume a shape.
    """
    if not isinstance(tutor_notes, dict):
        return ()
    signals = tutor_notes.get("signals")
    if not isinstance(signals, list):
        return ()
    wanted = str(node_id)
    actions: list[str] = []
    for entry in signals:
        if not isinstance(entry, dict) or str(entry.get("node_id")) != wanted:
            continue
        action = entry.get("action")
        if isinstance(action, str) and action in _SIGNAL_RULES and action not in actions:
            actions.append(action)
    return tuple(actions)


def _lazy() -> dict[str, Any]:
    return {
        "UI_GENERATOR_SYSTEM": ui_generator_system,
        "UI_REPAIR_SYSTEM": ui_repair_system,
    }


def __getattr__(name: str) -> Any:
    """Resolve the two artefact-derived constants on first use.

    They are ``str`` constants everywhere they are read; they are lazy here so that
    importing this module (``tests/test_runtime_router.py`` imports the budgets) does not
    require ``src/render/openui_prompt.txt`` to exist, and so that the dialect is never
    a copy: it is read from the generated artefact each first time.
    """
    factory = _lazy().get(name)
    if factory is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return factory()


# ``UI_GENERATOR_SYSTEM`` and ``UI_REPAIR_SYSTEM`` are intentionally absent from this
# list: they are resolved by ``__getattr__`` above, and a static ``__all__`` entry for a
# name that does not exist at module level is a linter error (F822). They are public all
# the same — ``from src.llm.prompts.runtime import UI_GENERATOR_SYSTEM`` works.
__all__ = [
    "ANSWER_KEY_SENTINEL",
    "DECIDE_MAX_TOKENS",
    "DECIDE_TEMPERATURE",
    "DECIDE_USE_CASE",
    "FORMAT_DECIDER_SYSTEM",
    "MAX_UI_RETRIES",
    "PROMPT_VERSION",
    "SOURCE_CONTEXT_MAX_CHARS",
    "UI_MAX_TOKENS",
    "UI_TEMPERATURE",
    "UI_USE_CASE",
    "build_format_prompt",
    "build_repair_prompt",
    "build_ui_prompt",
    "clip_source",
    "signal_actions_for_node",
    "ui_generator_system",
    "ui_max_tokens",
    "ui_repair_system",
]
