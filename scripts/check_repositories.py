# 验证用户、简历和简历版本 Repository 的隔离与软删除边界。

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import (
    ResumeRepository,
    ResumeVersionRepository,
    UserRepository,
)


async def check_repositories() -> None:
    suffix = uuid4().hex
    username1 = f"repo_user1_{suffix}"
    username2 = f"repo_user2_{suffix}"

    try:
        async with async_session_factory() as session:
            try:
                user_repository = UserRepository(session)
                resume_repository = ResumeRepository(session)
                version_repository = ResumeVersionRepository(session)

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

                assert await user_repository.get_by_id(
                    user1.user_id
                ) is not None
                assert await user_repository.get_by_username(
                    username1
                ) is not None
                print("user1_repo_ok")

                resume1 = await resume_repository.create(
                    user_id=user1.user_id,
                    title="User 1 Resume",
                )
                await resume_repository.create(
                    user_id=user2.user_id,
                    title="User 2 Resume",
                )

                version1 = await version_repository.create_for_user(
                    resume_id=resume1.resume_id,
                    user_id=user1.user_id,
                    version_no=1,
                    raw_text="User 1 resume version 1",
                    extracted_sections={"sections": []},
                )
                await version_repository.create_for_user(
                    resume_id=resume1.resume_id,
                    user_id=user1.user_id,
                    version_no=2,
                    raw_text="User 1 resume version 2",
                    extracted_sections={"sections": []},
                )

                loaded_resume = await resume_repository.get_for_user(
                    resume_id=resume1.resume_id,
                    user_id=user1.user_id,
                    with_versions=True,
                )
                if loaded_resume is None:
                    raise AssertionError("用户 1 无法读取自己的简历")

                if len(loaded_resume.versions) != 2:
                    raise AssertionError("简历版本数量不正确")

                user1_resumes = await resume_repository.list_for_user(
                    user_id=user1.user_id,
                )
                if len(user1_resumes) != 1:
                    raise AssertionError("用户 1 简历列表不正确")

                other_resume = await resume_repository.get_for_user(
                    resume_id=resume1.resume_id,
                    user_id=user2.user_id,
                )
                if other_resume is not None:
                    raise AssertionError("跨用户简历隔离失败")
                print("user2_resume_isolation_ok")

                other_version = await version_repository.get_for_user(
                    resume_version_id=version1.resume_version_id,
                    user_id=user2.user_id,
                )
                if other_version is not None:
                    raise AssertionError("跨用户版本隔离失败")
                print("user2_version_isolation_ok")

                try:
                    await version_repository.create_for_user(
                        resume_id=resume1.resume_id,
                        user_id=user2.user_id,
                        version_no=3,
                        raw_text="Cross-user version",
                    )
                except LookupError:
                    print("cross_user_create_rejected")
                else:
                    raise AssertionError("跨用户创建版本未被拒绝")

                resume1.deleted_at = datetime.now(timezone.utc)
                await session.flush()

                hidden_resume = await resume_repository.get_for_user(
                    resume_id=resume1.resume_id,
                    user_id=user1.user_id,
                )
                if hidden_resume is not None:
                    raise AssertionError("软删除简历仍然可见")
                print("soft_delete_hidden")

                try:
                    await version_repository.create_for_user(
                        resume_id=resume1.resume_id,
                        user_id=user1.user_id,
                        version_no=3,
                        raw_text="Version for deleted resume",
                    )
                except LookupError:
                    print("soft_deleted_parent_rejected")
                else:
                    raise AssertionError("软删除简历仍可创建版本")

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
    asyncio.run(check_repositories())
