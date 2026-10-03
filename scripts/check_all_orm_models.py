# 验证九个 ORM 模型、真实表、显式索引和外键名称。

import asyncio
import sys
from pathlib import Path

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import configure_mappers

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import (
    AnalysisTask,
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
from app.db.session import async_session_factory, dispose_engine


MODELS = (
    User,
    Resume,
    ResumeVersion,
    Job,
    KnowledgeChunk,
    Conversation,
    Message,
    AnalysisTask,
    Report,
    ToolCallRecord,
)
TABLE_NAMES = tuple(model.__table__.name for model in MODELS)


def _expected_indexes() -> dict[str, set[str]]:
    return {
        model.__table__.name: {
            index.name
            for index in model.__table__.indexes
            if index.name is not None
        }
        for model in MODELS
    }


def _expected_foreign_key_names() -> dict[str, set[str]]:
    return {
        model.__table__.name: {
            foreign_key.constraint.name
            for foreign_key in model.__table__.foreign_keys
            if foreign_key.constraint.name is not None
        }
        for model in MODELS
    }


def _load_database_schema(sync_connection) -> dict:
    inspector = inspect(sync_connection)
    indexes: dict[str, set[str]] = {}
    foreign_key_names: dict[str, set[str]] = {}

    for table_name in TABLE_NAMES:
        indexes[table_name] = {
            index["name"]
            for index in inspector.get_indexes(
                table_name,
                schema="jobfit",
            )
            if index["name"] is not None
        }
        foreign_key_names[table_name] = {
            foreign_key["name"]
            for foreign_key in inspector.get_foreign_keys(
                table_name,
                schema="jobfit",
            )
            if foreign_key["name"] is not None
        }

    return {
        "indexes": indexes,
        "foreign_key_names": foreign_key_names,
    }


async def check_all_orm_models() -> None:
    configure_mappers()
    expected_indexes = _expected_indexes()
    expected_foreign_key_names = _expected_foreign_key_names()

    try:
        async with async_session_factory() as session:
            for model in MODELS:
                result = await session.execute(
                    select(func.count()).select_from(model)
                )
                count = result.scalar_one()
                table = model.__table__
                print(
                    f"{model.__name__} "
                    f"{table.schema}.{table.name} "
                    f"ok count={count}"
                )

            connection = await session.connection()
            actual = await connection.run_sync(_load_database_schema)

            for model in MODELS:
                table_name = model.__table__.name
                missing_indexes = (
                    expected_indexes[table_name]
                    - actual["indexes"][table_name]
                )
                if missing_indexes:
                    raise RuntimeError(
                        f"{table_name} 缺少索引: "
                        f"{sorted(missing_indexes)}"
                    )

                expected_fks = expected_foreign_key_names[table_name]
                actual_fks = actual["foreign_key_names"][table_name]
                if expected_fks != actual_fks:
                    raise RuntimeError(
                        f"{table_name} 外键名称不一致: "
                        f"expected={sorted(expected_fks)} "
                        f"actual={sorted(actual_fks)}"
                    )

            print("indexes ok")
            print("foreign key names ok")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_all_orm_models())
