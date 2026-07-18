"""Tutor chat: RAG retrieval + conversational memory + SSE streaming.

No LangGraph, no tools. Each turn: load/create the session, persist the user
message, retrieve org-scoped RAG context, build a prompt (system persona + last
N turns as memory + a final turn embedding the cited context), stream tokens as
SSE events, then persist the assistant message with its citations.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError, NotFoundError
from src.core.logging import get_logger
from src.core.sse import format_sse
from src.llm.client import LLMService
from src.llm.embedding import EmbeddingService
from src.models import ChatMessage, ChatSession, User
from src.repositories.chat_repo import ChatRepository
from src.services.retrieval import retrieve_context

logger = get_logger(__name__)

MEMORY_TURNS = 8
TITLE_MAX_CHARS = 40
RETRIEVAL_TOP_K = 5

SYSTEM_PROMPT = (
    "Eres un tutor virtual de formacion para empleados. Respondes en espanol, "
    "con un tono claro, cercano y profesional.\n"
    "Reglas estrictas:\n"
    "- Responde UNICAMENTE con la informacion del contexto proporcionado.\n"
    "- Cita la fuente usando [Fuente N] al final de cada afirmacion relevante.\n"
    "- Si la respuesta no esta en el contexto, di exactamente: "
    '"No tengo informacion sobre esto en los documentos disponibles."\n'
    "- No inventes datos ni uses conocimiento externo.\n"
    "- Responde en el mismo idioma que la pregunta."
)

ADMIN_SYSTEM_PROMPT = (
    "Eres el asistente del administrador de una plataforma de formacion interna. "
    "Respondes en espanol, de forma concisa y profesional.\n"
    "Reglas estrictas:\n"
    "- Responde basandote en la documentacion de la organizacion proporcionada "
    "como contexto.\n"
    "- Cita la fuente usando [Fuente N] cuando uses el contexto.\n"
    "- Si la informacion no esta en el contexto, dilo con claridad en lugar de "
    "inventar datos.\n"
    "- Responde en el mismo idioma que la pregunta."
)


def _build_user_turn(context_block: str, question: str) -> str:
    context = context_block or "(No hay contexto disponible.)"
    return (
        "Contexto de la empresa (usa SOLO esta informacion para responder):\n\n"
        f"{context}\n\n"
        "---\n\n"
        f"Pregunta del empleado: {question}\n\n"
        "Instrucciones:\n"
        "- Responde basandote SOLO en el contexto anterior.\n"
        "- Cita la fuente usando [Fuente N].\n"
        '- Si la informacion no esta en el contexto, di "No tengo informacion '
        'sobre esto en los documentos disponibles."'
    )


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


class ChatService:
    def __init__(
        self,
        db: AsyncSession,
        tutor_llm: LLMService | None = None,
        embeddings: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.tutor_llm = tutor_llm
        self.embeddings = embeddings
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
            system_prompt=SYSTEM_PROMPT,
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
            system_prompt=ADMIN_SYSTEM_PROMPT,
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
        system_prompt: str,
    ) -> AsyncIterator[str]:
        citations: list[dict] = []
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

            context_block, citations = await retrieve_context(
                self.db,
                org_id=user.org_id,
                embedding_service=self.embeddings,
                query=message,
                top_k=RETRIEVAL_TOP_K,
                document_ids=_context_document_ids(context),
            )

            messages = self._build_messages(
                history, context_block, message, system_prompt
            )

            async for piece in self.tutor_llm.stream(messages):
                parts.append(piece)
                yield format_sse("token", {"content": piece})

            full_text = "".join(parts)
            yield format_sse("citations", {"citations": citations})

            assistant = await self.repo.add_message(
                session_id=session.id,
                role="assistant",
                content=full_text,
                metadata={"citations": citations},
            )
            await self.db.commit()
            yield format_sse("done", {"message_id": str(assistant.id)})

        except Exception as exc:  # noqa: BLE001 - stream must always terminate cleanly
            detail = exc.message if isinstance(exc, AppError) else str(exc)
            logger.error("Tutor chat failed: %s", exc, exc_info=True)
            await self._persist_partial(session, parts, citations)
            yield format_sse("error", {"detail": detail})

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
        context_block: str,
        question: str,
        system_prompt: str,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        for msg in history:
            if msg.role in ("user", "assistant"):
                messages.append({"role": msg.role, "content": msg.content})
        messages.append(
            {"role": "user", "content": _build_user_turn(context_block, question)}
        )
        return messages

    async def _persist_partial(
        self,
        session: ChatSession | None,
        parts: list[str],
        citations: list[dict],
    ) -> None:
        if session is None or not parts:
            return
        try:
            await self.db.rollback()
            await self.repo.add_message(
                session_id=session.id,
                role="assistant",
                content="".join(parts),
                metadata={"citations": citations, "partial": True},
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
