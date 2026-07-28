"""手机连续扫码应用外壳契约测试。"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

STATIC_DIR = Path(__file__).resolve().parents[1] / "app/static"


def test_scanner_page_and_pwa_assets_are_served() -> None:
    with TestClient(app) as client:
        page = client.get("/")
        manifest = client.get("/static/manifest.webmanifest")
        service_worker = client.get("/service-worker.js")

    assert page.status_code == 200
    assert "连续入库" in page.text
    assert "连续出库" in page.text
    assert manifest.status_code == 200
    assert manifest.json()["display"] == "standalone"
    assert service_worker.status_code == 200
    assert service_worker.headers["service-worker-allowed"] == "/"
    assert service_worker.headers["cache-control"] == "no-cache"


def test_service_worker_explicitly_excludes_api_from_cache() -> None:
    source = (STATIC_DIR / "service-worker.js").read_text(encoding="utf-8")

    assert 'url.pathname.startsWith("/api/")' in source
    assert 'request.method !== "GET"' in source


def test_scanner_supports_hid_terminators_and_string_barcode_validation() -> None:
    source = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'event.key === "Enter" || event.key === "Tab"' in source
    assert "/^[0-9]{8,14}$/" in source
    assert "parseInt" not in source
    assert 'fetch("/api/scans"' in source
    assert "/api/inventory/scans" not in source
