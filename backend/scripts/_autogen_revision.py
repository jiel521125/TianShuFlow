"""Generate a new alembic revision against an ephemeral Postgres schema.

Used by ``make migrate-rev MSG="..."``. Avoids two pitfalls:

1. A persistent DB might be at an unknown revision (or at no revision at all),
   producing a noisy autogenerate diff that mixes "real" changes with
   accidentally-detected drift.
2. Reusing the live database would autogenerate drift from unrelated local
   changes.

This script creates a *fresh* temporary schema in the configured Postgres
database, runs the existing alembic chain to ``head`` against it, then runs
``alembic revision --autogenerate`` against that. The temp schema must be
built from migration history -- not from ``Base.metadata.create_all`` -- so
newly edited ORM fields that do not yet have a revision remain visible to
autogenerate as a real diff.

The generated file lands in
``packages/harness/tianshu/persistence/migrations/versions/`` -- exactly
where alembic puts it by default -- and the temporary schema is dropped
when the run finishes. Review the generated revision and switch raw
``op.add_column`` / ``op.drop_column`` calls to the idempotent helpers in
``migrations/_helpers.py`` before committing.

Run from the ``backend/`` directory:
    PYTHONPATH=. uv run python scripts/_autogen_revision.py "MESSAGE"
or via Makefile:
    make migrate-rev MSG="..."

The Postgres URL defaults to the local dev database
(``postgresql+asyncpg://postgres:postgres@localhost:5432/tianshu``); override
it with the ``TIANSHU_AUTOGEN_POSTGRES_URL`` environment variable.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import tianshu.persistence.models  # noqa: F401  -- registers ORM models with Base.metadata
from tianshu.persistence.bootstrap import _escape_url_for_alembic

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = BACKEND_DIR / "packages/harness/tianshu/persistence/migrations"

DEFAULT_POSTGRES_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/tianshu"


def _alembic_config(url: str, schema: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Shared with ``bootstrap._alembic_safe_url`` so the ConfigParser ``%``
    # interpolation rule lives in one place.
    cfg.set_main_option("sqlalchemy.url", _escape_url_for_alembic(url))
    # env.py pins the alembic-spawned engine's search_path to this schema so
    # both alembic_version and migration DDL land in the temp schema.
    cfg.set_main_option("tianshu_pg_schema", schema)
    return cfg


def _build_temp_schema_at_head() -> tuple[str, str]:
    """Create a throwaway Postgres schema upgraded to alembic head.

    Returns ``(url, schema)``. The caller must drop the schema when done.
    """
    base_url = os.environ.get("TIANSHU_AUTOGEN_POSTGRES_URL", DEFAULT_POSTGRES_URL)
    schema = f"autogen_{uuid.uuid4().hex[:8]}"

    async def _create() -> None:
        engine = create_async_engine(base_url)
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await engine.dispose()

    asyncio.run(_create())
    command.upgrade(_alembic_config(base_url, schema), "head")
    return base_url, schema


def _drop_schema(url: str, schema: str) -> None:
    async def _drop() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()

    asyncio.run(_drop())


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('usage: python scripts/_autogen_revision.py "describe the change"', file=sys.stderr)
        sys.exit(2)
    message = sys.argv[1]

    url, schema = _build_temp_schema_at_head()
    print(f"autogen: built temp schema at head: {schema} on {url}", file=sys.stderr)
    try:
        command.revision(_alembic_config(url, schema), message=message, autogenerate=True)
    finally:
        _drop_schema(url, schema)


if __name__ == "__main__":
    main()
