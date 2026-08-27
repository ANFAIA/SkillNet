"""What SQL the group repository actually emits, compiled for PostgreSQL.

There is no database in CI, and these statements are the part of the feature a mock can
never check: a `SimpleNamespace` double happily accepts an `add_members` that builds a
broken `INSERT`. So the session is faked but the **repository is the real one** — it is
called normally, and the statement it hands the session is captured and compiled against
the real PostgreSQL dialect. That catches the construction errors a live database would
otherwise be the first to find: a wrong constraint name in `ON CONFLICT`, a `RETURNING`
the dialect refuses, a `JOIN` where a semijoin was meant.

(Compiling a statement written *in the test* would prove nothing about the code. Same
trick, same reason, as `test_gdpr_erasure.py`, which reads the SQL its repository emits.)

Four of these are load-bearing and each is here for a reason a reviewer would ask about:

* the membership insert must be **one** statement with `ON CONFLICT DO NOTHING`, not
  read-then-insert, because two admins ticking the same person race and the loser would
  otherwise take the whole request down with a 500;
* `GET /users?group_id=` must be a **semijoin**, not a `JOIN`: `BaseRepository.list`
  counts with `SELECT count(*) FROM users`, and a join that duplicated a row would
  inflate the total the pagination is computed from;
* `exclude_group_id` must be the exact complement, or the "add people" list offers to add
  somebody who is already in;
* `list_with_counts` must count its members with a **correlated subquery** now that it
  pages: under `LIMIT`/`OFFSET` the old `GROUP BY` over an `outerjoin` would spend a
  page's slots on one popular group, and its `count(*)` would report memberships where
  the rail says groups.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.user_group_repo import UserGroupRepository
from src.repositories.user_repo import UserRepository

GROUP_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_GROUP = uuid.UUID("1111ffff-1111-1111-1111-111111111111")
ORG_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ANA = uuid.UUID("33333333-3333-3333-3333-333333333333")
BRUNO = uuid.UUID("44444444-4444-4444-4444-444444444444")
COURSE = uuid.UUID("55555555-5555-5555-5555-555555555555")


class _Result:
    """Enough of a SQLAlchemy result for the repositories under test."""

    def all(self) -> list[Any]:
        return []

    def scalar_one(self) -> int:
        return 0

    def scalar_one_or_none(self) -> Any:
        return None

    def scalars(self) -> "_Result":
        return self

    def tuples(self) -> "_Result":
        return self


class CapturingSession:
    """Records every statement instead of running it."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any, *_args: Any, **_kwargs: Any) -> _Result:
        self.statements.append(statement)
        return _Result()

    async def scalars(self, statement: Any, *_args: Any, **_kwargs: Any) -> _Result:
        self.statements.append(statement)
        return _Result()

    async def flush(self) -> None:
        return None


def sql_of(session: CapturingSession, index: int = -1) -> str:
    """The captured statement as PostgreSQL would receive it, whitespace-normalised."""
    compiled = session.statements[index].compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compiled).split())


@pytest.fixture
def session() -> CapturingSession:
    return CapturingSession()


@pytest.mark.asyncio
async def test_the_membership_insert_is_one_idempotent_statement(
    session: CapturingSession,
) -> None:
    await UserGroupRepository(session).add_members(GROUP_ID, [ANA, BRUNO])

    sql = sql_of(session)
    assert sql.startswith("INSERT INTO user_group_members")
    # The constraint name has to match the one migration 0030 creates, or Postgres
    # answers "constraint does not exist" at runtime and nothing catches it earlier.
    assert "ON CONFLICT ON CONSTRAINT uq_user_group_members_pair DO NOTHING" in sql
    # RETURNING is how "how many were actually new" is known without a second read.
    assert "RETURNING user_group_members.id" in sql
    # One statement for the whole batch, not one per person.
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_a_repeated_id_does_not_reach_the_insert_twice(
    session: CapturingSession,
) -> None:
    """`ON CONFLICT` covers the race, not a body that names the same person twice.

    Postgres refuses an INSERT whose own VALUES collide on the conflict target
    ("cannot affect row a second time"), so the deduplication has to happen before it.
    """
    await UserGroupRepository(session).add_members(GROUP_ID, [ANA, ANA, BRUNO])

    sql = sql_of(session)
    assert sql.count(str(ANA)) == 1


@pytest.mark.asyncio
async def test_an_empty_membership_edit_writes_nothing(
    session: CapturingSession,
) -> None:
    repo = UserGroupRepository(session)

    assert await repo.add_members(GROUP_ID, []) == 0
    assert await repo.remove_members(GROUP_ID, []) == 0
    # An `INSERT ... VALUES ()` with no rows is a syntax error, and a `DELETE` with an
    # empty `IN` is a full scan that deletes nothing. Neither is emitted.
    assert session.statements == []


@pytest.mark.asyncio
async def test_the_membership_delete_is_scoped_to_the_group(
    session: CapturingSession,
) -> None:
    """A removal must never reach another group's row for the same person."""
    await UserGroupRepository(session).remove_members(GROUP_ID, [ANA])

    sql = sql_of(session)
    assert sql.startswith("DELETE FROM user_group_members")
    assert f"user_group_members.group_id = '{GROUP_ID}'" in sql
    assert "user_group_members.user_id IN" in sql


@pytest.mark.asyncio
async def test_the_group_filter_is_a_semijoin_and_not_a_join(
    session: CapturingSession,
) -> None:
    """A JOIN would duplicate a user per membership row and inflate the page total."""
    await UserRepository(session).list_users(org_id=ORG_ID, group_id=GROUP_ID)

    # `BaseRepository.list` emits the count first, then the page. Both carry the filter.
    joined = " || ".join(sql_of(session, index) for index in range(len(session.statements)))
    assert "IN (SELECT user_group_members.user_id" in joined
    assert "JOIN" not in joined


@pytest.mark.asyncio
async def test_the_exclude_filter_is_the_exact_complement(
    session: CapturingSession,
) -> None:
    await UserRepository(session).list_users(org_id=ORG_ID, exclude_group_id=GROUP_ID)

    joined = " || ".join(sql_of(session, index) for index in range(len(session.statements)))
    assert "NOT IN (SELECT user_group_members.user_id" in joined
    assert "JOIN" not in joined


@pytest.mark.asyncio
async def test_the_person_side_read_counts_members_without_double_joining(
    session: CapturingSession,
) -> None:
    """"Which groups is this person in", asked from the person's record.

    The member count comes from a correlated subquery, not a second join: joining the
    memberships once to find the person's groups and again to count them would multiply
    the outer rows and report every count as the square of itself.
    """
    await UserGroupRepository(session).groups_of_user(ANA, ORG_ID)

    assert len(session.statements) == 1
    sql = sql_of(session)
    assert f"user_group_members.user_id = '{ANA}'" in sql
    assert f"user_groups.org_id = '{ORG_ID}'" in sql
    # One correlated count, and exactly one join in the outer query.
    assert "(SELECT count(user_group_members.id)" in sql
    assert sql.count("JOIN user_group_members") == 1


@pytest.mark.asyncio
async def test_the_ungrouped_filter_means_no_group_at_all(
    session: CapturingSession,
) -> None:
    """"Who have I not covered?" — a different question from `exclude_group_id`.

    The subquery joins `user_groups` so it is scoped to this organization: a membership
    row pointing at another tenant's group must not make somebody look grouped here. It
    cannot happen through the API, and the filter that would silently hide a person from
    the one list that exists to find them is not the place to assume that.
    """
    await UserRepository(session).list_users(org_id=ORG_ID, ungrouped=True)

    joined = " || ".join(sql_of(session, i) for i in range(len(session.statements)))
    assert "NOT IN (SELECT user_group_members.user_id" in joined
    assert f"user_groups.org_id = '{ORG_ID}'" in joined
    # No group id anywhere: this is "no group", not "not in that one".
    assert str(GROUP_ID) not in joined


@pytest.mark.asyncio
async def test_the_member_expansion_reads_every_group_in_one_query(
    session: CapturingSession,
) -> None:
    """And carries ``User.org_id`` even though the groups were already scoped.

    That filter is the last thing between a membership row that should not exist and an
    enrollment in the wrong tenant.
    """
    await UserGroupRepository(session).memberships([GROUP_ID, OTHER_GROUP], ORG_ID)

    assert len(session.statements) == 1
    sql = sql_of(session)
    assert f"users.org_id = '{ORG_ID}'" in sql
    assert "user_group_members.group_id IN" in sql
    # The group id travels with the row: provenance is per person, so a flattened union
    # of user ids would not be enough to record which group put anybody there.
    assert "user_group_members.group_id, users.id, users.is_active" in sql
    # Deterministic order, so a retry of the same order enrols people the same way.
    assert "ORDER BY users.full_name, users.id" in sql


@pytest.mark.asyncio
async def test_expanding_no_groups_asks_the_database_nothing(
    session: CapturingSession,
) -> None:
    repo = UserGroupRepository(session)

    assert await repo.memberships([], ORG_ID) == []
    assert await repo.scoped_ids([], ORG_ID) == set()
    assert session.statements == []


@pytest.mark.asyncio
async def test_the_enrollment_batch_snapshot_filters_on_both_axes(
    session: CapturingSession,
) -> None:
    """One query for (these people) x (these courses), which is what bounds the loop."""
    await EnrollmentRepository(session).existing_pairs([COURSE], [ANA, BRUNO])

    assert len(session.statements) == 1
    sql = sql_of(session)
    assert "enrollments.course_id IN" in sql
    assert "enrollments.user_id IN" in sql


@pytest.mark.asyncio
async def test_an_empty_side_of_the_snapshot_asks_nothing(
    session: CapturingSession,
) -> None:
    """Assigning a folder with no published courses must not scan the whole table."""
    repo = EnrollmentRepository(session)

    assert await repo.existing_pairs([], [ANA]) == set()
    assert await repo.existing_pairs([COURSE], []) == set()
    assert await repo.list_with_courses([]) == []
    assert session.statements == []


@pytest.mark.asyncio
async def test_the_group_listing_is_one_page_with_a_total(
    session: CapturingSession,
) -> None:
    """The rail reads a window, so it needs both the window and how many there are.

    Two statements and no more: `count(*)` over the same filters, then the page. The
    total has to come from its own query — `len(page)` is the page size, which is the
    number that made the people list look complete at fifty.
    """
    await UserGroupRepository(session).list_with_counts(ORG_ID, offset=25, limit=25)

    assert len(session.statements) == 2
    count_sql, page_sql = (sql_of(session, i) for i in range(2))
    assert count_sql.startswith("SELECT count(*)")
    assert f"user_groups.org_id = '{ORG_ID}'" in count_sql
    assert "LIMIT" not in count_sql and "OFFSET" not in count_sql
    assert "LIMIT 25 OFFSET 25" in page_sql
    assert "ORDER BY lower(user_groups.name)" in page_sql


@pytest.mark.asyncio
async def test_the_group_search_is_a_case_insensitive_match_in_sql(
    session: CapturingSession,
) -> None:
    """Both statements carry it, or the total would count the unfiltered table.

    `ILIKE` and not `LIKE`: an admin typing "turno" must find "Turno de tarde". And it
    is in the query rather than in the browser, because the browser only holds one page
    — filtering there finds the matches that happened to land on it and calls the rest
    non-existent.
    """
    await UserGroupRepository(session).list_with_counts(ORG_ID, search="Turno")

    count_sql, page_sql = (sql_of(session, i) for i in range(2))
    for sql in (count_sql, page_sql):
        # The `%` are doubled because the compiler escapes them for the driver's own
        # parameter syntax; the pattern Postgres sees is `%Turno%`.
        assert "user_groups.name ILIKE '%%Turno%%'" in sql


@pytest.mark.asyncio
async def test_no_search_term_filters_on_nothing(session: CapturingSession) -> None:
    """An empty box is "show me everything", not a match against the empty string."""
    await UserGroupRepository(session).list_with_counts(ORG_ID, search="")

    joined = " || ".join(sql_of(session, i) for i in range(len(session.statements)))
    assert "ILIKE" not in joined


@pytest.mark.asyncio
async def test_the_paged_group_listing_counts_members_without_a_join(
    session: CapturingSession,
) -> None:
    """A `GROUP BY` over a join would break both halves of the pagination.

    `LIMIT` applies to the joined row set, so a group with twelve members would eat
    twelve slots of the page, and `SELECT count(*)` over the same join would report the
    number of *memberships* as the number of groups. The correlated subquery keeps the
    outer row set one row per group, which is what both numbers are about.
    """
    await UserGroupRepository(session).list_with_counts(ORG_ID)

    count_sql, page_sql = (sql_of(session, i) for i in range(2))
    assert "(SELECT count(user_group_members.id)" in page_sql
    assert "JOIN" not in page_sql
    assert "GROUP BY" not in page_sql
    assert "count(*)" in count_sql
    assert "user_group_members" not in count_sql


@pytest.mark.asyncio
async def test_the_person_exclusion_is_the_exact_complement(
    session: CapturingSession,
) -> None:
    """"Which groups is this person not in", for the picker on their own record.

    A `NOT IN` on the group id, carried by both statements: excluding the person's
    groups from the page they happened to fall on would leave every group on another
    page offered, and adding somebody to a group they are already in is an action that
    does nothing and reports success.
    """
    await UserGroupRepository(session).list_with_counts(ORG_ID, exclude_user_id=ANA)

    for index in range(2):
        sql = sql_of(session, index)
        assert "user_groups.id NOT IN (SELECT user_group_members.group_id" in sql
        assert f"user_group_members.user_id = '{ANA}'" in sql
    # A filter, not a second row source: joining the memberships would multiply the
    # groups and inflate the very total the pagination is computed from.
    assert "JOIN user_group_members" not in sql_of(session, 1)
