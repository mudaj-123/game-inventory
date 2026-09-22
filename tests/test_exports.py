"""CSV download authorization, full-filter exports, safe text and catalog round trips."""

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import CatalogEntry, InventoryTransaction, Product
from app.services.catalog import import_catalog
from app.services.csv_format import TEXT_ENCODING, decode_catalog_row, safe_cell
from app.services.exports import CATALOG_COLUMNS, read_chunks, save_export
from tests.test_auth_transactions import factory as factory
from tests.test_auth_transactions import login, seed_product
from tests.test_auth_transactions import raw_client as raw_client


def csv_rows(content: bytes) -> list[dict[str, str]]:
    assert content.startswith(b"\xef\xbb\xbf")
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline="")))


def test_download_permissions_headers_and_empty_files(raw_client: TestClient) -> None:
    urls = ["/api/admin/exports/manual-catalog.csv", "/api/admin/exports/inventory.csv"]
    for url in urls:
        assert raw_client.get(url).status_code == 401
    login(raw_client)
    for url in urls:
        assert raw_client.get(url).status_code == 403
    login(raw_client, "admin")
    for url in urls:
        response = raw_client.get(url)
        assert response.status_code == 200
        assert csv_rows(response.content) == []
        assert response.headers["content-type"].startswith("text/csv")
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.headers["cache-control"] == "no-store"
    assert raw_client.get("/api/admin/exports/inventory.csv?period=custom").status_code == 422
    assert raw_client.get("/api/admin/exports/inventory.csv?sort=invalid").status_code == 422


async def test_manual_mapping_roundtrip_and_no_inventory_mutation(
    raw_client: TestClient, factory: async_sessionmaker[AsyncSession], tmp_path: Path,
) -> None:
    p = await seed_product(factory, quantity=4)
    async with factory() as session, session.begin():
        product = await session.get(Product, p.id)
        product.game_name = '=测试("中文,引号")\n下一行'
        product.edition = "'原样单引号"
        product.manually_verified = False
        session.add(Product(barcode="00009999", game_name="目录商品", normalized_name="目录商品",
                            platform="PS5", metadata_source="LOCAL_CATALOG"))
    login(raw_client, "admin")
    response = raw_client.get("/api/admin/exports/manual-catalog.csv")
    rows = csv_rows(response.content)
    assert len(rows) == 1 and list(rows[0]) == CATALOG_COLUMNS
    assert rows[0]["barcode"] == "00001111"
    assert rows[0]["game_name"].startswith("'=")
    assert rows[0]["edition"] == "''原样单引号"
    assert rows[0]["verified"] == "false"
    path = tmp_path / "export.csv"
    path.write_bytes(response.content)
    async with factory() as session, session.begin():
        report = await import_catalog(session, path)
        assert report.added == 1 and report.errors == []
        entry = await session.scalar(select(CatalogEntry).where(CatalogEntry.barcode == "00001111"))
        assert entry.game_name == '=测试("中文,引号")\n下一行'
        assert entry.edition == "'原样单引号" and entry.verified is False
        again = await import_catalog(session, path)
        assert again.skipped == 1
        assert (await session.get(Product, p.id)).quantity == 4
        assert await session.scalar(select(func.count(InventoryTransaction.id))) == 0


async def test_inventory_export_all_pages_matches_filters_and_order(
    raw_client: TestClient, factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session, session.begin():
        session.add_all([
            Product(barcode=f"{i:08d}", game_name=f"商品{i}", normalized_name=f"商品{i}",
                    platform="PS5" if i < 103 else "PS4", quantity=i)
            for i in range(1, 105)
        ])
    login(raw_client, "admin")
    params = {"platform": "PS5", "sort": "quantity", "order": "desc", "page_size": 1, "page": 2}
    listed = raw_client.get("/api/admin/products", params=params).json()
    response = raw_client.get("/api/admin/exports/inventory.csv", params=params)
    rows = csv_rows(response.content)
    assert listed["total"] == len(rows) == 102
    assert [int(r["quantity"]) for r in rows] == list(range(102, 0, -1))
    assert rows[1]["barcode"] == listed["items"][0]["barcode"] == "00000101"
    assert rows[0]["period_start"] == listed["start"]
    assert rows[0]["period_end"] == listed["end"]
    assert rows[0]["timezone"] == listed["timezone"]
    assert all(r["period_sales"] == "0" for r in rows)


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-cmd", "@SUM(1)", "\tname", "\rname",
                                   "\nname", "  =1", "'literal", "中文,\"引号\"", "00000001"])
def test_safe_cells_are_reversible(value: str) -> None:
    encoded = safe_cell(value)
    assert not encoded.startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
    assert decode_catalog_row({"game_name": encoded, "csv_text_encoding": TEXT_ENCODING})[
        "game_name"
    ] == value
    assert decode_catalog_row({"game_name": "'ordinary"})["game_name"] == "'ordinary"


def test_atomic_file_failure_and_stream_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    destination = tmp_path / "manual.csv"
    destination.write_bytes(b"previous")
    file = io.BytesIO(b"new data")
    def fail_replace(*args: object) -> None:
        raise OSError("disk failure")
    monkeypatch.setattr("app.services.exports.os.replace", fail_replace)
    with pytest.raises(OSError):
        save_export(file, destination)
    assert destination.read_bytes() == b"previous" and file.closed
    assert not list(tmp_path.glob("*.tmp"))
    file = io.BytesIO(b"x" * 100000)
    stream = read_chunks(file)
    assert len(next(stream)) == 65536
    stream.close()
    assert file.closed


async def test_cli_publishes_manual_csv(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import cli

    await seed_product(factory)
    monkeypatch.setattr(cli, "async_session_factory", factory)
    destination = tmp_path / "exports" / "manual_catalog_additions.csv"
    await cli._export_manual(destination)
    assert csv_rows(destination.read_bytes())[0]["barcode"] == "00001111"
    assert not list(destination.parent.glob("*.tmp"))
