"""The blocking creator gate (§11.1). No DB, no network — in-memory fake repos.

The headline test is ``test_content_cannot_be_generated_for_an_unvalidated_schema``:
it is the executable form of the promise in §1.1. Everything else here guards the
three ways the gate could be walked around: editing after validating, deleting a
node somebody already worked on, and slipping a fresh unreviewed node into a course
that was signed off earlier.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.models import (
    ContentStatus,
    Course,
    CourseDeliveryMode,
    CourseNode,
    CourseSchemaStatus,
    EnrollmentStatus,
    NodeCriticality,
    UiFormat,
)
from src.services.course_schema_service import (
    CourseSchemaService,
    NodeHasProgress,
    NodeNotReviewed,
    SchemaInvalid,
    SchemaLocked,
    UnknownNode,
    ensure_deletable,
    ensure_node_servable,
)

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ACTOR_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
DOC_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeResult:
    def __init__(self, rows: list | None = None) -> None:
        self._rows = list(rows or [])

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """Records the SQL the service asks for without executing any of it."""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self.flushes = 0

    async def execute(self, query):
        self.statements.append(str(query))
        return FakeResult([])

    async def flush(self) -> None:
        self.flushes += 1

    async def delete(self, obj) -> None:  # pragma: no cover - unused path
        raise AssertionError("the service must delete through the node repo")


class FakeCourseRepo:
    def __init__(self, course: Course) -> None:
        self.course = course

    async def get_scoped(self, course_id, org_id):
        if course_id != self.course.id or org_id != self.course.org_id:
            return None
        return self.course


class FakeNodeRepo:
    def __init__(self, session: FakeSession, nodes: list[CourseNode]) -> None:
        self.session = session
        self.nodes = nodes
        self.edges: dict[uuid.UUID, list[uuid.UUID]] = {}
        self.attempts: dict[uuid.UUID, int] = {}
        self.mastery: list[tuple] = []
        self.deferred = False
        self.deleted: list[CourseNode] = []

    async def defer_position_constraint(self) -> None:
        self.deferred = True

    async def list_for_course(self, course_id, *, include_archived: bool = True):
        return [
            node
            for node in self.nodes
            if node.course_id == course_id and (include_archived or not node.archived)
        ]

    async def get_scoped(self, node_id, org_id):
        for node in self.nodes:
            if node.id == node_id and node.org_id == org_id:
                return node
        return None

    async def prerequisites_for(self, node_ids):
        return {nid: list(self.edges.get(nid, [])) for nid in node_ids}

    async def replace_prerequisites(self, node_id, prerequisite_ids) -> None:
        self.edges[node_id] = list(prerequisite_ids)

    async def attempt_counts(self, node_ids):
        return {nid: self.attempts.get(nid, 0) for nid in node_ids}

    async def mastery_rows(self, node_ids):
        """``(user_id, node_id, state, mastery, completed_at)``.

        5-wide: exactly the columns ``mastery_service.node_is_done`` reads, and the
        recompute is only as correct as this projection is complete.
        """
        return [row for row in self.mastery if row[1] in set(node_ids)]

    async def create(self, **kwargs) -> CourseNode:
        node = CourseNode(**kwargs)
        node.id = uuid.uuid4()
        self.nodes.append(node)
        return node

    async def delete(self, obj) -> None:
        self.deleted.append(obj)
        self.nodes.remove(obj)


class FakeAuditRepo:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def record(self, *, org_id, actor_id, action, subject, detail=None):
        row = {
            "org_id": org_id,
            "actor_id": actor_id,
            "action": action,
            "subject": subject,
            "detail": detail or {},
        }
        self.rows.append(row)
        return row


class FakeEnrollment:
    def __init__(self, user_id: uuid.UUID, status: EnrollmentStatus) -> None:
        self.user_id = user_id
        self.status = status
        self.completed_at: datetime | None = (
            datetime.now(timezone.utc) if status == EnrollmentStatus.COMPLETED else None
        )
        self.score: float | None = None


class FakeEnrollmentRepo:
    def __init__(self, enrollments: list[FakeEnrollment] | None = None) -> None:
        self.enrollments = list(enrollments or [])

    async def list_enrollments(self, *, org_id, course_id=None, limit=50, **kwargs):
        return list(self.enrollments), len(self.enrollments)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def make_course(
    *,
    status: CourseSchemaStatus = CourseSchemaStatus.PROPOSED,
    mode: CourseDeliveryMode = CourseDeliveryMode.STATIC,
) -> Course:
    course = Course(
        org_id=ORG_ID,
        title="Politica de devoluciones",
        outcome="Gestionar devoluciones sin errores",
        source_document_id=DOC_ID,
        schema_status=status,
        delivery_mode=mode,
        schema_version=1,
        intent_density=3,
    )
    course.id = uuid.uuid4()
    return course


def make_node(
    course: Course,
    *,
    position: int,
    title: str = "Nodo",
    summary: str = "resumen",
    criticality: NodeCriticality = NodeCriticality.CRITICAL,
    reviewed: bool = True,
    archived: bool = False,
) -> CourseNode:
    node = CourseNode(
        org_id=course.org_id,
        course_id=course.id,
        title=title,
        summary=summary,
        criticality=criticality,
        position=position,
        source_document_id=DOC_ID,
        source_headings=["Devoluciones"],
        mastery_threshold=0.9,
        default_ui_format=UiFormat.EXPLANATION,
        reviewed_at=datetime.now(timezone.utc) if reviewed else None,
        reviewed_by=ACTOR_ID if reviewed else None,
        archived=archived,
    )
    node.id = uuid.uuid4()
    return node


def make_service(course: Course, nodes: list[CourseNode], **kwargs):
    session = FakeSession()
    node_repo = FakeNodeRepo(session, nodes)
    audit_repo = FakeAuditRepo()
    enrollment_repo = FakeEnrollmentRepo(kwargs.pop("enrollments", None))
    service = CourseSchemaService(
        FakeCourseRepo(course),  # type: ignore[arg-type]
        node_repo,  # type: ignore[arg-type]
        audit_repo,  # type: ignore[arg-type]
        enrollment_repo,  # type: ignore[arg-type]
        **kwargs,
    )
    return service, node_repo, audit_repo, enrollment_repo


def node_payload(node: CourseNode, **overrides) -> dict:
    payload = {
        "id": node.id,
        "title": node.title,
        "summary": node.summary,
        "outcome": node.outcome,
        "criticality": node.criticality.value,
        "position": node.position,
        "mastery_threshold": float(node.mastery_threshold),
        "default_ui_format": node.default_ui_format.value,
        "skill_id": node.skill_id,
        "seed_lesson_id": node.seed_lesson_id,
        "source_document_id": node.source_document_id,
        "source_headings": list(node.source_headings or []),
        "prerequisite_node_ids": [],
        "archived": None,
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# The headline: the gate really blocks generation
# --------------------------------------------------------------------------- #
def test_content_cannot_be_generated_for_an_unvalidated_schema() -> None:
    """§1.1: a node whose course schema is not validated is never served."""
    course = make_course(status=CourseSchemaStatus.PROPOSED)
    node = make_node(course, position=1)

    with pytest.raises(NodeNotReviewed) as excinfo:
        ensure_node_servable(course, node)

    assert excinfo.value.status_code == 409
    assert excinfo.value.payload()["code"] == "node_not_reviewed"
    assert "no esta validado" in excinfo.value.payload()["message"]


def test_a_validated_and_dynamic_course_serves_a_reviewed_node() -> None:
    course = make_course(
        status=CourseSchemaStatus.VALIDATED, mode=CourseDeliveryMode.DYNAMIC
    )
    ensure_node_servable(course, make_node(course, position=1))


def test_unreviewed_node_is_409_even_in_a_validated_course() -> None:
    """The bypass of §11.1: adding a fresh node to an already-signed-off course."""
    course = make_course(
        status=CourseSchemaStatus.VALIDATED, mode=CourseDeliveryMode.DYNAMIC
    )
    node = make_node(course, position=2, reviewed=False)
    with pytest.raises(NodeNotReviewed) as excinfo:
        ensure_node_servable(course, node)
    assert "revisado" in excinfo.value.payload()["message"]


def test_archived_node_is_never_served() -> None:
    course = make_course(
        status=CourseSchemaStatus.VALIDATED, mode=CourseDeliveryMode.DYNAMIC
    )
    node = make_node(course, position=1, archived=True)
    with pytest.raises(NodeNotReviewed):
        ensure_node_servable(course, node)


def test_static_delivery_mode_is_never_served_dynamically() -> None:
    course = make_course(
        status=CourseSchemaStatus.VALIDATED, mode=CourseDeliveryMode.STATIC
    )
    with pytest.raises(NodeNotReviewed):
        ensure_node_servable(course, make_node(course, position=1))


def test_ensure_node_servable_accepts_raw_string_values() -> None:
    """Rows loaded through raw SQL carry strings, not enum members."""
    course = make_course()
    course.schema_status = "validated"
    course.delivery_mode = "dynamic"
    ensure_node_servable(course, make_node(course, position=1))


# --------------------------------------------------------------------------- #
# schema_locked
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_put_on_a_validated_schema_is_schema_locked() -> None:
    course = make_course(
        status=CourseSchemaStatus.VALIDATED, mode=CourseDeliveryMode.DYNAMIC
    )
    node = make_node(course, position=1)
    service, _, _, _ = make_service(course, [node])

    with pytest.raises(SchemaLocked) as excinfo:
        await service.update(
            course_id=course.id,
            org_id=ORG_ID,
            actor_id=ACTOR_ID,
            nodes=[node_payload(node)],
        )

    payload = excinfo.value.payload()
    assert payload["code"] == "schema_locked"
    assert "unvalidate" in payload["message"]
    assert excinfo.value.status_code == 422
    # Nothing was touched: the version did not move.
    assert course.schema_version == 1


@pytest.mark.asyncio
async def test_proposing_over_a_validated_schema_is_schema_locked() -> None:
    course = make_course(status=CourseSchemaStatus.VALIDATED)
    service, _, _, _ = make_service(course, [])
    with pytest.raises(SchemaLocked):
        await service.propose(
            course_id=course.id,
            org_id=ORG_ID,
            triggered_by=ACTOR_ID,
            source_document_id=DOC_ID,
            intent_density=3,
        )


@pytest.mark.asyncio
async def test_unvalidate_returns_to_proposed_and_static_in_one_transaction() -> None:
    course = make_course(
        status=CourseSchemaStatus.VALIDATED, mode=CourseDeliveryMode.DYNAMIC
    )
    course.schema_validated_by = ACTOR_ID
    course.schema_validated_at = datetime.now(timezone.utc)
    node = make_node(course, position=1)
    service, _, audit_repo, _ = make_service(course, [node])

    snapshot = await service.unvalidate(
        course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID
    )

    assert snapshot.course.schema_status == CourseSchemaStatus.PROPOSED
    assert snapshot.course.delivery_mode == CourseDeliveryMode.STATIC
    assert snapshot.course.schema_validated_by is None
    assert snapshot.course.schema_validated_at is None
    assert [row["action"] for row in audit_repo.rows] == [
        "course_schema_unvalidated"
    ]
    # And the node is no longer servable, even though it is still reviewed.
    with pytest.raises(NodeNotReviewed):
        ensure_node_servable(snapshot.course, node)


@pytest.mark.asyncio
async def test_put_is_allowed_again_after_unvalidate() -> None:
    course = make_course(
        status=CourseSchemaStatus.VALIDATED, mode=CourseDeliveryMode.DYNAMIC
    )
    node = make_node(course, position=1)
    service, _, _, _ = make_service(course, [node])

    await service.unvalidate(course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID)
    snapshot = await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[node_payload(node, summary="resumen reescrito")],
    )
    assert snapshot.course.schema_version == 2


# --------------------------------------------------------------------------- #
# node_has_progress
# --------------------------------------------------------------------------- #
def test_deleting_a_node_with_attempts_is_node_has_progress() -> None:
    course = make_course()
    node = make_node(course, position=1)
    with pytest.raises(NodeHasProgress) as excinfo:
        ensure_deletable(node, 3)
    payload = excinfo.value.payload()
    assert payload["code"] == "node_has_progress"
    assert payload["node_ids"] == [str(node.id)]


def test_deleting_an_untouched_node_is_allowed() -> None:
    course = make_course()
    ensure_deletable(make_node(course, position=1), 0)


@pytest.mark.asyncio
async def test_put_archives_a_missing_node_that_has_progress() -> None:
    course = make_course()
    keep = make_node(course, position=1, title="Plazo")
    worked_on = make_node(course, position=2, title="Excepciones")
    service, node_repo, _, _ = make_service(course, [keep, worked_on])
    node_repo.attempts[worked_on.id] = 4

    snapshot = await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[node_payload(keep)],
    )

    assert worked_on.archived is True
    assert worked_on not in node_repo.deleted
    assert [node.id for node in snapshot.nodes] == [keep.id]
    assert any("se archivo" in warning for warning in snapshot.warnings)


@pytest.mark.asyncio
async def test_put_deletes_a_missing_node_nobody_touched() -> None:
    course = make_course()
    keep = make_node(course, position=1, title="Plazo")
    untouched = make_node(course, position=2, title="Excepciones")
    service, node_repo, _, _ = make_service(course, [keep, untouched])

    await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[node_payload(keep)],
    )

    assert node_repo.deleted == [untouched]
    assert untouched.archived is False


# --------------------------------------------------------------------------- #
# reviewed_at invalidation
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_editing_the_summary_clears_reviewed_at() -> None:
    course = make_course()
    node = make_node(course, position=1)
    service, _, _, _ = make_service(course, [node])

    await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[node_payload(node, summary="un resumen distinto")],
    )

    assert node.reviewed_at is None
    assert node.reviewed_by is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "Otro titulo"),
        ("summary", "Otro resumen"),
        ("criticality", "contextual"),
        ("source_headings", ["Excepciones"]),
    ],
)
async def test_every_review_invalidating_field_clears_reviewed_at(
    field: str, value
) -> None:
    course = make_course()
    node = make_node(course, position=1)
    service, _, _, _ = make_service(course, [node])

    await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[node_payload(node, **{field: value})],
    )
    assert node.reviewed_at is None


@pytest.mark.asyncio
async def test_editing_a_harmless_field_keeps_reviewed_at() -> None:
    course = make_course()
    node = make_node(course, position=1)
    stamped = node.reviewed_at
    service, _, _, _ = make_service(course, [node])

    await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[node_payload(node, outcome="otro resultado")],
    )
    assert node.reviewed_at == stamped
    assert node.outcome == "otro resultado"


@pytest.mark.asyncio
async def test_a_node_created_by_a_put_is_never_pre_reviewed() -> None:
    course = make_course()
    existing = make_node(course, position=1)
    service, _, _, _ = make_service(course, [existing])

    snapshot = await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[
            node_payload(existing),
            {
                "title": "Nodo nuevo",
                "summary": "recien anadido por el creador",
                "criticality": "recommended",
                "position": 2,
                "prerequisite_node_ids": [],
            },
        ],
    )
    created = snapshot.nodes[-1]
    assert created.title == "Nodo nuevo"
    assert created.reviewed_at is None
    assert created.mastery_threshold == 0.80


@pytest.mark.asyncio
async def test_mark_reviewed_stamps_the_node() -> None:
    course = make_course()
    node = make_node(course, position=1, reviewed=False)
    service, _, _, _ = make_service(course, [node])

    stamped = await service.mark_reviewed(
        course_id=course.id, org_id=ORG_ID, node_id=node.id, actor_id=ACTOR_ID
    )
    assert stamped.reviewed_at is not None
    assert stamped.reviewed_by == ACTOR_ID


# --------------------------------------------------------------------------- #
# validate: the only door
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_validate_flips_status_and_delivery_and_audits() -> None:
    course = make_course()
    node = make_node(course, position=1)
    service, _, audit_repo, _ = make_service(course, [node])

    snapshot = await service.validate(
        course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID
    )

    assert snapshot.course.schema_status == CourseSchemaStatus.VALIDATED
    assert snapshot.course.delivery_mode == CourseDeliveryMode.DYNAMIC
    assert snapshot.course.status == ContentStatus.PUBLISHED
    assert snapshot.course.schema_validated_by == ACTOR_ID
    assert snapshot.course.schema_validated_at is not None
    assert audit_repo.rows[0]["action"] == "course_schema_validated"
    assert audit_repo.rows[0]["detail"]["node_count"] == 1
    experience_plan = audit_repo.rows[0]["detail"]["experience_plan"]
    assert experience_plan["planner_version"] == "neutral-experience-plan/1"
    assert experience_plan["planned_intents"] == 3
    assert experience_plan["planned_variants"] == 3
    assert len(experience_plan["plan_digest"]) == 64
    materialization = audit_repo.rows[0]["detail"]["experience_materialization"]
    assert materialization["materializer_version"] == (
        "neutral-experience-materializer/1"
    )
    assert materialization["planned_bindings"] >= 1
    assert len(materialization["materialization_digest"]) == 64
    ensure_node_servable(snapshot.course, node)


@pytest.mark.asyncio
async def test_neutral_plan_must_succeed_before_dynamic_is_activated() -> None:
    course = make_course()
    node = make_node(course, position=1)

    class FailingPlanner:
        async def plan_course(self, **kwargs):
            assert course.schema_status == CourseSchemaStatus.PROPOSED
            assert course.delivery_mode == CourseDeliveryMode.STATIC
            raise RuntimeError("planning failed")

    service, _, audit_repo, _ = make_service(
        course, [node], experience_planner=FailingPlanner()
    )

    with pytest.raises(RuntimeError, match="planning failed"):
        await service.validate(
            course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID
        )

    assert course.schema_status == CourseSchemaStatus.PROPOSED
    assert course.delivery_mode == CourseDeliveryMode.STATIC
    assert audit_repo.rows == []


@pytest.mark.asyncio
async def test_validate_does_not_unarchive_a_hidden_course() -> None:
    course = make_course()
    course.status = ContentStatus.ARCHIVED
    node = make_node(course, position=1)
    service, _, _, _ = make_service(course, [node])

    snapshot = await service.validate(
        course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID
    )

    assert snapshot.course.schema_status == CourseSchemaStatus.VALIDATED
    assert snapshot.course.status == ContentStatus.ARCHIVED


@pytest.mark.asyncio
async def test_validate_refuses_an_unreviewed_node() -> None:
    course = make_course()
    node = make_node(course, position=1, reviewed=False)
    service, _, audit_repo, _ = make_service(course, [node])

    with pytest.raises(SchemaInvalid) as excinfo:
        await service.validate(
            course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID
        )

    codes = [error["code"] for error in excinfo.value.payload()["errors"]]
    assert "node_not_reviewed" in codes
    assert course.schema_status == CourseSchemaStatus.PROPOSED
    assert course.delivery_mode == CourseDeliveryMode.STATIC
    assert audit_repo.rows == []


@pytest.mark.asyncio
async def test_validate_refuses_a_cyclic_graph() -> None:
    course = make_course()
    a = make_node(course, position=1, title="A")
    b = make_node(course, position=2, title="B")
    service, node_repo, _, _ = make_service(course, [a, b])
    node_repo.edges = {a.id: [b.id], b.id: [a.id]}

    with pytest.raises(SchemaInvalid) as excinfo:
        await service.validate(
            course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID
        )
    assert excinfo.value.payload()["code"] == "schema_invalid"
    assert "cycle" in [e["code"] for e in excinfo.value.payload()["errors"]]


@pytest.mark.asyncio
async def test_validate_does_not_pregenerate_probes() -> None:
    """Validating a course must not spend an LLM call per node on the probe.

    Origin 1 of §7.1 used to run here, warming ``course_nodes.probe_items`` for every
    node of every course. Nothing consumed it: no client calls ``POST /nodes/{id}/probe``,
    so the questions were generated and never asked, inside the critical path of course
    creation. §7.1's other two origins still cover the probe if it is ever wired up, so it
    generates on first use instead. See ``docs/design/future-progression-modes.md``.
    """
    course = make_course()
    node = make_node(course, position=1)
    assert not node.probe_items  # a fresh node starts without them

    service, _, audit_repo, _ = make_service(course, [node])
    await service.validate(course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID)

    assert not node.probe_items
    assert "probes_pregenerated" not in audit_repo.rows[0]["detail"]


# --------------------------------------------------------------------------- #
# §7.5 enrollment closure recompute
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_new_critical_node_reopens_a_completed_enrollment() -> None:
    course = make_course()
    user_id = uuid.uuid4()
    mastered = make_node(course, position=1, title="Plazo")
    fresh = make_node(course, position=2, title="Nuevo critico")
    service, node_repo, audit_repo, enrollment_repo = make_service(
        course,
        [mastered, fresh],
        enrollments=[FakeEnrollment(user_id, EnrollmentStatus.COMPLETED)],
    )
    node_repo.mastery = [(user_id, mastered.id, "mastered", 0.95, None)]

    await service.unvalidate(course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID)

    enrollment = enrollment_repo.enrollments[0]
    assert enrollment.status == EnrollmentStatus.IN_PROGRESS
    assert enrollment.completed_at is None
    assert audit_repo.rows[0]["detail"]["enrollments_recomputed"] == {
        "completed": 0,
        "reopened": 1,
    }


@pytest.mark.asyncio
async def test_archiving_the_missing_node_completes_a_stuck_enrollment() -> None:
    course = make_course()
    user_id = uuid.uuid4()
    mastered = make_node(course, position=1, title="Plazo")
    blocking = make_node(course, position=2, title="Bloqueante")
    service, node_repo, _, enrollment_repo = make_service(
        course,
        [mastered, blocking],
        enrollments=[FakeEnrollment(user_id, EnrollmentStatus.IN_PROGRESS)],
    )
    node_repo.mastery = [(user_id, mastered.id, "mastered", 0.9, None)]
    node_repo.attempts[blocking.id] = 2  # has progress -> archived, not deleted

    await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[node_payload(mastered)],
    )

    enrollment = enrollment_repo.enrollments[0]
    assert blocking.archived is True
    assert enrollment.status == EnrollmentStatus.COMPLETED
    # Closed by a schema edit, and closing writes no mark: the recompute and the runtime
    # share `apply_dynamic_closure`, so neither can invent a number the other would not.
    assert enrollment.score is None


@pytest.mark.asyncio
async def test_recompute_requires_every_node_mastered() -> None:
    course = make_course()
    user_id = uuid.uuid4()
    first = make_node(course, position=1, title="Plazo")
    optional = make_node(
        course, position=2, title="Tono", criticality=NodeCriticality.CONTEXTUAL
    )
    service, node_repo, _, enrollment_repo = make_service(
        course,
        [first, optional],
        enrollments=[FakeEnrollment(user_id, EnrollmentStatus.IN_PROGRESS)],
    )
    node_repo.mastery = [
        (user_id, first.id, "mastered", 1.0, None),
        (user_id, optional.id, "learning", 0.2, None),
    ]

    # The non-critical node now blocks closure: the enrollment stays in progress.
    result = await service.recompute_enrollment_closure(course, org_id=ORG_ID)
    assert result == {"completed": 0, "reopened": 0}
    assert enrollment_repo.enrollments[0].status == EnrollmentStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_a_course_finished_by_reading_it_is_not_reopened() -> None:
    """A closed enrollment survives a schema edit when its nodes were never mastered.

    The regression this guards lives in a projection, not in a rule: ``mastery_rows``
    returns ``completed_at`` as the fifth column and ``recompute_enrollment_closure``
    feeds it into ``NodeProgressRow``. Drop it — hand ``None`` where the timestamp
    belongs — and every node the learner worked through reads as ``not_started`` with
    nothing finished, so ``node_is_done`` says "not done" and the next schema edit
    reopens every enrollment that had closed that way. Mastery cannot rescue those
    nodes: an expository node carries no graded item to master, which is why
    ``completed_at`` exists (migration 0029).
    """
    course = make_course()
    user_id = uuid.uuid4()
    read = make_node(course, position=1, title="Ejemplo resuelto")
    checklist = make_node(course, position=2, title="Checklist")
    service, node_repo, _, enrollment_repo = make_service(
        course,
        [read, checklist],
        enrollments=[FakeEnrollment(user_id, EnrollmentStatus.COMPLETED)],
    )
    closed_at = enrollment_repo.enrollments[0].completed_at
    finished_at = datetime.now(timezone.utc)
    # Worked through to the end, never mastered: no graded item to answer.
    node_repo.mastery = [
        (user_id, read.id, "not_started", 0.0, finished_at),
        (user_id, checklist.id, "not_started", 0.0, finished_at),
    ]

    result = await service.recompute_enrollment_closure(course, org_id=ORG_ID)

    assert result == {"completed": 0, "reopened": 0}
    enrollment = enrollment_repo.enrollments[0]
    assert enrollment.status == EnrollmentStatus.COMPLETED
    assert enrollment.completed_at == closed_at


# --------------------------------------------------------------------------- #
# Position handling and payload hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_put_defers_the_position_constraint_and_can_swap_positions() -> None:
    course = make_course()
    first = make_node(course, position=1, title="A")
    second = make_node(course, position=2, title="B")
    service, node_repo, _, _ = make_service(course, [first, second])

    await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[node_payload(second, position=1), node_payload(first, position=2)],
    )

    assert node_repo.deferred is True
    assert (first.position, second.position) == (2, 1)


@pytest.mark.asyncio
async def test_put_rejects_a_node_id_from_another_course() -> None:
    course = make_course()
    node = make_node(course, position=1)
    service, _, _, _ = make_service(course, [node])

    with pytest.raises(UnknownNode):
        await service.update(
            course_id=course.id,
            org_id=ORG_ID,
            actor_id=ACTOR_ID,
            nodes=[node_payload(node, id=uuid.uuid4())],
        )


@pytest.mark.asyncio
async def test_put_drops_unknown_prerequisites_with_a_warning() -> None:
    course = make_course()
    node = make_node(course, position=1)
    service, node_repo, _, _ = make_service(course, [node])

    snapshot = await service.update(
        course_id=course.id,
        org_id=ORG_ID,
        actor_id=ACTOR_ID,
        nodes=[node_payload(node, prerequisite_node_ids=[uuid.uuid4()])],
    )
    assert node_repo.edges[node.id] == []
    assert any("desconocido" in warning for warning in snapshot.warnings)


@pytest.mark.asyncio
async def test_put_bumps_the_schema_version_once() -> None:
    course = make_course()
    node = make_node(course, position=1)
    service, _, _, _ = make_service(course, [node])

    await service.update(
        course_id=course.id, org_id=ORG_ID, actor_id=ACTOR_ID,
        nodes=[node_payload(node)], intent_density=5,
    )
    assert course.schema_version == 2
    assert course.intent_density == 5
