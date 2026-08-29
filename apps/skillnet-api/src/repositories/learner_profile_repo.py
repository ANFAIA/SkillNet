"""``learner_profiles`` data access, plus the art. 17 erasure unit.

``erase_user_data`` deliberately spans **eight** tables. It lives here, next to the
profile, because "erase everything this learner generated" is one atomic
requirement of §3.3/§11.2 and splitting it across eight repositories would make it
possible to forget a table and still look correct.

That is not hypothetical: an early version of this function skipped two of them and
still answered ``204``, leaving behind exactly the two tables that store
what the employee *wrote* (``node_attempts.answer``, ``node_probes.answers``). The
list below is the whole contract; ``tests/test_gdpr_erasure.py`` asserts it table
by table so a new personal table cannot be added without failing a test.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.learner_activity_state import LearnerActivityState
from src.models.learner_node_state import LearnerNodeState
from src.models.learner_profile import LearnerProfile
from src.models.learning_event import LearningEvent
from src.models.learning_experience import ExperienceAttempt
from src.models.node_attempt import NodeAttempt
from src.models.node_probe import NodeProbe
from src.models.node_render import NodeRender
from src.models.node_render_view import NodeRenderView
from src.repositories.base import BaseRepository

# Every table that holds rows belonging to one learner, in deletion order. The
# order is dictated by the FKs of ``0005_dynamic_courses.py``:
# ``node_attempts.probe_id -> node_probes.id ON DELETE SET NULL``, so attempts go
# first and the SET NULL never has to fire (it would be an extra UPDATE over rows
# that are about to disappear, and on a big erasure that is the difference between
# one statement and two). Nothing else in the list references anything else in it:
# ``learner_node_states.active_render_id`` and ``node_attempts.render_id`` point at
# ``node_renders``, which is anonymized rather than deleted. ``learner_activity_states``
# holds one learner's failure and disclosure counts per activity, so it is as personal as
# an attempt row and is deleted with the rest.
ERASURE_ORDER: tuple[tuple[str, type, object], ...] = (
    ("node_render_views", NodeRenderView, NodeRenderView.user_id),
    ("experience_attempts", ExperienceAttempt, ExperienceAttempt.user_id),
    ("node_attempts", NodeAttempt, NodeAttempt.user_id),
    ("learner_activity_states", LearnerActivityState, LearnerActivityState.user_id),
    ("node_probes", NodeProbe, NodeProbe.user_id),
    ("learner_node_states", LearnerNodeState, LearnerNodeState.user_id),
    ("learning_events", LearningEvent, LearningEvent.user_id),
    ("learner_profiles", LearnerProfile, LearnerProfile.user_id),
)


class LearnerProfileRepository(BaseRepository[LearnerProfile]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LearnerProfile)

    async def get_by_user(self, user_id: uuid.UUID) -> LearnerProfile | None:
        query = select(LearnerProfile).where(LearnerProfile.user_id == user_id)
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_or_create(
        self, *, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> LearnerProfile:
        """Fetch the single row of ``UNIQUE (user_id)`` or insert a default one."""
        existing = await self.get_by_user(user_id)
        if existing is not None:
            return existing
        profile = LearnerProfile(
            user_id=user_id,
            org_id=org_id,
            format_vector={"texto": 0, "ejercicio": 0, "codigo": 0, "dato": 0},
            tutor_notes={},
        )
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def erase_user_data(self, user_id: uuid.UUID) -> dict[str, int]:
        """Delete every learner-generated row of one user; anonymize renders.

        Every table in ``ERASURE_ORDER`` is deleted in dependency order. Both
        ``experience_attempts`` and legacy ``node_attempts`` may hold answers or scored
        results, so an erasure that skipped either would return ``204`` for a promise it
        had not kept. ``normalized_evidence`` follows its attempt by ``ON DELETE CASCADE``.

        ``node_renders`` is **shared** between learners (``UNIQUE (cache_key)``,
        no ``user_id``), so it is not deleted: ``generated_by`` is set to ``NULL``.
        Deleting it would destroy content other employees are looking at and the
        evidence behind their certificates (§3.4).

        Flushes; the route commits.
        """
        counts: dict[str, int] = {}

        anonymized = await self.session.execute(
            update(NodeRender)
            .where(NodeRender.generated_by == user_id)
            .values(generated_by=None)
        )
        counts["node_renders_anonymized"] = anonymized.rowcount or 0

        for label, model, column in ERASURE_ORDER:
            result = await self.session.execute(delete(model).where(column == user_id))
            counts[label] = result.rowcount or 0

        await self.session.flush()
        return counts
