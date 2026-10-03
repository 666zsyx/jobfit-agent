# 统计模型 Usage 并计算估算成本。

from __future__ import annotations

import os
from contextvars import ContextVar, Token
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.chat import TokenUsage


UsageCallType = Literal[
    "chat",
    "chat_json",
    "chat_with_tools",
    "stream_chat",
]


class UsageRecord(BaseModel):
    """一次模型调用的 Usage 记录。"""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    call_type: UsageCallType
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_total(self):
        expected = self.prompt_tokens + self.completion_tokens
        if self.total_tokens != expected:
            raise ValueError(
                "total_tokens 必须等于 prompt_tokens + completion_tokens"
            )
        return self


class ModelUsageAggregate(BaseModel):
    calls: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost: float = Field(default=0.0, ge=0)


class CostSummary(BaseModel):
    currency: str = "USD"
    calls: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost: float = Field(default=0.0, ge=0)
    by_model: dict[str, ModelUsageAggregate] = Field(default_factory=dict)


_USAGE_RECORDS: ContextVar[list[UsageRecord] | None] = ContextVar(
    "usage_records",
    default=None,
)


def start_usage_collection() -> Token:
    return _USAGE_RECORDS.set([])


def finish_usage_collection(token: Token) -> list[UsageRecord]:
    records = _USAGE_RECORDS.get() or []
    _USAGE_RECORDS.reset(token)
    return list(records)


def record_usage(
    *,
    model: str,
    call_type: UsageCallType,
    usage: TokenUsage,
    latency_ms: int,
) -> None:
    records = _USAGE_RECORDS.get()
    if records is None:
        return

    records.append(
        UsageRecord(
            model=model,
            call_type=call_type,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=max(latency_ms, 0),
        )
    )


def _env_float(name: str, default: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc
    if value < 0:
        raise ValueError(f"{name} 不能小于 0")
    return value


def get_model_pricing() -> tuple[float, float, str]:
    """从环境变量读取每 100 万 Token 的价格。"""

    input_price = _env_float("LLM_INPUT_PRICE_PER_1M", 0.0)
    output_price = _env_float("LLM_OUTPUT_PRICE_PER_1M", 0.0)
    currency = os.getenv("COST_CURRENCY", "USD").strip() or "USD"
    return input_price, output_price, currency


def summarize_usage_cost(
    records: list[UsageRecord],
    *,
    input_price_per_1m: float | None = None,
    output_price_per_1m: float | None = None,
    currency: str | None = None,
) -> CostSummary:
    """按模型聚合 Usage 并计算估算成本。"""

    env_input, env_output, env_currency = get_model_pricing()
    input_price = (
        env_input
        if input_price_per_1m is None
        else input_price_per_1m
    )
    output_price = (
        env_output
        if output_price_per_1m is None
        else output_price_per_1m
    )
    resolved_currency = currency or env_currency

    if input_price < 0 or output_price < 0:
        raise ValueError("模型价格不能小于 0")

    by_model: dict[str, ModelUsageAggregate] = {}
    for record in records:
        aggregate = by_model.get(
            record.model,
            ModelUsageAggregate(),
        )
        cost = (
            record.prompt_tokens / 1_000_000 * input_price
            + record.completion_tokens / 1_000_000 * output_price
        )
        by_model[record.model] = ModelUsageAggregate(
            calls=aggregate.calls + 1,
            prompt_tokens=(
                aggregate.prompt_tokens + record.prompt_tokens
            ),
            completion_tokens=(
                aggregate.completion_tokens + record.completion_tokens
            ),
            total_tokens=(
                aggregate.total_tokens + record.total_tokens
            ),
            estimated_cost=round(
                aggregate.estimated_cost + cost,
                8,
            ),
        )

    return CostSummary(
        currency=resolved_currency,
        calls=sum(item.calls for item in by_model.values()),
        prompt_tokens=sum(
            item.prompt_tokens for item in by_model.values()
        ),
        completion_tokens=sum(
            item.completion_tokens for item in by_model.values()
        ),
        total_tokens=sum(
            item.total_tokens for item in by_model.values()
        ),
        estimated_cost=round(
            sum(item.estimated_cost for item in by_model.values()),
            8,
        ),
        by_model=by_model,
    )


__all__ = [
    "CostSummary",
    "ModelUsageAggregate",
    "UsageCallType",
    "UsageRecord",
    "finish_usage_collection",
    "get_model_pricing",
    "record_usage",
    "start_usage_collection",
    "summarize_usage_cost",
]
