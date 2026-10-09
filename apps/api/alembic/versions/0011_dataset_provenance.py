"""G18 knowledge dataset provenance (authoritative-source governance, B-02)

Revision ID: 0011_dataset_provenance
Revises: 0010_copilot_meta
Create Date: 2026-10-09
"""
import sqlalchemy as sa

from alembic import op

revision = "0011_dataset_provenance"
down_revision = "0010_copilot_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_datasets", sa.Column("source_authority", sa.String(length=200), nullable=True))
    op.add_column("knowledge_datasets", sa.Column("source_document", sa.String(length=300), nullable=True))
    op.add_column("knowledge_datasets", sa.Column("source_reference", sa.String(length=500), nullable=True))
    op.add_column("knowledge_datasets", sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_datasets", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_datasets", sa.Column("verified_by", sa.Uuid(), nullable=True))
    op.add_column("knowledge_datasets", sa.Column("is_authoritative", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("knowledge_datasets", sa.Column("checksum", sa.String(length=64), nullable=True))
    op.add_column("knowledge_datasets", sa.Column("supersedes_id", sa.Uuid(), nullable=True))
    op.add_column("knowledge_datasets", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_knowledge_datasets_supersedes", "knowledge_datasets", "knowledge_datasets", ["supersedes_id"], ["id"])
    # Demo data can never be authoritative — enforced by the database, not only by the service layer.
    op.create_check_constraint("ck_knowledge_datasets_authoritative_not_demo", "knowledge_datasets", "NOT (is_authoritative AND is_demo)")


def downgrade() -> None:
    op.drop_constraint("ck_knowledge_datasets_authoritative_not_demo", "knowledge_datasets", type_="check")
    op.drop_constraint("fk_knowledge_datasets_supersedes", "knowledge_datasets", type_="foreignkey")
    for col in ("superseded_at", "supersedes_id", "checksum", "is_authoritative", "verified_by", "verified_at", "ingested_at",
                "source_reference", "source_document", "source_authority"):
        op.drop_column("knowledge_datasets", col)
