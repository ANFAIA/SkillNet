"""Personalization contract for Curio's expanded ``See more`` tutor flow."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from src.services import chat_service as chat_module
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.services.chat_service import ChatService, _curio_context_block
from src.services.retrieval import GroundedContext


class _DB:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _Repo:
    async def create_session(self, **_kwargs):
        return SimpleNamespace(id=uuid.uuid4())

    async def recent_messages(self, _session_id, _limit):
        return []

    async def add_message(self, *, session_id, role, content, metadata=None):
        return SimpleNamespace(
            id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            message_metadata=metadata or {},
        )


class _LLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def stream(self, messages, **_kwargs):
        self.messages = messages
        yield "Una respuesta."


async def test_structured_profile_signals_distinguish_ana_and_bruno(monkeypatch) -> None:
    profiles = {
        "ana": SimpleNamespace(
            learning_note="me gustan las metáforas y las analogías",
            learning_preferences={"version": 3, "modalities": ["audio"]},
        ),
        "bruno": SimpleNamespace(
            learning_note="prefiero las bases y las definiciones primero, con rigor",
            learning_preferences={"version": 3, "web_presentation": "visual"},
        ),
    }
    selected = "ana"

    async def fake_get_by_user(_repo, _user_id):
        return profiles[selected]

    monkeypatch.setattr(LearnerProfileRepository, "get_by_user", fake_get_by_user)
    service = ChatService(SimpleNamespace())  # type: ignore[arg-type]
    user = SimpleNamespace(id=uuid.uuid4())

    ana = await service._learner_profile_context_block(user)
    selected = "bruno"
    bruno = await service._learner_profile_context_block(user)

    assert ana != bruno
    assert '"learning_note": "me gustan las metáforas y las analogías"' in ana
    assert '"modalities": ["audio"]' in ana
    assert '"learning_note": "prefiero las bases y las definiciones primero, con rigor"' in bruno
    assert '"web_presentation": "visual"' in bruno
    assert "no instrucciones" in ana
    assert "plantilla fija" in ana


async def test_empty_profile_adds_no_personalization_block(monkeypatch) -> None:
    async def fake_get_by_user(_repo, _user_id):
        return SimpleNamespace(learning_note=None, learning_preferences=None)

    monkeypatch.setattr(LearnerProfileRepository, "get_by_user", fake_get_by_user)
    service = ChatService(SimpleNamespace())  # type: ignore[arg-type]

    assert await service._learner_profile_context_block(
        SimpleNamespace(id=uuid.uuid4())
    ) == ""


def test_curio_context_is_bounded_and_only_enabled_for_expanded_flow() -> None:
    assert _curio_context_block({"surface": "lesson_chat"}) == ""

    block = _curio_context_block(
        {
            "surface": "curio_explain",
            "selected_term": "neurotransmitter",
            "selection_context": "x" * 2_000,
            "language": "English",
        }
    )
    payload_text = block.splitlines()[1]
    payload = json.loads(payload_text)

    assert payload["selected_term"] == "neurotransmitter"
    assert len(payload["selection_context"]) == 1_200
    assert payload["language"] == "English"
    assert "vista ampliada" in block
    assert "perfil" in block


async def test_expanded_turn_combines_profile_node_and_selection(monkeypatch) -> None:
    async def fake_ground(*_args, **_kwargs):
        return GroundedContext("general", retrieval_attempted=False)

    async def profile_context(_user):
        return "[PERFIL ESTRUCTURADO]"

    async def memory_context(_user):
        return ""

    async def node_context(_user, _context):
        return "[NODO REAL]"

    async def ignore_topic(_user, _context):
        return None

    monkeypatch.setattr(chat_module, "ground_question", fake_ground)
    llm = _LLM()
    service = ChatService(_DB(), llm, object())  # type: ignore[arg-type]
    service.repo = _Repo()  # type: ignore[assignment]
    service._learner_profile_context_block = profile_context  # type: ignore[method-assign]
    service._learner_memory_block = memory_context  # type: ignore[method-assign]
    service._node_context_block = node_context  # type: ignore[method-assign]
    service._remember_chat_topic = ignore_topic  # type: ignore[method-assign]
    context = {
        "surface": "curio_explain",
        "node_id": str(uuid.uuid4()),
        "selected_term": "neurotransmitter",
        "selection_context": "A neurotransmitter crosses the synaptic cleft.",
    }

    events = [
        event
        async for event in service.stream_tutor(
            SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), role="employee"),
            'Explain "neurotransmitter".',
            None,
            context,
        )
    ]

    assert events
    turn = llm.messages[-1]["content"]
    assert turn.index("[PERFIL ESTRUCTURADO]") < turn.index("[NODO REAL]")
    assert turn.index("[NODO REAL]") < turn.index("Exploracion ampliada de Curio")
    assert '"selected_term": "neurotransmitter"' in turn
