"""G18G user lifecycle: users.password_changed_at (tokens issued before a password change are rejected)

Revision ID: 0014_password_changed_at
Revises: 0013_tenant_scoped_email
Create Date: 2026-10-10
"""
import sqlalchemy as sa

from alembic import op

revision = "0014_password_changed_at"
down_revision = "0013_tenant_scoped_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
