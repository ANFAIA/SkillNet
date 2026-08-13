"""The prompt that writes a source document from an idea ("desde cero").

This is the only place in the product where the model writes the *source* rather than
teaching from one, so it is also the only place where a hallucination cannot be caught
by comparing the output against a document. Three consequences shape the prompt:

1. **It must read like reference material, not like a lesson.** The generation pipeline
   downstream extracts themes, designs a structure and writes modules *from* this text.
   If the text is already a course, the pipeline summarises a summary and the result is
   thin. So: sections, procedures, concrete facts — the manual, not the class.
2. **It must not invent an organisation.** No company name, no "en nuestra empresa", no
   internal procedure attributed to somebody. The creator's own material is what says
   how *their* company does things, and this text is explicitly not that.
3. **It must be honest about regulation.** A model asked for "manipulación de alimentos"
   will happily invent article numbers. The prompt asks for the substance of a rule and
   forbids citing a specific article, decree or date unless the creator supplied it —
   a wrong legal citation in compliance training is worse than none.

The output is Markdown with `##` headings on purpose: `chunk_sections` keys chunks on
headings, and the v2 schema designer chooses node sources from the heading list, so the
headings here become the spine of the course.
"""

from __future__ import annotations

SOURCE_WRITER_SYSTEM = """Eres redactor de material de referencia para formacion en el puesto de trabajo, en una pyme espanola.

Escribes el DOCUMENTO FUENTE del que despues otro sistema sacara un curso. No escribes el curso.

Como tiene que ser el texto:
- Material de referencia: secciones, procedimientos, datos concretos, casos limite. Como un manual interno bien escrito, no como una leccion ni como un articulo de blog.
- En espanol claro y directo, dirigido a alguien que hace ese trabajo, no a un experto.
- Estructurado en secciones con encabezados Markdown de nivel 2 (##). Entre 4 y 8 secciones.
- Cada seccion con contenido real y util: pasos, listas de comprobacion, cifras, que hacer cuando algo sale mal.

Lo que NO puedes hacer:
- No inventes el nombre de ninguna empresa, ni digas "en nuestra empresa" ni "en [Empresa]". Este texto no es la politica interna de nadie.
- No cites articulos, reales decretos, normas UNE ni fechas concretas de legislacion salvo que te los den. Puedes explicar el fondo de una obligacion legal sin inventarte su referencia.
- No inventes datos de contacto, nombres de personas ni codigos internos.
- Nada de introducciones sobre lo importante que es el tema, ni conclusiones que resuman lo dicho. Directo al contenido.

Responde UNICAMENTE con el documento en Markdown. Sin preambulo, sin explicar lo que vas a hacer, sin bloque de codigo envolvente."""


def build_source_prompt(*, title: str, idea: str) -> str:
    """The creator's two inputs, and nothing else.

    ``idea`` may be empty — the wizard asks for it but a title alone is a legitimate,
    if thin, request. Saying so explicitly beats sending an empty section the model has
    to guess the meaning of.
    """
    described = idea.strip()
    detail = (
        f"Lo que el creador quiere cubrir:\n{described}"
        if described
        else "El creador no ha dado mas detalle que el titulo. Cubre lo que "
        "razonablemente esperaria encontrar quien busca material sobre ese tema."
    )
    return (
        f"TEMA DEL DOCUMENTO: {title.strip()}\n\n"
        f"{detail}\n\n"
        "Escribe el documento fuente."
    )


NODE_SOURCE_WRITER_SYSTEM = """Eres redactor de material de referencia para UN punto de formacion en el puesto, en una pyme espanola.

Escribes el DOCUMENTO FUENTE de este punto. Otro sistema sacara de aqui el dossier y la pantalla. No escribes la leccion.

Como tiene que ser el texto:
- Material de referencia de este punto solo: hechos, pasos, cifras, casos limite.
- En espanol claro, dirigido a quien hace el trabajo.
- Dos o tres secciones con encabezados Markdown de nivel 2 (##).
- Cada seccion con contenido util: un procedimiento, una lista de comprobacion, o los datos que hacen falta para dominar este resultado.

Escribe como un fragmento de manual interno generico, sin nombre de empresa.
Las obligaciones se describen por lo que hay que hacer en el puesto.

Responde unicamente con el documento en Markdown."""


def build_node_source_prompt(
    *,
    course_title: str,
    course_idea: str,
    node_title: str,
    summary: str,
    outcome: str,
) -> str:
    """One node, after the schema exists: the brief the pack generator will ground on."""

    idea = course_idea.strip()
    course_line = (
        f"Idea del curso: {idea}"
        if idea
        else "El creador definio el curso por su titulo y este punto del esquema."
    )
    result = outcome.strip() or summary.strip() or node_title.strip()
    covers = summary.strip() or result
    return (
        f"CURSO: {course_title.strip() or node_title.strip()}\n"
        f"{course_line}\n\n"
        f"PUNTO: {node_title.strip()}\n"
        f"Resultado que el empleado debe dominar: {result}\n"
        f"Que cubre este punto: {covers}\n\n"
        "Escribe el documento fuente de este punto."
    )


__all__ = [
    "NODE_SOURCE_WRITER_SYSTEM",
    "SOURCE_WRITER_SYSTEM",
    "build_node_source_prompt",
    "build_source_prompt",
]
