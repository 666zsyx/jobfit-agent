# 提供服务和容器健康检查接口。

from fastapi import APIRouter

router = APIRouter(tags=["health"])


# 返回服务存活状态，供本地和容器健康检查使用。
@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}