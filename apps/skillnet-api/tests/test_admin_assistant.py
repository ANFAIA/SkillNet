"""The admin assistant answers about the organization, and answers being greeted.

Both defects were reported from a live session at ``/admin/chat`` on 2026-07-27, and they
are the same defect twice: the assistant was the employee tutor with a different persona,
so it could read training *documents* and nothing else.

* *"como van mis empleados"* -> four bullets of generic management advice ("revisa el
  parte de incidencias", "habla con el encargado"), while five employees and their
  progress sat in the database it administers.
* *"que tal"* -> *"No tengo suficiente informacion para responder a tu pregunta."*

The tests below assert the mechanism, never the model's prose: that the facts are in the
turn, that the private ones are not, that a pleasantry is answered rather than refused, and
that the employee tutor is untouched by all of it.

--------------------------------------------------------------------------------------
Why this file changed on 2026-08-04
--------------------------------------------------------------------------------------
It stopped importing in ``7a48fa5`` ("feat(api): single-phase GenUI chat, remove small
talk", 2026-08-03), which deleted ``chat_service._canned_chunks`` along with the whole
canned-answer path. Because the module could not be collected, the suite was being run with
``--ignore=tests/test_admin_assistant.py`` and none of the twenty-odd properties below were
being checked at all — including the snapshot privacy line, which is the most expensive
thing in this file to get wrong.

What ``7a48fa5`` actually removed, and what that does to each group of tests:

* **The canned answers are gone.** ``stream_admin`` no longer consults
  ``small_talk_reply``; every message, greeting included, is grounded, given the snapshot
  and sent to the provider. So the four tests that asserted *"a greeting reaches no
  provider, pays for no snapshot and no second call"* were asserting the opposite of the
  code. They are not deleted — the *defect* they were written for is still a defect — they
  are inverted: the greeting now costs a turn, and what must hold instead is that the
  persona carries the instruction that stops *"No tengo suficiente informacion"*. That is
  where the fix moved, so that is where it is now pinned.
* **``_canned_chunks`` no longer exists.** Its test (``"".join(chunks) == text``) is
  deleted outright: there is no chunker, so there is nothing to be exact about.
* **``src/services/small_talk.py`` survives but is wired to nothing** — the commit says it
  is kept for potential reuse. Its unit tests are kept too, in their own clearly-labelled
  section, because they do test real behaviour of real code; what they no longer describe
  is anything the chat does. Deleting the module is a product call, not a test-repair call.
* **The prompt tests still hold**, with two strings updated for ``075e49f`` (``admin/4``,
  2026-08-04), which rewrote the "a format instruction with no subject" bullet.
* **The snapshot tests were correct all along** and are unchanged.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from src.llm.prompts.admin import (
    ADMIN_DATA_BLOCK,
    ADMIN_PROMPT_VERSION,
    admin_genui_system_prompt,
    admin_system_prompt,
    build_admin_turn,
)
from src.services import chat_service as chat_module
from src.services.chat_service import ChatService
from src.services.org_snapshot import EmployeeFact, EnrolmentFact, OrgSnapshot
from src.services.retrieval import GroundedContext
from src.services.small_talk import classify_small_talk, small_talk_reply

NOW = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)

SNAPSHOT = OrgSnapshot(
    org_name="Panaderia y Cafeteria La Espiga S.L.",
    generated_at=NOW,
    employees=(
        EmployeeFact(
            full_name="Lucia Fernandez Vila",
            role_title="Dependiente",
            enrolments=(
                EnrolmentFact(
                    "Alergenos", "in_progress", 2, 5, "nodos", deadline=date(2026, 8, 15)
                ),
            ),
        ),
    ),
    employees_total=1,
    documents=("Manual de alergenos",),
    documents_total=1,
)


# -- the prompt ---------------------------------------------------------------------
def test_the_data_block_only_appears_when_there_is_data() -> None:
    assert ADMIN_DATA_BLOCK not in admin_system_prompt("document")
    assert ADMIN_DATA_BLOCK in admin_system_prompt("document", org_data=True)


def test_the_data_prompt_forbids_the_number_the_model_did_not_get() -> None:
    """The one rule worth more than the feature: a wrong training figure about a named
    person is worse than "no lo se"."""
    prompt = admin_system_prompt("general", org_data=True)
    assert "tiene que estar literalmente en el bloque" in prompt
    assert "No sumes" in prompt
    assert "no consta" in prompt


def test_the_data_prompt_names_the_failure_it_replaces() -> None:
    """Told only "answer from the data", a small model still writes the advice bullets."""
    prompt = admin_system_prompt("document", org_data=True)
    assert "habla con el encargado" in prompt
    assert "nombres propios y numeros concretos" in prompt


def test_the_prompt_points_at_the_precounted_totals_instead_of_a_headcount() -> None:
    """The first live run answered with five name-by-name blocks and no headline."""
    prompt = admin_system_prompt("document", org_data=True)
    assert "RESUMEN" in prompt
    assert "Empieza SIEMPRE por el titular" in prompt
    # ...and it closed with "revisa el estado de cada empleado", which is the advice bullet
    # wearing a hat.
    assert "no es una accion, es relleno" in prompt


def test_the_closing_action_is_scoped_to_questions_about_people_and_courses() -> None:
    """Reported 2026-07-28: "explicame paso a paso como atender una consulta de alergenos"
    got five correct steps and then "Escribe a Aitana, que no ha abierto sus tres cursos".

    Aitana has nothing to do with the question. The rule that makes a *management* answer
    end in something actionable was firing on a *content* answer, and an answer that ends
    by nagging about an unrelated person reads as broken. So the block now sorts the
    question first and says, in imperative, that the close is forbidden outside case (A).
    """
    prompt = admin_system_prompt("document", org_data=True)

    assert "Pregunta DE GESTION" in prompt
    assert "Pregunta DE CONTENIDO" in prompt
    assert "NO se aplica y esta PROHIBIDA" in prompt
    # The failing turn is quoted verbatim, the way "habla con el encargado" already is.
    assert "escribe a Aitana" in prompt
    assert "La respuesta termina cuando termina el contenido" in prompt


def test_a_question_about_the_assistant_is_not_looked_up_in_the_data() -> None:
    """"quien eres" -> "No consta la informacion de identidad del administrador".

    This is where the deleted canned identity reply went. Until ``7a48fa5`` the question
    never reached a provider, so the prompt only had to be right in theory; now it is the
    only thing standing between *"quien eres"* and a search through the org snapshot for
    the admin's staff record.
    """
    prompt = admin_system_prompt("document", org_data=True)
    assert "la respuesta eres TU" in prompt
    assert "busques en los datos de la organizacion" in prompt
    assert "ahi estan sus empleados y sus cursos" in prompt


def test_no_question_is_allowed_to_be_a_dead_end() -> None:
    """"usa openui para esta respuesta" -> "no puedo comprender la pregunta"."""
    for grounding in ("chunks", "document", "general"):
        for prompt in (
            admin_system_prompt(grounding),
            admin_system_prompt(grounding, org_data=True),
        ):
            assert "no puedo comprender la pregunta" in prompt
            assert "Nunca escribas" in prompt
    # An instruction about the shape of the answer is answered, not refused. In `admin/3`
    # this was its own bullet ("Si te dan una instruccion sobre el FORMATO... y no te dicen
    # SOBRE QUE"); `075e49f` folded it into the "lo que no haces nunca" list, where it now
    # names the three real requests that triggered it.
    persona = admin_system_prompt("general")
    assert 'alguien pida "una tabla" o "un resumen" sin decir DE QUE' in persona
    assert "pregunta SOBRE QUE, no vuelques el bloque" in persona


def test_the_context_is_never_the_answer() -> None:
    """Measured live on the first fix of the dead-end: telling the model not to refuse
    *"usa openui para esta respuesta"* got it to paste the entire platform data block and
    both documents into the bubble instead.

    Trading a refusal for a context dump is not a fix — it is the same non-answer, at
    four kilobytes, with five employees' records in it. So "do not stall" and "do not
    empty the context onto the screen" have to be stated together, and a format
    instruction with no subject is a question to ask back, not an order to fill.
    """
    for prompt in (
        admin_system_prompt("document"),
        admin_system_prompt("document", org_data=True),
    ):
        assert "No copias NUNCA, tal cual, el bloque de datos" in prompt
        assert "no es responder, es vaciarlo en la pantalla" in prompt
        assert "sin tema concreto son" in prompt


def test_the_prompt_tells_the_model_the_private_half_is_not_missing_but_withheld() -> None:
    """So "no lo tengo" is answered as policy, not as a gap to be filled by guessing."""
    prompt = admin_system_prompt("document", org_data=True)
    assert "privado de cada empleado" in prompt
    assert "accesibilidad" in prompt


@pytest.mark.parametrize("grounding", ["chunks", "document", "general"])
def test_teaching_the_dialect_did_not_drop_a_single_limit(grounding: str) -> None:
    """``7a48fa5`` gave the admin a second system prompt, and a second system prompt is a
    second place for the privacy line to go missing.

    ``admin_genui_system_prompt`` is what the model actually sees whenever generative UI is
    on, so every rule the prose prompt is tested for above has to survive the addition of
    the OpenUI spec — and the spec has to actually be in there, or single-phase generation
    is asking for a dialect it never taught.
    """
    genui = admin_genui_system_prompt(grounding, org_data=True)  # type: ignore[arg-type]

    assert ADMIN_DATA_BLOCK in genui
    assert "tiene que estar literalmente en el bloque" in genui
    assert "privado de cada empleado" in genui
    assert "la respuesta eres TU" in genui
    # ...and the half that is new: the dialect it is being asked to write.
    assert "root = Stack(" in genui

    assert ADMIN_DATA_BLOCK not in admin_genui_system_prompt(grounding)  # type: ignore[arg-type]


def test_the_question_is_the_last_thing_in_the_turn() -> None:
    turn = build_admin_turn("document", "[Fuente 1: Manual]\ntexto", "DATOS...", "¿como van?")
    assert turn.rstrip().endswith("Pregunta: ¿como van?")
    assert turn.startswith("DATOS...")


def test_a_turn_with_data_and_no_documents_still_carries_the_data() -> None:
    turn = build_admin_turn("general", "", "DATOS DE LA PLATAFORMA — X", "¿cuantos hay?")
    assert "DATOS DE LA PLATAFORMA" in turn
    assert "criterio general" not in turn


def test_a_turn_with_neither_falls_back_to_the_general_instruction() -> None:
    turn = build_admin_turn("general", "", "", "¿que es un alergeno?")
    assert "criterio general" in turn
    assert "¿que es un alergeno?" in turn


# -- the stream ---------------------------------------------------------------------
class _FakeDB:
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class _FakeRepo:
    def __init__(self) -> None:
        self.messages: list[SimpleNamespace] = []

    async def create_session(self, **_kwargs):
        return SimpleNamespace(id=uuid.uuid4())

    async def get_owned_session(self, session_id, _user_id):
        return SimpleNamespace(id=session_id)

    async def recent_messages(self, _session_id, _limit):
        return []

    async def add_message(self, *, session_id, role, content, metadata=None):
        message = SimpleNamespace(
            id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            message_metadata=metadata or {},
        )
        self.messages.append(message)
        return message


class _RecordingLLM:
    """Records the messages it was asked to stream, then streams a fixed answer."""

    def __init__(self, answer: str = "Lucia va por el 40%.") -> None:
        self.answer = answer
        self.calls: list[list[dict]] = []
        self.completions = 0

    async def stream(self, messages, **_kwargs):
        self.calls.append(list(messages))
        yield self.answer

    async def complete(self, _system, _user, **_kwargs):
        self.completions += 1
        return "NO_UI"

    @property
    def system(self) -> str:
        return self.calls[-1][0]["content"]

    @property
    def turn(self) -> str:
        return self.calls[-1][-1]["content"]


def _events(chunks: list[str]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for chunk in chunks:
        head, _, tail = chunk.partition("\n")
        out.append((head.removeprefix("event: "), json.loads(tail.removeprefix("data: "))))
    return out


def _service(monkeypatch, llm, *, snapshot=SNAPSHOT, grounding="document", org_id=None):
    async def fake_ground(*_args, **_kwargs):
        if grounding == "general":
            return GroundedContext("general")
        return GroundedContext(
            grounding,
            "[Fuente 1: Manual (documento completo)]\ntexto",
            [{"document": "Manual", "section": "documento completo", "page": None}],
        )

    seen: dict[str, object] = {}

    async def fake_build(_db, *, org_id, now=None):
        seen["org_id"] = org_id
        if isinstance(snapshot, Exception):
            raise snapshot
        return snapshot

    monkeypatch.setattr(chat_module, "ground_question", fake_ground)
    monkeypatch.setattr(chat_module, "build_org_snapshot", fake_build)
    service = ChatService(_FakeDB(), llm, object())  # type: ignore[arg-type]
    service.repo = _FakeRepo()  # type: ignore[assignment]
    user = SimpleNamespace(id=uuid.uuid4(), org_id=org_id or uuid.uuid4())
    return service, user, seen


async def _run_admin(monkeypatch, llm, message="como van mis empleados", **kwargs):
    service, user, seen = _service(monkeypatch, llm, **kwargs)
    chunks = [event async for event in service.stream_admin(user, message, None, None)]
    return _events(chunks), service.repo, seen  # type: ignore[return-value]


async def test_the_reported_question_reaches_the_model_with_the_answer_in_it(
    monkeypatch,
) -> None:
    """The whole fix in one assertion: the names and the numbers are in the turn."""
    llm = _RecordingLLM()
    await _run_admin(monkeypatch, llm)

    assert "DATOS DE LA PLATAFORMA" in llm.turn
    assert "Lucia Fernandez Vila (Dependiente)" in llm.turn
    assert "40% (2/5 nodos)" in llm.turn
    assert ADMIN_DATA_BLOCK in llm.system


async def test_the_snapshot_is_announced_as_its_own_event(monkeypatch) -> None:
    events, _, _ = await _run_admin(monkeypatch, _RecordingLLM())
    names = [name for name, _ in events]
    org_data = next(data for name, data in events if name == "org_data")

    # ``grounding`` is about documents; the platform data is a separate axis.
    assert names.index("grounding") < names.index("org_data") < names.index("token")
    assert org_data["employees"] == 1
    assert org_data["generated_at"] == NOW.isoformat()


async def test_the_snapshot_is_scoped_to_the_callers_organization(monkeypatch) -> None:
    """One org today. A query that assumes so is the query that leaks when there are two."""
    org_id = uuid.uuid4()
    _, _, seen = await _run_admin(monkeypatch, _RecordingLLM(), org_id=org_id)
    assert seen["org_id"] == org_id


async def test_the_snapshot_is_persisted_alongside_the_answer(monkeypatch) -> None:
    _, repo, _ = await _run_admin(monkeypatch, _RecordingLLM())
    metadata = repo.messages[-1].message_metadata

    assert metadata["prompt_version"] == ADMIN_PROMPT_VERSION
    assert metadata["org_data"]["employees"] == 1


async def test_a_broken_snapshot_costs_the_data_and_never_the_answer(monkeypatch) -> None:
    """Eight aggregate queries is eight chances to fail; none of them may eat the turn."""
    llm = _RecordingLLM()
    events, _, _ = await _run_admin(
        monkeypatch, llm, snapshot=RuntimeError("relation does not exist")
    )
    names = [name for name, _ in events]

    assert "error" not in names
    assert "org_data" not in names
    assert "done" in names
    assert "DATOS DE LA PLATAFORMA" not in llm.turn
    # ...and the assistant it degrades to is exactly yesterday's document assistant.
    assert ADMIN_DATA_BLOCK not in llm.system
    assert "documentos de la organizacion" in llm.system


async def test_an_organization_with_nothing_in_it_adds_no_empty_block(monkeypatch) -> None:
    llm = _RecordingLLM()
    empty = OrgSnapshot(org_name="Nueva S.L.", generated_at=NOW)
    events, _, _ = await _run_admin(monkeypatch, llm, snapshot=empty)

    assert "org_data" not in [name for name, _ in events]
    assert "DATOS DE LA PLATAFORMA" not in llm.turn


async def test_the_snapshot_travels_even_when_no_document_matched(monkeypatch) -> None:
    """Rung 3 is about documents. "Cuantos empleados tengo" needs none of them."""
    llm = _RecordingLLM()
    await _run_admin(monkeypatch, llm, grounding="general")

    assert "DATOS DE LA PLATAFORMA" in llm.turn
    assert "Lucia Fernandez Vila" in llm.turn


# -- a pleasantry is a turn now ------------------------------------------------------
# These four replace the four that asserted the opposite. ``7a48fa5`` removed the canned
# path deliberately — "all messages go through the LLM, which now has enough persona
# context to handle them" — so what used to be free is now priced, and what used to be
# guaranteed by a lookup table is now guaranteed by the persona. Both halves are asserted,
# because a greeting that costs a provider call *and* comes back with "No tengo suficiente
# informacion" would be the reported defect back at a higher price.
@pytest.mark.parametrize("message", ["hola", "que tal", "gracias", "quien eres"])
async def test_a_pleasantry_now_reaches_the_provider_like_every_other_message(
    monkeypatch, message: str
) -> None:
    llm = _RecordingLLM()
    events, repo, seen = await _run_admin(monkeypatch, llm, message=message)
    names = [name for name, _ in events]

    assert llm.calls, "there is no canned path left: the model answers this"
    assert llm.turn.rstrip().endswith(f"Pregunta: {message}")
    # No canned answer means no marker for one.
    assert "small_talk" not in repo.messages[-1].message_metadata
    assert names[-1] == "done"


async def test_the_greeting_is_answered_by_the_persona_now_instead_of_a_lookup_table(
    monkeypatch,
) -> None:
    """*"que tal"* -> *"No tengo suficiente informacion"* was the reported defect, and the
    first fix was to answer it without a provider at all.

    That fix is gone. What has to hold instead is that the model is not put in the position
    that produced the refusal: it is a document assistant handed an allergen manual and a
    pleasantry unless the persona tells it that a dead end is not an answer, and that a
    question about itself is answered from itself.
    """
    llm = _RecordingLLM()
    _, _, _ = await _run_admin(monkeypatch, llm, message="que tal")

    assert "no puedo comprender la pregunta" in llm.system  # forbidden, verbatim
    assert "Nunca escribas" in llm.system
    assert "la respuesta eres TU" in llm.system
    assert "asistente del administrador de SkillNet" in llm.system


async def test_a_pleasantry_now_pays_for_the_snapshot_too(monkeypatch) -> None:
    """The measurable cost of removing the canned path, stated rather than discovered.

    Before ``7a48fa5``, *"hola"* skipped retrieval and skipped the eight aggregate queries
    of ``build_org_snapshot``. It no longer does: the gate that decided "this needs no
    context" was the small-talk classifier, and there is nothing in its place. Asserted so
    that a future change back to a cheap path fails here and gets read, rather than
    quietly re-diverging from what this file claims.
    """
    _, _, seen = await _run_admin(monkeypatch, _RecordingLLM(), message="hola")
    assert "org_id" in seen


@pytest.mark.parametrize("message", ["hola", "quien eres", "gracias"])
async def test_one_turn_is_still_exactly_one_provider_call(monkeypatch, message: str) -> None:
    """Single-phase, on the cheapest messages there are.

    Its ancestor asserted that a canned answer paid for no *layout* call — the identity
    reply is comfortably longer than ``MIN_LAYOUT_CHARS``, so the moment the admin path
    started laying out, the one question guaranteed never to reach a provider began
    emitting ``layout_start``. The canned answer is gone and so is the second call: the
    admin's blocks come out of the same stream as its prose, and ``complete`` is never
    reached on this path at all.
    """
    llm = _RecordingLLM()
    service, user, _ = _service(monkeypatch, llm)
    service.generative_ui = True
    events = _events(
        [event async for event in service.stream_admin(user, message, None, None)]
    )

    assert len(llm.calls) == 1
    assert llm.completions == 0
    assert "layout_start" not in [name for name, _ in events]
    assert [name for name, _ in events][-1] == "done"


async def test_every_turn_closes_the_stream_the_way_the_frontend_needs(
    monkeypatch,
) -> None:
    """The frontend re-enables the composer on ``done``; every turn must send one.

    Written for the canned path, kept for the ordinary one: this used to be the only test
    covering a turn that skipped grounding, and its ``citations == []`` assertion was an
    artefact of that skip. A greeting is grounded like anything else now, so what is pinned
    is the event order, which is what the composer depends on.
    """
    events, _, _ = await _run_admin(monkeypatch, _RecordingLLM(), message="gracias")
    names = [name for name, _ in events]

    assert names[0] == "grounding"
    assert "token" in names
    assert names.index("citations") < names.index("done")
    assert names[-1] == "done"


# -- the employee tutor is untouched --------------------------------------------------
async def test_the_tutor_gets_no_snapshot_and_no_admin_persona(monkeypatch) -> None:
    """Everything above is on the ``admin`` path. The tutor's ladder landed yesterday."""
    llm = _RecordingLLM()
    service, user, seen = _service(monkeypatch, llm)
    events = [event async for event in service.stream_tutor(user, "hola", None, None)]

    assert seen == {}
    assert llm.calls, "the tutor still calls the model for a greeting"
    assert "DATOS DE LA PLATAFORMA" not in llm.turn
    assert "tutor de SkillNet" in llm.system
    assert "org_data" not in [name for name, _ in _events(events)]


# --------------------------------------------------------------------------------------
# ``src/services/small_talk.py``: a module nothing imports any more
# --------------------------------------------------------------------------------------
# ``7a48fa5`` unwired it and kept the file, in its own words, "for its tests and potential
# reuse elsewhere". These tests are therefore honest about what they cover and honest about
# what they do not: the classifier and the canned replies still behave exactly as written,
# and nothing in the product calls either of them. Nothing above depends on this section —
# the chat's behaviour with a greeting is pinned in "a pleasantry is a turn now".
#
# Left in place rather than deleted because deleting the module is a product decision (it is
# the ready-made cheap path back, if the cost measured in
# ``test_a_pleasantry_now_pays_for_the_snapshot_too`` ever matters), and a test file is the
# wrong place to take it. If the decision is "small talk is not coming back", the module and
# this section go together.
@pytest.mark.parametrize(
    "message",
    ["hola", "Hola", "  hola  ", "¿Qué tal?", "que tal", "buenas", "Buenos dias"],
)
def test_a_greeting_is_recognised_however_it_is_typed(message: str) -> None:
    assert classify_small_talk(message) == "greeting"


@pytest.mark.parametrize("message", ["gracias", "Muchas gracias!", "ok gracias"])
def test_thanks_is_its_own_reply(message: str) -> None:
    assert classify_small_talk(message) == "thanks"


@pytest.mark.parametrize("message", ["adios", "Hasta luego", "nos vemos"])
def test_a_farewell_is_its_own_reply(message: str) -> None:
    assert classify_small_talk(message) == "farewell"


@pytest.mark.parametrize(
    "message",
    [
        "quien eres",
        "¿Quién eres?",
        "  QUE ERES  ",
        "que puedes hacer",
        "para que sirves",
        "ayuda",
        "en que me puedes ayudar",
        "como funcionas",
        "who are you",
    ],
)
def test_asking_the_assistant_about_itself_is_its_own_class(message: str) -> None:
    """Reported: *"quien eres"* -> *"No consta la informacion de identidad del
    administrador de la plataforma SkillNet."*

    It searched the org snapshot for the admin's identity. The assistant is the one thing
    in the turn that is not in the snapshot, so the question never got there. The chat
    answers this from the persona now — see
    ``test_a_question_about_the_assistant_is_not_looked_up_in_the_data``.
    """
    assert classify_small_talk(message) == "identity"


def test_the_identity_reply_says_what_it_is_what_it_does_and_what_it_will_not_do() -> None:
    reply = small_talk_reply("quien eres") or ""

    assert "asistente de SkillNet" in reply
    assert "empleados" in reply
    # The two honest limits, said before anyone has to discover them.
    assert "privadas" in reply
    assert "no me invento" in reply
    # Not the greeting: "hola" and "quien eres" are different questions.
    assert reply != small_talk_reply("hola")


def test_the_greeting_reply_says_what_the_assistant_can_do() -> None:
    reply = small_talk_reply("hola") or ""
    assert "empleados" in reply
    assert "cursos" in reply
    # A greeting that answers "hola" and stops is the refusal with better manners.
    assert len(reply) > 120


@pytest.mark.parametrize(
    "message",
    [
        "hola, como van mis empleados",
        "que tal va el curso de alergenos",
        "gracias, y quien no ha empezado?",
        "como van mis empleados",
        "buenas, necesito el listado de plazos",
        "",
        "   ",
        # Near misses of the identity table that are real questions about the data.
        "quien eres tu para Lucia",
        "que puedo hacer con Aitana",
        "que puedes hacer con los cursos sin publicar",
        "ayuda a Lucia",
        "para que sirve el curso de alergenos",
    ],
)
def test_a_real_question_is_never_classified_as_small_talk(message: str) -> None:
    """Too narrow costs one greeting to the model. Too wide costs a real answer."""
    assert classify_small_talk(message) is None
    assert small_talk_reply(message) is None
