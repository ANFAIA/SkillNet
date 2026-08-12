import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.models import EnrollmentStatus
from src.routes import talent


@pytest.mark.asyncio
async def test_people_route_forwards_course_skill_and_status_filters(monkeypatch) -> None:
    service = SimpleNamespace(list_people=AsyncMock(return_value=([], 0)))
    monkeypatch.setattr(talent, "_service", lambda db: service)
    org_id = uuid.uuid4()
    course_id = uuid.uuid4()
    skill_id = uuid.uuid4()

    response = await talent.list_people(
        admin=SimpleNamespace(org_id=org_id),
        db=object(),
        search="ana",
        course_id=course_id,
        skill_id=skill_id,
        status=EnrollmentStatus.COMPLETED,
        offset=0,
        limit=25,
    )

    assert response.total == 0
    service.list_people.assert_awaited_once_with(
        org_id=org_id,
        search="ana",
        course_id=course_id,
        skill_id=skill_id,
        status=EnrollmentStatus.COMPLETED,
        offset=0,
        limit=25,
    )
