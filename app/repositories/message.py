# 提供按用户隔离的会话消息数据访问。

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message
from app.repositories.conversation import ConversationRepository


class MessageRepository:
    """消息 Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_user(
        self,
        conversation_id: int,
        user_id: int,
        limit: int = 100,
    ) -> list[Message]:
        statement = (
            select(Message)
            .join(
                Conversation,
                Message.conversation_id
                == Conversation.conversation_id,
            )
            .where(
                Message.conversation_id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(Message.sequence_no)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())


    async def list_recent_for_user(
        self,
        conversation_id: int,
        user_id: int,
        limit: int = 20,
    ) -> list[Message]:
        """按时间顺序返回最近若干条消息。"""

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        statement = (
            select(Message)
            .join(
                Conversation,
                Message.conversation_id
                == Conversation.conversation_id,
            )
            .where(
                Message.conversation_id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(Message.sequence_no.desc())
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        messages = list(result.all())
        messages.reverse()
        return messages
    async def create_for_user(
        self,
        conversation_id: int,
        user_id: int,
        role: str,
        content: str,
        message_metadata: dict | None = None,
    ) -> Message:
        conversation_repository = ConversationRepository(self.session)
        conversation = await conversation_repository.get_for_user(
            conversation_id=conversation_id,
            user_id=user_id,
            for_update=True,
        )

        if conversation is None:
            raise LookupError("会话不存在或无权访问")

        next_sequence_statement = select(
            func.coalesce(func.max(Message.sequence_no), 0) + 1
        ).where(Message.conversation_id == conversation_id)
        sequence_no = await self.session.scalar(
            next_sequence_statement
        )

        message = Message(
            conversation_id=conversation_id,
            sequence_no=sequence_no,
            role=role,
            content=content,
            message_metadata=message_metadata,
        )
        self.session.add(message)
        await self.session.flush()
        return message
