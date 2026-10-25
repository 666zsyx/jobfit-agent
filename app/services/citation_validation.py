# 校验模型引用是否来自 EvidencePack。

from collections import Counter
from dataclasses import dataclass

from app.schemas.knowledge import EvidencePack


@dataclass(frozen=True)
class CitationValidationResult:
    """一次引用校验结果。"""

    valid: bool
    cited_chunk_ids: list[int]
    unknown_chunk_ids: list[int]
    duplicate_chunk_ids: list[int]
    missing_citation: bool


def validate_evidence_citations(
    *,
    evidence_pack: EvidencePack,
    cited_chunk_ids: list[int],
    require_at_least_one: bool = True,
) -> CitationValidationResult:
    """确保引用只来自当前证据包，并且没有未知或重复 ID。"""

    allowed_chunk_ids = {
        item.chunk_id
        for item in evidence_pack.items
    }
    unknown_chunk_ids = sorted(
        {
            chunk_id
            for chunk_id in cited_chunk_ids
            if chunk_id not in allowed_chunk_ids
        }
    )
    counts = Counter(cited_chunk_ids)
    duplicate_chunk_ids = sorted(
        chunk_id
        for chunk_id, count in counts.items()
        if count > 1
    )
    missing_citation = require_at_least_one and not cited_chunk_ids
    valid = (
        not unknown_chunk_ids
        and not duplicate_chunk_ids
        and not missing_citation
    )

    return CitationValidationResult(
        valid=valid,
        cited_chunk_ids=cited_chunk_ids,
        unknown_chunk_ids=unknown_chunk_ids,
        duplicate_chunk_ids=duplicate_chunk_ids,
        missing_citation=missing_citation,
    )

def collect_chunk_ids(value) -> list[int]:
    """从任意嵌套 JSON 中收集 chunk_id/chunkId。"""

    output: list[int] = []

    def visit(current) -> None:
        if isinstance(current, list):
            for item in current:
                visit(item)
            return
        if not isinstance(current, dict):
            return
        for key, child in current.items():
            if key in {
                "chunk_id",
                "chunkId",
                "chunk_ids",
                "evidence_ids",
                "cited_chunk_ids",
            } and child is not None:
                candidates = (
                    child if isinstance(child, list) else [child]
                )
                for candidate in candidates:
                    try:
                        output.append(int(candidate))
                    except (TypeError, ValueError):
                        pass
            else:
                visit(child)

    visit(value)
    return output


def validate_report_citations(
    *,
    result_json: dict,
    evidence_packs: list[EvidencePack],
    require_at_least_one: bool = True,
) -> CitationValidationResult:
    """校验报告中的 chunk_id 是否来自当前任务的证据包。"""

    allowed_chunk_ids = {
        item.chunk_id
        for pack in evidence_packs
        for item in pack.items
    }
    cited_chunk_ids = collect_chunk_ids(result_json)

    if not allowed_chunk_ids:
        return CitationValidationResult(
            valid=not cited_chunk_ids and not require_at_least_one,
            cited_chunk_ids=cited_chunk_ids,
            unknown_chunk_ids=cited_chunk_ids,
            duplicate_chunk_ids=[],
            missing_citation=require_at_least_one,
        )

    combined_items = []
    seen_chunk_ids: set[int] = set()
    for pack in evidence_packs:
        for item in pack.items:
            if item.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(item.chunk_id)
            combined_items.append(item)

    return validate_evidence_citations(
        evidence_pack=EvidencePack(
            requirement="combined",
            items=combined_items,
            rerank_applied=True,
        ),
        cited_chunk_ids=cited_chunk_ids,
        require_at_least_one=require_at_least_one,
    )
