"""Declarative base and shared mixins."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def naive_utc_now() -> datetime:
    """The value ``updated_at`` gets on every UPDATE. Naive, and on purpose.

    ``Mapped[datetime]`` with no explicit type resolves to ``DateTime()`` — *without*
    timezone — and SQLAlchemy's asyncpg dialect renders a bind cast from the declared
    type (``AsyncpgDateTime.render_bind_cast``), so the parameter reaches the driver as
    ``timestamp without time zone``. asyncpg refuses an aware value for that outright
    (``DataError: can't subtract offset-naive and offset-aware datetimes`` — the failure
    that migration 0006 exists to fix), and the physical columns behind this mixin are
    genuinely mixed: ``timestamptz`` in 0001 but plain ``timestamp`` in 0003, 0013
    (``course_folders``!) and 0014. So aware is not an option here.

    Naive **UTC** rather than naive local time because that is exactly what the
    ``now()`` server default has been writing: Postgres stores it in the server's
    ``TimeZone`` and this deployment runs ``Etc/UTC`` (stated in 0006, and the same
    reasoning that let that migration use a plain ``AT TIME ZONE 'UTC'``). It also
    matches ``api_keys.last_used_at``, the one other timestamp this codebase writes from
    Python into a naive column. Aligning the column types is a migration, and a separate
    decision.

    Known and bounded consequence: on a ``timestamptz`` table the row is stored
    correctly (Postgres casts the parameter at ``TimeZone`` = UTC), but the in-memory
    attribute stays naive until something re-reads it, so the *response to that one
    write* serializes ``updated_at`` without the ``+00:00`` a ``GET`` would carry. The
    real fix is one migration unifying every timestamp to ``timestamptz`` plus
    ``DateTime(timezone=True)`` on this mixin, after which this function returns an aware
    value and the difference disappears.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def aware_utc_now() -> datetime:
    """The ``onupdate`` value for a column declared ``DateTime(timezone=True)``.

    Same reason as :func:`naive_utc_now` — a Python callable, never ``text("now()")``,
    so the column stays out of the UPDATE's ``postfetch`` set and the attribute is not
    expired. The difference is only the tzinfo: a ``timestamptz`` column declared with
    ``DateTime(timezone=True)`` takes an aware value, and asyncpg wants it aware.
    """
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    #: ``onupdate`` **must** be a Python callable and must never go back to
    #: ``text("now()")``. A SQL expression is computed by the database, so SQLAlchemy
    #: cannot know the new value: it puts the column in the UPDATE's ``postfetch`` set
    #: (``eager_defaults`` is "auto", which for an UPDATE means no RETURNING) and then
    #: expires the attribute. With ``expire_on_commit=False`` in ``deps/db.py`` that
    #: expiration is *not* undone by the commit, so the first synchronous read of
    #: ``course.updated_at`` after ``await db.commit()`` — every route projector does
    #: one — triggers an implicit refresh outside SQLAlchemy's greenlet and raises
    #: ``MissingGreenlet``. That surfaced as a 500 on the *first* ``PUT`` of a course or
    #: a folder and a silent success on the retry (no change, no UPDATE, nothing to
    #: postfetch), which is what made it look like a frontend problem. A callable is
    #: evaluated in Python, so the value is known, no postfetch entry is created and the
    #: attribute stays loaded. See :func:`naive_utc_now` for why it is naive.
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
        onupdate=naive_utc_now,
    )
