# 验证十个 ORM 模型的结构、约束、索引、外键和关系配置。

from sqlalchemy.orm import configure_mappers

from app.db.models import (
    AnalysisTask,
    Base,
    Conversation,
    Job,
    KnowledgeChunk,
    Message,
    Report,
    Resume,
    ResumeVersion,
    ToolCallRecord,
    User,
)


EXPECTED_COLUMNS = {
    User: {
        "user_id", "username", "email", "role", "status",
        "created_at", "updated_at", "deleted_at",
    },
    Resume: {
        "resume_id", "user_id", "title", "status",
        "created_at", "updated_at", "deleted_at",
    },
    ResumeVersion: {
        "resume_version_id", "resume_id", "version_no", "raw_text",
        "extracted_sections", "source_type", "created_at",
    },
    Job: {
        "job_id", "user_id", "title", "company_name",
        "raw_description", "extracted_requirements", "status",
        "created_at", "updated_at", "deleted_at",
    },
    KnowledgeChunk: {
        "chunk_id", "user_id", "resume_version_id", "section_type",
        "title", "content", "content_hash", "position",
        "start_offset", "end_offset", "chunker_version", "index_status",
        "embedding_model", "embedding_dimension", "created_at", "updated_at",
    },
    Conversation: {
        "conversation_id", "user_id", "title", "status",
        "last_message_at", "created_at", "updated_at", "deleted_at",
    },
    Message: {
        "message_id", "conversation_id", "sequence_no",
        "role", "content", "metadata", "created_at",
    },
    AnalysisTask: {
        "task_id", "user_id", "conversation_id", "resume_version_id",
        "job_id", "status", "current_step", "attempt", "max_steps",
        "current_node", "last_request_id", "metrics_json",
        "error_code", "error_message_safe", "started_at", "finished_at",
        "created_at", "updated_at", "deleted_at",
    },
    Report: {
        "report_id", "task_id", "version_no", "is_current",
        "summary", "result_json", "created_at", "updated_at", "deleted_at",
    },
    ToolCallRecord: {
        "tool_call_record_id", "task_id", "step_no", "tool_call_id",
        "tool_name", "status", "duration_ms", "argument_keys",
        "error_code", "created_at",
    },
}

EXPECTED_CONSTRAINT_NAMES = {
    User: {
        "users_username_key", "users_email_key",
        "users_role_check", "users_status_check",
    },
    Resume: {"resumes_status_check"},
    ResumeVersion: {
        "resume_versions_resume_id_version_no_key",
        "resume_versions_version_no_check",
        "resume_versions_source_type_check",
    },
    Job: {"jobs_status_check"},
    KnowledgeChunk: {
        "knowledge_chunks_resume_version_id_chunker_version_position_key",
        "knowledge_chunks_position_check",
        "knowledge_chunks_section_type_check",
        "knowledge_chunks_start_offset_check",
        "knowledge_chunks_end_offset_check",
        "knowledge_chunks_offset_order_check",
        "knowledge_chunks_index_status_check",
        "knowledge_chunks_embedding_dimension_check",
    },
    Conversation: {"conversations_status_check"},
    Message: {
        "messages_conversation_id_sequence_no_key",
        "messages_sequence_no_check", "messages_role_check",
    },
    AnalysisTask: {
        "analysis_tasks_status_check", "analysis_tasks_current_step_check",
        "analysis_tasks_attempt_check", "analysis_tasks_max_steps_check",
        "analysis_tasks_check",
    },
    Report: {
        "reports_task_id_version_no_key", "reports_version_no_check",
    },
    ToolCallRecord: {
        "tool_call_records_task_id_tool_call_id_key",
        "tool_call_records_step_no_check",
        "tool_call_records_status_check",
        "tool_call_records_duration_ms_check",
    },
}

EXPECTED_INDEX_NAMES = {
    User: set(),
    Resume: {"idx_resumes_user_created_at"},
    ResumeVersion: set(),
    Job: {"idx_jobs_user_created_at"},
    KnowledgeChunk: {
        "idx_knowledge_chunks_user_resume_version",
        "idx_knowledge_chunks_resume_version_status",
        "idx_knowledge_chunks_user_content_hash",
    },
    Conversation: {"idx_conversations_user_updated_at"},
    Message: set(),
    AnalysisTask: {
        "idx_analysis_tasks_user_created_at",
        "idx_analysis_tasks_status_created_at",
        "idx_analysis_tasks_conversation_id",
        "idx_analysis_tasks_resume_version_id",
        "idx_analysis_tasks_job_id",
    },
    Report: {"idx_reports_one_current_per_task"},
    ToolCallRecord: {"idx_tool_call_records_task_step"},
}

EXPECTED_FOREIGN_KEY_NAMES = {
    User: set(),
    Resume: {"resumes_user_id_fkey"},
    ResumeVersion: {"resume_versions_resume_id_fkey"},
    Job: {"jobs_user_id_fkey"},
    KnowledgeChunk: {
        "knowledge_chunks_user_id_fkey",
        "knowledge_chunks_resume_version_id_fkey",
    },
    Conversation: {"conversations_user_id_fkey"},
    Message: {"messages_conversation_id_fkey"},
    AnalysisTask: {
        "analysis_tasks_user_id_fkey",
        "analysis_tasks_conversation_id_fkey",
        "analysis_tasks_resume_version_id_fkey",
        "analysis_tasks_job_id_fkey",
    },
    Report: {"reports_task_id_fkey"},
    ToolCallRecord: {"tool_call_records_task_id_fkey"},
}


def test_metadata_contains_ten_tables() -> None:
    assert set(Base.metadata.tables) == {
        "jobfit.users", "jobfit.resumes", "jobfit.resume_versions",
        "jobfit.jobs", "jobfit.knowledge_chunks", "jobfit.conversations", "jobfit.messages",
        "jobfit.analysis_tasks", "jobfit.reports",
        "jobfit.tool_call_records",
    }


def test_all_tables_use_jobfit_schema() -> None:
    for model in EXPECTED_COLUMNS:
        assert model.__table__.schema == "jobfit"


def test_all_model_columns_match_schema() -> None:
    for model, expected_columns in EXPECTED_COLUMNS.items():
        assert set(model.__table__.columns.keys()) == expected_columns


def test_all_expected_constraints_are_registered() -> None:
    for model, expected_names in EXPECTED_CONSTRAINT_NAMES.items():
        actual_names = {
            constraint.name
            for constraint in model.__table__.constraints
            if constraint.name is not None
        }
        assert expected_names <= actual_names


def test_all_expected_indexes_are_registered() -> None:
    for model, expected_names in EXPECTED_INDEX_NAMES.items():
        actual_names = {
            index.name
            for index in model.__table__.indexes
            if index.name is not None
        }
        assert actual_names == expected_names


def test_all_expected_foreign_key_names_are_registered() -> None:
    for model, expected_names in EXPECTED_FOREIGN_KEY_NAMES.items():
        actual_names = {
            foreign_key.constraint.name
            for foreign_key in model.__table__.foreign_keys
            if foreign_key.constraint.name is not None
        }
        assert actual_names == expected_names


def test_current_report_partial_unique_index() -> None:
    index = next(
        index
        for index in Report.__table__.indexes
        if index.name == "idx_reports_one_current_per_task"
    )
    condition = str(index.dialect_options["postgresql"]["where"])

    assert index.unique is True
    assert "is_current" in condition
    assert "deleted_at IS NULL" in condition


def test_message_metadata_attribute_maps_to_metadata_column() -> None:
    assert Message.message_metadata.property.columns[0].name == "metadata"
    assert Message.__table__.c.metadata.key == "metadata"


def test_relationships_are_configured() -> None:
    configure_mappers()

    assert User.resumes.property.mapper.class_ is Resume
    assert User.jobs.property.mapper.class_ is Job
    assert User.conversations.property.mapper.class_ is Conversation
    assert User.analysis_tasks.property.mapper.class_ is AnalysisTask
    assert Resume.user.property.mapper.class_ is User
    assert Resume.versions.property.mapper.class_ is ResumeVersion
    assert (
        ResumeVersion.knowledge_chunks.property.mapper.class_
        is KnowledgeChunk
    )
    assert KnowledgeChunk.resume_version.property.mapper.class_ is ResumeVersion
    assert Conversation.messages.property.mapper.class_ is Message
    assert Conversation.analysis_tasks.property.mapper.class_ is AnalysisTask
    assert AnalysisTask.reports.property.mapper.class_ is Report
    assert (
        AnalysisTask.tool_call_records.property.mapper.class_
        is ToolCallRecord
    )
