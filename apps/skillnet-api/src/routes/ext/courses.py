"""External one-call course creation — authenticated via API key.

``POST /ext/v1/courses/full`` runs the whole authoring flow (create, propose,
generate packs, review, validate, optional prewarm/enrol/artefacts) behind a
single request, so an agent creates a course the way it calls any other tool.
The heavy lifting lives in :func:`create_course_end_to_end`; this route only maps
the API-key identity onto it (org + creating admin) and shapes the response.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.routes.ext.auth import ExtApiKey
from src.services.course_orchestration import create_course_end_to_end

router = APIRouter(prefix="/courses", tags=["Courses (external)"])


class FullCourseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    document_id: uuid.UUID | None = Field(
        default=None,
        description="Optional ready document to ground the schema on.",
    )
    description: str | None = None
    outcome: str | None = None
    intent_density: int = Field(default=3, ge=1, le=5)
    enroll_user_id: uuid.UUID | None = Field(
        default=None, description="Optional employee to enrol on completion."
    )
    generate_artifacts: list[str] | None = Field(
        default=None,
        description="Media kinds to generate for the first nodes, e.g. "
        "['podcast', 'infographic'].",
    )
    artifact_node_limit: int = Field(default=1, ge=0, le=10)


@router.post("/full", status_code=201)
async def create_full_course(api_key: ExtApiKey, body: FullCourseRequest) -> dict:
    """Create a dynamic course end to end and return a structured result.

    The API key carries the organization and the admin the key was created for; the
    course is created and validated under that identity. Returns partial success
    honestly (``packs_ready``, ``validated``, ``warnings``) rather than failing when
    a flaky provider leaves a node short.
    """
    result = await create_course_end_to_end(
        body.title,
        org_id=api_key.org_id,
        created_by=api_key.created_by,
        document_id=body.document_id,
        description=body.description,
        outcome=body.outcome,
        intent_density=body.intent_density,
        enroll_user_id=body.enroll_user_id,
        generate_artifacts=body.generate_artifacts,
        artifact_node_limit=body.artifact_node_limit,
    )
    return result.to_dict()
