"""Whether a person may open a course *as a learner*. One gate, every learner surface.

Two rules, and both are about the course rather than the request:

* the caller is enrolled — org scoping is not an access rule, since every colleague
  shares an ``org_id``;
* the course is not archived. "Archived" means *stop showing this course to the
  learners*, and until this module existed it only meant "drop it from the list in
  ``GET /enrollments``": a learner with the URL still opened the course by hand, still
  answered its exercises and still had its documents fed to the tutor. Hiding it was a
  suggestion, not a rule.

**Admins are exempt from both, by role and not by enrollment.** The course library
self-enrols the admin through ``POST /enrollments`` for "Probar curso", so the person
reviewing an archived course is exactly the person who has an enrollment row for it —
gating on the row cannot tell the reviewer from the learner. Role can, which is what
``routes/nodes.py`` and ``services/experience_attempt_service.py`` already did for the
enrollment half of the gate.

**403, not 404.** The neighbouring routes are consistent about which is which: 404 is
for a resource the caller must not learn exists (another organisation's course or
folder; a static course reached through the v2 node surface, which has no nodes at all),
403 for one they demonstrably know about and may not have — ``"You are not enrolled in
this course"``. An enrolled learner opening an archived course is the second case: they
were assigned the course, their progress is still on the enrollment row, and
``POST /courses/{id}/unarchive`` can hand it back tomorrow. A 404 would also make the
SPA say "not found" about a course whose lessons the same person finished last week,
while leaking nothing it does not already know.

Only ``archived`` closes the door. ``draft`` is deliberately left alone: a draft has
never been reachable from the learner's list either, but courses are assigned and edited
in that state and turning "not published" into a 403 would lock people out of a course
mid-revision — a different decision, with a different blast radius.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any, Protocol

from src.core.exceptions import ForbiddenError
from src.models import ContentStatus, UserRole

#: The learner is enrolled but the course was withdrawn. Kept here so every surface says
#: the same sentence and the SPA can match on one string.
ARCHIVED_MESSAGE = "This course has been archived"

#: The message four call sites had spelled out by hand before this module.
NOT_ENROLLED_MESSAGE = "You are not enrolled in this course"


class EnrollmentLookup(Protocol):
    """The one method of ``EnrollmentRepository`` this gate needs.

    A protocol rather than the repository itself so the caller keeps naming
    ``EnrollmentRepository`` in its own module (which is what the route tests
    monkeypatch), and so ``ExerciseService`` and friends can pass the instance they
    already hold instead of a session.
    """

    async def get_by_user_and_course(
        self, user_id: uuid.UUID, course_id: uuid.UUID
    ) -> Any | None: ...  # pragma: no cover - structural type


def _value(raw: object) -> str:
    return raw.value if isinstance(raw, enum.Enum) else str(raw)


def is_admin(user: Any) -> bool:
    return _value(user.role) == UserRole.ADMIN.value


def is_archived(course: Any) -> bool:
    """Whether this course has been withdrawn from the learners.

    ``getattr`` with a fallback, like the projectors in ``routes/courses.py``: the unit
    tests hand these functions course stand-ins, and a row whose status cannot be read
    is not evidence of archiving — the state this asks about is one specific value.
    """
    raw = getattr(course, "status", None)
    if raw is None:
        return False
    return _value(raw) == ContentStatus.ARCHIVED.value


async def assert_learner_can_open(
    *, user: Any, course: Any, enrollments: EnrollmentLookup
) -> Any | None:
    """Raise unless ``user`` may open ``course`` as a learner. Returns their enrollment.

    The row is looked up for an admin too — it is one indexed read, and the alternative
    (returning ``None`` for admins) would have every caller that needs the row run the
    query a second time, which is how ``POST /lessons/{id}/complete`` would have started
    refusing the admin who *is* self-enrolled through "Probar curso". So: ``None`` means
    "no enrollment exists", for anybody, and only an admin gets that far.

    Enrollment is checked before the archive, so everyone who was already being turned
    away gets the sentence they already got; the archive check only ever adds a denial
    for someone who **is** enrolled — the exact hole this module closes.
    """
    enrollment = await enrollments.get_by_user_and_course(user.id, course.id)
    if is_admin(user):
        return enrollment
    if enrollment is None:
        raise ForbiddenError(NOT_ENROLLED_MESSAGE)
    if is_archived(course):
        raise ForbiddenError(ARCHIVED_MESSAGE)
    return enrollment
