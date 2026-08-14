"""Provider-neutral, append-only learning-experience records.

The planning records deliberately stop before a concrete UI library.  A provider
only appears at ``ImplementationBinding``, which may pin an existing
``ActivityDefinition`` while that legacy-compatible store remains in service.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    REAL,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin


class ExperienceIntent(UUIDMixin, Base):
    """One immutable version of a provider-neutral pedagogical need."""

    __tablename__ = "experience_intents"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_experience_intents_version"),
        CheckConstraint("objective_version > 0", name="ck_experience_intents_objective_version"),
        CheckConstraint(
            "contract_digest ~ '^[0-9a-f]{64}$'",
            name="ck_experience_intents_digest",
        ),
        UniqueConstraint("org_id", "intent_key", "version", name="uq_experience_intent_version"),
        Index("idx_experience_intents_course", "course_id"),
        Index("idx_experience_intents_node", "node_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    intent_key: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    objective_id: Mapped[str] = mapped_column(Text, nullable=False)
    objective_version: Mapped[int] = mapped_column(Integer, nullable=False)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    learner_actions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    representations: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    required_evidence: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    feedback_policy: Mapped[str] = mapped_column(Text, nullable=False)
    constraints: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    contract_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ExperienceVariant(UUIDMixin, Base):
    """An immutable pedagogical realization of an intent, still provider-free."""

    __tablename__ = "experience_variants"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_experience_variants_version"),
        CheckConstraint(
            "variant_digest ~ '^[0-9a-f]{64}$'",
            name="ck_experience_variants_digest",
        ),
        UniqueConstraint("org_id", "variant_key", "version", name="uq_experience_variant_version"),
        Index("idx_experience_variants_intent", "intent_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    intent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experience_intents.id", ondelete="CASCADE"), nullable=False
    )
    variant_key: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    representations: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    learner_actions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    best_for: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    required_capabilities: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    selection_policy: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    variant_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ImplementationBinding(UUIDMixin, Base):
    """Immutable provider binding for a neutral variant.

    ``activity_definition_id`` is the additive compatibility seam.  New providers
    can use ``definition_ref`` directly; existing Didact activities can pin the
    exact server-owned ActivityDefinition row they already execute.
    """

    __tablename__ = "implementation_bindings"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_implementation_bindings_version"),
        CheckConstraint(
            "implementation_version > 0", name="ck_implementation_bindings_implementation_version"
        ),
        CheckConstraint(
            "definition_digest ~ '^[0-9a-f]{64}$' AND "
            "(assets_digest IS NULL OR assets_digest ~ '^[0-9a-f]{64}$')",
            name="ck_implementation_bindings_digests",
        ),
        UniqueConstraint(
            "org_id", "binding_key", "version", name="uq_implementation_binding_version"
        ),
        Index("idx_implementation_bindings_variant", "variant_id"),
        Index("idx_implementation_bindings_activity", "activity_definition_id"),
        Index("idx_implementation_bindings_implementation", "provider", "implementation_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experience_variants.id", ondelete="CASCADE"), nullable=False
    )
    binding_key: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_id: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_ref: Mapped[str] = mapped_column(Text, nullable=False)
    activity_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activity_definitions.id", ondelete="CASCADE"), nullable=True
    )
    definition_digest: Mapped[str] = mapped_column(Text, nullable=False)
    assets_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    catalog_version: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_adapter_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    renderer_version: Mapped[str] = mapped_column(Text, nullable=False)
    required_ports: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    is_fallback: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ExperienceAttempt(UUIDMixin, Base):
    """Server-confirmed immutable result of one experience submission."""

    __tablename__ = "experience_attempts"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('correct','incorrect','partial','unscored')",
            name="ck_experience_attempts_outcome",
        ),
        CheckConstraint(
            "request_digest ~ '^[0-9a-f]{64}$'",
            name="ck_experience_attempts_request_digest",
        ),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 1)", name="ck_experience_attempts_score"),
        CheckConstraint(
            "(outcome = 'unscored' AND score IS NULL AND passed IS NULL) OR "
            "(outcome <> 'unscored' AND score IS NOT NULL AND passed IS NOT NULL)",
            name="ck_experience_attempts_scoring_shape",
        ),
        CheckConstraint("hints_used >= 0", name="ck_experience_attempts_hints"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_experience_attempts_duration"),
        Index("idx_experience_attempts_user_node", "user_id", "node_id", text("created_at DESC")),
        Index("idx_experience_attempts_binding", "binding_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    intent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experience_intents.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experience_variants.id", ondelete="CASCADE"), nullable=False
    )
    binding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("implementation_bindings.id", ondelete="CASCADE"), nullable=False
    )
    activity_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activity_definitions.id", ondelete="CASCADE"), nullable=True
    )
    request_digest: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    passed: Mapped[bool | None] = mapped_column(nullable=True)
    hints_used: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class NormalizedEvidence(UUIDMixin, Base):
    """Provider-independent evidence emitted by one confirmed attempt."""

    __tablename__ = "normalized_evidence"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('correct','incorrect','partial','unscored')",
            name="ck_normalized_evidence_outcome",
        ),
        CheckConstraint(
            "evidence_digest ~ '^[0-9a-f]{64}$'",
            name="ck_normalized_evidence_digest",
        ),
        CheckConstraint("objective_version > 0", name="ck_normalized_evidence_objective_version"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 1)", name="ck_normalized_evidence_score"),
        CheckConstraint(
            "(outcome = 'unscored' AND score IS NULL) OR outcome <> 'unscored'",
            name="ck_normalized_evidence_scoring_shape",
        ),
        CheckConstraint("hints_used >= 0", name="ck_normalized_evidence_hints"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_normalized_evidence_duration"),
        UniqueConstraint("attempt_id", "evidence_key", name="uq_normalized_evidence_attempt_key"),
        Index("idx_normalized_evidence_objective", "objective_id", "objective_version"),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experience_attempts.id", ondelete="CASCADE"), nullable=False
    )
    evidence_key: Mapped[str] = mapped_column(Text, nullable=False)
    objective_id: Mapped[str] = mapped_column(Text, nullable=False)
    objective_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    error_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    hints_used: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    implementation_ref: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
