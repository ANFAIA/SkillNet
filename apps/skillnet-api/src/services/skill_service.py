"""Skill business logic: taxonomy, who-knows, gap analysis, and verification.

The v1 half of this module is untouched. The v2 half at the bottom is the **two-way
bridge between ``mastery`` and ``user_skills``** that §7 needed and never had:

* **Reading** (``level_for_skill`` / ``mastery_prior_for``) is the probe prior of
  §7.1. Until B11 §7 only ever *wrote* to ``user_skills``, so every learner started
  every node at ``mastery = 0.0`` even when the org had already verified — by a peer
  or by a supervisor — that they know the skill. The prior is only a starting point
  for the EWMA and for ``scaffold_band``; it never skips a node, that is the probe's
  job.
* **Writing** (``record_mastery``) is the ``mastery -> skill_level`` translation of
  §3.3: ``< 0.5 -> low``, ``< 0.85 -> medium``, ``>= 0.85 -> high``, applied **only
  upwards**, exactly as ``_assign_course_skills`` already does for course completion.
  Never downwards: a bad day on one node may not delete a verified competence, and
  ``user_skills`` is what "who knows X" answers to a human looking for help.

Both live here rather than in ``mastery_service`` because they touch the database and
that module is pure by design; and here rather than in
``EnrollmentService._assign_course_skills`` because a node closes long before its
course does.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from src.core.exceptions import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.models.user_skill import SkillLevel, UserSkill
from src.repositories.skill_repo import SkillRepository
from src.services.mastery_service import mastery_prior, skill_level_for

logger = get_logger(__name__)

#: ``user_skills.source`` written when a *node* is what raised the level. Distinct
#: from v1's ``course_completion`` on purpose: the two answer different questions
#: ("finished the course" vs "demonstrated this node"), and the audit trail of a
#: verified skill is worth more than one shared string.
NODE_MASTERY_SOURCE = "node_mastery"

#: Ordering for the never-downgrade rule. Same map ``_assign_course_skills`` uses.
LEVEL_ORDER: dict[SkillLevel, int] = {
    SkillLevel.LOW: 0,
    SkillLevel.MEDIUM: 1,
    SkillLevel.HIGH: 2,
}


def _to_level(value: str) -> SkillLevel:
    try:
        return SkillLevel(value)
    except ValueError as exc:
        raise ValidationError(f"Invalid skill level: {value}", field="level") from exc


def mastery_to_level(mastery: float) -> SkillLevel:
    """``mastery`` -> ``user_skills.level`` (§3.3), as the enum.

    Thin wrapper over the pure ``mastery_service.skill_level_for`` so the thresholds
    live in exactly one place: the same numbers decide the Shu-Ha-Ri phase and the
    target Bloom level, and three copies of ``0.85`` would drift.
    """
    return SkillLevel(skill_level_for(mastery))


class SkillService:
    def __init__(self, repo: SkillRepository) -> None:
        self.repo = repo

    async def list_skills(self, org_id: uuid.UUID) -> list[dict]:
        """Return the full skill taxonomy grouped by category."""
        categories = await self.repo.list_skills(org_id)
        result = []
        for cat in categories:
            result.append(
                {
                    "id": getattr(cat, "id", None),
                    "name": cat.name,
                    "position": cat.position,
                    "skills": [
                        {
                            "id": s.id,
                            "name": s.name,
                            "description": s.description,
                        }
                        for s in cat.skills
                    ],
                }
            )
        return result

    async def who_knows(
        self,
        org_id: uuid.UUID,
        skill_name: str,
        min_level: str | None = None,
    ) -> list[dict]:
        """Find employees who possess a given skill."""
        level_enum = _to_level(min_level) if min_level else None
        rows = await self.repo.who_knows(org_id, skill_name, level_enum)
        return [
            {
                "user_id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "level": level.value,
            }
            for user, level in rows
        ]

    async def get_gap(self, org_id: uuid.UUID) -> list[dict]:
        """Return gap analysis for every skill in the org."""
        return await self.repo.get_gaps(org_id)

    async def verify_skill(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        skill_name: str,
        level: str,
        source: str,
    ) -> dict:
        """Create or update a user's proficiency for a skill.

        If the skill does not exist yet, it is created automatically.
        """
        level_enum = _to_level(level)

        skill = await self.repo.get_by_name(org_id, skill_name)
        if skill is None:
            skill = await self.repo.create(org_id=org_id, name=skill_name)

        user_skill = await self.repo.upsert_user_skill(
            user_id=user_id,
            skill_id=skill.id,
            level=level_enum,
            source=source,
        )
        return {
            "user_skill_id": user_skill.id,
            "user_id": user_skill.user_id,
            "skill_id": user_skill.skill_id,
            "skill_name": skill.name,
            "level": user_skill.level.value,
            "source": user_skill.source,
        }

    async def get_user_skills(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[dict]:
        """Return all skills for a given user."""
        user_skills = await self.repo.get_user_skills(org_id, user_id)
        return [
            {
                "id": us.id,
                "skill_id": us.skill_id,
                "skill_name": us.skill.name,
                "level": us.level.value,
                "source": us.source,
                "last_assessed_at": us.last_assessed_at,
            }
            for us in user_skills
        ]

    # ------------------------------------------------------------------
    # v2: the mastery <-> user_skills bridge (§3.3, §7.1)
    # ------------------------------------------------------------------

    async def level_for_skill(
        self, *, user_id: uuid.UUID, skill_id: uuid.UUID | None
    ) -> SkillLevel | None:
        """The level this user already holds for one skill, or ``None``.

        ``skill_id`` is nullable on ``course_nodes`` (a node need not map to a skill),
        so ``None`` in gives ``None`` out and the caller does not have to guard.
        Deliberately a plain ``select`` against ``self.repo.session`` rather than a new
        ``SkillRepository`` method: ``src/repositories/skill_repo.py`` is a v1 file this
        batch may not edit (§13), and a single-column read has no business logic to
        hide.
        """
        if skill_id is None:
            return None
        query = select(UserSkill.level).where(
            UserSkill.user_id == user_id, UserSkill.skill_id == skill_id
        )
        return (await self.repo.session.execute(query)).scalars().first()

    async def mastery_prior_for(
        self, *, user_id: uuid.UUID, skill_id: uuid.UUID | None
    ) -> float:
        """The §7.1 seed for ``learner_node_states.mastery``.

        ``{"high": 0.85, "medium": 0.55, "low": 0.25}``, and ``0.0`` when the org has
        never verified anything for this skill.
        """
        return mastery_prior(await self.level_for_skill(user_id=user_id, skill_id=skill_id))

    async def record_mastery(
        self,
        *,
        user_id: uuid.UUID,
        skill_id: uuid.UUID | None,
        mastery: float,
        source: str = NODE_MASTERY_SOURCE,
    ) -> SkillLevel | None:
        """Translate a node's ``mastery`` into ``user_skills.level``, upwards only.

        Returns the level the row ends up at, or ``None`` when there was nothing to do
        (no ``skill_id``, or the existing level is already at least as high). The
        no-downgrade rule is not politeness: ``user_skills`` feeds "who knows X", the
        gap analysis and the probe prior, so a single weak answer must not be able to
        retract a competence a human verified.
        """
        if skill_id is None:
            return None

        target = mastery_to_level(mastery)
        query = select(UserSkill).where(
            UserSkill.user_id == user_id, UserSkill.skill_id == skill_id
        )
        existing = (await self.repo.session.execute(query)).scalar_one_or_none()

        if existing is not None:
            if LEVEL_ORDER[existing.level] >= LEVEL_ORDER[target]:
                return None
            existing.level = target
            existing.source = source
            existing.last_assessed_at = datetime.now(timezone.utc)
            await self.repo.session.flush()
            logger.info(
                "Raised user_skill %s for user %s to %s from mastery %.2f",
                skill_id,
                user_id,
                target.value,
                mastery,
            )
            return target

        self.repo.session.add(
            UserSkill(
                user_id=user_id,
                skill_id=skill_id,
                level=target,
                source=source,
                last_assessed_at=datetime.now(timezone.utc),
            )
        )
        await self.repo.session.flush()
        logger.info(
            "Granted user_skill %s to user %s at %s from mastery %.2f",
            skill_id,
            user_id,
            target.value,
            mastery,
        )
        return target


__all__ = [
    "LEVEL_ORDER",
    "NODE_MASTERY_SOURCE",
    "SkillService",
    "mastery_to_level",
]
