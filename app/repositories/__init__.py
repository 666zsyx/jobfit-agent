# 导出数据访问层 Repository。

from app.repositories.analysis_task import AnalysisTaskRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.job import JobRepository
from app.repositories.knowledge_chunk import KnowledgeChunkRepository
from app.repositories.message import MessageRepository
from app.repositories.report import ReportRepository
from app.repositories.resume import ResumeRepository
from app.repositories.resume_version import ResumeVersionRepository
from app.repositories.tool_call_record import ToolCallRecordRepository
from app.repositories.user import UserRepository

__all__ = [
    "UserRepository",
    "ResumeRepository",
    "ResumeVersionRepository",
    "JobRepository",
    "KnowledgeChunkRepository",
    "ConversationRepository",
    "MessageRepository",
    "AnalysisTaskRepository",
    "ReportRepository",
    "ToolCallRecordRepository",
]
