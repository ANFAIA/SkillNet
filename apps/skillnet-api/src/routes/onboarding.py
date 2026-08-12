"""Onboarding endpoints (§11.2)."""

from fastapi import APIRouter

from src.deps.auth import CurrentUser
from src.deps.db import DBSession
from src.models import Organization
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.learning_event_repo import LearningEventRepository
from src.schemas.learner_profile import LearnerProfileRead
from src.schemas.onboarding import (
    ONBOARDING_VERSION,
    PRIVACY_NOTICE,
    OnboardingRead,
    OnboardingSubmit,
    build_questions,
)
from src.services.learner_profile_service import LearnerProfileService

router = APIRouter(
    prefix="/onboarding",
    tags=["Onboarding"],
)


def _service(db: DBSession) -> LearnerProfileService:
    return LearnerProfileService(
        LearnerProfileRepository(db), LearningEventRepository(db)
    )


async def _org_sector(db: DBSession, org_id) -> str | None:
    """Sector configured on the organization, used to seed the role suggestions.

    Read with an explicit ``get`` instead of ``user.organization`` because the
    relationship is lazy and would raise under the async session.
    """
    org = await db.get(Organization, org_id)
    if org is None:
        return None
    settings_blob = org.settings or {}
    sector = settings_blob.get("sector")
    return str(sector) if sector else None


@router.get("", response_model=OnboardingRead, response_model_exclude_none=True)
async def get_onboarding(user: CurrentUser, db: DBSession) -> OnboardingRead:
    """The five questions, plus whether this learner has already been asked."""
    service = _service(db)
    profile = await service.get(user.id)
    sector = await _org_sector(db, user.org_id)
    return OnboardingRead(
        version=ONBOARDING_VERSION,
        completed=profile is not None and profile.onboarding_completed_at is not None,
        notice=PRIVACY_NOTICE,
        questions=build_questions(sector=sector),
    )


@router.post("", response_model=LearnerProfileRead)
async def submit_onboarding(
    user: CurrentUser, db: DBSession, body: OnboardingSubmit
) -> LearnerProfileRead:
    """Writes ``learner_profiles`` + ``users.learning_profile`` +
    ``users.accessibility`` in a single transaction (§11.2)."""
    service = _service(db)
    sector = body.sector or await _org_sector(db, user.org_id)
    profile = await service.complete_onboarding(
        user=user,
        role_title=body.role_title,
        sector=sector,
        goal=body.goal,
        experience_level=body.experience_level,
        preset=body.preset,
        accessibility=(
            body.accessibility.model_dump() if body.accessibility is not None else None
        ),
        learning_preferences=(
            body.learning_preferences.model_dump()
            if body.learning_preferences is not None
            else None
        ),
    )
    await db.commit()
    return LearnerProfileRead.from_profile(profile)


@router.post("/skip", response_model=LearnerProfileRead)
async def skip_onboarding(user: CurrentUser, db: DBSession) -> LearnerProfileRead:
    """"Lo hago luego": marks it answered with ``experience_level = 'unknown'``.

    Not ``'none'``: ``'none'`` declares being a novice and forces novice
    scaffolding, which is precisely the case that hurts the expert (§6.1).
    """
    service = _service(db)
    profile = await service.skip_onboarding(user=user)
    await db.commit()
    return LearnerProfileRead.from_profile(profile)
