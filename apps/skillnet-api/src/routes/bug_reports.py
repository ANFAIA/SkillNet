"""Bug reports: report a problem with the app, follow it, and (admins) file or discard it.

``POST /bugs`` answers at once; the model judges the report afterwards and, if it is genuine,
files it on GitHub. ``GET /bugs/mine`` shows where it ended up.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks
from fastapi import status as http_status

from src.config import settings
from src.core.exceptions import AppError, ConflictError, NotFoundError
from src.deps.auth import AdminUser, CurrentUser, _role_value
from src.deps.db import DBSession
from src.deps.llm import LLMDep
from src.models import BugReport, UserRole
from src.repositories.bug_report_repo import BugReportRepository
from src.schemas.bug_report import (
    BugReportAdminRead,
    BugReportCreate,
    BugReportDiscard,
    BugReportQueued,
    BugReportRead,
)
from src.services.bug_report_service import (
    file_by_admin,
    github_configured,
    process_report,
)

router = APIRouter(prefix="/bugs", tags=["Bug reports"])


def _read(row: BugReport) -> BugReportRead:
    verdict = row.verdict or {}
    return BugReportRead(
        id=row.id,
        title=row.title,
        status=row.status,
        severity=verdict.get("severity"),
        reason=verdict.get("reason"),
        issue_url=row.issue_url,
        page_path=row.page_path,
        environment=row.environment,
        created_at=row.created_at,
    )


def _admin_read(row: BugReport) -> BugReportAdminRead:
    return BugReportAdminRead(
        **_read(row).model_dump(), body=row.body, author_id=row.user_id
    )


@router.post("", response_model=BugReportQueued, status_code=http_status.HTTP_202_ACCEPTED)
async def report_bug(
    payload: BugReportCreate,
    background: BackgroundTasks,
    user: CurrentUser,
    db: DBSession,
    llm: LLMDep,
) -> BugReportQueued:
    title, body = payload.title.strip(), payload.body.strip()
    if not title or not body:
        raise AppError("Add a title and a description", "VALIDATION_ERROR", 422)

    repo = BugReportRepository(db)
    # Each report costs a model call, so a person sends a limited number a day. Admins have
    # no cap.
    if _role_value(user.role) != UserRole.ADMIN.value:
        since = datetime.now(timezone.utc) - timedelta(days=1)
        if await repo.count_since(user.id, since) >= settings.BUG_REPORT_DAILY_LIMIT:
            raise AppError(
                "You've reached today's limit for bug reports", "RATE_LIMITED", 429
            )

    row = BugReport(
        org_id=user.org_id,
        user_id=user.id,
        title=title,
        body=body,
        page_path=payload.page_path,
        # One line, so it can't add markdown or a second paragraph to the issue.
        environment=" ".join((payload.environment or "").split()) or None,
        status="pending",
    )
    db.add(row)
    await db.commit()
    background.add_task(process_report, row.id, llm)
    return BugReportQueued(id=row.id)


@router.get("/mine", response_model=list[BugReportRead])
async def my_bug_reports(user: CurrentUser, db: DBSession) -> list[BugReportRead]:
    rows = await BugReportRepository(db).list_for_user(user.id)
    return [_read(r) for r in rows]


@router.get("", response_model=list[BugReportAdminRead])
async def list_bug_reports(admin: AdminUser, db: DBSession) -> list[BugReportAdminRead]:
    rows = await BugReportRepository(db).list_for_org(admin.org_id)
    return [_admin_read(r) for r in rows]


async def _find(repo: BugReportRepository, admin_org: uuid.UUID, report_id: uuid.UUID):
    row = await repo.get_by_id(report_id)
    if row is None or row.org_id != admin_org:
        raise NotFoundError("bug_report", str(report_id))
    if row.status == "issue":
        raise ConflictError("That report is already filed")
    return row


@router.post("/{report_id}/file", response_model=BugReportAdminRead)
async def file_bug_report(
    report_id: uuid.UUID, admin: AdminUser, db: DBSession, llm: LLMDep
) -> BugReportAdminRead:
    """File a pending, failed or discarded report now, without the genuine check."""
    repo = BugReportRepository(db)
    row = await _find(repo, admin.org_id, report_id)
    if not github_configured():
        raise ConflictError(
            "GitHub isn't set up on this server: add GITHUB_TOKEN and GITHUB_REPO"
        )
    try:
        await file_by_admin(repo, row, llm)
    except Exception as exc:
        raise AppError(
            "Could not file the report; try again later", "UPSTREAM_ERROR", 502
        ) from exc
    await db.commit()
    return _admin_read(row)


@router.post("/{report_id}/discard", response_model=BugReportAdminRead)
async def discard_bug_report(
    report_id: uuid.UUID,
    payload: BugReportDiscard,
    admin: AdminUser,
    db: DBSession,
) -> BugReportAdminRead:
    """Discard a report that is not an issue to file. The author sees the reason."""
    repo = BugReportRepository(db)
    row = await _find(repo, admin.org_id, report_id)
    row.status = "discarded"
    row.verdict = {
        **(row.verdict or {}),
        "reason": (payload.reason or "").strip() or "Discarded by an admin.",
    }
    await db.commit()
    return _admin_read(row)
