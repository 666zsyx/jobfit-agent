# 验证 User ORM 与 jobfit.users 表结构保持一致。

from app.db.models import Base, User


def test_user_table_name_and_schema() -> None:
    assert User.__table__.name == "users"
    assert User.__table__.schema == "jobfit"


def test_user_table_columns() -> None:
    expected_columns = {
        "user_id",
        "username",
        "email",
        "role",
        "status",
        "created_at",
        "updated_at",
        "deleted_at",
    }

    assert set(User.__table__.columns.keys()) == expected_columns


def test_user_model_is_registered() -> None:
    assert "jobfit.users" in Base.metadata.tables


def test_user_nullable_fields() -> None:
    assert User.__table__.c.deleted_at.nullable is True
    assert User.__table__.c.user_id.nullable is False
    assert User.__table__.c.username.nullable is False
    assert User.__table__.c.email.nullable is False
