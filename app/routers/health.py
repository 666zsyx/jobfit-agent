# 提供服务和容器健康检查接口。

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.services.readiness import collect_readiness


router = APIRouter(tags=["health"])


# 返回服务存活状态，供本地和容器健康检查使用。
@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# 返回依赖就绪状态，供负载均衡和部署平台使用。
@router.get("/ready")
async def ready() -> JSONResponse:
    payload = await collect_readiness()
    status_code = (
        status.HTTP_200_OK
        if payload["status"] == "ready"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=status_code, content=payload)
