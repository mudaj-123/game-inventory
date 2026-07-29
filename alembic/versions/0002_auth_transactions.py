"""add users, ownership and safe reversal constraint

Revision ID: 0002_auth_transactions
Revises: 0001_inventory_core
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_auth_transactions"
down_revision: str | None = "0001_inventory_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("role IN ('ADMIN', 'STAFF')", name="ck_users_role"),
        sa.UniqueConstraint("username"))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    with op.batch_alter_table("inventory_transactions") as batch:
        batch.create_foreign_key("fk_transactions_user", "users", ["user_id"], ["id"])
        batch.create_unique_constraint("uq_tx_related_transaction_id", ["related_transaction_id"])
        batch.create_index("ix_inventory_transactions_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("inventory_transactions") as batch:
        batch.drop_index("ix_inventory_transactions_user_id")
        batch.drop_constraint("uq_tx_related_transaction_id", type_="unique")
        batch.drop_constraint("fk_transactions_user", type_="foreignkey")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
