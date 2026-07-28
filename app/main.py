"""FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """供开发环境及未来部署健康检查使用。"""

    return {"status": "ok", "environment": settings.app_env}
