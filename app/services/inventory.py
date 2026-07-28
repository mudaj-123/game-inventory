"""原子、幂等的库存扫码业务。"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CatalogEntry, InventoryTransaction, Product
from app.schemas import ResolveUnknownRequest, ScanRequest, ScanResponse
from app.services.catalog import normalize_name


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
    session: AsyncSession, product: Product, operation: str, scan: ScanRequest
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
    )
    session.add(transaction)
    await session.flush()
    return _response_from_transaction(transaction, False)


async def process_scan(session: AsyncSession, scan: ScanRequest) -> ScanResponse:
    """处理已知、目录匹配和未知条码，成功变化与流水同事务提交。"""

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
        return await _change_quantity(session, product, scan.operation, scan)


async def resolve_unknown(
    session: AsyncSession, request: ResolveUnknownRequest
) -> ScanResponse:
    """人工建品和首次入库在同一数据库事务内完成。"""

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
        return await _change_quantity(session, product, "IN", scan)
