"""Persistent stock alert transitions; existing inventory is preserved."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_stock_alerts"
down_revision: str | None = "0002_auth_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind IN ('LOW_STOCK', 'SOLD_OUT', 'OVERSTOCK', 'STALE_STOCK')",
            name="ck_stock_alert_kind",
        ),
    )
    op.create_index("ix_stock_alerts_product_id", "stock_alerts", ["product_id"])
    op.create_index(
        "uq_stock_alert_active",
        "stock_alerts",
        ["product_id", "kind"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
        sqlite_where=sa.text("closed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("stock_alerts")
