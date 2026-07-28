"""流水查询与原子撤销服务。"""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import InventoryTransaction, Product, User
from app.schemas.transactions import ReverseResponse, TransactionItem, TransactionPage


class TransactionError(RuntimeError):
    pass


def _today_bounds() -> tuple[datetime, datetime]:
    timezone = ZoneInfo(settings.app_timezone)
    start = datetime.now(timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


async def list_transactions(session: AsyncSession, user: User, page: int, page_size: int,
                            operation_type: str | None) -> TransactionPage:
    start, end = _today_bounds()
    filters = [InventoryTransaction.created_at >= start, InventoryTransaction.created_at < end]
    if user.role != "ADMIN":
        filters.append(InventoryTransaction.user_id == user.id)
    if operation_type:
        filters.append(InventoryTransaction.operation_type == operation_type)
    # Use an alias because the correlated self-reference above would otherwise collapse.
    from sqlalchemy.orm import aliased
    reversal = aliased(InventoryTransaction)
    reversed_col = exists(
        select(reversal.id).where(reversal.related_transaction_id == InventoryTransaction.id)
    )
    count = await session.scalar(
        select(func.count()).select_from(InventoryTransaction).where(*filters)
    )
    total = int(count or 0)
    rows = (await session.execute(
        select(InventoryTransaction, User.username, reversed_col.label("reversed"))
        .join(User, User.id == InventoryTransaction.user_id)
        .where(*filters)
        .order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all()
    items = [TransactionItem(transaction_id=tx.id, game_name=tx.game_name_snapshot,
        barcode=tx.barcode_snapshot, platform=tx.platform_snapshot,
        operation_type=tx.operation_type, quantity_delta=tx.quantity_delta,
        quantity_before=tx.quantity_before, quantity_after=tx.quantity_after,
        username=username, created_at=tx.created_at, reversed=bool(was_reversed))
        for tx, username, was_reversed in rows]
    return TransactionPage(items=items, page=page, page_size=page_size, total=total)


async def _latest_reversible_id(session: AsyncSession, user: User) -> int | None:
    reversal = InventoryTransaction.__table__.alias("reversal")
    return await session.scalar(select(InventoryTransaction.id).where(
        InventoryTransaction.user_id == user.id,
        InventoryTransaction.operation_type.in_(["IN", "SALE_OUT"]),
        ~exists(
            select(reversal.c.id).where(
                reversal.c.related_transaction_id == InventoryTransaction.id
            )
        ),
    ).order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc()).limit(1))


async def reverse_transaction(
    session: AsyncSession, user: User, transaction_id: int | None
) -> ReverseResponse:
    try:
        async with session.begin():
            target_id = transaction_id
            if target_id is None:
                target_id = await _latest_reversible_id(session, user)
            if target_id is None:
                raise TransactionError("没有可撤销的流水")
            original = await session.scalar(select(InventoryTransaction).where(
                InventoryTransaction.id == target_id).with_for_update())
            if original is None:
                raise TransactionError("流水不存在")
            if original.operation_type == "REVERSAL":
                raise TransactionError("撤销流水不能再次撤销")
            if user.role != "ADMIN":
                latest = await _latest_reversible_id(session, user)
                if original.user_id != user.id:
                    raise TransactionError("只能撤销自己的流水")
                if latest != original.id:
                    raise TransactionError("只能撤销最近一条可撤销流水")
                created = original.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                if datetime.now(UTC) - created > timedelta(minutes=settings.undo_window_minutes):
                    raise TransactionError("流水已超过撤销时间窗口")
            already = await session.scalar(select(InventoryTransaction.id).where(
                InventoryTransaction.related_transaction_id == original.id))
            if already is not None:
                raise TransactionError("该流水已被撤销")
            delta = -original.quantity_delta
            statement = update(Product).where(Product.id == original.product_id)
            if delta < 0:
                statement = statement.where(Product.quantity >= -delta)
            quantity_after = await session.scalar(statement.values(
                quantity=Product.quantity + delta).returning(Product.quantity))
            if quantity_after is None:
                raise TransactionError("库存不足，撤销会导致负库存")
            reversal_tx = InventoryTransaction(client_scan_id=str(uuid.uuid4()),
                product_id=original.product_id, barcode_snapshot=original.barcode_snapshot,
                game_name_snapshot=original.game_name_snapshot,
                platform_snapshot=original.platform_snapshot, operation_type="REVERSAL",
                quantity_delta=delta, quantity_before=int(quantity_after) - delta,
                quantity_after=int(quantity_after), related_transaction_id=original.id,
                user_id=user.id, note=f"撤销流水 #{original.id}")
            session.add(reversal_tx)
            await session.flush()
            return ReverseResponse(transaction_id=reversal_tx.id,
                related_transaction_id=original.id, quantity_after=int(quantity_after),
                message=f"已撤销 {original.game_name_snapshot}，当前库存 {quantity_after} 件。")
    except IntegrityError as error:
        await session.rollback()
        raise TransactionError("该流水已被撤销") from error
