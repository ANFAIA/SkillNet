from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import uuid

import pytest

from src.models import MediaArtifactStatus, MediaKind
from src.services import runtime_modalities


@pytest.mark.asyncio
async def test_ready_node_audio_is_reused_without_starting_a_course_job(monkeypatch):
    ready = SimpleNamespace(
        id=uuid.uuid4(), kind=MediaKind.PODCAST, status=MediaArtifactStatus.DONE
    )
    repository = SimpleNamespace(list_for_course=AsyncMock(return_value=[ready]))
    monkeypatch.setattr(runtime_modalities, "MediaArtifactRepository", lambda _db: repository)
    enqueue = AsyncMock()
    spawn = Mock()
    monkeypatch.setattr(runtime_modalities, "enqueue_artifact", enqueue)
    monkeypatch.setattr(runtime_modalities, "spawn_media_job", spawn)
    db = SimpleNamespace(commit=AsyncMock())
    course = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    node = SimpleNamespace(id=uuid.uuid4())

    result, created = await runtime_modalities.request_runtime_modality(
        db, course=course, node=node, modality="audio"
    )

    assert result is ready
    assert created is False
    repository.list_for_course.assert_awaited_once_with(
        course.id, course.org_id, node_id=node.id
    )
    enqueue.assert_not_awaited()
    db.commit.assert_not_awaited()
    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_failed_video_is_retried_on_demand_as_a_runtime_representation(monkeypatch):
    failed = SimpleNamespace(
        id=uuid.uuid4(), kind=MediaKind.VIDEO, status=MediaArtifactStatus.ERROR
    )
    created_artifact = SimpleNamespace(
        id=uuid.uuid4(), kind=MediaKind.VIDEO, status=MediaArtifactStatus.PENDING
    )
    repository = SimpleNamespace(list_for_course=AsyncMock(return_value=[failed]))
    monkeypatch.setattr(runtime_modalities, "MediaArtifactRepository", lambda _db: repository)
    enqueue = AsyncMock(return_value=created_artifact)
    spawn = Mock()
    monkeypatch.setattr(runtime_modalities, "enqueue_artifact", enqueue)
    monkeypatch.setattr(runtime_modalities, "spawn_media_job", spawn)
    db = SimpleNamespace(commit=AsyncMock())
    course = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    node = SimpleNamespace(id=uuid.uuid4())

    result, created = await runtime_modalities.request_runtime_modality(
        db, course=course, node=node, modality="video", language="en"
    )

    assert result is created_artifact
    assert created is True
    enqueue.assert_awaited_once_with(
        db,
        course=course,
        node=node,
        kind=MediaKind.VIDEO,
        spec={"language": "en", "delivery_scope": "runtime_node"},
    )
    db.commit.assert_awaited_once()
    spawn.assert_called_once_with(created_artifact.id)
