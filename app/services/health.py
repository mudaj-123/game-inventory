"""数据库健康探测服务。"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def database_is_healthy(session: AsyncSession) -> bool:
    """执行轻量查询，确认应用使用的数据库连接确实可用。"""

    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # 数据库驱动异常类型因后端而异，健康端点统一降级。
        logger.exception("Database health query failed")
        return False
    return True
