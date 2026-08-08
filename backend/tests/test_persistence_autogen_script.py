"""Tests for ``scripts/_autogen_revision.py`` (``make migrate-rev``).

The script must work without any pre-existing data directory -- the failure
mode reported as P2. The fix: the script builds its own temporary Postgres
schema by running the existing alembic chain to head and runs autogenerate
against THAT, instead of relying on a persistent DB that may be at an
unknown revision.

Requires ``TIANSHU_TEST_POSTGRES_URL`` (the repo convention for live
PostgreSQL tests); skipped otherwise.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa

import tianshu.persistence.models  # noqa: F401
from tianshu.persistence.base import Base

POSTGRES_URL = os.getenv("TIANSHU_TEST_POSTGRES_URL")


@pytest.fixture(scope="module")
def autogen_module():
    """Load ``scripts/_autogen_revision.py`` as an importable module.

    The file lives outside the package tree (under ``backend/scripts/``) so we
    load it directly via ``spec_from_file_location``.
    """
    script_path = Path(__file__).resolve().parents[1] / "scripts/_autogen_revision.py"
    assert script_path.exists(), f"missing autogen script at {script_path}"
    spec = importlib.util.spec_from_file_location("_autogen_revision_under_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _skip_without_postgres() -> None:
    if not POSTGRES_URL:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL autogen tests")


def test_autogen_builds_temp_schema_at_head(autogen_module, monkeypatch) -> None:
    """The temp-schema builder must succeed without a pre-existing data dir."""
    _skip_without_postgres()
    import tempfile  # noqa: PLC0415

    workdir = tempfile.mkdtemp(prefix="tianshu-autogen-test-")
    monkeypatch.chdir(workdir)
    # Sanity: this directory has no ``./data/``.
    assert not os.path.exists("data")

    url, schema = autogen_module._build_temp_schema_at_head()
    assert schema.startswith("autogen_"), f"unexpected schema name: {schema}"
    try:
        # The temp schema should exist on the live server.
        import psycopg  # noqa: PLC0415

        with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
            row = conn.execute(
                "SELECT count(*) FROM information_schema.schemata WHERE schema_name = %s",
                (schema,),
            ).fetchone()
            assert row[0] == 1, f"temp schema not created: {schema}"
    finally:
        autogen_module._drop_schema(url, schema)


def test_autogen_temp_db_is_at_head(autogen_module) -> None:
    """The temp schema must be at head, so the autogenerate diff against
    current models is empty (or only reflects intentional, in-progress model
    changes)."""
    _skip_without_postgres()
    url, schema = autogen_module._build_temp_schema_at_head()
    try:
        import psycopg  # noqa: PLC0415

        with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
            row = conn.execute(
                """
                SELECT version_num FROM alembic_version
                WHERE EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = 'alembic_version'
                )
                """,
                (schema,),
            ).fetchone()
            assert row is not None, "autogen temp schema has no alembic_version row -- bootstrap failed"
            # head is whatever the script tree currently says; we just assert it's there.
            assert row[0]
    finally:
        autogen_module._drop_schema(url, schema)


def test_autogen_temp_db_comes_from_migration_history_not_current_metadata(autogen_module) -> None:
    """Pending ORM changes must remain visible to autogenerate.

    If the helper accidentally uses runtime ``bootstrap_schema`` /
    ``Base.metadata.create_all`` again, this probe table would be created in
    the temp DB and the test would fail. A temp DB built from alembic history
    only contains objects that committed revisions know how to create.
    """
    _skip_without_postgres()
    probe_name = "__autogen_probe_pending_migration__"
    probe_table = sa.Table(probe_name, Base.metadata, sa.Column("id", sa.Integer, primary_key=True))
    try:
        url, schema = autogen_module._build_temp_schema_at_head()
        try:
            import psycopg  # noqa: PLC0415

            with psycopg.connect(POSTGRES_URL, autocommit=True) as conn:
                row = conn.execute(
                    """
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                    """,
                    (schema, probe_name),
                ).fetchone()
                assert row[0] == 0, "temp DB was built from current ORM metadata instead of migration history"
        finally:
            autogen_module._drop_schema(url, schema)
    finally:
        Base.metadata.remove(probe_table)
