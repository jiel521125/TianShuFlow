"""Regression test for migration ``0007_scheduled_run_active_index`` dedupe pass.

End-to-end shape (mirrors ``test_migration_0004_run_ownership_dedupe``):

1. Hand-build a PostgreSQL DB (isolated schema) that mirrors a real pre-0007
   deployment that ran the racy ``dispatch_task`` check-then-insert and
   accumulated duplicate active rows per ``task_id`` (the exact dirty state
   the partial unique index targets).
2. Stamp it at ``0006_agents`` so ``bootstrap_schema`` takes the
   versioned branch and runs ``alembic upgrade head``.
3. Insert two+ queued/running rows for the same ``task_id`` (only possible
   because the partial unique index does not exist yet).
4. Run ``init_engine`` (the FastAPI lifespan entry point), which routes through
   ``bootstrap_schema`` -> ``upgrade head`` -> ``0007.upgrade()``.
5. Verify the migration superseded the older duplicates (set them to
   ``interrupted`` with an explanatory message + ``finished_at``), kept the
   newest active row, and successfully built the ``uq_scheduled_task_run_active``
   partial unique index.

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
from tianshu.persistence.scheduled_task_runs.model import ScheduledTaskRunRow

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


def _seed_pre_0007_with_duplicates(schema: str) -> None:
    """Build a DB at revision 0006 with duplicate active rows per task_id.

    Uses a synchronous engine so the seed is independent of the async engine
    under test. ``Base.metadata.create_all`` produces the full current schema
    (including the partial unique index), so we drop just that index to land
    in the dirty state the migration's dedupe pass targets, then stamp at 0006
    and insert the duplicates via the ORM so Python-side defaults populate.
    ``search_path`` is pinned to the isolated schema.
    """
    sync_engine = sa.create_engine(
        _sync_url(),
        connect_args={"options": f"-csearch_path={schema}"},
    )
    try:
        Base.metadata.create_all(sync_engine)
        with sync_engine.begin() as conn:
            # Drop only the partial unique index — its absence is what permits
            # duplicate active rows to exist in the first place.
            conn.execute(sa.text("DROP INDEX IF EXISTS uq_scheduled_task_run_active"))
            # Stamp at 0006 so bootstrap takes the versioned branch and runs
            # ``alembic upgrade head`` (which is what executes 0007.upgrade()).
            conn.execute(sa.text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(sa.text("DELETE FROM alembic_version"))
            conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0006_agents')"))

        base = datetime.now(UTC)
        with Session(sync_engine) as session:
            session.add_all(
                [
                    # Task with three active rows: two older duplicates + newest.
                    ScheduledTaskRunRow(
                        id="run-old-a",
                        task_id="task-dup",
                        thread_id="thread-a",
                        scheduled_for=base,
                        trigger="scheduled",
                        status="queued",
                        created_at=base,
                    ),
                    ScheduledTaskRunRow(
                        id="run-old-b",
                        task_id="task-dup",
                        thread_id="thread-b",
                        scheduled_for=base,
                        trigger="manual",
                        status="running",
                        created_at=base + timedelta(seconds=10),
                    ),
                    ScheduledTaskRunRow(
                        id="run-newest",
                        task_id="task-dup",
                        thread_id="thread-c",
                        scheduled_for=base,
                        trigger="scheduled",
                        status="queued",
                        created_at=base + timedelta(seconds=60),
                    ),
                    # A single-active-row task: must be left untouched.
                    ScheduledTaskRunRow(
                        id="run-solo",
                        task_id="task-solo",
                        thread_id="thread-solo",
                        scheduled_for=base,
                        trigger="scheduled",
                        status="running",
                        created_at=base,
                    ),
                    # A terminal row: must stay terminal.
                    ScheduledTaskRunRow(
                        id="run-done",
                        task_id="task-done",
                        thread_id="thread-done",
                        scheduled_for=base,
                        trigger="scheduled",
                        status="success",
                        created_at=base,
                    ),
                ]
            )
            session.commit()
    finally:
        sync_engine.dispose()


def _fetch_runs(schema: str) -> dict[str, tuple[str, str | None, str | None]]:
    """Map id -> (status, error, finished_at) for assertions."""
    import psycopg

    with psycopg.connect(os.environ["TIANSHU_TEST_POSTGRES_URL"]) as conn:
        rows = conn.execute(
            f'SELECT id, status, error, finished_at FROM "{schema}".scheduled_task_runs'
        ).fetchall()
    return {run_id: (status, error, finished_at) for run_id, status, error, finished_at in rows}


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


def _fetch_dupe_tasks(schema: str) -> list[tuple[str, int]]:
    import psycopg

    with psycopg.connect(os.environ["TIANSHU_TEST_POSTGRES_URL"]) as conn:
        return conn.execute(
            f'SELECT task_id, COUNT(*) FROM "{schema}".scheduled_task_runs WHERE status IN (\'queued\', \'running\') GROUP BY task_id HAVING COUNT(*) > 1'
        ).fetchall()


async def test_migration_supersedes_duplicate_active_runs_before_unique_index() -> None:
    import uuid

    import psycopg

    schema = f"pgtest_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(POSTGRES_URL or "", autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    try:
        _seed_pre_0007_with_duplicates(schema)

        await init_engine_from_config(
            DatabaseConfig(
                backend="postgres",
                postgres_url=POSTGRES_URL or "",
                postgres_schema=schema,
            )
        )

        try:
            runs = _fetch_runs(schema)

            # Newest active row on the duplicated task survives unchanged.
            assert runs["run-newest"][0] == "queued"
            assert runs["run-newest"][1] is None

            # Older duplicate active rows are superseded with an explanatory error
            # and a finished_at timestamp (mark_stale_active_runs orphan semantics).
            for run_id in ("run-old-a", "run-old-b"):
                status, error, finished_at = runs[run_id]
                assert status == "interrupted", (run_id, status)
                assert "uq_scheduled_task_run_active" in (error or ""), (run_id, error)
                assert finished_at is not None, run_id

            # Untouched tasks: single active row stays active, terminal stays terminal.
            assert runs["run-solo"][0] == "running"
            assert runs["run-done"][0] == "success"

            # The partial unique index was successfully created — the upgrade did
            # not abort with ``UNIQUE constraint failed`` / ``could not create
            # unique index``.
            assert _index_exists(schema, "uq_scheduled_task_run_active")

            # Bootstrap upgrades through the later revisions after 0007.
            assert _fetch_alembic_version(schema) == "0014_workspaces"

            # Sanity: the invariant the index enforces now holds — at most one
            # active row per task_id.
            assert _fetch_dupe_tasks(schema) == []
        finally:
            await close_engine()
    finally:
        with psycopg.connect(POSTGRES_URL or "", autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')