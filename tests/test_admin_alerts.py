"""管理员调整、预警跨越与身份绑定幂等键回归。"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import InventoryTransaction, Product, StockAlert
from tests.test_auth_transactions import (  # noqa: F401
    factory as factory,
)
from tests.test_auth_transactions import (
    login,
    scan,
    seed_product,
)
from tests.test_auth_transactions import (
    raw_client as raw_client,
)


async def test_adjustment_permissions_reason_idempotency_and_reversal(raw_client, factory):
    product = await seed_product(factory, quantity=2)
    body = {"client_scan_id": str(uuid.uuid4()), "quantity_delta": -1, "reason": "盘点破损"}
    url = f"/api/admin/products/{product.id}/adjust"
    csrf = login(raw_client)
    assert raw_client.post(url, json=body, headers={"X-CSRF-Token": csrf}).status_code == 403
    csrf = login(raw_client, "admin")
    assert raw_client.post(url, json=body).status_code == 403
    headers = {"X-CSRF-Token": csrf}
    assert raw_client.post(url, json={**body, "reason": " "}, headers=headers).status_code == 422
    first = raw_client.post(url, json=body, headers=headers)
    assert first.status_code == 200
    assert first.json()["quantity_after"] == 1
    assert raw_client.post(url, json=body, headers=headers).json()["idempotent_replay"]
    assert (
        raw_client.post(url, json={**body, "quantity_delta": -2}, headers=headers).status_code
        == 409
    )
    body["client_scan_id"] = str(uuid.uuid4())
    body["quantity_delta"] = -5
    assert raw_client.post(url, json=body, headers=headers).status_code == 409
    original_id = first.json()["transaction_id"]
    response = raw_client.post(f"/api/transactions/{original_id}/reverse", headers=headers)
    assert response.status_code == 200, response.text
    async with factory() as session:
        original = await session.get(InventoryTransaction, original_id)
        assert original.note == "盘点破损" and original.quantity_delta == -1
        assert (await session.get(Product, product.id)).quantity == 2


async def test_alert_transitions_refresh_dedup_and_stale_stock(raw_client, factory):
    product = await seed_product(factory, quantity=2)
    async with factory() as session, session.begin():
        p = await session.get(Product, product.id)
        p.overstock_threshold = 3
        p.created_at = datetime.now(UTC) - timedelta(days=40)
    csrf = login(raw_client, "admin")
    for _ in range(2):
        response = raw_client.get("/api/admin/alerts")
        assert [a["kind"] for a in response.json()["items"]] == ["STALE_STOCK"]
    assert "LOW_STOCK" in scan(raw_client, csrf, "OUT")["alerts"]
    assert "SOLD_OUT" in scan(raw_client, csrf, "OUT")["alerts"]
    assert [a["kind"] for a in raw_client.get("/api/admin/alerts").json()["items"]] == ["SOLD_OUT"]
    for _ in range(3):
        result = scan(raw_client, csrf)
    assert result["alerts"] == ["OVERSTOCK"]
    async with factory() as session:
        active = (
            await session.scalars(select(StockAlert).where(StockAlert.closed_at.is_(None)))
        ).all()
        assert len(active) == 1
        count = await session.scalar(select(func.count(StockAlert.id)))
        assert count == 5  # stale, low, sold out, low reopened, overstock


async def test_scan_id_cannot_be_reused_for_another_user_or_intent(raw_client, factory):
    await seed_product(factory)
    csrf = login(raw_client)
    body = {"barcode": "00001111", "operation": "IN", "client_scan_id": str(uuid.uuid4())}
    headers = {"X-CSRF-Token": csrf}
    assert raw_client.post("/api/scans", json=body, headers=headers).status_code == 200
    assert (
        raw_client.post(
            "/api/scans", json={**body, "operation": "OUT"}, headers=headers
        ).status_code
        == 409
    )
    csrf = login(raw_client, "other")
    assert (
        raw_client.post("/api/scans", json=body, headers={"X-CSRF-Token": csrf}).status_code == 409
    )


async def test_inventory_search_and_admin_only_dashboard(raw_client, factory):
    await seed_product(factory)
    login(raw_client)
    assert raw_client.get("/api/admin/products").status_code == 403
    assert raw_client.get("/api/admin/alerts").status_code == 403
    login(raw_client, "admin")
    response = raw_client.get("/api/admin/products?q=0000")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["barcode"] == "00001111"
    assert raw_client.get("/api/admin/products?q=%25").json()["total"] == 0


async def test_product_confirmation_changes_thresholds_but_keeps_snapshots(raw_client, factory):
    product = await seed_product(factory)
    csrf = login(raw_client, "admin")
    original = scan(raw_client, csrf)
    response = raw_client.patch(
        f"/api/admin/products/{product.id}",
        json={
            "game_name": "新名称",
            "platform": "PS4",
            "low_stock_threshold": 0,
            "overstock_threshold": 0,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["alerts"] == ["OVERSTOCK"]
    assert raw_client.get("/api/admin/alerts").json()["pending_products"] == []
    async with factory() as session:
        tx = await session.get(InventoryTransaction, original["transaction_id"])
        assert tx.game_name_snapshot == "撤销游戏" and tx.platform_snapshot == "PS5"


async def test_admin_imports_configured_bom_catalog(raw_client, tmp_path, monkeypatch):
    from app.config import settings

    path = tmp_path / "catalog.csv"
    path.write_text("barcode,game_name,platform\n00008888,目录游戏,Switch\n", encoding="utf-8-sig")
    monkeypatch.setattr(settings, "local_catalog_path", path)
    csrf = login(raw_client, "admin")
    headers = {"X-CSRF-Token": csrf}
    result = raw_client.post("/api/admin/catalog/import", headers=headers)
    assert result.status_code == 200 and result.json()["added"] == 1
    assert raw_client.post("/api/admin/catalog/import", headers=headers).json()["skipped"] == 1
    response = raw_client.post(
        "/api/scans",
        headers=headers,
        json={"barcode": "00008888", "operation": "IN", "client_scan_id": str(uuid.uuid4())},
    )
    assert response.json()["game_name"] == "目录游戏"
    assert response.json()["barcode"] == "00008888"
