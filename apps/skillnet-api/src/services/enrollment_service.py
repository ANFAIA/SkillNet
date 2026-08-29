"""Enrollment business logic: assignment, progress, and removal rules.

Two closing rules live here, and they must never mix:

* **v1 (static).** ``complete()``: every lesson visited and every exercise passed.
  Byte-for-byte the rule it has always been. Driven by the learner pressing "he
  terminado" on ``POST /enrollments/{id}/complete``.
* **v2 (dynamic).** §7.5: every non-archived ``critical`` node of the course is
  ``mastered`` — by demonstration, by probe or by ``waive``. ``recommended`` and
  ``contextual`` never block. Nobody presses anything: the enrollment closes the moment
  the last critical node closes, and it can *reopen* when the creator adds a new critical
  node. **It writes no ``score``**: a finished dynamic course says that it was finished
  (see :func:`apply_dynamic_closure`).

Which means ``enrollments.score`` is now written by the v1 rule alone, where it has
always held the completed-lessons fraction. That is the one meaning it has going
forward; the rows the v2 rule wrote before this change hold mean mastery instead, and
the ``AVG`` in ``routes/stats.py`` still averages both together. Nothing here can fix
that — it is history in a column — but nothing here adds to it either.

Which of the two applies is decided by ``resolve_delivery`` — the single decision point
of §10.1 — everywhere except one place, ``CourseSchemaService.recompute_enrollment_closure``,
where it cannot be: ``PUT /courses/{id}/schema`` runs while the course is still
``proposed``, so the course is *by construction* not dynamic yet at the moment §7.5
requires the recompute. The gate that *is* correct there is inside
:func:`apply_dynamic_closure`: with no node at all the verdict has no opinion, so a pure
v1 course — which has no ``course_nodes`` — cannot have its enrollments touched by an
admin editing somebody else's schema.

The rule itself is not written twice. ``mastery_service.evaluate_course_completion`` is
the pure form (unit-testable with plain dataclasses, no DB) and
:func:`apply_dynamic_closure` is the one function that turns its verdict into a mutation
of an ``enrollments`` row. ``CourseSchemaService.recompute_enrollment_closure`` calls
both, so the schema editor and the runtime can never disagree about what "completed"
means — which matters because completion is the whole of what a certificate now asserts.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from src.core.logging import get_logger
from src.models import Enrollment, EnrollmentStatus, User
from src.models.course_skill import CourseSkill
from src.models.user_skill import SkillLevel, UserSkill
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.user_group_repo import UserGroupRepository
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.repositories.lesson_progress_repo import LessonProgressRepository
from src.services.course_delivery import resolve_delivery
from src.services.mastery_service import (
    CourseCompletion,
    evaluate_course_completion,
)
from src.services.skill_service import mastery_to_level

logger = get_logger(__name__)

#: Where a dynamic enrollment goes when it stops being complete. Not ``ASSIGNED``:
#: the learner demonstrably started, and sending them back to "sin empezar" would
#: lose that fact and re-trigger every "tienes formación nueva" surface.
REOPENED_STATUS = EnrollmentStatus.IN_PROGRESS

#: The largest (people x courses) an assignment order may be.
#:
#: Groups made this reachable. Assigning a folder of 30 courses to a group of 400 people
#: is 12 000 enrollment rows in one request: the write alone outlives any reverse proxy's
#: timeout, and the admin gets a 504 with no idea whether anything landed (nothing did —
#: the route commits once — but the screen cannot say so). A 422 that names the number is
#: worth more than a hang, and it is the honest answer until assignment is a background
#: job. Read as a ceiling on *work*, not on people: 400 people and one course is fine.
MAX_ASSIGNMENT_PAIRS = 5_000


@dataclass(frozen=True)
class ResolvedAudience:
    """Who an assignment order actually lands on, and who it deliberately missed.

    Groups are expanded **here and nowhere else**. The browser never sends the members
    of a group: with the people list paginated it does not know them all, and it would
    run into the 100-``user_ids`` cap of the request body long before a real group ran
    out. One expansion point also means "who is in this group" is answered once, at the
    moment of the write, instead of once in the client and once again on the server.
    """

    #: Every person to enrol, deduplicated, explicit ids first and then group members.
    user_ids: list[uuid.UUID]
    #: Group members left out because their account is deactivated.
    skipped_inactive: int
    #: Which group each person got here through, for the people who got here *only*
    #: through a group. Absent for anyone the caller named directly — naming somebody is
    #: not the group's doing, and recording it as such would make a future
    #: "revoke what this group assigned" take back a row the group never created.
    #: Absent too for anyone in two of the named groups: either answer would be a coin
    #: toss written down as a fact.
    source_group_by_user: dict[uuid.UUID, uuid.UUID]


@dataclass(frozen=True)
class NodeProgressRow:
    """One ``(course_nodes, learner_node_states)`` pair, as §7.5 needs it.

    ``mastery_service.NodeProgressLike`` is a structural protocol, so this is only a
    convenience: neither half of the rule lives in a single table, and the ORM has no
    row shaped like the join.
    """

    node_id: uuid.UUID
    criticality: Any
    archived: bool
    state: str
    mastery: float
    #: ``learner_node_states.completed_at``: the learner reached the end of the node
    #: (migration 0029). Defaulted so the two call sites that predate it keep compiling
    #: while reading as "never recorded a finish", which is what a missing row means.
    completed_at: datetime | None = None
    #: The two halves of ``mastery_service.node_was_measured``. Defaulted for the same
    #: reason as above, and to the same effect: a learner with no row on a node was asked
    #: nothing there, so "no attempts, no probe" is the truth and not a placeholder.
    attempts_count: int = 0
    probe_score: float | None = None


def apply_dynamic_closure(
    enrollment: Any,
    completion: CourseCompletion,
    *,
    now: datetime | None = None,
) -> str | None:
    """Move one enrollment to match the §7.5 verdict. Returns what happened.

    ``"completed"``, ``"reopened"`` or ``None`` when the row already agreed with the
    verdict. Pure apart from the clock, so both callers (the runtime and the schema
    editor) share one definition of the mutation and not just of the predicate.

    **It does not write ``enrollments.score``, and that is the point of the column now.**
    It used to write ``completion.score``, the mean ``mastery`` over every node, and that
    number was presented as the mark of the course. It could not distinguish a node
    nobody was asked about from one answered wrong, so a course of expository nodes read
    from end to end went on the record at 0.0 — see ``evaluate_course_completion`` for
    the full argument. The column is left alone rather than removed: it holds the history
    of enrollments already closed, and the v1 rule still writes its own meaning into it.
    Not writing is therefore also what keeps the two meanings from mixing any further.

    ``total_critical == 0`` (now: the course has *no* non-archived node) is treated as
    **"no opinion"**, never as "not complete": an empty course mid-edit cannot be
    evaluated, and reopening every completed enrollment because the creator momentarily
    deleted the last node would corrupt real records for a transient state. A
    *validated* course always has at least one node, so it never reaches this branch.
    """
    if completion.total_critical == 0:
        return None

    moment = now or datetime.now(timezone.utc)
    if completion.can_complete and enrollment.status != EnrollmentStatus.COMPLETED:
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = moment
        return "completed"
    if not completion.can_complete and enrollment.status == EnrollmentStatus.COMPLETED:
        enrollment.status = REOPENED_STATUS
        enrollment.completed_at = None
        # A reopened enrollment is `in_progress`, and an `in_progress` row with no
        # `started_at` is what "Cursos activos" and the learner dashboard read as never
        # begun. Backfilled only when it is missing, so a real start date is never moved.
        if getattr(enrollment, "started_at", None) is None:
            enrollment.started_at = moment
        return "reopened"
    return None


class EnrollmentService:
    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        course_repo: CourseRepository,
        exercise_repo: ExerciseRepository,
        lesson_progress_repo: LessonProgressRepository | None = None,
        user_group_repo: UserGroupRepository | None = None,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.course_repo = course_repo
        self.exercise_repo = exercise_repo
        self.lesson_progress_repo = lesson_progress_repo or LessonProgressRepository(
            enrollment_repo.session
        )
        # Defaulted from the session for the same reason as `lesson_progress_repo`: every
        # caller already hands over three repositories built from one session, and a
        # fourth positional argument at each of them buys nothing.
        self.user_group_repo = user_group_repo or UserGroupRepository(
            enrollment_repo.session
        )

    async def _assert_users_in_org(
        self, *, org_id: uuid.UUID, user_ids: Iterable[uuid.UUID]
    ) -> None:
        """Refuse to enrol a learner who belongs to another organisation.

        The course is already scoped to ``org_id`` by ``get_scoped``, but nothing
        constrained the ``user_ids``: an admin of org A could enrol a learner of org B,
        producing a row whose two ends live in different tenants. It surfaced in the
        learner's "My Courses" (title visible) and then 404'd on open. This closes the
        write path; the read path in ``enrollment_repo.list_enrollments`` also filters
        by ``Course.org_id`` so any pre-existing mismatch stays hidden without deletion.
        """
        wanted = {uid for uid in user_ids}
        if not wanted:
            return
        result = await self.enrollment_repo.session.execute(
            select(User.id).where(User.id.in_(wanted), User.org_id == org_id)
        )
        found = {row[0] for row in result.all()}
        missing = wanted - found
        if missing:
            raise ForbiddenError(
                "Cannot enrol users from another organisation: "
                + ", ".join(str(uid) for uid in sorted(missing, key=str))
            )

    async def resolve_audience(
        self,
        *,
        org_id: uuid.UUID,
        user_ids: Sequence[uuid.UUID],
        group_ids: Sequence[uuid.UUID] = (),
    ) -> ResolvedAudience:
        """Turn "these people and these groups" into one deduplicated list of people.

        The **only** place a group becomes a list of users. See :class:`ResolvedAudience`
        for why that expansion must not happen in the browser.

        Two rules that look inconsistent and are not:

        * A **named** person is enrolled even if their account is deactivated. Naming
          somebody is an instruction, and refusing it silently would be the surprise.
        * A **group member** who is deactivated is not, and is counted in
          ``skipped_inactive`` so the screen can say so. Resolving a group is a question
          — "who should get this?" — and the answer does not include people who cannot
          sign in. They stay members, so reactivating them puts them back in scope for
          the next assignment.

        An unknown or foreign group is a 404 before anything is written, so a typo in one
        of several ids cannot half-assign the order.
        """
        unknown = set(group_ids) - await self.user_group_repo.scoped_ids(
            list(group_ids), org_id
        )
        if unknown:
            raise NotFoundError(
                "user_groups", ", ".join(str(gid) for gid in sorted(unknown, key=str))
            )
        await self._assert_users_in_org(org_id=org_id, user_ids=user_ids)

        named = set(user_ids)
        rows = await self.user_group_repo.memberships(list(group_ids), org_id)
        members: list[uuid.UUID] = []
        provenance: dict[uuid.UUID, uuid.UUID] = {}
        ambiguous: set[uuid.UUID] = set()
        inactive: set[uuid.UUID] = set()
        for group_id, member_id, is_active in rows:
            if not is_active:
                # Not enrolled, but still counted — and never given provenance, since no
                # row will exist to carry it.
                if member_id not in named:
                    inactive.add(member_id)
                continue
            if member_id not in named and member_id not in members:
                members.append(member_id)
            if member_id in named:
                continue
            if member_id in provenance and provenance[member_id] != group_id:
                ambiguous.add(member_id)
            provenance.setdefault(member_id, group_id)
        for member_id in ambiguous:
            del provenance[member_id]

        # Explicit ids first, then group members: `dict.fromkeys` keeps first occurrence,
        # so someone named *and* in a group appears once, in the position the caller put
        # them. The order is what `POST /enrollments` echoes back for the legacy shape.
        resolved = list(dict.fromkeys([*user_ids, *members]))
        return ResolvedAudience(
            user_ids=resolved,
            # A deactivated person who was *also* named explicitly is enrolled, so they
            # are not "skipped" and must not be counted as such.
            skipped_inactive=len(inactive),
            source_group_by_user=provenance,
        )

    @staticmethod
    def _assert_within_limit(*, people: int, courses: int) -> None:
        pairs = people * courses
        if pairs > MAX_ASSIGNMENT_PAIRS:
            raise ValidationError(
                f"This assignment is {pairs} enrollments "
                f"({people} people x {courses} courses), over the limit of "
                f"{MAX_ASSIGNMENT_PAIRS}. Split it into smaller orders.",
                field="user_ids",
            )

    async def _enrol_once(
        self,
        *,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
        assigned_by: uuid.UUID,
        deadline: date | None,
        source_group_id: uuid.UUID | None = None,
        known_existing: set[tuple[uuid.UUID, uuid.UUID]] | None = None,
    ) -> tuple[Enrollment, bool]:
        """Enrol one learner in one course. Returns ``(row, created)``.

        The single write used by both assignment entry points, so they cannot disagree
        about what "already enrolled" means.

        Check-then-insert is not enough on its own: two concurrent requests (a
        double-clicked "assign" button is the everyday case) both see no row and both
        insert, and the loser violates ``uq_enrollments_user_course``. That
        ``IntegrityError`` is not an ``AppError``, so it left the API as a 500. The
        insert therefore runs inside a SAVEPOINT: when it fails, only the savepoint is
        rolled back — the surrounding transaction stays usable, which matters because
        this runs inside a loop over a whole batch — and the row the winner wrote is
        read back and treated as what it is, an enrollment that already exists.
        """
        # `known_existing` is the batch's one-query snapshot of what is already enrolled
        # (`existing_pairs`). A pair it does not contain still goes through the insert
        # below and can still lose the race, which the savepoint handles; a pair it does
        # contain is fetched, not guessed, so the caller gets the same row it always did.
        if known_existing is not None and (user_id, course_id) not in known_existing:
            existing = None
        else:
            existing = await self.enrollment_repo.get_by_user_and_course(
                user_id, course_id
            )
        if existing is not None:
            return existing, False

        session = self.enrollment_repo.session
        try:
            async with session.begin_nested():
                enrollment = await self.enrollment_repo.create(
                    user_id=user_id,
                    course_id=course_id,
                    assigned_by=assigned_by,
                    status=EnrollmentStatus.ASSIGNED,
                    deadline=deadline,
                    source_group_id=source_group_id,
                )
        except IntegrityError:
            existing = await self.enrollment_repo.get_by_user_and_course(
                user_id, course_id
            )
            if existing is None:
                # Some other constraint failed — a dangling user or course id, say.
                # Nothing here can honestly recover from that.
                raise
            logger.info(
                "Enrollment of user %s in course %s lost the insert race; "
                "reusing the existing row",
                user_id,
                course_id,
            )
            return existing, False
        return enrollment, True

    async def assign(
        self,
        *,
        org_id: uuid.UUID,
        assigned_by: uuid.UUID,
        course_id: uuid.UUID,
        user_ids: list[uuid.UUID],
        deadline: date | None,
    ) -> list[Enrollment]:
        """Enrol a batch of learners in one course, idempotently.

        **A learner who is already enrolled is not an error.** This used to raise
        ``ConflictError`` on the first such learner and abort the whole batch, so
        assigning a course to ten people failed entirely — writing nothing — because one
        of them already had it. ``assign_courses`` had always skipped instead, and the
        two disagreeing was the bug.

        Returns one row **per requested user**, in the requested order: the enrollment
        just created, or the one that already existed. ``POST /enrollments`` answers
        ``list[EnrollmentRead]`` and its callers read that list as the result of what
        they asked for, so dropping the already-enrolled users would turn "9 of 10
        already had it" into a response that looks like nine assignments failed.
        Duplicate ids in ``user_ids`` collapse to one row.

        No ``source_group_id``: this branch is only reached when the caller named people
        directly. An order that names a group goes through :meth:`assign_courses`, which
        is also the one that can report created-versus-already-there — see
        ``POST /enrollments``.
        """
        course = await self.course_repo.get_scoped(course_id, org_id)
        if course is None:
            raise NotFoundError("courses", str(course_id))
        await self._assert_users_in_org(org_id=org_id, user_ids=user_ids)
        people = list(dict.fromkeys(user_ids))
        self._assert_within_limit(people=len(people), courses=1)

        known_existing = await self.enrollment_repo.existing_pairs([course_id], people)
        enrollments: list[Enrollment] = []
        for user_id in people:
            enrollment, _created = await self._enrol_once(
                user_id=user_id,
                course_id=course_id,
                assigned_by=assigned_by,
                deadline=deadline,
                known_existing=known_existing,
            )
            enrollments.append(enrollment)
        return enrollments

    async def assign_courses(
        self,
        *,
        org_id: uuid.UUID,
        assigned_by: uuid.UUID,
        course_ids: Sequence[uuid.UUID],
        user_ids: list[uuid.UUID],
        deadline: date | None,
        source_group_by_user: Mapping[uuid.UUID, uuid.UUID] | None = None,
    ) -> tuple[list[Enrollment], int]:
        """Assign a published collection while treating existing rows as idempotent.

        The size of this loop is (people x courses), which groups made large. The reads
        are hoisted into two queries — one for the courses, one for every existing pair —
        so what is left inside the loop is the insert itself and the savepoint that keeps
        a lost race from taking the batch down. :meth:`_assert_within_limit` refuses an
        order too big for one request before any of it runs.
        """
        await self._assert_users_in_org(org_id=org_id, user_ids=user_ids)
        people = list(dict.fromkeys(user_ids))
        courses = list(dict.fromkeys(course_ids))
        self._assert_within_limit(people=len(people), courses=len(courses))

        for course_id in courses:
            # Still one lookup per course, and still before the first write: a folder
            # holding a course of another organization must assign nothing at all.
            if await self.course_repo.get_scoped(course_id, org_id) is None:
                raise NotFoundError("courses", str(course_id))

        known_existing = await self.enrollment_repo.existing_pairs(courses, people)
        created: list[Enrollment] = []
        skipped = 0
        for course_id in courses:
            for user_id in people:
                enrollment, was_created = await self._enrol_once(
                    user_id=user_id,
                    course_id=course_id,
                    assigned_by=assigned_by,
                    deadline=deadline,
                    source_group_id=(source_group_by_user or {}).get(user_id),
                    known_existing=known_existing,
                )
                if was_created:
                    created.append(enrollment)
                else:
                    skipped += 1
        return created, skipped

    async def get_scoped(
        self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID
    ) -> Enrollment:
        enrollment = await self.enrollment_repo.get_with_course(enrollment_id)
        if enrollment is None or enrollment.course.org_id != org_id:
            raise NotFoundError("enrollments", str(enrollment_id))
        return enrollment

    async def list_enrollments(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        course_id: uuid.UUID | None,
        status: EnrollmentStatus | None,
        offset: int,
        limit: int,
        include_archived_courses: bool = True,
        #: Plural forms of the two filters above. ``None`` means "no filter"; an empty
        #: list means "none of them" and answers nothing. See the repository.
        user_ids: Sequence[uuid.UUID] | None = None,
        course_ids: Sequence[uuid.UUID] | None = None,
    ) -> tuple[Sequence[Enrollment], int]:
        """List enrollments; see the repository for what ``include_archived_courses`` is.

        Short version: pass ``False`` for a learner's own list — an archived course must
        not appear there — and leave the default for the admin surfaces, which want the
        history.
        """
        return await self.enrollment_repo.list_enrollments(
            org_id=org_id,
            user_id=user_id,
            user_ids=user_ids,
            course_id=course_id,
            course_ids=course_ids,
            status=status,
            include_archived_courses=include_archived_courses,
            offset=offset,
            limit=limit,
        )

    async def compute_progress(
        self, *, enrollment: Enrollment, org_id: uuid.UUID
    ) -> float | None:
        """Fraction of lessons completed (v1) or mastered critical nodes (v2).

        **v1 (static):**
        A lesson is "completed" when:
        - it has been visited (a ``LessonProgress`` row exists), AND
        - all its exercises (if any) have a passing attempt.
        Progress = completed_lessons / total_lessons.

        **v2 (dynamic):**
        Progress = mastered_critical_nodes / total_critical_nodes (§7.5).
        Falls back to 0.0 when the course has neither modules nor nodes.
        """
        course = await self.course_repo.get_detail(enrollment.course_id, org_id)
        if course is None:
            return 0.0

        # Delivery mode wins over storage shape. Dynamic demo courses deliberately keep
        # their v1 modules as a fallback, but those lessons must never shadow §7.5's
        # mastered-critical-node progress once the validated schema activates v2.
        if resolve_delivery(course) == "dynamic":
            completion = await self.evaluate_dynamic(
                course_id=enrollment.course_id, user_id=enrollment.user_id
            )
            return completion.progress_percent / 100.0

        if not course.modules:
            # Neither static modules nor an active dynamic schema: genuinely empty.
            return 0.0

        all_lessons = [
            lesson
            for module in course.modules
            for lesson in module.lessons
        ]
        if not all_lessons:
            return 1.0

        # Gather all lesson & exercise ids for batch queries.
        all_lesson_ids = [lesson.id for lesson in all_lessons]
        all_exercise_ids = [
            exercise.id
            for lesson in all_lessons
            for exercise in lesson.exercises
        ]

        visited = await self.lesson_progress_repo.completed_lesson_ids(
            user_id=enrollment.user_id, lesson_ids=all_lesson_ids
        )
        passed = await self.exercise_repo.passed_exercise_ids(
            user_id=enrollment.user_id, exercise_ids=all_exercise_ids
        )

        completed = 0
        for lesson in all_lessons:
            if lesson.id not in visited:
                continue
            lesson_exercise_ids = [ex.id for ex in lesson.exercises]
            if all(eid in passed for eid in lesson_exercise_ids):
                completed += 1

        return completed / len(all_lessons)

    async def complete(
        self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Enrollment, float]:
        """Mark an enrollment as completed, compute and store the final score.

        Returns the updated enrollment and its progress value.
        """
        enrollment = await self.get_scoped(
            enrollment_id=enrollment_id, org_id=org_id
        )
        if enrollment.user_id != user_id:
            raise ForbiddenError("You can only complete your own enrollments")

        if enrollment.status == EnrollmentStatus.COMPLETED:
            progress = await self.compute_progress(
                enrollment=enrollment, org_id=org_id
            )
            # Grant the skills even on the idempotent path. The status is not only
            # written here: `routes/lessons.py`, `exercise_service._update_enrollment_
            # progress` and `course_service` all flip an enrollment to `completed` the
            # moment progress reaches 1.0, and none of them assign skills. So by the time
            # the learner posts the explicit `/complete`, the early return above was
            # reached and `user_skills` stayed empty — the course was finished and taught
            # the org nothing. `_assign_course_skills` is idempotent (it only ever raises
            # a level, never lowers one), so re-running it converges on the intended end
            # state instead of depending on which side door closed the enrollment first.
            await self._assign_course_skills(enrollment.user_id, enrollment.course_id)
            return enrollment, progress or 0.0

        progress = await self.compute_progress(
            enrollment=enrollment, org_id=org_id
        )
        if progress is None or progress < 1.0:
            raise ConflictError(
                "Cannot complete enrollment: not all lessons are finished. "
                f"Current progress: {int((progress or 0) * 100)}%"
            )
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = datetime.now(timezone.utc)
        enrollment.score = progress
        await self.enrollment_repo.session.flush()

        # Assign skills linked to the course.
        await self._assign_course_skills(enrollment.user_id, enrollment.course_id)

        return enrollment, progress or 0.0

    async def _assign_course_skills(
        self,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
        level: SkillLevel | None = None,
    ) -> None:
        """Assign skills linked to the completed course to the user.

        When a user completes a course, they earn all skills associated
        with that course at 'medium' level (first completion) or keep
        their existing level if already higher.

        ``level`` is the v2 addition and defaults to ``MEDIUM``, so the v1 call site is
        unchanged. A dynamic course passes the ``mastery -> skill_level`` translation of
        §3.3 applied to ``CourseCompletion.measured_mastery``: finishing a course whose
        nodes were mastered at 0.95 is more evidence than finishing one at 0.72, and v1
        had no number to tell them apart. The never-downgrade rule below is untouched
        and is what makes passing a lower level harmless.

        **Deciding not to call this at all is the caller's job**, and
        ``close_dynamic_if_mastered`` does exactly that when the course measured nothing.
        There is deliberately no "grant nothing" level here: an absent measurement is not
        a low one, and the only way to say so is not to write a row.
        """
        db = self.enrollment_repo.session
        granted = level or SkillLevel.MEDIUM

        # Find skills linked to this course.
        result = await db.execute(
            select(CourseSkill.skill_id).where(CourseSkill.course_id == course_id)
        )
        skill_ids = [row[0] for row in result.all()]
        if not skill_ids:
            return

        for skill_id in skill_ids:
            # Check if user already has this skill.
            existing = await db.execute(
                select(UserSkill).where(
                    UserSkill.user_id == user_id,
                    UserSkill.skill_id == skill_id,
                )
            )
            user_skill = existing.scalar_one_or_none()

            if user_skill is not None:
                # Only upgrade, never downgrade.
                level_order = {SkillLevel.LOW: 0, SkillLevel.MEDIUM: 1, SkillLevel.HIGH: 2}
                if level_order.get(user_skill.level, 0) < level_order[granted]:
                    user_skill.level = granted
                    user_skill.source = "course_completion"
                    user_skill.last_assessed_at = datetime.now(timezone.utc)
            else:
                db.add(UserSkill(
                    user_id=user_id,
                    skill_id=skill_id,
                    level=granted,
                    source="course_completion",
                ))

        await db.flush()
        logger.info(
            "Assigned %d skills to user %s from course %s",
            len(skill_ids), user_id, course_id,
        )

    # ------------------------------------------------------------------
    # §7.5 — course closing on the dynamic branch
    # ------------------------------------------------------------------

    async def node_progress(
        self, *, course_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[NodeProgressRow]:
        """The ``(node, state)`` join §7.5 evaluates, for one learner.

        Archived nodes are excluded at the query, and a node with no
        ``learner_node_states`` row counts as ``not_started`` with ``mastery = 0.0`` —
        which is the truth, and is what keeps a course from completing because nobody
        ever opened the last node.
        """
        db = self.enrollment_repo.session
        node_repo = CourseNodeRepository(db)
        nodes = list(await node_repo.list_for_course(course_id, include_archived=False))
        if not nodes:
            return []
        states = await LearnerNodeStateRepository(db).states_for_nodes(
            user_id=user_id, node_ids=[node.id for node in nodes]
        )
        rows: list[NodeProgressRow] = []
        for node in nodes:
            state = states.get(node.id)
            rows.append(
                NodeProgressRow(
                    node_id=node.id,
                    criticality=node.criticality,
                    archived=bool(node.archived),
                    state="not_started"
                    if state is None
                    else str(getattr(state.state, "value", state.state)),
                    mastery=float(getattr(state, "mastery", 0.0) or 0.0),
                    completed_at=getattr(state, "completed_at", None),
                    attempts_count=int(getattr(state, "attempts_count", 0) or 0),
                    probe_score=getattr(state, "probe_score", None),
                )
            )
        return rows

    async def evaluate_dynamic(
        self, *, course_id: uuid.UUID, user_id: uuid.UUID
    ) -> CourseCompletion:
        """§7.5's verdict for one learner on one dynamic course. Writes nothing."""
        return evaluate_course_completion(
            await self.node_progress(course_id=course_id, user_id=user_id)
        )

    async def mark_dynamic_started(
        self, *, course: Any, user_id: uuid.UUID, now: datetime | None = None
    ) -> Enrollment | None:
        """``assigned -> in_progress`` on the first real interaction with a v2 course.

        The dynamic branch had no such transition at all: :func:`apply_dynamic_closure`
        only ever writes ``completed`` or reopens a ``completed`` row, so a learner could
        work through more than half a course and their enrollment would still say
        ``assigned`` — printed as "Pendiente" on the learner dashboard, and counted as zero
        by "Cursos activos". v1 has always stamped this on the first lesson visit
        (``routes/lessons.py``); this is the same rule on the branch that lacked it.

        **"First interaction" is a render being handed to the browser**, i.e. the same
        moment ``LearnerNodeStateRepository.mark_opened`` stamps ``first_seen_at``, and the
        call site is that one. The three candidates are not equivalent:

        * *Answering an item* is too late and too narrow. An expository node has no graded
          item at all, so a course made of them would stay "Pendiente" forever — and it is
          the same hole that made ``completed_at`` necessary next to ``mastered_at``.
        * *``POST /nodes/{id}/complete``* is later still: a learner in the middle of their
          first node has demonstrably started, and until they press "next node" nothing
          would say so.
        * *Serving a render* is the honest "the learner was here" event, and it is
          deliberately **not** ``POST /nodes/{id}/render``: that one is also fired by the
          anticipatory prefetch for the nodes ahead, so it would mark a course started
          because the warm-up looked at it. ``GET /render`` is the response a browser
          actually displays.

        Idempotent by construction: it only writes when the row is still ``assigned``, and
        it never touches ``started_at`` once that column is set. Returns the enrollment when
        it moved, ``None`` otherwise — including for a course that is not dynamic, for a
        learner with no enrollment (an admin previewing, per ``_assert_enrolled``), and for
        every visit after the first.
        """
        if resolve_delivery(course) != "dynamic":
            return None
        enrollment = await self.enrollment_repo.get_by_user_and_course(
            user_id, course.id
        )
        if enrollment is None or enrollment.status != EnrollmentStatus.ASSIGNED:
            return None
        enrollment.status = EnrollmentStatus.IN_PROGRESS
        if enrollment.started_at is None:
            enrollment.started_at = now or datetime.now(timezone.utc)
        await self.enrollment_repo.session.flush()
        logger.info(
            "Dynamic enrollment %s for user %s on course %s: started",
            enrollment.id,
            user_id,
            course.id,
        )
        return enrollment

    async def close_dynamic_if_mastered(
        self, *, course: Any, user_id: uuid.UUID
    ) -> tuple[Enrollment | None, CourseCompletion | None]:
        """Close (or reopen) this learner's enrollment after a node changed state.

        Called from ``POST /nodes/{id}/answer`` on the ``learning -> mastered``
        transition and from ``POST /nodes/{id}/waive``: those are the only two events
        that can make the last critical node of a course ``mastered``. Nothing else
        closes a dynamic course — there is no "he terminado" button, because the rule is
        computable and asking would let a learner claim a course they have not mastered.

        Gated on ``resolve_delivery``, so a static course is never touched by this path
        and its v1 rule keeps its monopoly. Returns ``(enrollment, completion)`` with
        ``enrollment = None`` when there is nothing enrolled (a learner may open a node
        of a published course they were never assigned) and ``completion = None`` when
        the course is not on the dynamic branch at all.
        """
        if resolve_delivery(course) != "dynamic":
            return None, None

        completion = await self.evaluate_dynamic(
            course_id=course.id, user_id=user_id
        )
        enrollment = await self.enrollment_repo.get_by_user_and_course(
            user_id, course.id
        )
        if enrollment is None:
            return None, completion

        outcome = apply_dynamic_closure(enrollment, completion)
        if outcome is None:
            return enrollment, completion

        await self.enrollment_repo.session.flush()
        if outcome == "completed" and completion.measured_mastery is not None:
            # §7.5 / §3.3: the course's skills, at the level its **measured** nodes
            # support, still only upwards.
            #
            # The level used to come from `completion.score`, the mean mastery over every
            # node — so a course whose nodes ask nothing accredited its skills at `low`
            # to everyone who finished it, whether or not they knew any of it. That is
            # not a cautious grant, it is a false one: `user_skills` answers "who knows
            # X" and feeds the gap analysis and the probe prior, and a `low` row there is
            # a claim about a person, not the absence of one.
            #
            # So the grant is now gated on there being something to translate. A course
            # that measured nothing accredits nothing and leaves `user_skills` exactly as
            # it found it — the honest record of "they went through it", which is what
            # the completed enrollment itself already says. When a course does measure,
            # nothing changes except that the mean no longer counts the silences.
            await self._assign_course_skills(
                user_id,
                course.id,
                mastery_to_level(completion.measured_mastery),
            )
        logger.info(
            "Dynamic enrollment %s for user %s on course %s: %s (%d/%d nodes done, "
            "%d measured)",
            enrollment.id,
            user_id,
            course.id,
            outcome,
            completion.mastered_critical,
            completion.total_critical,
            completion.measured_nodes,
        )
        return enrollment, completion

    async def delete(self, *, enrollment_id: uuid.UUID, org_id: uuid.UUID) -> None:
        enrollment = await self.get_scoped(
            enrollment_id=enrollment_id, org_id=org_id
        )
        if enrollment.status != EnrollmentStatus.ASSIGNED:
            raise ConflictError("Only assigned (not started) enrollments can be removed")
        await self.enrollment_repo.delete(enrollment)
