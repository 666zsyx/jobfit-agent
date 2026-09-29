# 提供用户数据访问和软删除过滤。

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:
    """用户 Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(
        self,
        user_id: int,
        for_update: bool = False,
    ) -> User | None:
        statement = select(User).where(
            User.user_id == user_id,
            User.deleted_at.is_(None),
        )

        if for_update:
            statement = statement.with_for_update()

        return await self.session.scalar(statement)

    async def get_by_username(
        self,
        username: str,
    ) -> User | None:
        statement = select(User).where(
            User.username == username,
            User.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

