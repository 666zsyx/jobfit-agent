# 验证 JobFit Agent 是否能够通过 SQLAlchemy 异步连接 PostgreSQL。

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings


async def check_database_connection() -> None:
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT
                        current_user AS db_user,
                        current_database() AS db_name,
                        version() AS pg_version
                    """
                )
            )
            row = result.one()

            print("database connection ok")
            print(f"user={row.db_user}")
            print(f"database={row.db_name}")
            print(f"postgresql={row.pg_version}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_database_connection())

