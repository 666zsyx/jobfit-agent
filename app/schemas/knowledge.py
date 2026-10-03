# 定义简历 Chunk、向量召回和混合召回的领域契约。

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.schemas.resume import ResumeSectionType


RESUME_CHUNKER_VERSION = "v1"


class KnowledgeChunkDraft(BaseModel):
    """尚未写入数据库的一段简历证据。"""

    model_config = ConfigDict(extra="forbid")

    section_type: ResumeSectionType
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=20_000)
    content_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    position: int = Field(ge=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)
    chunker_version: str = RESUME_CHUNKER_VERSION

    @model_validator(mode="after")
    def validate_offsets(self):
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset 必须大于 start_offset")

        if len(self.content) != self.end_offset - self.start_offset:
            raise ValueError("content 长度必须与 offset 范围一致")

        return self


class RetrievalHit(BaseModel):
    """关键词、向量和混合召回共享的证据结构。"""

    model_config = ConfigDict(extra="forbid")

    chunk_id: int = Field(ge=1)
    user_id: int = Field(ge=1)
    resume_version_id: int = Field(ge=1)
    section_type: ResumeSectionType
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=20_000)
    content_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    position: int = Field(ge=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=1)
    chunker_version: str = Field(min_length=1)


class VectorSearchHit(RetrievalHit):
    """向量召回命中。"""

    similarity: float = Field(ge=-1, le=1)
    rank: int = Field(ge=1)


class LexicalSearchHit(RetrievalHit):
    """BM25 关键词召回命中。"""

    bm25_score: float = Field(ge=0)
    rank: int = Field(ge=1)


class HybridSearchHit(RetrievalHit):
    """关键词和向量经过 RRF 融合后的候选。"""

    lexical_score: float | None = Field(default=None, ge=0)
    lexical_rank: int | None = Field(default=None, ge=1)
    vector_score: float | None = Field(default=None, ge=-1, le=1)
    vector_rank: int | None = Field(default=None, ge=1)
    fusion_score: float = Field(gt=0)
    rank: int = Field(ge=1)


class RerankedSearchHit(HybridSearchHit):
    """Reranker 重排后的候选，保留融合排名。"""

    rerank_score: float
    rerank_rank: int = Field(ge=1)


class EvidenceItem(RetrievalHit):
    """最终进入上下文的一条证据。"""

    relevance_score: float
    rank: int = Field(ge=1)


class EvidencePack(BaseModel):
    """一次岗位要求分析使用的 Top-N 证据包。"""

    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=1, max_length=500)
    items: list[EvidenceItem] = Field(max_length=20)
    rerank_applied: bool
    degraded: bool = False
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def validate_unique_chunks(self):
        chunk_ids = [item.chunk_id for item in self.items]

        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("EvidencePack 不能包含重复 chunk_id")

        return self