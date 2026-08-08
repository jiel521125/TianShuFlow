"""Agent-storage backend selection, startup validation, and the db importer."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest
import yaml
from sqlalchemy import create_engine

from app.gateway.deps import _validate_agent_storage
from tianshu.config.agent_storage_config import AgentStorageConfig
from tianshu.config.app_config import reset_app_config
from tianshu.config.database_config import DatabaseConfig
from tianshu.persistence.agents import get_agent_store, make_agent_store
from tianshu.persistence.agents.file import FileAgentStore
from tianshu.persistence.agents.model import AgentRow
from tianshu.persistence.agents.sql import SqlAgentStore
from tianshu.persistence.base import Base


def _cfg(agent_backend: str, db_backend: str, postgres_url: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        agent_storage=AgentStorageConfig(backend=agent_backend),
        database=DatabaseConfig(backend=db_backend, postgres_url=postgres_url),
    )


# -- make_agent_store selection --------------------------------------------


def test_file_is_the_default_backend():
    assert isinstance(make_agent_store(_cfg("file", "memory")), FileAgentStore)


def test_db_backend_builds_sql_store():
    # Construction only builds a sessionmaker; no connection is opened, so a
    # placeholder URL is enough to pin the store-type selection.
    assert isinstance(make_agent_store(_cfg("db", "postgres", "postgresql://u:p@h:5432/db")), SqlAgentStore)


def test_db_backend_on_memory_database_is_rejected():
    with pytest.raises(ValueError, match="requires database.backend"):
        make_agent_store(_cfg("db", "memory"))


# -- startup validation (deps) ---------------------------------------------


def test_validation_rejects_db_on_memory_database():
    with pytest.raises(SystemExit):
        _validate_agent_storage(_cfg("db", "memory"))


def test_validation_allows_file_and_db_on_postgres():
    _validate_agent_storage(_cfg("file", "memory"))  # no raise
    _validate_agent_storage(_cfg("db", "postgres", "postgresql://u:p@h:5432/db"))  # no raise


def test_validation_warns_on_file_under_multiworker_postgres(monkeypatch, caplog):
    monkeypatch.setenv("GATEWAY_WORKERS", "4")
    cfg = SimpleNamespace(
        agent_storage=AgentStorageConfig(backend="file"),
        database=DatabaseConfig(backend="postgres", postgres_url="postgresql://u:p@h/db"),
    )
    with caplog.at_level("WARNING"):
        _validate_agent_storage(cfg)
    assert any("not visible across workers" in r.message for r in caplog.records)


# -- importer: file layout → db --------------------------------------------


@pytest.fixture()
def file_home(tmp_path, monkeypatch):
    """Root the file store at a temp TIAN_SHU_HOME with two seeded agents."""
    monkeypatch.setenv("TIAN_SHU_HOME", str(tmp_path))
    from tianshu.config import paths as paths_module

    monkeypatch.setattr(paths_module, "_paths", None)
    fs = FileAgentStore()
    fs.create("reviewer", {"name": "reviewer", "description": "reviews"}, "review soul", user_id="u1")
    fs.create("planner", {"name": "planner", "description": "plans", "model": "m1"}, "plan soul", user_id="u2")
    return tmp_path


def _clean_test_user_agents(url: str) -> None:
    """Delete agent rows for the test-only users (``u1``/``u2``).

    ``AgentRow`` lives in the ``tianshu`` schema, and the store isolates data
    by ``user_id`` — every read/write is scoped to the effective user. These
    tests only ever touch the dedicated ``u1``/``u2`` users, so deleting those
    users' rows before/after each test keeps assertions deterministic without
    touching other users' data (e.g. the ``default`` seed agents).
    """
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        if conn.execute("SELECT to_regclass('tianshu.agents')").fetchone()[0] is None:
            return
        conn.execute("DELETE FROM tianshu.agents WHERE user_id IN ('u1', 'u2')")


@pytest.fixture()
def pg_agent_store_cfg():
    """Postgres ``database`` config for the sync db agent-store tests.

    Synchronous analogue of the ``pg_test_engine`` fixture for the sync
    ``SqlAgentStore`` path (the importer and the db agent store are
    synchronous). The store isolates by ``user_id``; the fixture cleans the
    dedicated ``u1``/``u2`` rows before and after each test. Skipped unless
    ``TIANSHU_TEST_POSTGRES_URL`` is set (the repo convention for
    live-PostgreSQL tests).
    """
    url = os.getenv("TIANSHU_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set TIANSHU_TEST_POSTGRES_URL to run live PostgreSQL tests")

    _clean_test_user_agents(url)
    try:
        yield SimpleNamespace(
            agent_storage=AgentStorageConfig(backend="db"),
            database=DatabaseConfig(backend="postgres", postgres_url=url, postgres_schema="tianshu"),
        )
    finally:
        _clean_test_user_agents(url)


def _patch_importer(monkeypatch, cfg):
    import scripts.migrate_agents_to_db as importer

    async def _noop_init(_):
        return None

    # Ensure the ``agents`` table exists (stand in for the Alembic bootstrap
    # the real run does). ``AgentRow`` is bound to the ``tianshu`` schema;
    # ``list_all()`` is the only cross-user read, so the per-test assertions
    # filter to the dedicated ``u1``/``u2`` users (see ``pg_agent_store_cfg``).
    engine = create_engine(cfg.database.app_sync_sqlalchemy_url)
    Base.metadata.create_all(engine, tables=[AgentRow.__table__])
    engine.dispose()

    monkeypatch.setattr(importer, "get_app_config", lambda: cfg)
    monkeypatch.setattr("tianshu.persistence.engine.init_engine_from_config", _noop_init)
    # ``SqlAgentStore._build_engine`` resolves the schema from the current app
    # config (imported fresh inside the function) and caches sync engines by
    # URL. Pin the schema to the shared one and start from a clean cache so an
    # engine built for a previous test's config doesn't leak in.
    monkeypatch.setattr("tianshu.persistence.agents.sql._engines", {})
    monkeypatch.setattr("tianshu.config.app_config.peek_current_app_config", lambda: cfg)
    return importer


def test_importer_copies_all_agents_into_db(file_home, monkeypatch, pg_agent_store_cfg):
    cfg = pg_agent_store_cfg
    importer = _patch_importer(monkeypatch, cfg)
    monkeypatch.setattr(sys, "argv", ["migrate_agents_to_db"])

    assert importer.main() == 0

    dest = SqlAgentStore(cfg.database.app_sync_sqlalchemy_url)
    assert dest.get("reviewer", user_id="u1").description == "reviews"
    assert dest.get_soul("reviewer", user_id="u1") == "review soul"
    assert dest.get("planner", user_id="u2").model == "m1"


def test_importer_is_idempotent(file_home, monkeypatch, pg_agent_store_cfg):
    cfg = pg_agent_store_cfg
    importer = _patch_importer(monkeypatch, cfg)
    monkeypatch.setattr(sys, "argv", ["migrate_agents_to_db"])

    assert importer.main() == 0
    # Second run must not raise on the already-present rows.
    assert importer.main() == 0
    dest = SqlAgentStore(cfg.database.app_sync_sqlalchemy_url)
    # Count only the importer's users: rows are isolated by ``user_id`` and
    # the table may hold rows for other users (seed agents, other tests).
    assert sum(1 for r in dest.list_all() if r[0] in ("u1", "u2")) == 2


def test_importer_dry_run_writes_nothing(file_home, monkeypatch, pg_agent_store_cfg):
    cfg = pg_agent_store_cfg
    importer = _patch_importer(monkeypatch, cfg)
    monkeypatch.setattr(sys, "argv", ["migrate_agents_to_db", "--dry-run"])

    assert importer.main() == 0
    dest = SqlAgentStore(cfg.database.app_sync_sqlalchemy_url)
    assert sum(1 for r in dest.list_all() if r[0] in ("u1", "u2")) == 0


def test_read_free_functions_dispatch_to_db_backend(file_home, monkeypatch, pg_agent_store_cfg):
    """The headline invariant: under the db backend the standard read path (the
    same free functions the per-run agent build calls) resolves from the shared
    DB, not from node-local files — so on-disk agents are invisible and db agents
    are visible everywhere."""
    cfg = pg_agent_store_cfg
    _patch_importer(monkeypatch, cfg)  # creates the schema
    monkeypatch.setattr("tianshu.config.app_config.get_app_config", lambda: cfg)

    from tianshu.config.agents_config import list_custom_agents, load_agent_config, load_agent_soul

    # The file store seeded 'reviewer'/'planner' on disk; the db is empty, so
    # the free functions (now db-backed) do not see them.
    assert list_custom_agents(user_id="u1") == []
    with pytest.raises(FileNotFoundError):
        load_agent_config("reviewer", user_id="u1")

    # An agent written to the shared db is visible through the same free functions.
    SqlAgentStore(cfg.database.app_sync_sqlalchemy_url).create("dbonly", {"name": "dbonly", "description": "shared"}, "db soul", user_id="u1")
    assert [c.name for c in list_custom_agents(user_id="u1")] == ["dbonly"]
    assert load_agent_config("dbonly", user_id="u1").description == "shared"
    assert load_agent_soul("dbonly", user_id="u1") == "db soul"


def test_file_create_race_maps_file_exists_to_agent_exists(tmp_path, monkeypatch):
    # TOCTOU: the existence guard passes (no agent yet), but a concurrent create
    # wins the race so mkdir(exist_ok=False) raises FileExistsError. The store
    # must translate that to AgentExistsError so the router returns 409, not a
    # generic 500 — matching SqlAgentStore's IntegrityError path.
    import pathlib

    from tianshu.persistence.agents.base import AgentExistsError

    monkeypatch.setenv("TIAN_SHU_HOME", str(tmp_path))
    from tianshu.config import paths as paths_module

    monkeypatch.setattr(paths_module, "_paths", None)

    def _racing_mkdir(self, *args, **kwargs):
        raise FileExistsError(str(self))

    monkeypatch.setattr(pathlib.Path, "mkdir", _racing_mkdir)

    fs = FileAgentStore()
    with pytest.raises(AgentExistsError):
        fs.create("racy", {"name": "racy"}, "soul", user_id="u1")


# -- graph-subprocess config resolution (db backend's core cross-process invariant) --


def _write_min_config(path, extra: dict) -> None:
    """Minimal but valid config.yaml (sandbox + models are the only hard requirements)."""
    doc = {
        "sandbox": {"use": "tianshu.sandbox.local:LocalSandboxProvider"},
        "models": [{"name": "m", "use": "langchain_openai:ChatOpenAI", "model": "gpt-test"}],
        **extra,
    }
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_get_agent_store_resolves_db_backend_from_on_disk_config(tmp_path, monkeypatch):
    """Pins the db backend's headline cross-process guarantee.

    The per-run agent build runs in the graph subprocess, a different process
    from the gateway; its db visibility holds only because ``get_agent_store()``
    resolves ``agent_storage.backend: db`` from the real on-disk ``config.yaml``
    there (not a monkeypatched stub) rather than silently falling back to
    node-local ``file``. Existing coverage monkeypatches ``get_app_config``;
    this drives the genuine file-resolution path a fresh process would take.
    """
    cfg_path = tmp_path / "config.yaml"
    _write_min_config(
        cfg_path,
        {
            "agent_storage": {"backend": "db"},
            "database": {
                "backend": "postgres",
                "postgres_url": "postgresql://postgres:postgres@localhost:5432/tianshu",
                "postgres_schema": "tianshu_test_resolve",
            },
        },
    )
    monkeypatch.setenv("TIAN_SHU_CONFIG_PATH", str(cfg_path))
    try:
        reset_app_config()  # force a fresh read from the on-disk file
        assert isinstance(get_agent_store(), SqlAgentStore)
    finally:
        reset_app_config()  # don't leak the custom config into other tests


def test_get_agent_store_falls_back_to_file_without_config(tmp_path, monkeypatch):
    """The ``except -> file`` fallback is for genuinely unresolvable config only
    (CLI/tests); it must not fire when a config exists — that asymmetry is what
    keeps a misconfigured graph process from silently downgrading db to file."""
    monkeypatch.setenv("TIAN_SHU_CONFIG_PATH", str(tmp_path / "does-not-exist.yaml"))
    try:
        reset_app_config()
        assert isinstance(get_agent_store(), FileAgentStore)
    finally:
        reset_app_config()
