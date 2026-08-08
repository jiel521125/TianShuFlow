"""Regression: ``bootstrap_schema`` offloads ``alembic.command.stamp`` /
``alembic.command.upgrade`` via ``asyncio.to_thread``.

The alembic commands are synchronous: they open their own engine and execute
DDL. Calling them directly on the FastAPI lifespan event loop would block --
exactly the failure mode of the issue chain that motivated the hybrid
bootstrap (sync IO on the loop = silent stalls / timeouts).

Anchor strategy
---------------

This test installs a spy on ``asyncio.to_thread`` and confirms that the
two alembic entry points -- ``_stamp`` and ``_upgrade`` from
``bootstrap_schema`` -- are dispatched through it, not invoked inline. If a
future refactor inlines either call, the spy records zero invocations for
that function and the assertion fails.

Requires ``TIANSHU_TEST_POSTGRES_URL`` (the repo convention for live
PostgreSQL tests); skipped otherwise.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

import tianshu.persistence.models  # noqa: F401
from tianshu.persistence import bootstrap as bootstrap_mod

pytestmark = pytest.mark.asyncio

POSTGRES_URL = os.getenv("TIANSHU_TEST_POSTGRES_URL")


@pytest.mark.allow_blocking_io
async def test_bootstrap_offloads_alembic_stamp_and_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stamp + upgrade must go through ``asyncio.to_thread``.

    Marked ``allow_blocking_io`` so the strict Blockbuster gate does not flag
    incidental blocking IO in test-fixture setup (engine creation paths,
    schema creation). The point of this test is the
    ``asyncio.to_thread`` wrapping invariant, which the spy below checks
    deterministically.
    """
    if not POSTGRES_URL:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL bootstrap tests")

    import psycopg

    schema = f"bootstrap_spy_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')

    seen: list[str] = []

    original_to_thread = asyncio.to_thread

    async def spy_to_thread(func, *args, **kwargs):
        seen.append(getattr(func, "__name__", repr(func)))
        return await original_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(bootstrap_mod.asyncio, "to_thread", spy_to_thread)

    # Use a real PostgreSQL engine so alembic actually runs stamp + upgrade.
    engine = create_async_engine(
        POSTGRES_URL,
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        # Empty branch -> create_all + stamp head. ``_stamp`` must be offloaded.
        await bootstrap_mod.bootstrap_schema(engine, backend="postgres", postgres_schema=schema)
        assert "_stamp" in seen, f"_stamp not offloaded; saw: {seen}"

        # Re-run -> versioned branch -> upgrade head (no-op at head). ``_upgrade`` must be offloaded.
        seen.clear()
        await bootstrap_mod.bootstrap_schema(engine, backend="postgres", postgres_schema=schema)
        assert "_upgrade" in seen, f"_upgrade not offloaded; saw: {seen}"
    finally:
        await engine.dispose()
        with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
