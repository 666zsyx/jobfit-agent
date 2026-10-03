# 计算 RAG 检索和引用评估指标。

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalMetrics:
    """单个检索案例的二元相关性指标。"""

    recall: float
    mrr: float
    ndcg: float
    precision: float


def evaluate_ranked_ids(
    *,
    retrieved_ids: Sequence[int],
    relevant_ids: set[int],
    k: int,
) -> RetrievalMetrics:
    """按二元相关性计算 Recall、MRR、nDCG 和 Precision。"""

    if k < 1:
        raise ValueError("k 必须大于等于 1")

    ranked_ids = list(retrieved_ids[:k])

    if not relevant_ids:
        return RetrievalMetrics(
            recall=0.0,
            mrr=0.0,
            ndcg=0.0,
            precision=0.0,
        )

    hits = [
        chunk_id
        for chunk_id in ranked_ids
        if chunk_id in relevant_ids
    ]
    recall = len(set(hits)) / len(relevant_ids)

    reciprocal_rank = 0.0
    for rank, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in relevant_ids:
            reciprocal_rank = 1.0 / rank
            break

    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(ranked_ids, start=1)
        if chunk_id in relevant_ids
    )
    ideal_hits = min(k, len(relevant_ids))
    idcg = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(1, ideal_hits + 1)
    )
    ndcg = dcg / idcg if idcg > 0 else 0.0
    precision = len(hits) / k

    return RetrievalMetrics(
        recall=recall,
        mrr=reciprocal_rank,
        ndcg=ndcg,
        precision=precision,
    )


def precision_of_returned_ids(
    *,
    retrieved_ids: Sequence[int],
    relevant_ids: set[int],
) -> float:
    """计算返回证据中的相关比例。"""

    if not retrieved_ids or not relevant_ids:
        return 0.0

    relevant_hits = sum(
        1
        for chunk_id in retrieved_ids
        if chunk_id in relevant_ids
    )
    return relevant_hits / len(retrieved_ids)

def mean_metrics(
    metrics: Sequence[RetrievalMetrics],
) -> RetrievalMetrics:
    """对多个案例求平均；没有案例时返回零。"""

    if not metrics:
        return RetrievalMetrics(
            recall=0.0,
            mrr=0.0,
            ndcg=0.0,
            precision=0.0,
        )

    count = len(metrics)
    return RetrievalMetrics(
        recall=sum(item.recall for item in metrics) / count,
        mrr=sum(item.mrr for item in metrics) / count,
        ndcg=sum(item.ndcg for item in metrics) / count,
        precision=sum(item.precision for item in metrics) / count,
    )

