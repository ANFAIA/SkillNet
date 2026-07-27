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
from src.llm.prompts.tutor import (
    NO_UI_SENTINEL,
    TUTOR_PROMPT_VERSION,
    Grounding,
    admin_system_prompt,
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
from src.services.retrieval import GroundedContext, ground_question

logger = get_logger(__name__)

MEMORY_TURNS = 8
TITLE_MAX_CHARS = 40
RETRIEVAL_TOP_K = 5

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
        async for event in self._stream(
            user,
            message,
            session_id,
            context,
            agent_type="admin",
            whole_documents="org",
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
    ) -> AsyncIterator[str]:
        grounded = GroundedContext("general")
        parts: list[str] = []
        session: ChatSession | None = None
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
            # Announced before the first token, so the bubble carries its provenance from
            # the moment it starts filling rather than growing a label at the end.
            yield format_sse("grounding", {"grounding": grounded.grounding})

            messages = self._build_messages(history, grounded, message, agent_type)

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
                    "prompt_version": TUTOR_PROMPT_VERSION,
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
    ) -> list[dict[str, str]]:
        grounding: Grounding = grounded.grounding
        system = (
            admin_system_prompt(grounding)
            if agent_type == "admin"
            else tutor_system_prompt(grounding)
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for msg in history:
            if msg.role in ("user", "assistant"):
                messages.append({"role": msg.role, "content": msg.content})
        messages.append(
            {
                "role": "user",
                "content": build_user_turn(grounding, grounded.context, question),
            }
        )
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
    "CHAT_UI_FORMAT",
    "MEMORY_TURNS",
    "MIN_LAYOUT_CHARS",
    "RETRIEVAL_TOP_K",
    "ChatService",
    "strip_no_ui",
    "validate_chat_program",
]
