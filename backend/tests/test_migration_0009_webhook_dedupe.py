"""Migration ``0009_webhook_dedupe`` regression test (issue #4120).

Verifies the migration creates ``webhook_deliveries`` with the composite
primary key (channel, workspace_id, chat_id, message_id) and no legacy
``dedupe_key`` column, and that re-running it is idempotent.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

import tianshu.persistence.models  # noqa: F401  -- registers ORM models
from tianshu.config.database_config import DatabaseConfig
from tianshu.persistence.base import Base
from tianshu.persistence.bootstrap import bootstrap_schema
from tianshu.persistence.engine import close_engine, get_engine, init_engine_from_config

pytestmark = pytest.mark.asyncio

POSTGRES_URL = os.getenv("TIANSHU_TEST_POSTGRES_URL")
if not POSTGRES_URL:
    pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL migration tests", allow_module_level=True)


def _sync_url() -> str:
    """Synchronous (psycopg) URL derived from the async test URL."""
    url = os.environ["TIANSHU_TEST_POSTGRES_URL"]
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


async def test_migration_0009_creates_composite_pk_table_and_is_idempotent() -> None:
    import uuid

    import psycopg

    schema = f"pgtest_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(POSTGRES_URL or "", autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    try:
        # Seed all baseline tables, then drop ONLY webhook_deliveries so the
        # 0009 upgrade actually exercises its create_table path (not the
        # idempotent early-return). Stamp at 0004 so bootstrap upgrades to head.
        sync = sa.create_engine(
            _sync_url(),
            connect_args={"options": f"-csearch_path={schema}"},
        )
        try:
            Base.metadata.create_all(sync)
            with sync.begin() as conn:
                conn.execute(sa.text("DROP TABLE IF EXISTS webhook_deliveries"))
                conn.execute(sa.text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
                conn.execute(sa.text("DELETE FROM alembic_version"))
                conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0004_run_ownership')"))
        finally:
            sync.dispose()

        await init_engine_from_config(
            DatabaseConfig(
                backend="postgres",
                postgres_url=POSTGRES_URL or "",
                postgres_schema=schema,
            )
        )
        # init_engine_from_config runs upgrade head -> executes 0009.create_table.
        engine = get_engine()
        assert engine is not None
        await bootstrap_schema(engine, backend="postgres", postgres_schema=schema)

        with psycopg.connect(POSTGRES_URL or "") as conn:
            cols = {
                row[0]
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = 'webhook_deliveries'",
                    (schema,),
                ).fetchall()
            }
        # Composite PK columns only; the old single-column ``dedupe_key`` must
        # NOT exist (it is illegal in Postgres TEXT and caused schema drift).
        assert cols == {"channel", "workspace_id", "chat_id", "message_id", "first_seen"}

        # Idempotent: re-running bootstrap at head must not raise (table exists).
        await bootstrap_schema(engine, backend="postgres", postgres_schema=schema)
    finally:
        await close_engine()
        with psycopg.connect(POSTGRES_URL or "", autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')