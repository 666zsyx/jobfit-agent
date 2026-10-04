# 验证服务重启后会清理遗留 running 任务。

import asyncio

from app.services.analysis_results import recover_stale_running_tasks


def test_recover_stale_running_tasks():
    class FakeResult:
        def all(self):
            return [1, 2, 3]

    class FakeSession:
        async def scalars(self, statement):
            return FakeResult()

    recovered = asyncio.run(
        recover_stale_running_tasks(FakeSession())
    )

    assert recovered == 3
