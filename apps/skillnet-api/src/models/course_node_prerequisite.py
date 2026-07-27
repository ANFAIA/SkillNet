"""Edge of the course-node prerequisite DAG.

Acyclicity cannot be expressed as a CHECK; it is enforced by a topological sort
in ``CourseSchemaService.validate()`` before a schema may reach ``validated``.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class CourseNodePrerequisite(Base):
    __tablename__ = "course_node_prerequisites"
    __table_args__ = (
        PrimaryKeyConstraint(
            "node_id", "prerequisite_node_id", name="pk_course_node_prerequisites"
        ),
        CheckConstraint(
            "node_id <> prerequisite_node_id", name="ck_node_prereq_not_self"
        ),
        Index("idx_node_prereq_node", "node_id"),
    )

    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    prerequisite_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
