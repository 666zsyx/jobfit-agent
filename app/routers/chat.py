# 提供普通聊天和 SSE 流式聊天接口。

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.exceptions import LLMServiceError
from app.cache.client import get_redis_client
from app.core.response import success_response
from app.dependencies.rate_limit import make_rate_limit_dependency
from app.dependencies.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.chat import ChatRequest
from app.services.llm import chat as llm_chat
from app.services.llm import stream_chat as llm_stream_chat
from app.services.rate_limit import record_daily_token_usage

router = APIRouter(prefix="/api", tags=["chat"])


# 处理非流式聊天请求，并返回模型结果和 Usage。
@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("chat")
    ),
) -> dict:
    message_dicts = [
        message.model_dump()
        for message in request.messages
    ]
    result = await llm_chat(message_dicts)
    await record_daily_token_usage(
        get_redis_client(),
        user_id=current_user.id,
        total_tokens=result.usage.total_tokens,
    )
    return success_response(data=result)


# 把 LLM 事件转换成 SSE 流返回客户端。
@router.post("/chat/stream")
async def stream_chat_endpoint(
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("chat_stream")
    ),
) -> StreamingResponse:
    message_dicts = [
        message.model_dump()
        for message in request.messages
    ]

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in llm_stream_chat(message_dicts):
                if event.type == "usage" and event.usage is not None:
                    await record_daily_token_usage(
                        get_redis_client(),
                        user_id=current_user.id,
                        total_tokens=event.usage.total_tokens,
                    )
                payload = event.model_dump(exclude_none=True)
                data = json.dumps(payload, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except LLMServiceError as exc:
            error_data = {
                "type": "error",
                "message": exc.message,
            }
            data = json.dumps(error_data, ensure_ascii=False)
            yield f"data: {data}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )