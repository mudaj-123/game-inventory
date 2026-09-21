"""在商品行锁保护下记录预警跨越；不重复创建活动预警。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import InventoryTransaction, Product, StockAlert


async def refresh_product_alerts(session: AsyncSession, product: Product) -> list[str]:
    # Caller holds the product lock (UPDATE or SELECT FOR UPDATE) until commit.
    now = datetime.now(UTC)
    last_sale = await session.scalar(
        select(func.max(InventoryTransaction.created_at)).where(
            InventoryTransaction.product_id == product.id,
            InventoryTransaction.operation_type == "SALE_OUT",
        )
    )
    last_activity = last_sale or product.created_at
    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=UTC)
    desired = set()
    if product.active:
        if product.quantity == 0:
            desired.add("SOLD_OUT")
        elif product.quantity <= product.low_stock_threshold:
            desired.add("LOW_STOCK")
        if (
            product.overstock_threshold is not None
            and product.quantity > product.overstock_threshold
        ):
            desired.add("OVERSTOCK")
        if product.quantity > 0 and last_activity <= now - timedelta(
            days=settings.stale_stock_days
        ):
            desired.add("STALE_STOCK")
    active = (
        await session.scalars(
            select(StockAlert).where(
                StockAlert.product_id == product.id, StockAlert.closed_at.is_(None)
            )
        )
    ).all()
    for alert in active:
        if alert.kind not in desired:
            alert.closed_at = now
    existing = {alert.kind for alert in active}
    for kind in desired - existing:
        session.add(StockAlert(product_id=product.id, kind=kind, opened_at=now))
    await session.flush()
    return sorted(desired)


async def refresh_all_alerts(session: AsyncSession) -> None:
    # Stable lock order avoids deadlocks between concurrent dashboard refreshes.
    products = (await session.scalars(select(Product).order_by(Product.id).with_for_update())).all()
    for product in products:
        await refresh_product_alerts(session, product)
