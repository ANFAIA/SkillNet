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
from src.render.spec import FORMATS_REQUIRING_LEAD

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
#: ``runtime/29`` (2026-08-13): one idea per screen; teach with a case or
#: graphic; practice is a second workplace situation, not the same sentence.
PROMPT_VERSION = "runtime/30"

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
    4: "4-5 bloques. Puedes desarrollar mas dentro de cada bloque, no anadir mas bloques.",
    5: (
        "5 bloques como maximo, pero desarrollados: ejemplos y matices DENTRO de esos "
        "cinco. Nunca un sexto."
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

REGLA: Cada pantalla combina AL MENOS un bloque de Contenido + un bloque de Interaccion
o Evaluacion. La pantalla SIEMPRE acaba con QuizItem, DragOrder o BeforeAfter: nunca
terminar solo con texto. Si el formato es "mixed" o "exercise", el bloque final es
OBLIGATORIAMENTE un QuizItem o un DragOrder.

## SkillNet: que bloque para que contenido

Elige el bloque por lo que ES el material. Un contenido en el bloque equivocado es una
pantalla mal hecha aunque el programa sea valido.

- LISTA de cosas (los N alergenos, los contenedores, los EPI por tarea) -> UN Table, una
  fila por cosa; segunda columna solo si la fuente da un dato de cada una.
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
- MULTIPLES ASPECTOS de un tema (tipos de residuos, categorias de EPI, fases de un
  proceso) -> una Table con una fila por aspecto, todos visibles a la vez.

## SkillNet: estructura pedagogica de la pantalla

El user prompt trae ESQUEMA DE ESTA PANTALLA cuando el nodo ya tiene un plan.
Rellena esos huecos en ese orden. El concepto es el material (filas, pasos,
barras), no un parrafo que define el titulo.

Si el esquema pide QuizItem, tiene estas formas:
- "test": 4 opciones sobre un caso concreto.
- "true_false": una afirmacion sobre un caso. options = [].
- "fill_blank": una frase con UN hueco ____.
- order_steps / DragOrder: ordenar los pasos.

MAXIMO 4 bloques (lead + concepto + practica + a veces un Callout).

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

_UI_GENERATOR_TAIL = f"""
{_BLOCK_CHOICE}
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

La practica de esta pantalla es Didact. Usa uno de:
Flashcard, HintReveal, DidactGlossary, DidactTimeline, DidactWorkedExample
o DidactActivity(activity_id, component_id).
Si el servidor ya preparo una Actividad Didact, esa es la practica de la pantalla.
La correccion vive en el servidor: el programa termina con el bloque Didact.

## SkillNet: un caso, luego otro

El ESQUEMA DE ESTA PANTALLA ya nombra los tres huecos. Rellenalos.
La practica Didact es un segundo encargo del puesto, distinto del lead
y distinto del concepto.

Un Card solo cuando agrupa varios datos distintos que caben juntos.
"""


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
    literally (§3.3, §6.2): they are what the examples get framed around, and the reason
    ``role_bucket`` is part of the ``cache_key``. ``goal`` and ``accessibility`` do not
    travel, by design.

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
        # El esquema didáctico ya está decidido (``screen_scheme.py``). Va lo último
        # antes de la fuente: en un modelo pequeño gana la instrucción más cercana
        # al contenido. El generador rellena estos huecos; no inventa la forma.
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
