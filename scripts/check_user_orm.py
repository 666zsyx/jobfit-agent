# 验证 User ORM 映射和未提交数据会被事务回滚。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import User
from app.db.session import async_session_factory, dispose_engine


async def check_user_orm() -> None:
    unique_suffix = uuid4().hex
    username = f"orm_test_{unique_suffix}"
    email = f"{username}@example.com"

    try:
        async with async_session_factory() as session:
            user = User(
                username=username,
                email=email,
            )
            session.add(user)

            try:
                await session.flush()

                table_name = (
                    f"{User.__table__.schema}.{User.__table__.name}"
                )
                print(f"table={table_name}")
                print(f"assigned_id={user.user_id}")

                await session.rollback()

                result = await session.execute(
                    select(User).where(User.username == username)
                )
                persisted_user = result.scalar_one_or_none()
                print(f"after_rollback={persisted_user}")
            except Exception:
                await session.rollback()
                raise
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_user_orm())
