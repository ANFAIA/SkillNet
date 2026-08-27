"""Allow ``chat_sessions.agent_type = 'admin_agent'``: the tool-calling admin agent.

Additive: widens the existing check constraint, does not touch any row. The new
agent type is a separate thread from ``'admin'`` (the read-only org assistant) —
see ``src/services/admin_agent_service.py``.

Revision ID: 0020
Revises: 0019
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0020b"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CONSTRAINT = "agent_type IN ('tutor', 'admin')"
_NEW_CONSTRAINT = "agent_type IN ('tutor', 'admin', 'admin_agent')"


def upgrade() -> None:
    op.drop_constraint(
        "ck_chat_sessions_agent_type", "chat_sessions", type_="check"
    )
    op.create_check_constraint(
        "ck_chat_sessions_agent_type", "chat_sessions", _NEW_CONSTRAINT
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_chat_sessions_agent_type", "chat_sessions", type_="check"
    )
    op.create_check_constraint(
        "ck_chat_sessions_agent_type", "chat_sessions", _OLD_CONSTRAINT
    )
