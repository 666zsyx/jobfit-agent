from collections.abc import AsyncIterator
from time import perf_counter

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from app.core.config import settings
from app.core.exceptions import LLMServiceError
from app.schemas.chat import ChatResult, LLMStreamEvent, TokenUsage


# 创建客户端
client = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    timeout=60.0,
    max_retries=1,
)


async def _chat(
    messages: list[dict[str, str]],
    response_format: dict[str, str] | None = None,
) -> ChatResult:
    try:
        start = perf_counter()
        if response_format is None:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
            )
        else:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                response_format=response_format,
            )
        latency_ms = round((perf_counter() - start) * 1000)
    except AuthenticationError as exc:
        # 认证失败属于服务端配置或上游认证问题
        raise LLMServiceError(
            message="LLM 服务认证失败，请检查服务配置。",
            status_code=500,
        ) from exc
    except RateLimitError as exc:
        # 频率限制：请求太快或额度用完，映射为 503
        raise LLMServiceError(
            message="LLM 请求频率超限，请稍后重试。",
            status_code=503,
        ) from exc
    except APITimeoutError as exc:
        # 超时：连接或读取超时，映射为 504
        raise LLMServiceError(
            message="LLM 请求超时，请检查网络或稍后重试。",
            status_code=504,
        ) from exc
    except APIConnectionError as exc:
        # 连接错误：网络故障或无法访问服务，映射为 502
        raise LLMServiceError(
            message="无法连接到 LLM 服务，请检查网络。",
            status_code=502,
        ) from exc
    except BadRequestError as exc:
        # 错误请求：通常是因为 messages 格式错误或上下文超限，映射为 500
        raise LLMServiceError(
            message="LLM 请求参数错误，可能上下文超限或格式不对。",
            status_code=500,
        ) from exc
    except APIStatusError as exc:
        # 其他状态码异常，映射为 502
        raise LLMServiceError(
            message="LLM 服务返回异常状态，请稍后重试。",
            status_code=502,
        ) from exc
    else:
        text = response.choices[0].message.content
        usage = response.usage

        if usage is None:
            raise LLMServiceError("模型响应中没有 usage。")
        if text is None:
            raise LLMServiceError("模型没有返回内容。")

        return ChatResult(
            answer=text,
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            ),
            latency_ms=latency_ms,
        )


async def chat(messages: list[dict[str, str]]) -> ChatResult:
    return await _chat(messages=messages)


async def chat_json(
    messages: list[dict[str, str]],
) -> ChatResult:
    return await _chat(
        messages=messages,
        response_format={"type": "json_object"},
    )


async def stream_chat(
    messages: list[dict[str, str]],
) -> AsyncIterator[LLMStreamEvent]:
    try:
        start = perf_counter()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        usage = None

        async for chunk in response:
            if chunk.usage is not None:
                usage = chunk.usage

            if not chunk.choices:
                continue

            piece = chunk.choices[0].delta.content
            if piece:
                yield LLMStreamEvent(
                    type="content",
                    content=piece,
                )

        if usage is None:
            raise LLMServiceError("模型响应中没有 usage。")

        latency_ms = round((perf_counter() - start) * 1000)

        yield LLMStreamEvent(
            type="usage",
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            ),
            latency_ms=latency_ms,
        )
    except AuthenticationError as exc:
        # 认证失败属于服务端配置或上游认证问题
        raise LLMServiceError(
            message="LLM 服务认证失败，请检查服务配置。",
            status_code=500,
        ) from exc
    except RateLimitError as exc:
        # 频率限制：请求太快或额度用完，映射为 503
        raise LLMServiceError(
            message="LLM 请求频率超限，请稍后重试。",
            status_code=503,
        ) from exc
    except APITimeoutError as exc:
        # 超时：连接或读取超时，映射为 504
        raise LLMServiceError(
            message="LLM 请求超时，请检查网络或稍后重试。",
            status_code=504,
        ) from exc
    except APIConnectionError as exc:
        # 连接错误：网络故障或无法访问服务，映射为 502
        raise LLMServiceError(
            message="无法连接到 LLM 服务，请检查网络。",
            status_code=502,
        ) from exc
    except BadRequestError as exc:
        # 错误请求：通常是因为 messages 格式错误或上下文超限，映射为 500
        raise LLMServiceError(
            message="LLM 请求参数错误，可能上下文超限或格式不对。",
            status_code=500,
        ) from exc
    except APIStatusError as exc:
        # 其他状态码异常，映射为 502
        raise LLMServiceError(
            message="LLM 服务返回异常状态，请稍后重试。",
            status_code=502,
        ) from exc
