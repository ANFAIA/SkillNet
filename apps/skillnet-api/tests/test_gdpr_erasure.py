"""Art. 17 erasure really erases: the nine tables, in an order the FKs allow (§3.3, §11.2).

No database (there is none in CI, §12.2): the fake session records the SQL the
repository emits, and the assertions read the compiled statements. That is enough to
catch the bug this file exists for — ``DELETE /users/me/learner-profile`` answered
``204`` while never touching ``node_attempts`` or ``node_probes``, the two tables
that store the text the employee typed.

The order matters as much as the list: ``node_attempts.probe_id`` references
``node_probes.id ON DELETE SET NULL`` (``0005_dynamic_courses.py``), so attempts must
go before probes or Postgres has to fire an UPDATE over rows that are about to be
deleted anyway.
"""

from __future__ import annotations

import re
import uuid

import pytest

from src.repositories.learner_profile_repo import (
    ERASURE_ORDER,
    LearnerProfileRepository,
)

# Every table that holds personal rows of one learner (§3.6 minus the shared and the
# org-level ones). Written out literally instead of derived from ERASURE_ORDER: a
# test that reads the same tuple as the code cannot notice a missing table.
PERSONAL_TABLES = (
    "node_render_views",
    "node_feedback",
    "experience_attempts",
    "node_attempts",
    # Per-(user, activity) failure and disclosure counts (migration 0035). As personal as
    # an attempt row: it is the record of how often this learner missed this question.
    "learner_activity_states",
    "node_probes",
    "learner_node_states",
    "learning_events",
    "learner_profiles",
)


class FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class RecordingSession:
    """Records compiled SQL without executing any of it."""

    def __init__(self, rowcount: int = 1) -> None:
        self.statements: list[str] = []
        self.flushes = 0
        self._rowcount = rowcount

    async def execute(self, statement):
        self.statements.append(str(statement))
        return FakeResult(self._rowcount)

    async def flush(self) -> None:
        self.flushes += 1

    def deleted_tables(self) -> list[str]:
        """Tables named by a DELETE, in the order they were issued."""
        found = []
        for statement in self.statements:
            match = re.match(r"\s*DELETE FROM ([a-z_]+)", statement)
            if match:
                found.append(match.group(1))
        return found


async def _erase() -> tuple[RecordingSession, dict[str, int]]:
    session = RecordingSession()
    repo = LearnerProfileRepository(session)  # type: ignore[arg-type]
    counts = await repo.erase_user_data(uuid.uuid4())
    return session, counts


@pytest.mark.asyncio
async def test_erasure_deletes_all_personal_tables() -> None:
    """New evidence stores must join erasure in the same release that creates them."""
    session, counts = await _erase()

    assert set(session.deleted_tables()) == set(PERSONAL_TABLES)
    for table in PERSONAL_TABLES:
        assert table in counts, f"{table} is missing from the erasure report"


@pytest.mark.asyncio
async def test_erasure_deletes_the_tables_that_hold_the_written_answers() -> None:
    """The regression itself: the two tables with the employee's own text."""
    session, counts = await _erase()

    deleted = session.deleted_tables()
    assert "node_attempts" in deleted
    assert "node_probes" in deleted
    assert counts["node_attempts"] == 1
    assert counts["node_probes"] == 1


@pytest.mark.asyncio
async def test_attempts_are_deleted_before_probes_so_the_set_null_never_fires() -> None:
    """``node_attempts.probe_id -> node_probes.id ON DELETE SET NULL`` (0005)."""
    deleted = (await _erase())[0].deleted_tables()
    assert deleted.index("node_attempts") < deleted.index("node_probes")


@pytest.mark.asyncio
async def test_shared_renders_are_anonymized_and_never_deleted() -> None:
    """§3.4: deleting them would destroy other employees' content and evidence."""
    session, counts = await _erase()

    assert "node_renders" not in session.deleted_tables()
    assert any("UPDATE node_renders" in sql for sql in session.statements)
    assert counts["node_renders_anonymized"] == 1


@pytest.mark.asyncio
async def test_erasure_flushes_once_and_lets_the_route_commit() -> None:
    session, _ = await _erase()
    assert session.flushes == 1


def test_the_erasure_order_and_the_personal_table_list_agree() -> None:
    """Guards the other direction: a table added to the code but not to this test."""
    assert [label for label, _model, _column in ERASURE_ORDER] == list(PERSONAL_TABLES)
