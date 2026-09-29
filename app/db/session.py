# 创建异步数据库 Engine 和 Session 工厂。

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def dispose_engine() -> None:
    """关闭连接池中的所有连接。"""

    await engine.dispose()
