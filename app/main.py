"""FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin_router, auth_router, scans_router, transactions_router
from app.config import settings
from app.database import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """释放连接池；数据库升级由 Alembic 独立负责。"""

    yield
    await engine.dispose()


app = FastAPI(
    title="实体游戏库存管理系统",
    version="0.1.0",
    lifespan=lifespan,
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(scans_router)
app.include_router(auth_router)
app.include_router(transactions_router)
app.include_router(admin_router)


@app.get("/", include_in_schema=False)
async def scanner_page() -> FileResponse:
    """提供手机端连续扫码应用外壳。"""

    return FileResponse(STATIC_DIR / "index.html")


@app.get("/service-worker.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    """从站点根路径提供 Service Worker，使其可以控制扫码首页。"""

    return FileResponse(
        STATIC_DIR / "service-worker.js",
        media_type="text/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """供开发环境及未来部署健康检查使用。"""

    return {"status": "ok", "environment": settings.app_env}
