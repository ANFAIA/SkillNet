"""Read auditing for shared renders.

``node_renders`` has no ``user_id``, so "who saw which spec" lives here. Without
this table the audit promise of §2.1 would be false on every cache hit.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, PrimaryKeyConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class NodeRenderView(Base):
    __tablename__ = "node_render_views"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "render_id", name="pk_node_render_views"),
        Index(
            "idx_node_render_views_user",
            "user_id",
            "node_id",
            text("first_seen_at DESC"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    render_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("node_renders.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
