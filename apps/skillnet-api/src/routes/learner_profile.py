"""``/users/me/learner-profile`` (§11.2).

The ``DELETE`` is the art. 17 erasure path §3.3 promised and previously had no
endpoint. It is not a nice-to-have: it deletes the profile, the events, the
feedback, the per-node states and the render views, and anonymizes
``node_renders.generated_by``. Shared renders are **not** deleted — see
``LearnerProfileRepository.erase_user_data``.

``/users/{user_id}`` in ``routes/users.py`` cannot shadow these paths: they carry
an extra segment, so the router order in ``main.py`` is irrelevant.
"""

from fastapi import APIRouter, Response

from src.deps.auth import CurrentUser
from src.deps.db import DBSession
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.learning_event_repo import LearningEventRepository
from src.schemas.learner_profile import LearnerProfileRead, LearnerProfileUpdate
from src.services.learner_profile_service import LearnerProfileService

router = APIRouter(
    prefix="/users/me/learner-profile",
    tags=["Learner profile"],
)


def _service(db: DBSession) -> LearnerProfileService:
    return LearnerProfileService(
        LearnerProfileRepository(db), LearningEventRepository(db)
    )


@router.get("", response_model=LearnerProfileRead)
async def get_learner_profile(user: CurrentUser, db: DBSession) -> LearnerProfileRead:
    """``404`` when there is no profile yet — the client reads that as "do not
    redirect", never as "not onboarded" (§6.1)."""
    profile = await _service(db).get_or_404(user.id)
    return LearnerProfileRead.from_profile(profile)


@router.patch("", response_model=LearnerProfileRead)
async def update_learner_profile(
    user: CurrentUser, db: DBSession, body: LearnerProfileUpdate
) -> LearnerProfileRead:
    """Partial update of the four editable fields; ``preset`` mirrors to ``users``."""
    service = _service(db)
    profile = await service.update_profile(
        user=user, changes=body.model_dump(exclude_unset=True)
    )
    await db.commit()
    return LearnerProfileRead.from_profile(profile)


@router.delete("", status_code=204)
async def delete_learner_profile(user: CurrentUser, db: DBSession) -> Response:
    """RGPD art. 17. Idempotent: erasing twice is a second ``204``, not a 404."""
    await _service(db).erase(user_id=user.id)
    await db.commit()
    return Response(status_code=204)
