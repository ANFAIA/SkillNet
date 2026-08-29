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
from src.services.mastery_service import WORKED_SOLUTION_FAILURES, transition_on_answer
from src.models.learner_node_state import ErrorKind
from src.services.activity_definitions import validated_score


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
    def __init__(self, *chains):
        self.chains = list(chains)
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
        for chain in self.chains:
            if chain.binding.id == binding_id and chain.binding.org_id == org_id:
                return chain
        return None

    async def evidence_for_attempt(self, attempt_id):
        return self.evidence.get(attempt_id, [])

    async def failures_for_binding(self, *, user_id, binding_id):
        return sum(
            row.user_id == user_id
            and row.binding_id == binding_id
            and row.passed is False
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
    def __init__(self, *activities):
        self.activities = {activity.id: activity for activity in activities}
        self.evaluations = 0

    async def get(self, activity_id, org_id):
        activity = self.activities[activity_id]
        assert org_id == activity.org_id
        return activity

    async def evaluate(self, activity, submission):
        assert self.activities[activity.id] is activity
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


#: The rendered worked solution of every activity built below. ``normalized_any`` is used
#: because it is the one mode :func:`render_solution` handles without needing a matching
#: ``public_definition`` collection, so these doubles stay about attempts, not about copy.
SOLUTION = {"solution": "4", "explanation": "Dos más dos."}


def _activity(*, org_id, course_id, node_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        course_id=course_id,
        node_id=node_id,
        component_id="didact.step-sequencer",
        public_definition={"prompt": "¿Cuánto es 2 + 2?"},
        private_definition={
            "evaluation": {
                "mode": "normalized_any",
                "expected": ["4"],
                "explanation": "Dos más dos.",
            }
        },
    )


def _chain_for(activity):
    """One intent/variant/binding triple implementing exactly one activity."""
    intent_id = uuid.uuid4()
    variant_id = uuid.uuid4()
    intent = SimpleNamespace(
        id=intent_id,
        org_id=activity.org_id,
        course_id=activity.course_id,
        node_id=activity.node_id,
        objective_id="safe-lifting",
        objective_version=2,
        required_evidence=["selected_response"],
    )
    variant = SimpleNamespace(id=variant_id, org_id=activity.org_id, intent_id=intent_id)
    binding = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=activity.org_id,
        variant_id=variant_id,
        activity_definition_id=activity.id,
        provider="didact",
        implementation_id="step-sequencer",
        implementation_version=3,
        definition_ref="didact:step-sequencer@3:sha256:definition",
    )
    return SimpleNamespace(binding=binding, variant=variant, intent=intent)


def fixture():
    org_id = uuid.uuid4()
    course_id = uuid.uuid4()
    node_id = uuid.uuid4()
    activity = _activity(org_id=org_id, course_id=course_id, node_id=node_id)
    chain = _chain_for(activity)
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

    # An adapter that does not classify gets `None`, not an invented label. Until
    # 2026-08-30 this asserted `"incorrect_response"` — a value the `error_kind` enum
    # cannot store, so it locked in a 500 on every wrong answer.
    assert generic[-1] is None
    assert adapted[-1] == "procedural"


@pytest.mark.parametrize(
    "evaluated",
    [
        {"outcome": "incorrect", "score": 0.0, "passed": False},
        {"outcome": "partial", "score": 0.5, "passed": False},
        {"outcome": "correct", "score": 1.0, "passed": True},
        {"outcome": "incorrect", "score": 0.0, "passed": False, "error_kind": "conceptual"},
        {"outcome": "incorrect", "score": 0.0, "passed": False, "error_kind": "incorrect_response"},
        {"outcome": "incorrect", "score": 0.0, "passed": False, "error_kind": "vaguely_wrong"},
    ],
)
def test_error_kind_always_fits_the_column(evaluated):
    """Whatever comes out has to be storable, or the request 500s in the learner's face.

    `last_error_kind` is a Postgres enum. Both scoring bridges are checked, because they
    are copies of each other and the bug was in both.
    """
    valid = {k.value for k in ErrorKind}

    from_attempts = ExperienceAttemptService._validated_score(evaluated)[-1]
    from_evaluate = validated_score(evaluated)[-1]

    assert from_attempts is None or from_attempts in valid
    assert from_evaluate is None or from_evaluate in valid
    assert from_attempts == from_evaluate


class CountingSession:
    """Captures the SQL a repository builds, without a database behind it."""

    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return SimpleNamespace(scalar_one=lambda: 0)


@pytest.mark.asyncio
async def test_the_failure_counter_is_scoped_to_the_binding_and_not_to_the_node():
    """Pinned in SQL, because the doubles above can only mirror what the query does.

    ``node_id`` in this WHERE clause is the regression itself: it makes one failure budget
    for every activity in the node.
    """
    session = CountingSession()
    repository = ExperienceAttemptRepository(session)

    assert await repository.failures_for_binding(
        user_id=uuid.uuid4(), binding_id=uuid.uuid4()
    ) == 0
    where = session.statements[0]
    assert "experience_attempts.binding_id" in where
    assert "experience_attempts.node_id" not in where
    assert "experience_attempts.passed IS false" in where


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


# --------------------------------------------------------------------------------------
# Two activities under one node, and the worked solution `/attempts` promises
#
# Everything above this line runs a single activity per node, which is the one shape where
# "failures of this item", "failures of this node" and "failures of this node ever" are the
# same number — so it could not see rule 8's counter being read node-wide. These use the
# real `transition_on_answer`, because the claim under test is what the learner is shown.
# --------------------------------------------------------------------------------------
class RuleMastery:
    """``MasteryEvidenceService`` with the persistence removed and the rule kept.

    Node-scoped streaks, exactly like ``learner_node_states``: two activities in one node
    share the streak counters and must *not* share the per-item failure count.
    """

    def __init__(self):
        self.calls = []
        self.mastery = 0.4
        self.consecutive_correct = 0
        self.consecutive_failed = 0

    async def apply(self, **values):
        self.calls.append(values)
        transition = transition_on_answer(
            state="learning",
            mastery=self.mastery,
            consecutive_correct=self.consecutive_correct,
            consecutive_failed=self.consecutive_failed,
            score=values["score"],
            passed=values["passed"],
            threshold=0.8,
            hints_used=values.get("hints_used", 0),
            item_failures=values.get("item_failures", 0),
            error_kind=values.get("error_kind"),
        )
        self.mastery = float(transition.changes.get("mastery", self.mastery))
        self.consecutive_correct = int(transition.changes.get("consecutive_correct", 0))
        self.consecutive_failed = int(transition.changes.get("consecutive_failed", 0))
        return SimpleNamespace(
            state=SimpleNamespace(
                state=transition.to_state,
                mastery=self.mastery,
                consecutive_correct=self.consecutive_correct,
                consecutive_failed=self.consecutive_failed,
            ),
            transition=transition,
        )


def node_with_two_activities():
    """One learner, one node, two activities — the case the old fixture could not express."""
    org_id = uuid.uuid4()
    course_id = uuid.uuid4()
    node_id = uuid.uuid4()
    first = _activity(org_id=org_id, course_id=course_id, node_id=node_id)
    second = _activity(org_id=org_id, course_id=course_id, node_id=node_id)
    chains = [_chain_for(first), _chain_for(second)]
    node = SimpleNamespace(id=node_id, org_id=org_id, course_id=course_id, archived=False)
    course = SimpleNamespace(
        id=course_id, org_id=org_id, delivery_mode="dynamic", schema_status="validated"
    )
    user = SimpleNamespace(id=uuid.uuid4(), org_id=org_id, role="employee")
    mastery = RuleMastery()
    subject = ExperienceAttemptService(
        Session(),
        attempts=Attempts(*chains),
        activities=Activities(first, second),
        mastery=mastery,
        nodes=ScopedRepo(node),
        courses=ScopedRepo(course),
        enrollments=Enrollments(),
    )

    async def submit(index, *, answer="wrong", attempt_id=None):
        return await subject.submit(
            user=user,
            activity_id=(first, second)[index].id,
            body=ExperienceAttemptSubmission(
                attempt_id=attempt_id or uuid.uuid4(),
                binding_id=chains[index].binding.id,
                submission={"answer": answer},
            ),
        )

    return submit, mastery


@pytest.mark.asyncio
async def test_failing_one_activity_never_opens_the_next_ones_solution():
    """Rule 8's counter is per activity. Failing A must leave B untouched.

    The counter used to be ``COUNT(*) WHERE node_id = ...``: every failure the learner had
    ever recorded anywhere in the node. Once four had piled up, the *next* activity handed
    over its worked solution on the first attempt, and so did every one after it, for ever —
    which does not trap anybody but empties the node's evidence of meaning, and that
    evidence is what accredits a skill.
    """
    submit, mastery = node_with_two_activities()

    for _ in range(WORKED_SOLUTION_FAILURES):
        opened = await submit(0)
    assert opened.result["show_worked_solution"] is True

    first_failure_on_b = await submit(1)

    assert mastery.calls[-1]["item_failures"] == 0
    assert first_failure_on_b.result["show_worked_solution"] is False
    assert first_failure_on_b.result["solution"] is None


@pytest.mark.asyncio
async def test_each_activity_reaches_its_own_exit_on_its_own_fourth_failure():
    """B is not blocked either: its own four failures still open its own solution."""
    submit, _mastery = node_with_two_activities()

    for _ in range(WORKED_SOLUTION_FAILURES):
        await submit(0)
    for _ in range(WORKED_SOLUTION_FAILURES - 1):
        interim = await submit(1)
        assert interim.result["show_worked_solution"] is False

    assert (await submit(1)).result["show_worked_solution"] is True


@pytest.mark.asyncio
async def test_attempts_sends_the_solution_it_promises_to_show():
    """The promise and the thing promised travel together, or the screen is a dead end.

    ``show_worked_solution: true`` closes the activity in the client and takes the retry
    button away. Announcing it while sending no ``solution`` leaves an empty panel and no
    way back — the same cul-de-sac ``/evaluate`` had, one port further along.
    """
    submit, _mastery = node_with_two_activities()

    for _ in range(WORKED_SOLUTION_FAILURES - 1):
        ordinary = await submit(0)
        assert ordinary.result["show_worked_solution"] is False
        assert ordinary.result["solution"] is None

    opened = await submit(0)

    assert opened.result["show_worked_solution"] is True
    assert opened.result["solution"] == SOLUTION


@pytest.mark.asyncio
async def test_a_pass_reveals_the_solution_and_a_replay_reveals_it_again():
    """Same gate as ``/evaluate``: ``passed or show_worked_solution``, replay included."""
    submit, _mastery = node_with_two_activities()
    attempt_id = uuid.uuid4()

    first = await submit(0, answer="4", attempt_id=attempt_id)
    replay = await submit(0, answer="4", attempt_id=attempt_id)

    assert first.passed is True
    assert first.result["solution"] == SOLUTION
    # The row is immutable and holds no answer key; the replay re-renders from the activity.
    assert replay.result["solution"] == SOLUTION
