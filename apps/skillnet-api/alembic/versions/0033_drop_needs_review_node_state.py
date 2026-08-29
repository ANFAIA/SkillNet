"""node_state: drop `needs_review`, the label that stood for the escape hatch

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-29

``needs_review`` had exactly one producer: rule 8 of §7.3
(``mastery_service.transition_on_answer``), the fourth failure of an item once the three
hints of §7.4 were spent. **That rule survives this migration untouched** — it is the only
thing that closes an item the learner is not going to get right, and without it the answer
falls through to rule 0 and the learner re-attempts the same item for ever. What the rule
returns now is ``learning`` with ``show_worked_solution=True``: the worked solution is the
escape hatch, and it was always the flag doing the work. The state only added a label that
took the node out of the normal flow, plus a "para practicar" queue and a re-probe gate
built on top of a label.

``learning`` and not ``mastered`` for the surviving rows, for the same reason the rule
returns ``learning``: failing four times and being shown the answer demonstrates nothing,
and ``mastered`` is what a certificate reads.

**The backfill is not optional.** The Python enum loses the member in the same commit, so
``NodeState("needs_review")`` raises ``ValueError`` on the first read of any surviving row
— and rows can exist, because the state was reachable through ``POST /nodes/{id}/hint``.
The ``UPDATE`` therefore runs before the type is narrowed, in the same transaction.

The type is rebuilt rather than edited because PostgreSQL has no ``ALTER TYPE ... DROP
VALUE``. Shaped as: create the narrow type beside the old one, retype the column through
``text``, drop the old type, rename. No ``autocommit_block``: ``alembic/env.py`` already
wraps the whole run in one transaction, and every step of this sequence is transactional
in PostgreSQL — the enum creation included — so a failure half way leaves the type and the
column as they were.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPE = "node_state"
_TMP = "node_state_new"
_WITHOUT_NEEDS_REVIEW = ("not_started", "probing", "learning", "mastered")
_WITH_NEEDS_REVIEW = (*_WITHOUT_NEEDS_REVIEW, "needs_review")


def _values(labels: tuple[str, ...]) -> str:
    return ", ".join(f"'{label}'" for label in labels)


def _retype(labels: tuple[str, ...]) -> None:
    """Swap ``learner_node_states.state`` onto a freshly built ``node_state``.

    The ``server_default`` has to be dropped and put back: it is stored parsed against the
    old type's OID, so ``ALTER COLUMN ... TYPE`` refuses to leave it standing. It is
    restored after the rename, which is why the cast in it names the final type.
    """
    op.execute(f"CREATE TYPE {_TMP} AS ENUM ({_values(labels)})")
    op.execute("ALTER TABLE learner_node_states ALTER COLUMN state DROP DEFAULT")
    op.execute(
        f"ALTER TABLE learner_node_states ALTER COLUMN state "
        f"TYPE {_TMP} USING state::text::{_TMP}"
    )
    op.execute(f"DROP TYPE {_TYPE}")
    op.execute(f"ALTER TYPE {_TMP} RENAME TO {_TYPE}")
    op.execute(
        f"ALTER TABLE learner_node_states ALTER COLUMN state "
        f"SET DEFAULT 'not_started'::{_TYPE}"
    )


def upgrade() -> None:
    # First, and inside the same transaction as the narrowing: a row left behind here is a
    # `ValueError` on every read of that learner's state, not a stale value.
    op.execute(
        "UPDATE learner_node_states SET state = 'learning' WHERE state = 'needs_review'"
    )
    _retype(_WITHOUT_NEEDS_REVIEW)


def downgrade() -> None:
    """Puts the value back in the type. **It cannot put it back in the rows.**

    Which rows were ``needs_review`` is not recorded anywhere — the upgrade rewrote them to
    ``learning`` and nothing kept the old value — so downgrading gives back a five-valued
    enum in which nothing is ``needs_review``. That is the honest outcome, not a bug to fix
    here: reconstructing it would mean guessing from ``node_attempts``, and a guess written
    into a mastery column is worse than a state nobody is in.
    """
    _retype(_WITH_NEEDS_REVIEW)
