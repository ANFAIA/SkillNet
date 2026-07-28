"""Greetings, thanks and goodbyes, answered without a model.

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
"""

from __future__ import annotations

import unicodedata
from typing import Literal

SmallTalkKind = Literal["greeting", "thanks", "farewell"]

#: The longest phrase below is four words. Anything longer is a question by construction
#: and is not even looked up, so a paragraph that happens to start with "hola" is safe.
MAX_SMALL_TALK_WORDS = 4

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
    """``greeting`` / ``thanks`` / ``farewell``, or ``None`` for anything with a question in it."""
    folded = _fold(message)
    if not folded or len(folded.split()) > MAX_SMALL_TALK_WORDS:
        return None
    for kind, phrases in (
        ("greeting", _GREETINGS),
        ("thanks", _THANKS),
        ("farewell", _FAREWELLS),
    ):
        if folded in {_fold(phrase) for phrase in phrases}:
            return kind  # type: ignore[return-value]
    return None


def small_talk_reply(message: str) -> str | None:
    """The canned answer for ``message``, or ``None`` when it is a real question."""
    kind = classify_small_talk(message)
    return _REPLIES[kind] if kind else None


__all__ = [
    "MAX_SMALL_TALK_WORDS",
    "SmallTalkKind",
    "classify_small_talk",
    "small_talk_reply",
]
