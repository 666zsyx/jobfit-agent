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
