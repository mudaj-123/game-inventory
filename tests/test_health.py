"""应用入口的最小契约测试（安装开发依赖后运行）。"""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "development"}


def test_health_check_reports_database_failure(monkeypatch) -> None:
    """数据库不可用时返回 503，响应中不包含凭据。"""

    from app.database import get_db_session

    async def broken_session():
        class BrokenSession:
            async def execute(self, _statement):
                raise RuntimeError("database offline")

        yield BrokenSession()

    app.dependency_overrides[get_db_session] = broken_session
    try:
        with TestClient(app) as client:
            response = client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "environment": "development",
        "database": "unavailable",
    }
