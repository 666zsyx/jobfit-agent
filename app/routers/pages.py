# 提供同源静态工作台页面。

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse


STATIC_DIRECTORY = Path(__file__).resolve().parent.parent / "static"
router = APIRouter(include_in_schema=False)


@router.get("/")
async def root_page() -> RedirectResponse:
    """将根路径跳转到演示工作台。"""

    return RedirectResponse(url="/app")


@router.get("/app")
async def app_page() -> FileResponse:
    """返回 JobFit Agent 静态工作台。"""

    return FileResponse(STATIC_DIRECTORY / "index.html")


__all__ = ["STATIC_DIRECTORY", "router"]
