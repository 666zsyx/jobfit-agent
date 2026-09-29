import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.db.models import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

database_url = os.getenv(
    "ALEMBIC_DATABASE_URL",
    settings.database_url,
)
config.set_main_option(
    "sqlalchemy.url",
    database_url.replace("%", "%%"),
)


def include_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, str | None],
) -> bool:
    if type_ == "schema":
        return name == "jobfit"
    return True


def configure_context(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
        version_table_schema="jobfit",
        autogenerate_plugins=(
            "alembic.autogenerate.*",
            "alembic.ext.checkconstraint_byname",
        ),
        include_name=include_name,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """在离线模式下生成 SQL。"""

    configure_context(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.execute(
            text("CREATE SCHEMA IF NOT EXISTS jobfit")
        )
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    configure_context(connection=connection)

    with context.begin_transaction():
        connection.execute(
            text("CREATE SCHEMA IF NOT EXISTS jobfit")
        )
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
