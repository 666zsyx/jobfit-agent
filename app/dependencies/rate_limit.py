# 提供 FastAPI 限流和配额依赖。

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends

from app.cache.client import get_redis_client
from app.dependencies.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.services.rate_limit import enforce_api_limits


def make_rate_limit_dependency(scope: str) -> Callable:
    async def dependency(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> None:
        await enforce_api_limits(
            get_redis_client(),
            user_id=current_user.id,
            scope=scope,
        )

    return dependency


__all__ = ["make_rate_limit_dependency"]
