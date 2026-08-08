"""Alembic environment for TianShu application tables.

ONLY manages TianShu's tables (runs, threads_meta, feedback, users,
run_events, channel_connections, channel_credentials, channel_oauth_states,
channel_conversations).

LangGraph's checkpointer tables (``checkpoints``, ``checkpoint_blobs``,
``checkpoint_writes``, ``checkpoint_migrations``) are managed by LangGraph
itself -- they have their own schema lifecycle and must not be touched by
Alembic. The ``include_object`` filter below explicitly excludes them so a
future ``alembic revision --autogenerate`` will not emit ``drop_table`` for
tables it does not own.
"""

from __future__ import annotations

import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from tianshu.persistence.base import Base
from tianshu.persistence.migrations._env_filters import (
    LANGGRAPH_OWNED_TABLES,
    include_object,
)

# Re-export under the module namespace for any consumer that addresses them
# via ``env.LANGGRAPH_OWNED_TABLES`` / ``env.include_object``.
__all__ = ["LANGGRAPH_OWNED_TABLES", "include_object"]

# Import all models so metadata is populated.
try:
    import tianshu.persistence.models as models  # register ORM models with Base.metadata

    _ = models
except ImportError:
    # Models not available — migration will work with existing metadata only.
    logging.getLogger(__name__).warning("Could not import tianshu.persistence.models; Alembic may not detect all tables")

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    # When a custom Postgres schema is configured, pin the alembic-spawned
    # engine's search_path to it. This engine is built from the bare URL and
    # does NOT inherit the asyncpg ``server_settings`` the app engine sets via
    # ``connect_args``, so without this both ``alembic_version`` and every
    # migration's DDL would land in the default (``public``) schema while the
    # ORM tables land in the custom schema. ``init_engine`` has already created
    # the schema (``CREATE SCHEMA IF NOT EXISTS``) before bootstrap runs.
    pg_schema = config.get_main_option("tianshu_pg_schema")
    connect_args: dict = {}
    # Accept both the canonical ``postgresql`` scheme and libpq's ``postgres``
    # short scheme (with or without a SQLAlchemy ``+driver`` suffix) so a
    # ``postgres://`` DSN still gets its search_path pinned instead of silently
    # writing ``alembic_version`` + migration DDL to the default schema.
    if pg_schema and url and url.split("+", 1)[0].split(":", 1)[0] in {"postgresql", "postgres"}:
        from tianshu.persistence.postgres_schema import build_asyncpg_connect_args

        connect_args = build_asyncpg_connect_args(pg_schema)

    connectable = create_async_engine(url, connect_args=connect_args)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
