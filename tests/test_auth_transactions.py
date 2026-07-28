"""认证、权限、今日流水和安全撤销。"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.security import hash_password
from app.database import Base, get_db_session
from app.main import app
from app.models import InventoryTransaction, Product, User


@pytest.fixture
async def factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        session.add_all([
            User(username="staff", password_hash=hash_password("correct"), role="STAFF"),
            User(username="other", password_hash=hash_password("correct"), role="STAFF"),
            User(username="admin", password_hash=hash_password("correct"), role="ADMIN"),
            User(username="disabled", password_hash=hash_password("correct"), role="STAFF", active=False),  # noqa: E501
        ])
    yield maker
    await engine.dispose()


@pytest.fixture
def raw_client(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[TestClient]:
    async def db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session
    app.dependency_overrides[get_db_session] = db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def login(client: TestClient, username: str = "staff", password: str = "correct") -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


async def seed_product(factory: async_sessionmaker[AsyncSession], quantity: int = 0) -> Product:
    async with factory() as session, session.begin():
        product = Product(barcode="00001111", game_name="撤销游戏", normalized_name="撤销游戏",
            platform="PS5", region="UNKNOWN", quantity=quantity, low_stock_threshold=1,
            identification_status="CONFIRMED", metadata_source="MANUAL")
        session.add(product)
    return product


def scan(client: TestClient, csrf: str, operation: str = "IN") -> dict[str, object]:
    response = client.post("/api/scans", headers={"X-CSRF-Token": csrf}, json={
        "barcode": "00001111", "operation": operation, "client_scan_id": str(uuid.uuid4())})
    assert response.status_code == 200
    return response.json()


async def test_password_hash_and_login_rules(raw_client: TestClient,
                                             factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        staff = await session.scalar(select(User).where(User.username == "staff"))
        assert staff is not None and staff.password_hash != "correct"
        assert staff.password_hash.startswith("$2")
    assert raw_client.post("/api/auth/login", json={"username": "staff", "password": "bad"}).status_code == 401  # noqa: E501
    assert raw_client.post("/api/auth/login", json={"username": "disabled", "password": "correct"}).status_code == 401  # noqa: E501
    response = raw_client.post("/api/auth/login", json={"username": "staff", "password": "correct"})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]  # noqa: E501


async def test_scan_requires_auth_csrf_and_records_user(raw_client: TestClient,
                                                        factory: async_sessionmaker[AsyncSession]) -> None:  # noqa: E501
    await seed_product(factory)
    payload = {"barcode": "00001111", "operation": "IN", "client_scan_id": str(uuid.uuid4())}
    assert raw_client.post("/api/scans", json=payload).status_code == 401
    csrf = login(raw_client)
    assert raw_client.post("/api/scans", json=payload).status_code == 403
    result = scan(raw_client, csrf)
    async with factory() as session:
        tx = await session.get(InventoryTransaction, result["transaction_id"])
        staff_id = await session.scalar(select(User.id).where(User.username == "staff"))
        assert tx is not None and tx.user_id == staff_id
    assert raw_client.get("/api/admin/users").status_code == 403


async def test_today_visibility_sort_and_reversals(raw_client: TestClient,
                                                   factory: async_sessionmaker[AsyncSession]) -> None:  # noqa: E501
    await seed_product(factory)
    csrf = login(raw_client)
    first = scan(raw_client, csrf)
    second = scan(raw_client, csrf, "OUT")
    page = raw_client.get("/api/transactions").json()
    assert [item["transaction_id"] for item in page["items"]] == [second["transaction_id"], first["transaction_id"]]  # noqa: E501
    undone = raw_client.post("/api/transactions/undo-last", headers={"X-CSRF-Token": csrf})
    assert undone.status_code == 200 and undone.json()["quantity_after"] == 1
    duplicate = raw_client.post(f"/api/transactions/{second['transaction_id']}/reverse",
                                headers={"X-CSRF-Token": csrf})
    assert duplicate.status_code == 409
    async with factory() as session:
        assert await session.scalar(select(func.count(InventoryTransaction.id))) == 3
        assert await session.get(InventoryTransaction, second["transaction_id"]) is not None


async def test_reverse_in_refuses_negative_and_staff_restrictions(raw_client: TestClient,
                                                                  factory: async_sessionmaker[AsyncSession]) -> None:  # noqa: E501
    await seed_product(factory)
    csrf = login(raw_client)
    inbound = scan(raw_client, csrf)
    scan(raw_client, csrf, "OUT")
    response = raw_client.post(f"/api/transactions/{inbound['transaction_id']}/reverse",
                               headers={"X-CSRF-Token": csrf})
    assert response.status_code == 409  # not the most recent reversible transaction
    # Admin can target the inbound, but current stock is zero so the atomic update is rejected.
    raw_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    admin_csrf = login(raw_client, "admin")
    negative = raw_client.post(f"/api/transactions/{inbound['transaction_id']}/reverse",
                               headers={"X-CSRF-Token": admin_csrf})
    assert negative.status_code == 409


async def test_staff_cannot_reverse_other_or_expired(raw_client: TestClient,
                                                     factory: async_sessionmaker[AsyncSession]) -> None:  # noqa: E501
    product = await seed_product(factory, quantity=2)
    async with factory() as session, session.begin():
        other_id = await session.scalar(select(User.id).where(User.username == "other"))
        old = InventoryTransaction(client_scan_id=str(uuid.uuid4()), product_id=product.id,
            barcode_snapshot=product.barcode, game_name_snapshot=product.game_name,
            platform_snapshot=product.platform, operation_type="IN", quantity_delta=1,
            quantity_before=0, quantity_after=1, user_id=other_id,
            created_at=datetime.now(UTC) - timedelta(hours=1))
        session.add(old)
    csrf = login(raw_client)
    forbidden = raw_client.post(f"/api/transactions/{old.id}/reverse",
                                headers={"X-CSRF-Token": csrf})
    assert forbidden.status_code == 409
