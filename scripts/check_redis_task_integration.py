# 验证 Redis 任务状态缓存和运行锁与数据库任务集成。

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.cache.client import get_redis_client
from app.cache.task_state import (
    get_cached_task_status,
    invalidate_task_status,
)
from app.core.exceptions import TaskStateConflictError
from app.db.models import AnalysisTask, Job, Report, Resume, ResumeVersion, User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import (
    JobRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from app.schemas.chat import LLMWithToolsResult, TokenUsage, ToolCall
from app.services import react_agent
from app.services.persisted_agent import (
    create_persisted_task,
    run_persisted_task,
)


def usage(prompt_tokens: int, completion_tokens: int) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


async def cleanup_test_data(usernames: list[str]) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            user_ids = select(User.user_id).where(
                User.username.in_(usernames)
            )
            task_ids = select(AnalysisTask.task_id).where(
                AnalysisTask.user_id.in_(user_ids)
            )
            resume_ids = select(Resume.resume_id).where(
                Resume.user_id.in_(user_ids)
            )
            await session.execute(
                delete(Report).where(Report.task_id.in_(task_ids))
            )
            await session.execute(
                delete(AnalysisTask).where(
                    AnalysisTask.user_id.in_(user_ids)
                )
            )
            await session.execute(
                delete(ResumeVersion).where(
                    ResumeVersion.resume_id.in_(resume_ids)
                )
            )
            await session.execute(
                delete(Resume).where(Resume.user_id.in_(user_ids))
            )
            await session.execute(
                delete(Job).where(Job.user_id.in_(user_ids))
            )
            await session.execute(
                delete(User).where(User.user_id.in_(user_ids))
            )

async def check_redis_task_integration() -> None:
    suffix = uuid4().hex
    username1 = f"redis_task_user1_{suffix}"
    username2 = f"redis_task_user2_{suffix}"
    redis = get_redis_client()
    model_call_count = 0
    lock_conflict_rejected = False

    async def fake_chat_with_tools(*, messages, tools):
        nonlocal model_call_count
        nonlocal lock_conflict_rejected
        model_call_count += 1

        if model_call_count == 1:
            cached = await get_cached_task_status(
                redis,
                user_id=user1_id,
                task_id=task_id,
            )
            if cached is None or cached["status"] != "running":
                raise AssertionError("模型开始时未看到 running 缓存")
            print("running_cache_ok")

            try:
                await run_persisted_task(
                    async_session_factory,
                    user_id=user1_id,
                    task_id=task_id,
                    redis_client=redis,
                )
            except TaskStateConflictError:
                lock_conflict_rejected = True
            else:
                raise AssertionError("并发执行未被运行锁拒绝")

            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="redis-task-report",
                        name="save_match_report",
                        arguments=json.dumps(
                            {
                                "summary": "Redis integration report",
                                "result_json": {"status": "completed"},
                            }
                        ),
                    )
                ],
                usage=usage(10, 2),
                latency_ms=10,
            )

        return LLMWithToolsResult(
            content="Redis integration completed.",
            tool_calls=[],
            usage=usage(20, 5),
            latency_ms=12,
        )

    original_chat_with_tools = react_agent.chat_with_tools

    try:
        async with async_session_factory() as session:
            async with session.begin():
                user1 = User(
                    username=username1,
                    email=f"{username1}@example.com",
                    role="user",
                )
                user2 = User(
                    username=username2,
                    email=f"{username2}@example.com",
                    role="user",
                )
                session.add_all([user1, user2])
                await session.flush()

                resume = await ResumeRepository(session).create(
                    user_id=user1.user_id,
                    title="Redis Integration Resume",
                )
                resume_version = await ResumeVersionRepository(
                    session
                ).create_for_user(
                    resume_id=resume.resume_id,
                    user_id=user1.user_id,
                    version_no=1,
                    raw_text="Python FastAPI resume",
                )
                job = await JobRepository(session).create(
                    user_id=user1.user_id,
                    raw_description="Python FastAPI role",
                    title="Backend",
                )
                task = await create_persisted_task(
                    session,
                    user_id=user1.user_id,
                    job_id=job.job_id,
                    resume_version_id=resume_version.resume_version_id,
                    conversation_id=None,
                )
                user1_id = user1.user_id
                user2_id = user2.user_id
                task_id = task.task_id

        react_agent.chat_with_tools = fake_chat_with_tools

        result = await run_persisted_task(
            async_session_factory,
            user_id=user1_id,
            task_id=task_id,
            redis_client=redis,
        )

        if result.status != "completed":
            raise AssertionError("Redis 集成任务未完成")

        if not lock_conflict_rejected:
            raise AssertionError("未验证运行锁冲突")
        print("run_lock_conflict_rejected")

        completed = await get_cached_task_status(
            redis,
            user_id=user1_id,
            task_id=task_id,
        )
        if (
            completed is None
            or completed["status"] != "completed"
            or completed["max_steps"] != 8
        ):
            raise AssertionError("completed 缓存不正确")
        print("completed_cache_ok")

        lock_key = f"jobfit:task:{task_id}:run_lock"
        if await redis.exists(lock_key):
            raise AssertionError("运行锁未释放")
        print("run_lock_released")

        if await get_cached_task_status(
            redis,
            user_id=user2_id,
            task_id=task_id,
        ) is not None:
            raise AssertionError("缓存用户隔离失败")
        print("cache_user_isolation_ok")

        ttl = await redis.ttl(
            f"jobfit:user:{user1_id}:task:{task_id}:status"
        )
        if ttl <= 0:
            raise AssertionError("completed 缓存 TTL 不存在")
        print("redis_task_integration_ok")
    finally:
        react_agent.chat_with_tools = original_chat_with_tools
        try:
            if "user1_id" in locals() and "task_id" in locals():
                await invalidate_task_status(
                    redis,
                    user_id=user1_id,
                    task_id=task_id,
                )
                await redis.delete(
                    f"jobfit:task:{task_id}:run_lock"
                )
            await cleanup_test_data([username1, username2])
        finally:
            await redis.aclose()
            await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_redis_task_integration())