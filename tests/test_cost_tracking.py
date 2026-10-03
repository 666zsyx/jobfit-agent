# 验证 Usage 收集和成本计算。

import pytest

from app.core.cost_tracking import (
    UsageRecord,
    finish_usage_collection,
    record_usage,
    start_usage_collection,
    summarize_usage_cost,
)
from app.core.observability import build_task_metrics
from app.schemas.chat import TokenUsage


def make_usage(prompt: int, completion: int) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


def test_usage_collection_records_only_inside_context() -> None:
    record_usage(
        model="outside",
        call_type="chat",
        usage=make_usage(1, 1),
        latency_ms=1,
    )

    token = start_usage_collection()
    record_usage(
        model="test-model",
        call_type="chat_with_tools",
        usage=make_usage(10, 5),
        latency_ms=20,
    )
    records = finish_usage_collection(token)

    assert len(records) == 1
    assert records[0].model == "test-model"
    assert records[0].total_tokens == 15


def test_summarize_usage_cost_calculates_expected_amount() -> None:
    records = [
        UsageRecord(
            model="test-model",
            call_type="chat",
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
            total_tokens=1_500_000,
            latency_ms=10,
        )
    ]
    summary = summarize_usage_cost(
        records,
        input_price_per_1m=2.0,
        output_price_per_1m=4.0,
        currency="USD",
    )

    assert summary.total_tokens == 1_500_000
    assert summary.estimated_cost == 4.0
    assert summary.currency == "USD"


def test_summarize_usage_by_model() -> None:
    records = [
        UsageRecord(
            model="model-a",
            call_type="chat",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=1,
        ),
        UsageRecord(
            model="model-a",
            call_type="chat_json",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            latency_ms=2,
        ),
        UsageRecord(
            model="model-b",
            call_type="chat_with_tools",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
            latency_ms=3,
        ),
    ]
    summary = summarize_usage_cost(
        records,
        input_price_per_1m=1.0,
        output_price_per_1m=2.0,
    )

    assert summary.calls == 3
    assert summary.by_model["model-a"].calls == 2
    assert summary.by_model["model-a"].total_tokens == 450
    assert summary.by_model["model-b"].total_tokens == 75
    assert summary.estimated_cost > 0


def test_usage_record_rejects_inconsistent_total() -> None:
    with pytest.raises(ValueError):
        UsageRecord(
            model="test-model",
            call_type="chat",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=100,
            latency_ms=1,
        )


def test_task_metrics_can_include_cost_fields() -> None:
    metrics = build_task_metrics(
        request_id="req-1",
        total_ms=100,
        usage={"total_tokens": 200},
        estimated_cost=0.123,
        currency="USD",
        usage_call_count=2,
        usage_by_model={
            "test-model": {
                "calls": 2,
                "prompt_tokens": 100,
                "completion_tokens": 100,
                "total_tokens": 200,
                "estimated_cost": 0.123,
            }
        },
    )

    assert metrics.estimated_cost == 0.123
    assert metrics.usage_call_count == 2
    assert metrics.usage_by_model["test-model"]["total_tokens"] == 200
