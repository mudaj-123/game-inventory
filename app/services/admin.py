"""有原因、有幂等键、只追加流水的管理员库存调整。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.models import InventoryTransaction, Product
from app.schemas.admin import AdjustmentRequest
from app.services.alerts import refresh_product_alerts
from app.services.inventory import InventoryConflictError


async def adjust_stock(
    session: AsyncSession, product_id: int, request: AdjustmentRequest, user: CurrentUser
) -> dict[str, object]:
    async with session.begin():
        product = await session.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        if product is None:
            raise InventoryConflictError("商品不存在")
        existing = await session.scalar(
            select(InventoryTransaction).where(
                InventoryTransaction.client_scan_id == str(request.client_scan_id)
            )
        )
        if existing:
            if (
                existing.product_id,
                existing.user_id,
                existing.quantity_delta,
                existing.note,
                existing.operation_type,
            ) != (product_id, user.id, request.quantity_delta, request.reason, "ADJUST"):
                raise InventoryConflictError("请求编号已被其他操作使用")
            return {
                "transaction_id": existing.id,
                "quantity_after": existing.quantity_after,
                "idempotent_replay": True,
            }
        before = product.quantity
        if before + request.quantity_delta < 0:
            raise InventoryConflictError("调整会导致负库存")
        product.quantity += request.quantity_delta
        tx = InventoryTransaction(
            client_scan_id=str(request.client_scan_id),
            product_id=product.id,
            barcode_snapshot=product.barcode,
            game_name_snapshot=product.game_name,
            platform_snapshot=product.platform,
            operation_type="ADJUST",
            quantity_delta=request.quantity_delta,
            quantity_before=before,
            quantity_after=product.quantity,
            user_id=user.id,
            note=request.reason,
        )
        session.add(tx)
        await session.flush()
        alerts = await refresh_product_alerts(session, product)
        return {
            "transaction_id": tx.id,
            "quantity_after": product.quantity,
            "idempotent_replay": False,
            "alerts": alerts,
        }
