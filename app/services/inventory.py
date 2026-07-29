"""原子、幂等的库存扫码业务。"""

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.config import settings
from app.models import CatalogEntry, InventoryTransaction, Product
from app.schemas import ResolveUnknownRequest, ScanRequest, ScanResponse
from app.services.catalog import normalize_name

MAX_TRANSACTION_ATTEMPTS = 3


class InventoryConflictError(RuntimeError):
    """A retryable inventory uniqueness race could not be resolved."""


def _is_unique_violation(error: IntegrityError) -> bool:
    """Return whether an IntegrityError is specifically a unique violation."""

    original = error.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate == "23505":
        return True
    # SQLite is used by local/unit tests and does not expose SQLSTATE.
    return "UNIQUE constraint failed" in str(original)


def _response_from_transaction(transaction: InventoryTransaction, replay: bool) -> ScanResponse:
    action = "入库" if transaction.operation_type == "IN" else "出库"
    suffix = "当前库存" if action == "入库" else "剩余"
    return ScanResponse(
        status="SUCCESS",
        message=(
            f"{transaction.game_name_snapshot}，{action}成功，"
            f"{suffix} {transaction.quantity_after} 件。"
        ),
        barcode=transaction.barcode_snapshot,
        game_name=transaction.game_name_snapshot,
        platform=transaction.platform_snapshot,
        quantity_before=transaction.quantity_before,
        quantity_after=transaction.quantity_after,
        transaction_id=transaction.id,
        idempotent_replay=replay,
    )


async def _existing_transaction(
    session: AsyncSession, client_scan_id: str
) -> InventoryTransaction | None:
    return await session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.client_scan_id == client_scan_id
        )
    )


async def _change_quantity(
    session: AsyncSession, product: Product, operation: str, scan: ScanRequest, user: CurrentUser
) -> ScanResponse:
    delta = 1 if operation == "IN" else -1
    statement = update(Product).where(Product.id == product.id)
    if delta < 0:
        statement = statement.where(Product.quantity > 0)
    new_quantity = await session.scalar(
        statement.values(quantity=Product.quantity + delta).returning(Product.quantity)
    )
    if new_quantity is None:
        return ScanResponse(
            status="OUT_OF_STOCK",
            message=f"{product.game_name}，库存不足，无法出库。",
            barcode=product.barcode,
            game_name=product.game_name,
            platform=product.platform,
            quantity_before=0,
            quantity_after=0,
        )
    quantity_after = int(new_quantity)
    transaction = InventoryTransaction(
        client_scan_id=str(scan.client_scan_id),
        product_id=product.id,
        barcode_snapshot=product.barcode,
        game_name_snapshot=product.game_name,
        platform_snapshot=product.platform,
        operation_type="IN" if delta > 0 else "SALE_OUT",
        quantity_delta=delta,
        quantity_before=quantity_after - delta,
        quantity_after=quantity_after,
        device_id=scan.device_id,
        user_id=user.id,
    )
    session.add(transaction)
    await session.flush()
    return _response_from_transaction(transaction, False)


async def _process_scan_once(
    session: AsyncSession, scan: ScanRequest, user: CurrentUser
) -> ScanResponse:
    scan_id = str(scan.client_scan_id)
    async with session.begin():
        previous = await _existing_transaction(session, scan_id)
        if previous is not None:
            return _response_from_transaction(previous, True)

        product = await session.scalar(select(Product).where(Product.barcode == scan.barcode))
        if product is None:
            catalog = await session.scalar(
                select(CatalogEntry).where(CatalogEntry.barcode == scan.barcode)
            )
            if catalog is None or scan.operation == "OUT":
                return ScanResponse(
                    status="UNKNOWN_BARCODE_REQUIRES_INPUT",
                    message="未知条码，请先入库登记或由管理员补全资料。",
                    barcode=scan.barcode,
                )
            product = Product(
                barcode=catalog.barcode,
                game_name=catalog.game_name,
                normalized_name=catalog.normalized_name,
                platform=catalog.platform,
                region=catalog.region,
                edition=catalog.edition,
                language=catalog.language,
                cover_filename=catalog.cover_filename,
                quantity=0,
                low_stock_threshold=settings.default_low_stock_threshold,
                overstock_threshold=settings.default_overstock_threshold,
                identification_status="CATALOG_MATCHED",
                metadata_source="LOCAL_CATALOG",
                catalog_entry_id=catalog.id,
            )
            session.add(product)
            await session.flush()
        return await _change_quantity(session, product, scan.operation, scan, user)


async def process_scan(
    session: AsyncSession, scan: ScanRequest, user: CurrentUser
) -> ScanResponse:
    """处理扫码，并对商品或幂等键的唯一约束竞争作有限重试。"""

    for attempt in range(MAX_TRANSACTION_ATTEMPTS):
        try:
            return await _process_scan_once(session, scan, user)
        except IntegrityError as error:
            # begin() normally rolls back, but make the boundary explicit before
            # any retry/query so no failed transaction state can leak forward.
            await session.rollback()
            if not _is_unique_violation(error):
                raise
            if attempt == MAX_TRANSACTION_ATTEMPTS - 1:
                raise InventoryConflictError(
                    "库存请求发生并发冲突，请重新扫描。"
                ) from error
    raise AssertionError("unreachable")


async def _resolve_unknown_once(
    session: AsyncSession, request: ResolveUnknownRequest, user: CurrentUser
) -> ScanResponse:
    scan_id = str(request.client_scan_id)
    async with session.begin():
        previous = await _existing_transaction(session, scan_id)
        if previous is not None:
            return _response_from_transaction(previous, True)
        product = await session.scalar(select(Product).where(Product.barcode == request.barcode))
        if product is None:
            product = Product(
                barcode=request.barcode,
                game_name=request.game_name,
                normalized_name=normalize_name(request.game_name),
                platform=request.platform,
                region=request.region.upper(),
                edition=request.edition,
                quantity=0,
                low_stock_threshold=request.low_stock_threshold,
                overstock_threshold=request.overstock_threshold,
                identification_status="CONFIRMED",
                metadata_source="MANUAL",
                manually_verified=True,
            )
            session.add(product)
            await session.flush()
        scan = ScanRequest(
            barcode=request.barcode,
            operation="IN",
            client_scan_id=request.client_scan_id,
            device_id=request.device_id,
        )
        return await _change_quantity(session, product, "IN", scan, user)


async def resolve_unknown(
    session: AsyncSession, request: ResolveUnknownRequest, user: CurrentUser
) -> ScanResponse:
    """人工建品和首次入库在同一事务内完成，并处理唯一约束竞争。"""

    for attempt in range(MAX_TRANSACTION_ATTEMPTS):
        try:
            return await _resolve_unknown_once(session, request, user)
        except IntegrityError as error:
            await session.rollback()
            if not _is_unique_violation(error):
                raise
            if attempt == MAX_TRANSACTION_ATTEMPTS - 1:
                raise InventoryConflictError(
                    "未知条码补录发生并发冲突，请重新扫描。"
                ) from error
    raise AssertionError("unreachable")
