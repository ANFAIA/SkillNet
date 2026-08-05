"""The organization's own data, assembled by the server for the admin assistant.

The defect this module exists for, measured on 2026-07-27: the owner asked the admin
assistant *"como van mis empleados"* and got four bullet points of generic management
advice — "revisa el parte de incidencias", "habla con el encargado". The answer was in
the database the whole time. ``ChatService.stream_admin`` delegated to the same grounding
ladder as the employee tutor, so the admin assistant was a *document* assistant: it could
read the training material and nothing else. It had no idea the platform it administers
had five employees in it.

**Why a server-assembled snapshot and not tool-calling.** The snapshot is built here,
deterministically, and pasted into the turn the way a document already is. The model
phrases; it never queries, never filters and never picks a row. Three reasons:

* The product is compliance training for Spanish SMEs. The seeded organization has five
  employees; the whole snapshot below renders to roughly 1.2 kB. A tool loop would cost
  two extra round trips and a schema the model can get wrong, to fetch less.
* Determinism is the safety property. A wrong number about a named person's training
  record is worse than "no lo se", and a model that cannot choose a filter cannot choose
  the wrong one.
* It cannot fail in a new way. Assembly is eight aggregate queries; if any of it raises,
  the caller drops the snapshot and the assistant answers exactly as it did yesterday.

The trade is that the block grows with the payroll. It is linear at about 45 tokens per
employee, so 40 employees is ~1.8 k tokens per turn — still cheaper than one tool round
trip. Past :data:`MAX_EMPLOYEES_LISTED` the renderer stops listing everybody and switches
to org-level counts plus the employees that actually need attention, saying out loud that
the list is partial. An organization big enough for that number to hurt (say 500 people)
wants a filtered query, i.e. tool-calling, and that is the point to revisit this — not
before.

**The privacy line is a column allowlist, not a review habit.** ``learner_profiles`` says
it in its own docstring: private to the employee, the admin only ever sees k>=5
aggregates. So what an employer legitimately holds about training — enrolments, progress,
mastery, skills, deadlines — is here, and how the person asked to be taught is not.
``preset``, ``experience_level``, ``goal``, ``format_vector``, ``tutor_notes`` and
``users.accessibility`` are never selected by any query in this file, and
``tests/test_org_snapshot.py`` reads this module's source to prove it, because "we
remembered" is not a control. ``role_title`` is the one profile column that travels: it
is the job the person does, the same string that already reaches the LLM on every node
render (§3.3), and an admin who cannot be told who the cook is cannot be helped at all.

No aggregate derived from the private columns is emitted either, above the threshold or
below it. The threshold exists so that a future feature *can*; nothing here needs one, and
the smallest safe surface is the one with nothing on it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models import (
    ContentStatus,
    Course,
    CourseNode,
    Document,
    Enrollment,
    EnrollmentStatus,
    LearnerNodeState,
    LearnerProfile,
    Lesson,
    LessonProgress,
    Module,
    NodeState,
    Organization,
    Skill,
    User,
    UserRole,
    UserSkill,
)
from src.services.course_delivery import resolve_delivery

logger = get_logger(__name__)

#: Above this many employees the renderer stops naming everyone and reports org-level
#: counts plus the people who need attention. See the module docstring for the arithmetic.
MAX_EMPLOYEES_LISTED = 40

#: Per employee, so one person with thirty badges cannot crowd out the other four.
MAX_SKILLS_PER_EMPLOYEE = 8

#: Titles only, and only so the admin can be told what is uploaded. The text of a document
#: reaches the turn through the retrieval ladder, not through here.
MAX_DOCUMENTS_LISTED = 25

#: The columns of ``learner_profiles`` and ``users`` that describe how a person asked to
#: be taught. Never selected, never rendered, never aggregated. Enforced by a test that
#: greps this module rather than by anyone's memory.
FORBIDDEN_PROFILE_FIELDS: frozenset[str] = frozenset(
    {
        "accessibility",
        "experience_level",
        "format_vector",
        "goal",
        "learning_profile",
        "preset",
        "tutor_notes",
    }
)

_ENROLMENT_LABELS: dict[str, str] = {
    EnrollmentStatus.ASSIGNED.value: "asignado, sin empezar",
    EnrollmentStatus.IN_PROGRESS.value: "en curso",
    EnrollmentStatus.COMPLETED.value: "completado",
}

_COURSE_STATUS_LABELS: dict[str, str] = {
    ContentStatus.DRAFT.value: "borrador",
    ContentStatus.PUBLISHED.value: "publicado",
    ContentStatus.ARCHIVED.value: "archivado",
}


def _enum_value(raw: object) -> str:
    return str(getattr(raw, "value", raw))


# --------------------------------------------------------------------------------------
# The facts. Plain data, no ORM: the renderer and every test work without a database.
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class EnrolmentFact:
    """One person on one course. Every number here was counted, never estimated."""

    course_title: str
    status: str
    #: ``done``/``total`` in whatever unit the course is delivered in, or ``None`` when
    #: the course has no units at all to count.
    done: int | None = None
    total: int | None = None
    #: "lecciones" or "nodos". Printed, because 3/5 lessons and 3/5 nodes are not the
    #: same claim and an admin reading a percentage deserves to know which was counted.
    unit: str = ""
    deadline: date | None = None
    completed_on: date | None = None

    @property
    def percent(self) -> int | None:
        if not self.total or self.done is None:
            return None
        return round(100 * self.done / self.total)

    def is_overdue(self, today: date) -> bool:
        return (
            self.deadline is not None
            and self.deadline < today
            and self.status != EnrollmentStatus.COMPLETED.value
        )

    def needs_attention(self, today: date) -> bool:
        """Overdue, or assigned and never opened. What an admin scans a list for."""
        return self.is_overdue(today) or self.status == EnrollmentStatus.ASSIGNED.value


@dataclass(frozen=True)
class EmployeeFact:
    """Training record for one employee. See the module docstring for what is absent."""

    full_name: str
    role_title: str | None = None
    active: bool = True
    hired_on: date | None = None
    enrolments: tuple[EnrolmentFact, ...] = ()
    #: ``(skill name, level)``, level being low/medium/high as stored.
    skills: tuple[tuple[str, str], ...] = ()
    #: Nodes this person has taken to ``mastered``, across every course.
    nodes_mastered: int = 0

    def needs_attention(self, today: date) -> bool:
        return any(e.needs_attention(today) for e in self.enrolments)


@dataclass(frozen=True)
class CourseFact:
    title: str
    status: str
    delivery: str
    units: int = 0
    unit_name: str = ""
    assigned: int = 0
    in_progress: int = 0
    completed: int = 0

    @property
    def enrolled(self) -> int:
        return self.assigned + self.in_progress + self.completed


@dataclass(frozen=True)
class OrgSnapshot:
    """Everything the admin assistant is allowed to know about its own organization."""

    org_name: str
    generated_at: datetime
    employees: tuple[EmployeeFact, ...] = ()
    courses: tuple[CourseFact, ...] = ()
    documents: tuple[str, ...] = ()
    documents_total: int = 0
    #: The real headcount, which is ``len(employees)`` unless the renderer had to trim.
    employees_total: int = 0

    @property
    def is_empty(self) -> bool:
        return not (self.employees or self.courses or self.documents)


# --------------------------------------------------------------------------------------
# Assembly. Eight aggregate queries, every one of them scoped to ``org_id``.
# --------------------------------------------------------------------------------------
async def build_org_snapshot(
    db: AsyncSession, *, org_id: uuid.UUID, now: datetime | None = None
) -> OrgSnapshot:
    """The organization's training data as of now.

    ``org_id`` is a predicate on every query and on both sides of every join that could
    reach another organization's rows. There is one organization in the product today;
    the query that assumes so is the query that leaks when there are two.
    """
    generated_at = now or datetime.now(timezone.utc)
    org_name = (
        await db.execute(select(Organization.name).where(Organization.id == org_id))
    ).scalar_one_or_none() or "la organizacion"

    employees = await _employee_rows(db, org_id=org_id)
    user_ids = [row[0] for row in employees]
    courses = await _course_rows(db, org_id=org_id)
    course_ids = [row.id for row in courses]

    enrolments = await _enrolment_rows(db, org_id=org_id, course_ids=course_ids)
    lesson_totals, lessons_done = await _lesson_counts(
        db, course_ids=course_ids, user_ids=user_ids
    )
    node_totals, nodes_done = await _node_counts(
        db, org_id=org_id, course_ids=course_ids, user_ids=user_ids
    )
    skills = await _skill_rows(db, org_id=org_id, user_ids=user_ids)
    documents, documents_total = await _document_titles(db, org_id=org_id)

    by_course = {
        course.id: _units_for(
            course,
            lessons=lesson_totals.get(course.id, 0),
            nodes=node_totals.get(course.id, 0),
        )
        for course in courses
    }

    titles = {course.id: course.title for course in courses}
    per_user: dict[uuid.UUID, list[EnrolmentFact]] = {}
    course_counts: dict[uuid.UUID, dict[str, int]] = {
        course.id: {status.value: 0 for status in EnrollmentStatus} for course in courses
    }
    for row in enrolments:
        unit, _delivery, total = by_course.get(row.course_id, ("", "estatico", 0))
        done = (nodes_done if unit == "nodos" else lessons_done).get(
            (row.user_id, row.course_id), 0
        )
        status = _enum_value(row.status)
        if row.course_id in course_counts:
            course_counts[row.course_id][status] = (
                course_counts[row.course_id].get(status, 0) + 1
            )
        per_user.setdefault(row.user_id, []).append(
            EnrolmentFact(
                course_title=titles.get(row.course_id, "Curso"),
                status=status,
                # A completed enrolment is 100% by definition of "completed": the v1 rule
                # closes it at progress 1.0 and the v2 rule at every critical node
                # mastered. Reporting 4/5 next to "completado" would be two answers.
                done=total if status == EnrollmentStatus.COMPLETED.value else min(done, total),
                total=total,
                unit=unit if total else "",
                deadline=row.deadline,
                completed_on=row.completed_at.date() if row.completed_at else None,
            )
        )

    facts = tuple(
        EmployeeFact(
            full_name=full_name,
            role_title=role_title,
            active=bool(is_active),
            hired_on=hired_at,
            enrolments=tuple(per_user.get(user_id, ())),
            skills=tuple(skills.get(user_id, ())[:MAX_SKILLS_PER_EMPLOYEE]),
            nodes_mastered=sum(
                count
                for (uid, _cid), count in nodes_done.items()
                if uid == user_id
            ),
        )
        for user_id, full_name, role_title, is_active, hired_at in employees
    )

    return OrgSnapshot(
        org_name=org_name,
        generated_at=generated_at,
        employees=facts,
        employees_total=len(facts),
        courses=tuple(
            CourseFact(
                title=course.title,
                status=_COURSE_STATUS_LABELS.get(
                    _enum_value(course.status), _enum_value(course.status)
                ),
                delivery=by_course[course.id][1],
                units=by_course[course.id][2],
                unit_name=by_course[course.id][0],
                assigned=course_counts[course.id].get(
                    EnrollmentStatus.ASSIGNED.value, 0
                ),
                in_progress=course_counts[course.id].get(
                    EnrollmentStatus.IN_PROGRESS.value, 0
                ),
                completed=course_counts[course.id].get(
                    EnrollmentStatus.COMPLETED.value, 0
                ),
            )
            for course in courses
        ),
        documents=documents,
        documents_total=documents_total,
    )


def _units_for(course, *, lessons: int, nodes: int) -> tuple[str, str, int]:
    """``(unit name, how the course is served, how many units)``.

    Two different questions, answered from two different places, and conflating them is
    how the admin gets told a course is empty when it is not. **How it is served** is
    ``resolve_delivery`` and nothing else — the single decision point. **What there is
    to count** is whatever the course actually has rows for: a schema-first course has
    nodes and no lessons, and reporting "0 lecciones" for it would be a true sentence
    that reads as a false one. Preference goes to the served unit when both exist,
    because that is the one the learner's progress is measured in.
    """
    served = "dinamico" if resolve_delivery(course) == "dynamic" else "estatico"
    if served == "dinamico" and nodes:
        return "nodos", served, nodes
    if lessons:
        return "lecciones", served, lessons
    if nodes:
        return "nodos", served, nodes
    return "", served, 0


async def _employee_rows(
    db: AsyncSession, *, org_id: uuid.UUID
) -> list[tuple[uuid.UUID, str, str | None, bool, date | None]]:
    """Employees of this org, and the single profile column allowed to travel.

    The ``LearnerProfile`` join selects ``role_title`` and nothing else, and the
    ``org_id`` predicate is repeated on the profile side: a profile row belongs to an
    organization too, and a join that only constrains the user is one refactor away from
    not constraining anything.
    """
    query = (
        select(
            User.id,
            User.full_name,
            LearnerProfile.role_title,
            User.is_active,
            User.hired_at,
        )
        .outerjoin(
            LearnerProfile,
            (LearnerProfile.user_id == User.id) & (LearnerProfile.org_id == org_id),
        )
        .where(User.org_id == org_id, User.role == UserRole.EMPLOYEE)
        .order_by(User.full_name)
    )
    return [tuple(row) for row in (await db.execute(query)).all()]  # type: ignore[misc]


async def _course_rows(db: AsyncSession, *, org_id: uuid.UUID) -> list:
    query = (
        select(
            Course.id,
            Course.title,
            Course.status,
            Course.delivery_mode,
            Course.schema_status,
        )
        .where(Course.org_id == org_id, Course.status != ContentStatus.ARCHIVED)
        .order_by(Course.title)
    )
    return list((await db.execute(query)).all())


async def _enrolment_rows(
    db: AsyncSession, *, org_id: uuid.UUID, course_ids: Sequence[uuid.UUID]
) -> list:
    if not course_ids:
        return []
    query = (
        select(
            Enrollment.user_id,
            Enrollment.course_id,
            Enrollment.status,
            Enrollment.deadline,
            Enrollment.completed_at,
        )
        .join(Course, Course.id == Enrollment.course_id)
        .where(Course.org_id == org_id, Enrollment.course_id.in_(course_ids))
    )
    return list((await db.execute(query)).all())


async def _lesson_counts(
    db: AsyncSession,
    *,
    course_ids: Sequence[uuid.UUID],
    user_ids: Sequence[uuid.UUID],
) -> tuple[dict[uuid.UUID, int], dict[tuple[uuid.UUID, uuid.UUID], int]]:
    """``(lessons per course, lessons visited per (user, course))``.

    The v1 completion rule also demands a passing attempt on every exercise of a lesson
    (``EnrollmentService.compute_progress``). This counts visits only, which can read one
    or two lessons ahead of the strict rule on a course with exercises. That is a
    deliberate simplification of a *progress indicator*, and it is why the enrolment
    ``status`` column — which is written by the strict rule — is what the assistant is
    told to answer "has X finished?" with.
    """
    if not course_ids:
        return {}, {}
    totals_query = (
        select(Module.course_id, func.count(Lesson.id))
        .join(Lesson, Lesson.module_id == Module.id)
        .where(Module.course_id.in_(course_ids))
        .group_by(Module.course_id)
    )
    totals = {row[0]: int(row[1]) for row in (await db.execute(totals_query)).all()}
    if not user_ids:
        return totals, {}
    done_query = (
        select(LessonProgress.user_id, Module.course_id, func.count())
        .join(Lesson, Lesson.id == LessonProgress.lesson_id)
        .join(Module, Module.id == Lesson.module_id)
        .where(
            Module.course_id.in_(course_ids),
            LessonProgress.user_id.in_(user_ids),
        )
        .group_by(LessonProgress.user_id, Module.course_id)
    )
    done = {
        (row[0], row[1]): int(row[2]) for row in (await db.execute(done_query)).all()
    }
    return totals, done


async def _node_counts(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    course_ids: Sequence[uuid.UUID],
    user_ids: Sequence[uuid.UUID],
) -> tuple[dict[uuid.UUID, int], dict[tuple[uuid.UUID, uuid.UUID], int]]:
    """``(live nodes per course, nodes mastered per (user, course))``.

    Archived nodes are excluded on both sides, matching ``EnrollmentService.node_progress``:
    a learner cannot master a node that is no longer served, so counting it would make
    every course permanently incomplete.
    """
    if not course_ids:
        return {}, {}
    totals_query = (
        select(CourseNode.course_id, func.count())
        .where(
            CourseNode.org_id == org_id,
            CourseNode.course_id.in_(course_ids),
            CourseNode.archived.is_(False),
        )
        .group_by(CourseNode.course_id)
    )
    totals = {row[0]: int(row[1]) for row in (await db.execute(totals_query)).all()}
    if not user_ids:
        return totals, {}
    done_query = (
        select(LearnerNodeState.user_id, CourseNode.course_id, func.count())
        .join(CourseNode, CourseNode.id == LearnerNodeState.node_id)
        .where(
            CourseNode.org_id == org_id,
            CourseNode.course_id.in_(course_ids),
            CourseNode.archived.is_(False),
            LearnerNodeState.user_id.in_(user_ids),
            LearnerNodeState.state == NodeState.MASTERED,
        )
        .group_by(LearnerNodeState.user_id, CourseNode.course_id)
    )
    done = {
        (row[0], row[1]): int(row[2]) for row in (await db.execute(done_query)).all()
    }
    return totals, done


async def _skill_rows(
    db: AsyncSession, *, org_id: uuid.UUID, user_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[str, str]]]:
    if not user_ids:
        return {}
    query = (
        select(UserSkill.user_id, Skill.name, UserSkill.level)
        .join(Skill, Skill.id == UserSkill.skill_id)
        .where(Skill.org_id == org_id, UserSkill.user_id.in_(user_ids))
        .order_by(Skill.name)
    )
    out: dict[uuid.UUID, list[tuple[str, str]]] = {}
    for user_id, name, level in (await db.execute(query)).all():
        out.setdefault(user_id, []).append((name, _enum_value(level)))
    return out


async def _document_titles(
    db: AsyncSession, *, org_id: uuid.UUID
) -> tuple[tuple[str, ...], int]:
    query = (
        select(Document.title)
        .where(Document.org_id == org_id)
        .order_by(Document.created_at.desc())
    )
    titles = [row[0] for row in (await db.execute(query)).all()]
    return tuple(titles[:MAX_DOCUMENTS_LISTED]), len(titles)


# --------------------------------------------------------------------------------------
# Rendering. Pure, so the exact bytes that reach the model are testable without a DB.
# --------------------------------------------------------------------------------------
def _level_label(level: str) -> str:
    return {"low": "bajo", "medium": "medio", "high": "alto"}.get(level, level)


def _enrolment_line(fact: EnrolmentFact, today: date) -> str:
    label = _ENROLMENT_LABELS.get(fact.status, fact.status)
    bits = [f"{fact.course_title}: {label}"]
    if fact.total:
        bits.append(f"{fact.percent}% ({fact.done}/{fact.total} {fact.unit})")
    if fact.completed_on:
        bits.append(f"terminado el {fact.completed_on.isoformat()}")
    if fact.deadline:
        overdue = " (FUERA DE PLAZO)" if fact.is_overdue(today) else ""
        bits.append(f"plazo {fact.deadline.isoformat()}{overdue}")
    return ", ".join(bits)


def _employee_block(employee: EmployeeFact, today: date) -> list[str]:
    head = f"- {employee.full_name}"
    if employee.role_title:
        head += f" ({employee.role_title})"
    if not employee.active:
        head += " [cuenta desactivada]"
    if employee.hired_on:
        head += f", alta {employee.hired_on.isoformat()}"
    lines = [head]
    if employee.enrolments:
        for enrolment in employee.enrolments:
            lines.append(f"    * {_enrolment_line(enrolment, today)}")
    else:
        lines.append("    * sin cursos asignados")
    if employee.nodes_mastered:
        lines.append(f"    * nodos dominados: {employee.nodes_mastered}")
    if employee.skills:
        rendered = ", ".join(
            f"{name} ({_level_label(level)})" for name, level in employee.skills
        )
        lines.append(f"    * competencias acreditadas: {rendered}")
    return lines


def _course_line(course: CourseFact) -> str:
    state = course.status
    if course.delivery == "dinamico":
        # Only when it is true: "estatico" on every line is noise on a v1 deployment,
        # where every course is static and the word distinguishes nothing.
        state += " (dinamico)"
    bits = [f"- {course.title}: {state}"]
    if course.units:
        bits.append(f"{course.units} {course.unit_name}")
    bits.append(
        f"{course.enrolled} asignaciones "
        f"({course.completed} completadas, {course.in_progress} en curso, "
        f"{course.assigned} sin empezar)"
    )
    return ", ".join(bits)


def _summary_lines(employees: Sequence[EmployeeFact], today: date) -> list[str]:
    """The org-level totals, counted here so the model never has to count.

    Measured on the first live run against the demo organization: given only the
    per-person list, ``groq/llama-3.1-8b-instant`` answered *"como van mis empleados"*
    with five name-by-name blocks and no headline — correct, and unreadable, and exactly
    what the rule above ("no sumes, no promedies") obliges it to do when the total it
    would need is not written down. So the totals are written down. Every figure an admin
    would open the dashboard for is a literal string in the block, which is what makes
    "only state what you were given" a usable instruction rather than a gag.
    """
    enrolments = [e for person in employees for e in person.enrolments]
    counted = {
        "sin empezar": sum(
            1 for e in enrolments if e.status == EnrollmentStatus.ASSIGNED.value
        ),
        "en curso": sum(
            1 for e in enrolments if e.status == EnrollmentStatus.IN_PROGRESS.value
        ),
        "completadas": sum(
            1 for e in enrolments if e.status == EnrollmentStatus.COMPLETED.value
        ),
    }
    overdue = [
        person for person in employees if any(e.is_overdue(today) for e in person.enrolments)
    ]
    idle = [
        person
        for person in employees
        if person.enrolments
        and all(e.status == EnrollmentStatus.ASSIGNED.value for e in person.enrolments)
    ]
    unassigned = [person for person in employees if not person.enrolments]

    return [
        "RESUMEN (ya contado, no lo recalcules)",
        f"- empleados: {len(employees)}",
        f"- asignaciones de curso: {len(enrolments)} "
        f"({counted['completadas']} completadas, {counted['en curso']} en curso, "
        f"{counted['sin empezar']} sin empezar)",
        f"- empleados que no han empezado NINGUNO de sus cursos: {_named(idle)}",
        f"- empleados sin ningun curso asignado: {_named(unassigned)}",
        f"- empleados con algun plazo vencido: {_named(overdue)}",
    ]


def _named(people: Sequence[EmployeeFact], limit: int = 10) -> str:
    """``"3 (Ana, Berta, Carlos)"``. The count is always exact; the names may be cut.

    An admin asking "quien no ha empezado" wants the names, and on an SME payroll they
    all fit. Past ``limit`` the line says how many were left out rather than growing
    without bound, and the count in front of the parenthesis stays the real one — a
    truncated name list next to a truncated count would be two lies for the price of one.
    """
    if not people:
        return "0"
    shown = [person.full_name for person in people[:limit]]
    rest = len(people) - len(shown)
    tail = f", +{rest} mas" if rest else ""
    return f"{len(people)} ({', '.join(shown)}{tail})"


def render_snapshot(
    snapshot: OrgSnapshot, *, max_employees: int = MAX_EMPLOYEES_LISTED
) -> str:
    """The snapshot as the text the model receives. ``""`` when there is nothing to say.

    Two properties this text has to carry, because the model cannot be trusted to infer
    either: every number is printed (nothing is left to be computed), and when the
    employee list is trimmed the trim is stated in the block itself, so "todos mis
    empleados" cannot be answered from a partial list without the model being told it is
    partial.
    """
    if snapshot.is_empty:
        return ""
    today = snapshot.generated_at.date()
    lines = [
        f"DATOS DE LA PLATAFORMA - {snapshot.org_name} "
        f"(al {snapshot.generated_at.date().isoformat()})",
    ]

    listed = list(snapshot.employees)
    trimmed = len(listed) > max_employees
    if trimmed:
        # Attention first, then whoever fits: a truncated list that drops the overdue
        # person is worse than no list, because it reads like an all-clear.
        listed.sort(key=lambda e: (not e.needs_attention(today), e.full_name))
        listed = listed[:max_employees]

    if snapshot.employees:
        lines.append("")
        lines.extend(_summary_lines(snapshot.employees, today))

    header = f"EMPLEADOS ({snapshot.employees_total})"
    if trimmed:
        header += (
            f" - se listan {len(listed)} de {snapshot.employees_total}, "
            "los que requieren atencion primero. La lista es PARCIAL: dilo si te "
            "preguntan por el conjunto."
        )
    lines.append("")
    lines.append(header)
    if listed:
        for employee in listed:
            lines.extend(_employee_block(employee, today))
    else:
        lines.append("- no hay ningun empleado dado de alta")

    lines.append("")
    lines.append(f"CURSOS ({len(snapshot.courses)})")
    if snapshot.courses:
        lines.extend(_course_line(course) for course in snapshot.courses)
    else:
        lines.append("- no hay ningun curso creado")

    lines.append("")
    lines.append(f"DOCUMENTOS SUBIDOS ({snapshot.documents_total})")
    if snapshot.documents:
        lines.extend(f"- {title}" for title in snapshot.documents)
        if snapshot.documents_total > len(snapshot.documents):
            lines.append(
                f"- (+{snapshot.documents_total - len(snapshot.documents)} mas)"
            )
    else:
        lines.append("- no hay ningun documento subido")

    return "\n".join(lines)


__all__ = [
    "FORBIDDEN_PROFILE_FIELDS",
    "MAX_DOCUMENTS_LISTED",
    "MAX_EMPLOYEES_LISTED",
    "MAX_SKILLS_PER_EMPLOYEE",
    "CourseFact",
    "EmployeeFact",
    "EnrolmentFact",
    "OrgSnapshot",
    "build_org_snapshot",
    "render_snapshot",
]
