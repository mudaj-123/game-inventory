"""Real PostgreSQL coverage for inventory race handling."""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.security import hash_password
from app.models import CatalogEntry, InventoryTransaction, Product, User
from app.schemas import ScanRequest
from app.services.inventory import process_scan
from app.services.transactions import TransactionError, reverse_transaction

pytestmark = pytest.mark.postgres


@pytest.fixture
async def postgres_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("TEST_POSTGRES_URL is required in GitHub Actions")
        pytest.skip("TEST_POSTGRES_URL is not configured")
    engine = create_async_engine(url, pool_size=5)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE inventory_transactions, products, catalog_entries, users "
                "RESTART IDENTITY CASCADE"
            )
        )
    async with factory() as session, session.begin():
        session.add(User(username="postgres-staff", password_hash=hash_password("test"), role="STAFF"))  # noqa: E501
    yield factory
    await engine.dispose()


def request(barcode: str, operation: str, scan_id: uuid.UUID | None = None) -> ScanRequest:
    return ScanRequest(
        barcode=barcode,
        operation=operation,
        client_scan_id=scan_id or uuid.uuid4(),
    )


async def run_scan(
    factory: async_sessionmaker[AsyncSession], scan: ScanRequest
):
    async with factory() as session:
        user = await session.scalar(select(User).where(User.username == "postgres-staff"))
        assert user is not None
        await session.rollback()
        return await process_scan(session, scan, user)


async def add_catalog(factory: async_sessionmaker[AsyncSession], barcode: str) -> None:
    async with factory() as session, session.begin():
        session.add(
            CatalogEntry(
                barcode=barcode,
                game_name="并发游戏",
                normalized_name="并发游戏",
                platform="PS5",
                region="UNKNOWN",
                verified=True,
                source_file="postgres-test.csv",
                source_row=1,
            )
        )


async def test_two_outbound_scans_cannot_make_stock_negative(
    postgres_factory: async_sessionmaker[AsyncSession],
) -> None:
    barcode = "00000011"
    await add_catalog(postgres_factory, barcode)
    await run_scan(postgres_factory, request(barcode, "IN"))

    results = await asyncio.gather(
        run_scan(postgres_factory, request(barcode, "OUT")),
        run_scan(postgres_factory, request(barcode, "OUT")),
    )

    assert sorted(result.status for result in results) == ["OUT_OF_STOCK", "SUCCESS"]
    async with postgres_factory() as session:
        product = await session.scalar(select(Product).where(Product.barcode == barcode))
        successful_out = await session.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.barcode_snapshot == barcode,
                InventoryTransaction.operation_type == "SALE_OUT",
            )
        )
    assert product is not None and product.quantity == 0
    assert successful_out == 1


async def test_same_scan_id_is_applied_once_under_concurrency(
    postgres_factory: async_sessionmaker[AsyncSession],
) -> None:
    barcode = "00000012"
    scan_id = uuid.uuid4()
    await add_catalog(postgres_factory, barcode)

    results = await asyncio.gather(
        run_scan(postgres_factory, request(barcode, "IN", scan_id)),
        run_scan(postgres_factory, request(barcode, "IN", scan_id)),
    )

    assert sorted(result.idempotent_replay for result in results) == [False, True]
    assert {result.quantity_after for result in results} == {1}
    async with postgres_factory() as session:
        product = await session.scalar(select(Product).where(Product.barcode == barcode))
        transaction_count = await session.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.client_scan_id == str(scan_id)
            )
        )
    assert product is not None and product.quantity == 1
    assert transaction_count == 1


async def test_first_catalog_scan_product_creation_race_is_retried(
    postgres_factory: async_sessionmaker[AsyncSession],
) -> None:
    barcode = "00000013"
    await add_catalog(postgres_factory, barcode)

    results = await asyncio.gather(
        run_scan(postgres_factory, request(barcode, "IN")),
        run_scan(postgres_factory, request(barcode, "IN")),
    )

    assert [result.status for result in results] == ["SUCCESS", "SUCCESS"]
    async with postgres_factory() as session:
        product_count = await session.scalar(
            select(func.count(Product.id)).where(Product.barcode == barcode)
        )
        product = await session.scalar(select(Product).where(Product.barcode == barcode))
        transaction_count = await session.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.barcode_snapshot == barcode
            )
        )
    assert product_count == 1
    assert product is not None and product.quantity == 2
    assert transaction_count == 2


async def test_concurrent_duplicate_reversal_succeeds_once(
    postgres_factory: async_sessionmaker[AsyncSession],
) -> None:
    barcode = "00000014"
    await add_catalog(postgres_factory, barcode)
    original = await run_scan(postgres_factory, request(barcode, "IN"))

    async def undo() -> object:
        async with postgres_factory() as session:
            user = await session.scalar(select(User).where(User.username == "postgres-staff"))
            assert user is not None
            await session.rollback()
            try:
                return await reverse_transaction(session, user, original.transaction_id)
            except TransactionError as error:
                return error

    results = await asyncio.gather(undo(), undo())
    assert sum(not isinstance(result, TransactionError) for result in results) == 1
    async with postgres_factory() as session:
        product = await session.scalar(select(Product).where(Product.barcode == barcode))
        reversal_count = await session.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.related_transaction_id == original.transaction_id
            )
        )
    assert product is not None and product.quantity == 0
    assert reversal_count == 1
