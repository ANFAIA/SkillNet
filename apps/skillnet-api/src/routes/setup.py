"""First-boot setup: a public, single-shot flow to initialize a fresh deployment.

`GET /setup/status` tells the SPA whether the deployment has an owner yet.
`POST /setup` creates that owner and fixes the workspace mode — but only while no
user exists. Once one does, it is closed forever (409). This is the UI-first
alternative to the headless `ADMIN_EMAIL`/`ADMIN_PASSWORD` bootstrap; the two
never collide, since a deployment created either way reports `initialized`.

See docs/design/audience-modes.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users.password import PasswordHelper
from sqlalchemy import select

from src.auth.backend import get_database_strategy
from src.config import settings
from src.core.bootstrap import ensure_organization
from src.core.exceptions import ConflictError
from src.deps.auth import auth_backend
from src.deps.db import DBSession
from src.models import User, UserRole, WorkspaceMode
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.schemas.setup import SetupRequest, SetupStatus
from src.services.capabilities import derive_capabilities

router = APIRouter(prefix="/setup", tags=["Setup"])


async def _has_any_user(db: DBSession) -> bool:
    return (await db.execute(select(User).limit(1))).scalar_one_or_none() is not None


@router.get("/status", response_model=SetupStatus)
async def setup_status(db: DBSession) -> SetupStatus:
    return SetupStatus(
        initialized=await _has_any_user(db),
        onboarding_enabled=settings.ONBOARDING_ENABLED,
        capabilities=derive_capabilities(),
    )


@router.post("")
async def setup(
    body: SetupRequest,
    db: DBSession,
    strategy: DatabaseStrategy = Depends(get_database_strategy),
) -> Response:
    """Create the owner and set the workspace mode, then sign them in.

    Guarded by "no user exists": the check and the insert share one transaction,
    so a second concurrent call fails on the unique email/atomic commit rather
    than creating a second owner.
    """
    if await _has_any_user(db):
        raise ConflictError("This deployment is already set up.")

    mode = WorkspaceMode(body.workspace_mode)
    org = await ensure_organization(db)
    org.workspace_mode = mode
    # In an individual workspace the org name is derived, not asked; in an
    # organization it is required (the frontend enforces it too).
    if mode is WorkspaceMode.INDIVIDUAL:
        org.name = (body.org_name or "").strip() or "Mi espacio"
    else:
        org.name = (body.org_name or "").strip() or org.name

    owner = User(
        email=body.owner_email,
        hashed_password=PasswordHelper().hash(body.owner_password),
        org_id=org.id,
        full_name=body.owner_full_name.strip(),
        role=UserRole.ADMIN,
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )
    db.add(owner)
    await db.flush()

    # In an individual workspace the owner also learns, so give them a learner
    # profile now (onboarding not yet completed) — the onboarding gate then fires
    # on first entry, exactly as for an employee. An organization admin does not
    # learn, so gets none. See docs/design/audience-modes.md.
    if mode is WorkspaceMode.INDIVIDUAL:
        await LearnerProfileRepository(db).get_or_create(
            user_id=owner.id, org_id=org.id
        )

    await db.commit()
    await db.refresh(owner)

    # Auto-login: issue the session cookie so the SPA can go straight on to
    # onboarding without a second sign-in step.
    return await auth_backend.login(strategy, owner)
