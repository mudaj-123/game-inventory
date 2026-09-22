"""Validated sales report filters and response types."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Period = Literal["week", "month", "7d", "30d", "custom"]


class SalesCount(BaseModel):
    sold: int = 0
    reversed: int = 0
    net: int = 0


class DailySales(SalesCount):
    date: date


class PlatformSales(SalesCount):
    platform: str


class GameSales(SalesCount):
    product_id: int
    barcode: str
    game_name: str
    platform: str


class SalesReport(BaseModel):
    start: date
    end: date
    timezone: str
    totals: SalesCount
    daily: list[DailySales]
    platforms: list[PlatformSales]
    games: list[GameSales]
    game_total: int
    page: int
    page_size: int = Field(default=50)
