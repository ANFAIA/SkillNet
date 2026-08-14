"""Add provider-neutral, append-only learning experience contracts.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
EMPTY_JSON = sa.text("'{}'::jsonb")
EMPTY_TEXT_ARRAY = sa.text("'{}'")
NOW = sa.text("now()")


def _id() -> sa.Column:
    return sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _timestamps() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW)


def upgrade() -> None:
    op.add_column("node_attempts", sa.Column("request_digest", sa.Text(), nullable=True))

    op.create_table(
        "experience_intents",
        _id(),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", UUID, sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", UUID, sa.ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intent_key", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("objective_id", sa.Text(), nullable=False),
        sa.Column("objective_version", sa.Integer(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("learner_actions", postgresql.ARRAY(sa.Text()), nullable=False, server_default=EMPTY_TEXT_ARRAY),
        sa.Column("representations", postgresql.ARRAY(sa.Text()), nullable=False, server_default=EMPTY_TEXT_ARRAY),
        sa.Column("required_evidence", postgresql.ARRAY(sa.Text()), nullable=False, server_default=EMPTY_TEXT_ARRAY),
        sa.Column("feedback_policy", sa.Text(), nullable=False),
        sa.Column("constraints", postgresql.JSONB(), nullable=False, server_default=EMPTY_JSON),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=EMPTY_JSON),
        sa.Column("contract_digest", sa.Text(), nullable=False),
        _timestamps(),
        sa.CheckConstraint("version > 0", name="ck_experience_intents_version"),
        sa.CheckConstraint("objective_version > 0", name="ck_experience_intents_objective_version"),
        sa.CheckConstraint(
            "contract_digest ~ '^[0-9a-f]{64}$'", name="ck_experience_intents_digest"
        ),
        sa.UniqueConstraint("org_id", "intent_key", "version", name="uq_experience_intent_version"),
    )
    op.create_index("idx_experience_intents_course", "experience_intents", ["course_id"])
    op.create_index("idx_experience_intents_node", "experience_intents", ["node_id"])

    op.create_table(
        "experience_variants",
        _id(),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intent_id", UUID, sa.ForeignKey("experience_intents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_key", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("representations", postgresql.ARRAY(sa.Text()), nullable=False, server_default=EMPTY_TEXT_ARRAY),
        sa.Column("learner_actions", postgresql.ARRAY(sa.Text()), nullable=False, server_default=EMPTY_TEXT_ARRAY),
        sa.Column("best_for", postgresql.ARRAY(sa.Text()), nullable=False, server_default=EMPTY_TEXT_ARRAY),
        sa.Column("required_capabilities", postgresql.JSONB(), nullable=False, server_default=EMPTY_JSON),
        sa.Column("selection_policy", postgresql.JSONB(), nullable=False, server_default=EMPTY_JSON),
        sa.Column("variant_digest", sa.Text(), nullable=False),
        _timestamps(),
        sa.CheckConstraint("version > 0", name="ck_experience_variants_version"),
        sa.CheckConstraint(
            "variant_digest ~ '^[0-9a-f]{64}$'", name="ck_experience_variants_digest"
        ),
        sa.UniqueConstraint("org_id", "variant_key", "version", name="uq_experience_variant_version"),
    )
    op.create_index("idx_experience_variants_intent", "experience_variants", ["intent_id"])

    op.create_table(
        "implementation_bindings",
        _id(),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", UUID, sa.ForeignKey("experience_variants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("binding_key", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("implementation_id", sa.Text(), nullable=False),
        sa.Column("implementation_version", sa.Integer(), nullable=False),
        sa.Column("definition_ref", sa.Text(), nullable=False),
        sa.Column(
            "activity_definition_id",
            UUID,
            sa.ForeignKey("activity_definitions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("definition_digest", sa.Text(), nullable=False),
        sa.Column("assets_digest", sa.Text(), nullable=True),
        sa.Column("catalog_version", sa.Text(), nullable=False),
        sa.Column("evidence_adapter_version", sa.Text(), nullable=True),
        sa.Column("renderer_version", sa.Text(), nullable=False),
        sa.Column("required_ports", postgresql.ARRAY(sa.Text()), nullable=False, server_default=EMPTY_TEXT_ARRAY),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _timestamps(),
        sa.CheckConstraint("version > 0", name="ck_implementation_bindings_version"),
        sa.CheckConstraint(
            "implementation_version > 0", name="ck_implementation_bindings_implementation_version"
        ),
        sa.CheckConstraint(
            "definition_digest ~ '^[0-9a-f]{64}$' AND "
            "(assets_digest IS NULL OR assets_digest ~ '^[0-9a-f]{64}$')",
            name="ck_implementation_bindings_digests",
        ),
        sa.UniqueConstraint("org_id", "binding_key", "version", name="uq_implementation_binding_version"),
    )
    op.create_index("idx_implementation_bindings_variant", "implementation_bindings", ["variant_id"])
    op.create_index(
        "idx_implementation_bindings_activity", "implementation_bindings", ["activity_definition_id"]
    )
    op.create_index(
        "idx_implementation_bindings_implementation",
        "implementation_bindings",
        ["provider", "implementation_id"],
    )

    op.create_table(
        "experience_attempts",
        _id(),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", UUID, sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", UUID, sa.ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intent_id", UUID, sa.ForeignKey("experience_intents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", UUID, sa.ForeignKey("experience_variants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("binding_id", UUID, sa.ForeignKey("implementation_bindings.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "activity_definition_id",
            UUID,
            sa.ForeignKey("activity_definitions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("request_digest", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("hints_used", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default=EMPTY_JSON),
        _timestamps(),
        sa.CheckConstraint(
            "outcome IN ('correct','incorrect','partial','unscored')",
            name="ck_experience_attempts_outcome",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^[0-9a-f]{64}$'",
            name="ck_experience_attempts_request_digest",
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)", name="ck_experience_attempts_score"
        ),
        sa.CheckConstraint(
            "(outcome = 'unscored' AND score IS NULL AND passed IS NULL) OR "
            "(outcome <> 'unscored' AND score IS NOT NULL AND passed IS NOT NULL)",
            name="ck_experience_attempts_scoring_shape",
        ),
        sa.CheckConstraint("hints_used >= 0", name="ck_experience_attempts_hints"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_experience_attempts_duration"
        ),
    )
    op.create_index(
        "idx_experience_attempts_user_node",
        "experience_attempts",
        ["user_id", "node_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_experience_attempts_binding", "experience_attempts", ["binding_id"])

    op.create_table(
        "normalized_evidence",
        _id(),
        sa.Column(
            "attempt_id", UUID, sa.ForeignKey("experience_attempts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("evidence_key", sa.Text(), nullable=False),
        sa.Column("objective_id", sa.Text(), nullable=False),
        sa.Column("objective_version", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.Text(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("error_kind", sa.Text(), nullable=True),
        sa.Column("hints_used", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("implementation_ref", sa.Text(), nullable=False),
        sa.Column("evidence_digest", sa.Text(), nullable=False),
        _timestamps(),
        sa.CheckConstraint(
            "outcome IN ('correct','incorrect','partial','unscored')",
            name="ck_normalized_evidence_outcome",
        ),
        sa.CheckConstraint(
            "evidence_digest ~ '^[0-9a-f]{64}$'",
            name="ck_normalized_evidence_digest",
        ),
        sa.CheckConstraint(
            "objective_version > 0", name="ck_normalized_evidence_objective_version"
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)", name="ck_normalized_evidence_score"
        ),
        sa.CheckConstraint(
            "(outcome = 'unscored' AND score IS NULL) OR outcome <> 'unscored'",
            name="ck_normalized_evidence_scoring_shape",
        ),
        sa.CheckConstraint("hints_used >= 0", name="ck_normalized_evidence_hints"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_normalized_evidence_duration"
        ),
        sa.UniqueConstraint("attempt_id", "evidence_key", name="uq_normalized_evidence_attempt_key"),
    )
    op.create_index(
        "idx_normalized_evidence_objective",
        "normalized_evidence",
        ["objective_id", "objective_version"],
    )

    # Plan/binding/evidence records are versioned facts, not mutable state. Cascaded
    # deletes remain possible for tenancy erasure, while ordinary UPDATE is rejected.
    op.execute(
        """
        CREATE FUNCTION reject_learning_experience_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only; insert a new version instead', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "experience_intents",
        "experience_variants",
        "implementation_bindings",
        "experience_attempts",
        "normalized_evidence",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_learning_experience_update()"
        )


def downgrade() -> None:
    op.drop_table("normalized_evidence")
    op.drop_table("experience_attempts")
    op.drop_table("implementation_bindings")
    op.drop_table("experience_variants")
    op.drop_table("experience_intents")
    op.execute("DROP FUNCTION reject_learning_experience_update()")
    op.drop_column("node_attempts", "request_digest")
