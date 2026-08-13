"""Who may enqueue a course-level media artifact (podcast, video, slides, infographic)."""

from __future__ import annotations

import enum
import uuid
from collections.abc import Iterable


def _value(raw: object) -> str:
    return raw.value if isinstance(raw, enum.Enum) else str(raw)


def can_generate_artifacts(
    *,
    role: object,
    user_id: uuid.UUID,
    policy: object,
    generator_ids: Iterable[uuid.UUID],
) -> bool:
    """Admins always can. Everyone else follows the course policy.

    ``admin`` — only admins.
    ``everyone`` — any signed-in person in the org who can already see the course.
    ``selected`` — the listed users (plus admins).
    """
    if _value(role) == "admin":
        return True
    policy_value = _value(policy) if policy is not None else "admin"
    if policy_value == "everyone":
        return True
    if policy_value == "selected":
        return user_id in set(generator_ids)
    return False
