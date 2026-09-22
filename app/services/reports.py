"""Read-only sales reports; reversals are booked on their own local date."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import settings
from app.models import InventoryTransaction
from app.schemas.reports import (
    DailySales,
    GameSales,
    Period,
    PlatformSales,
    SalesCount,
    SalesReport,
)


def report_dates(
    period: Period, start: date | None, end: date | None, today: date | None = None,
) -> tuple[date, date]:
    today = today or datetime.now(ZoneInfo(settings.app_timezone)).date()
    if period == "custom":
        if start is None or end is None:
            raise ValueError("自选日期必须提供开始和结束日期")
    else:
        if start is not None or end is not None:
            raise ValueError("开始和结束日期仅适用于自选日期")
        end = today
        if period == "week":
            start = today - timedelta(days=today.weekday())
        elif period == "month":
            start = today.replace(day=1)
        else:
            start = today - timedelta(days=6 if period == "7d" else 29)
    assert start is not None and end is not None
    if start > end or (end - start).days >= 366 or start.year < 2 or end.year > 9998:
        raise ValueError("日期范围须为顺序正确的 1～366 天")
    return start, end


def utc_bounds(start: date, end: date, timezone: ZoneInfo) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, timezone).astimezone(UTC),
        datetime.combine(end + timedelta(days=1), time.min, timezone).astimezone(UTC),
    )


async def sales_report(
    session: AsyncSession, start: date, end: date, page: int, page_size: int,
) -> SalesReport:
    timezone = ZoneInfo(settings.app_timezone)
    lower, upper = utc_bounds(start, end, timezone)
    tx = InventoryTransaction
    original = aliased(InventoryTransaction)
    # Select columns and stream in bounded batches, without retaining ORM transaction objects.
    statement = (
        select(tx.created_at, tx.product_id, tx.barcode_snapshot, tx.game_name_snapshot,
               tx.platform_snapshot, tx.operation_type, tx.quantity_delta)
        .outerjoin(original, original.id == tx.related_transaction_id)
        .where(tx.created_at >= lower, tx.created_at < upper,
               or_(tx.operation_type == "SALE_OUT",
                   and_(tx.operation_type == "REVERSAL", original.operation_type == "SALE_OUT")))
        .execution_options(yield_per=500)
    )
    daily = {
        start + timedelta(days=i): DailySales(date=start + timedelta(days=i))
        for i in range((end - start).days + 1)
    }
    platforms: dict[str, PlatformSales] = {}
    games: dict[tuple[int, str, str, str], GameSales] = {}
    totals = SalesCount()
    async for created, product_id, barcode, name, platform, operation, delta in (
        await session.stream(statement)
    ):
        local_day = created.replace(tzinfo=UTC) if created.tzinfo is None else created
        key = (product_id, barcode, name, platform)
        game = games.setdefault(key, GameSales(
            product_id=product_id, barcode=barcode, game_name=name, platform=platform,
        ))
        platform_count = platforms.setdefault(platform, PlatformSales(platform=platform))
        for count in (totals, daily[local_day.astimezone(timezone).date()], platform_count, game):
            if operation == "SALE_OUT":
                count.sold += -delta
            else:
                count.reversed += delta
            count.net = count.sold - count.reversed
    ordered = sorted(games.values(), key=lambda g: (-g.sold, g.barcode, g.game_name, g.platform))
    return SalesReport(
        start=start, end=end, timezone=settings.app_timezone, totals=totals,
        daily=list(daily.values()), platforms=sorted(platforms.values(), key=lambda p: p.platform),
        games=ordered[(page - 1) * page_size:page * page_size], game_total=len(ordered),
        page=page, page_size=page_size,
    )
