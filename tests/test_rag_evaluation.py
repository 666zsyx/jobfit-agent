# 验证 Recall、MRR、nDCG 和 Precision 计算。

import pytest

from app.services.rag_evaluation import (
    RetrievalMetrics,
    evaluate_ranked_ids,
    mean_metrics,
    precision_of_returned_ids,
)


def test_perfect_first_rank_metrics():
    metrics = evaluate_ranked_ids(
        retrieved_ids=[1, 2],
        relevant_ids={1},
        k=2,
    )

    assert metrics.recall == 1.0
    assert metrics.mrr == 1.0
    assert metrics.ndcg == 1.0
    assert metrics.precision == 0.5


def test_first_relevant_at_second_rank():
    metrics = evaluate_ranked_ids(
        retrieved_ids=[9, 2, 3],
        relevant_ids={2},
        k=3,
    )

    assert metrics.recall == 1.0
    assert metrics.mrr == 0.5
    assert metrics.precision == pytest.approx(1 / 3)


def test_no_hit_returns_zero_metrics():
    metrics = evaluate_ranked_ids(
        retrieved_ids=[1, 2, 3],
        relevant_ids={99},
        k=3,
    )

    assert metrics.recall == 0.0
    assert metrics.mrr == 0.0
    assert metrics.ndcg == 0.0
    assert metrics.precision == 0.0


def test_multi_relevant_recall_and_ndcg():
    metrics = evaluate_ranked_ids(
        retrieved_ids=[1, 2, 3],
        relevant_ids={1, 3},
        k=3,
    )

    assert metrics.recall == 1.0
    assert metrics.mrr == 1.0
    assert 0 < metrics.ndcg <= 1.0
    assert metrics.precision == pytest.approx(2 / 3)


def test_precision_of_returned_ids():
    precision = precision_of_returned_ids(
        retrieved_ids=[1, 2, 3],
        relevant_ids={1, 3},
    )

    assert precision == pytest.approx(2 / 3)


def test_mean_metrics():
    average = mean_metrics(
        [
            RetrievalMetrics(1.0, 1.0, 1.0, 1.0),
            RetrievalMetrics(0.0, 0.5, 0.5, 0.0),
        ]
    )

    assert average == RetrievalMetrics(
        recall=0.5,
        mrr=0.75,
        ndcg=0.75,
        precision=0.5,
    )


def test_invalid_k_is_rejected():
    with pytest.raises(ValueError, match="k 必须大于等于 1"):
        evaluate_ranked_ids(
            retrieved_ids=[1],
            relevant_ids={1},
            k=0,
        )
