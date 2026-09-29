# 统一导出数据库模型，确保 Alembic 导入时模型已注册到 Metadata。

from app.db.base import Base
from app.db.models.analysis_task import AnalysisTask
from app.db.models.conversation import Conversation
from app.db.models.job import Job
from app.db.models.message import Message
from app.db.models.report import Report
from app.db.models.resume import Resume
from app.db.models.resume_version import ResumeVersion
from app.db.models.tool_call_record import ToolCallRecord
from app.db.models.user import User

__all__ = [
    "Base",
    "User",
    "Resume",
    "ResumeVersion",
    "Job",
    "Conversation",
    "Message",
    "AnalysisTask",
    "Report",
    "ToolCallRecord",
]
