"""On-demand course retrieval for the employee's general chat."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from src.services import chat_service as chat_module
from src.services.chat_retrieval_policy import course_retrieval_required
from src.services.chat_service import ChatService
from src.services.retrieval import GroundedContext


class _DB:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def execute(self, _statement):
        # The turn reads the course in ``context`` once, for its ``tutor_style`` and its
        # ``language``. There is no course row in this stub's world, which is the case
        # these tests are about: retrieval policy, not personalization.
        return SimpleNamespace(scalar_one_or_none=lambda: None)


class _Repo:
    def __init__(self) -> None:
        self.messages: list[SimpleNamespace] = []

    async def create_session(self, **_kwargs):
        return SimpleNamespace(id=uuid.uuid4())

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


class _LLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def stream(self, messages, **_kwargs):
        self.messages = messages
        yield "Respuesta general."


def _decode(chunks: list[str]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for chunk in chunks:
        head, _, body = chunk.partition("\n")
        events.append((head.removeprefix("event: "), json.loads(body.removeprefix("data: "))))
    return events


async def _empty_memory(_user):
    return ""


async def _ignore_topic(_user, _context):
    return None


async def _service_events(monkeypatch, message: str, context: dict | None = None):
    retrieval_calls: list[str] = []

    async def fake_ground(*_args, **kwargs):
        retrieval_calls.append(kwargs["query"])
        return GroundedContext(
            "chunks",
            "[Fuente 1: Manual]\ncontenido",
            [{"document": "Manual", "section": "", "page": None}],
        )

    monkeypatch.setattr(chat_module, "ground_question", fake_ground)
    llm = _LLM()
    service = ChatService(_DB(), llm, object())  # type: ignore[arg-type]
    repo = _Repo()
    service.repo = repo  # type: ignore[assignment]
    service._learner_memory_block = _empty_memory  # type: ignore[method-assign]
    service._remember_chat_topic = _ignore_topic  # type: ignore[method-assign]
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), role="employee")
    chunks = [event async for event in service.stream_tutor(user, message, None, context)]
    return _decode(chunks), retrieval_calls, repo, llm


def test_policy_distinguishes_general_questions_from_course_questions() -> None:
    assert not course_retrieval_required("¿Cómo organizo mejor mi tiempo?", None)
    assert not course_retrieval_required("¿Qué significa contaminación cruzada?", None)
    assert course_retrieval_required("¿Qué dice mi curso sobre contaminación cruzada?", None)
    assert course_retrieval_required("Según el manual, ¿qué debo hacer?", None)


async def test_general_chat_skips_rag_and_has_no_sources(monkeypatch) -> None:
    events, calls, repo, llm = await _service_events(monkeypatch, "¿Cómo organizo mejor mi tiempo?")

    assert calls == []
    assert next(data for name, data in events if name == "grounding") == {"grounding": "general"}
    assert next(data for name, data in events if name == "citations")["citations"] == []
    assert repo.messages[-1].message_metadata["citations"] == []
    assert repo.messages[-1].message_metadata["grounding"] == "general"
    assert repo.messages[-1].message_metadata["retrieval_attempted"] is False
    assert "no se ha ejecutado recuperacion documental" in llm.messages[-1]["content"]


async def test_explicit_course_question_runs_rag(monkeypatch) -> None:
    events, calls, _repo, _llm = await _service_events(
        monkeypatch, "¿Qué dice mi curso sobre alérgenos?"
    )

    assert calls == ["¿Qué dice mi curso sobre alérgenos?"]
    assert next(data for name, data in events if name == "grounding") == {"grounding": "chunks"}


async def test_contextual_course_chat_always_runs_rag(monkeypatch) -> None:
    _events, calls, _repo, _llm = await _service_events(
        monkeypatch,
        "Explícamelo de otra forma",
        {"course_id": str(uuid.uuid4())},
    )

    assert calls == ["Explícamelo de otra forma"]
