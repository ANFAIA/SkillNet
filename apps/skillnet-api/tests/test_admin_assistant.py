"""The admin assistant answers about the organization, and says hello back.

Both defects were reported from a live session at ``/admin/chat`` on 2026-07-27, and they
are the same defect twice: the assistant was the employee tutor with a different persona,
so it could read training *documents* and nothing else.

* *"como van mis empleados"* -> four bullets of generic management advice ("revisa el
  parte de incidencias", "habla con el encargado"), while five employees and their
  progress sat in the database it administers.
* *"que tal"* -> *"No tengo suficiente informacion para responder a tu pregunta."*

The tests below assert the mechanism, never the model's prose: that the facts are in the
turn, that the private ones are not, that the greeting never reaches a provider, and that
the employee tutor is untouched by all of it.
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
    admin_system_prompt,
    build_admin_turn,
)
from src.services import chat_service as chat_module
from src.services.chat_service import ChatService, _canned_chunks
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


def test_the_prompt_tells_the_model_the_private_half_is_not_missing_but_withheld() -> None:
    """So "no lo tengo" is answered as policy, not as a gap to be filled by guessing."""
    prompt = admin_system_prompt("document", org_data=True)
    assert "privado de cada empleado" in prompt
    assert "accesibilidad" in prompt


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


# -- small talk ---------------------------------------------------------------------
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
        "hola, como van mis empleados",
        "que tal va el curso de alergenos",
        "gracias, y quien no ha empezado?",
        "como van mis empleados",
        "buenas, necesito el listado de plazos",
        "",
        "   ",
    ],
)
def test_a_real_question_is_never_answered_from_the_can(message: str) -> None:
    """Too narrow costs one greeting to the model. Too wide costs a real answer."""
    assert classify_small_talk(message) is None
    assert small_talk_reply(message) is None


def test_the_greeting_reply_says_what_the_assistant_can_do() -> None:
    reply = small_talk_reply("hola") or ""
    assert "empleados" in reply
    assert "cursos" in reply
    # A greeting that answers "hola" and stops is the refusal with better manners.
    assert len(reply) > 120


def test_canned_chunks_reassemble_to_exactly_the_reply() -> None:
    for text in ("hola", "una frase algo mas larga que la anterior, con coma", ""):
        assert "".join(_canned_chunks(text)) == text


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


async def test_a_greeting_never_reaches_the_provider(monkeypatch) -> None:
    """"que tal" used to be answered "No tengo suficiente informacion"."""
    llm = _RecordingLLM()
    events, repo, _ = await _run_admin(monkeypatch, llm, message="que tal")
    answer = "".join(data["content"] for name, data in events if name == "token")

    assert llm.calls == []
    assert llm.completions == 0
    assert "No tengo" not in answer
    assert "empleados" in answer
    assert repo.messages[-1].content == answer
    assert repo.messages[-1].message_metadata["small_talk"] is True


async def test_a_greeting_does_not_pay_for_a_snapshot_either(monkeypatch) -> None:
    _, _, seen = await _run_admin(monkeypatch, _RecordingLLM(), message="hola")
    assert "org_id" not in seen


async def test_a_greeting_still_closes_the_stream_the_way_every_turn_does(
    monkeypatch,
) -> None:
    """The frontend re-enables the composer on ``done``; a canned turn must send one."""
    events, _, _ = await _run_admin(monkeypatch, _RecordingLLM(), message="gracias")
    names = [name for name, _ in events]

    assert names[0] == "grounding"
    assert "token" in names
    assert names[-1] == "done"
    assert next(d for n, d in events if n == "citations")["citations"] == []


# -- the employee tutor is untouched --------------------------------------------------
async def test_the_tutor_gets_no_snapshot_and_no_canned_greeting(monkeypatch) -> None:
    """Everything above is on the ``admin`` path. The tutor's ladder landed yesterday."""
    llm = _RecordingLLM()
    service, user, seen = _service(monkeypatch, llm)
    events = [event async for event in service.stream_tutor(user, "hola", None, None)]

    assert seen == {}
    assert llm.calls, "the tutor still calls the model for a greeting"
    assert "DATOS DE LA PLATAFORMA" not in llm.turn
    assert "tutor de SkillNet" in llm.system
    assert "org_data" not in [name for name, _ in _events(events)]
