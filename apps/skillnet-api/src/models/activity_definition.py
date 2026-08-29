"""Server-owned definitions and per-learner state for rich Didact activities."""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class ActivityFamily(str, enum.Enum):
    ASSESSMENT = "assessment"
    ARTIFACT = "artifact"
    MEDIA = "media"
    SIMULATION = "simulation"
    EXECUTION = "execution"


class ActivityDefinition(UUIDMixin, TimestampMixin, Base):
    """A versioned activity contract. Secrets live only in ``private_definition``."""

    __tablename__ = "activity_definitions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_activity_definitions_version"),
        UniqueConstraint("org_id", "definition_key", "version", name="uq_activity_definition_version"),
        Index("idx_activity_definitions_node", "node_id"),
        Index("idx_activity_definitions_component", "component_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False)
    source_render_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("node_renders.id", ondelete="SET NULL"), nullable=True
    )
    source_knowledge_pack_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("node_knowledge_packs.id", ondelete="SET NULL"), nullable=True
    )
    definition_key: Mapped[str] = mapped_column(Text, nullable=False)
    component_id: Mapped[str] = mapped_column(Text, nullable=False)
    family: Mapped[ActivityFamily] = mapped_column(
        SAEnum(ActivityFamily, name="activity_family", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    public_definition: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    private_definition: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    required_ports: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)


class ActivityState(UUIDMixin, TimestampMixin, Base):
    """Opaque learner-owned draft/state, separate from the immutable definition.

    ``state`` is written by the client through ``PUT /activities/{id}/state`` and is never
    interpreted by the server. Anything the server has to *decide* with — how many times
    this learner missed, how much has been disclosed to them — belongs in
    ``learner_activity_states``, which has the same ``(activity, user)`` key and no
    client-writable column at all.
    """

    __tablename__ = "activity_states"
    __table_args__ = (
        UniqueConstraint("activity_id", "user_id", name="uq_activity_states_learner"),
        Index("idx_activity_states_user", "user_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activity_definitions.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
