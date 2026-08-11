"""Generative UI in the chat: the gate on the layout call, and the stream around it.

Three properties are worth more than the rest and each has its own block below:

1. **The browser never receives the model's bytes.** Everything served is the
   re-serialization of a validated ``UISpec`` — the same rule as a node render, applied to
   an input that is *less* trusted than a node prompt, because a learner's free text is in
   it.
2. **A failed layout costs nothing.** Every rejection path ends with the prose the learner
   has already read, never with a blank bubble and never with a slower chat.
3. **The model classifies and populates; the server writes the program** (2026-07-28).
   The assertions in "classify + populate" below are about what the model can no longer
   do: it cannot pass a named argument, cannot put an accent in an identifier and cannot
   blow the line cap, because it does not type the program. Every one of those was a real
   rejection in ``bench_out/failures/``.

The two surfaces stopped sharing a mechanism on 2026-08-03 (``7a48fa5``): the **tutor**
still streams prose and buys a second call to classify and populate it, while the **admin**
is taught the dialect in its own system prompt and the stream *is* the program. Property 1
holds for both — nothing reaches the browser that is not a re-serialized ``UISpec`` — and
property 2 changes shape for the admin: there is no second call to fail, so a turn with no
usable program is simply a turn, with no ``layout_start``/``layout_skipped`` pair around it.
"""

from __future__ import annotations

import inspect
import json
import uuid
from types import SimpleNamespace

import pytest

from src.llm.prompts.tutor import (
    CHAT_LAYOUT_SYSTEM,
    CHAT_SHAPES,
    MAX_STEPS,
    NO_UI_SENTINEL,
    chat_ui_system,
)
from src.routes import chat as chat_route
from src.services import chat_service as chat_module
from src.services.chat_service import (
    ALLOWED_TOOLS,
    MIN_LAYOUT_CHARS,
    ChatService,
    emit_chat_program,
    extract_actions,
    invented_figures,
    parse_layout_json,
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

#: What the layout model returns now: a shape and its fields, never markup.
STEPS_PAYLOAD = json.dumps(
    {
        "shape": "steps",
        # No digit anywhere: ``LONG_ANSWER`` writes "catorce" in words, and the
        # invented-figure guard is right to refuse a "14" the prose never showed.
        "lead": "Los alergenos son las sustancias de declaracion obligatoria.",
        "title": "Como se informa",
        "steps": ["Consulta la ficha del producto", "Lee lo que pone en voz alta"],
    }
)

TABLE_PAYLOAD = json.dumps(
    {
        "shape": "table",
        "lead": "Asi va cada persona.",
        "headers": ["Empleado", "Curso", "Estado"],
        "rows": [
            ["Lucia Fernandez Vila", "Alergenos", "40%"],
            ["Aitana Ruiz", "Higiene", "sin empezar"],
        ],
    }
)

PROSE_PAYLOAD = json.dumps({"shape": "prose"})

#: The admin answer the table above re-lays. Every figure in ``TABLE_PAYLOAD`` is in here,
#: which is the only way a table about people's training records is allowed to exist.
ADMIN_ANSWER = (
    "Tienes dos personas con formacion abierta. Lucia Fernandez Vila va por el 40% del "
    "curso de Alergenos y Aitana Ruiz no ha empezado el de Higiene. "
) * 2

#: What the admin assistant streams since ``7a48fa5``: the program itself, in one call.
#: The tutor still streams prose and pays for ``STEPS_PAYLOAD``-shaped second call above.
ADMIN_PROGRAM = (
    'root = Stack([intro, tabla], "md")\n'
    'intro = TextContent("Asi va cada persona.", "lead")\n'
    'tabla = Table(["Empleado", "Curso", "Estado"], '
    '[["Lucia Fernandez Vila", "Alergenos", "40%"], '
    '["Aitana Ruiz", "Higiene", "sin empezar"]])\n'
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


def test_the_node_layout_prompt_still_teaches_the_shared_catalogue() -> None:
    """``chat_ui_system`` is no longer on the chat's path; the node runtime's rules are.

    Kept as a test so the artefact those rules are generated from cannot drift unnoticed
    while nothing in the chat reads it any more.
    """
    system = chat_ui_system()
    assert "Prohibido QuizItem" in system
    assert "StepSequence(title: string, steps: string[])" in system  # the shared artefact
    assert NO_UI_SENTINEL in system


# -- classify + populate ---------------------------------------------------------------
def test_the_layout_prompt_asks_for_json_and_forbids_markup() -> None:
    """The whole point: the model is told it is not writing a program."""
    assert "NO escribes codigo" in CHAT_LAYOUT_SYSTEM
    assert "UN objeto JSON" in CHAT_LAYOUT_SYSTEM
    # ...and the five shapes are all offered, "prose" included, or the model has to
    # squeeze a paragraph into a table.
    for shape in CHAT_SHAPES:
        assert f'"{shape}"' in CHAT_LAYOUT_SYSTEM
    # The rule that outranks the layout: this call may not touch a number.
    assert "No cambias ninguna cifra" in CHAT_LAYOUT_SYSTEM


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"shape": "steps", "lead": "L", "title": "T", "steps": ["a", "b"]}, "StepSequence"),
        (
            {"shape": "table", "lead": "L", "headers": ["a", "b"], "rows": [["1", "2"], ["3", "4"]]},
            "Table",
        ),
        ({"shape": "callout", "lead": "L", "tone": "warn", "text": "x"}, "Callout"),
        (
            {
                "shape": "definition",
                "lead": "L",
                "title": "T",
                "points": [{"term": "a", "detail": "b"}, {"term": "c", "detail": "d"}],
            },
            "Card",
        ),
    ],
)
def test_each_shape_emits_a_program_the_gate_accepts(payload, expected) -> None:
    program = emit_chat_program(payload)
    assert program is not None and expected in program
    # And the gate — the same one a node render goes through — takes it unchanged.
    assert validate_chat_program(program) == program


def test_the_emitted_program_is_already_canonical() -> None:
    """``serialize(parse(emitted)) == emitted``, so the gate is a check, not a rewrite.

    Worth its own assertion: it is the evidence that the server writes the *canonical*
    form rather than something the backend has to tidy up, which is what makes the round
    trip through ``canonicalize`` free of surprises.
    """
    program = emit_chat_program(json.loads(TABLE_PAYLOAD))
    assert program is not None
    assert validate_chat_program(program) == program


@pytest.mark.parametrize(
    "payload",
    [
        {"shape": "prose"},
        {"shape": "prose", "lead": "sobra"},
        {"shape": "diagram", "lead": "L"},  # not in the enum
        {"shape": "steps", "lead": "L", "title": "T", "steps": ["solo uno"]},
        {"shape": "steps", "lead": "L", "title": "T", "steps": ["x"] * (MAX_STEPS + 1)},
        {"shape": "steps", "lead": "L", "steps": ["a", "b"]},  # no title
        {"shape": "table", "lead": "L", "headers": ["a", "b"], "rows": [["1"], ["2", "3"]]},
        {"shape": "table", "lead": "L", "headers": ["a"], "rows": [["1"], ["2"]]},
        {"shape": "table", "lead": "L", "headers": ["a", "b"], "rows": [["1", "2"]]},
        {"shape": "definition", "lead": "L", "title": "T", "points": [{"term": "a"}]},
        {"shape": "steps", "lead": "L", "title": "T", "steps": "no es una lista"},
        {"shape": "steps"},
        "no es un objeto",
        None,
        [],
    ],
)
def test_anything_that_is_not_the_shape_it_claims_falls_back_to_prose(payload) -> None:
    """No coercion, no second guess. A table with a hole in it is worse than a paragraph."""
    assert emit_chat_program(payload) is None


def test_a_number_where_a_cell_was_asked_for_is_kept_not_blanked() -> None:
    """Asked for a cell, a model writes ``40`` as often as ``"40"``.

    The first cut of the emitter required ``str`` and turned an all-numeric table into a
    grid of empty cells — a block that renders, says nothing, and reads as missing data
    rather than as a failed layout. The worst of the three possible outcomes.
    """
    program = emit_chat_program(
        {"shape": "table", "lead": "L", "headers": ["A", "B"], "rows": [[1, 2], [3, 4]]}
    )
    assert program is not None
    assert '[["1", "2"], ["3", "4"]]' in program


def test_an_empty_cell_is_data_and_a_non_scalar_cell_is_a_failure() -> None:
    """"sin plazo" is a blank cell. ``{"a": 1}`` is a table the model did not populate."""
    blank = emit_chat_program(
        {"shape": "table", "lead": "L", "headers": ["A", "B"], "rows": [["x", ""], ["y", "z"]]}
    )
    assert blank is not None and '["x", ""]' in blank

    for bad_cell in ({"a": 1}, ["nested"], True, None):
        assert (
            emit_chat_program(
                {
                    "shape": "table",
                    "lead": "L",
                    "headers": ["A", "B"],
                    "rows": [["x", bad_cell], ["y", "z"]],
                }
            )
            is None
        )


@pytest.mark.parametrize("bad_step", [{"a": 1}, ["nested"], "", "   ", None, True])
def test_one_unusable_step_kills_the_procedure_instead_of_shortening_it(bad_step) -> None:
    """Dropping it quietly would serve a three-step procedure as two.

    A wrong answer that looks like a right one is the worst thing this call can produce,
    and a procedure is where it would hurt most: the missing step is the one nobody knows
    they skipped.
    """
    assert (
        emit_chat_program(
            {"shape": "steps", "lead": "L", "title": "T", "steps": [bad_step, "b", "c"]}
        )
        is None
    )


def test_a_lead_is_required_unless_the_body_can_fill_the_slot_itself() -> None:
    """Contract rule 7. A Callout is a legal first child; a StepSequence is not.

    The emitter never writes a lead of its own to satisfy the rule — inventing a sentence
    is exactly the thing this whole call is forbidden to do.
    """
    assert emit_chat_program({"shape": "steps", "title": "T", "steps": ["a", "b"]}) is None
    callout = emit_chat_program({"shape": "callout", "text": "No sirvas sin comprobarlo"})
    assert callout is not None
    assert validate_chat_program(callout) == callout


def test_the_failure_classes_the_bench_measured_are_unrepresentable() -> None:
    """Named arguments, an accented identifier, ``{``, the line cap.

    All four were real rejections in ``bench_out/failures/`` when the model authored the
    program. Here the model supplies them *as content* and the program is still clean,
    because the model no longer writes any of the syntax.
    """
    program = emit_chat_program(
        {
            "shape": "steps",
            "lead": "Stack(children = [intro], gap = \"md\")",
            "title": "Conclusión con acento y {llaves}",
            "steps": ["línea uno\ncon salto", "dos"],
        }
    )
    assert program is not None
    assert validate_chat_program(program) == program
    # Three lines, whatever the model wrote: the shape decides the size, not the content.
    assert program.count("\n") == 3
    # The newline inside a value became a space rather than an unterminated literal.
    assert "línea uno con salto" in program


# -- no figure survives the layout call that was not in the answer -----------------------
def test_a_figure_the_answer_never_had_is_caught() -> None:
    answer = "Lucia va por el 40% (2 de 5 nodos) y Aitana no ha empezado."
    honest = 'cuerpo = Table(["Quien", "Cuanto"], [["Lucia", "40%"], ["Aitana", "sin empezar"]])'
    invented = 'cuerpo = Table(["Quien", "Cuanto"], [["Lucia", "60%"], ["Aitana", "0 de 5"]])'

    assert invented_figures(honest, answer) == []
    # "0" counts too: the answer said "no ha empezado", not "0 de 5".
    assert invented_figures(invented, answer) == ["0", "60"]


def test_the_shape_of_a_figure_does_not_count_against_it() -> None:
    """"40%" and "40" are the same claim; "2/5" contributes both of its halves."""
    assert invented_figures('x = TextContent("40", "body")', "va por el 40%") == []
    assert invented_figures('x = TextContent("2/5", "body")', "2 de 5 nodos") == []


def test_a_deadline_invented_between_the_two_calls_never_reaches_the_browser() -> None:
    """The class of error that matters most here: a plazo that is not in the seed."""
    answer = "Aitana tiene el curso de Higiene asignado y no lo ha abierto."
    program = 'cuerpo = Callout("warn", "Aitana debe terminarlo antes del 15/08/2026")'
    assert invented_figures(program, answer) == ["08", "15", "2026"]


async def test_an_invented_figure_costs_the_blocks_and_never_the_answer(monkeypatch) -> None:
    """End to end: the reader keeps the prose the first call actually produced."""
    lying = json.dumps(
        {
            "shape": "table",
            "lead": "Asi van.",
            "headers": ["Empleado", "Avance"],
            # Nothing in LONG_ANSWER contains 60 or 99.
            "rows": [["Lucia", "60%"], ["Aitana", "99%"]],
        }
    )
    llm = _FakeLLM(LONG_ANSWER, layout=lying)
    events, repo = await _run(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert llm.completions == 1
    assert "ui" not in names
    assert "layout_skipped" in names
    assert "program" not in repo.messages[-1].message_metadata
    assert repo.messages[-1].content.strip().startswith("Los alergenos")


def test_a_reply_that_is_not_json_is_a_fallback_and_not_a_crash() -> None:
    for raw in ("", "lo siento", NO_UI_SENTINEL, "{roto", "[1, 2]"):
        assert emit_chat_program(parse_layout_json(raw)) is None


def test_a_fenced_object_is_still_read() -> None:
    """``json_mode`` is requested, but "mostly honoured" is not a contract."""
    assert parse_layout_json('```json\n{"shape": "prose"}\n```') == {"shape": "prose"}
    assert parse_layout_json('Aqui tienes:\n{"shape": "prose"}') == {"shape": "prose"}


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
    """Streams ``answer`` token by token, then returns ``layout`` from ``complete``.

    ``layout`` is now the *JSON* the classify+populate call returns, not a program.
    """

    def __init__(self, answer: str, layout: str = PROSE_PAYLOAD) -> None:
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
    llm = _FakeLLM(LONG_ANSWER, layout=STEPS_PAYLOAD)
    events, repo = await _run(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert names.index("done") < names.index("ui")
    assert names.index("layout_start") == names.index("done") + 1
    program = dict(events[names.index("ui")][1])["program"]
    assert "StepSequence" in program
    # Persisted for the next time the session is opened, canonical text only.
    assert repo.messages[-1].message_metadata["program"] == program


async def test_an_unusable_shape_degrades_to_the_prose(monkeypatch) -> None:
    ragged = json.dumps(
        {"shape": "table", "lead": "L", "headers": ["a", "b"], "rows": [["1"], ["2", "3"]]}
    )
    llm = _FakeLLM(LONG_ANSWER, layout=ragged)
    events, repo = await _run(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert "ui" not in names
    assert "layout_skipped" in names
    assert repo.messages[-1].content.strip().startswith("Los alergenos")
    assert "program" not in repo.messages[-1].message_metadata


async def test_a_model_that_answers_with_a_program_gets_the_prose(monkeypatch) -> None:
    """Belt and braces on the seam: the old output is not JSON, so it is simply refused.

    Worth asserting because a provider ignoring ``json_mode`` and reverting to its old
    habit must degrade, not half-work.
    """
    llm = _FakeLLM(LONG_ANSWER, layout=VALID_PROGRAM)
    events, _ = await _run(monkeypatch, llm, generative_ui=True)

    assert "ui" not in [name for name, _ in events]
    assert "layout_skipped" in [name for name, _ in events]


async def test_the_layout_call_asks_for_json_mode(monkeypatch) -> None:
    """Requested on the call, not just hoped for in the prompt."""
    seen: dict[str, object] = {}

    class _Recording(_FakeLLM):
        async def complete(self, _system, _user, **kwargs):
            seen.update(kwargs)
            return PROSE_PAYLOAD

    await _run(monkeypatch, _Recording(LONG_ANSWER), generative_ui=True)
    assert seen["json_mode"] is True


async def test_a_provider_failure_during_layout_degrades_to_the_prose(monkeypatch) -> None:
    llm = _FakeLLM(LONG_ANSWER, layout=RuntimeError("429 rate limit"))
    events, _ = await _run(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert "ui" not in names
    assert "error" not in names
    assert "done" in names


async def test_generative_ui_off_is_yesterdays_chat(monkeypatch) -> None:
    """With generative_ui off: no second call, no new events."""
    llm = _FakeLLM(LONG_ANSWER, layout=STEPS_PAYLOAD)
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
    generative_ui = chat_generative_ui_enabled(org_off)
    assert generative_ui is False

    off_llm = _FakeLLM(LONG_ANSWER, layout=STEPS_PAYLOAD)
    off_events, off_repo = await _run(monkeypatch, off_llm, generative_ui=generative_ui)

    # ...and the same turn where the model simply returned something unusable.
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


def test_the_admin_route_composes_the_switch_the_same_way_the_tutor_route_does() -> None:
    """Both routes must read the same org setting.

    Asserted against the source because both routes must keep using
    ``chat_generative_ui_enabled``.
    """
    source = inspect.getsource(chat_route.admin_chat)
    assert "chat_generative_ui_enabled(org_settings)" in source
    assert "generative_ui=generative_ui" in source


@pytest.mark.parametrize(
    ("org_settings", "expected"),
    [
        (None, True),
        ({}, True),
        ({"chat_generative_ui": True}, True),
        ({"chat_generative_ui": "si"}, True),  # malformed is not "off"
        ({"chat_generative_ui": False}, False),
    ],
)
def test_the_org_switch_controls_generative_ui(org_settings, expected) -> None:
    enabled = chat_generative_ui_enabled(org_settings)
    assert enabled is expected


async def test_a_short_answer_does_not_pay_for_a_second_call(monkeypatch) -> None:
    llm = _FakeLLM("Si, siempre.", layout=STEPS_PAYLOAD)
    events, _ = await _run(monkeypatch, llm, generative_ui=True)

    assert len("Si, siempre.") < MIN_LAYOUT_CHARS
    assert llm.completions == 0
    assert "ui" not in [name for name, _ in events]


async def _run_admin_layout(monkeypatch, llm, *, generative_ui: bool):
    async def fake_ground(*_args, **_kwargs):
        return GroundedContext("general")

    async def fake_build(*_args, **_kwargs):
        raise RuntimeError("no database in this test")

    monkeypatch.setattr(chat_module, "ground_question", fake_ground)
    monkeypatch.setattr(chat_module, "build_org_snapshot", fake_build)
    service = ChatService(
        _FakeDB(),  # type: ignore[arg-type]
        llm,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        generative_ui=generative_ui,
    )
    service.repo = _FakeRepo()  # type: ignore[assignment]
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    return _events(
        [
            event
            async for event in service.stream_admin(user, "como van mis empleados", None, None)
        ]
    )


async def test_the_admin_assistant_generates_its_blocks_in_the_first_call(
    monkeypatch,
) -> None:
    """A table of five employees is still the clearest case in the app; the *second call*
    that used to build it is gone.

    Rewritten for ``7a48fa5`` ("single-phase GenUI chat", 2026-08-03). Until then the admin
    streamed prose and a second LLM call classified it into a shape; now
    ``admin_genui_system_prompt`` teaches the dialect up front and the stream itself is the
    program. So the assertion that used to read ``completions == 1`` reads ``== 0``: the
    blocks arrive without a second round trip, which is the whole point of the change.
    """
    llm = _FakeLLM(ADMIN_PROGRAM)
    events = await _run_admin_layout(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert llm.completions == 0
    assert "layout_start" not in names  # there is no second phase to announce
    assert names.index("done") < names.index("ui")
    program = dict(events[names.index("ui")][1])["program"]
    assert "Table(" in program
    assert "Lucia Fernandez Vila" in program


async def test_the_admin_program_answers_to_the_same_two_switches(monkeypatch) -> None:
    """Single-phase did not give the admin its own way in.

    With the switch off the model is never asked for a dialect at all, so a stream that
    happens to contain one is not served: ``self.generative_ui`` is checked before the
    answer is even looked at.
    """
    llm = _FakeLLM(ADMIN_PROGRAM)
    events = await _run_admin_layout(monkeypatch, llm, generative_ui=False)

    assert llm.completions == 0
    assert "ui" not in [name for name, _ in events]
    assert "layout_start" not in [name for name, _ in events]


async def test_an_admin_answer_that_is_prose_is_served_as_prose(monkeypatch) -> None:
    """The degradation contract, minus the second call.

    Note what is *not* asserted any more: ``layout_skipped``. That event belonged to the
    two-phase path — it told the frontend "the call you saw start produced nothing". In
    single-phase there is no call to start, so an answer with no program in it is
    indistinguishable from an ordinary turn, which is exactly right.
    """
    llm = _FakeLLM(ADMIN_ANSWER)
    events = await _run_admin_layout(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert llm.completions == 0
    assert "ui" not in names
    assert "layout_start" not in names
    assert "layout_skipped" not in names
    assert "error" not in names
    assert names[-1] == "done"


async def test_an_admin_program_that_does_not_validate_degrades_to_the_prose(
    monkeypatch,
) -> None:
    """A stream that *attempts* the dialect and gets it wrong must not blank the bubble.

    ``root = Stack(`` is the cheap candidate check, so this reaches the validator and is
    refused by it — an undeclared id. What the reader keeps is the text that streamed.
    """
    broken = 'root = Stack([intro, tabla], "md")\nintro = TextContent("Asi va cada persona.", "lead")\n'
    llm = _FakeLLM(broken)
    events = await _run_admin_layout(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert validate_chat_program(broken) is None  # the seam this test depends on
    assert "ui" not in names
    assert "error" not in names
    assert names[-1] == "done"


async def test_a_sentence_in_front_of_the_program_costs_the_whole_program(
    monkeypatch,
) -> None:
    """Measured, because ``_extract_genui_program`` claimed the opposite.

    Its comment says the ``invented_figures`` guard is kept "in case the model emits prose
    before the program (which ``validate_chat_program`` strips)". It does not strip it:
    a leading sentence is a line the dialect cannot parse, so the *whole* answer is refused
    and served as prose. Which means that in single-phase the guard can never fire — the
    answer and the program are byte-identical by the time it runs — and the comment was
    corrected rather than the code: an inert floor is cheap, a floor described as
    load-bearing is not.

    The behaviour itself is the right one (a half-parsed program is not a program), and it
    is worth pinning because it is what makes ``invented_figures`` unreachable here. The
    tutor's two-phase path is where that guard still earns its keep.
    """
    prose_then_program = "Lucia va por el 72%.\n" + ADMIN_PROGRAM

    assert validate_chat_program(ADMIN_PROGRAM) is not None
    assert validate_chat_program(prose_then_program) is None
    # And with nothing stripped, the guard has nothing left to compare against.
    assert invented_figures(ADMIN_PROGRAM, ADMIN_PROGRAM) == []

    llm = _FakeLLM(prose_then_program)
    events = await _run_admin_layout(monkeypatch, llm, generative_ui=True)
    names = [name for name, _ in events]

    assert "ui" not in names
    assert "error" not in names
    assert names[-1] == "done"


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


# -- frontend tool calls (ACTION lines) ----------------------------------------

def test_extract_actions_parses_a_valid_action_line() -> None:
    text = (
        "Listo, cambio el idioma a ingles.\n"
        'ACTION: {"tool": "set_locale", "args": {"locale": "en"}}'
    )
    clean, actions = extract_actions(text)
    assert clean == "Listo, cambio el idioma a ingles."
    assert len(actions) == 1
    assert actions[0] == {"tool": "set_locale", "args": {"locale": "en"}}


def test_extract_actions_ignores_unknown_tools() -> None:
    text = 'ACTION: {"tool": "delete_everything", "args": {}}'
    clean, actions = extract_actions(text)
    assert actions == []
    assert clean == ""


def test_extract_actions_ignores_malformed_json() -> None:
    text = "ACTION: {not json}"
    clean, actions = extract_actions(text)
    assert actions == []
    assert clean == ""


def test_extract_actions_strips_the_line_even_when_invalid() -> None:
    """The ACTION prefix is always stripped from visible text, valid or not."""
    text = "Hola.\nACTION: {invalid}\nAdios."
    clean, actions = extract_actions(text)
    assert "ACTION" not in clean
    assert actions == []


def test_extract_actions_handles_no_action_lines() -> None:
    text = "Los alergenos son catorce sustancias de declaracion obligatoria."
    clean, actions = extract_actions(text)
    assert clean == text
    assert actions == []


def test_extract_actions_requires_args_to_be_a_dict() -> None:
    text = 'ACTION: {"tool": "set_locale", "args": "es"}'
    _, actions = extract_actions(text)
    assert actions == []


def test_extract_actions_allows_all_registered_tools() -> None:
    """Every tool in ``ALLOWED_TOOLS`` is accepted."""
    for tool_name in ALLOWED_TOOLS:
        text = f'ACTION: {{"tool": "{tool_name}", "args": {{}}}}'
        _, actions = extract_actions(text)
        assert len(actions) == 1
        assert actions[0]["tool"] == tool_name


def test_action_inside_prose_is_not_matched() -> None:
    """The word ACTION inside a sentence is not a tool call."""
    text = "El ACTION de este paso es importante para la seguridad alimentaria."
    clean, actions = extract_actions(text)
    assert actions == []
    assert clean == text


async def test_action_events_are_emitted_after_done(monkeypatch) -> None:
    """End to end: the model emits an ACTION line and the stream delivers it."""
    answer_with_action = (
        "Listo, cambio el idioma a ingles.\n"
        'ACTION: {"tool": "set_locale", "args": {"locale": "en"}}'
    )
    llm = _FakeLLM(answer_with_action)
    events, repo = await _run(monkeypatch, llm, generative_ui=False)
    names = [name for name, _ in events]

    assert "action" in names
    action_idx = names.index("action")
    done_idx = names.index("done")
    assert action_idx > done_idx

    action_data = events[action_idx][1]
    assert action_data["tool"] == "set_locale"
    assert action_data["args"] == {"locale": "en"}

    # The ACTION line is stripped from the persisted content.
    stored = repo.messages[-1].content
    assert "ACTION" not in stored
    assert "Listo, cambio el idioma a ingles." in stored


async def test_sidebar_action_is_not_streamed_as_visible_text(monkeypatch) -> None:
    """Regression: LessonBuddy receives prose tokens and the actionable SSE event only."""
    answer_with_action = (
        "He ocultado la barra lateral.\n"
        'ACTION: {"tool":"set_sidebar_collapsed","args":{"collapsed":true}}'
    )
    llm = _FakeLLM(answer_with_action)
    events, _ = await _run(monkeypatch, llm, generative_ui=False)

    visible = "".join(data["content"] for name, data in events if name == "token")
    assert visible == "He ocultado la barra lateral.\n"
    assert "ACTION:" not in visible
    assert (
        "action",
        {"tool": "set_sidebar_collapsed", "args": {"collapsed": True}},
    ) in events


async def test_no_action_events_when_answer_has_none(monkeypatch) -> None:
    llm = _FakeLLM("Los alergenos son catorce sustancias.")
    events, _ = await _run(monkeypatch, llm, generative_ui=False)
    names = [name for name, _ in events]
    assert "action" not in names
