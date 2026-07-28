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
same answer as a program in the frozen SkillNet kit, which the browser paints with the
same ``UiSpecRenderer`` a node render uses. Three properties are load-bearing:

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
  correctly says when it is handed an allergen manual and a pleasantry.
"""

from __future__ import annotations

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
    NO_UI_SENTINEL,
    TUTOR_PROMPT_VERSION,
    Grounding,
    build_chat_ui_prompt,
    build_user_turn,
    chat_ui_system,
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


def validate_chat_program(raw: str) -> str | None:
    """Untrusted layout output -> the canonical program the browser may receive.

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

            if self._should_lay_out(agent_type, answer):
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

    def _should_lay_out(self, agent_type: str, answer: str) -> bool:
        """Whether this answer earns a second call.

        The admin assistant is excluded: it answers operational questions in two lines,
        and its surface is the one place in the product where a wall of blocks would be
        slower to act on than a sentence.
        """
        return (
            self.generative_ui
            and agent_type == "tutor"
            and self.tutor_llm is not None
            and len(answer.strip()) >= MIN_LAYOUT_CHARS
        )

    async def _lay_out(self, question: str, answer: str) -> str | None:
        """Re-lay ``answer`` in the kit. ``None`` means "serve the prose", always."""
        try:
            raw = await self.tutor_llm.complete(  # type: ignore[union-attr]
                chat_ui_system(),
                build_chat_ui_prompt(question, answer),
                temperature=LAYOUT_TEMPERATURE,
                max_tokens=LAYOUT_MAX_TOKENS,
            )
        except Exception as exc:  # noqa: BLE001 - the prose is already on screen
            logger.info("Chat layout call failed, serving prose: %s", exc)
            return None
        return validate_chat_program(raw)

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
    "RETRIEVAL_TOP_K",
    "ChatService",
    "strip_no_ui",
    "validate_chat_program",
]
