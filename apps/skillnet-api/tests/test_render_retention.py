"""The startup sweep of ``node_renders``, and the guard that keeps its list honest.

No database (there is none in CI, §12.2). The foreign keys are read off
``Base.metadata``, which is the same declaration Alembic generates the schema from, and
the sweep's SQL is asserted from the compiled statements a fake session records.

The guard is the point of this file. Deleting a render that something still points at is
damage no error message announces: ``node_render_views.render_id`` is ``ON DELETE
CASCADE`` and the other three are ``SET NULL``, so Postgres would carry out the loss
without a word. The day a fifth table references ``node_renders``, this file fails.
"""

from __future__ import annotations

import uuid

import pytest

from src.models import NodeRender
from src.models.base import Base
from src.services import render_retention
from src.services.render_retention import (
    RENDER_REFERENCES,
    RETENTION_BATCH,
    sweep_evicted_renders,
)

# Every foreign key that points at `node_renders`, written out literally instead of
# derived from RENDER_REFERENCES: a test that reads the same tuple as the code cannot
# notice a missing table. Verified against the live schema on 2026-08-28 with
# `\d node_renders` ("Referenced by").
#
# Adding a row here is not the fix on its own — it is half of it. The other half is
# adding the same reference to RENDER_REFERENCES, which the second test checks.
REFERENCES_TO_NODE_RENDERS = {
    ("node_render_views", "render_id", "CASCADE"),
    ("node_attempts", "render_id", "SET NULL"),
    ("learner_node_states", "active_render_id", "SET NULL"),
    ("activity_definitions", "source_render_id", "SET NULL"),
}


def _schema_references() -> set[tuple[str, str, str]]:
    """Every FK into ``node_renders``, straight from the ORM declaration."""
    found: set[tuple[str, str, str]] = set()
    for table in Base.metadata.sorted_tables:
        for foreign_key in table.foreign_keys:
            if foreign_key.column.table.name == NodeRender.__tablename__:
                found.add(
                    (table.name, foreign_key.parent.name, str(foreign_key.ondelete))
                )
    return found


def test_the_schema_has_exactly_the_references_this_file_knows_about():
    """A new foreign key into node_renders must be declared here in the same release."""
    assert _schema_references() == REFERENCES_TO_NODE_RENDERS, (
        "the foreign keys pointing at node_renders changed. The retention sweep deletes "
        "a render only when NOTHING references it, so an unlisted reference means it "
        "will delete rows that are in use — silently, because SET NULL and CASCADE do "
        "not raise. Add the reference to REFERENCES_TO_NODE_RENDERS *and* to "
        "RENDER_REFERENCES in src/services/render_retention.py."
    )


def test_the_sweep_checks_every_reference_the_schema_declares():
    """The half that catches "documented but not implemented"."""
    swept = {
        (reference.table, reference.column, reference.on_delete)
        for reference in RENDER_REFERENCES
    }
    assert swept == REFERENCES_TO_NODE_RENDERS, (
        "src/services/render_retention.py checks a different set of references than the "
        "schema declares. Every foreign key into node_renders has to be in "
        "RENDER_REFERENCES or the sweep will delete rows it protects."
    )


class FakeResult:
    def __init__(self, ids: list[uuid.UUID] | None = None, rowcount: int = 0) -> None:
        self._ids = ids or []
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return list(self._ids)


class RecordingSession:
    """Records compiled SQL without executing any of it."""

    def __init__(self, candidates: int = 0, deleted: int | None = None) -> None:
        self.statements: list[str] = []
        self.commits = 0
        self.rollbacks = 0
        self._candidates = [uuid.uuid4() for _ in range(candidates)]
        self._deleted = candidates if deleted is None else deleted

    async def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if sql.lstrip().upper().startswith("DELETE"):
            return FakeResult(rowcount=min(self._deleted, RETENTION_BATCH))
        return FakeResult(ids=self._candidates)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    def statement_starting_with(self, verb: str) -> str | None:
        for sql in self.statements:
            if sql.lstrip().upper().startswith(verb):
                return sql
        return None


@pytest.fixture(autouse=True)
def _sweep_enabled(monkeypatch):
    monkeypatch.setattr(render_retention.settings, "RENDER_CACHE_SWEEP", True)


async def _sweep(session: RecordingSession, **kwargs):
    return await sweep_evicted_renders(session, prompt_version="runtime/43", **kwargs)


@pytest.mark.asyncio
async def test_the_delete_refuses_every_referenced_row():
    """The criterion, read off the SQL: one NOT EXISTS per reference."""
    session = RecordingSession(candidates=3)
    await _sweep(session)

    deletion = session.statement_starting_with("DELETE")
    assert deletion is not None, "nothing was deleted with candidates waiting"
    for reference in RENDER_REFERENCES:
        assert f"FROM {reference.table}" in deletion, (
            f"{reference.table}.{reference.column} references node_renders and the "
            "DELETE does not exclude the rows it points at"
        )
        assert f"{reference.table}.{reference.column} = node_renders.id" in deletion
    assert deletion.count("NOT (EXISTS") == len(RENDER_REFERENCES)


@pytest.mark.asyncio
async def test_only_rows_from_another_prompt_version_are_swept():
    session = RecordingSession(candidates=1)
    await _sweep(session)

    deletion = session.statement_starting_with("DELETE")
    assert "prompt_version IS DISTINCT FROM" in deletion
    # A preview key is salted or hand-written, so a prompt bump proves nothing about it.
    assert "node_renders.is_preview IS false" in deletion


@pytest.mark.asyncio
async def test_a_boot_deletes_at_most_one_batch_and_reports_the_rest():
    """Bounded per boot, idempotent across boots: the queue drains, it is not drained."""
    session = RecordingSession(candidates=RETENTION_BATCH + 7)
    report = await _sweep(session)

    assert report.ran is True
    assert report.deleted == RETENTION_BATCH
    assert report.remaining == 7
    assert report.remaining_is_lower_bound is False
    assert session.commits == 1


@pytest.mark.asyncio
async def test_a_backlog_past_the_probe_is_reported_as_a_lower_bound():
    """The scan stops early on purpose; the log says "at least", not a wrong number."""
    session = RecordingSession(candidates=render_retention._CANDIDATE_PROBE)
    report = await _sweep(session)

    assert report.deleted == RETENTION_BATCH
    assert report.remaining_is_lower_bound is True
    assert report.remaining == render_retention._CANDIDATE_PROBE - RETENTION_BATCH


@pytest.mark.asyncio
async def test_nothing_to_reclaim_issues_no_delete_and_no_commit():
    session = RecordingSession(candidates=0)
    report = await _sweep(session)

    assert report.ran is True
    assert report.deleted == 0
    assert session.statement_starting_with("DELETE") is None
    assert session.commits == 0


@pytest.mark.asyncio
async def test_the_switch_turns_it_off_completely(monkeypatch):
    """Whoever deploys this has the right to say no: no scan, no delete."""
    monkeypatch.setattr(render_retention.settings, "RENDER_CACHE_SWEEP", False)
    session = RecordingSession(candidates=10)

    report = await _sweep(session)

    assert report.ran is False
    assert report.skipped_reason == "disabled"
    assert session.statements == []


@pytest.mark.asyncio
async def test_a_failed_sweep_never_stops_the_api_from_starting():
    """An optional disk reclamation that can block a boot is worse than the disk."""

    class ExplodingSession(RecordingSession):
        async def execute(self, statement):
            raise RuntimeError("database went away mid-sweep")

    session = ExplodingSession()
    report = await _sweep(session)

    assert report.ran is False
    assert report.skipped_reason == "error"
    assert report.deleted == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_the_log_says_how_many_went_and_how_many_are_left(caplog):
    """A silent deletion of data is the thing nobody wants to find out afterwards."""
    session = RecordingSession(candidates=RETENTION_BATCH + 4)

    with caplog.at_level("WARNING"):
        await _sweep(session)

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert str(RETENTION_BATCH) in logged
    assert "4 still waiting" in logged
