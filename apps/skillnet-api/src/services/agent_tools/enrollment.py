"""``enrollment_*`` tools: enroll/unenroll a learner, list who's enrolled.

Same rule as ``users.py``: every handler is a thin wrapper over
:class:`EnrollmentService`, so it inherits that service's own org-scoping and
cross-tenant guard (``_assert_users_in_org``) rather than re-implementing it.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError
from src.models import EnrollmentStatus, User
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.services.agent_tools.base import ToolSpec
from src.services.enrollment_service import EnrollmentService


def _service(db: AsyncSession) -> EnrollmentService:
    return EnrollmentService(
        EnrollmentRepository(db), CourseRepository(db), ExerciseRepository(db)
    )


async def _enrollment_list(db: AsyncSession, user: User, args: dict[str, Any]) -> Any:
    status = args.get("status")
    rows, total = await _service(db).list_enrollments(
        org_id=user.org_id,
        user_id=_optional_uuid(args.get("user_id")),
        course_id=_optional_uuid(args.get("course_id")),
        status=EnrollmentStatus(status) if status else None,
        offset=0,
        limit=min(int(args.get("limit") or 50), 100),
    )
    return {
        "total": total,
        "enrollments": [
            {
                "id": str(e.id),
                "user_id": str(e.user_id),
                "course_id": str(e.course_id),
                "status": e.status.value,
                "deadline": e.deadline.isoformat() if e.deadline else None,
            }
            for e in rows
        ],
    }


async def _enrollment_create(db: AsyncSession, user: User, args: dict[str, Any]) -> Any:
    target_user_id = args.get("user_id")
    course_id = args.get("course_id")
    if not target_user_id or not course_id:
        raise AppError(
            message="user_id and course_id are required",
            code="VALIDATION_ERROR",
            status_code=400,
        )
    created = await _service(db).assign(
        org_id=user.org_id,
        assigned_by=user.id,
        course_id=uuid.UUID(str(course_id)),
        user_ids=[uuid.UUID(str(target_user_id))],
        deadline=None,
    )
    await db.commit()
    return {"enrollment_ids": [str(e.id) for e in created]}


async def _enrollment_delete(db: AsyncSession, user: User, args: dict[str, Any]) -> Any:
    enrollment_id = args.get("enrollment_id")
    if not enrollment_id:
        raise AppError(
            message="enrollment_id is required", code="VALIDATION_ERROR", status_code=400
        )
    await _service(db).delete(
        enrollment_id=uuid.UUID(str(enrollment_id)), org_id=user.org_id
    )
    await db.commit()
    return {"deleted": True}


def _optional_uuid(value: Any) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="enrollment_list",
        domain="enrollment",
        verb="list",
        description="List enrollments, optionally filtered by user, course or status.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "course_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": [s.value for s in EnrollmentStatus],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
        handler=_enrollment_list,
    ),
    ToolSpec(
        name="enrollment_create",
        domain="enrollment",
        verb="create",
        description=(
            "Enroll one user in one course. WRITE ACTION: only call this after "
            "the admin has explicitly confirmed which user and which course."
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "course_id": {"type": "string"},
            },
            "required": ["user_id", "course_id"],
        },
        handler=_enrollment_create,
        requires_confirmation=True,
    ),
    ToolSpec(
        name="enrollment_delete",
        domain="enrollment",
        verb="delete",
        description=(
            "Remove an enrollment (only allowed while it is still 'assigned', "
            "not started). WRITE ACTION: only call this after the admin has "
            "explicitly confirmed which enrollment to remove."
        ),
        parameters={
            "type": "object",
            "properties": {"enrollment_id": {"type": "string"}},
            "required": ["enrollment_id"],
        },
        handler=_enrollment_delete,
        requires_confirmation=True,
    ),
)
