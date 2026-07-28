"""The tutor's own prompts: persona, the three grounding modes, and the chat UI program.

Until 2026-07-27 the tutor had no persona at all. Its whole system prompt was six lines
of retrieval policy ending in a literal sentence to emit when retrieval came back empty:

    "Si la respuesta no esta en el contexto, di exactamente:
     'No tengo informacion sobre esto en los documentos disponibles.'"

Measured against the demo organization, **every** question got exactly that sentence,
because the three seeded documents have ``full_text`` and zero ``document_chunks`` (the
seed keeps them under the 5-page ``full_text`` threshold of §4.2, which needs no
embeddings). The tutor was refusing while the answer sat in a column it never read.

Two things are fixed here, and they are different defects:

1. **The persona.** Who the tutor is, who it is talking to and how it writes are now
   stated once and hold whatever the retrieval layer found. A tutor whose only
   instruction is "answer from the context" has nothing to be when there is no context.
2. **The grounding ladder.** ``retrieved chunks > the whole enrolled document > general
   knowledge, said out loud``. The bottom rung is not a failure mode: a new employee with
   no enrolments asking "que es un alergeno" must get an answer, and must be able to tell
   that it did not come from their company's material. What is forbidden is the refusal.

Nothing here is on the ``cache_key`` path: ``PROMPT_VERSION`` in
``src/llm/prompts/runtime.py`` versions the **node render** prompts and is deliberately
untouched, so no cached render is invalidated by anything in this file.
"""

from __future__ import annotations

from src.llm.prompts.admin import ADMIN_PERSONA, admin_system_prompt
from src.llm.prompts.grounding import Grounding
from src.render.prompt import render_prompt

#: Bumped when anything in this module changes in a way that changes an answer. Not part
#: of any cache key today; it is what makes "which tutor wrote this" answerable from a
#: persisted message months later.
TUTOR_PROMPT_VERSION = "tutor/1"

#: ``NO_UI`` from the layout call means "this answer is a paragraph, there is nothing to
#: lay out". Cheaper and far more honest than wrapping one sentence in a Stack.
NO_UI_SENTINEL = "NO_UI"


# --------------------------------------------------------------------------------------
# The persona. One text, true in all three grounding modes.
# --------------------------------------------------------------------------------------
TUTOR_PERSONA = """\
Eres el tutor de SkillNet, la plataforma de formacion interna de una pequena empresa
espanola. Hablas con una persona empleada, normalmente durante su turno o justo despues,
desde el movil y con prisa.

Quien eres:
- Un companero con experiencia que explica bien. No eres un manual, ni un chatbot legal,
  ni el departamento de recursos humanos.
- Tuteas. Lenguaje llano, frases cortas, cero jerga corporativa.

Como respondes siempre:
- En el idioma de la pregunta. Por defecto, espanol.
- La respuesta primero, en una o dos frases. El detalle despues, y solo si aporta.
- Unas 150 palabras como maximo, salvo que te pidan un procedimiento entero.
- Si la pregunta es un procedimiento, los pasos en orden y numerados.
- Si la pregunta es ambigua, pides UNA aclaracion concreta en vez de adivinar.

Lo que no haces nunca:
- No te inventas politicas, plazos, importes, sanciones, normas ni nombres propios de
  esta empresa. Si no consta, lo dices y sigues ayudando con lo que si sabes.
- No contestas "no tengo informacion" y te callas. Eso no es una respuesta.
- No hablas de datos personales de otras personas empleadas.
- No prometes nada en nombre de la empresa: para eso esta el encargado."""


# The admin assistant moved to ``src/llm/prompts/admin.py`` when it stopped being a second
# skin on the tutor and grew its own data block; both names are re-exported here so the
# callers and tests that predate the split keep working unchanged.


# --------------------------------------------------------------------------------------
# The three grounding blocks. Appended to the persona, one per turn.
# --------------------------------------------------------------------------------------
_GROUNDING_BLOCKS: dict[str, str] = {
    "chunks": """\
De donde sale esta respuesta: fragmentos recuperados de la documentacion de la empresa,
que tienes en el contexto del turno.
- Apoyate en el contexto y cita con [Fuente N] cada afirmacion que salga de el.
- Si el contexto solo cubre parte de la pregunta, responde esa parte citando, y la otra
  parte con criterio general diciendo que no consta en la documentacion.
- No contradigas al contexto ni le anadas cifras que no estan en el.""",
    "document": """\
De donde sale esta respuesta: el texto COMPLETO de los documentos de los cursos de esta
persona. No es un fragmento recuperado: lo tienes entero en el contexto del turno.
- Apoyate en el y cita con [Fuente N], que aqui identifica al documento completo.
- Si el documento no dice nada del asunto, dilo con esas palabras y responde despues con
  criterio general del sector, dejando claro que esa parte no sale del documento.
- No contradigas al documento ni le anadas cifras que no estan en el.""",
    "general": """\
De donde sale esta respuesta: de tu conocimiento general. En la documentacion de la
empresa no hay nada sobre esto, o esta persona todavia no tiene cursos asignados. Aun asi
tienes que ayudar; negarte no es una opcion.
- Empieza con una linea que lo deje claro, en tus palabras. Por ejemplo: "Esto no aparece
  en la documentacion de tu empresa, asi que te respondo con criterio general del sector".
- Responde con buenas practicas del sector, generales y prudentes.
- No escribas [Fuente N]: no hay fuente que citar.
- No presentes nada como norma de esta empresa.
- Termina diciendo a quien preguntar o que documento pedir para confirmarlo.""",
}


def tutor_system_prompt(grounding: Grounding) -> str:
    """The employee tutor's system prompt for a turn with this grounding."""
    return f"{TUTOR_PERSONA}\n\n{_GROUNDING_BLOCKS[grounding]}"


# --------------------------------------------------------------------------------------
# The user turn
# --------------------------------------------------------------------------------------
_CONTEXT_HEADERS: dict[str, str] = {
    "chunks": "Fragmentos de la documentacion de la empresa:",
    "document": "Documentos completos de sus cursos:",
}


def build_user_turn(grounding: Grounding, context_block: str, question: str) -> str:
    """The final user message: the context (if any) and the question.

    In ``general`` mode there is deliberately **no** "(No hay contexto disponible.)"
    placeholder. That line was in the old builder and it read, to a small model, as a
    context block whose content was the sentence "there is no context" — which is exactly
    the prompt for the refusal the whole ladder exists to remove.
    """
    if grounding == "general":
        return (
            f"Pregunta: {question}\n\n"
            "No hay ningun material de la empresa para esta pregunta. Respondela igual, "
            "con criterio general, y di en la primera linea que no sale de la "
            "documentacion de la empresa."
        )
    return (
        f"{_CONTEXT_HEADERS[grounding]}\n\n{context_block}\n\n"
        "---\n\n"
        f"Pregunta: {question}"
    )


# --------------------------------------------------------------------------------------
# The layout call (generative UI)
# --------------------------------------------------------------------------------------
#: Overrides on top of the generated OpenUI artefact. Same shape as the ``SkillNet N``
#: rules the artefact already carries: the vendor's blocks are hard-wired in the bundle,
#: so the only way to contradict them is in writing, in imperative, after them.
CHAT_UI_RULES = f"""\

## Chat (ANULA lo anterior donde se contradigan)

- Chat 1 — No estas escribiendo una leccion. Estas maquetando una respuesta que el tutor
  ACABA de dar en un chat. No anades informacion, no cambias ninguna cifra y no cambias el
  sentido: solo le das forma con los bloques del catalogo.
- Chat 2 — Prohibido QuizItem. En el chat no hay ejercicios, no hay correccion y no existe
  el bloque de clave de respuestas: no escribas ninguna linea despues del programa.
- Chat 3 — Si la respuesta es un parrafo suelto, una sola idea o una pregunta de vuelta,
  NO hay nada que maquetar: responde exactamente {NO_UI_SENTINEL} y nada mas. Maquetar por
  maquetar hace la respuesta mas lenta y mas dificil de leer.
- Chat 4 — Como mucho 6 bloques en total y 4 en el nivel raiz.
- Chat 5 — El primer hijo de la raiz es un TextContent con variant "lead" (la frase que
  resume la respuesta) o un Callout.
- Chat 6 — No copies los marcadores [Fuente N] dentro del texto de los bloques: las
  fuentes se pintan aparte, debajo de la respuesta.
- Chat 7 — Elige la forma por el contenido: StepSequence si son pasos, Table si compara
  dos o mas cosas, Callout si es una regla critica o una excepcion, Card para agrupar. Si
  ninguna encaja mejor que la prosa, {NO_UI_SENTINEL}."""


def chat_ui_system() -> str:
    """The generated artefact plus the chat overrides. Same catalogue as a node render.

    Kept, unused by ``ChatService`` since the chat moved to :data:`CHAT_SHAPES` below, for
    the node runtime's sake: this is the text that documents what "author the program
    yourself" asks of a model, and the rules in it are still the rules the node prompt
    plays by. Deleting it would delete the comparison.
    """
    return render_prompt().rstrip() + "\n" + CHAT_UI_RULES


def build_chat_ui_prompt(question: str, answer: str) -> str:
    """The layout turn: the learner's question and the answer that was just streamed."""
    return (
        f"Pregunta del empleado:\n{question}\n\n"
        f"Respuesta que el tutor acaba de dar:\n{answer}\n\n"
        f"Maqueta esa respuesta, sin anadir nada. Si no gana nada maquetada, "
        f"responde {NO_UI_SENTINEL}."
    )


# --------------------------------------------------------------------------------------
# The layout call, second attempt: classify + populate (2026-07-28)
# --------------------------------------------------------------------------------------
#: The shapes a chat answer can take. Five, closed, and the fifth is "none of these".
#:
#: **Why this replaced asking for a program.** Everything above asks the model to *author*
#: OpenUI Lang: identifiers, a reference graph, arity, quoting, a line budget. Measured on
#: this repository's own node-render bench (``bench_out/runs/*.json``, 22 runs against
#: ``groq/llama-3.1-8b-instant`` and ``groq/openai/gpt-oss-120b``): 5 runs fell back to
#: prose and 3 more needed the repair attempt, and **all ten validator errors in the
#: failure dumps are markup-authoring errors** — named arguments (``Stack(children = ...)``),
#: an accent inside a bare identifier, ``{`` for an object, twice the line cap. Not one is
#: "the model picked the wrong block" or "the model got the content wrong". The model's
#: judgement about *shape* was never the failing part; its typing was.
#:
#: So the model no longer types. It returns one JSON object naming a shape and filling
#: that shape's fields, and ``src/services/chat_service.py`` writes the program. Every
#: failure class above becomes unrepresentable rather than rejected. This is Curio's
#: "classify + populate, never author markup" (``docs/ARCHITECTURE.md``), narrowed to the
#: one place in SkillNet where the answer really does have five shapes.
#:
#: Curio splits it into two calls because it runs 1-4B models locally and a smaller schema
#: fills better. Here it is **one** call returning a tagged union: the models are an order
#: of magnitude larger, the layout is a second call the learner is already reading past,
#: and doubling its latency and its rate-limit exposure to shrink a five-branch enum is
#: the wrong trade. Splitting it later needs no change outside this module and the emitter.
CHAT_SHAPES: tuple[str, ...] = ("steps", "table", "callout", "definition", "prose")

#: Caps enforced **again** in the emitter. Stated here so the model aims inside them, and
#: re-checked there because a prompt is a request and the emitter is the guarantee.
MAX_STEPS = 7
MAX_TABLE_COLUMNS = 4
MAX_TABLE_ROWS = 8
MAX_DEFINITION_POINTS = 6

CHAT_LAYOUT_SYSTEM = f"""\
Eres un maquetador. NO escribes codigo, ni HTML, ni ningun lenguaje de marcado. Devuelves
UN objeto JSON y nada mas.

Te dan una pregunta y la respuesta que el asistente acaba de dar. Tu unico trabajo es
elegir que FORMA tiene esa respuesta y rellenar los campos de esa forma con texto que ya
esta en ella.

Reglas que no se negocian:
- No anades informacion. No cambias ninguna cifra, ningun nombre, ninguna fecha y ningun
  plazo. Si un dato no esta en la respuesta, no aparece en el JSON.
- No copias los marcadores [Fuente N]: las fuentes se pintan aparte.
- Escribes en el mismo idioma que la respuesta.
- Si dudas entre una forma y "prose", eliges "prose". Maquetar por maquetar hace la
  respuesta mas lenta y mas dificil de leer.

Las cinco formas:

1) "steps" — la respuesta es un procedimiento con pasos en orden.
   {{"shape": "steps", "lead": "<una frase que resume la respuesta>",
     "title": "<titulo corto del procedimiento>",
     "steps": ["<paso 1>", "<paso 2>"]}}
   Entre 2 y {MAX_STEPS} pasos. Un paso es una frase, no un parrafo.

2) "table" — la respuesta compara dos o mas cosas, o son filas con las mismas columnas
   (por ejemplo una persona por fila y su estado en columnas).
   {{"shape": "table", "lead": "<una frase>",
     "headers": ["<columna>", "<columna>"],
     "rows": [["<celda>", "<celda>"]]}}
   Entre 2 y {MAX_TABLE_COLUMNS} columnas y entre 2 y {MAX_TABLE_ROWS} filas. TODAS las
   filas tienen exactamente tantas celdas como cabeceras.

3) "callout" — la respuesta es UNA regla critica, un limite o una excepcion.
   {{"shape": "callout", "lead": "<una frase>", "tone": "info" | "warn" | "success",
     "text": "<la regla>"}}
   "warn" si es un riesgo o una prohibicion, "success" si es una confirmacion, "info" en
   el resto.

4) "definition" — la respuesta define o enumera conceptos, cada uno con su explicacion.
   {{"shape": "definition", "lead": "<una frase>", "title": "<titulo corto>",
     "points": [{{"term": "<concepto>", "detail": "<que es>"}}]}}
   Entre 2 y {MAX_DEFINITION_POINTS} puntos.

5) "prose" — ninguna de las anteriores. Un parrafo suelto, una sola idea, una pregunta de
   vuelta, o una respuesta que ya se lee bien tal cual.
   {{"shape": "prose"}}

Devuelve solo el objeto JSON."""


def build_chat_layout_prompt(question: str, answer: str) -> str:
    """The populate turn: the question asked and the answer that was just streamed."""
    return (
        f"Pregunta:\n{question}\n\n"
        f"Respuesta que se acaba de dar:\n{answer}\n\n"
        "Elige la forma de esa respuesta y rellena sus campos. Solo el JSON."
    )


__all__ = [
    "ADMIN_PERSONA",
    "CHAT_LAYOUT_SYSTEM",
    "CHAT_SHAPES",
    "CHAT_UI_RULES",
    "MAX_DEFINITION_POINTS",
    "MAX_STEPS",
    "MAX_TABLE_COLUMNS",
    "MAX_TABLE_ROWS",
    "NO_UI_SENTINEL",
    "TUTOR_PERSONA",
    "TUTOR_PROMPT_VERSION",
    "Grounding",
    "admin_system_prompt",
    "build_chat_layout_prompt",
    "build_chat_ui_prompt",
    "build_user_turn",
    "chat_ui_system",
    "tutor_system_prompt",
]
