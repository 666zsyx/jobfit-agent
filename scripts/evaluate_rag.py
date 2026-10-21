# 在固定评估集上比较关键词、向量、混合和 Rerank 策略。

import asyncio
import json
import math
import os
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import Resume, ResumeVersion, User
from app.db.session import async_session_factory, dispose_engine
from app.schemas.resume import ResumeSection
from app.services.chunking import ingest_resume_version_chunks
from app.services.evidence_pipeline import search_resume_chunks_with_evidence
from app.services.hybrid_search import search_resume_chunks_hybrid
from app.services.keyword_search import search_resume_chunks_by_keyword
from app.services.rag_evaluation import (
    RetrievalMetrics,
    evaluate_ranked_ids,
    mean_metrics,
    precision_of_returned_ids,
)
from app.services.rag_runtime import (
    get_embedding_provider,
    get_reranker,
    get_vector_index,
)
from app.services.vector_indexing import index_resume_version_chunks
from app.services.vector_search import search_resume_chunks_by_vector


DATASET_PATH = PROJECT_ROOT / "data/evaluation/rag_cases.json"
REPORT_JSON_PATH = PROJECT_ROOT / "docs/rag_evaluation_results.json"
REPORT_MARKDOWN_PATH = PROJECT_ROOT / "docs/RAG_EVALUATION.md"
EVALUATION_K = 5
RERANK_PRODUCTION_THRESHOLD = -2.9


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * ratio) - 1)
    return ordered[index]


def format_metric(value: float) -> str:
    return f"{value:.4f}"


def build_markdown_report(summary: dict, case_count: int) -> str:
    lines = [
        "# STEP 08 RAG Evaluation",
        "",
        f"- Evaluation cases: {case_count}",
        f"- K: {EVALUATION_K}",
        "- Dataset: `data/evaluation/rag_cases.json`",
        "",
        "| Strategy | Recall@5 | MRR@5 | nDCG@5 | Precision@5 | Citation Precision | Abstention Accuracy | p50 ms | p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for strategy_name, metrics in summary.items():
        lines.append(
            "| "
            f"{strategy_name} | "
            f"{format_metric(metrics['recall_at_k'])} | "
            f"{format_metric(metrics['mrr_at_k'])} | "
            f"{format_metric(metrics['ndcg_at_k'])} | "
            f"{format_metric(metrics['precision_at_k'])} | "
            f"{format_metric(metrics['citation_precision'])} | "
            f"{format_metric(metrics['abstention_accuracy'])} | "
            f"{metrics['p50_latency_ms']:.2f} | "
            f"{metrics['p95_latency_ms']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Positive cases evaluate Recall, MRR, nDCG, Precision and citation precision.",
            "- Negative cases evaluate whether the strategy returns no accepted evidence.",
            "- Rerank raw reports unthresholded ranking quality.",
            "- Rerank prod applies a calibrated minimum score of -2.9.",
            "- The threshold -2.9 was calibrated on the original 30-case subset; the current set has 100 cases, and an independent holdout is still recommended.",
        ]
    )

    return "\n".join(lines) + "\n"


async def evaluate_rag() -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    corpus = dataset["corpus"]
    cases = dataset["cases"]
    limit = int(os.getenv("RAG_EVAL_LIMIT", "0"))
    if limit > 0:
        cases = cases[:limit]
    sections = [
        ResumeSection(
            section_type=item["section_type"],
            title=item["title"],
            content=item["content"],
        )
        for item in corpus
    ]

    suffix = uuid4().hex[:12]
    resume_version_id: int | None = None
    user_id: int | None = None
    vector_index = get_vector_index()

    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            owner = User(
                username=f"rag-eval-{suffix}",
                email=f"rag-eval-{suffix}@example.com",
            )
            session.add(owner)
            await session.flush()
            user_id = owner.user_id

            resume = Resume(user_id=owner.user_id, title="RAG Evaluation")
            session.add(resume)
            await session.flush()

            version = ResumeVersion(
                resume_id=resume.resume_id,
                version_no=1,
                raw_text="RAG evaluation corpus",
                extracted_sections={
                    "sections": [
                        section.model_dump(mode="json")
                        for section in sections
                    ],
                },
            )
            session.add(version)
            await session.flush()
            resume_version_id = version.resume_version_id

            chunks = await ingest_resume_version_chunks(
                session,
                user_id=owner.user_id,
                resume_version_id=resume_version_id,
            )
            await index_resume_version_chunks(
                session,
                user_id=owner.user_id,
                resume_version_id=resume_version_id,
                embedding_provider=get_embedding_provider(),
                vector_index=vector_index,
            )

            chunk_by_title = {
                chunk.title: chunk.chunk_id
                for chunk in chunks
            }
            section_to_chunk = {
                item["section_key"]: chunk_by_title[item["title"]]
                for item in corpus
            }

            embedding_provider = get_embedding_provider()
            reranker = get_reranker()
            strategy_metrics: dict[str, list[RetrievalMetrics]] = {
                "keyword": [],
                "vector": [],
                "hybrid": [],
                "rerank": [],
                "rerank_prod": [],
            }
            strategy_citation_precision: dict[str, list[float]] = {
                "keyword": [],
                "vector": [],
                "hybrid": [],
                "rerank": [],
                "rerank_prod": [],
            }
            strategy_latency: dict[str, list[float]] = {
                "keyword": [],
                "vector": [],
                "hybrid": [],
                "rerank": [],
                "rerank_prod": [],
            }
            strategy_abstention: dict[str, list[bool]] = {
                "keyword": [],
                "vector": [],
                "hybrid": [],
                "rerank": [],
                "rerank_prod": [],
            }
            case_details: list[dict] = []


            print(f"chunks={len(chunks)} cases={len(cases)}", flush=True)

            for case_index, case in enumerate(cases, start=1):
                print(
                    f"case {case_index}/{len(cases)} {case['case_id']}",
                    flush=True,
                )
                relevant_ids = {
                    section_to_chunk[key]
                    for key in case["expected_section_keys"]
                }
                case_result = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "requirement": case["requirement"],
                    "expected_chunk_ids": sorted(relevant_ids),
                    "strategies": {},
                }

                started = perf_counter()
                keyword_hits = await search_resume_chunks_by_keyword(
                    session,
                    user_id=user_id,
                    resume_version_id=resume_version_id,
                    requirement=case["requirement"],
                    top_k=EVALUATION_K,
                )
                keyword_ids = [hit.chunk_id for hit in keyword_hits]
                strategy_latency["keyword"].append(
                    (perf_counter() - started) * 1000
                )

                started = perf_counter()
                vector_hits = await search_resume_chunks_by_vector(
                    session,
                    user_id=user_id,
                    resume_version_id=resume_version_id,
                    requirement=case["requirement"],
                    top_k=EVALUATION_K,
                    embedding_provider=embedding_provider,
                    vector_index=vector_index,
                )
                vector_ids = [hit.chunk_id for hit in vector_hits]
                strategy_latency["vector"].append(
                    (perf_counter() - started) * 1000
                )

                started = perf_counter()
                hybrid_hits = await search_resume_chunks_hybrid(
                    session,
                    user_id=user_id,
                    resume_version_id=resume_version_id,
                    requirement=case["requirement"],
                    top_k=10,
                    top_n=EVALUATION_K,
                    embedding_provider=embedding_provider,
                    vector_index=vector_index,
                )
                hybrid_ids = [hit.chunk_id for hit in hybrid_hits]
                strategy_latency["hybrid"].append(
                    (perf_counter() - started) * 1000
                )

                started = perf_counter()
                evidence_pack = await search_resume_chunks_with_evidence(
                    session,
                    user_id=user_id,
                    resume_version_id=resume_version_id,
                    requirement=case["requirement"],
                    candidate_top_k=10,
                    rerank_candidate_top_n=10,
                    evidence_top_n=EVALUATION_K,
                    min_rerank_score=-float("inf"),
                    embedding_provider=embedding_provider,
                    vector_index=vector_index,
                    reranker=reranker,
                )
                rerank_ranked_items = [
                    (item.chunk_id, item.relevance_score)
                    for item in evidence_pack.items
                ]
                rerank_ids = [
                    chunk_id for chunk_id, _ in rerank_ranked_items
                ]
                rerank_prod_ids = [
                    chunk_id
                    for chunk_id, score in rerank_ranked_items
                    if score >= RERANK_PRODUCTION_THRESHOLD
                ][:EVALUATION_K]
                case_result["rerank_scores"] = [
                    score for _, score in rerank_ranked_items
                ]
                rerank_latency_ms = (perf_counter() - started) * 1000
                strategy_latency["rerank"].append(rerank_latency_ms)
                strategy_latency["rerank_prod"].append(rerank_latency_ms)

                retrieved_by_strategy = {
                    "keyword": keyword_ids,
                    "vector": vector_ids,
                    "hybrid": hybrid_ids,
                    "rerank": rerank_ids,
                    "rerank_prod": rerank_prod_ids,
                }

                for strategy_name, retrieved_ids in (
                    retrieved_by_strategy.items()
                ):
                    case_result["strategies"][strategy_name] = retrieved_ids

                    if case["should_abstain"]:
                        strategy_abstention[strategy_name].append(
                            not retrieved_ids
                        )
                    else:
                        strategy_metrics[strategy_name].append(
                            evaluate_ranked_ids(
                                retrieved_ids=retrieved_ids,
                                relevant_ids=relevant_ids,
                                k=EVALUATION_K,
                            )
                        )
                        strategy_citation_precision[
                            strategy_name
                        ].append(
                            precision_of_returned_ids(
                                retrieved_ids=retrieved_ids,
                                relevant_ids=relevant_ids,
                            )
                        )

                case_details.append(case_result)


            summary: dict[str, dict[str, float]] = {}
            for strategy_name in strategy_metrics:
                average = mean_metrics(strategy_metrics[strategy_name])
                citation_precision_values = (
                    strategy_citation_precision[strategy_name]
                )
                abstention_values = strategy_abstention[strategy_name]
                latencies = strategy_latency[strategy_name]
                summary[strategy_name] = {
                    "recall_at_k": average.recall,
                    "mrr_at_k": average.mrr,
                    "ndcg_at_k": average.ndcg,
                    "precision_at_k": average.precision,
                    "citation_precision": (
                        sum(citation_precision_values)
                        / len(citation_precision_values)
                        if citation_precision_values
                        else 0.0
                    ),
                    "abstention_accuracy": (
                        sum(abstention_values) / len(abstention_values)
                        if abstention_values
                        else 0.0
                    ),
                    "p50_latency_ms": percentile(latencies, 0.50),
                    "p95_latency_ms": percentile(latencies, 0.95),
                }

            report = {
                "dataset_version": dataset["version"],
                "case_count": len(cases),
                "k": EVALUATION_K,
                "summary": summary,
                "cases": case_details,
            }

            REPORT_JSON_PATH.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            REPORT_MARKDOWN_PATH.write_text(
                build_markdown_report(summary, len(cases)),
                encoding="utf-8",
            )

            print(f"cases={len(cases)}")
            for strategy_name, metrics in summary.items():
                print(
                    f"{strategy_name}: "
                    f"recall@5={metrics['recall_at_k']:.4f} "
                    f"mrr@5={metrics['mrr_at_k']:.4f} "
                    f"ndcg@5={metrics['ndcg_at_k']:.4f} "
                    f"citation_precision={metrics['citation_precision']:.4f} "
                    f"abstention={metrics['abstention_accuracy']:.4f} "
                    f"p95={metrics['p95_latency_ms']:.2f}ms"
                )

            await transaction.rollback()
        finally:
            if resume_version_id is not None and user_id is not None:
                await asyncio.to_thread(
                    vector_index.delete_resume_version,
                    user_id=user_id,
                    resume_version_id=resume_version_id,
                )

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(evaluate_rag())
