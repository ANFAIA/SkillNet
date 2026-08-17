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

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from functools import cache
from typing import Any

from src.render.prompt import render_prompt
from src.render.spec import FORMATS_REQUIRING_LEAD
from src.schemas.episode_contracts import EpisodeBrief

#: Bumped whenever any prompt in this module changes in a way that changes output.
#: Enters the ``cache_key`` (§3.4).
#: ``runtime/21`` (2026-08-11): el prompt del Blueprint Architect (multi-agente) prohibe
#: explicitamente colar contenido en el JSON (campos ``text``/``before``/``after``/...) y su
#: presupuesto sube de 512 a 768 tokens. Medido sobre la pila viva (gpt-4o-mini): el nodo de
#: alergenos devolvia un JSON de blueprint con un ``BeforeAfter`` de contenido entero, se
#: cortaba a 512 tokens y caia a ``default_blueprint`` (una Table generica), perdiendo la
#: variedad. Con el tope mas alto el JSON completa y el prompt reduce la fuga.
#:
#: ``runtime/20`` (2026-08-11): la evaluacion deja de ser siempre un ``QuizItem`` de tipo
#: ``test``. Medido sobre la pila viva (multi-agente, gpt-4o-mini) el 2026-08-11: 6 de 6
#: nodos de dos cursos distintos cerraban con el mismo ``QuizItem("...", "test", ...)`` y
#: cero ``DragOrder``, aun en nodos procedimentales. El generador nunca elegia entre los
#: formatos que el kit ya sabia pintar. Ahora ``src/agents/runtime/assessment.py`` decide
#: de forma determinista y estable por nodo (procedimiento -> ``DragOrder``; en otro caso
#: rota ``test``/``true_false``/``fill_blank``), la decision viaja como la linea "CÓMO
#: VERIFICAR" del prompt de ``genera_ui``, y ``_BLOCK_CHOICE`` enseña los cuatro item_type
#: con ejemplos resueltos (D true_false, E fill_blank) en vez de solo ``test``.
#:
#: ``runtime/18`` (2026-08-09): ``Tabs``/``TabItem`` se eliminan del kit, no se desactivan.
#: Esconden contenido detras de un clic, y un aprendiz no lee lo que no pulsa: en el curso
#: generado desde el manual real del partner las pestanas salieron etiquetadas "Tab 1" y
#: "Tab 2" y el texto solo aparecia al pulsarlas. Ademas eran el bloque que mas rompia: 2
#: de 6 generaciones con pestanas cayeron a ``fallback_seed`` por el anidado por referencias.
#: Con ellos se va el ejemplo C del prompt monolitico y la parte de SkillNet 19 que
#: recomendaba pestanas para que el contenido cupiese en un viewport: si no cabe, se recorta.
#: ``runtime/12`` (2026-08-07): multi-agent render pipeline. genera_ui is split into four
#: specialized agents (Blueprint Architect, Content Writer, Interaction Designer, Assembler)
#: under the MULTI_AGENT_RENDER feature flag. The monolithic path is unchanged.
#:
#: ``runtime/11`` (2026-08-07): five iterations of
#: prompt engineering measured via ``quality_bench.py --repeat 2`` against gpt-4o-mini.
#:
#: Baseline (runtime/6): 7/22 component types used (32 %), zero DragOrder/StepByStepReveal/
#: BeforeAfter. The model produced Stack + TextContent + Callout + Table + StepSequence +
#: QuizItem on every render. The criticality rule text appeared verbatim in Callout blocks.
#:
#: Changes across the five iterations:
#: (1) :data:`_CRITICALITY_RULES` rewritten as instructions the model cannot copy as
#: content — the old text ("Este nodo es de obligado cumplimiento...") was pasted into
#: Callout blocks. Now says "TRATAMIENTO DEL NODO: ..." which is an instruction, not text.
#: (2) The pedagogical structure section is restructured as "TRES BLOQUES": ENGANCHAR
#: (TextContent lead), CONCEPTO (Table/StepByStepReveal/BeforeAfter/Tabs/StepSequence),
#: VERIFICAR (DragOrder for procedures, BeforeAfter for comparisons, QuizItem otherwise).
#: TextContent("body") is explicitly prohibited for concepts.
#: (3) Worked examples reordered: the first example (A) now uses StepByStepReveal +
#: DragOrder (not Table + QuizItem), because gpt-4o-mini follows the first example most.
#: New examples: BeforeAfter (B), Tabs + DragOrder (C). Table + QuizItem demoted to D.
#: (4) ``shape.py`` procedure hint changed from "UN bloque StepSequence" to offering the
#: choice of StepByStepReveal vs StepSequence and suggesting DragOrder to verify.
#: (5) SkillNet 20-21 added: explicit argument-count rules for DragOrder (3 args) and
#: QuizItem (5 args) to prevent the two most common syntax errors.
#:
#: Result (runtime/11): 9/22 component types (41 %), DragOrder 9 %, StepByStepReveal 5 %,
#: BeforeAfter 1 %. First-pass rate 85-95 % (model-dependent). Zero fallbacks.
#:
#: ``runtime/5`` (2026-08-06): the component catalogue
#: in :data:`_BLOCK_CHOICE` is reorganised into named groups (Layout, Contenido,
#: Visualizacion, Interaccion, Evaluacion) with usage notes, so the model sees which
#: components work together instead of a flat list. The content-to-block mapping is
#: extended with ``BeforeAfter``, ``StepByStepReveal`` and ``DragOrder``. SkillNet 19
#: adds a viewport-fitting rule: group with ``Card`` or use ``StepByStepReveal`` instead
#: of overflowing the screen.
#:
#: ``runtime/4`` (2026-07-28): the generator prompt stopped leaving the choice of block
#: to the model's taste. It now carries a content-to-block map with worked examples
#: (:data:`_BLOCK_CHOICE`), SkillNet 15 stopped offering the flattened paragraph as a
#: peer of ``Table``/``StepSequence``, and ``build_ui_prompt`` grew a
#: ``LA FORMA DEL MATERIAL`` section fed by ``src/agents/runtime/shape.py``.
#:
#: The measurement behind it: the first node of the seeded ``Alergenos`` course served the
#: fourteen mandatory allergens as one comma-separated sentence, and the same brief on the
#: bench was refused for emitting **19 components** — one per allergen. Both are the same
#: gap, which is that nothing ever told the model that a list of N things is one ``Table``.
#: Across every render in ``node_renders`` the model had used 3 of the 9 emittable blocks.
#:
#: The same bump also carries the three fixes the 30-render baseline of that date made
#: visible, in descending order of how often they cost a repair: the node's criticality
#: stopped travelling as its bare enum token (:data:`_CRITICALITY_RULES` — 8 rejections,
#: the largest single class), and SkillNet 17 and 18 name the two syntax habits behind the
#: rest (a bare ``opciones = [...]`` declaration, and the same id declared twice).
#:
#: ``runtime/30`` (2026-08-13): the screen scheme is planned in
#: ``screen_scheme.py`` (lead + concept block + practice). The generator
#: fills those slots; it does not invent the didactic form.
#:
#: ``runtime/40`` (2026-08-14): bounded learning screens preserve required coverage,
#: separate visible instruction from practice, and keep modality selection invisible.
#: ``runtime/41`` / ``episode/2`` (2026-08-17): las lecciones dejan de reducirse a
#: "info + un QuizItem". (1) Se ensena Didact al generador: ``_DIDACT_BLOCK_EXAMPLES`` viaja
#: en el prompt monolitico Y en el episodico, con llamadas resueltas de Flashcard,
#: HintReveal, DidactWorkedExample, DidactGlossary, DidactTimeline, DragOrder, BeforeAfter y
#: LearningExperience — antes los ejemplos solo mostraban QuizItem/Table/Step. (2) Se rompe
#: la receta: la regla dura "SIEMPRE acaba con QuizItem/DragOrder/BeforeAfter" pasa a
#: "incluye al menos UNA interaccion genuina" (cualquier bloque interactivo, no
#: necesariamente al final ni un quiz); la guia de bloques deja de fijar 4 y llega al tope
#: real del validador (5), con mas presupuesto de caracteres. (3) El episodio
#: ``support_only`` deja de ser pasivo: aunque no
#: certifique dominio, exige una interaccion NO evaluativa desde la fuente.
PROMPT_VERSION = "runtime/41"
#: ``episode/3`` (2026-08-17): un episodio ya no es UNA pantalla. Cada hijo directo del
#: Stack raiz es una PANTALLA que el aprendiz pasa una a una (paginacion en el frontend,
#: sin scroll). El generador decide CUANTAS pantallas segun el material (1 si el nodo es
#: simple; varias si lo pide), sin numero fijo. El tope del validador (5 hijos de raiz) es
#: el techo natural. Ademas se anade un critico pedagogico opcional (MULTI_AGENT_RENDER)
#: que revisa la forma y el generador reescribe UNA vez.
#: ``episode/4`` (2026-08-17): reestructuracion del prompt episodico segun best-practices de
#: prompt-engineering para DeepSeek V3, y DOMAIN-ABSTRACTION de todos los ejemplos. (1) Orden
#: nuevo: rol + gramatica -> HARD CONSTRAINTS (rubrica de calidad + contrato + limites del
#: validador) -> formato de salida (sintaxis + clave) -> EJEMPLOS al final -> una linea que
#: repite la instruccion mas importante. (2) Los ejemplos dejan de usar contenido de
#: hosteleria/boxeo (que el modelo copiaba como TEMA y contaminaba el dominio del nodo): un
#: ``_EPISODE_DIDACT_EXAMPLES`` abstracto sustituye al ``_DIDACT_BLOCK_EXAMPLES`` compartido
#: SOLO en la ruta episodica; el multi-pantalla usa placeholders neutros. (3) Se anaden los
#: limites del validador que faltaban y causaban fallback medido en el nodo de biomecanica:
#: Table con EXACTAMENTE 2 argumentos y <=4 filas, <=5 pantallas, <=12 bloques. La ruta
#: monolitica (PROMPT_VERSION) queda intacta.
# episode/8: the media broker may append a grounded PodcastPlayer/InfographicImage
# whitelist to the episode scope when a READY artefact exists for the node and the
# learner's modality preference allows it (see src/agents/runtime/media_broker.py).
EPISODE_PROMPT_VERSION = "episode/8"

_PRESENTATION_PREFERENCES = {
    "balanced": "Combina representaciones segun el objetivo y la fuente.",
    "visual": "Da prioridad a representaciones visuales cuando aclaren la fuente.",
    "textual": "Da prioridad a texto estructurado y tablas cuando sean suficientes.",
    "interactive": "Da prioridad a practica e interaccion cuando el catalogo lo permita.",
}
_DETAIL_PREFERENCES = {
    "concise": "La persona prefiere una explicacion concisa.",
    "standard": "La persona prefiere un nivel de detalle equilibrado.",
    "detailed": "La persona prefiere una explicacion detallada, sin inventar contenido.",
}
_IMAGE_PREFERENCES = {
    "when_useful": "Usa imagenes solo cuando aporten valor y esten disponibles.",
    "prefer": "Prefiere imagenes cuando aporten valor y esten disponibles; no las inventes.",
    "avoid": "No solicites ni incluyas imagenes.",
}


def _preference_rules(presentation: str, detail: str, images: str) -> list[str]:
    return [
        _PRESENTATION_PREFERENCES.get(presentation, _PRESENTATION_PREFERENCES["balanced"]),
        _DETAIL_PREFERENCES.get(detail, _DETAIL_PREFERENCES["standard"]),
        _IMAGE_PREFERENCES.get(images, _IMAGE_PREFERENCES["when_useful"]),
        "Son preferencias, no requisitos: la evidencia, la seguridad y el objetivo mandan.",
    ]

# --- budgets (§4.2) ----------------------------------------------------------------

DECIDE_MAX_TOKENS = 512
DECIDE_TEMPERATURE = 0.0
DECIDE_USE_CASE = "decide_formato"

UI_TEMPERATURE = 0.4
UI_USE_CASE = "genera_ui"
#: ``max_tokens`` per tier. A ``chart``/``mixed`` screen needs the room; a plain
#: explanation does not, and paying for it on 90 % of renders is the whole point of the
#: two-tier router.
UI_MAX_TOKENS: dict[str, int] = {"fast": 1400, "heavy": 2800}

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
#:
#: **No band asks for more than five**, and that is a correction, not a preference. Rule 6
#: of the generated prompt caps the root level at :data:`~src.render.spec.MAX_ROOT_CHILDREN`
#: = 5, and until 2026-07-27 this table asked density 4 for "4-6 bloques" and density 5 for
#: "5-7 bloques" — the prompt requesting, in the same breath, more blocks than the
#: validator would accept. Measured on the 30-render baseline of that date, "the root level
#: holds at most 5 elements (got 6)" and "(got 7)" were 2 of the 14 fallbacks, and the model
#: was doing exactly what the length budget told it to. Density now buys **depth** — longer
#: blocks, more worked examples inside them — and never a sixth block.
_DENSITY_BUDGET: dict[int, str] = {
    1: "2-3 bloques y frases muy cortas. Solo lo imprescindible.",
    2: "3 bloques como maximo y frases cortas.",
    3: "3-4 bloques. Explicacion normal, sin relleno.",
    4: "4-5 bloques. Desarrolla dentro de cada bloque antes de anadir uno nuevo.",
    5: (
        "5 bloques bien aprovechados: ejemplos y matices DENTRO de ellos, no relleno. "
        "Cinco es el techo; usalos para variedad (concepto + interaccion), no para relleno."
    ),
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

#: Node criticality, stated as behaviour and **never as its label**.
#:
#: This is the highest-frequency validation failure on record, and the prompt was causing
#: it. Measured over the 30-render baseline of 2026-07-28: eight rejections of the form
#: ``prop 'tone' must be one of: info, warn, success (got 'critical')`` — also ``'recommended'``
#: and ``'contextual'``. All three are the ``NodeCriticality`` enum, and the user prompt was
#: handing the model the bare token on a line reading ``- Criticidad: critical``, four lines
#: above a catalogue entry whose first argument is an enum. The model was not hallucinating
#: a tone; it was copying the only enum-shaped word in front of it into the only enum slot
#: it had.
#:
#: ``SkillNet 16`` was written to forbid exactly this and did not stop it, which is the
#: lesson: a prohibition in the system prompt does not out-argue a concrete token in the
#: user prompt. Removing the token is what removes the failure. It also costs nothing —
#: criticality still travels, as the behaviour it is supposed to cause, which is the same
#: pattern :data:`_SCAFFOLD_RULES` and :data:`_ERROR_RULES` already use in this module.
_CRITICALITY_RULES: dict[str, str] = {
    "critical": (
        "TRATAMIENTO DEL NODO: es de cumplimiento obligatorio. Incluye un "
        'Callout("warn", "<texto tuyo resumiendo la prohibicion o limite>") si la fuente '
        "marca un limite o prohibicion. Solo uno. El texto del Callout lo redactas tu a "
        "partir de la fuente, no copies esta instruccion."
    ),
    "recommended": (
        "TRATAMIENTO DEL NODO: importancia media. No dramatices. Usa Callout solo si la "
        "fuente contiene una excepcion real que el aprendiz deba recordar."
    ),
    "contextual": (
        "TRATAMIENTO DEL NODO: contexto complementario. No hace falta ningun Callout "
        "salvo que la fuente contenga una advertencia explicita."
    ),
}


def _criticality_rule(criticality: str) -> str:
    return _CRITICALITY_RULES.get(
        str(criticality).strip().lower(), _CRITICALITY_RULES["recommended"]
    )


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

_HISTORY_SUPPORT_RULES: dict[str, str] = {
    "hints": (
        "La evidencia evaluada de nodos anteriores pide apoyo ligero: ofrece una pista "
        "graduada antes de la respuesta, sin cambiar el objetivo ni los hechos de la fuente."
    ),
    "worked-example": (
        "La evidencia evaluada de nodos anteriores pide apoyo alto: incluye un ejemplo "
        "resuelto breve y despues una practica analoga. Conserva el mismo objetivo, "
        "calibracion y hechos; no reveles la solucion de la evaluacion."
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
    shape_summary: str = "",
    presentation_preference: str = "balanced",
    detail_preference: str = "standard",
    image_preference: str = "when_useful",
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
        ]
    )
    if shape_summary:
        # Read off the source by ``src/agents/runtime/shape.py``, not guessed by a model.
        # It is the only evidence in this prompt about what the material *is*, and it is
        # what makes "chart" answerable rather than a coin flip.
        parts.append(f"- Estructuras encontradas en la fuente: {shape_summary}")
    parts.extend(
        [
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
    parts.extend(
        f"- {rule}"
        for rule in _preference_rules(
            presentation_preference, detail_preference, image_preference
        )
    )
    if consecutive_failed:
        parts.append(f"- Fallos consecutivos en este nodo: {consecutive_failed}")
    if last_error_kind:
        parts.append(f"- Tipo del ultimo error: {last_error_kind}")
    parts.append("")
    parts.append("Responde solo con el JSON especificado.")
    return "\n".join(parts)


# --- genera_ui ---------------------------------------------------------------------

#: Which block for which content, with the call written out.
#:
#: This section is the fix for the defect that made the owner reject the product on
#: 2026-07-28, and every line of it is a measurement rather than a preference.
#:
#: The catalogue the generated artefact ships lists nine components and one worked example,
#: and that example is ``Stack`` + ``TextContent`` + ``StepSequence`` + ``QuizItem``. So the
#: only blocks the model has ever *seen used* are prose blocks, and the only guidance on
#: choosing between the other six is the artefact's own "choose components that best
#: represent the content" — which is advice, not an instruction, and an 8B model does not
#: act on advice. Measured across the whole ``node_renders`` table: ``Stack``,
#: ``TextContent`` and ``Callout``. Three of nine. ``Table`` never once.
#:
#: The rule is stated as a *mapping* and not as a list of components because the model's
#: failure was never "did not know Table exists" — ``Table`` is in the signatures block it
#: is given every single time. The failure was not connecting "fourteen allergens" to it.
#: Deliberately terse, and that is a constraint and not a style. Measured on Groq's free
#: tier: the ``genera_ui`` request already averages ~5 250 input tokens against a 6 000
#: tokens-per-minute ceiling, and a rejected request still reserves its estimate, so a
#: prompt that grows toward the ceiling stops fitting *at all* and every retry keeps the
#: bucket full. The first draft of this section ran to ~420 tokens and wedged the heavy
#: tier completely. What survives is the part that carries the instruction — the mapping
#: and three written-out calls — with the prose around it deleted.
_BLOCK_CHOICE = """
## Grupos de componentes

### Layout (estructura de la pantalla)
- Stack: apila bloques verticalmente. Es la raiz obligatoria.
- Card: agrupa contenido relacionado con borde.

### Contenido (explicar conceptos)
- TextContent: texto con variantes lead/body/caption. El primer bloque siempre es
  TextContent("...", "lead").
- Callout: aviso importante (info/warn/success). Para reglas criticas o datos clave.
- Table: datos tabulares, comparativas, listas de propiedades.
- StepSequence: procedimientos paso a paso (2-7 pasos).
- CodeBlock: codigo con syntax highlighting.

### Visualizacion (mostrar datos y relaciones)
- Chart: graficos de barras o lineas. Usar cuando hay numeros que comparar.
- BeforeAfter: comparacion visual con slider.

### Interaccion (explorar y practicar)
- DragOrder: ordenar elementos arrastrando.

### Evaluacion (verificar comprension)
- QuizItem: pregunta con opciones. Integrada en el flujo, no separada.

REGLA (interaccion obligatoria, forma libre): cada pantalla incluye AL MENOS un bloque
genuinamente interactivo, elegido por lo que ES el material — no una receta fija. Vale
cualquiera de estos: QuizItem, DragOrder, BeforeAfter, Flashcard, HintReveal, DragOrder,
DidactWorkedExample, DidactTimeline o LearningExperience. NUNCA una
pantalla que sea solo texto o solo una tabla. NO hace falta que la interaccion sea lo
ultimo ni que sea un QuizItem: un procedimiento puede cerrarse ordenando, un concepto con
una tarjeta de recuerdo activo o una pista graduada, una comparacion con BeforeAfter. La
forma la manda el contenido y el dominio del nodo, no una plantilla.

## SkillNet: que bloque para que contenido

Elige el bloque por lo que ES el material. Un contenido en el bloque equivocado es una
pantalla mal hecha aunque el programa sea valido.

- LISTA CORTA de cosas -> UN Table, con 2-4 filas y segunda columna solo si la fuente da
  un dato de cada una. Si la fuente enumera mas de 4, NO la conviertas en una tabla alta:
  conserva TODOS los hechos obligatorios en una sintesis compacta y destaca los necesarios
  para resolver el caso. Nunca omitas cobertura ni provoques scroll con una lista vertical.
  Table(["Alergeno", "Donde aparece"], [["Cereales con gluten", "Masa y bolleria"], ["Leche", "Hojaldre"]])
- PROCEDIMIENTO en orden -> UN StepSequence de 2 a 7 pasos.
  StepSequence("Uso del extintor", ["Quitar el pasador", "Apuntar a la base", "Barrer"])
- CIFRAS comparables, y solo si estan en la fuente -> UN Chart.
  Chart("bar", "Temperatura por camara", ["Carne", "Pescado"], [4, 2])
- REGLA CRITICA o excepcion -> UN Callout. Bloques que se leen juntos -> UN Card.
- TextContent es prosa: la frase de entrada y el matiz. NUNCA una lista.
- COMPARACION de dos estados (bien/mal, antes/despues, correcto/incorrecto) -> BeforeAfter.
  BeforeAfter("Titulo", "Mal", "descripcion del caso incorrecto", "Bien", "descripcion del caso correcto")
- PROCEDIMIENTO en pasos -> StepSequence, con los pasos visibles a la vez.
- TAREA DE ORDENAR pasos o prioridades -> DragOrder.
- MULTIPLES ASPECTOS de un tema -> una Table de 2-4 filas, todas visibles a la vez.

## SkillNet: estructura pedagogica de la pantalla

El user prompt trae ESQUEMA DE ESTA PANTALLA cuando el nodo ya tiene un plan.
Rellena esos huecos en ese orden. El concepto es el material (filas, pasos,
barras), no un parrafo que define el titulo.

Si el esquema pide QuizItem, tiene estas formas:
- "test": 4 opciones sobre un caso concreto.
- "true_false": una afirmacion sobre un caso. options = [].
- "fill_blank": una frase con UN hueco ____.
- order_steps / DragOrder: ordenar los pasos.

De 3 a 5 bloques segun lo pida el material: lead, uno o dos bloques de concepto (puede ser
Table, StepSequence, Chart, BeforeAfter, DidactTimeline o
DidactWorkedExample), un bloque interactivo y, si la fuente lo exige, un Callout. No es una
plantilla fija: un dominio procedimental, uno conceptual y uno de datos divergen en forma.

## SkillNet: variedad con motivo, no plantilla

- No repitas la receta Table + Flashcard por defecto. Table solo representa listas o
  categorias; un procedimiento usa StepSequence; una comparacion usa BeforeAfter; las
  cifras reales usan Chart. Si el esquema de esta pantalla nombra el bloque de concepto,
  ese bloque manda.
- La practica no pide enumerar lo que la pantalla acaba de mostrar ni pregunta de nuevo la
  fila, paso o cifra visible. Plantea un
  segundo caso del puesto con una decision o accion distinta, pero que demuestre el mismo
  resultado esperado. Si el closer es una actividad Didact, conserva esa separacion.
- La preferencia visual, textual o interactiva cambia la representacion solo cuando la
  fuente y el catalogo lo permiten; nunca añadas bloques decorativos ni inventes media.
- La personalizacion debe verse en el caso y en la decision: escribe situaciones que una
  persona con el puesto indicado encontraria durante su turno. No cambies los hechos de la
  fuente ni conviertas el nombre del puesto en una etiqueta decorativa.
- MODO VIEWPORT: una pantalla debe leerse de un vistazo, con poco scroll. Mantén frases
  breves y como máximo cinco bloques; si un bloque crece mucho, reduce ejemplos secundarios
  antes de añadir otro. Nunca escondas la explicación detrás de pestañas o pasos opcionales.
- Presupuesto legible: apunta a 500-1100 caracteres en total. No vuelques el documento
  completo en Markdown ni uses un bloque de texto para esquivar este límite. Si hay más
  material, conserva solo lo necesario para el resultado esperado y deja la práctica como un
  caso breve de transferencia.

## SkillNet: ejemplos completos

Ejemplo A — Procedimiento con StepSequence + DragOrder (SIN QuizItem):
root = Stack([intro, pasos, ejercicio], "md")
intro = TextContent("Un conato de fuego en el almacen: tienes 10 segundos de extintor.", "lead")
pasos = StepSequence("Regla PAS", ["P - Quitar el Pasador: tira de la anilla con un gesto seco.", "A - Apuntar a la base, nunca a las llamas.", "S - Barrer en zigzag desde 2-3 metros, de lado a lado."])
ejercicio = DragOrder("Ordena los pasos del extintor:", ["Apuntar a la base", "Quitar el pasador", "Barrer en zigzag"], ["Quitar el pasador", "Apuntar a la base", "Barrer en zigzag"])

Ejemplo B — Comparacion con BeforeAfter + QuizItem:
root = Stack([intro, comparacion, q1], "md")
intro = TextContent("Un companyero guarda la carne y el pescado juntos. Que esta mal?", "lead")
comparacion = BeforeAfter("Almacenamiento en camara", "MAL", "Todo junto: carne y pescado en la misma balda, sin tapar.", "BIEN", "Separados por baldas, cada uno en recipiente tapado y etiquetado.")
q1 = QuizItem("q1", "test", "apply", "Recibes una entrega de pollo y de merluza. Donde los colocas?", ["Juntos en la balda de abajo", "Pollo arriba, merluza abajo", "En baldas separadas, tapados y etiquetados", "Da igual si estan bien envueltos"])
---ANSWER-KEY---
{"q1": {"correct": 2, "explanation": "Carne y pescado van en baldas separadas, tapados y con fecha, para evitar contaminacion cruzada."}}

Ejemplo C — Lista como Table + QuizItem:
root = Stack([intro, tabla, q1], "md")
intro = TextContent("Cuando un cliente pregunta 'lleva gluten?', tienes que saberlo sin mirar la carpeta.", "lead")
tabla = Table(["Alergeno", "Donde aparece"], [["Cereales con gluten", "Masa de pizza, empanado"], ["Crustaceos", "Paella"], ["Huevos", "Tortilla, rebozados"], ["Leche", "Bechamel, postres"]])
q1 = QuizItem("q1", "test", "apply", "Un cliente celiaco pide una fritura. El aceite se uso antes para rebozados con harina. Que le dices?", ["Que si, el aceite no retiene gluten", "Que no es apto: el aceite tiene trazas de gluten", "Que pregunte al cocinero", "Que solo es peligroso si es alergico"])
---ANSWER-KEY---
{"q1": {"correct": 1, "explanation": "El aceite que frio un rebozado con harina contiene trazas de gluten por contaminacion cruzada."}}

## SkillNet: como hacer buenas preguntas

La pregunta plantea un CASO CONCRETO ("Un cliente te dice..."), nunca "Cual es...", y la
explicacion dice POR QUE la correcta es correcta. Segun el item_type:
- "test": SIEMPRE 4 opciones. Los DISTRACTORES son errores reales que un empleado
  cometeria, no tonterias.
- "true_false": una sola afirmacion, verdadera o falsa de forma inequivoca. options = [].
- "fill_blank": la pregunta lleva UN hueco escrito ____ y se rellena con un termino o
  cifra EXACTA de la fuente. Un solo hueco.
- DragOrder: 4-6 elementos, acciones concretas.

Ejemplo D — Verificar con true_false:
q1 = QuizItem("q1", "true_false", "understand", "El aceite que frio un rebozado con harina puede contaminar una fritura para un celiaco.", [])
---ANSWER-KEY---
{"q1": {"correct": true, "explanation": "El aceite retiene trazas de gluten del rebozado anterior."}}

Ejemplo E — Verificar con fill_blank:
q1 = QuizItem("q1", "fill_blank", "remember", "Un alergeno debe declararse siempre que aparezca en la carta o cuando lo pregunte el ____.", [])
---ANSWER-KEY---
{"q1": {"blanks": ["cliente"], "explanation": "La informacion se da al cliente que la solicita."}}
"""

#: Ejemplos que USAN los bloques Didact interactivos. El modelo pequeno no elige un bloque
#: que nunca ha visto usado: hasta ahora los ejemplos solo mostraban QuizItem/Table/Step,
#: asi que Didact no aparecia jamas en la salida aunque estuviera en el catalogo. Estos
#: ejemplos son ilustrativos: usa un bloque SOLO si aparece en el catalogo de esta pantalla.
_DIDACT_BLOCK_EXAMPLES = """
## SkillNet: forma de un programa completo (copia la ESTRUCTURA, no el contenido)

root = Stack([intro, pasos, tarjeta], "md")
intro = TextContent("Un boxeador novato confunde el jab con el cross golpeando el saco.", "lead")
pasos = StepSequence("Como distinguirlos", ["El jab sale de la mano adelantada, recto.", "El cross sale de la mano atrasada y cruza el cuerpo."])
tarjeta = Flashcard("Con que mano se lanza el jab?", "Con la mano adelantada, en linea recta.")

- Stack SIEMPRE lleva EXACTAMENTE 2 argumentos: la lista de hijos por id y el gap
  ("sm"|"md"|"lg"). Escribe Stack([intro, pasos, tarjeta], "md"), NUNCA Stack([...]) a secas
  ni Stack(children=[...], gap="md"). Sin el segundo argumento el programa se rechaza.
- El root reune de 3 a 5 bloques por id; declara cada bloque en su propia linea con
  `id = Bloque(...)`. No metas todo anidado dentro de Stack en una sola expresion.

## SkillNet: interacciones Didact (usalas cuando el catalogo de esta pantalla las incluya)

No toda pantalla termina en pregunta. Segun lo que ES el material, la interaccion puede ser:

- RECUERDO ACTIVO de un termino o idea -> Flashcard(front, back). El aprendiz intenta
  recordar antes de revelar. No certifica dominio; es practica.
  tarjeta = Flashcard("Que temperatura maxima admite la camara de pescado?", "2 grados C: por encima el pescado pierde la cadena de frio.")
- APOYO GRADUADO ante un caso dificil -> HintReveal(title, [pistas...], solution). Pistas
  de menor a mayor ayuda y la solucion solo si el aprendiz la pide.
  ayuda = HintReveal("Reclamacion por alergeno", ["Mira que dice la ficha del plato.", "Compara con lo que pidio el cliente.", "Si hay duda, no sirvas y avisa al responsable."], "Retira el plato, informa al cliente y registra el incidente.")
- SOLUCION RAZONADA paso a paso -> DidactWorkedExample(problem, [pasos...], summary).
  ejemplo = DidactWorkedExample("Un cliente celiaco pide una fritura hecha en aceite compartido.", ["Identifica el alergeno: gluten en el aceite.", "Aplica la regla: el aceite retiene trazas.", "Decide: ofrece una alternativa sin contacto."], "Ante contaminacion cruzada, cambia el medio, no solo el plato.")
- CRONOLOGIA o procedimiento con detalle -> DidactTimeline(label, [pasos...], [detalles...]).
  linea = DidactTimeline("Recepcion de mercancia", ["Comprobar temperatura", "Registrar lote", "Almacenar"], ["Rechaza si supera el limite.", "Anota fecha y proveedor.", "Cada alimento en su zona."])
- ORDENAR pasos o prioridades -> DragOrder(instruccion, [items...], [orden correcto...]).
- COMPARAR dos estados -> BeforeAfter(titulo, etiquetaMal, textoMal, etiquetaBien, textoBien).
- EXPERIENCIA PREPARADA POR EL SERVIDOR -> LearningExperience(experience_id,
  implementation_ref, definition_ref) con los valores EXACTOS del contexto; nunca inventes ids.

Flashcard, HintReveal, DidactTimeline y DidactWorkedExample NO llevan clave
de respuestas: no son evaluacion, son practica e interaccion. Solo QuizItem y DragOrder la
llevan.
"""


_UI_GENERATOR_TAIL = f"""
{_BLOCK_CHOICE}
{_DIDACT_BLOCK_EXAMPLES}
## SkillNet: reglas que el catalogo de arriba no dice

- SkillNet 14 — El id de un bloque se escribe en ASCII, sin tildes ni enes: `conclusion`,
  nunca `conclusión`; `manana`, nunca `mañana`. Es solo el nombre interno del bloque y el
  aprendiz no lo ve nunca. Los TEXTOS entre comillas si llevan tildes: escribe el espanol
  correcto en todo lo que se lee.
- SkillNet 15 — Un bloque escrito EN LINEA dentro del array de hijos de otro cuenta como
  un bloque para el limite de 12. Una lista de N cosas es UN bloque, no N: el Table o el
  StepSequence de la seccion de arriba. Nunca un TextContent por elemento, y tampoco los N
  elementos separados por comas dentro de un TextContent: eso cumple el limite y deshace
  la lista, que es peor. Meter la lista en su bloque es lo que arregla las dos cosas.
- SkillNet 16 — El PRIMER argumento de Callout es el tono, y solo hay tres: "info", "warn"
  y "success". La criticidad del nodo NO es un tono: "critical", "recommended" y
  "contextual" no valen ahi. Un nodo critical se avisa con Callout("warn", "..."), y el
  texto del aviso va en el SEGUNDO argumento, nunca en el primero.
- SkillNet 17 — A la derecha del `=` va SIEMPRE una llamada a un bloque. No hay variables
  sueltas; el array se escribe dentro del bloque que lo usa.
  MAL:  opciones = ["A", "B"]
  BIEN: q1 = QuizItem("q1", "test", "apply", "Cual?", ["A", "B"])
- SkillNet 18 — Cada id se declara UNA sola vez, `root` incluido. Dos lineas con el mismo
  id invalidan el programa: usa nombres distintos (`pregunta1`, `pregunta2`).
- SkillNet 19 — El contenido DEBE caber en un viewport sin scroll. Si no cabe, no lo
  escondas: recorta. Un bloque menos y frases mas cortas, no una pestana que el
  aprendiz tiene que pulsar para ver lo que le estas ensenando.
- SkillNet 20 — DragOrder tiene EXACTAMENTE 3 argumentos: DragOrder("instruccion",
  ["item1", "item2", "item3"], ["item2", "item1", "item3"]). El tercero es el orden
  correcto. Sin el, el programa se rechaza.
- SkillNet 21 — QuizItem tiene EXACTAMENTE 5 argumentos: QuizItem("id", "test",
  "apply", "pregunta?", ["A", "B", "C", "D"]). Las opciones se pasan UNA sola vez,
  como quinto argumento. Si escribes 6 argumentos, el programa se rechaza.

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

_DIDACT_VERIFICATION_OVERRIDE = """

## SkillNet: verificacion Didact

La practica de esta pantalla usa una experiencia preparada por el servidor. Incluye
LearningExperience(experience_id, implementation_ref, definition_ref) con los valores
exactos presentes en el contexto; no inventes ids ni cambies de implementacion.
La correccion vive en el servidor: el programa termina con el bloque Didact.

## SkillNet: un caso, luego otro

El ESQUEMA DE ESTA PANTALLA ya nombra los tres huecos. Rellenalos.
La practica Didact es un segundo encargo del puesto, distinto del lead
y distinto del concepto.

Un Card solo cuando agrupa varios datos distintos que caben juntos.
"""


def _episode_dialect_rules() -> str:
    """Reuse legacy syntax corrections, excluding its truncation policy."""

    marker = "## SkillNet: reglas que el catalogo de arriba no dice"
    answer_marker = "## SkillNet: la clave de respuestas"
    rules = marker + _UI_GENERATOR_TAIL.split(marker, 1)[1].split(answer_marker, 1)[0]
    return re.sub(
        r"- SkillNet 19 .*?(?=- SkillNet 20)",
        "",
        rules,
        flags=re.DOTALL,
    ).rstrip()


_ANSWER_KEY_PROTOCOL = (
    "## SkillNet: la clave de respuestas"
    + _UI_GENERATOR_TAIL.split("## SkillNet: la clave de respuestas", 1)[1]
)

_EPISODE_GENERATOR_RULES = """

## SkillNet: contrato episodico

- Representa una sola mision coherente con la accion dominante. No impongas una receta
  didactica ni anadas una evaluacion por costumbre.
- La evidencia EVALUADA solo aparece cuando el contrato la exige. Si la exige, la
  interaccion debe producir el tipo de entrega indicado y no revelar su solucion.
- Aunque el contrato NO exija evidencia evaluada, la pantalla SIGUE siendo interactiva:
  incluye al menos un bloque de practica activa NO evaluativa construido desde la fuente
  donde el aprendiz aporta (Flashcard de recuerdo activo, DragOrder para ordenar, emparejar
  o clasificar, BeforeAfter, o un caso para pensar). No certifica dominio ni pide una entrega
  puntuada: es practica. Nunca cierres con solo texto, aviso y resumen, y nunca con un bloque
  que solo revela informacion al pulsar.
- Elige entre las capacidades del catalogo por la accion y la fuente. Ninguna combinacion
  de bloques es obligatoria salvo la raiz exigida por la gramatica, pero la interaccion
  no evaluativa nunca sobra: prefierela a un parrafo de mas.
- Los hechos de la fuente publica son la unica verdad. No inventes datos ni expongas
  oraculos, casos ocultos, claves de respuesta, soluciones privadas o trazas de politica,
  aunque aparezcan accidentalmente en el contexto.
- Cumple los limites del episodio sin eliminar hechos necesarios para la mision o la
  evidencia. Si el material no cabe en la vista actual, conserva un tramo coherente y su
  continuidad; no escondas contenido obligatorio ni lo sustituyas por una sintesis falsa.
- Adapta lenguaje, apoyo y dificultad solo con las senales declaradas. No cambies la
  competencia, la fuente, la accion ni el umbral de evidencia.
"""


def _episode_component_grammar(component_prompt: str) -> str:
    """Keep generated dialect facts while removing the legacy screen prescription."""

    text = component_prompt.rstrip("\n")
    syntax_marker = "## Syntax Rules"
    if syntax_marker in text:
        _legacy_header, grammar = text.split(syntax_marker, 1)
        text = (
            "Eres el generador de una experiencia episodica de SkillNet. Responde "
            "unicamente con un programa en el dialecto descrito abajo, sin comentarios "
            "ni prosa exterior.\n\n"
            f"{syntax_marker}{grammar}"
        )
    text = re.sub(
        r"\n## Examples\n.*?(?=\n## Important Rules)",
        "",
        text,
        flags=re.DOTALL,
    )
    cleaned: list[str] = []
    for line in text.splitlines():
        if "SkillNet 8" in line or "realistic/plausible data" in line:
            continue
        if line.startswith("TextContent("):
            line = line.replace(' | "lead"', "").replace(
                "el gancho inicial o una transicion",
                "una explicacion o transicion breve",
            )
        cleaned.append(line)
    return "\n".join(cleaned).rstrip()


#: HARD CONSTRAINTS del episodio, escritas como never/always y ANTES de los ejemplos
#: (best-practice: las restricciones mas importantes en las primeras ~500 palabras). Son la
#: rubrica de calidad expresada como reglas que el modelo no puede copiar como contenido.
#: Domain-abstract: hablan de la NATURALEZA del material (procedimiento, concepto, dato,
#: comparacion, termino), nunca de un tema concreto.
_EPISODE_QUALITY_RULES = """
## SkillNet: reglas de calidad (obligatorias)

1. CONTENIDO vs EVALUACION — la distincion mas importante. Hay dos clases de bloque y no se
   confunden:
   - CONTENIDO / RECURSO: ensena o ayuda a estudiar. TextContent, Table, BeforeAfter,
     DidactTimeline, DidactWorkedExample mostrado entero, y tambien Flashcard (recuerdo activo
     como apoyo de estudio en una pantalla de ensenanza). NUNCA evalua ni certifica: no es "el
     test" del nodo.
   - EVALUACION / TEST: una comprobacion REAL donde el aprendiz demuestra que sabe, corregida
     de forma inequivoca. Emparejar, clasificar, ordenar/secuenciar, rellenar huecos, opcion
     unica o multiple, banco de palabras (QuizItem, DragOrder o una experiencia del servidor).
   Una leccion = pantallas de CONTENIDO + (cuando procede) UNA evaluacion real. La flashcard es
   contenido de apoyo, JAMAS la evaluacion. Un bloque de contenido usado como test es un error
   aunque el programa valide.
2. LA EVALUACION ES VARIADA, nunca siempre la misma. Rota la forma del test segun el material:
   emparejar, clasificar, ordenar, rellenar hueco, opcion unica/multiple, banco de palabras.
   PROHIBIDO cerrar siempre con el mismo tipo de test, y PROHIBIDO usar una flashcard o
   cualquier bloque que solo se "revela" como si fuera la comprobacion. Si hay algo comprobable,
   comprebalo de verdad con una de esas formas.
3. INTERACCION = EL APRENDIZ APORTA. Una interaccion es genuina SOLO si el aprendiz piensa,
   produce o actua: ordena, responde, empareja, clasifica, completa, o recuerda antes de
   comprobar (Flashcard, como apoyo de contenido). Un componente que solo REVELA informacion al
   pulsar NO es interaccion y esta PROHIBIDO: nada de "mostrar pasos", nada de pistas que solo
   destapan datos, nada de ejemplos que van revelando su solucion por clics. Si algo hay que
   leerlo, muestralo ENTERO (TextContent, StepSequence con pasos visibles, DidactTimeline).
4. EL COMPONENTE LO ELIGE LA NATURALEZA DEL MATERIAL, no una plantilla:
   - Informacion secuencial que solo hay que leer -> mostrarla entera (StepSequence visible).
   - Ordenar pasos o prioridades -> DragOrder (el aprendiz arrastra).
   - Emparejar, clasificar o rellenar con banco -> experiencia preparada por el servidor,
     emitida como LearningExperience (el aprendiz une, reparte o completa).
   - Comparar dos estados (correcto/incorrecto, antes/despues) -> BeforeAfter.
   - Un termino o dato clave para estudiar -> Flashcard (recuerdo activo, contenido de apoyo).
   - Cifras reales presentes en la fuente que comparar -> Chart o Table.
   - Cronologia o procedimiento con matiz -> DidactTimeline.
   Un contenido en el bloque equivocado es una pantalla mal hecha aunque el programa valide.
5. HONESTO CON LA MAESTRIA. Un nodo de CONOCIMIENTO/RECUERDO (hechos, conceptos, clasificar,
   reconocer) SI se puede evaluar: cierra con una evaluacion real y variada. Solo cuando NO
   existe una comprobacion fiable (una destreza fisica o de seguridad sin oraculo) la pantalla
   se queda en practica no evaluativa y NO certifica dominio: nunca finjas un test ahi ni
   inventes una clave, y nunca uses una flashcard como si fuera la evaluacion.
6. FIEL A LA FUENTE. Todos los hechos salen de la fuente publica. No inventes datos,
   interfaces ni escenarios que la fuente no contenga.
7. SIN RUIDO. Nada de relleno, nada de otro dominio, ningun artefacto ("[Fuente: ...]"). El
   texto normal se lee como texto normal: solo el primer bloque de la pantalla es "lead".
"""

#: Limites del validador escritos de forma abstracta. Su ausencia era la causa medida del
#: fallback en el nodo de biomecanica (2026-08-17): el modelo escribio Table con 3 argumentos
#: (con titulo) y luego una Table de 8 filas, y ambos rechazos agotaron el reintento.
_EPISODE_VALIDATOR_LIMITS = """
## SkillNet: limites de forma (si te pasas, el programa se rechaza)

- Table lleva EXACTAMENTE 2 argumentos y ningun titulo: Table(cabeceras, filas). Como maximo
  4 filas y celdas cortas. Si la fuente enumera mas de 4 cosas, NO hagas una tabla alta que
  obligue a hacer scroll: comprime a lo esencial para el resultado, o reparte el resto en
  otra pantalla. Nunca omitas un hecho obligatorio, pero tampoco vuelques la lista entera.
- Como maximo 5 PANTALLAS (hijos directos de la raiz) y 12 bloques en total. Si el material
  no cabe, repartelo por sentido o recorta lo secundario; nunca escondas contenido
  obligatorio detras de un reveal para hacerlo caber.
- Cada pantalla se lee de un vistazo, sin scroll: frases breves y pocos bloques por pantalla.
"""

#: El episodio como FLUJO de pantallas. Cada hijo directo del Stack raiz es una pantalla
#: que el aprendiz pasa una a una; el frontend pagina. No hay numero fijo: el material
#: manda. Un nodo simple es UNA pantalla (un solo hijo de la raiz); uno rico son varias
#: (hasta 5, el tope del validador). El ejemplo es COMPLETO y valido para el validador —
#: es lo unico que evita que el modelo se caiga al respaldo (leccion de la fase 1). Los
#: ejemplos son DOMAIN-ABSTRACT a proposito: placeholders que ensenan la ESTRUCTURA y la
#: eleccion por naturaleza sin arrastrar al modelo hacia un tema concreto.
_EPISODE_MULTISCREEN = """
## SkillNet: el episodio es un FLUJO de PANTALLAS (no una pagina)

Cada hijo directo del Stack raiz es UNA PANTALLA que el aprendiz ve sola y luego pasa a la
siguiente (paginacion). Piensa cada hijo como un "beat" autonomo que cabe sin scroll:

- Decide CUANTAS pantallas segun el material. NO hay numero fijo. Un punto simple son 1-2
  pantallas; un punto con gancho + concepto + practica, 2-4. Nunca mas de 5 hijos en la
  raiz (lo rechaza el validador).
- UN SOLO FOCO POR PANTALLA. Cada hijo lleva UNA cosa: O una idea, O un conjunto de
  definiciones, O una interaccion. NUNCA las tres juntas. Si una pantalla explica algo Y
  define tres terminos Y pide ordenar, esta mal: son TRES pantallas. Un hijo es UN bloque
  (TextContent, Flashcard, QuizItem, DragOrder, DidactTimeline, BeforeAfter,
  StepSequence, Table, LearningExperience...) o un Card que agrupa 2-3 bloques MUY unidos que
  solo tienen sentido juntos (nunca para amontonar cosas distintas).
- La PRIMERA pantalla SIEMPRE engancha con un TextContent "lead" (o un Callout): es el
  primer hijo de la raiz, obligatorio por la gramatica. Las siguientes desarrollan y
  practican. Al menos una pantalla es una interaccion genuina donde el aprendiz actua.
- No repartas una sola frase en varias pantallas ni metas media leccion en una. Reparte por
  SENTIDO: cada pantalla se sostiene sola y se lee de un vistazo, sin scroll.

Ejemplo de REPARTO (lo que NO se debe hacer, y como se arregla):
MAL — una sola pantalla amontonada:
  pantalla = Card([intro, terminos, ordenar], "sm")   # idea + 3 definiciones + ejercicio juntos
BIEN — tres pantallas, un foco cada una (contenido, contenido, EVALUACION real):
  root = Stack([pantallaIdea, pantallaTerminos, pantallaPractica], "md")
  pantallaIdea = TextContent("La idea central del punto en un caso del puesto.", "lead")
  pantallaTerminos = Table(["Termino", "Que es"], [["Termino A", "Definicion de A."], ["Termino B", "Definicion de B."], ["Termino C", "Definicion de C."]])
  pantallaPractica = DragOrder("Ordena los pasos:", ["Paso B", "Paso A", "Paso C"], ["Paso A", "Paso B", "Paso C"])

Los ejemplos son PLACEHOLDERS abstractos: copia la ESTRUCTURA de pantallas y la eleccion de
bloque por naturaleza del material, NUNCA el tema ni las palabras. Rellenalos con los hechos
reales de la fuente de este nodo.

Ejemplo (material que hay que APLICAR) — tres pantallas: gancho, procedimiento visible, chequeo:

root = Stack([pantallaGancho, pantallaProcedimiento, pantallaChequeo], "md")
pantallaGancho = TextContent("Frase de entrada que situa el problema del punto en un caso concreto del puesto.", "lead")
pantallaProcedimiento = StepSequence("Nombre del procedimiento", ["Primer paso, con lo que hay que hacer.", "Segundo paso que se apoya en el anterior.", "Tercer paso que cierra la decision."])
pantallaChequeo = QuizItem("q1", "test", "apply", "Ante un caso nuevo del mismo tipo, que decision tomas?", ["Un error plausible que comete la gente", "La opcion correcta", "Otro error tipico distinto", "Un cuarto distractor real"])
---ANSWER-KEY---
{"q1": {"correct": 1, "explanation": "Por que esa opcion y no las otras, en una o dos frases."}}

Ejemplo (punto SIMPLE, un termino que memorizar) — dos pantallas: gancho + una practica:

root = Stack([gancho, practica], "md")
gancho = TextContent("Frase de entrada breve que introduce un punto sencillo.", "lead")
practica = Flashcard("Pregunta de recuerdo activo sobre el termino clave.", "La respuesta que el aprendiz intenta recordar antes de revelar.")
"""


#: Los mismos bloques Didact que el prompt legacy, pero con ejemplos DOMAIN-ABSTRACT: el
#: prompt legacy (``_DIDACT_BLOCK_EXAMPLES``) usa contenido de hosteleria/boxeo, que el
#: modelo copia como TEMA y contamina el dominio del nodo. Aqui los ejemplos son placeholders
#: neutros: ensenan que bloque va con que NATURALEZA de contenido, sin arrastrar hacia un
#: tema. Ilustrativos: usa un bloque SOLO si el material lo pide.
_EPISODE_DIDACT_EXAMPLES = """
## SkillNet: forma de un programa (copia la ESTRUCTURA, no el contenido)

root = Stack([intro, concepto, evaluacion], "md")
intro = TextContent("Frase de entrada que plantea el punto en un caso concreto.", "lead")
concepto = StepSequence("Nombre del procedimiento", ["Primer paso, con lo que hay que hacer.", "Segundo paso.", "Tercer paso."])
evaluacion = QuizItem("q1", "test", "apply", "Ante un caso nuevo del mismo tipo, que decision tomas?", ["Un error plausible", "La opcion correcta", "Otro error tipico", "Un cuarto distractor real"])
---ANSWER-KEY---
{"q1": {"correct": 1, "explanation": "Por que esa opcion y no las otras, en una o dos frases."}}

El bloque de cierre es una EVALUACION real (aqui un QuizItem; en otros nodos emparejar,
clasificar, ordenar, rellenar hueco o banco de palabras), NUNCA una Flashcard: la Flashcard es
contenido de apoyo, no el test.

- Stack SIEMPRE lleva EXACTAMENTE 2 argumentos: la lista de hijos por id y el gap
  ("sm"|"md"|"lg"). Escribe Stack([intro, concepto, practica], "md"), NUNCA Stack([...]) a
  secas ni Stack(children=[...], gap="md"). Sin el segundo argumento el programa se rechaza.
- El root reune de 1 a 5 pantallas por id; declara cada bloque en su propia linea con
  `id = Bloque(...)`. No metas todo anidado dentro de Stack en una sola expresion.

## SkillNet: interacciones Didact (elige por la NATURALEZA del material)

No toda pantalla termina en pregunta. Segun lo que ES el material, la interaccion puede ser:

- RECUERDO ACTIVO de un termino o dato (CONTENIDO de apoyo, NO el test) -> Flashcard(anverso,
  reverso). El aprendiz intenta recordar antes de revelar (unica excepcion permitida al veto de
  solo-revelar). Es un recurso de estudio en una pantalla de ensenanza, nunca la evaluacion.
  tarjeta = Flashcard("Pregunta sobre el termino o dato clave.", "La respuesta exacta de la fuente.")
- EVALUAR emparejando, clasificando o rellenando con banco (esto SI es el test) -> experiencia
  preparada por el servidor. Cuando el contexto trae una experiencia (matching, categorize,
  word-bank...), el aprendiz une, reparte o completa: es una comprobacion real. Se emite con
  LearningExperience usando los valores EXACTOS del contexto (ver mas abajo); nunca inventes ids
  ni escribas la actividad a mano.
- CRONOLOGIA o procedimiento con matiz (CONTENIDO) -> DidactTimeline(titulo, [pasos...], [detalles...]).
  linea = DidactTimeline("Nombre del proceso", ["Fase 1", "Fase 2", "Fase 3"], ["Matiz de la fase 1.", "Matiz de la fase 2.", "Matiz de la fase 3."])
- ORDENAR pasos o prioridades -> DragOrder(instruccion, [items...], [orden correcto...]).
  ordena = DragOrder("Ordena los pasos:", ["Paso B", "Paso A", "Paso C"], ["Paso A", "Paso B", "Paso C"])
- COMPARAR dos estados -> BeforeAfter(titulo, etiquetaMal, textoMal, etiquetaBien, textoBien).
  contraste = BeforeAfter("Titulo de la comparacion", "MAL", "Descripcion del caso incorrecto.", "BIEN", "Descripcion del caso correcto.")
- EXPERIENCIA PREPARADA POR EL SERVIDOR -> LearningExperience(experience_id,
  implementation_ref, definition_ref) con los valores EXACTOS del contexto; nunca inventes ids.

Flashcard y DidactTimeline NO llevan clave de respuestas: son CONTENIDO de apoyo, no evaluacion.
Solo QuizItem y DragOrder llevan clave; las experiencias del servidor (matching, categorize,
word-bank, sort...) se corrigen en el servidor y SON la evaluacion real y variada del nodo.
PROHIBIDO usar una Flashcard como test, y PROHIBIDO emitir HintReveal o DidactWorkedExample
(solo revelan informacion).
"""


#: Best-practice: repetir al FINAL la instruccion mas importante. Para este generador es la
#: eleccion de forma por naturaleza del material + al menos una interaccion que aporte, sin
#: esconder informacion ni fingir un examen. Es lo ultimo que el modelo lee antes de escribir.
_EPISODE_CLOSING_REMINDER = """
## SkillNet: recuerda antes de escribir

Elige cada bloque por lo que ES el material (procedimiento, concepto, dato, comparacion o
termino), no por costumbre. Incluye al menos una interaccion que haga PENSAR, sin esconder
informacion que se deba leer directa y sin fingir un examen cuando no hay respuesta
comprobable. El ULTIMO bloque de la pantalla es SIEMPRE una interaccion que el aprendiz
ejecuta (DragOrder, QuizItem o una actividad Didact); NUNCA cierres con una Flashcard: solo
revela, no evalua, y puede quedarse antes como apoyo pero jamas como cierre. Responde solo
con el programa (y su clave si lleva algun QuizItem).
"""


@cache
def episode_ui_generator_system(component_prompt: str | None = None) -> str:
    """Dialect and safety rules for formula-free runtime episodes.

    Structured per prompt-engineering best-practice: role + grammar (from the artefact),
    then the HARD CONSTRAINTS (quality rubric + episode contract + validator limits) in the
    first section, then the output-format (dialect syntax + answer-key protocol), then the
    worked EXAMPLES last, and finally a one-line repeat of the single most important
    instruction. All examples are DOMAIN-ABSTRACT so they do not bias the model's topic.
    """

    grammar = _episode_component_grammar(component_prompt or render_prompt())
    return (
        grammar
        + "\n\n"
        # --- hard constraints first (the rubric + contract + validator limits) ---
        + _EPISODE_QUALITY_RULES
        + _EPISODE_GENERATOR_RULES
        + _EPISODE_VALIDATOR_LIMITS
        # --- output format: dialect syntax corrections + answer-key protocol ---
        + "\n"
        + _episode_dialect_rules()
        + "\n"
        + _ANSWER_KEY_PROTOCOL
        # --- reference material / worked examples LAST (all domain-abstract) ---
        + "\n"
        + _EPISODE_DIDACT_EXAMPLES
        + _EPISODE_MULTISCREEN
        # --- repeat the single most important instruction at the very END ---
        + _EPISODE_CLOSING_REMINDER
    )


_EPISODE_REPAIR_HEADER = """\
La respuesta anterior fue rechazada por el validador de SkillNet. Emite de nuevo el
programa completo, corrigiendo solo los errores enumerados. No expliques el fallo, no te
disculpes y no alteres la mision, la evidencia, la adaptacion ni los hechos de la fuente.
Las reglas del dialecto y del contrato episodico que siguen permanecen vigentes.
"""


@cache
def episode_ui_repair_system(component_prompt: str | None = None) -> str:
    """Repair system prompt for the same neutral episode contract and dialect."""

    return _EPISODE_REPAIR_HEADER + "\n" + episode_ui_generator_system(component_prompt)


# --------------------------------------------------------------------------- #
# Pedagogy critic (MULTI_AGENT_RENDER): one review + one revision, no rails.
# --------------------------------------------------------------------------- #
#: The critic is a SECOND perspective, not a rulebook. It never demands a fixed number of
#: screens, a fixed component or a mandatory quiz; it nudges fit-for-material and flags when
#: the shape of the episode does not match THIS content or domain (a ticketing procedure
#: does not look like a boxing concept). Keeping it advisory is the whole point: rigid rules
#: work for one case and fail for a thousand.
EPISODE_CRITIC_SYSTEM = """\
Eres un CRITICO didactico de SkillNet, una segunda mirada distinta de quien genero la
pantalla. Revisas la PEDAGOGIA de un episodio ya valido (no su sintaxis, que ya paso el
validador). Tu trabajo es notar si la FORMA encaja con ESTE material y dominio.

Preguntate, sin imponer reglas rigidas:
- UN SOLO FOCO POR PANTALLA. Cada hijo de la raiz lleva UNA cosa (una idea, O un contenido,
  O una interaccion), nunca las tres amontonadas. Si una pantalla explica algo Y define varios
  terminos Y pide actuar, pide trocearla.
- CONTENIDO vs EVALUACION separados. El CONTENIDO ensena o ayuda (texto, tabla, antes/despues,
  cronologia, ejemplo resuelto mostrado entero, flashcard de apoyo) y NUNCA evalua. La
  EVALUACION es una comprobacion REAL. Marca como error: una flashcard (o cualquier bloque que
  solo se revela) usada COMO test; y la presencia de un DidactGlossary (esta prohibido: la
  plataforma ya tiene "Curio" para consultar palabras).
- El componente encaja con la NATURALEZA del material? Un procedimiento se ordena; un concepto
  se comprueba con un caso; una comparacion, con antes/despues; hechos/clasificacion, con
  emparejar o clasificar. Materiales de distinta naturaleza no se parecen entre si.
- VARIEDAD de la evaluacion. Si el test es "siempre el mismo tipo" (p. ej. siempre opcion
  unica) o es una flashcard/reveal, pide cambiarlo a una forma real y variada (emparejar,
  clasificar, ordenar, rellenar hueco, opcion unica/multiple, banco de palabras).
- El numero de pantallas es sensato para el material? (Ni trocear una idea simple en cinco
  pantallas, ni comprimir un tema rico en una sola.) NO exijas un numero concreto.

Responde UNICAMENTE con JSON, sin texto alrededor:
{"revise": true|false, "notes": ["nota accionable y breve", ...]}

- "revise": true SOLO si un cambio mejoraria de verdad la pantalla. Si ya esta bien, false
  y notes vacio. No reescribas por costumbre.
- "notes": ordenes concretas y cortas para quien regenere (que cambiar y por que), nunca
  reglas fijas del tipo "debe tener exactamente N". Maximo 4 notas.
- No cambies la mision, la fuente, la evidencia ni el idioma. No inventes hechos.
"""

_EPISODE_REVISE_HEADER = """\
Un critico didactico reviso tu pantalla y pidio mejoras concretas. Vuelve a emitir el
programa COMPLETO aplicando esas notas, sin cambiar la mision, la fuente ni los hechos, y
respetando las reglas del dialecto y del flujo de pantallas de abajo. No expliques nada:
responde solo con el programa (y su clave si lleva QuizItem).
"""


@cache
def episode_ui_revise_system(component_prompt: str | None = None) -> str:
    """Revision system prompt: same episode dialect, plus 'apply the critic's notes'."""

    return _EPISODE_REVISE_HEADER + "\n" + episode_ui_generator_system(component_prompt)


def build_episode_critic_prompt(
    *,
    title: str,
    summary: str,
    domain: str,
    program: str,
    screen_count: int,
    assessment_mode: str,
) -> str:
    """Ask the critic to review the pedagogy of an already-valid episode program."""

    return "\n".join(
        [
            "NODO",
            f"- Titulo: {title}",
            f"- Resumen: {summary}",
            f"- Dominio: {domain or 'sin declarar'}",
            f"- Modo de evaluacion: {assessment_mode}",
            f"- Pantallas actuales (hijos de la raiz): {screen_count}",
            "",
            "PANTALLA GENERADA (dialecto ya validado)",
            program.strip(),
            "",
            "Devuelve solo el JSON con 'revise' y 'notes'.",
        ]
    )


def build_episode_revise_prompt(
    *,
    episode: EpisodeBrief | Mapping[str, Any],
    source_context: str,
    previous: str,
    notes: Sequence[str],
) -> str:
    """Restate the episode contract and hand the critic's notes to the generator."""

    listed = "\n".join(f"- {note}" for note in notes) or "- mejora la pantalla"
    context = build_episode_ui_prompt(episode=episode, source_context=source_context)
    return (
        "CONTRATO AUTORITATIVO DEL EPISODIO\n"
        f"{context}\n\n"
        "NOTAS DEL CRITICO (aplicalas)\n"
        f"{listed}\n\n"
        "PANTALLA ANTERIOR\n"
        f"{previous}\n\n"
        "Emite el programa completo revisado. Conserva la mision y los hechos; aplica las "
        "notas del critico."
    )


@cache
def ui_generator_system(
    component_prompt: str | None = None, *, didact_verification: bool = False
) -> str:
    """``library.prompt()`` (the artefact) plus the answer-key protocol.

    Cached: the artefact is immutable at runtime and this string is hashed on every
    fixture lookup. ``didact_verification`` is part of the cache key so the live
    Didact closer does not share a prompt with the legacy QuizItem path.
    """
    text = (component_prompt or render_prompt()).rstrip("\n") + _UI_GENERATOR_TAIL
    if didact_verification:
        return text + _DIDACT_VERIFICATION_OVERRIDE
    return text


#: The repair header. The MAL/BIEN block is not decoration: a paired counterexample is the
#: cheapest instruction that has ever fixed a syntax habit, and the repair turn is where it
#: pays, because there is exactly one retry (``MAX_UI_RETRIES``).
#:
#: **Which** examples are here is a measurement, not a taste, and the set changed on
#: 2026-07-27. The one that left was "a call split over several lines": that is legal
#: OpenUI Lang — ``lang-core``'s statement splitter ignores a newline inside an open
#: bracket — and this repository only thought otherwise until ``src/render/lines.py``.
#: Spending a counterexample on a rule that does not exist is worse than spending nothing:
#: it teaches the model to reformat a program that was never wrong, on the one turn it has.
#: The two that replaced it are the mistakes the real corpus actually made, both of them
#: about the answer key: dropping it (``higiene-alimentaria``, ``alergenos-hosteleria``)
#: and smuggling it in as a declaration (``atencion-reclamaciones``: ``clave = {...}``).
#:
#: The last paragraph exists because the loop's failure mode is *chasing the wrong bug*.
#: The measured run had the model rewriting quotes that were correct, three attempts in a
#: row, because the parse error blamed a quote for an inline component call. The parser no
#: longer misdiagnoses that (``src/render/backends/openui.py``) and inline nesting is now
#: accepted, so the model is told plainly not to go looking for it.
_UI_REPAIR_HEADER = f"""\
Tu respuesta anterior fue RECHAZADA por el validador de SkillNet. Vuelve a emitir el
programa completo, corregido. No expliques el error, no te disculpes y no comentes nada:
responde solo con el programa (y su clave de respuestas si lleva QuizItem).

Corrige EXACTAMENTE lo que dicen los errores del validador: cada uno nombra la linea y la
causa real. No cambies nada mas: el contenido que no aparece en la lista ya era correcto.

Los fallos de forma que mas se repiten, con su version corregida al lado:

MAL  (argumentos con nombre):  root = Stack(children = [intro], gap = "md")
BIEN (posicionales, en orden): root = Stack([intro], "md")

MAL  (comilla sin escapar dentro del texto): aviso = Callout("info", "Dijo "no" y colgo.")
BIEN (comilla escapada con \\"):              aviso = Callout("info", "Dijo \\"no\\" y colgo.")

MAL  (tilde en el id de un bloque):  conclusión = TextContent("...", "body")
BIEN (id en ASCII, texto con tildes): conclusion = TextContent("Aquí sí van tildes.", "body")

MAL  (la clave como declaracion del programa):  clave = {{"q1": {{"correct": 1}}}}
BIEN (la clave despues del programa, tras la linea {ANSWER_KEY_SENTINEL}):
q1 = QuizItem("q1", "test", "understand", "Enunciado?", ["A", "B"])
{ANSWER_KEY_SENTINEL}
{{"q1": {{"correct": 1, "explanation": "Por que esa y no otra."}}}}

Dos construcciones que SI son validas, por si el error te hace dudar de ellas:
- Anidar un bloque dentro de otro en la misma linea, aunque se prefieren las referencias
  por id: root = Stack([TextContent("Hola.", "lead")], "md")
- Partir una declaracion en varias lineas mientras haya un corchete abierto.
Si los errores del validador no hablan de eso, no lo toques.

Reglas del dialecto y catalogo de bloques: los mismos de abajo, sin excepciones.
"""


@cache
def ui_repair_system(
    component_prompt: str | None = None, *, didact_verification: bool = False
) -> str:
    """The repair system prompt: the same dialect, plus "you were rejected, emit again".

    A separate system prompt rather than an extra user turn, because the model has to be
    told that its previous output is not a starting point to patch but something to
    re-emit whole: the parser is line-oriented and a half-fixed program fails again.
    """
    return (
        _UI_REPAIR_HEADER
        + "\n"
        + ui_generator_system(
            component_prompt, didact_verification=didact_verification
        )
    )


def _normalize_for_grounding(text: str) -> str:
    """Lowercase, strip accents, collapse to spaces — so grounding compares meaning,
    not diacritics or punctuation. `Atención al cliente` → `atencion al cliente`."""
    stripped = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


# Profile tokens this short carry no domain signal (articles, prepositions, "de/la/al"),
# so they must never make a role look grounded on their own.
_PROFILE_STOPWORD_LEN = 4


def _profile_is_grounded(
    *, role_title: str | None, sector: str | None, source_context: str
) -> bool:
    """Does the learner's declared job actually appear in the source material?

    Structural and domain-neutral: it never names a domain. It tokenizes the learner's
    ``role_title``/``sector`` and asks whether any meaningful token occurs in the source
    text. When none does — a shop-assistant profile on a boxing source — the role is
    *not* grounded and must not enter the generative prompt at all, because a role the
    source cannot support is exactly what makes the model invent "un cliente se acerca…"
    in a course that has no clients. With no source text there is nothing to ground
    against, so the role stays out.
    """
    source = _normalize_for_grounding(source_context)
    if not source:
        return False
    source_tokens = set(source.split())
    profile = _normalize_for_grounding(f"{role_title or ''} {sector or ''}")
    tokens = [t for t in profile.split() if len(t) >= _PROFILE_STOPWORD_LEN]
    return any(t in source_tokens for t in tokens)


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
    shape_hints: Sequence[str] = (),
    assessment_hint: str = "",
    screen_scheme: str = "",
    presentation_preference: str = "balanced",
    detail_preference: str = "standard",
    image_preference: str = "when_useful",
    longitudinal_support_level: str = "base",
) -> str:
    """The user prompt for ``genera_ui``.

    ``role_title`` and ``sector`` are the only learner-declared strings that travel
    literally (§3.3, §6.2), and the reason ``role_bucket`` is part of the ``cache_key``.
    They adapt tone and difficulty; they do **not** set the topic. The source and the
    node win over the profile: the role only frames examples when it fits the source's
    subject, and never introduces a role, a client or a workplace scenario the source
    does not support (that was the boxing-course-with-a-shop-assistant contamination).
    ``goal`` and ``accessibility`` do not travel, by design.

    ``shape_hints`` come from :func:`src.agents.runtime.shape.analyze_shape` and are the
    one part of this prompt derived from reading the source rather than from describing
    the learner. They are placed **immediately before** the source and after everything
    else, because that is the last thing the model reads before the material itself, and
    the ordering is the same reason :func:`_closing_line` exists: on an 8B model the
    instruction nearest the content wins.
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
    # NOT ``- Criticidad: critical``. See ``_CRITICALITY_RULES``: the bare enum token on
    # this line was being copied straight into ``Callout("critical", ...)``.
    parts.append(f"- {_criticality_rule(criticality)}")

    # El perfil laboral solo entra en el prompt generativo cuando la propia fuente lo
    # respalda. Si el puesto/sector del lector no aparece en el material, se OMITE por
    # completo: no es "sin declarar", es que no debe influir. Así el modelo no tiene un
    # rol al que arrastrar los ejemplos y no puede inventar "un cliente se acerca…" en un
    # curso que no trata de atención al cliente. La comprobación es estructural (¿está el
    # rol en la fuente?), nunca una lista de dominios.
    role_grounded = bool(role_title) and _profile_is_grounded(
        role_title=role_title, sector=sector, source_context=source_context
    )
    audience_lines = ["", "PARA QUIEN ESCRIBES"]
    if role_grounded:
        audience_lines.append(f"- Puesto: {role_title}")
        if sector:
            audience_lines.append(f"- Sector: {sector}")
    audience_lines.extend(
        [
            f"- Experiencia declarada: {experience_level}",
            f"- Preset de lectura: {preset}",
            "",
            "COMO LO ESCRIBES",
            f"- Presupuesto de longitud: {_density_budget(effective_density)}",
            f"- {_SCAFFOLD_RULES.get(scaffold_band, _SCAFFOLD_RULES['neutral'])}",
            f"- Nivel cognitivo del ejercicio, si lo hay: {target_bloom}",
        ]
    )
    parts.extend(audience_lines)
    if role_grounded:
        # El puesto aparece en la fuente: puede enmarcar los ejemplos, pero sigue
        # ajustando tono y nivel, no el tema. Aun así, nunca inventa hechos ni situaciones
        # que la fuente no respalde.
        role_frame = f"un/una {role_title}" + (f" del sector {sector}" if sector else "")
        parts.append(
            f"- El puesto del lector ({role_frame}) ajusta el tono y el nivel y puede "
            "enmarcar los ejemplos, siempre dentro de lo que dice la fuente; no inventes "
            "hechos ni situaciones que no aparezcan en el material."
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
    history_rule = _HISTORY_SUPPORT_RULES.get(str(longitudinal_support_level))
    if history_rule:
        parts.append(f"- {history_rule}")
    parts.extend(
        f"- {rule}"
        for rule in _preference_rules(
            presentation_preference, detail_preference, image_preference
        )
    )

    shape_section = _shape_section(shape_hints, ui_format)
    if shape_section:
        parts.append("")
        parts.extend(shape_section)

    if assessment_hint.strip() and ui_format in _FORMATS_WITH_QUIZ | {"explanation", "chart"}:
        # Cómo cierra la pantalla, decidido por ``assessment.py`` a partir de la forma del
        # material y del ``node_id``: es lo que reparte la variedad entre nodos en vez de
        # caer siempre en el mismo QuizItem "test". Va junto a la forma del material, lo
        # último antes de la fuente, porque en un modelo pequeño gana la instrucción más
        # cercana al contenido.
        parts.append("")
        parts.append("CÓMO VERIFICAR (elegido por la forma del nodo, no es opcional)")
        parts.append(f"- {assessment_hint.strip()}")

    if screen_scheme.strip():
        # El esquema didáctico es una FORMA SUGERIDA (``screen_scheme.py``), no una
        # plantilla rígida: va lo último antes de la fuente porque en un modelo pequeño gana
        # la instrucción más cercana al contenido, pero el generador puede enriquecerla o
        # divergir si el dominio lo pide, siempre con al menos una interacción genuina.
        parts.append("")
        parts.append(screen_scheme.strip())

    parts.append("")
    if source_context.strip():
        parts.append("FUENTE (es la unica verdad; no anadas datos que no esten aqui)")
        parts.append(clip_source(source_context))
    else:
        parts.append(
            "MATERIAL DE ESTE PUNTO: el titulo, el resumen y el resultado del nodo. "
            "Escribe la pantalla con eso."
        )
    parts.append("")
    parts.append(_closing_line(ui_format))
    return "\n".join(parts)


def build_episode_ui_prompt(
    *,
    episode: EpisodeBrief | Mapping[str, Any],
    source_context: str,
) -> str:
    """Build a formula-free runtime prompt from a public episode contract.

    Only an allowlist of contract fields is rendered.  Internal policy traces, oracle
    references, hidden tests, answer keys and private solutions therefore cannot leak by
    serializing the input wholesale.  ``source_context`` must be the already-authorized
    public source slice for this learner and episode.
    """

    payload = _episode_payload(episode)
    action = _mapping(payload.get("dominant_action"))
    belief = _mapping(payload.get("belief_snapshot"))
    budget = _mapping(payload.get("budget"))
    assessment_mode = str(payload.get("assessment_mode", "none"))

    parts = [
        "MISION DEL EPISODIO",
        f"- Encargo: {_text(action.get('instructions'), 'Completa la accion indicada.')}",
        f"- Accion dominante: {_text(action.get('verb'), 'actuar')}",
        f"- Objetivo de la accion: {_text(action.get('target'), 'objetivo declarado')}",
        "",
        "ACCION OBSERVABLE",
        f"- Entrega: {_text(action.get('submission_kind'), 'sin entrega evaluable')}",
    ]
    constraints = _public_constraints(action.get("constraints"))
    if constraints:
        parts.append(
            "- Limites de la accion: "
            + json.dumps(constraints, ensure_ascii=False, sort_keys=True)
        )

    submission_kind = str(action.get("submission_kind") or "")
    parts.extend(["", "EVIDENCIA"])
    if assessment_mode == "none":
        parts.append(
            "- Este episodio NO exige evidencia evaluada ni certifica dominio: no pidas una "
            "entrega puntuada ni muestres una clave de respuestas."
        )
        parts.append(
            "- Pero la pantalla SIGUE siendo interactiva: incluye al menos un bloque de "
            "practica activa NO evaluativa donde el aprendiz aporta, construida con los hechos "
            "de la fuente (por ejemplo Flashcard de recuerdo activo, DragOrder para ordenar, "
            "DidactTimeline o BeforeAfter). No lo puntues ni emitas un bloque "
            "de solo-revelar. Nunca cierres solo con texto, aviso y resumen."
        )
        if submission_kind == "unscored-support-interaction":
            parts.append(
                "- Es un episodio de APOYO: el aprendiz ensaya la tarea con el material. "
                "Ofrece esa practica sin evaluarla."
            )
    else:
        parts.extend(
            [
                f"- Modo declarado: {assessment_mode}",
                "- La entrega debe permitir al servidor verificar los criterios referenciados.",
                "- No muestres el oraculo, los casos ocultos ni la respuesta correcta.",
            ]
        )

    parts.extend(["", "LIMITES DEL EPISODIO"])
    budget_labels = (
        ("max_content_units", "Unidades de contenido"),
        ("max_interaction_steps", "Pasos de interaccion"),
        ("max_words", "Palabras"),
        ("max_media_seconds", "Segundos de media"),
        ("latency_budget_ms", "Latencia en ms"),
    )
    for key, label in budget_labels:
        value = budget.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            parts.append(f"- {label}: maximo {value}")

    parts.extend(["", "ADAPTACION"])
    adaptation = (
        ("experience_level", "Experiencia declarada"),
        ("mastery", "Dominio estimado"),
        ("confidence", "Confianza estimada"),
        ("hints_used", "Pistas usadas"),
    )
    found_adaptation = False
    for key, label in adaptation:
        value = belief.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            parts.append(f"- {label}: {value}")
            found_adaptation = True
    recent_errors = belief.get("recent_error_kinds")
    if isinstance(recent_errors, (list, tuple)) and all(
        isinstance(value, str) for value in recent_errors
    ):
        if recent_errors:
            parts.append(f"- Errores recientes: {', '.join(recent_errors)}")
            found_adaptation = True
    if not found_adaptation:
        parts.append("- Sin senales personales: usa apoyo neutro y no presupongas preferencias.")

    parts.extend(
        [
            "",
            "VERDAD FUENTE PUBLICA",
            clip_source(source_context)
            if source_context.strip()
            else "No hay hechos publicos adicionales: no inventes ninguno.",
            "",
            (
                "Responde solo con el programa y, unicamente si usas QuizItem, con su "
                f"bloque {ANSWER_KEY_SENTINEL} privado despues."
            ),
        ]
    )
    return "\n".join(parts)


def build_episode_repair_prompt(
    *,
    episode: EpisodeBrief | Mapping[str, Any],
    source_context: str,
    previous: str,
    errors: Sequence[str],
) -> str:
    """Restate the episode contract while repairing grammar or validation failures."""

    listed = "\n".join(f"- {error}" for error in errors) or "- programa invalido"
    context = build_episode_ui_prompt(episode=episode, source_context=source_context)
    return (
        "CONTRATO AUTORITATIVO DEL EPISODIO\n"
        f"{context}\n\n"
        "ERRORES DEL VALIDADOR\n"
        f"{listed}\n\n"
        "RESPUESTA ANTERIOR\n"
        f"{previous}\n\n"
        "Emite el programa completo corregido. Conserva la mision y los hechos; "
        "corrige solo los errores enumerados."
    )


def _episode_payload(episode: EpisodeBrief | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(episode, EpisodeBrief):
        return episode.model_dump(mode="json")
    if isinstance(episode, Mapping):
        return episode
    raise TypeError("episode must be an EpisodeBrief or mapping")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


_PRIVATE_CONSTRAINT_TOKENS = (
    "answer",
    "correct",
    "expected",
    "key",
    "oracle",
    "private",
    "secret",
    "solution",
)


def _public_constraints(value: object) -> dict[str, Any]:
    """Allow harmless action bounds while dropping likely evaluation secrets."""

    if not isinstance(value, Mapping):
        return {}
    public: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        lowered = key.lower()
        if not key or any(token in lowered for token in _PRIVATE_CONSTRAINT_TOKENS):
            continue
        if isinstance(raw_value, (str, int, float, bool)) or raw_value is None:
            public[key] = raw_value
        elif isinstance(raw_value, (list, tuple)) and all(
            isinstance(item, (str, int, float, bool)) or item is None
            for item in raw_value
        ):
            public[key] = list(raw_value)
    return public


#: The formats whose screen carries a ``QuizItem``, and therefore an answer key.
_FORMATS_WITH_QUIZ: frozenset[str] = frozenset({"exercise", "mixed"})


def _shape_section(shape_hints: Sequence[str], ui_format: str) -> list[str]:
    """The ``LA FORMA DEL MATERIAL`` block, or ``[]`` when the source had no structure.

    Shared by the first turn and the repair turn: the material does not change between
    them, and the repair is the turn where "those 14 items are one Table" matters most.

    The closing line about the lead slot is not decoration. Measured end to end on the
    real ``Los catorce alergenos obligatorios`` node the first time these hints ran: the
    model obeyed the hint, opened the screen with the ``Table``, and was refused **twice**
    for contract rule 7 — *"requires the first child of root to be a TextContent with
    variant='lead' or a Callout. Got Table"* — and fell back to the seed lesson. The hints
    sit last in the prompt precisely because the nearest instruction wins on an 8B model,
    and that is exactly how they out-shouted a rule they were never meant to touch. Rule 7
    is stated in the system prompt (``SkillNet 8``); it has to be restated *here*, next to
    the instruction that competes with it, or the two keep fighting on every render.
    """
    hints = [str(hint).strip() for hint in shape_hints if str(hint).strip()]
    if not hints:
        return []
    lines = [
        "LA FORMA DEL MATERIAL (leido de la fuente, no es una preferencia de estilo)"
    ]
    lines.extend(f"- {hint}" for hint in hints)
    if ui_format in FORMATS_REQUIRING_LEAD:
        lines.append(
            "- El PRIMER bloque de la pantalla sigue siendo la linea de entrada "
            '(TextContent con variant "lead", o un Callout). El bloque de la lista va '
            "DESPUES de esa linea, nunca el primero."
        )
    return lines


def _closing_line(ui_format: str) -> str:
    """The last line of the user prompt, and it may not contradict the system prompt.

    It said ``"Responde solo con el programa."`` for every format until 2026-07-27, which
    is the opposite of what the answer-key protocol at the end of the system prompt asks
    for. A model reconciling the two has three ways out and the corpus measured all three
    on real Groq: emit the key and be right, drop the key (``higiene-alimentaria``,
    ``alergenos-hosteleria`` — both then repaired, at the cost of the whole retry), or
    keep "solo el programa" literally and smuggle the key in as a declaration
    (``atencion-reclamaciones`` r2: ``clave = {"q1": {...}}``, which the gate refuses for
    the braces and which no repair message can explain, because the model was obeying the
    last instruction it read).

    So the last instruction it reads now says the same thing as the first.
    """
    if ui_format not in _FORMATS_WITH_QUIZ:
        return "Responde solo con el programa."
    return (
        "Responde con el programa y, si lleva algun QuizItem, con su bloque "
        f"{ANSWER_KEY_SENTINEL} justo despues. Nada mas."
    )


def build_repair_prompt(
    *,
    previous: str,
    errors: Sequence[str],
    ui_format: str = "explanation",
    shape_hints: Sequence[str] = (),
    screen_scheme: str = "",
) -> str:
    """The user prompt for the single repair attempt.

    The validator's messages travel verbatim: they name the line, the component and the
    rule, which is exactly what an 8B model needs to fix an escaping mistake instead of
    rewriting the lesson.

    The closing line carries the same correction as :func:`_closing_line`, and for the
    same measured reason: "Solo el programa." was the last instruction on the repair turn
    too, including on the turn whose *only* complaint was a missing answer key. Telling a
    model to fix a missing key and then telling it to send only the program is asking it
    to fail twice.

    ``shape_hints`` are repeated here rather than assumed remembered. The single most
    expensive rejection measured on real Groq is rule 4 with a large count —
    ``alergenos-hosteleria`` came back with 19 components and ``atencion-reclamaciones``
    with 23 declarations, both of them a list written as one block per item. "You have too
    many blocks" tells the model to delete content; "those N items are one Table" tells it
    what to do instead, and it is the only message that ends that loop in one attempt.
    """
    listed = "\n".join(f"- {error}" for error in errors) or "- programa invalido"
    section = _shape_section(shape_hints, ui_format)
    reminder = "\n".join(section) + "\n\n" if section else ""
    scheme = screen_scheme.strip()
    if scheme:
        reminder = reminder + scheme + "\n\n"
    return (
        f"FORMATO QUE DEBES PRODUCIR: {ui_format}\n\n"
        "ERRORES DEL VALIDADOR:\n"
        f"{listed}\n\n"
        f"{reminder}"
        "TU RESPUESTA ANTERIOR:\n"
        f"{previous}\n\n"
        f"Vuelve a emitir el programa completo y corregido. {_closing_line(ui_format)}"
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
    "EPISODE_CRITIC_SYSTEM",
    "EPISODE_PROMPT_VERSION",
    "FORMAT_DECIDER_SYSTEM",
    "MAX_UI_RETRIES",
    "PROMPT_VERSION",
    "SOURCE_CONTEXT_MAX_CHARS",
    "UI_MAX_TOKENS",
    "UI_TEMPERATURE",
    "UI_USE_CASE",
    "build_format_prompt",
    "build_episode_critic_prompt",
    "build_episode_repair_prompt",
    "build_episode_revise_prompt",
    "build_episode_ui_prompt",
    "build_repair_prompt",
    "build_ui_prompt",
    "clip_source",
    "episode_ui_generator_system",
    "episode_ui_repair_system",
    "episode_ui_revise_system",
    "signal_actions_for_node",
    "ui_generator_system",
    "ui_max_tokens",
    "ui_repair_system",
]
