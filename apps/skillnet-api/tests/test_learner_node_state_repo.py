"""The one read that spans the node graph and the learner's state (§3.3).

There is no Postgres in this environment (§12.2) and ``course_nodes`` uses
``ARRAY``/``JSONB``, so SQLite cannot stand in. What *can* be checked without a
database is the shape of the statement, and for this query the shape is the whole
risk: the two ways ``revisar_prerrequisito`` silently stops firing are an inner
join instead of a left join, and the user predicate drifting from the ON clause
into the WHERE clause (which turns a left join back into an inner one). Both are
invisible in a green test suite and both are asserted here.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from src.repositories.learner_node_state_repo import (
    LearnerNodeStateRepository,
    unmastered_prerequisites_query,
)

USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
NODE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
PREREQ_A = uuid.UUID("33333333-3333-3333-3333-333333333333")
PREREQ_B = uuid.UUID("44444444-4444-4444-4444-444444444444")


def compiled() -> str:
    query = unmastered_prerequisites_query(user_id=USER_ID, node_id=NODE_ID)
    return str(
        query.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class FakeSession:
    def __init__(self, rows: list) -> None:
        self.rows = rows
        self.statements: list[str] = []

    async def execute(self, query):
        self.statements.append(str(query))
        return FakeResult(self.rows)


def test_the_join_to_learner_state_is_a_left_join() -> None:
    """A prerequisite nobody opened has no row; an inner join would hide it."""
    sql = compiled()
    assert "LEFT OUTER JOIN learner_node_states" in sql
    assert "JOIN learner_node_states ON" not in sql.replace("LEFT OUTER JOIN", "LEFT")


def test_the_user_predicate_stays_in_the_on_clause() -> None:
    """In the WHERE clause it would drop every NULL row and re-inner the join."""
    sql = compiled()
    on_clause, _, where_clause = sql.partition("\nWHERE ")
    assert f"learner_node_states.user_id = '{USER_ID}'" in on_clause
    assert "user_id" not in where_clause


def test_only_unmastered_prerequisites_of_this_node_are_returned() -> None:
    sql = compiled()
    _, _, where_clause = sql.partition("\nWHERE ")
    assert f"course_node_prerequisites.node_id = '{NODE_ID}'" in where_clause
    assert "learner_node_states.id IS NULL" in where_clause
    assert "learner_node_states.state != 'mastered'" in where_clause
    assert "SELECT course_node_prerequisites.prerequisite_node_id" in sql


def test_archived_prerequisites_are_excluded() -> None:
    """§11.1 archives a worked-on node instead of deleting it, edges and all.

    Counting one would send the learner back to a node the course no longer
    teaches, with no way to ever clear the signal.
    """
    sql = compiled()
    assert "JOIN course_nodes AS" in sql
    _, _, where_clause = sql.partition("\nWHERE ")
    assert ".archived IS false" in where_clause


async def test_the_repository_returns_the_ids_not_a_count() -> None:
    """``len()`` feeds ``NodeSignalContext``; the ids make the action actionable."""
    session = FakeSession([PREREQ_A, PREREQ_B])
    repo = LearnerNodeStateRepository(session)  # type: ignore[arg-type]

    result = await repo.unmastered_prerequisites(user_id=USER_ID, node_id=NODE_ID)

    assert result == [PREREQ_A, PREREQ_B]
    assert len(session.statements) == 1
    assert "course_node_prerequisites" in session.statements[0]


async def test_a_fully_mastered_learner_gets_an_empty_list() -> None:
    session = FakeSession([])
    repo = LearnerNodeStateRepository(session)  # type: ignore[arg-type]
    assert await repo.unmastered_prerequisites(user_id=USER_ID, node_id=NODE_ID) == []
