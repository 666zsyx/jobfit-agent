# 创建分析任务，并在同一事务中验证资源归属。

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisTask
from app.repositories import (
    AnalysisTaskRepository,
    ConversationRepository,
    JobRepository,
    ResumeVersionRepository,
    UserRepository,
)


async def create_analysis_task(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    resume_version_id: int,
    conversation_id: int | None = None,
    max_steps: int = 8,
) -> AnalysisTask:
    """锁定并验证全部资源后，创建 pending 分析任务。"""

    user_repository = UserRepository(session)
    job_repository = JobRepository(session)
    resume_version_repository = ResumeVersionRepository(session)
    conversation_repository = ConversationRepository(session)
    task_repository = AnalysisTaskRepository(session)

    user = await user_repository.get_by_id(
        user_id=user_id,
        for_update=True,
    )
    if user is None:
        raise LookupError("资源不存在或无权访问")

    job = await job_repository.get_for_user(
        job_id=job_id,
        user_id=user_id,
        for_update=True,
    )
    if job is None:
        raise LookupError("资源不存在或无权访问")

    resume_version = await resume_version_repository.get_for_user(
        resume_version_id=resume_version_id,
        user_id=user_id,
        for_update=True,
    )
    if resume_version is None:
        raise LookupError("资源不存在或无权访问")

    if conversation_id is not None:
        conversation = await conversation_repository.get_for_user(
            conversation_id=conversation_id,
            user_id=user_id,
            for_update=True,
        )
        if conversation is None:
            raise LookupError("资源不存在或无权访问")

    return await task_repository.create(
        user_id=user_id,
        job_id=job_id,
        resume_version_id=resume_version_id,
        conversation_id=conversation_id,
        max_steps=max_steps,
    )
