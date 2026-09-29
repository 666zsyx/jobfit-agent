# 提供按用户隔离的会话数据访问。

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation


class ConversationRepository:
    """会话 Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_user(
        self,
        conversation_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.conversation_id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )

        if for_update:
            statement = statement.with_for_update()

        return await self.session.scalar(statement)

    async def create(
        self,
        user_id: int,
        title: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            title=title,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation
