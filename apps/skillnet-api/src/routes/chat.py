"""Chat routes: tutor SSE streaming, session listing, message history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.deps.auth import AdminUser, CurrentUser, EmployeeUser
from src.deps.db import DBSession
from src.deps.llm import EmbeddingDep, LLMDep, TutorLLMDep
from src.schemas.chat import ChatMessageRead, ChatRequest, ChatSessionRead
from src.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["Chat"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.post("")
async def chat(
    request: ChatRequest,
    user: EmployeeUser,
    db: DBSession,
    tutor_llm: TutorLLMDep,
    embeddings: EmbeddingDep,
) -> StreamingResponse:
    service = ChatService(db, tutor_llm, embeddings)
    stream = service.stream_tutor(
        user, request.message, request.session_id, request.context
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
) -> StreamingResponse:
    service = ChatService(db, llm, embeddings)
    stream = service.stream_admin(
        user, request.message, request.session_id, request.context
    )
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
