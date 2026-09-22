"""Inventory search, sorting, live states, period counts and safe local covers."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models import CatalogEntry, InventoryTransaction, Product, StockAlert
from app.schemas.products import InventoryFilters
from app.services.products import cover_path, list_inventory
from tests.test_auth_transactions import factory as factory
from tests.test_auth_transactions import login, seed_product
from tests.test_auth_transactions import raw_client as raw_client


@pytest.fixture
async def inventory(factory: async_sessionmaker[AsyncSession]) -> list[int]:
    old = datetime.now(UTC) - timedelta(days=100)
    async with factory() as session, session.begin():
        catalog = CatalogEntry(barcode="00000001", game_name="Zelda", normalized_name="zelda",
                               platform="SWITCH", aliases="塞尔达|zelda alias",
                               source_file="test.csv",
                               source_row=2)
        session.add(catalog)
        await session.flush()
        products = [
            Product(barcode=f"0000000{i}", game_name=name, normalized_name=name.lower(),
                    platform=platform, quantity=quantity, region="JP" if i == 1 else "UNKNOWN",
                    edition="Deluxe" if i == 1 else None, manually_verified=i != 5,
                    low_stock_threshold=1, overstock_threshold=5 if i == 3 else None,
                    created_at=old if i in (3, 4) else datetime.now(UTC),
                    updated_at=datetime(2026, 1, i, tzinfo=UTC), active=i != 6,
                    catalog_entry_id=catalog.id if i == 1 else None)
            for i, (name, platform, quantity) in enumerate([
                ("Zelda", "SWITCH", 3), ("Alpha", "PS5", 0), ("Beta", "PS4", 5),
                ("Gamma", "PS5", 1), ("100%_literal", "SWITCH2", 3), ("Disabled", "PS5", 3),
            ], start=1)
        ]
        session.add_all(products)
        await session.flush()
        def tx(index: int, stamp: str, operation: str, delta: int) -> InventoryTransaction:
            p = products[index]
            return InventoryTransaction(client_scan_id=str(uuid.uuid4()), product_id=p.id,
                barcode_snapshot=p.barcode, game_name_snapshot="历史名", platform_snapshot="PS4",
                operation_type=operation, quantity_delta=delta, quantity_before=10,
                quantity_after=10 + delta, created_at=datetime.fromisoformat(stamp))
        sale = tx(0, "2026-03-01T00:00:00+00:00", "SALE_OUT", -2)
        session.add(sale)
        await session.flush()
        reversal = tx(0, "2026-03-01T01:00:00+00:00", "REVERSAL", 2)
        reversal.related_transaction_id = sale.id
        session.add_all([sale, reversal,
            tx(0, "2026-02-28T16:00:00+00:00", "IN", 4),
            tx(0, "2026-03-01T02:00:00+00:00", "ADJUST", -3),
            tx(2, "2026-03-01T15:59:59+00:00", "SALE_OUT", -5),
            tx(3, "2026-03-01T16:00:00+00:00", "SALE_OUT", -1),
        ])
        return [p.id for p in products]


def test_validation_and_permissions(raw_client: TestClient) -> None:
    url = "/api/admin/products"
    assert raw_client.get(url).status_code == 401
    login(raw_client)
    assert raw_client.get(url).status_code == 403
    assert raw_client.get(url + "/1/cover").status_code == 403
    login(raw_client, "admin")
    for query in ("sort=bad", "status=bad", "sales=bad", "order=bad", "page=0", "page_size=101",
                  "low_sales_max=0", "period=custom", "q=" + "x" * 256):
        assert raw_client.get(url + "?" + query).status_code == 422
    response = raw_client.get(url)
    assert response.json()["items"] == [] and response.json()["total"] == 0
    assert response.headers["Cache-Control"] == "no-store"


async def test_search_fields_literal_wildcards_and_exact_filters(
    raw_client: TestClient, inventory: list[int],
) -> None:
    login(raw_client, "admin")
    for term in ("zelda", "塞尔达", "00000001", "switch", "jp", "deluxe"):
        response = raw_client.get("/api/admin/products", params={"q": term})
        assert inventory[0] in [p["id"] for p in response.json()["items"]]
    response = raw_client.get("/api/admin/products", params={"q": "%_"})
    assert [p["id"] for p in response.json()["items"]] == [inventory[4]]
    response = raw_client.get("/api/admin/products", params={
        "platform": "switch", "region": "jp", "edition": "DELUXE",
    })
    assert response.json()["total"] == 1
    assert raw_client.get("/api/admin/products?edition=Del").json()["total"] == 0


async def test_period_counts_sorting_and_sales_filters(
    factory: async_sessionmaker[AsyncSession], inventory: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_timezone", "Asia/Shanghai")
    args = dict(period="custom", start="2026-03-01", end="2026-03-01")
    async with factory() as session:
        result = await list_inventory(session, InventoryFilters(**args, sort="sales", order="desc"))
        assert [p.id for p in result.items[:2]] == [inventory[2], inventory[0]]
        zelda = result.items[1]
        assert zelda.period_sales == 2 and zelda.period_inbound == 4
        assert zelda.game_name == "Zelda" and zelda.platform == "SWITCH"
        assert zelda.last_sale_at == datetime(2026, 3, 1, tzinfo=UTC)
        zero = await list_inventory(session, InventoryFilters(**args, sales="none"))
        assert [p.id for p in zero.items] == [inventory[3], inventory[4]]
        low = await list_inventory(session, InventoryFilters(**args, sales="low", low_sales_max=2))
        assert [p.id for p in low.items] == [inventory[0]]
        for sort in ("quantity", "name", "updated", "sales", "inbound", "outbound", "last_sale"):
            asc = await list_inventory(session, InventoryFilters(**args, sort=sort))
            desc = await list_inventory(session, InventoryFilters(**args, sort=sort, order="desc"))
            field = {"name": "game_name", "updated": "updated_at", "sales": "period_sales",
                     "inbound": "period_inbound", "outbound": "period_sales",
                     "last_sale": "last_sale_at"}.get(sort, sort)
            for result, reverse in ((asc, False), (desc, True)):
                values = [getattr(p, field) for p in result.items if getattr(p, field) is not None]
                if field == "game_name":
                    values = [v.lower() for v in values]
                assert values == sorted(values, reverse=reverse)
            if sort == "last_sale":
                assert asc.items[-1].last_sale_at is None
                assert desc.items[-1].last_sale_at is None
        first = await list_inventory(session, InventoryFilters(**args, page_size=2))
        second = await list_inventory(session, InventoryFilters(**args, page_size=2, page=2))
        assert first.total == second.total == 6
        assert {p.id for p in first.items}.isdisjoint(p.id for p in second.items)
        beyond = await list_inventory(session, InventoryFilters(**args, page=100))
        assert beyond.items == [] and beyond.total == 6


async def test_live_states_without_refresh_or_alert_writes(
    raw_client: TestClient, factory: async_sessionmaker[AsyncSession], inventory: list[int],
) -> None:
    login(raw_client, "admin")
    expected = {"low": [inventory[3]], "sold_out": [inventory[1]], "overstock": [inventory[2]],
                "pending": [inventory[4]]}
    for status, ids in expected.items():
        result = raw_client.get("/api/admin/products", params={"status": status}).json()
        assert [p["id"] for p in result["items"]] == ids
        assert all(status in p["states"] for p in result["items"])
    async with factory() as session, session.begin():
        p = await session.get(Product, inventory[4])
        p.manually_verified = True
        p.created_at = datetime.now(UTC) - timedelta(days=settings.stale_stock_days + 1)
        assert await session.scalar(select(func.count(StockAlert.id))) == 0
    stale = raw_client.get("/api/admin/products?status=stale").json()
    assert inventory[4] in [p["id"] for p in stale["items"]]
    async with factory() as session, session.begin():
        p = await session.get(Product, inventory[4])
        p.created_at = datetime.now(UTC)
    normal = raw_client.get("/api/admin/products?status=normal").json()
    assert inventory[4] in [p["id"] for p in normal["items"]]
    assert inventory[5] not in [p["id"] for p in normal["items"]]
    async with factory() as session:
        assert await session.scalar(select(func.count(StockAlert.id))) == 0


async def test_local_cover_path_and_authenticated_delivery(
    raw_client: TestClient, factory: async_sessionmaker[AsyncSession], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "covers"
    root.mkdir()
    monkeypatch.setattr(settings, "local_cover_dir", root)
    (root / "test.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "outside.png").write_bytes(b"private")
    (root / "bad.svg").write_text("<svg/>")
    for name in ("../outside.png", str(tmp_path / "outside.png"),
                 "bad.svg", "missing.png", "\0.png"):
        assert cover_path(name) is None
    p = await seed_product(factory)
    async with factory() as session, session.begin():
        product = await session.get(Product, p.id)
        product.cover_filename = "test.png"
    assert raw_client.get(f"/api/admin/products/{p.id}/cover").status_code == 401
    login(raw_client, "admin")
    listing = raw_client.get("/api/admin/products").json()
    response = raw_client.get(listing["items"][0]["cover_url"])
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert raw_client.get("/api/admin/products/999/cover").status_code == 404
