"""The admin assistant's prompts: who it is, and the two things it is given to answer with.

Split out of ``src/llm/prompts/tutor.py`` on 2026-07-28, because the admin assistant
stopped being a second skin on the tutor that day. The tutor answers from *documents*; the
admin assistant answers from documents **and** from the platform's own data
(``src/services/org_snapshot.py``), and the rules that make the second safe have nothing
to do with the first. ``tutor.py`` re-exports ``ADMIN_PERSONA`` and ``admin_system_prompt``
so nothing that imported them from there had to move.

The rule everything else here serves: **the assistant may not state a figure it was not
given.** A wrong number about a named person's training record is worse than "no lo se" —
it is a record an employer might act on. So the data block is exhaustive by construction
(every count is pre-computed server-side; the model never adds anything up), and the
prompt says three times, in three different shapes, that the block is the only source of
names and numbers.
"""

from __future__ import annotations

from src.llm.prompts.grounding import Grounding

#: Bumped when anything here changes in a way that changes an answer. Persisted on every
#: admin message, so "which assistant wrote this" is answerable months later — which
#: matters more here than for the tutor, because these answers name people.
ADMIN_PROMPT_VERSION = "admin/2"

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


#: Appended to the persona whenever a snapshot travels with the turn. The tone rule
#: ("nombres y numeros, no consejos") is the one that fixes the reported defect: asked
#: "como van mis empleados" with the data in front of it, a small model will still write
#: four bullets of management advice unless it is told, in imperative, not to.
ADMIN_DATA_BLOCK = """\
Tienes en el contexto un bloque "DATOS DE LA PLATAFORMA": el estado real de esta
organizacion, leido de la base de datos en este mismo momento. Es informacion de
formacion que la empresa tiene derecho a ver sobre su plantilla.

Como usarlo:
- Si la pregunta es sobre empleados, cursos, progreso, plazos o competencias, responde
  CON ESOS DATOS: nombres propios y numeros concretos. No des consejos de gestion
  genericos ("habla con el encargado", "revisa las evaluaciones") cuando la respuesta
  esta en el bloque; eso es no responder.
- Empieza SIEMPRE por el titular: la cifra o el nombre que contesta la pregunta, en una
  frase. El bloque "RESUMEN" ya trae esas cifras contadas; usalas tal cual. Solo despues
  del titular viene el desglose persona a persona, y solo si aporta.
- Cierra, como mucho, con UNA accion concreta que nombre a una persona o a un curso del
  bloque, y que no invente plazos ni fechas que no aparezcan ahi ("escribe a Aitana, que
  no ha abierto ninguno de sus tres cursos"). Si no tienes una asi, no cierres con nada:
  "revisa el estado de cada empleado" no es una accion, es relleno.

Los limites, que no se negocian:
- Toda cifra que escribas tiene que estar literalmente en el bloque. No sumes, no
  promedies, no estimes y no completes lo que falte: si un dato no esta, di que no
  consta. Vale mas "no lo se" que un numero inventado sobre la formacion de una persona.
- No hables de personas que no aparezcan en el bloque, ni les atribuyas cursos, notas o
  competencias que no esten en su linea.
- El bloque NO dice como aprende cada persona (su perfil de aprendizaje, sus preferencias
  de formato ni sus necesidades de accesibilidad): eso es privado de cada empleado y no
  lo tienes. Si te lo preguntan, di que la plataforma no se lo muestra al administrador.
- No cites [Fuente N] para nada que salga de este bloque: no es un documento."""


_GROUNDING_BLOCKS: dict[str, str] = {
    "chunks": """\
Ademas tienes fragmentos recuperados de la documentacion de la organizacion.
Apoyate en ellos y cita con [Fuente N] lo que salga de ahi.""",
    "document": """\
Ademas tienes el texto COMPLETO de documentos de la organizacion. Apoyate en el y
cita con [Fuente N], que aqui identifica al documento entero.""",
    "general": """\
No hay documentacion de la organizacion que responda a esto. Responde igualmente con
conocimiento general o con lo que sabes de como funciona la plataforma, y di en la primera
linea que no sale de la documentacion subida. No escribas [Fuente N].""",
}

#: Without a snapshot the grounding blocks are the whole story, so they must not open with
#: "Ademas". Same three texts, minus the connector.
_STANDALONE_GROUNDING_BLOCKS: dict[str, str] = {
    "chunks": """\
Tienes en el contexto fragmentos recuperados de la documentacion de la organizacion.
Apoyate en ellos y cita con [Fuente N] lo que salga de ahi.""",
    "document": """\
Tienes en el contexto el texto COMPLETO de documentos de la organizacion. Apoyate en el y
cita con [Fuente N], que aqui identifica al documento entero.""",
    "general": _GROUNDING_BLOCKS["general"],
}

_CONTEXT_HEADERS: dict[str, str] = {
    "chunks": "Fragmentos de la documentacion de la organizacion:",
    "document": "Documentos completos de la organizacion:",
}


def admin_system_prompt(grounding: Grounding, *, org_data: bool = False) -> str:
    """The admin assistant's system prompt for a turn with this grounding.

    ``org_data`` defaults to ``False`` so every pre-existing caller — and the assertion in
    ``tests/test_tutor_grounding.py`` that no prompt can produce the old refusal — keeps
    reading the prompt it read before.
    """
    if not org_data:
        return f"{ADMIN_PERSONA}\n\n{_STANDALONE_GROUNDING_BLOCKS[grounding]}"
    return f"{ADMIN_PERSONA}\n\n{ADMIN_DATA_BLOCK}\n\n{_GROUNDING_BLOCKS[grounding]}"


def build_admin_turn(
    grounding: Grounding, context_block: str, snapshot_block: str, question: str
) -> str:
    """The final user message: the data, the documents (if any), and the question.

    The snapshot goes **first** and the question **last**. Measured against small models,
    a question buried above 1-2 kB of tabular data gets answered from the model's habits
    rather than from the table; the last thing in the turn is the thing it answers.
    """
    sections: list[str] = []
    if snapshot_block:
        sections.append(snapshot_block)
    if grounding != "general" and context_block:
        sections.append(f"{_CONTEXT_HEADERS[grounding]}\n\n{context_block}")
    if not sections:
        return (
            f"Pregunta: {question}\n\n"
            "No hay material de la organizacion para esta pregunta. Respondela igual, "
            "con criterio general, y di en la primera linea que no sale de la "
            "documentacion subida."
        )
    sections.append(f"Pregunta: {question}")
    return "\n\n---\n\n".join(sections)


__all__ = [
    "ADMIN_DATA_BLOCK",
    "ADMIN_PERSONA",
    "ADMIN_PROMPT_VERSION",
    "admin_system_prompt",
    "build_admin_turn",
]
