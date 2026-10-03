# 验证 PostgreSQL Checkpoint 的连接串和线程配置。

import pytest

from app.db.checkpoint import (
    build_checkpoint_config,
    checkpoint_thread_id,
    to_psycopg_conn_string,
)


def test_asyncpg_url_is_converted_for_psycopg() -> None:
    value = to_psycopg_conn_string(
        "postgresql+asyncpg://user:pass@127.0.0.1:5432/jobfit_dev"
    )
    assert value == (
        "postgresql://user:pass@127.0.0.1:5432/jobfit_dev"
    )


def test_psycopg_url_is_normalized() -> None:
    value = to_psycopg_conn_string(
        "postgresql+psycopg://user:pass@127.0.0.1:5432/jobfit_dev"
    )
    assert value == (
        "postgresql://user:pass@127.0.0.1:5432/jobfit_dev"
    )


def test_plain_postgresql_url_is_preserved() -> None:
    value = "postgresql://user:pass@127.0.0.1:5432/jobfit_dev"
    assert to_psycopg_conn_string(value) == value


def test_non_postgres_url_is_rejected() -> None:
    with pytest.raises(ValueError):
        to_psycopg_conn_string("sqlite:///jobfit.db")


def test_checkpoint_thread_id_is_stable() -> None:
    assert checkpoint_thread_id(42) == "jobfit-task-42"


def test_checkpoint_thread_id_rejects_invalid_task() -> None:
    with pytest.raises(ValueError):
        checkpoint_thread_id(0)


def test_build_checkpoint_config_uses_thread_id() -> None:
    assert build_checkpoint_config(42) == {
        "configurable": {
            "thread_id": "jobfit-task-42",
        }
    }
