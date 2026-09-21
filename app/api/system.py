"""系统状态 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db_session
from app.services.health import database_is_healthy

router = APIRouter(tags=["system"])


@router.get("/health")
async def health_check(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    """同时检查 Web 进程和数据库，且不暴露连接信息。"""

    if not await database_is_healthy(session):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "environment": settings.app_env, "database": "unavailable"}
    return {"status": "ok", "environment": settings.app_env}
