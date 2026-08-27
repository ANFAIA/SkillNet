"""ADMIN_EMAIL that the API cannot read back must not become an owner account.

``users.email`` is a plain string column and the bootstrap writes to it directly, while
``UserRead.email`` is an ``EmailStr``. Without this check a reserved TLD produced an owner
who could sign in and then got a 500 from ``GET /users/me`` — shown on the login screen as
"Unknown error" while the network tab showed 204.
"""

from __future__ import annotations

from src.core.bootstrap import _usable_admin_email


def test_accepts_an_ordinary_address() -> None:
    assert _usable_admin_email("owner@example.com") == "owner@example.com"


def test_refuses_a_reserved_tld() -> None:
    # RFC 2606 reserves .test, and it is exactly what a local deployment reaches for.
    assert _usable_admin_email("owner@clean.test") is None


def test_refuses_something_that_is_not_an_address() -> None:
    assert _usable_admin_email("owner") is None
