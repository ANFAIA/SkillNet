from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from src.repositories.media_artifact_repo import MediaArtifactRepository


@pytest.mark.asyncio
async def test_course_overview_query_excludes_node_runtime_outputs():
    scalars = SimpleNamespace(all=lambda: [])
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: scalars))
    )

    await MediaArtifactRepository(session).list_course_level(uuid.uuid4(), uuid.uuid4())

    statement = session.execute.await_args.args[0]
    assert "media_artifacts.node_id IS NULL" in str(statement)
