"""Regression test for migration ``0004_run_ownership`` dedupe pass.

End-to-end shape:

1. Hand-build a PostgreSQL DB (isolated schema) that mirrors a real pre-0004
   deployment that ran ``GATEWAY_WORKERS>1`` before this PR and accumulated
   duplicate active rows per thread (the exact dirty state the multi-worker
   ownership fix targets).
2. Stamp it at ``0003_scheduled_tasks`` so ``bootstrap_schema`` takes the
   versioned branch and runs ``alembic upgrade head``.
3. Insert two+ pending/running rows for the same ``thread_id`` (only possible
   because the partial unique index does not exist yet).
4. Run ``init_engine`` (the FastAPI lifespan entry point), which routes
   through ``bootstrap_schema`` → ``upgrade head`` → ``0004.upgrade()``.
5. Verify the migration cancelled the superseded duplicates (set them to
   ``error`` with an explanatory message), kept the newest active row, and
   successfully built the ``uq_runs_thread_active`` partial unique index.

Pre-fix codepath would have raised ``UNIQUE constraint failed`` (SQLite) /
``could not create unique index`` (Postgres) on step 5, aborting the alembic
upgrade and blocking gateway startup.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

import tianshu.persistence.models  # noqa: F401  -- registers ORM models
from tianshu.config.database_config import DatabaseConfig
from tianshu.persistence.base import Base
from tianshu.persistence.engine import close_engine, init_engine_from_config
from tianshu.persistence.run.model import RunRow

pytestmark = pytest.mark.asyncio

POSTGRES_URL = os.getenv("TIANSHU_TEST_POSTGRES_URL")
if not POSTGRES_URL:
    pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL migration tests", allow_module_level=True)


def _seed_pre_0004_with_duplicates(schema: str) -> None:
    """Build a DB at revision 0003 with duplicate active rows per thread.

    Uses a synchronous engine so the seed is independent of the async engine
    under test. ``Base.metadata.create_all`` produces the full current schema
    (including the partial unique index), so we drop just the unique index to
    land in the dirty state the migration's dedupe pass targets: a versioned
    DB at 0003 where duplicate active rows per thread can coexist. We then
    stamp at 0003 and insert the duplicates via the ORM (so Python-side
    defaults populate). ``search_path`` is pinned to the isolated schema.
    """
    sync_engine = sa.create_engine(
        _sync_url(),
        connect_args={"options": f"-csearch_path={schema}"},
    )
    try:
        Base.metadata.create_all(sync_engine)
        with sync_engine.begin() as conn:
            # Drop only the partial unique index — this is the invariant the
            # migration rebuilds, and its absence is what permits duplicate
            # active rows to exist in the first place.
            conn.execute(sa.text("DROP INDEX IF EXISTS uq_runs_thread_active"))
            # Stamp at 0003 so bootstrap takes the versioned branch and runs
            # ``alembic upgrade head`` (which is what executes 0004.upgrade()).
            conn.execute(sa.text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(sa.text("DELETE FROM alembic_version"))
            conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0003_scheduled_tasks')"))

        base = datetime.now(UTC)
        with Session(sync_engine) as session:
            session.add_all(
                [
                    RunRow(
                        run_id="run-old-a",
                        thread_id="thread-dup",
                        status="pending",
                        created_at=base,
                        updated_at=base,
                    ),
                    RunRow(
                        run_id="run-old-b",
                        thread_id="thread-dup",
                        status="running",
                        created_at=base + timedelta(seconds=10),
                        updated_at=base + timedelta(seconds=10),
                    ),
                    RunRow(
                        run_id="run-newest",
                        thread_id="thread-dup",
                        status="pending",
                        created_at=base + timedelta(seconds=60),
                        updated_at=base + timedelta(seconds=60),
                    ),
                    RunRow(
                        run_id="run-solo",
                        thread_id="thread-solo",
                        status="running",
                        created_at=base,
                        updated_at=base,
                    ),
                    RunRow(
                        run_id="run-success",
                        thread_id="thread-done",
                        status="success",
                        created_at=base,
                        updated_at=base,
                    ),
                ]
            )
            session.commit()
    finally:
        sync_engine.dispose()


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


def _fetch_runs(schema: str) -> dict[str, tuple[str, str | None]]:
    """Map run_id -> (status, error) for assertions."""
    import psycopg

    with psycopg.connect(os.environ["TIANSHU_TEST_POSTGRES_URL"]) as conn:
        rows = conn.execute(
            f'SELECT run_id, status, error FROM "{schema}".runs'
        ).fetchall()
    return {run_id: (status, error) for run_id, status, error in rows}


def _index_exists(schema: str, index_name: str) -> bool:
    import psycopg

    with psycopg.connect(os.environ["TIANSHU_TEST_POSTGRES_URL"]) as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_indexes WHERE schemaname = %s AND indexname = %s",
            (schema, index_name),
        ).fetchone()
    return row is not None


def _fetch_alembic_version(schema: str) -> str:
    import psycopg

    with psycopg.connect(os.environ["TIANSHU_TEST_POSTGRES_URL"]) as conn:
        row = conn.execute(f'SELECT version_num FROM "{schema}".alembic_version').fetchone()
    return row[0]


def _fetch_dupe_threads(schema: str) -> list[tuple[str, int]]:
    import psycopg

    with psycopg.connect(os.environ["TIANSHU_TEST_POSTGRES_URL"]) as conn:
        return conn.execute(
            f'SELECT thread_id, COUNT(*) FROM "{schema}".runs WHERE status IN (\'pending\', \'running\') GROUP BY thread_id HAVING COUNT(*) > 1'
        ).fetchall()


async def test_migration_dedupes_duplicate_active_rows_before_unique_index() -> None:
    import uuid

    import psycopg

    schema = f"pgtest_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(POSTGRES_URL or "", autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    try:
        _seed_pre_0004_with_duplicates(schema)

        await init_engine_from_config(
            DatabaseConfig(
                backend="postgres",
                postgres_url=POSTGRES_URL or "",
                postgres_schema=schema,
            )
        )

        try:
            runs = _fetch_runs(schema)

            # Newest active row on the duplicated thread survives unchanged.
            assert runs["run-newest"] == ("pending", None)

            # Older duplicate active rows are cancelled with an explanatory error.
            assert runs["run-old-a"][0] == "error"
            assert "uq_runs_thread_active" in (runs["run-old-a"][1] or "")
            assert runs["run-old-b"][0] == "error"
            assert "uq_runs_thread_active" in (runs["run-old-b"][1] or "")

            # Untouched threads: single active row stays active, terminal rows stay terminal.
            assert runs["run-solo"] == ("running", None)
            assert runs["run-success"] == ("success", None)

            # The partial unique index was successfully created — the upgrade did
            # not abort with ``UNIQUE constraint failed``.
            assert _index_exists(schema, "uq_runs_thread_active")
            assert _index_exists(schema, "ix_runs_lease")

            # Bootstrap upgrades through the later revisions after 0004.
            assert _fetch_alembic_version(schema) == "0014_workspaces"

            # Sanity: the invariant the index enforces is now true — at most one
            # active row per thread.
            assert _fetch_dupe_threads(schema) == []
        finally:
            await close_engine()
    finally:
        with psycopg.connect(POSTGRES_URL or "", autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
