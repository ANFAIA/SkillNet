"""The admin agent: a tool-calling chat, separate from the read-only admin chat.

``ChatService.stream_admin`` (``chat_service.py``) stays untouched — it is the fast,
no-tools, always-streams-prose surface. This is a different session thread
(``ChatSession.agent_type == "admin_agent"``) for admins who want to *act*
("matricula a Ana en el curso X") rather than only ask.

Design, agreed with the product owner before writing this:

* **Native function-calling, not the ``ACTION:`` text pattern.** That pattern (see
  ``chat_service.ALLOWED_TOOLS``) is for the model nudging the UI (locale,
  sidebar) — it is not built for retries, structured args, or a write with
  real side effects.
* **Every tool is always sent.** No heuristic decides "this turn needs tools" —
  the provider's own tool-choice does that, exactly like Claude Code/Codex send
  their whole tool list every turn. With six tools this costs nothing; the
  registry carries ``domain``/``verb`` for the day a dynamic subset is worth it.
* **Read tools run free; write tools need the human, not the model, to have
  confirmed.** The check lives here, once, not duplicated per tool: a write
  tool call is executed only if the *user's* immediately preceding turn
  contains a recognizable confirmation. Otherwise the loop feeds the model a
  synthetic tool result asking it to get that confirmation in text instead.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError
from src.core.logging import get_logger
from src.core.sse import format_sse
from src.deps.db import async_session_factory
from src.llm.client import LLMService
from src.models import User
from src.repositories.chat_repo import ChatRepository
from src.services.agent_tools import registry

logger = get_logger(__name__)

AGENT_TYPE = "admin_agent"

#: Safety net against a model that loops calling tools forever.
MAX_TOOL_ITERATIONS = 5

TITLE_MAX_CHARS = 60

SYSTEM_PROMPT = """You are the SkillNet admin agent: a chat assistant that can act on \
behalf of an organization admin using the tools you are given, in addition to \
answering questions in plain text.

Rules:
- Tool names follow a `domain_verb` convention (e.g. `users_list`, \
`enrollment_create`) — group them mentally by the part before the underscore.
- Read tools (`*_list`, `*_get_progress`) are safe to call any time you need a fact.
- Write tools create or delete real data (a new account, an enrollment). Before \
calling a write tool, you must have the admin's explicit confirmation of exactly \
what you are about to do, in this conversation. If you do not have it yet, ask a \
clear question in plain text instead of calling the tool. If you call a write tool \
without confirmation, the system will refuse to run it and tell you to ask first.
- When a person could refer to several documents/users/courses, or when it is not \
clear whether several items should be grouped or handled one by one, ask the admin \
rather than guessing.
- Answer in the same language the admin is writing in.
"""

#: A cheap, deliberately permissive detector for "yes, do it" — false positives cost
#: nothing (the model still has to have asked the right question to get here), false
#: negatives just mean one extra confirmation round, which is the safe direction to
#: err in for a write action.
_CONFIRMATION_RE = re.compile(
    r"\b(s[ií]|vale|ok|confirmo|adelante|hazlo|correcto|yes|confirm|go ahead|do it)\b",
    re.IGNORECASE,
)


def _looks_like_confirmation(text: str) -> bool:
    return bool(_CONFIRMATION_RE.search(text or ""))


#: The confirmation gate, factored out of ``AdminAgentService._run_tool`` so it can
#: be unit-tested without a DB session: given whether the tool needs confirmation
#: and whether the triggering user turn had one, decide whether to run it at all.
def confirmation_error(tool_requires_confirmation: bool, *, confirmed: bool) -> str | None:
    """``None`` means "go ahead"; otherwise the message to hand back as a tool result."""
    if not tool_requires_confirmation or confirmed:
        return None
    return (
        "This is a write action and the admin has not explicitly confirmed it "
        "yet in this message. Ask them to confirm in plain text, then call this "
        "tool again."
    )


class AdminAgentService:
    def __init__(self, db: AsyncSession, llm: LLMService) -> None:
        self.db = db
        self.llm = llm
        self.repo = ChatRepository(db)

    async def stream(
        self,
        user: User,
        message: str,
        session_id: uuid.UUID | None,
        context: dict | None,
    ) -> AsyncIterator[str]:
        session = await self._load_or_create_session(user, message, session_id)
        history = await self.repo.recent_messages(session.id, 20)
        await self.repo.add_message(session_id=session.id, role="user", content=message)
        await self.db.commit()

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for turn in history:
            if turn.role in ("user", "assistant"):
                messages.append({"role": turn.role, "content": turn.content})
        messages.append({"role": "user", "content": message})

        # The confirmation gate only ever looks at the admin's own words, so it is
        # computed once, up front, from the turn that triggered this call.
        user_confirmed = _looks_like_confirmation(message)

        tools = registry.provider_schemas()
        tool_trace: list[dict] = []
        final_text = ""
        try:
            for _ in range(MAX_TOOL_ITERATIONS):
                text, tool_calls = await self.llm.complete_with_tools(
                    messages, tools=tools
                )
                if not tool_calls:
                    final_text = text
                    break

                messages.append(
                    {
                        "role": "assistant",
                        "content": text or None,
                        "tool_calls": [
                            {
                                "id": call["id"],
                                "type": "function",
                                "function": {
                                    "name": call["name"],
                                    "arguments": json.dumps(call["arguments"]),
                                },
                            }
                            for call in tool_calls
                        ],
                    }
                )
                for call in tool_calls:
                    yield format_sse(
                        "tool_call", {"name": call["name"], "arguments": call["arguments"]}
                    )
                    result = await self._run_tool(call, user, confirmed=user_confirmed)
                    tool_trace.append({"name": call["name"], "result": result})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(result, default=str),
                        }
                    )
            else:
                final_text = final_text or (
                    "I ran out of tool-call attempts for this turn — could you "
                    "rephrase or split the request?"
                )
        except AppError as exc:
            yield format_sse("error", {"detail": exc.message})
            return

        yield format_sse("token", {"content": final_text})
        assistant = await self.repo.add_message(
            session_id=session.id,
            role="assistant",
            content=final_text,
            metadata={"tool_calls": tool_trace},
        )
        await self.db.commit()
        yield format_sse(
            "done", {"message_id": str(assistant.id), "session_id": str(session.id)}
        )

    async def _run_tool(self, call: dict, user: User, *, confirmed: bool) -> dict:
        tool = registry.get(call["name"])
        if tool is None:
            return {"error": f"Unknown tool '{call['name']}'"}
        gate_error = confirmation_error(tool.requires_confirmation, confirmed=confirmed)
        if gate_error is not None:
            return {"error": gate_error}
        try:
            # A fresh session per tool call: a write tool commits its own
            # transaction (see agent_tools/users.py, enrollment.py), and nothing
            # here should share a transaction with the chat-history writes above.
            async with async_session_factory() as tool_db:
                return await tool.handler(tool_db, user, call["arguments"] or {})
        except AppError as exc:
            return {"error": exc.message}

    async def _load_or_create_session(
        self, user: User, message: str, session_id: uuid.UUID | None
    ):
        if session_id is not None:
            from src.core.exceptions import NotFoundError

            session = await self.repo.get_owned_session(session_id, user.id)
            if session is None:
                raise NotFoundError("chat_sessions", str(session_id))
            return session
        title = message.strip()[:TITLE_MAX_CHARS] or None
        return await self.repo.create_session(
            user_id=user.id, org_id=user.org_id, title=title, agent_type=AGENT_TYPE
        )

    async def list_sessions(self, user: User):
        sessions = await self.repo.list_sessions(user.id)
        return [s for s in sessions if s.agent_type == AGENT_TYPE]
