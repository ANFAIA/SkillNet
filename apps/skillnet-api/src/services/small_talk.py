"""Greetings, thanks, goodbyes and "quien eres", answered without a model.

The reported defect: the owner typed **"que tal"** into the admin assistant and got *"No
tengo suficiente informacion para responder a tu pregunta."* Nothing was broken in the
retrieval layer — that is the point. The organization has documents, so the turn grounded
on rung 2, the model was handed four kilobytes of an allergen manual and the question
"que tal", and it correctly concluded that the manual does not answer it. A refusal to a
greeting is the single cheapest way to make a product feel dead, and no amount of persona
text fixes it, because the model is not wrong: it *was* asked to answer from a document.

So a greeting never reaches the model at all. The reply is written here, streamed as if it
had been generated, and costs zero tokens, zero latency and zero chance of hallucinating a
figure about somebody's training record. It is also the only place in the assistant where
a canned string is the *better* answer: "hola" has one correct response and it is the same
every time, and this one doubles as the discoverability the surface otherwise lacks — the
admin is told what they can ask for, which is exactly what a person typing "que tal" at a
new tool is trying to find out.

**The matcher is deliberately unable to grow.** It matches the *whole* message against a
closed set of phrases, after folding accents and stripping punctuation. Not a prefix, not
a keyword, not a classifier: "hola, como van mis empleados" is a real question and must
reach the real path. The failure mode of being too narrow is one greeting answered by the
model, which is survivable; the failure mode of being too wide is a real question answered
by a canned string, which is not.

**"quien eres" is the same defect as "que tal", and it arrives here for the same reason**
(reported 2026-07-28). The assistant answered *"No consta la informacion de identidad del
administrador de la plataforma SkillNet"* — it went looking for the admin's identity in
the org snapshot, found no such row, and the no-invention rule correctly turned that into
a non-answer. The mistake was upstream of the model: "who are you" is not a question
*about the data*, it is a question about the assistant, and the assistant is the one thing
in the turn that is not in the snapshot. So it never reaches the model either. Unlike a
greeting this one is not merely cheap-to-can, it is *only* correct canned: the answer is a
fact about the product, and a model paraphrasing it from a persona string is how a
capability the assistant does not have ends up promised to an administrator.
"""

from __future__ import annotations

import unicodedata
from typing import Literal

SmallTalkKind = Literal["greeting", "thanks", "farewell", "identity"]

#: The longest phrase below is six words ("en que me puedes ayudar"). Anything longer is a
#: question by construction and is not even looked up, so a paragraph that happens to
#: start with "hola" is safe. The cap is only an early-out: what keeps a real question off
#: this path is the whole-message equality below, not the length.
MAX_SMALL_TALK_WORDS = 6

_GREETINGS = frozenset(
    {
        "hola",
        "holaa",
        "buenas",
        "hey",
        "ey",
        "que tal",
        "que tal todo",
        "que hay",
        "como estas",
        "como va",
        "como va todo",
        "como te va",
        "buenos dias",
        "buen dia",
        "buenas tardes",
        "buenas noches",
        "hola que tal",
        "hola buenas",
        "buenas hola",
        "hi",
        "hello",
    }
)

_THANKS = frozenset(
    {
        "gracias",
        "muchas gracias",
        "mil gracias",
        "muchisimas gracias",
        "gracias!",
        "genial gracias",
        "perfecto gracias",
        "vale gracias",
        "ok gracias",
        "thanks",
        "thank you",
    }
)

_FAREWELLS = frozenset(
    {
        "adios",
        "hasta luego",
        "hasta manana",
        "nos vemos",
        "chao",
        "chau",
        "buenas noches me voy",
        "bye",
    }
)

#: "Who are you", "what can you do", "help". Every one of these is answered by the same
#: paragraph, because they are the same question: a person who types any of them wants to
#: know what this box is for. Deliberately does **not** contain "que puedo hacer" (the
#: admin asking about their own next action, which is a real question for the data path)
#: nor anything with a noun of the domain in it.
_IDENTITY = frozenset(
    {
        "quien eres",
        "quien eres tu",
        "y tu quien eres",
        "que eres",
        "que eres tu",
        "como te llamas",
        "que puedes hacer",
        "que puedes hacer por mi",
        "que sabes hacer",
        "que haces",
        "que haces tu",
        "para que sirves",
        "para que vales",
        "para que sirve esto",
        "en que me puedes ayudar",
        "en que puedes ayudarme",
        "que te puedo preguntar",
        "que puedo preguntarte",
        "como funcionas",
        "ayuda",
        "help",
        "who are you",
        "what can you do",
    }
)

#: What the assistant can actually do, in the admin's words. Kept in one place so the
#: greeting and the goodbye cannot drift into promising different things.
_CAPABILITIES = (
    "Puedo contarte como van tus empleados (quien ha terminado, quien no ha empezado y "
    "que plazos se estan pasando), que cursos y documentos tienes, y responderte sobre "
    "el contenido de la documentacion que has subido."
)

_REPLIES: dict[str, str] = {
    "greeting": f"Hola. Todo en orden por aqui. {_CAPABILITIES}\n\n"
    "Prueba con \"¿como van mis empleados?\" o \"¿que cursos tengo publicados?\".",
    "thanks": "A mandar. Si necesitas otra cosa —estado de un empleado, de un curso o "
    "de un plazo— dime y lo miro.",
    "farewell": "Hasta luego. Aqui me tienes cuando quieras revisar el estado de la "
    "formacion.",
    # Says what it is before it says what it does, and lists only what the data path can
    # actually deliver today. A capability promised here is a refusal three messages later.
    "identity": "Soy el asistente de SkillNet, el sitio desde el que gestionas la "
    f"formacion de tu equipo. {_CAPABILITIES}\n\n"
    "Lo que no puedo: no veo como aprende cada persona (sus preferencias ni sus "
    "necesidades de accesibilidad son privadas), y no me invento ninguna cifra ni "
    "ningun plazo que no este en la plataforma.\n\n"
    'Prueba con "¿quien no ha empezado sus cursos?", "¿que plazos se estan pasando?" '
    'o "¿que dice el manual de alergenos sobre las trazas?".',
}


#: What the tutor can do, in an employee's words. Kept in one place so the greeting and
#: the goodbye promise the same thing. Deliberately about *learning*, never about other
#: people's records — an employee tutor has no business naming a colleague's progress.
_TUTOR_CAPABILITIES = (
    "Estoy aqui para echarte una mano con tus cursos: te explico lo que no se entienda, "
    "te resumo un tema o te doy los pasos de un procedimiento."
)

#: Employee-facing canned replies. The admin set names admin capabilities ("como van tus
#: empleados"), which would be wrong here, so the tutor gets its own, warmer and about the
#: lesson in front of the learner.
_TUTOR_REPLIES: dict[str, str] = {
    "greeting": f"Hola. {_TUTOR_CAPABILITIES}\n\n"
    'Prueba con "explicame esto mas facil" o "dame los pasos".',
    "thanks": "A ti. Si te atascas con algo del curso, aqui sigo.",
    "farewell": "Hasta luego. Cuando quieras seguir con el curso, aqui me tienes.",
    "identity": "Soy el tutor de SkillNet, tu companero para la formacion. "
    f"{_TUTOR_CAPABILITIES}\n\n"
    'Preguntame lo que no entiendas del curso, o pideme "un ejemplo" o "los pasos".',
}


def _fold(text: str) -> str:
    """Lower-case, strip accents and drop everything that is not a letter or a space.

    Same folding idea as ``src/services/retrieval.py``: an admin writes "¿Qué tal?" and
    the table is written without accents, because this whole repository is.
    """
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = "".join(
        char if (char.isalnum() or char.isspace()) else " " for char in stripped
    )
    return " ".join(cleaned.split())


def classify_small_talk(message: str) -> SmallTalkKind | None:
    """One of the four kinds, or ``None`` for anything that is a real question."""
    folded = _fold(message)
    if not folded or len(folded.split()) > MAX_SMALL_TALK_WORDS:
        return None
    for kind, phrases in (
        ("greeting", _GREETINGS),
        ("thanks", _THANKS),
        ("farewell", _FAREWELLS),
        ("identity", _IDENTITY),
    ):
        if folded in {_fold(phrase) for phrase in phrases}:
            return kind  # type: ignore[return-value]
    return None


def small_talk_reply(
    message: str, *, audience: Literal["admin", "tutor"] = "admin"
) -> str | None:
    """The canned answer for ``message``, or ``None`` when it is a real question.

    ``audience`` picks the voice: the admin assistant lists admin capabilities, the tutor
    lists learning help. The *matcher* is shared — a greeting is a greeting on either
    surface — only the reply text differs.
    """
    kind = classify_small_talk(message)
    if kind is None:
        return None
    replies = _TUTOR_REPLIES if audience == "tutor" else _REPLIES
    return replies[kind]


__all__ = [
    "MAX_SMALL_TALK_WORDS",
    "SmallTalkKind",
    "classify_small_talk",
    "small_talk_reply",
]
