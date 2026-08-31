"""Chat routes: tutor SSE streaming, session listing, message history.

Generative UI is controlled by the organization's ``chat_generative_ui`` setting,
edited from ``/admin/ajustes``. The admin chooses the model, so they choose whether
it is worth a second call to ask that model for a layout. With it off,
``ChatService`` never makes the layout call, never emits a ``ui`` event and costs
exactly the tokens it cost yesterday.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from src.deps.auth import AdminUser, CurrentUser, EmployeeOrAdminUser
from src.deps.db import DBSession
from src.deps.llm import EmbeddingDep, LLMDep, TutorLLMDep
from src.models import Organization
from src.schemas.chat import ChatMessageRead, ChatRequest, ChatSessionRead
from src.services.admin_agent_service import AdminAgentService
from src.services.chat_service import ChatService
from src.services.org_features import chat_generative_ui_enabled

router = APIRouter(prefix="/chat", tags=["Chat"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


async def _org_settings(db: DBSession, org_id: uuid.UUID | None) -> dict[str, Any]:
    """The organization's own settings dict, or ``{}``.

    Falls back to the single row when the user carries no ``org_id``, matching what
    ``src/deps/llm.py`` does one dependency earlier for the very same row.
    """
    query = select(Organization)
    query = query.where(Organization.id == org_id) if org_id else query.limit(1)
    org = (await db.execute(query)).scalar_one_or_none()
    return dict(org.settings) if org and org.settings else {}


@router.post("")
async def chat(
    request: ChatRequest,
    user: EmployeeOrAdminUser,
    db: DBSession,
    tutor_llm: TutorLLMDep,
    embeddings: EmbeddingDep,
    accept_language: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """The employee tutor.

    The header is the *last* step of the language order in
    ``src/services/language_policy.py``: the course in ``request.context`` and the
    organization's own default both outrank it. It is read here because a route is the only
    place a header exists.
    """
    org_settings = await _org_settings(db, getattr(user, "org_id", None))
    generative_ui = chat_generative_ui_enabled(org_settings)
    service = ChatService(db, tutor_llm, embeddings, generative_ui=generative_ui)
    stream = service.stream_tutor(
        user,
        request.message,
        request.session_id,
        request.context,
        accept_language=accept_language,
        # Already loaded for ``chat_generative_ui_enabled``; handed over so resolving the
        # organization's default language does not cost a second read of the same row.
        org_settings=org_settings,
    )
    return StreamingResponse(
        stream, media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.post("/admin")
async def admin_chat(
    request: ChatRequest,
    user: AdminUser,
    db: DBSession,
    llm: LLMDep,
    embeddings: EmbeddingDep,
    accept_language: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    org_settings = await _org_settings(db, getattr(user, "org_id", None))
    generative_ui = chat_generative_ui_enabled(org_settings)
    service = ChatService(db, llm, embeddings, generative_ui=generative_ui)
    stream = service.stream_admin(
        user,
        request.message,
        request.session_id,
        request.context,
        accept_language=accept_language,
        org_settings=org_settings,
    )
    return StreamingResponse(
        stream, media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.post("/admin/agent")
async def admin_agent_chat(
    request: ChatRequest,
    user: AdminUser,
    db: DBSession,
    llm: LLMDep,
) -> StreamingResponse:
    """The tool-calling admin agent — a separate thread from ``/chat/admin``.

    Uses the org's plain ``llm`` (not the tutor-purpose one): tool-calling
    reliability depends on the model, not on the tutor persona tuning.
    """
    service = AdminAgentService(db, llm)
    stream = service.stream(user, request.message, request.session_id, request.context)
    return StreamingResponse(
        stream, media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.get("/sessions", response_model=list[ChatSessionRead])
async def list_sessions(
    user: CurrentUser,
    db: DBSession,
) -> list[ChatSessionRead]:
    service = ChatService(db)
    sessions = await service.list_sessions(user)
    return [ChatSessionRead.model_validate(s) for s in sessions]


@router.get(
    "/sessions/{session_id}/messages", response_model=list[ChatMessageRead]
)
async def get_messages(
    session_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> list[ChatMessageRead]:
    service = ChatService(db)
    messages = await service.get_messages(user, session_id)
    return [
        ChatMessageRead(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            metadata=m.message_metadata or {},
        )
        for m in messages
    ]
