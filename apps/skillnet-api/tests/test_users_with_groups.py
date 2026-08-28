"""``GET /users?with_groups=true`` — the group column's data, and its price.

The people table shows which group each person is in. The membership travels on the row
rather than from a second endpoint, because two reads of the same fact can disagree about
it: a row fetched now and its groups fetched a moment later describe two different
moments, and the screen would present them as one.

What these pin is the other half of that decision — that it is **opt-in**, and that
asking for it costs one bounded read and not one per row. The list is also what the
people pickers, the assignment dialogs and the one-row count probes call, and none of
them render a group; a default-on flag would make every one of them pay for a join they
throw away.

No database: the service is a fake that records what the route asked it for.
"""

import uuid
from types import SimpleNamespace

import pytest

from src.routes import users as users_route

ORG = uuid.UUID("22222222-2222-2222-2222-222222222222")
ANA = uuid.UUID("33333333-3333-3333-3333-333333333333")
BRUNO = uuid.UUID("44444444-4444-4444-4444-444444444444")
TARDE = uuid.UUID("55555555-5555-5555-5555-555555555555")
NORTE = uuid.UUID("66666666-6666-6666-6666-666666666666")


def person(user_id: uuid.UUID, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email=f"{name.lower()}@test.dev",
        is_active=True,
        is_superuser=False,
        is_verified=False,
        full_name=name,
        role="employee",
        learning_profile="standard",
        org_id=ORG,
        accessibility={},
        hired_at=None,
    )


class FakeService:
    """Records the calls the route makes, and hands back a fixed page."""

    def __init__(self, rows, groups=None) -> None:
        self.rows = rows
        self.groups = groups or {}
        self.group_calls: list[tuple[list[uuid.UUID], uuid.UUID]] = []

    async def list_users(self, **_kwargs):
        return self.rows, len(self.rows)

    async def groups_of_users(self, user_ids, org_id):
        self.group_calls.append((list(user_ids), org_id))
        return self.groups


@pytest.fixture
def admin() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), org_id=ORG)


def install(monkeypatch, service: FakeService) -> None:
    monkeypatch.setattr(users_route, "_service", lambda _db: service)


@pytest.mark.asyncio
async def test_groups_are_not_read_unless_asked_for(monkeypatch, admin) -> None:
    service = FakeService([person(ANA, "Ana")])
    install(monkeypatch, service)

    page = await users_route.list_users(admin=admin, db=None, _org=None)

    # Not one query, not a cheap one — none at all.
    assert service.group_calls == []
    # `None`, not `[]`: "nobody asked" and "in no group" are different answers, and a
    # client that sees `[]` here would render an em dash for somebody who has a group.
    assert page.items[0].groups is None


@pytest.mark.asyncio
async def test_asking_for_them_costs_one_read_for_the_whole_page(
    monkeypatch, admin
) -> None:
    service = FakeService(
        [person(ANA, "Ana"), person(BRUNO, "Bruno")],
        groups={
            ANA: [
                SimpleNamespace(id=TARDE, name="Turno de tarde"),
                SimpleNamespace(id=NORTE, name="Delegación Norte"),
            ]
        },
    )
    install(monkeypatch, service)

    page = await users_route.list_users(
        admin=admin, db=None, _org=None, with_groups=True
    )

    # One call, carrying every id on the page. Two calls here would be the N+1 the
    # column exists to avoid, and it would still render correctly.
    assert len(service.group_calls) == 1
    asked_for, org = service.group_calls[0]
    assert asked_for == [ANA, BRUNO]
    assert org == ORG

    ana, bruno = page.items
    assert [g.name for g in ana.groups] == ["Turno de tarde", "Delegación Norte"]
    # Bruno is in none, and that is an empty list rather than `None` — he was asked
    # about and the answer is "no group", which the row draws as a dash.
    assert bruno.groups == []


@pytest.mark.asyncio
async def test_the_row_carries_only_what_names_a_group(monkeypatch, admin) -> None:
    """Not ``member_count``: it is a correlated subquery per group, and a page of
    twenty-five people would pay for it twenty-five times to render a name."""
    service = FakeService(
        [person(ANA, "Ana")],
        groups={ANA: [SimpleNamespace(id=TARDE, name="Turno de tarde")]},
    )
    install(monkeypatch, service)

    page = await users_route.list_users(
        admin=admin, db=None, _org=None, with_groups=True
    )

    assert set(page.items[0].groups[0].model_dump()) == {"id", "name"}
