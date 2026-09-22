"""Report permissions, business-day boundaries, immutable snapshots and reversal accounting."""

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models import InventoryTransaction
from app.services.reports import report_dates, utc_bounds
from tests.test_auth_transactions import factory as factory
from tests.test_auth_transactions import login, seed_product
from tests.test_auth_transactions import raw_client as raw_client


def test_periods_and_dst() -> None:
    today = date(2026, 3, 1)
    assert report_dates("week", None, None, today) == (date(2026, 2, 23), today)
    assert report_dates("month", None, None, today) == (today, today)
    assert report_dates("7d", None, None, today) == (date(2026, 2, 23), today)
    assert report_dates("30d", None, None, today) == (date(2026, 1, 31), today)
    lower, upper = utc_bounds(date(2026, 3, 8), date(2026, 3, 8), ZoneInfo("America/New_York"))
    assert (upper - lower).total_seconds() == 23 * 3600


def test_report_permissions_and_validation(raw_client: TestClient) -> None:
    url = "/api/admin/reports/sales"
    assert raw_client.get(url).status_code == 401
    login(raw_client)
    assert raw_client.get(url).status_code == 403
    login(raw_client, "admin")
    for query in ("period=invalid", "period=custom", "page=0", "page_size=101",
                  "period=7d&start=2026-01-01",
                  "period=custom&start=2026-03-02&end=2026-03-01",
                  "period=custom&start=2025-01-01&end=2026-12-31",
                  "period=custom&start=9999-12-31&end=9999-12-31",
                  "period=custom&start=0001-01-01&end=0001-01-01"):
        assert raw_client.get(f"{url}?{query}").status_code == 422
    response = raw_client.get(url)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["totals"] == {"sold": 0, "reversed": 0, "net": 0}
    assert len(response.json()["daily"]) == 7


async def test_sales_snapshots_boundaries_reversals_and_pages(
    raw_client: TestClient, factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_timezone", "Asia/Shanghai")
    product = await seed_product(factory, quantity=10)
    async with factory() as session, session.begin():
        def tx(day: str, operation: str, delta: int, related: int | None = None,
               name: str = "旧名称") -> InventoryTransaction:
            return InventoryTransaction(
                client_scan_id=str(uuid.uuid4()), product_id=product.id,
                barcode_snapshot="00001111", game_name_snapshot=name,
                platform_snapshot="PS4", operation_type=operation, quantity_delta=delta,
                quantity_before=10, quantity_after=10 + delta, related_transaction_id=related,
                created_at=datetime.fromisoformat(day).replace(tzinfo=UTC),
            )
        old = tx("2026-02-28T15:59:59", "SALE_OUT", -2)
        inbound = tx("2026-03-01T01:00:00", "IN", 1)
        sale = tx("2026-02-28T16:00:00", "SALE_OUT", -3)
        session.add_all([old, inbound, sale])
        await session.flush()
        session.add_all([
            tx("2026-03-01T15:59:59", "REVERSAL", 2, old.id),
            tx("2026-03-01T03:00:00", "REVERSAL", -1, inbound.id),
            tx("2026-03-01T02:00:00", "ADJUST", -2),
            tx("2026-03-01T04:00:00", "SALE_OUT", -1, name="另一快照"),
            tx("2026-03-01T16:00:00", "REVERSAL", 3, sale.id),
        ])
    login(raw_client, "admin")
    url = "/api/admin/reports/sales?period=custom&start=2026-03-01&end=2026-03-01"
    report = raw_client.get(url + "&page_size=1").json()
    assert report["totals"] == {"sold": 4, "reversed": 2, "net": 2}
    assert report["daily"] == [{"date": "2026-03-01", **report["totals"]}]
    assert report["platforms"] == [{"platform": "PS4", **report["totals"]}]
    assert report["game_total"] == 2
    assert report["games"][0]["barcode"] == "00001111"
    assert report["games"][0]["game_name"] == "旧名称"
    second = raw_client.get(url + "&page_size=1&page=2").json()
    assert second["games"][0]["game_name"] == "另一快照"
    assert second["totals"] == report["totals"]
    next_day = raw_client.get(
        "/api/admin/reports/sales?period=custom&start=2026-03-02&end=2026-03-02"
    ).json()
    assert next_day["totals"] == {"sold": 0, "reversed": 3, "net": -3}
