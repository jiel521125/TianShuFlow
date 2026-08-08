"""Concurrency safety tests for ``bootstrap_schema``.

The contract: N concurrent callers against the same DB always converge to
``alembic_version == head`` without exceptions and without duplicate schema
mutations.

We model concurrency at the *async-task* level here (multiple coroutines
inside one process). Cross-process serialisation falls through to
PostgreSQL's advisory lock (true cross-process) plus the idempotent
revision helpers.

Requires ``TIANSHU_TEST_POSTGRES_URL`` (the repo convention for live
PostgreSQL tests); skipped otherwise.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

import tianshu.persistence.models  # noqa: F401
from tianshu.persistence import bootstrap as bootstrap_mod
from tianshu.persistence.bootstrap import bootstrap_schema

pytestmark = pytest.mark.asyncio

POSTGRES_URL = os.getenv("TIANSHU_TEST_POSTGRES_URL")

HEAD = bootstrap_mod._get_head_revision()


def _new_schema() -> str:
    return f"bootstrap_concurrency_{uuid.uuid4().hex[:12]}"


def _engine(schema: str):
    assert POSTGRES_URL
    return create_async_engine(
        POSTGRES_URL,
        connect_args={"server_settings": {"search_path": schema}},
    )


def _create_schema(schema: str) -> None:
    assert POSTGRES_URL
    import psycopg

    with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')


def _drop_schema(schema: str) -> None:
    assert POSTGRES_URL
    import psycopg

    with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


async def _alembic_version(engine) -> str | None:
    async with engine.connect() as conn:
        row = await conn.execute(sa.text("SELECT version_num FROM alembic_version"))
        return row.scalar()


async def _runs_columns(engine) -> set[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda c: {col["name"] for col in sa.inspect(c).get_columns("runs")})


async def test_two_concurrent_bootstrap_callers_converge() -> None:
    if not POSTGRES_URL:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL bootstrap concurrency tests")
    schema = _new_schema()
    _create_schema(schema)
    engine = _engine(schema)
    try:
        await asyncio.gather(
            bootstrap_schema(engine, backend="postgres", postgres_schema=schema),
            bootstrap_schema(engine, backend="postgres", postgres_schema=schema),
        )
        assert await _alembic_version(engine) == HEAD
        assert "token_usage_by_model" in await _runs_columns(engine)
    finally:
        await engine.dispose()
        _drop_schema(schema)


async def test_five_concurrent_bootstrap_callers_converge() -> None:
    if not POSTGRES_URL:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL bootstrap concurrency tests")
    schema = _new_schema()
    _create_schema(schema)
    engine = _engine(schema)
    try:
        await asyncio.gather(
            *(bootstrap_schema(engine, backend="postgres", postgres_schema=schema) for _ in range(5))
        )
        assert await _alembic_version(engine) == HEAD
    finally:
        await engine.dispose()
        _drop_schema(schema)


async def test_cancelled_caller_does_not_block_others() -> None:
    """Cancelling one task mid-bootstrap must not strand the lock or the DB.

    After the cancel, a subsequent ``bootstrap_schema`` call must still reach
    head.
    """
    if not POSTGRES_URL:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL bootstrap concurrency tests")
    schema = _new_schema()
    _create_schema(schema)
    engine = _engine(schema)
    try:
        task = asyncio.create_task(bootstrap_schema(engine, backend="postgres", postgres_schema=schema))
        # Give the event loop a turn so the task can start; then cancel.
        await asyncio.sleep(0)
        task.cancel()
        # Cancelled task may have raced past the lock; swallow either outcome.
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

        # Lock must be free for the next caller.
        await bootstrap_schema(engine, backend="postgres", postgres_schema=schema)
        assert await _alembic_version(engine) == HEAD
    finally:
        await engine.dispose()
        _drop_schema(schema)


async def test_late_caller_after_head_is_noop(monkeypatch) -> None:
    """When the first caller leaves the DB at head, the second observes
    'versioned' and skips create_all / stamp -- it only runs upgrade head,
    which is alembic-no-op.

    We use a monkeypatched ``_upgrade`` counter to assert the second caller's
    upgrade ran but did no real work (no new revision applied).
    """
    if not POSTGRES_URL:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL bootstrap concurrency tests")
    schema = _new_schema()
    _create_schema(schema)
    engine = _engine(schema)
    try:
        # First caller: empty branch.
        await bootstrap_schema(engine, backend="postgres", postgres_schema=schema)
        first_version = await _alembic_version(engine)
        assert first_version == HEAD

        upgrade_calls: list[str] = []
        original_upgrade = bootstrap_mod._upgrade

        def counting_upgrade(cfg, rev: str) -> None:
            upgrade_calls.append(rev)
            original_upgrade(cfg, rev)

        monkeypatch.setattr(bootstrap_mod, "_upgrade", counting_upgrade)

        # Second caller: versioned branch -> calls _upgrade('head').
        await bootstrap_schema(engine, backend="postgres", postgres_schema=schema)
        assert upgrade_calls == ["head"]
        assert await _alembic_version(engine) == HEAD
    finally:
        await engine.dispose()
        _drop_schema(schema)


async def test_slow_upgrade_does_not_corrupt_concurrent_state(monkeypatch) -> None:
    """Inject a delay into the upgrade path; concurrent callers must still
    converge to head with no exceptions."""
    if not POSTGRES_URL:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL bootstrap concurrency tests")
    schema = _new_schema()
    _create_schema(schema)
    engine = _engine(schema)
    try:
        original_upgrade = bootstrap_mod._upgrade

        def slow_upgrade(cfg, rev: str) -> None:
            import time  # noqa: PLC0415

            time.sleep(0.2)
            original_upgrade(cfg, rev)

        monkeypatch.setattr(bootstrap_mod, "_upgrade", slow_upgrade)

        await asyncio.gather(
            bootstrap_schema(engine, backend="postgres", postgres_schema=schema),
            bootstrap_schema(engine, backend="postgres", postgres_schema=schema),
            bootstrap_schema(engine, backend="postgres", postgres_schema=schema),
        )
        assert await _alembic_version(engine) == HEAD
    finally:
        await engine.dispose()
        _drop_schema(schema)
