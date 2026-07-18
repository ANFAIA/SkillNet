"""Data access for chat sessions and messages."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ChatMessage, ChatSession


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        title: str | None,
        agent_type: str = "tutor",
        course_id: uuid.UUID | None = None,
    ) -> ChatSession:
        chat_session = ChatSession(
            user_id=user_id,
            org_id=org_id,
            title=title,
            agent_type=agent_type,
            course_id=course_id,
        )
        self.session.add(chat_session)
        await self.session.flush()
        return chat_session

    async def get_owned_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ChatSession | None:
        chat_session = await self.session.get(ChatSession, session_id)
        if chat_session is None or chat_session.user_id != user_id:
            return None
        return chat_session

    async def list_sessions(self, user_id: uuid.UUID) -> Sequence[ChatSession]:
        query = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
        return (await self.session.execute(query)).scalars().all()

    async def add_message(
        self,
        *,
        session_id: uuid.UUID,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            message_metadata=metadata or {},
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_messages(self, session_id: uuid.UUID) -> Sequence[ChatMessage]:
        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        return (await self.session.execute(query)).scalars().all()

    async def recent_messages(
        self, session_id: uuid.UUID, limit: int
    ) -> list[ChatMessage]:
        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(query)).scalars().all()
        return list(reversed(rows))
