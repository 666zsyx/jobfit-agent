# 创建演示鉴权所需的固定开发用户。

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import UserRepository


async def seed_dev_user() -> None:
    try:
        async with async_session_factory() as session:
            async with session.begin():
                repository = UserRepository(session)
                existing = await repository.get_by_id(1)

                if existing is not None:
                    print("existing")
                    return

                session.add(
                    User(
                        user_id=1,
                        username="demo_user",
                        email="demo_user@example.com",
                        role="admin",
                        status="active",
                    )
                )
                await session.flush()
                print("created")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed_dev_user())
