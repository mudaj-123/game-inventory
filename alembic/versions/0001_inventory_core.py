"""create inventory core tables

Revision ID: 0001_inventory_core
Revises:
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_inventory_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("barcode", sa.String(14), nullable=False),
        sa.Column("game_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("edition", sa.String(100)),
        sa.Column("language", sa.String(100)),
        sa.Column("publisher", sa.String(255)),
        sa.Column("release_year", sa.Integer()),
        sa.Column("cover_filename", sa.String(255)),
        sa.Column("aliases", sa.Text()),
        sa.Column("source", sa.String(255)),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("source_file", sa.String(500), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("barcode"),
    )
    op.create_index("ix_catalog_entries_barcode", "catalog_entries", ["barcode"], unique=True)
    op.create_index("ix_catalog_entries_normalized_name", "catalog_entries", ["normalized_name"])
    op.create_index("ix_catalog_entries_platform", "catalog_entries", ["platform"])
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("barcode", sa.String(14), nullable=False),
        sa.Column("game_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("edition", sa.String(100)),
        sa.Column("language", sa.String(100)),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False),
        sa.Column("overstock_threshold", sa.Integer()),
        sa.Column("cover_filename", sa.String(255)),
        sa.Column("identification_status", sa.String(24), nullable=False),
        sa.Column("metadata_source", sa.String(24), nullable=False),
        sa.Column("catalog_entry_id", sa.Integer(), sa.ForeignKey("catalog_entries.id")),
        sa.Column("manually_verified", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("quantity >= 0", name="ck_products_quantity_nonnegative"),
        sa.CheckConstraint("low_stock_threshold >= 0", name="ck_products_low_stock_nonnegative"),
        sa.UniqueConstraint("barcode"),
    )
    op.create_index("ix_products_barcode", "products", ["barcode"], unique=True)
    op.create_index("ix_products_normalized_name", "products", ["normalized_name"])
    op.create_index("ix_products_platform", "products", ["platform"])
    op.create_table(
        "inventory_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_scan_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("barcode_snapshot", sa.String(14), nullable=False),
        sa.Column("game_name_snapshot", sa.String(255), nullable=False),
        sa.Column("platform_snapshot", sa.String(16), nullable=False),
        sa.Column("operation_type", sa.String(24), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("quantity_before", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column(
            "related_transaction_id", sa.Integer(), sa.ForeignKey("inventory_transactions.id")
        ),
        sa.Column("user_id", sa.Integer()),
        sa.Column("device_id", sa.String(255)),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("quantity_after >= 0", name="ck_tx_quantity_nonnegative"),
        sa.UniqueConstraint("client_scan_id"),
    )
    op.create_index(
        "ix_inventory_transactions_client_scan_id",
        "inventory_transactions",
        ["client_scan_id"],
        unique=True,
    )
    op.create_index(
        "ix_inventory_transactions_product_id", "inventory_transactions", ["product_id"]
    )


def downgrade() -> None:
    op.drop_table("inventory_transactions")
    op.drop_table("products")
    op.drop_table("catalog_entries")
