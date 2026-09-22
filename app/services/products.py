"""Database-side inventory filtering, aggregation and bounded pagination; no stock writes."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CatalogEntry, InventoryTransaction, Product
from app.schemas.products import InventoryFilters, InventoryItem, InventoryPage
from app.services.reports import report_dates, utc_bounds


def cover_path(filename: str | None) -> Path | None:
    """Only existing raster files inside the configured local cover directory are served."""
    if not filename:
        return None
    root = settings.local_cover_dir.resolve()
    try:
        path = (root / filename).resolve()
        allowed = {".png", ".jpg", ".jpeg", ".webp"}
        if not path.is_relative_to(root) or path.suffix.lower() not in allowed:
            return None
        return path if path.is_file() else None
    except (OSError, ValueError):
        return None


async def list_inventory(session: AsyncSession, filters: InventoryFilters) -> InventoryPage:
    start, end = report_dates(filters.period, filters.start, filters.end)
    lower, upper = utc_bounds(start, end, ZoneInfo(settings.app_timezone))
    tx = InventoryTransaction
    in_period = and_(tx.created_at >= lower, tx.created_at < upper)
    stats = (
        select(
            tx.product_id,
            func.max(case((tx.operation_type == "SALE_OUT", tx.created_at))).label("last_sale"),
            func.sum(case((and_(in_period, tx.operation_type == "SALE_OUT"),
                           -tx.quantity_delta), else_=0)).label("sold"),
            func.sum(case((and_(in_period, tx.operation_type == "IN"),
                           tx.quantity_delta), else_=0)).label("inbound"),
        ).where(tx.operation_type.in_(["IN", "SALE_OUT"]))
        .group_by(tx.product_id).subquery()
    )
    sold = func.coalesce(stats.c.sold, 0)
    inbound = func.coalesce(stats.c.inbound, 0)
    stale_before = datetime.now(UTC) - timedelta(days=settings.stale_stock_days)
    states = {
        "low": and_(Product.active, Product.quantity > 0,
                    Product.quantity <= Product.low_stock_threshold),
        "sold_out": and_(Product.active, Product.quantity == 0),
        "overstock": and_(Product.active, Product.overstock_threshold.is_not(None),
                          Product.quantity >= Product.overstock_threshold),
        "stale": and_(Product.active, Product.quantity > 0,
                      func.coalesce(stats.c.last_sale, Product.created_at) <= stale_before),
        "pending": Product.manually_verified.is_(False),
    }
    states["normal"] = and_(Product.active, not_(or_(*states.values())))
    conditions = []
    q = filters.q.strip()
    if q:
        conditions.append(or_(*[
            column.icontains(q, autoescape=True) for column in (
                Product.game_name, Product.barcode, Product.platform, Product.region,
                Product.edition, CatalogEntry.aliases,
            )
        ]))
    for column, value in ((Product.platform, filters.platform), (Product.region, filters.region),
                          (Product.edition, filters.edition)):
        if value.strip():
            conditions.append(func.lower(column) == value.strip().lower())
    if filters.status != "all":
        conditions.append(states[filters.status])
    if filters.sales != "all":
        conditions.extend([Product.active, Product.quantity > 0])
        conditions.append(sold == 0 if filters.sales == "none" else sold.between(
            1, filters.low_sales_max,
        ))
    base = (
        select(Product, stats.c.last_sale, sold.label("sold"), inbound.label("inbound"),
               *[value.label(key) for key, value in states.items()])
        .outerjoin(stats, stats.c.product_id == Product.id)
        .outerjoin(CatalogEntry, CatalogEntry.id == Product.catalog_entry_id)
        .where(*conditions)
    )
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    sort_column = {
        "id": Product.id, "quantity": Product.quantity, "name": Product.normalized_name,
        "updated": Product.updated_at, "last_sale": stats.c.last_sale,
        "sales": sold, "inbound": inbound, "outbound": sold,
    }[filters.sort]
    ordering = sort_column.desc() if filters.order == "desc" else sort_column.asc()
    rows = (await session.execute(
        base.order_by(ordering.nulls_last(), Product.id.asc())
        .offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
    )).all()
    items = []
    for row in rows:
        product = row[0]
        item = InventoryItem.model_validate(product)
        item.last_sale_at = row.last_sale
        # SQLite test fixtures omit timezone information; production timestamptz does not.
        for field in ("last_sale_at", "updated_at"):
            value = getattr(item, field)
            if value is not None and value.tzinfo is None:
                setattr(item, field, value.replace(tzinfo=UTC))
        item.period_sales = int(row.sold)
        item.period_inbound = int(row.inbound)
        item.states = [key for key in states if row._mapping[key]]
        item.cover_url = f"/api/admin/products/{product.id}/cover" if cover_path(
            product.cover_filename,
        ) else None
        items.append(item)
    return InventoryPage(items=items, total=total, page=filters.page, page_size=filters.page_size,
                         start=start, end=end, timezone=settings.app_timezone)
