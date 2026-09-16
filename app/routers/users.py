from fastapi import APIRouter, Depends

from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me")
async def get_me(
    user: CurrentUser = Depends(get_current_user),
):
    return success_response(data=user)