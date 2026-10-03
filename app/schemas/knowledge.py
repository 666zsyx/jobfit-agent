# 定义简历 Chunk 切分后的领域契约。

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

