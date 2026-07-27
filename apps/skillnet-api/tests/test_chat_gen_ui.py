"""Generative UI in the chat: the gate on the layout call, and the stream around it.

Two properties are worth more than the rest and each has its own block below:

1. **The browser never receives the model's bytes.** Everything served is the
   re-serialization of a validated ``UISpec`` — the same rule as a node render, applied to
   an input that is *less* trusted than a node prompt, because a learner's free text is in
   it.
2. **A failed layout costs nothing.** Every rejection path ends with the prose the learner
   has already read, never with a blank bubble and never with a slower chat.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from src.llm.prompts.tutor import NO_UI_SENTINEL, chat_ui_system
from src.routes import chat as chat_route
from src.services import chat_service as chat_module
from src.services.chat_service import (
    MIN_LAYOUT_CHARS,
    ChatService,
    strip_no_ui,
    validate_chat_program,
)
from src.services.org_features import chat_generative_ui_enabled
from src.services.retrieval import GroundedContext

VALID_PROGRAM = (
    'root = Stack([intro, pasos], "md")\n'
    'intro = TextContent("Los alergenos son las 14 sustancias de declaracion obligatoria.", "lead")\n'
    'pasos = StepSequence("Como se informa", ["Consulta la ficha del producto", "Lee lo que pone"])\n'
)

QUIZ_PROGRAM = (
    'root = Stack([intro, q1], "md")\n'
    'intro = TextContent("Repasemos.", "lead")\n'
    'q1 = QuizItem("q1", "test", "apply", "Cuantos alergenos hay?", ["12", "14"])\n'
)

REACTIVE_PROGRAM = (
    'root = Stack([intro], "md")\n'
    'intro = TextContent($nombre, "lead")\n'
)


# -- the verdict token --------------------------------------------------------------
@pytest.mark.parametrize(
    "raw", [NO_UI_SENTINEL, f"  {NO_UI_SENTINEL}  ", f"{NO_UI_SENTINEL}.", f"`{NO_UI_SENTINEL}`"]
)
def test_no_ui_is_recognised_however_the_model_dresses_it(raw: str) -> None:
    assert strip_no_ui(raw) == ""


def test_a_program_survives_strip() -> None:
    assert strip_no_ui(VALID_PROGRAM).startswith("root =")


# -- the gate -----------------------------------------------------------------------
def test_a_valid_program_comes_back_canonical() -> None:
    program = validate_chat_program(VALID_PROGRAM)

    assert program is not None
    assert "StepSequence" in program
    # Canonical, not the input: one declaration per line, re-serialized from the spec.
    assert program.count("\n") >= 3


def test_the_browser_never_gets_the_model_bytes() -> None:
    """A trailing comment is legal prose to a model and absent from a ``UISpec``."""
    program = validate_chat_program(VALID_PROGRAM + "\n```\n")
    assert program is not None
    assert "```" not in program


def test_citation_markers_are_stripped_out_of_the_blocks() -> None:
    """Measured on the first live run: the model copied ``[Fuente 1]`` into the lead.

    The citations are printed under the bubble, so the marker is a duplicate pointing at a
    numbering the blocks do not have. Rule Chat 6 asks; this makes it true.
    """
    program = validate_chat_program(
        'root = Stack([intro], "md")\n'
        'intro = TextContent("Hay catorce alergenos [Fuente 1]. Estan en el manual.", "lead")\n'
    )

    assert program is not None
    assert "[Fuente" not in program
    assert "Hay catorce alergenos. Estan en el manual." in program


def test_a_quiz_item_is_refused() -> None:
    """No node, no render row, no answer_key: a chat quiz could only be ungradeable."""
    assert validate_chat_program(QUIZ_PROGRAM) is None


def test_reactivity_is_refused() -> None:
    assert validate_chat_program(REACTIVE_PROGRAM) is None


def test_garbage_is_refused_rather_than_raising() -> None:
    assert validate_chat_program("lo siento, no puedo ayudarte con eso") is None


def test_no_ui_is_refused_quietly() -> None:
    assert validate_chat_program(NO_UI_SENTINEL) is None


def test_the_layout_prompt_forbids_quiz_and_teaches_the_same_catalogue() -> None:
    system = chat_ui_system()
    assert "Prohibido QuizItem" in system
    assert "StepSequence(title: string, steps: string[])" in system  # the shared artefact
    assert NO_UI_SENTINEL in system


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


class _FakeLLM:
    """Streams ``answer`` token by token, then returns ``layout`` from ``complete``."""

    def __init__(self, answer: str, layout: str = NO_UI_SENTINEL) -> None:
        self.answer = answer
        self.layout = layout
        self.completions = 0

    async def stream(self, _messages, **_kwargs):
        for word in self.answer.split(" "):
            yield word + " "

    async def complete(self, _system, _user, **_kwargs):
        self.completions += 1
        if isinstance(self.layout, Exception):
            raise self.layout
        return self.layout


def _events(chunks: list[str]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for chunk in chunks:
        head, _, tail = chunk.partition("\n")
        out.append((head.removeprefix("event: "), json.loads(tail.removeprefix("data: "))))
    return out


async def _run(monkeypatch, llm: _FakeLLM, *, generative_ui: bool, grounding="document"):
    async def fake_ground(*_args, **_kwargs):
        return GroundedContext(
            grounding,
            "[Fuente 1: Manual (documento completo)]\ntexto",
            [{"document": "Manual", "section": "documento completo", "page": None}],
        )

    monkeypatch.setattr(chat_module, "ground_question", fake_ground)
    service = ChatService(
        _FakeDB(),  # type: ignore[arg-type]
        llm,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        generative_ui=generative_ui,
    )
    repo = _FakeRepo()
    service.repo = repo  # type: ignore[assignment]
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    chunks = [
        event async for event in service.stream_tutor(user, "¿Qué son los alérgenos?", None, None)
    ]
    return _events(chunks), repo


LONG_ANSWER = "Los alergenos son las catorce sustancias de declaracion obligatoria. " * 4


async def test_grounding_is_announced_before_the_first_token(monkeypatch) -> None:
    events, _ = await _run(monkeypatch, _FakeLLM("Hola."), generative_ui=False)
    names = [name for name, _ in events]

    assert names[0] == "grounding"
    assert events[0][1]["grounding"] == "document"
    assert names.index("token") < names.index("citations") < names.index("done")


async def test_the_program_arrives_after_done(monkeypatch) -> None:
    """The composer is handed back at ``done``; the blocks are a trailing event."""
    llm = _FakeLLM(LONG_ANSWER, layout=VALID_PROGRAM)
    events, repo = await _run(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert names.index("done") < names.index("ui")
    assert names.index("layout_start") == names.index("done") + 1
    program = dict(events[names.index("ui")][1])["program"]
    assert "StepSequence" in program
    # Persisted for the next time the session is opened, canonical text only.
    assert repo.messages[-1].message_metadata["program"] == program


async def test_an_invalid_program_degrades_to_the_prose(monkeypatch) -> None:
    llm = _FakeLLM(LONG_ANSWER, layout=QUIZ_PROGRAM)
    events, repo = await _run(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert "ui" not in names
    assert "layout_skipped" in names
    assert repo.messages[-1].content.strip().startswith("Los alergenos")
    assert "program" not in repo.messages[-1].message_metadata


async def test_a_provider_failure_during_layout_degrades_to_the_prose(monkeypatch) -> None:
    llm = _FakeLLM(LONG_ANSWER, layout=RuntimeError("429 rate limit"))
    events, _ = await _run(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert "ui" not in names
    assert "error" not in names
    assert "done" in names


async def test_the_flag_off_is_yesterdays_chat(monkeypatch) -> None:
    """v1 with ``DYNAMIC_COURSES_MODE`` off: no second call, no new events."""
    llm = _FakeLLM(LONG_ANSWER, layout=VALID_PROGRAM)
    events, _ = await _run(monkeypatch, llm, generative_ui=False)
    names = [name for name, _ in events]

    assert llm.completions == 0
    assert "ui" not in names
    assert "layout_start" not in names


async def test_the_admin_switch_off_costs_nothing_and_reads_the_same(monkeypatch) -> None:
    """The admin's ``chat_generative_ui=False``, end to end through the composition.

    Two claims, and the second is the one worth a test: the layout model is never called
    (the point of the switch is the *call*, not the blocks), and what the learner gets is
    indistinguishable from the automatic fall back to prose — same answer, same citations,
    same grounding label.
    """
    org_off = {"chat_generative_ui": False}
    monkeypatch.setattr(chat_route.settings, "DYNAMIC_COURSES_MODE", "on")
    generative_ui = chat_route.dynamic_courses_on() and chat_generative_ui_enabled(org_off)
    assert generative_ui is False

    off_llm = _FakeLLM(LONG_ANSWER, layout=VALID_PROGRAM)
    off_events, off_repo = await _run(monkeypatch, off_llm, generative_ui=generative_ui)

    # ...and the same turn where the model simply wrote an unusable program.
    rejected_llm = _FakeLLM(LONG_ANSWER, layout="lo siento, no puedo")
    rejected_events, _ = await _run(monkeypatch, rejected_llm, generative_ui=True)

    assert off_llm.completions == 0
    assert rejected_llm.completions == 1
    assert "program" not in off_repo.messages[-1].message_metadata

    def answer(events):
        return (
            "".join(d["content"] for n, d in events if n == "token"),
            next(d for n, d in events if n == "citations"),
            next(d for n, d in events if n == "grounding"),
            "ui" in [n for n, _ in events],
        )

    assert answer(off_events) == answer(rejected_events)


@pytest.mark.parametrize(
    ("mode", "org_settings", "expected"),
    [
        ("on", None, True),
        ("on", {}, True),
        ("on", {"chat_generative_ui": True}, True),
        ("on", {"chat_generative_ui": "si"}, True),  # malformed is not "off"
        ("on", {"chat_generative_ui": False}, False),
        ("shadow", {}, False),
        ("off", {}, False),
        ("off", {"chat_generative_ui": True}, False),
    ],
)
def test_both_switches_have_to_agree(monkeypatch, mode, org_settings, expected) -> None:
    monkeypatch.setattr(chat_route.settings, "DYNAMIC_COURSES_MODE", mode)
    enabled = chat_route.dynamic_courses_on() and chat_generative_ui_enabled(org_settings)
    assert enabled is expected


async def test_a_short_answer_does_not_pay_for_a_second_call(monkeypatch) -> None:
    llm = _FakeLLM("Si, siempre.", layout=VALID_PROGRAM)
    events, _ = await _run(monkeypatch, llm, generative_ui=True)

    assert len("Si, siempre.") < MIN_LAYOUT_CHARS
    assert llm.completions == 0
    assert "ui" not in [name for name, _ in events]


async def test_the_admin_assistant_never_lays_out(monkeypatch) -> None:
    async def fake_ground(*_args, **_kwargs):
        return GroundedContext("general")

    monkeypatch.setattr(chat_module, "ground_question", fake_ground)
    llm = _FakeLLM(LONG_ANSWER, layout=VALID_PROGRAM)
    service = ChatService(
        _FakeDB(),  # type: ignore[arg-type]
        llm,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        generative_ui=True,
    )
    service.repo = _FakeRepo()  # type: ignore[assignment]
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    events = [event async for event in service.stream_admin(user, "cuantos cursos hay", None, None)]

    assert llm.completions == 0
    assert "ui" not in [name for name, _ in _events(events)]


async def test_a_user_with_nothing_still_gets_an_answer(monkeypatch) -> None:
    """Rung 3 end to end: no enrolments, no documents, and still not a refusal."""
    async def fake_ground(*_args, **_kwargs):
        return GroundedContext("general")

    monkeypatch.setattr(chat_module, "ground_question", fake_ground)
    llm = _FakeLLM("Esto no aparece en la documentacion de tu empresa, pero en general...")
    service = ChatService(
        _FakeDB(),  # type: ignore[arg-type]
        llm,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
    )
    repo = _FakeRepo()
    service.repo = repo  # type: ignore[assignment]
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    events = _events(
        [event async for event in service.stream_tutor(user, "que es un alergeno", None, None)]
    )

    grounding = next(data for name, data in events if name == "grounding")
    assert grounding["grounding"] == "general"
    assert "".join(data["content"] for name, data in events if name == "token").strip()
    assert repo.messages[-1].message_metadata["grounding"] == "general"
