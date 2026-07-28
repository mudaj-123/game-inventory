"""目录、商品和不可变库存流水模型。"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    """可登录的店员或管理员。"""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('ADMIN', 'STAFF')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="STAFF")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CatalogEntry(Base):
    """从本地 CSV 导入的条码目录记录。"""

    __tablename__ = "catalog_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    game_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    region: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    edition: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str | None] = mapped_column(String(100))
    publisher: Mapped[str | None] = mapped_column(String(255))
    release_year: Mapped[int | None] = mapped_column(Integer)
    cover_filename: Mapped[str | None] = mapped_column(String(255))
    aliases: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(255))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source_file: Mapped[str] = mapped_column(String(500))
    source_row: Mapped[int] = mapped_column(Integer)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Product(Base):
    """一个可盘点的实体游戏 SKU。"""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_products_quantity_nonnegative"),
        CheckConstraint("low_stock_threshold >= 0", name="ck_products_low_stock_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    game_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    region: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    edition: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=1)
    overstock_threshold: Mapped[int | None] = mapped_column(Integer)
    cover_filename: Mapped[str | None] = mapped_column(String(255))
    identification_status: Mapped[str] = mapped_column(String(24), default="CONFIRMED")
    metadata_source: Mapped[str] = mapped_column(String(24), default="MANUAL")
    catalog_entry_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_entries.id"))
    manually_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    transactions: Mapped[list["InventoryTransaction"]] = relationship(back_populates="product")


class InventoryTransaction(Base):
    """库存变化流水；应用只追加，不更新或删除。"""

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        CheckConstraint("quantity_after >= 0", name="ck_tx_quantity_nonnegative"),
        UniqueConstraint("related_transaction_id", name="uq_tx_related_transaction_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_scan_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    barcode_snapshot: Mapped[str] = mapped_column(String(14))
    game_name_snapshot: Mapped[str] = mapped_column(String(255))
    platform_snapshot: Mapped[str] = mapped_column(String(16))
    operation_type: Mapped[str] = mapped_column(String(24))
    quantity_delta: Mapped[int] = mapped_column(Integer)
    quantity_before: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer)
    related_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_transactions.id")
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped[User | None] = relationship()
    device_id: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product: Mapped[Product] = relationship(back_populates="transactions")
