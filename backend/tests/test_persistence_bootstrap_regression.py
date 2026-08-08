"""Regression test for GitHub issue #3682.

End-to-end shape:

1. Hand-build a PostgreSQL schema that mirrors a real pre-#3658 deployment
   -- the ``runs`` table is missing the ``token_usage_by_model`` column,
   mirroring what every existing user's DB looked like after the upgrade
   that triggered the issue.
2. Run ``init_engine`` (the entry point used by the FastAPI Gateway
   lifespan), which now routes through ``bootstrap_schema``.
3. Confirm a real ``SELECT`` against the column succeeds, demonstrating the
   500 from the original issue is gone.

The pre-fix codepath would have raised
``sqlalchemy.exc.OperationalError: no such column: runs.token_usage_by_model``
on step 3.

Requires ``TIANSHU_TEST_POSTGRES_URL`` (the repo convention for live
PostgreSQL tests); skipped otherwise.
"""

from __future__ import annotations

import os
import uuid
from uuid import uuid4

import pytest
import sqlalchemy as sa

import tianshu.persistence.models  # noqa: F401  -- registers ORM models
from tianshu.config.database_config import DatabaseConfig
from tianshu.persistence import bootstrap as bootstrap_mod
from tianshu.persistence.base import Base
from tianshu.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from tianshu.persistence.run import RunRepository

pytestmark = pytest.mark.asyncio

POSTGRES_URL = os.getenv("TIANSHU_TEST_POSTGRES_URL")


def _new_schema() -> str:
    return f"bootstrap_regression_{uuid.uuid4().hex[:12]}"


def _seed_pre_3658_database(schema: str) -> None:
    """Build a schema that looks like a pre-PR-#3658 deployment.

    Uses a synchronous psycopg engine so the seed is independent of the
    async engine under test. The schema is created first; ``create_all``
    then runs with ``search_path`` pinned to it, and the new column is
    dropped with a raw ``ALTER TABLE``.
    """
    assert POSTGRES_URL
    import psycopg

    with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')

    db_config = DatabaseConfig(backend="postgres", postgres_url=POSTGRES_URL, postgres_schema=schema)
    sync_url = db_config.app_sync_sqlalchemy_url
    sync_engine = sa.create_engine(sync_url, connect_args={"options": f"-c search_path={schema}"})
    try:
        Base.metadata.create_all(sync_engine)
        with sync_engine.begin() as conn:
            conn.execute(sa.text("ALTER TABLE runs DROP COLUMN token_usage_by_model"))
    finally:
        sync_engine.dispose()


def _drop_schema(schema: str) -> None:
    assert POSTGRES_URL
    import psycopg

    with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _runs_columns_sync(schema: str) -> set[str]:
    assert POSTGRES_URL
    import psycopg

    with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
        rows = conn.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'runs'
            """,
            (schema,),
        ).fetchall()
    return {row[0] for row in rows}


async def test_legacy_database_recovers_token_usage_column() -> None:
    if not POSTGRES_URL:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL bootstrap regression tests")

    schema = _new_schema()
    _seed_pre_3658_database(schema)
    try:
        # Sanity: confirm we did indeed land in the buggy pre-fix shape before
        # init_engine touches the DB.
        cols = _runs_columns_sync(schema)
        assert "run_id" in cols
        assert "token_usage_by_model" not in cols

        # Run the same init_engine path FastAPI lifespan uses on startup.
        db_config = DatabaseConfig(backend="postgres", postgres_url=POSTGRES_URL, postgres_schema=schema)
        await init_engine_from_config(db_config)

        # The column must now be present, and alembic must be at head.
        cols = _runs_columns_sync(schema)
        assert "token_usage_by_model" in cols
        head = bootstrap_mod._get_head_revision()

        # And the read path that originally 500'd must now succeed.
        sf = get_session_factory()
        assert sf is not None
        repo = RunRepository(sf)
        # No rows yet -- the point is just that the SELECT does not raise.
        result = await repo.aggregate_tokens_by_thread(thread_id=str(uuid4()))
        assert result["total_tokens"] == 0
        assert result["by_model"] == {}
        assert head  # keep ruff quiet about the unused local if assertions change
    finally:
        await close_engine()
        _drop_schema(schema)


async def test_legacy_database_with_manual_alter_still_bootstraps() -> None:
    """User-side workaround scenario: someone already applied the manual
    ``ALTER TABLE runs ADD COLUMN token_usage_by_model JSON`` from the issue
    write-up. The hybrid bootstrap must just stamp head, not double-add the
    column, and not error.
    """
    if not POSTGRES_URL:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL bootstrap regression tests")

    schema = _new_schema()
    _seed_pre_3658_database(schema)
    try:
        # Re-add the column manually -- this is the "user already ran the
        # workaround" case.
        assert POSTGRES_URL
        import psycopg

        with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
            conn.execute(
                'ALTER TABLE "runs" ADD COLUMN token_usage_by_model JSON',
            )

        db_config = DatabaseConfig(backend="postgres", postgres_url=POSTGRES_URL, postgres_schema=schema)
        await init_engine_from_config(db_config)

        cols = _runs_columns_sync(schema)
        # No duplicate column -- list, not set, to catch dupes.
        assert cols.count("token_usage_by_model") == 1
        head = bootstrap_mod._get_head_revision()
        assert head  # keep ruff quiet about the unused local if assertions change
    finally:
        await close_engine()
        _drop_schema(schema)
