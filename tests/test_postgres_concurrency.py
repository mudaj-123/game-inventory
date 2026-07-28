"""只在真实 PostgreSQL 上运行的库存竞争集成测试。"""

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import CatalogEntry, InventoryTransaction, Product
from app.schemas import ScanRequest
from app.services.inventory import process_scan

pytestmark = pytest.mark.postgres
POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")


@pytest.fixture(scope="module")
async def postgres_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    if not POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL 未设置，未运行 PostgreSQL 并发测试")
    engine = create_async_engine(POSTGRES_URL, pool_size=10)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def run_scan(
    factory: async_sessionmaker[AsyncSession], request: ScanRequest
) -> dict[str, object]:
    async with factory() as session:
        return (await process_scan(session, request)).model_dump()


async def test_two_simultaneous_outs_only_sell_one(
    postgres_factory: async_sessionmaker[AsyncSession],
) -> None:
    barcode = "10000001"
    async with postgres_factory() as session, session.begin():
        session.add(
            Product(
                barcode=barcode,
                game_name="并发出库",
                normalized_name="并发出库",
                platform="PS5",
                region="UNKNOWN",
                quantity=1,
                low_stock_threshold=1,
                identification_status="CONFIRMED",
                metadata_source="MANUAL",
            )
        )
    requests = [
        ScanRequest(barcode=barcode, operation="OUT", client_scan_id=uuid4()) for _ in range(2)
    ]
    results = await asyncio.gather(*(run_scan(postgres_factory, request) for request in requests))

    assert sorted(result["status"] for result in results) == ["OUT_OF_STOCK", "SUCCESS"]
    async with postgres_factory() as session:
        product = await session.scalar(select(Product).where(Product.barcode == barcode))
        count = await session.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.barcode_snapshot == barcode
            )
        )
    assert product is not None and product.quantity == 0
    assert count == 1


async def test_same_scan_id_simultaneously_is_idempotent(
    postgres_factory: async_sessionmaker[AsyncSession],
) -> None:
    barcode = "10000002"
    async with postgres_factory() as session, session.begin():
        session.add(
            Product(
                barcode=barcode,
                game_name="并发幂等",
                normalized_name="并发幂等",
                platform="PS4",
                region="UNKNOWN",
                quantity=0,
                low_stock_threshold=1,
                identification_status="CONFIRMED",
                metadata_source="MANUAL",
            )
        )
    scan_id = uuid4()
    request = ScanRequest(barcode=barcode, operation="IN", client_scan_id=scan_id)
    results = await asyncio.gather(
        run_scan(postgres_factory, request), run_scan(postgres_factory, request)
    )

    assert all(result["status"] == "SUCCESS" for result in results)
    assert sorted(result["idempotent_replay"] for result in results) == [False, True]
    async with postgres_factory() as session:
        product = await session.scalar(select(Product).where(Product.barcode == barcode))
        count = await session.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.client_scan_id == str(scan_id)
            )
        )
    assert product is not None and product.quantity == 1
    assert count == 1


async def test_simultaneous_first_catalog_scans_create_one_product(
    postgres_factory: async_sessionmaker[AsyncSession],
) -> None:
    barcode = "10000003"
    async with postgres_factory() as session, session.begin():
        session.add(
            CatalogEntry(
                barcode=barcode,
                game_name="目录并发",
                normalized_name="目录并发",
                platform="SWITCH",
                region="UNKNOWN",
                verified=True,
                source_file="concurrency.csv",
                source_row=2,
            )
        )
    requests = [
        ScanRequest(barcode=barcode, operation="IN", client_scan_id=uuid4()) for _ in range(2)
    ]
    results = await asyncio.gather(*(run_scan(postgres_factory, request) for request in requests))

    assert all(result["status"] == "SUCCESS" for result in results)
    async with postgres_factory() as session:
        products = (
            await session.scalars(select(Product).where(Product.barcode == barcode))
        ).all()
        count = await session.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.barcode_snapshot == barcode
            )
        )
    assert len(products) == 1
    assert products[0].quantity == 2
    assert count == 2
