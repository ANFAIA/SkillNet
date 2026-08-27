"""Enrollment schemas."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EnrollmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    deadline: date | None = None
    score: float | None = None
    progress: float | None = None
    course_title: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    #: Same **effective** value as ``CourseRead.delivery_mode`` (``resolve_delivery``, so
    #: the schema gate is folded in). It lives here as well as on the course because an
    #: employee cannot call ``GET /courses`` at all -- that route is admin-only -- so
    #: their own two lists ("Mis cursos", the dashboard) have no other way to tell a
    #: node-based course from a v1 one before opening it. ``static`` whenever the course
    #: is not loaded.
    delivery_mode: Literal["static", "dynamic"] = "static"


class EnrollmentCreate(BaseModel):
    """One assignment order: these people get **one course** or **one folder**.

    ``course_id`` alone is the original contract and is unchanged. ``folder_id`` is the
    same order expressed against the library: every **published** course of that folder,
    which is the exact set ``POST /course-folders/{id}/assign`` enrolls — the two entry
    points must not disagree about what "the folder" means, so both read
    ``list_published_course_ids``.

    Exactly one of the two, never both: an order that names a course *and* a folder has
    no single obvious meaning (is the course extra? a filter?), and guessing would make
    a typo silently enroll people in a whole library. Both fields are optional at the
    field level only so this validator can answer with one 422 that says which of the
    two mistakes was made, instead of the bare "field required" of the old signature.
    """

    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    #: Groups whose members are also part of this order.
    #:
    #: **Additive** with ``user_ids``, unlike the target, which stays exclusive: "the
    #: onboarding group and these two contractors" has one obvious meaning, while a
    #: course *and* a folder has none. The server resolves the membership
    #: (``EnrollmentService.resolve_audience``) — the client never sends the people of a
    #: group, because with the people list paginated it does not know them all and would
    #: hit the 100-``user_ids`` cap long before a real group ran out.
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    course_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    deadline: date | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> "EnrollmentCreate":
        if self.course_id is not None and self.folder_id is not None:
            raise ValueError("Provide either course_id or folder_id, not both")
        if self.course_id is None and self.folder_id is None:
            raise ValueError("Provide course_id or folder_id")
        if not self.user_ids and not self.group_ids:
            raise ValueError("Provide user_ids or group_ids")
        return self


class EnrollmentAssignmentResult(BaseModel):
    """What a **folder** assignment did, with the rows it created.

    The single-course branch of ``POST /enrollments`` still answers with a bare
    ``list[EnrollmentRead]`` — every existing caller keeps its contract byte for byte.
    The folder branch cannot: assigning N courses to N people is idempotent (a person
    already enrolled is skipped, not an error), so "created 3 of 8" is the outcome, and
    a list of three rows is indistinguishable from a folder that only had three courses.
    Hence the counts, and hence a second response shape rather than headers — a header
    is invisible to the SPA in development, where Vite serves a different origin than
    the API and nothing is in ``expose_headers``.

    Same three counts, in the same names, as ``CourseFolderAssignmentResult``: it is the
    same operation reached from the other side (person -> folder instead of folder ->
    people), and one vocabulary for it keeps the two screens' wording honest.
    """

    course_count: int
    created_count: int
    skipped_existing_count: int
    #: Distinct people the order landed on, after resolving groups and deduplicating.
    #: ``0`` with a non-empty request means every group was empty or fully deactivated,
    #: which the screen has to say out loud — it looks exactly like success otherwise.
    person_count: int = 0
    #: Group members left out because their account is deactivated. A person named
    #: explicitly in ``user_ids`` is never counted here: naming somebody is an
    #: instruction, and it is honoured.
    skipped_inactive_count: int = 0
    #: The rows just created, capped at ``ENROLLMENT_ECHO_LIMIT``. A group assignment can
    #: create thousands, and serialising them all would make the response the most
    #: expensive part of the request for information the caller did not ask for.
    enrollments: list[EnrollmentRead]
    #: True when ``enrollments`` is a prefix rather than the whole set. Present so the
    #: caller can tell "these are all of them" from "these are the first hundred"
    #: instead of inferring it from a length.
    enrollments_truncated: bool = False
