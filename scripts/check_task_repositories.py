# 验证任务、岗位、会话和消息 Repository 的用户隔离与事务边界。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import (
    AnalysisTaskRepository,
    ConversationRepository,
    JobRepository,
    MessageRepository,
    ResumeRepository,
    ResumeVersionRepository,
    UserRepository,
)
from app.services.analysis_tasks import create_analysis_task


async def check_task_repositories() -> None:
    suffix = uuid4().hex
    username1 = f"task_user1_{suffix}"
    username2 = f"task_user2_{suffix}"

    try:
        async with async_session_factory() as session:
            try:
                user_repository = UserRepository(session)
                resume_repository = ResumeRepository(session)
                version_repository = ResumeVersionRepository(session)
                job_repository = JobRepository(session)
                conversation_repository = ConversationRepository(session)
                message_repository = MessageRepository(session)
                task_repository = AnalysisTaskRepository(session)

                user1 = User(
                    username=username1,
                    email=f"{username1}@example.com",
                )
                user2 = User(
                    username=username2,
                    email=f"{username2}@example.com",
                )
                session.add_all([user1, user2])
                await session.flush()

                resume1 = await resume_repository.create(
                    user_id=user1.user_id,
                    title="User 1 Resume",
                )
                resume2 = await resume_repository.create(
                    user_id=user2.user_id,
                    title="User 2 Resume",
                )
                version1 = await version_repository.create_for_user(
                    resume_id=resume1.resume_id,
                    user_id=user1.user_id,
                    version_no=1,
                    raw_text="User 1 resume text",
                    extracted_sections={"sections": []},
                )
                version2 = await version_repository.create_for_user(
                    resume_id=resume2.resume_id,
                    user_id=user2.user_id,
                    version_no=1,
                    raw_text="User 2 resume text",
                    extracted_sections={"sections": []},
                )

                job1 = await job_repository.create(
                    user_id=user1.user_id,
                    raw_description="User 1 job",
                    title="Backend",
                )
                job2 = await job_repository.create(
                    user_id=user2.user_id,
                    raw_description="User 2 job",
                    title="Frontend",
                )
                conversation1 = await conversation_repository.create(
                    user_id=user1.user_id,
                    title="User 1 conversation",
                )
                conversation2 = await conversation_repository.create(
                    user_id=user2.user_id,
                    title="User 2 conversation",
                )

                task = await create_analysis_task(
                    session,
                    user_id=user1.user_id,
                    job_id=job1.job_id,
                    resume_version_id=version1.resume_version_id,
                    conversation_id=conversation1.conversation_id,
                )
                if (
                    task.status != "pending"
                    or task.current_step != 0
                    or task.attempt != 0
                ):
                    raise AssertionError("任务初始状态不正确")

                loaded_task = await task_repository.get_for_user(
                    task_id=task.task_id,
                    user_id=user1.user_id,
                )
                if loaded_task is None:
                    raise AssertionError("用户 1 无法读取自己的任务")
                print("task_create_ok")

                message1 = await message_repository.create_for_user(
                    conversation_id=conversation1.conversation_id,
                    user_id=user1.user_id,
                    role="user",
                    content="Analyze this job.",
                )
                message2 = await message_repository.create_for_user(
                    conversation_id=conversation1.conversation_id,
                    user_id=user1.user_id,
                    role="assistant",
                    content="I will analyze it.",
                )
                if [message1.sequence_no, message2.sequence_no] != [1, 2]:
                    raise AssertionError("消息 sequence_no 不正确")
                print("message_sequence_ok")

                other_messages = await message_repository.list_for_user(
                    conversation_id=conversation1.conversation_id,
                    user_id=user2.user_id,
                )
                if other_messages:
                    raise AssertionError("跨用户消息隔离失败")
                print("message_isolation_ok")

                try:
                    await create_analysis_task(
                        session,
                        user_id=user1.user_id,
                        job_id=job2.job_id,
                        resume_version_id=version1.resume_version_id,
                        conversation_id=conversation1.conversation_id,
                    )
                except LookupError:
                    print("cross_user_job_rejected")
                else:
                    raise AssertionError("跨用户岗位未被拒绝")

                try:
                    await create_analysis_task(
                        session,
                        user_id=user1.user_id,
                        job_id=job1.job_id,
                        resume_version_id=version2.resume_version_id,
                        conversation_id=conversation1.conversation_id,
                    )
                except LookupError:
                    print("cross_user_resume_version_rejected")
                else:
                    raise AssertionError("跨用户简历版本未被拒绝")

                try:
                    await create_analysis_task(
                        session,
                        user_id=user1.user_id,
                        job_id=job1.job_id,
                        resume_version_id=version1.resume_version_id,
                        conversation_id=conversation2.conversation_id,
                    )
                except LookupError:
                    print("cross_user_conversation_rejected")
                else:
                    raise AssertionError("跨用户会话未被拒绝")

                await session.rollback()

                cleaned_user = await user_repository.get_by_username(
                    username1
                )
                if cleaned_user is not None:
                    raise AssertionError("测试用户未随事务回滚")
                print("rollback_cleanup_ok")
            except Exception:
                await session.rollback()
                raise
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_task_repositories())
