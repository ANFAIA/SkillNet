import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.core.exceptions import ConflictError, ForbiddenError
from src.repositories.experience_attempt_repo import ExperienceAttemptRepository
from src.routes import activities as activity_routes
from src.schemas.learning_experience import ExperienceAttemptSubmission
from src.services.experience_attempt_service import (
    ExperienceAttemptService,
    attempt_request_digest,
)


class Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class StatementSession:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))


class Attempts:
    def __init__(self, chain):
        self.chain = chain
        self.rows = {}
        self.evidence = {}
        self.locks = []
        self.creates = 0
        self.fail_create = False

    async def lock_attempt(self, attempt_id):
        self.locks.append(("attempt", attempt_id))

    async def lock_learner_node(self, *, user_id, node_id):
        self.locks.append(("node", user_id, node_id))

    async def get_attempt(self, attempt_id):
        return self.rows.get(attempt_id)

    async def get_binding_chain(self, *, binding_id, org_id):
        if binding_id != self.chain.binding.id or org_id != self.chain.binding.org_id:
            return None
        return self.chain

    async def evidence_for_attempt(self, attempt_id):
        return self.evidence.get(attempt_id, [])

    async def prior_failures(self, *, user_id, node_id):
        return sum(
            row.user_id == user_id and row.node_id == node_id and row.passed is False
            for row in self.rows.values()
        )

    async def create_attempt(self, *, attempt, evidence):
        self.creates += 1
        if self.fail_create:
            raise RuntimeError("insert failed")
        now = datetime.now(timezone.utc)
        attempt.created_at = now
        for row in evidence:
            row.created_at = now
        self.rows[attempt.id] = attempt
        self.evidence[attempt.id] = evidence


class Activities:
    def __init__(self, activity):
        self.activity = activity
        self.evaluations = 0

    async def get(self, activity_id, org_id):
        assert activity_id == self.activity.id
        assert org_id == self.activity.org_id
        return self.activity

    async def evaluate(self, activity, submission):
        assert activity is self.activity
        self.evaluations += 1
        return {
            "outcome": "correct" if submission.get("answer") == "4" else "incorrect",
            "score": 1.0 if submission.get("answer") == "4" else 0.0,
            "passed": submission.get("answer") == "4",
            "feedback": "Comprobado por el servidor",
        }


class ScopedRepo:
    def __init__(self, row):
        self.row = row

    async def get_scoped(self, row_id, org_id):
        if row_id == self.row.id and org_id == self.row.org_id:
            return self.row
        return None


class Enrollments:
    def __init__(self, enrolled=True):
        self.enrolled = enrolled

    async def get_by_user_and_course(self, user_id, course_id):
        return SimpleNamespace() if self.enrolled else None


class Mastery:
    def __init__(self):
        self.calls = []

    async def apply(self, **values):
        self.calls.append(values)
        return SimpleNamespace(
            state=SimpleNamespace(
                state="learning",
                mastery=0.72,
                consecutive_correct=1,
                consecutive_failed=0,
            ),
            transition=SimpleNamespace(show_worked_solution=False),
        )


def fixture():
    org_id = uuid.uuid4()
    course_id = uuid.uuid4()
    node_id = uuid.uuid4()
    activity_id = uuid.uuid4()
    intent_id = uuid.uuid4()
    variant_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    activity = SimpleNamespace(
        id=activity_id,
        org_id=org_id,
        course_id=course_id,
        node_id=node_id,
        component_id="didact.step-sequencer",
    )
    intent = SimpleNamespace(
        id=intent_id,
        org_id=org_id,
        course_id=course_id,
        node_id=node_id,
        objective_id="safe-lifting",
        objective_version=2,
        required_evidence=["selected_response"],
    )
    variant = SimpleNamespace(id=variant_id, org_id=org_id, intent_id=intent_id)
    binding = SimpleNamespace(
        id=binding_id,
        org_id=org_id,
        variant_id=variant_id,
        activity_definition_id=activity_id,
        provider="didact",
        implementation_id="step-sequencer",
        implementation_version=3,
        definition_ref="didact:step-sequencer@3:sha256:definition",
    )
    chain = SimpleNamespace(binding=binding, variant=variant, intent=intent)
    node = SimpleNamespace(
        id=node_id,
        org_id=org_id,
        course_id=course_id,
        archived=False,
    )
    course = SimpleNamespace(
        id=course_id,
        org_id=org_id,
        delivery_mode="dynamic",
        schema_status="validated",
    )
    user = SimpleNamespace(id=uuid.uuid4(), org_id=org_id, role="employee")
    return activity, chain, node, course, user


def service(*, enrolled=True):
    activity, chain, node, course, user = fixture()
    session = Session()
    attempts = Attempts(chain)
    activity_service = Activities(activity)
    mastery = Mastery()
    subject = ExperienceAttemptService(
        session,
        attempts=attempts,
        activities=activity_service,
        mastery=mastery,
        nodes=ScopedRepo(node),
        courses=ScopedRepo(course),
        enrollments=Enrollments(enrolled),
    )
    return subject, session, attempts, activity_service, mastery, activity, chain, user


@pytest.mark.asyncio
async def test_submission_is_server_scored_and_exact_retry_is_read_only():
    subject, session, attempts, activities, mastery, activity, chain, user = service()
    body = ExperienceAttemptSubmission(
        attempt_id=uuid.uuid4(),
        binding_id=chain.binding.id,
        submission={"answer": "4"},
        duration_ms=1250,
    )

    first = await subject.submit(user=user, activity_id=activity.id, body=body)
    second = await subject.submit(user=user, activity_id=activity.id, body=body)

    assert first == second
    assert first.score == 1.0
    assert first.result["feedback"] == "Comprobado por el servidor"
    assert first.result["mastery"] == 0.72
    assert first.evidence[0].implementation_ref == "didact:step-sequencer@3:sha256:definition"
    assert activities.evaluations == 1
    assert len(mastery.calls) == 1
    assert attempts.creates == 1
    assert attempts.locks[:2] == [
        ("attempt", body.attempt_id),
        ("node", user.id, activity.node_id),
    ]
    assert session.commits == 0


@pytest.mark.asyncio
async def test_same_attempt_id_with_different_payload_or_user_conflicts():
    subject, _session, _attempts, activities, mastery, activity, chain, user = service()
    attempt_id = uuid.uuid4()
    original = ExperienceAttemptSubmission(
        attempt_id=attempt_id,
        binding_id=chain.binding.id,
        submission={"answer": "4"},
    )
    await subject.submit(user=user, activity_id=activity.id, body=original)

    with pytest.raises(ConflictError, match="another submission"):
        await subject.submit(
            user=user,
            activity_id=activity.id,
            body=original.model_copy(update={"submission": {"answer": "5"}}),
        )
    with pytest.raises(ConflictError, match="another submission"):
        await subject.submit(
            user=SimpleNamespace(id=uuid.uuid4(), org_id=user.org_id, role="employee"),
            activity_id=activity.id,
            body=original,
        )

    assert activities.evaluations == 1
    assert len(mastery.calls) == 1


@pytest.mark.asyncio
async def test_failed_persistence_never_commits_partial_mastery():
    subject, session, attempts, _activities, mastery, activity, chain, user = service()
    attempts.fail_create = True
    body = ExperienceAttemptSubmission(
        attempt_id=uuid.uuid4(),
        binding_id=chain.binding.id,
        submission={"answer": "4"},
    )

    with pytest.raises(RuntimeError, match="insert failed"):
        await subject.submit(user=user, activity_id=activity.id, body=body)

    assert len(mastery.calls) == 1
    assert session.commits == 0
    assert body.attempt_id not in attempts.rows


@pytest.mark.asyncio
async def test_employee_must_be_enrolled():
    subject, _session, attempts, activities, mastery, activity, chain, user = service(
        enrolled=False
    )
    body = ExperienceAttemptSubmission(
        attempt_id=uuid.uuid4(),
        binding_id=chain.binding.id,
        submission={"answer": "4"},
    )

    with pytest.raises(ForbiddenError, match="not enrolled"):
        await subject.submit(user=user, activity_id=activity.id, body=body)

    assert activities.evaluations == 0
    assert mastery.calls == []
    assert attempts.creates == 0


def test_request_digest_covers_all_client_fields_and_route_identity():
    body = ExperienceAttemptSubmission(
        attempt_id=uuid.uuid4(),
        binding_id=uuid.uuid4(),
        submission={"b": 2, "a": [1]},
        duration_ms=10,
    )
    activity_id = uuid.uuid4()

    assert attempt_request_digest(activity_id=activity_id, body=body) == attempt_request_digest(
        activity_id=activity_id,
        body=body.model_copy(update={"submission": {"a": [1], "b": 2}}),
    )
    assert attempt_request_digest(activity_id=activity_id, body=body) != attempt_request_digest(
        activity_id=activity_id,
        body=body.model_copy(update={"duration_ms": 11}),
    )


def test_client_attempt_contract_rejects_server_owned_scoring():
    with pytest.raises(PydanticValidationError):
        ExperienceAttemptSubmission(
            attempt_id=uuid.uuid4(),
            binding_id=uuid.uuid4(),
            submission={"answer": "4"},
            score=1.0,
        )


def test_error_classification_is_adapter_owned_not_component_owned():
    generic = ExperienceAttemptService._validated_score(
        {"outcome": "incorrect", "score": 0.0, "passed": False}
    )
    adapted = ExperienceAttemptService._validated_score(
        {
            "outcome": "incorrect",
            "score": 0.0,
            "passed": False,
            "error_kind": "procedural",
        }
    )

    assert generic[-1] == "incorrect_response"
    assert adapted[-1] == "procedural"


@pytest.mark.asyncio
async def test_repository_uses_transaction_scoped_postgres_locks():
    session = StatementSession()
    repository = ExperienceAttemptRepository(session)
    attempt_id = uuid.uuid4()
    user_id = uuid.uuid4()
    node_id = uuid.uuid4()

    await repository.lock_attempt(attempt_id)
    await repository.lock_learner_node(user_id=user_id, node_id=node_id)

    assert all("pg_advisory_xact_lock" in statement for statement, _ in session.calls)
    assert session.calls[0][1]["lock_key"] != session.calls[1][1]["lock_key"]


@pytest.mark.asyncio
async def test_route_owns_the_single_successful_commit(monkeypatch):
    session = Session()
    expected = object()

    class Service:
        def __init__(self, db):
            assert db is session

        async def submit(self, **_values):
            return expected

    monkeypatch.setattr(activity_routes, "ExperienceAttemptService", Service)
    result = await activity_routes.submit_experience_attempt(
        SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4()),
        session,
        uuid.uuid4(),
        ExperienceAttemptSubmission(
            attempt_id=uuid.uuid4(), binding_id=uuid.uuid4(), submission={}
        ),
    )

    assert result is expected
    assert session.commits == 1


@pytest.mark.asyncio
async def test_route_does_not_commit_a_failed_transaction(monkeypatch):
    session = Session()

    class Service:
        def __init__(self, _db):
            pass

        async def submit(self, **_values):
            raise RuntimeError("atomic write failed")

    monkeypatch.setattr(activity_routes, "ExperienceAttemptService", Service)
    with pytest.raises(RuntimeError, match="atomic write failed"):
        await activity_routes.submit_experience_attempt(
            SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4()),
            session,
            uuid.uuid4(),
            ExperienceAttemptSubmission(
                attempt_id=uuid.uuid4(), binding_id=uuid.uuid4(), submission={}
            ),
        )

    assert session.commits == 0
