from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from alembic.operations.ops import MigrationScript
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlalchemy.dialects import postgresql

import odds_value.db.models  # noqa: F401
from odds_value.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_database_url() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    return os.environ.get("DATABASE_URL", "sqlite+pysqlite:///./odds_value.db")


def render_item(
    type_: str,
    obj: Any,
    autogen_context: AutogenContext,
) -> str | Literal[False]:
    if type_ == "type" and isinstance(obj, postgresql.JSONB):
        return "postgresql.JSONB()"

    return False


def process_revision_directives(context, revision, directives) -> None:
    script = directives[0]
    if not isinstance(script, MigrationScript):
        return

    script.imports.add("from sqlalchemy.dialects import postgresql")


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            compare_type=True,
            render_item=render_item,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
