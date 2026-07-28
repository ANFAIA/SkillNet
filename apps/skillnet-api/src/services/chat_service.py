"""Tutor chat: grounded answers + conversational memory + SSE streaming + generative UI.

No LangGraph, no tools. Each turn: load/create the session, persist the user message,
**ground** the question (``src/services/retrieval.py``), build a prompt (persona + last N
turns as memory + a final turn embedding the context), stream tokens as SSE events, then
persist the assistant message with its citations.

Two things changed on 2026-07-27, and the order matters because the second is worthless
without the first.

**1. The tutor answers.** It used to be told to reply, literally, *"No tengo informacion
sobre esto en los documentos disponibles."* whenever RAG came back empty — and in the
demo organization RAG comes back empty for every question, because the seeded documents
are small enough to have ``full_text`` and no ``document_chunks`` at all. The retrieval
layer now walks a ladder (chunks -> the whole enrolled document -> general knowledge) and
this service labels the answer with which rung it stood on. The label is an SSE event and
a persisted field, not a sentence the model was asked to write: honesty about the source
is a property of the system, not a request to the model.

**2. Generative UI.** After the prose has finished streaming, a second call re-lays the
same answer in the frozen SkillNet kit, which the browser paints with the same
``UiSpecRenderer`` a node render uses. Since 2026-07-28 that call does **not** ask the
model for a program: it asks for one JSON object naming a shape out of five and filling
that shape's fields, and ``emit_chat_program`` below writes the OpenUI Lang. The reason is
measured and lives in :data:`src.llm.prompts.tutor.CHAT_SHAPES` — every validator
rejection in this repository's own render bench was a markup-authoring error, not a
judgement error, so the model kept the judgement and lost the typewriter. Three properties
are load-bearing:

* **The prose is untouched.** The layout call happens *after* ``done``, so the first token
  arrives exactly as fast as it did before, the input re-enables at exactly the same
  moment, and a chat that fails to lay out is a chat that behaves like yesterday's.
  Streaming the program instead would have meant showing the learner either a spinner or
  raw dialect until the last token — a slower, worse chat, for a nicer end state.
* **It goes through the same gate.** ``gate.canonicalize`` parses the model's bytes into a
  ``UISpec`` and the browser is served the **re-serialization**, never the model's own
  text. A free-text question is a *less* trusted input than a node prompt, so it gets no
  weaker a gate. ``QuizItem`` is rejected outright here: there is no node, no render row
  and no ``answer_key`` in a chat, so a gradeable item could only ever be a broken one.
* **It degrades to the prose.** Every failure — the model refusing, an invalid program, a
  provider 429 — ends with no ``ui`` event and the answer the learner already read. The
  one thing that never happens is a blank bubble.

**3. The admin assistant stopped being a copy of the tutor** (2026-07-28). It used to walk
the same document ladder and nothing else, so asked *"como van mis empleados"* it answered
with four bullets of management advice while five employees, their enrolments and their
mastery sat in the database it is the administration console for. Two changes, both on the
``admin`` path only:

* ``_org_snapshot`` assembles the organization's training data server-side and pastes it
  into the turn the way a document already is. Deterministic, ``org_id``-scoped, and it
  carries no field of the private learner profile — see ``src/services/org_snapshot.py``,
  which is where the privacy line is drawn and tested.
* A greeting never reaches the model: ``src/services/small_talk.py`` answers it. *"que
  tal"* used to be met with *"No tengo suficiente informacion"*, which is what a model
  correctly says when it is handed an allergen manual and a pleasantry. *"quien eres"*
  joined it on 2026-07-28, for the same reason one rung up: the assistant is the one thing
  in the turn that is not in the snapshot, so looking for it there can only end in "no
  consta".

**4. The admin assistant lays out too** (2026-07-28). It was excluded from the layout call
on the grounds that a wall of blocks is slower to act on than a sentence; ``MIN_LAYOUT_CHARS``
already enforces that on its own, and the exclusion was costing the clearest case of
generative UI in the product — *"como van mis empleados"* is five people, four columns and
a deadline. Same two switches, same silent fall back to the prose, plus one rule the tutor
does not need: ``invented_figures`` refuses any program carrying a number the answer did
not, because these blocks describe named people's training records.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError, NotFoundError
from src.core.logging import get_logger
from src.core.sse import format_sse
from src.llm.client import LLMService
from src.llm.embedding import EmbeddingService
from src.llm.prompts.admin import (
    ADMIN_PROMPT_VERSION,
    admin_system_prompt,
    build_admin_turn,
)
from src.llm.prompts.tutor import (
    CHAT_LAYOUT_SYSTEM,
    CHAT_SHAPES,
    MAX_DEFINITION_POINTS,
    MAX_STEPS,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_ROWS,
    NO_UI_SENTINEL,
    TUTOR_PROMPT_VERSION,
    Grounding,
    build_chat_layout_prompt,
    build_user_turn,
    tutor_system_prompt,
)
from src.models import ChatMessage, ChatSession, User
from src.render.errors import RenderError
from src.render.gate import canonicalize
from src.render.prompt import catalog_version
from src.repositories.chat_repo import ChatRepository
from src.services.org_snapshot import build_org_snapshot, render_snapshot
from src.services.retrieval import GroundedContext, ground_question
from src.services.small_talk import small_talk_reply

logger = get_logger(__name__)

MEMORY_TURNS = 8
TITLE_MAX_CHARS = 40
RETRIEVAL_TOP_K = 5

#: A canned answer is not streamed by a provider, so it has no natural chunking. Emitted a
#: few words at a time rather than in one event, purely so the bubble fills the way every
#: other bubble does — a greeting that appears instantly while every real answer types
#: itself out reads like two different products.
CANNED_CHUNK_WORDS = 6

#: Below this many characters an answer is one idea, and a ``Stack`` around one idea is
#: worse than the paragraph it replaces. Also the cheap half of the rate-limit story: the
#: short answers are the frequent ones, and skipping them skips most of the second calls.
MIN_LAYOUT_CHARS = 220

#: The layout call is a reformatting job, not a writing one. Low temperature, and a budget
#: a six-block program fits into twice over.
LAYOUT_TEMPERATURE = 0.2
LAYOUT_MAX_TOKENS = 1_200

#: Chat programs are always ``explanation``: there is no exercise in a chat (rule Chat 2),
#: and ``explanation`` is the format whose contract rule 7 demands the lead line, which is
#: exactly the one-sentence answer the persona already asks for.
CHAT_UI_FORMAT = "explanation"

#: ``[Fuente 3]`` and friends, with the space in front they usually come with.
#:
#: Rule Chat 6 already tells the model not to copy the citation markers of the answer it
#: is laying out, and measured against ``groq/llama-3.1-8b-instant`` on the very first
#: live run it copied one anyway, into the lead block. The citations are printed under the
#: bubble by the frontend, so the marker is a duplicate pointing at a numbering the blocks
#: do not have. Stripped from the **raw** text, before the gate: whatever is left still
#: goes through the whole parse -> validate -> re-serialize path, so this cannot become a
#: way to smuggle text past it.
_CITATION_MARKER_RE = re.compile(r"[ \t]*\[Fuente\s+\d+\]")


def _context_document_ids(context: dict | None) -> list[uuid.UUID] | None:
    """Best-effort restriction to specific documents from the request context."""
    if not context:
        return None
    raw = context.get("document_ids")
    if not isinstance(raw, list) or not raw:
        return None
    ids: list[uuid.UUID] = []
    for value in raw:
        try:
            ids.append(value if isinstance(value, uuid.UUID) else uuid.UUID(str(value)))
        except (ValueError, TypeError):
            continue
    return ids or None


def _context_course_id(context: dict | None) -> uuid.UUID | None:
    if not context:
        return None
    raw = context.get("course_id")
    if raw is None:
        return None
    try:
        return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None


def _canned_chunks(text: str, words: int = CANNED_CHUNK_WORDS) -> list[str]:
    """A canned answer cut into token-sized pieces that reassemble to it exactly.

    ``"".join(_canned_chunks(t)) == t`` is the whole contract: the persisted message and
    the bubble have to be the same string, and a chunker that drops a space is a chunker
    that makes them differ by the time anyone notices.
    """
    pieces = text.split(" ")
    return [
        " ".join(pieces[i : i + words]) + (" " if i + words < len(pieces) else "")
        for i in range(0, len(pieces), words)
    ]


def strip_no_ui(raw: str) -> str:
    """The model's layout answer with the ``NO_UI`` verdict removed.

    Returns ``""`` when the model declined, which is a first-class outcome and not a
    failure: rule Chat 3 asks for exactly that on an answer with no shape. Tolerant of the
    model wrapping the sentinel in a fence or ending it with a full stop, because it does.
    """
    text = raw.strip().strip("`").strip()
    if not text:
        return ""
    head = text.split("\n", 1)[0].strip().rstrip(".").upper()
    if head == NO_UI_SENTINEL or text.upper().startswith(NO_UI_SENTINEL):
        return ""
    return text


# --------------------------------------------------------------------------------------
# classify + populate: the model's JSON -> a program the *server* wrote
#
# The model no longer authors OpenUI Lang here. See :data:`src.llm.prompts.tutor
# .CHAT_SHAPES` for the measurement that motivated it; what follows is the half that makes
# the measurement moot. Every rejection class in that bench — named arguments, an accent
# in a bare identifier, ``{`` for an object, twice the line cap — is a property of text
# *this module* now writes, so none of them can be produced by anything the model says.
#
# The output still goes through ``validate_chat_program`` unchanged. That is not belt and
# braces for its own sake: the strings inside the program are still the model's bytes, and
# the rule that only a re-serialized ``UISpec`` reaches the browser has to hold for text
# the server assembled exactly as it holds for text the model typed.
# --------------------------------------------------------------------------------------

#: Anything below this is not a shape, it is a fragment. A one-step "procedure" and a
#: one-row "table" are both the paragraph they came from, wearing a border.
MIN_SHAPE_ITEMS = 2

_CALLOUT_TONES = ("info", "warn", "success")


def _scalar(value: object) -> str | None:
    """``value`` as one line of printable text; ``None`` when it is not a scalar at all.

    The distinction from :func:`_one_line` is the whole reason both exist. ``""`` is a
    *legitimately empty* field — a table cell for a person with no deadline — while
    ``None`` means the model put a dict, a list or a boolean where text belongs, which is
    a shape it did not populate rather than a field it left blank. Collapsing the two
    would turn ``rows: [[{"a": 1}]]`` into a table of empty cells: a block that renders,
    says nothing, and looks like the data is missing rather than like the layout failed.

    A number is scalar and is kept: asked for a cell, a model writes ``40`` as often as
    ``"40"``, and refusing that would throw away a good table over JSON typing.

    A dialect string literal closes its quote on the line that opened it (SkillNet rule 1),
    so every newline the model puts in a field collapses to a space here rather than
    becoming an unterminated value the gate would reject.
    """
    if isinstance(value, str):
        text = value
    elif isinstance(value, bool) or not isinstance(value, int | float):
        # ``bool`` first: it is an ``int`` subclass, and "True" is not a figure.
        return None
    else:
        text = str(value)
    collapsed = " ".join(part for part in text.split() if part)
    return "".join(char for char in collapsed if char.isprintable()).strip()


def _one_line(value: object) -> str | None:
    """``_scalar``, with "blank" folded into "absent". For fields that must carry text."""
    return _scalar(value) or None


def _literal(text: str) -> str:
    """A dialect string literal. Same escapes as ``OpenUiLangBackend.serialize``.

    Only two of that function's three rules are needed, because ``_one_line`` has already
    removed every newline; the backslash must still be escaped before the quote, and in
    that order, or a trailing ``\\`` swallows the closing quote.
    """
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _string_list(value: object, *, minimum: int, maximum: int) -> list[str] | None:
    """A list of non-empty lines, or ``None``.

    Strict about every item rather than filtering: a step the model wrote as an object is
    a step, and dropping it quietly would serve a four-step procedure as three — a wrong
    answer that looks like a right one. Prose is the better outcome.
    """
    if not isinstance(value, list):
        return None
    items: list[str] = []
    for item in value:
        line = _one_line(item)
        if line is None:
            return None
        items.append(line)
    if not minimum <= len(items) <= maximum:
        return None
    return items


def _emit_body(shape: str, payload: dict) -> list[str] | None:
    """The declarations for the body block, ``cuerpo`` last-but-not-least.

    ``None`` whenever the populated fields do not make the shape the model claimed. The
    only thing forgiven is JSON typing — a number where a string was asked for — because
    that is a habit, not a mistake. Anything that changes what the block *says* is refused
    outright: a "table" whose rows are ragged is a model that misread its own answer, and
    prose is a better outcome than a table with a hole in it.
    """
    match shape:
        case "steps":
            title = _one_line(payload.get("title"))
            steps = _string_list(
                payload.get("steps"), minimum=MIN_SHAPE_ITEMS, maximum=MAX_STEPS
            )
            if title is None or steps is None:
                return None
            rendered = ", ".join(_literal(step) for step in steps)
            return [f"cuerpo = StepSequence({_literal(title)}, [{rendered}])"]

        case "table":
            headers = _string_list(
                payload.get("headers"),
                minimum=MIN_SHAPE_ITEMS,
                maximum=MAX_TABLE_COLUMNS,
            )
            raw_rows = payload.get("rows")
            if headers is None or not isinstance(raw_rows, list):
                return None
            rows: list[list[str]] = []
            for raw_row in raw_rows:
                # A cell may legitimately be empty ("sin plazo"), so cells are kept
                # positionally and only the *width* has to match. Dropping empties would
                # silently shift every value in the row one column to the left. A cell
                # that is not a scalar at all is a different matter and kills the table.
                if not isinstance(raw_row, list) or len(raw_row) != len(headers):
                    return None
                cells: list[str] = []
                for cell in raw_row:
                    text = _scalar(cell)
                    if text is None:
                        return None
                    cells.append(text)
                rows.append(cells)
            if not MIN_SHAPE_ITEMS <= len(rows) <= MAX_TABLE_ROWS:
                return None
            head = ", ".join(_literal(header) for header in headers)
            body = ", ".join(
                "[" + ", ".join(_literal(cell) for cell in row) + "]" for row in rows
            )
            return [f"cuerpo = Table([{head}], [{body}])"]

        case "callout":
            text = _one_line(payload.get("text"))
            if text is None:
                return None
            tone = payload.get("tone")
            # An unknown tone is a colour, not a claim: "info" is the neutral one and
            # losing a shade is not worth losing the block.
            tone = tone if tone in _CALLOUT_TONES else "info"
            return [f"cuerpo = Callout({_literal(tone)}, {_literal(text)})"]

        case "definition":
            title = _one_line(payload.get("title"))
            raw_points = payload.get("points")
            if title is None or not isinstance(raw_points, list):
                return None
            points: list[str] = []
            for raw_point in raw_points:
                if not isinstance(raw_point, dict):
                    return None
                term = _one_line(raw_point.get("term"))
                detail = _one_line(raw_point.get("detail"))
                if term is None or detail is None:
                    return None
                points.append(f"{term}: {detail}")
            if not MIN_SHAPE_ITEMS <= len(points) <= MAX_DEFINITION_POINTS:
                return None
            ids = [f"punto{index}" for index in range(1, len(points) + 1)]
            lines = [f"cuerpo = Card({_literal(title)}, [{', '.join(ids)}])"]
            lines.extend(
                f"{point_id} = TextContent({_literal(point)}, \"body\")"
                for point_id, point in zip(ids, points, strict=True)
            )
            return lines

    return None


def emit_chat_program(payload: object) -> str | None:
    """The model's populated shape -> program text, or ``None`` for "serve the prose".

    ``None`` is the answer to every doubt: an unknown shape, a missing field, a ragged
    table, and the explicit ``"prose"`` verdict all leave the reader with the answer they
    already read. Same contract ``NO_UI`` had, minus the model's ability to misspell it.
    """
    if not isinstance(payload, dict):
        return None
    shape = payload.get("shape")
    if not isinstance(shape, str) or shape not in CHAT_SHAPES or shape == "prose":
        return None

    body = _emit_body(shape, payload)
    if body is None:
        return None

    lead = _one_line(payload.get("lead"))
    if lead is None:
        # Contract rule 7: the first child of the root has to be a lead TextContent or a
        # Callout. A Callout body can stand in for itself; nothing else can, and inventing
        # a lead line would be this module writing content, which is the one thing it must
        # never do.
        if shape != "callout":
            return None
        return "root = Stack([cuerpo], \"md\")\n" + "\n".join(body) + "\n"
    return (
        'root = Stack([entrada, cuerpo], "md")\n'
        f'entrada = TextContent({_literal(lead)}, "lead")\n' + "\n".join(body) + "\n"
    )


#: Any run of digits. Deliberately not a number parser: "40", "2026", "1169" and the "5"
#: in "2/5" are all figures a reader would hold the platform to, and the question asked of
#: them is only ever "was this already on screen?".
_DIGIT_RUN = re.compile(r"\d+")


def invented_figures(program: str, answer: str) -> list[str]:
    """Digit runs the layout step put on screen that the answer never contained.

    The layout call is forbidden to add information, and for an administrator reading
    other people's training records that rule is worth more than the blocks: a table that
    says a person is at 60% when the prose said 40% is a record an employer might act on.
    The prompt asks; this is what makes it true. Every figure in a program the server
    emitted came out of a model-supplied string, so anything here that is not already in
    the prose was invented between the two calls.

    Comparing digit runs rather than parsed numbers is what keeps it honest about
    formatting: "40%" and "40" agree, and "2/5" contributes both of its halves. It also
    means "catorce" in the prose does not license "14" in the table — which is the safe
    direction to be wrong in, because the cost is the paragraph the reader already has.
    """
    known = set(_DIGIT_RUN.findall(answer))
    return sorted({run for run in _DIGIT_RUN.findall(program) if run not in known})


def parse_layout_json(raw: str) -> object | None:
    """The model's reply as a JSON value, or ``None``.

    ``json_mode`` is requested on the call, and providers honour it well enough that this
    is mostly a formality — but "mostly" is not a contract, and a fenced or prefaced object
    is the failure they actually produce, so the outermost braces are located rather than
    trusted to be the whole string.
    """
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except ValueError:
        logger.info("Chat layout returned something that is not JSON")
        return None


def validate_chat_program(raw: str) -> str | None:
    """Program text -> the canonical program the browser may receive.

    Since the chat moved to classify+populate the input is text ``emit_chat_program``
    wrote, not text a model wrote — but the *strings inside it* are still the model's, and
    the rule that only a re-serialized ``UISpec`` reaches the browser has to hold for both.
    So this stayed exactly where it was, and the emitter is an extra floor under it rather
    than a replacement for it.

    ``None`` for anything that does not hold, and the caller's answer to ``None`` is
    always "serve the prose". There is no repair loop here on purpose: the node runtime
    can spend a second call because a failed render leaves the learner with nothing, while
    a failed layout leaves them with the answer they already read. Paying tokens to
    prettify a message the learner has finished reading is the wrong trade.
    """
    program = _CITATION_MARKER_RE.sub("", strip_no_ui(raw))
    if not program:
        return None
    try:
        spec, canonical = canonicalize(program, ui_format=CHAT_UI_FORMAT)
    except RenderError as exc:
        problems = list(getattr(exc, "errors", None) or [str(exc)])
        logger.info("Chat layout rejected: %s", "; ".join(problems))
        return None
    if "QuizItem" in spec.types:
        # Rule Chat 2. A QuizItem needs a node, a render row and an answer_key to grade
        # against, and a chat turn has none of the three: the block would render an item
        # nobody can answer. Caught here rather than trusted to the prompt.
        logger.info("Chat layout rejected: it contains a QuizItem")
        return None
    return canonical


class ChatService:
    def __init__(
        self,
        db: AsyncSession,
        tutor_llm: LLMService | None = None,
        embeddings: EmbeddingService | None = None,
        *,
        generative_ui: bool = False,
    ) -> None:
        self.db = db
        self.tutor_llm = tutor_llm
        self.embeddings = embeddings
        #: Decided by the route, never read from ``settings`` here: one flag consulted in
        #: ten places is ten flags (``src/services/course_delivery.py``). It is the AND of
        #: the deployment's ``DYNAMIC_COURSES_MODE`` and the admin's own
        #: ``chat_generative_ui``; ``False`` short-circuits **before** the model, because
        #: the point of the admin's switch is not paying for the second call.
        self.generative_ui = generative_ui
        self.repo = ChatRepository(db)

    async def stream_tutor(
        self,
        user: User,
        message: str,
        session_id: uuid.UUID | None,
        context: dict | None,
    ) -> AsyncIterator[str]:
        async for event in self._stream(
            user,
            message,
            session_id,
            context,
            agent_type="tutor",
            whole_documents="enrolled",
        ):
            yield event

    async def stream_admin(
        self,
        user: User,
        message: str,
        session_id: uuid.UUID | None,
        context: dict | None,
    ) -> AsyncIterator[str]:
        """The admin assistant. Same stream as the tutor, two things more.

        It is handed the **organization's own data** (``src/services/org_snapshot.py``)
        alongside whatever the document ladder found, because "como van mis empleados" is
        an admin's first question and the answer is a query, not a paragraph of the
        allergen manual. And a greeting is answered here rather than by the model: see
        ``src/services/small_talk.py`` for why that is a fix and not a shortcut.
        """
        async for event in self._stream(
            user,
            message,
            session_id,
            context,
            agent_type="admin",
            whole_documents="org",
            canned=small_talk_reply(message),
        ):
            yield event

    async def _stream(
        self,
        user: User,
        message: str,
        session_id: uuid.UUID | None,
        context: dict | None,
        *,
        agent_type: str,
        whole_documents: str,
        canned: str | None = None,
    ) -> AsyncIterator[str]:
        grounded = GroundedContext("general")
        parts: list[str] = []
        session: ChatSession | None = None
        snapshot_block = ""
        if self.tutor_llm is None or self.embeddings is None:
            yield format_sse("error", {"detail": "Chat services are not configured."})
            return
        try:
            session = await self._load_or_create_session(
                user, message, session_id, context, agent_type=agent_type
            )

            # Fetch prior turns for memory BEFORE persisting the current message.
            history = await self.repo.recent_messages(session.id, MEMORY_TURNS)

            await self.repo.add_message(
                session_id=session.id, role="user", content=message
            )
            await self.db.commit()

            org_data: dict | None = None
            if canned is None:
                grounded = await ground_question(
                    self.db,
                    user_id=user.id,
                    org_id=user.org_id,
                    embedding_service=self.embeddings,
                    query=message,
                    top_k=RETRIEVAL_TOP_K,
                    document_ids=_context_document_ids(context),
                    whole_documents=whole_documents,
                )
                if agent_type == "admin":
                    snapshot_block, org_data = await self._org_snapshot(user)

            # Announced before the first token, so the bubble carries its provenance from
            # the moment it starts filling rather than growing a label at the end.
            # ``grounding`` describes the *documents*; ``org_data`` is a separate axis,
            # because an answer can be grounded on the platform's data and on no document
            # at all, and collapsing the two would make the label lie in one direction or
            # the other.
            yield format_sse("grounding", {"grounding": grounded.grounding})
            if org_data is not None:
                yield format_sse("org_data", org_data)

            if canned is not None:
                for piece in _canned_chunks(canned):
                    parts.append(piece)
                    yield format_sse("token", {"content": piece})
            else:
                messages = self._build_messages(
                    history, grounded, message, agent_type, snapshot_block
                )
                async for piece in self.tutor_llm.stream(messages):
                    parts.append(piece)
                    yield format_sse("token", {"content": piece})

            answer = "".join(parts)
            yield format_sse("citations", {"citations": grounded.citations})

            assistant = await self.repo.add_message(
                session_id=session.id,
                role="assistant",
                content=answer,
                metadata={
                    "citations": grounded.citations,
                    "grounding": grounded.grounding,
                    "prompt_version": (
                        ADMIN_PROMPT_VERSION
                        if agent_type == "admin"
                        else TUTOR_PROMPT_VERSION
                    ),
                    **({"org_data": org_data} if org_data is not None else {}),
                    **({"small_talk": True} if canned is not None else {}),
                },
            )
            await self.db.commit()
            # ``done`` goes out BEFORE the layout call. The turn is over as far as the
            # learner is concerned: the answer is complete and the input re-enables. The
            # optional program arrives later on the same open stream, if it validates.
            yield format_sse("done", {"message_id": str(assistant.id)})

            if self._should_lay_out(agent_type, answer, canned=canned is not None):
                yield format_sse("layout_start", {})
                program = await self._lay_out(message, answer)
                if program:
                    await self._persist_program(assistant, program)
                    yield format_sse("ui", {"program": program, "format": CHAT_UI_FORMAT})
                else:
                    yield format_sse("layout_skipped", {})

        except Exception as exc:  # noqa: BLE001 - stream must always terminate cleanly
            detail = exc.message if isinstance(exc, AppError) else str(exc)
            logger.error("Tutor chat failed: %s", exc, exc_info=True)
            await self._persist_partial(session, parts, grounded)
            yield format_sse("error", {"detail": detail})

    # -- the organization's own data ----------------------------------------------

    async def _org_snapshot(self, user: User) -> tuple[str, dict | None]:
        """``(the block for the prompt, the summary for the browser)``.

        Scoped to ``user.org_id`` and to nothing else: the admin assistant must be
        incapable of reading another organization's rows, and "there is only one
        organization today" is a fact about the data, not a property of the code.

        A failure here costs the data and never the answer. Eight aggregate queries is
        eight chances to hit a lock, a migration mid-flight or a column that moved, and
        the right behaviour for all of them is the assistant this surface had yesterday:
        documents only. It is logged at ``warning`` because a snapshot that quietly stops
        being assembled looks exactly like a model that has gone vague.
        """
        org_id = getattr(user, "org_id", None)
        if org_id is None:
            return "", None
        try:
            snapshot = await build_org_snapshot(self.db, org_id=org_id)
            block = render_snapshot(snapshot)
        except Exception as exc:  # noqa: BLE001 - the answer survives a missing snapshot
            logger.warning("Could not assemble the org snapshot: %s", exc, exc_info=True)
            return "", None
        if not block:
            return "", None
        return block, {
            "employees": snapshot.employees_total,
            "courses": len(snapshot.courses),
            "documents": snapshot.documents_total,
            "generated_at": snapshot.generated_at.isoformat(),
        }

    # -- the layout call ---------------------------------------------------------

    def _should_lay_out(self, agent_type: str, answer: str, *, canned: bool) -> bool:
        """Whether this answer earns a second call.

        A canned answer never does, and that check is worth more than it looks. The point
        of ``src/services/small_talk.py`` is that "hola" and "quien eres" cost **zero**
        tokens; the identity reply is long enough to clear ``MIN_LAYOUT_CHARS``, so the
        moment the admin path started laying out, a question that deliberately never
        reaches a provider started paying for a call to one. Measured live before this
        line existed: ``quien eres`` emitted ``layout_start``.

        The admin assistant used to be excluded, on the grounds that it answers in two
        lines and a wall of blocks would be slower to act on than a sentence. The first
        half is enforced by ``MIN_LAYOUT_CHARS`` on its own, and the second half turned
        out to be wrong in the one case that matters: *"como van mis empleados"* is five
        people, four columns and a deadline, which is a table in every other tool an
        administrator uses. So it is in, behind exactly the same two switches, with
        exactly the same fall back to the prose it already streamed.
        """
        return (
            self.generative_ui
            and not canned
            and agent_type in ("tutor", "admin")
            and self.tutor_llm is not None
            and len(answer.strip()) >= MIN_LAYOUT_CHARS
        )

    async def _lay_out(self, question: str, answer: str) -> str | None:
        """Re-lay ``answer`` in the kit. ``None`` means "serve the prose", always.

        The model classifies and populates; **this process writes the program**. See
        ``emit_chat_program`` above and :data:`src.llm.prompts.tutor.CHAT_SHAPES` for why.
        """
        try:
            raw = await self.tutor_llm.complete(  # type: ignore[union-attr]
                CHAT_LAYOUT_SYSTEM,
                build_chat_layout_prompt(question, answer),
                temperature=LAYOUT_TEMPERATURE,
                max_tokens=LAYOUT_MAX_TOKENS,
                json_mode=True,
            )
        except Exception as exc:  # noqa: BLE001 - the prose is already on screen
            logger.info("Chat layout call failed, serving prose: %s", exc)
            return None
        program = emit_chat_program(parse_layout_json(raw))
        if program is None:
            return None
        invented = invented_figures(program, answer)
        if invented:
            logger.info(
                "Chat layout rejected: figures not in the answer: %s", ", ".join(invented)
            )
            return None
        return validate_chat_program(program)

    async def _persist_program(self, assistant: ChatMessage, program: str) -> None:
        """Store the canonical program so reopening the session repaints the blocks.

        Only ever the **canonical** text, exactly as ``node_renders.dialect`` holds it, and
        for the same reason: this column is read straight into a renderer.
        """
        try:
            assistant.message_metadata = {
                **(assistant.message_metadata or {}),
                "program": program,
                "ui_format": CHAT_UI_FORMAT,
                "catalog_version": catalog_version(),
            }
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001 - the event was already sent
            logger.warning("Could not persist the chat program: %s", exc)
            await self.db.rollback()

    # -- session plumbing --------------------------------------------------------

    async def _load_or_create_session(
        self,
        user: User,
        message: str,
        session_id: uuid.UUID | None,
        context: dict | None,
        *,
        agent_type: str,
    ) -> ChatSession:
        if session_id is not None:
            session = await self.repo.get_owned_session(session_id, user.id)
            if session is None:
                raise NotFoundError("chat_sessions", str(session_id))
            return session
        title = message.strip()[:TITLE_MAX_CHARS] or None
        return await self.repo.create_session(
            user_id=user.id,
            org_id=user.org_id,
            title=title,
            agent_type=agent_type,
            course_id=_context_course_id(context),
        )

    def _build_messages(
        self,
        history: Sequence[ChatMessage],
        grounded: GroundedContext,
        question: str,
        agent_type: str,
        snapshot_block: str = "",
    ) -> list[dict[str, str]]:
        """Persona, the last N turns, and one final turn carrying everything found.

        The snapshot is pasted into the **current** turn and never into the history, so a
        long admin session does not accumulate five stale copies of the payroll and the
        model never has two contradictory versions of a number in front of it. Yesterday's
        counts are worse than none.
        """
        grounding: Grounding = grounded.grounding
        is_admin = agent_type == "admin"
        system = (
            admin_system_prompt(grounding, org_data=bool(snapshot_block))
            if is_admin
            else tutor_system_prompt(grounding)
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for msg in history:
            if msg.role in ("user", "assistant"):
                messages.append({"role": msg.role, "content": msg.content})
        turn = (
            build_admin_turn(grounding, grounded.context, snapshot_block, question)
            if is_admin
            else build_user_turn(grounding, grounded.context, question)
        )
        messages.append({"role": "user", "content": turn})
        return messages

    async def _persist_partial(
        self,
        session: ChatSession | None,
        parts: list[str],
        grounded: GroundedContext,
    ) -> None:
        if session is None or not parts:
            return
        try:
            await self.db.rollback()
            await self.repo.add_message(
                session_id=session.id,
                role="assistant",
                content="".join(parts),
                metadata={
                    "citations": grounded.citations,
                    "grounding": grounded.grounding,
                    "partial": True,
                },
            )
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not persist partial assistant message: %s", exc)

    async def list_sessions(self, user: User) -> Sequence[ChatSession]:
        return await self.repo.list_sessions(user.id)

    async def get_messages(
        self, user: User, session_id: uuid.UUID
    ) -> Sequence[ChatMessage]:
        session = await self.repo.get_owned_session(session_id, user.id)
        if session is None:
            raise NotFoundError("chat_sessions", str(session_id))
        return await self.repo.list_messages(session_id)


__all__ = [
    "CANNED_CHUNK_WORDS",
    "CHAT_UI_FORMAT",
    "MEMORY_TURNS",
    "MIN_LAYOUT_CHARS",
    "MIN_SHAPE_ITEMS",
    "RETRIEVAL_TOP_K",
    "ChatService",
    "emit_chat_program",
    "invented_figures",
    "parse_layout_json",
    "strip_no_ui",
    "validate_chat_program",
]
