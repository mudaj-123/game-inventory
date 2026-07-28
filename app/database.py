"""SQLAlchemy 异步数据库基础设施。"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """所有业务数据库模型的声明式基类。"""


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """为每个请求提供独立事务会话，并确保请求结束后关闭。"""

    async with async_session_factory() as session:
        yield session
