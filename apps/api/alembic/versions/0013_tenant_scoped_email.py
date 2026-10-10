"""G18F tenant-scoped user e-mail (tenant-aware login; closes the cross-tenant e-mail oracle)

Revision ID: 0013_tenant_scoped_email
Revises: 0012_ai_usage_events
Create Date: 2026-10-10
"""
import sqlalchemy as sa

from alembic import op

revision = "0013_tenant_scoped_email"
down_revision = "0012_ai_usage_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0002 created the constraint with PostgreSQL's default name for UniqueConstraint('email').
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_unique_constraint("uq_users_tenant_email", "users", ["tenant_id", "email"])
    op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    # Fail closed: a global unique e-mail cannot be restored while the same e-mail exists in two tenants.
    dup = op.get_bind().execute(sa.text("SELECT email FROM users GROUP BY email HAVING count(*) > 1 LIMIT 1")).scalar()
    if dup is not None:
        raise RuntimeError("downgrade refused: the same e-mail exists in more than one tenant; resolve the duplicates first")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_constraint("uq_users_tenant_email", "users", type_="unique")
    op.create_unique_constraint("users_email_key", "users", ["email"])
