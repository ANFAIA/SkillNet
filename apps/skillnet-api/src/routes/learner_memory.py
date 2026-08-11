"""``/users/me/memory`` — the learner's own narrative memory ("user.md"), GDPR self-service.

Three verbs, employee-only, all scoped to the caller's own row:

* ``GET`` returns the sectioned markdown notebook (the empty skeleton if the learner has no
  history yet) — the GDPR right of access.
* ``PUT`` replaces it with the learner's edited markdown — the right of rectification. The
  body is normalized back to the five canonical sections and size-capped server-side.
* ``DELETE`` blanks the notebook — the right of erasure of *this field only*. Full erasure
  of the whole learner profile stays ``DELETE /users/me/learner-profile``.

There is **no admin route** on purpose: the notebook is the learner's own prose and the
admin never reads it, consistent with the k>=5-aggregates privacy line the rest of the
learner model draws. See ``docs/learner-memory.md``.
"""

from fastapi import APIRouter, Response

from src.core.exceptions import NotFoundError
from src.deps.auth import EmployeeUser
from src.deps.db import DBSession
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.schemas.learner_profile import LearnerMemoryRead, LearnerMemoryUpdate
from src.services.learner_memory import LearnerMemoryService

router = APIRouter(prefix="/users/me/memory", tags=["Learner memory"])


def _service(db: DBSession) -> LearnerMemoryService:
    return LearnerMemoryService(LearnerProfileRepository(db))


async def _read(db: DBSession, user: EmployeeUser) -> LearnerMemoryRead:
    profile = await LearnerProfileRepository(db).get_by_user(user.id)
    service = _service(db)
    return LearnerMemoryRead(
        memory_md=await service.get(user.id),
        memory_updated_at=getattr(profile, "memory_updated_at", None),
    )


@router.get("", response_model=LearnerMemoryRead)
async def get_memory(user: EmployeeUser, db: DBSession) -> LearnerMemoryRead:
    """The learner's notebook. Never 404s: a learner with no row reads the empty skeleton."""
    return await _read(db, user)


@router.put("", response_model=LearnerMemoryRead)
async def put_memory(
    user: EmployeeUser, db: DBSession, body: LearnerMemoryUpdate
) -> LearnerMemoryRead:
    """Replace the notebook with the learner's edited markdown (GDPR rectification)."""
    try:
        await _service(db).set(user_id=user.id, markdown=body.memory_md)
    except LookupError as exc:
        # No profile row yet — nothing to rectify. The learner should complete onboarding
        # (which creates the row) before editing what the app remembers about them.
        raise NotFoundError("learner_profile", str(user.id)) from exc
    await db.commit()
    return await _read(db, user)


@router.delete("", status_code=204)
async def delete_memory(user: EmployeeUser, db: DBSession) -> Response:
    """Erase the notebook (GDPR erasure of this field). Idempotent — a no-op is still 204."""
    await _service(db).clear(user_id=user.id)
    await db.commit()
    return Response(status_code=204)
