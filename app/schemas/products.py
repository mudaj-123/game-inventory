"""Validated inventory search options and paginated results."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.reports import Period


class InventoryFilters(BaseModel):
    q: str = Field(default="", max_length=255)
    platform: str = Field(default="", max_length=16)
    region: str = Field(default="", max_length=16)
    edition: str = Field(default="", max_length=100)
    status: Literal[
        "all", "normal", "low", "sold_out", "overstock", "stale", "pending",
    ] = "all"
    sales: Literal["all", "none", "low"] = "all"
    low_sales_max: int = Field(default=3, ge=1, le=1000000)
    period: Period = "30d"
    start: date | None = None
    end: date | None = None
    sort: Literal[
        "id", "quantity", "name", "updated", "last_sale", "sales", "inbound", "outbound",
    ] = "id"
    order: Literal["asc", "desc"] = "asc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class InventoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    barcode: str
    game_name: str
    platform: str
    region: str
    edition: str | None
    quantity: int
    identification_status: str
    manually_verified: bool
    low_stock_threshold: int
    overstock_threshold: int | None
    active: bool
    updated_at: datetime
    last_sale_at: datetime | None = None
    period_sales: int = 0
    period_inbound: int = 0
    states: list[str] = Field(default_factory=list)
    cover_url: str | None = None


class InventoryPage(BaseModel):
    items: list[InventoryItem]
    total: int
    page: int
    page_size: int
    start: date
    end: date
    timezone: str
