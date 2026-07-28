"""P0 库存闭环：目录导入、扫码、幂等和事务测试。"""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.security import hash_password
from app.database import Base, get_db_session
from app.main import app
from app.models import CatalogEntry, InventoryTransaction, Product, User
from app.services.catalog import import_catalog


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[TestClient]:
    async with session_factory() as session, session.begin():
        session.add(
            User(username="tester", password_hash=hash_password("test-password"), role="STAFF")
        )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as test_client:
        login = test_client.post(
            "/api/auth/login", json={"username": "tester", "password": "test-password"}
        )
        test_client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        yield test_client
    app.dependency_overrides.clear()


def scan_payload(barcode: str, operation: str = "IN", scan_id: str | None = None) -> dict[str, str]:
    return {
        "barcode": barcode,
        "operation": operation,
        "client_scan_id": scan_id or str(uuid.uuid4()),
    }


async def test_csv_import_accepts_bom_preserves_zeroes_and_reports_bad_rows(
    tmp_path: Path, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text(
        "\ufeffbarcode,game_name,platform,verified\n"
        "00001234,零号游戏,Nintendo Switch,yes\n"
        "00001234,重复游戏,NS,false\n"
        "123,坏条码,PS5,false\n"
        "12345678,平台错误,XBOX,false\n",
        encoding="utf-8",
    )
    async with session_factory() as session, session.begin():
        report = await import_catalog(session, path)
    async with session_factory() as session:
        entry = await session.scalar(select(CatalogEntry))

    assert report.added == 1
    assert report.conflicts == 1
    assert len(report.errors) == 3
    assert entry is not None
    assert entry.barcode == "00001234"
    assert entry.platform == "SWITCH"
    assert entry.verified is True


async def seed_catalog(session_factory: async_sessionmaker[AsyncSession], barcode: str) -> None:
    async with session_factory() as session, session.begin():
        session.add(
            CatalogEntry(
                barcode=barcode,
                game_name="测试游戏",
                normalized_name="测试游戏",
                platform="PS5",
                region="UNKNOWN",
                verified=True,
                source_file="test.csv",
                source_row=2,
            )
        )


async def test_catalog_match_in_out_and_out_of_stock(
    client: TestClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await seed_catalog(session_factory, "00000001")

    inbound = client.post("/api/scans", json=scan_payload("00000001"))
    outbound = client.post("/api/scans", json=scan_payload("00000001", "OUT"))
    empty = client.post("/api/scans", json=scan_payload("00000001", "OUT"))

    assert inbound.status_code == 200
    assert inbound.json()["quantity_after"] == 1
    assert outbound.json()["quantity_after"] == 0
    assert empty.json()["status"] == "OUT_OF_STOCK"
    async with session_factory() as session:
        assert await session.scalar(select(func.count(InventoryTransaction.id))) == 2


async def test_unknown_barcode_and_manual_resolution_are_atomic(
    client: TestClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    barcode = "00009999"
    unknown = client.post("/api/scans", json=scan_payload(barcode))
    scan_id = str(uuid.uuid4())
    resolved = client.post(
        "/api/scans/resolve-unknown",
        json={
            **scan_payload(barcode, scan_id=scan_id),
            "game_name": "人工游戏",
            "platform": "SWITCH2",
        },
    )

    assert unknown.json()["status"] == "UNKNOWN_BARCODE_REQUIRES_INPUT"
    assert resolved.json()["status"] == "SUCCESS"
    assert resolved.json()["quantity_before"] == 0
    assert resolved.json()["quantity_after"] == 1
    async with session_factory() as session:
        product = await session.scalar(select(Product).where(Product.barcode == barcode))
        transaction = await session.scalar(
            select(InventoryTransaction).where(InventoryTransaction.client_scan_id == scan_id)
        )
        assert product is not None and product.quantity == 1 and product.manually_verified
        assert transaction is not None and transaction.product_id == product.id


async def test_idempotent_replay_and_distinct_scan_ids_count_separately(
    client: TestClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await seed_catalog(session_factory, "00123456")
    request = scan_payload("00123456")

    first = client.post("/api/scans", json=request).json()
    replay = client.post("/api/scans", json=request).json()
    next_scan = client.post("/api/scans", json=scan_payload("00123456")).json()

    assert first["quantity_after"] == 1
    assert replay["quantity_after"] == 1
    assert replay["idempotent_replay"] is True
    assert next_scan["quantity_after"] == 2
    async with session_factory() as session:
        assert await session.scalar(select(func.count(InventoryTransaction.id))) == 2


async def test_database_constraint_rolls_back_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(
            Product(
                barcode="00999999",
                game_name="回滚测试",
                normalized_name="回滚测试",
                platform="PS4",
                region="UNKNOWN",
                quantity=-1,
                low_stock_threshold=1,
                identification_status="CONFIRMED",
                metadata_source="MANUAL",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with session_factory() as session:
        assert await session.scalar(select(func.count(Product.id))) == 0
