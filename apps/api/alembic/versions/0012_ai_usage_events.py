"""G18B persistent AI usage ledger (cost control survives restarts)

Revision ID: 0012_ai_usage_events
Revises: 0011_dataset_provenance
Create Date: 2026-10-09
"""
import sqlalchemy as sa

from alembic import op

revision = "0012_ai_usage_events"
down_revision = "0011_dataset_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_ai_usage_events_created_at", "ai_usage_events", ["created_at"])
    op.create_index("ix_ai_usage_events_correlation_id", "ai_usage_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_events_correlation_id", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_created_at", table_name="ai_usage_events")
    op.drop_table("ai_usage_events")
