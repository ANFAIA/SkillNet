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

from typing import Literal

from src.render.prompt import render_prompt

#: The three rungs of the ladder, best first. Persisted in ``chat_messages.metadata`` and
#: sent to the browser as a ``grounding`` SSE event, so the bubble can say where it came
#: from without the model having to be trusted to say it.
Grounding = Literal["chunks", "document", "general"]

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


ADMIN_PERSONA = """\
Eres el asistente del administrador de SkillNet, la plataforma de formacion interna de una
pequena empresa espanola. Hablas con la persona que gestiona los cursos, los documentos y
los empleados.

Como respondes siempre:
- En el idioma de la pregunta. Por defecto, espanol.
- Conciso y operativo: que hacer, donde, en que orden.
- En cuanto haya mas de dos pasos, los enumeras.

Lo que no haces nunca:
- No te inventas cifras, plazos ni contenido de documentos que no tengas delante.
- No contestas "no tengo informacion" y te callas: dices que no consta y ofreces lo que
  si puedes (criterio general, o que documento haria falta subir)."""


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

_ADMIN_GROUNDING_BLOCKS: dict[str, str] = {
    "chunks": """\
Tienes en el contexto fragmentos recuperados de la documentacion de la organizacion.
Apoyate en ellos y cita con [Fuente N] lo que salga de ahi.""",
    "document": """\
Tienes en el contexto el texto COMPLETO de documentos de la organizacion. Apoyate en el y
cita con [Fuente N], que aqui identifica al documento entero.""",
    "general": """\
No hay documentacion de la organizacion que responda a esto. Responde igualmente con
conocimiento general o con lo que sabes de como funciona la plataforma, y di en la primera
linea que no sale de la documentacion subida. No escribas [Fuente N].""",
}


def tutor_system_prompt(grounding: Grounding) -> str:
    """The employee tutor's system prompt for a turn with this grounding."""
    return f"{TUTOR_PERSONA}\n\n{_GROUNDING_BLOCKS[grounding]}"


def admin_system_prompt(grounding: Grounding) -> str:
    """The admin assistant's system prompt for a turn with this grounding."""
    return f"{ADMIN_PERSONA}\n\n{_ADMIN_GROUNDING_BLOCKS[grounding]}"


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
    """The generated artefact plus the chat overrides. Same catalogue as a node render."""
    return render_prompt().rstrip() + "\n" + CHAT_UI_RULES


def build_chat_ui_prompt(question: str, answer: str) -> str:
    """The layout turn: the learner's question and the answer that was just streamed."""
    return (
        f"Pregunta del empleado:\n{question}\n\n"
        f"Respuesta que el tutor acaba de dar:\n{answer}\n\n"
        f"Maqueta esa respuesta, sin anadir nada. Si no gana nada maquetada, "
        f"responde {NO_UI_SENTINEL}."
    )


__all__ = [
    "ADMIN_PERSONA",
    "CHAT_UI_RULES",
    "NO_UI_SENTINEL",
    "TUTOR_PERSONA",
    "TUTOR_PROMPT_VERSION",
    "Grounding",
    "admin_system_prompt",
    "build_chat_ui_prompt",
    "build_user_turn",
    "chat_ui_system",
    "tutor_system_prompt",
]
