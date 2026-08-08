"""Unit tests for checkpointer config, packaging metadata, and factories."""

import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tianshu.config.app_config as app_config_module
from tianshu.config.checkpointer_config import (
    CheckpointerConfig,
    ensure_config_loaded,
    get_checkpointer_config,
    load_checkpointer_config_from_dict,
    set_checkpointer_config,
)
from tianshu.config.database_config import DatabaseConfig
from tianshu.runtime.checkpointer import get_checkpointer, reset_checkpointer
from tianshu.runtime.checkpointer.provider import POSTGRES_INSTALL
from tianshu.runtime.store import get_store, reset_store
from tianshu.runtime.store.provider import POSTGRES_STORE_INSTALL


@pytest.fixture(autouse=True)
def reset_state():
    """Reset singleton state before each test."""
    app_config_module._app_config = None
    set_checkpointer_config(None)
    reset_checkpointer()
    reset_store()
    yield
    app_config_module._app_config = None
    set_checkpointer_config(None)
    reset_checkpointer()
    reset_store()


class _BlockingSingletonContext:
    def __init__(self, value: object, entered: Event, release: Event, stats: dict[str, object]):
        self._value = value
        self._entered = entered
        self._release = release
        self._stats = stats

    def __enter__(self):
        with self._stats["lock"]:
            self._stats["enters"] += 1
            self._entered.set()
        assert self._release.wait(timeout=3), "timed out waiting to release singleton initialization"
        return self._value

    def __exit__(self, exc_type, exc, tb):
        with self._stats["lock"]:
            self._stats["exits"] += 1
        return False


class _BlockingSingletonFactory:
    def __init__(self):
        self.value = object()
        self.entered = Event()
        self.release = Event()
        self.stats = {"enters": 0, "exits": 0, "lock": Lock()}

    def context_manager(self, _config):
        return _BlockingSingletonContext(self.value, self.entered, self.release, self.stats)

    def enter_count(self) -> int:
        with self.stats["lock"]:
            return self.stats["enters"]

    def exit_count(self) -> int:
        with self.stats["lock"]:
            return self.stats["exits"]


class _TrackingLock:
    def __init__(self):
        self._lock = Lock()
        self.acquired = Event()

    def acquire(self, *args, **kwargs):
        acquired = self._lock.acquire(*args, **kwargs)
        if acquired:
            self.acquired.set()
        return acquired

    def release(self):
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False

    def locked(self) -> bool:
        return self._lock.locked()


def _call_getter_concurrently(getter, workers: int = 8) -> list[object]:
    ready = Barrier(workers + 1)

    def worker():
        ready.wait(timeout=3)
        return getter()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker) for _ in range(workers)]
        ready.wait(timeout=3)
        return [future.result(timeout=3) for future in futures]


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestCheckpointerConfig:
    def test_load_memory_config(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        config = get_checkpointer_config()
        assert config is not None
        assert config.type == "memory"
        assert config.connection_string is None

    def test_load_sqlite_config_is_rejected(self):
        """SQLite checkpointer type no longer exists in production."""
        with pytest.raises(Exception):
            load_checkpointer_config_from_dict({"type": "sqlite", "connection_string": "/tmp/test.db"})

    def test_load_postgres_config(self):
        load_checkpointer_config_from_dict({"type": "postgres", "connection_string": "postgresql://localhost/db"})
        config = get_checkpointer_config()
        assert config is not None
        assert config.type == "postgres"
        assert config.connection_string == "postgresql://localhost/db"
        assert config.postgres_schema == ""

    def test_postgres_schema_accepts_valid_identifier(self):
        config = CheckpointerConfig(type="postgres", connection_string="postgresql://localhost/db", postgres_schema="tianshu")
        assert config.postgres_schema == "tianshu"

    @pytest.mark.parametrize("schema", ["1abc", "a b", "a;b", "a-b", "a" * 64, 'a"b', "MySchema", "Orders", "Public"])
    def test_postgres_schema_rejects_invalid_identifier(self, schema):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CheckpointerConfig(type="postgres", connection_string="postgresql://localhost/db", postgres_schema=schema)

    def test_default_connection_string_is_none(self):
        config = CheckpointerConfig(type="memory")
        assert config.connection_string is None

    def test_set_config_to_none(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        set_checkpointer_config(None)
        assert get_checkpointer_config() is None

    def test_ensure_config_loaded_loads_app_config_when_uninitialized(self):
        def fake_get_app_config():
            load_checkpointer_config_from_dict({"type": "memory"})

        with patch("tianshu.config.app_config.get_app_config", side_effect=fake_get_app_config) as mock_get_app_config:
            ensure_config_loaded()

        mock_get_app_config.assert_called_once()
        config = get_checkpointer_config()
        assert config is not None
        assert config.type == "memory"

    def test_ensure_config_loaded_skips_explicit_config(self):
        load_checkpointer_config_from_dict({"type": "memory"})

        with patch("tianshu.config.app_config.get_app_config") as mock_get_app_config:
            ensure_config_loaded()

        mock_get_app_config.assert_not_called()

    def test_invalid_type_raises(self):
        with pytest.raises(Exception):
            load_checkpointer_config_from_dict({"type": "unknown"})

    def test_connection_string_description_matches_runtime_defaults(self):
        description = CheckpointerConfig.model_fields["connection_string"].description

        assert description is not None
        assert "Required for postgres" in description
        assert "postgresql://" in description


class TestHarnessPackaging:
    def test_pyproject_declares_postgres_extra(self):
        pyproject_path = Path(__file__).resolve().parents[1] / "packages" / "harness" / "pyproject.toml"
        data = tomllib.loads(pyproject_path.read_text())

        optional_dependencies = data["project"]["optional-dependencies"]
        assert "postgres" in optional_dependencies
        assert optional_dependencies["postgres"] == [
            "asyncpg>=0.29",
            "langgraph-checkpoint-postgres>=3.1.0,<3.2",
            "psycopg[binary]>=3.3.3",
            "psycopg-pool>=3.3.0",
        ]

    def test_workspace_pyproject_forwards_postgres_extra_to_harness(self):
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject_path.read_text())

        optional_dependencies = data["project"]["optional-dependencies"]
        assert optional_dependencies["postgres"] == ["tianshu-harness[postgres]"]

    def test_postgres_missing_dependency_messages_recommend_package_extra(self):
        assert "tianshu-harness[postgres]" in POSTGRES_INSTALL
        assert "tianshu-harness[postgres]" in POSTGRES_STORE_INSTALL
        assert "uv sync --all-packages --extra postgres" in POSTGRES_INSTALL
        assert "uv sync --all-packages --extra postgres" in POSTGRES_STORE_INSTALL


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestGetCheckpointer:
    def test_returns_in_memory_saver_when_not_configured(self):
        """get_checkpointer should return InMemorySaver when not configured."""
        from langgraph.checkpoint.memory import InMemorySaver

        with patch("tianshu.runtime.checkpointer.provider.get_app_config", side_effect=FileNotFoundError):
            cp = get_checkpointer()
        assert cp is not None
        assert isinstance(cp, InMemorySaver)

    def test_memory_returns_in_memory_saver(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        from langgraph.checkpoint.memory import InMemorySaver

        cp = get_checkpointer()
        assert isinstance(cp, InMemorySaver)

    def test_memory_singleton(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        cp1 = get_checkpointer()
        cp2 = get_checkpointer()
        assert cp1 is cp2

    def test_reset_clears_singleton(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        cp1 = get_checkpointer()
        reset_checkpointer()
        cp2 = get_checkpointer()
        assert cp1 is not cp2

    def test_postgres_raises_when_package_missing(self):
        load_checkpointer_config_from_dict({"type": "postgres", "connection_string": "postgresql://localhost/db"})
        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres": None}):
            reset_checkpointer()
            with pytest.raises(ImportError, match="langgraph-checkpoint-postgres"):
                get_checkpointer()

    def test_postgres_raises_when_connection_string_missing(self):
        load_checkpointer_config_from_dict({"type": "postgres"})
        mock_saver = MagicMock()
        mock_module = MagicMock()
        mock_module.PostgresSaver = mock_saver
        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres": mock_module}):
            reset_checkpointer()
            with pytest.raises(ValueError, match="connection_string is required"):
                get_checkpointer()

    def test_postgres_creates_saver(self):
        """Postgres checkpointer is created when packages are available."""
        load_checkpointer_config_from_dict({"type": "postgres", "connection_string": "postgresql://localhost/db"})

        mock_saver_instance = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_saver_instance)
        mock_cm.__exit__ = MagicMock(return_value=False)

        mock_saver_cls = MagicMock()
        mock_saver_cls.from_conn_string = MagicMock(return_value=mock_cm)

        mock_pg_module = MagicMock()
        mock_pg_module.PostgresSaver = mock_saver_cls

        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres": mock_pg_module}):
            reset_checkpointer()
            cp = get_checkpointer()

        assert cp is mock_saver_instance
        mock_saver_cls.from_conn_string.assert_called_once_with("postgresql://localhost/db")
        mock_saver_instance.setup.assert_called_once()

    def test_postgres_schema_creates_schema_and_sets_search_path(self):
        """Sync Postgres checkpointer should create schema before setup."""
        load_checkpointer_config_from_dict({"type": "postgres", "connection_string": "postgresql://localhost/db", "postgres_schema": "tianshu"})

        mock_saver_instance = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_saver_instance)
        mock_cm.__exit__ = MagicMock(return_value=False)

        mock_saver_cls = MagicMock()
        mock_saver_cls.from_conn_string = MagicMock(return_value=mock_cm)

        mock_pg_module = MagicMock()
        mock_pg_module.PostgresSaver = mock_saver_cls

        mock_conn = MagicMock()
        mock_psycopg = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        with (
            patch.dict(sys.modules, {"langgraph.checkpoint.postgres": mock_pg_module}),
            patch.dict(sys.modules, {"psycopg": mock_psycopg}),
        ):
            reset_checkpointer()
            cp = get_checkpointer()

        assert cp is mock_saver_instance
        mock_psycopg.connect.assert_called_once_with("postgresql://localhost/db", autocommit=True)
        mock_conn.execute.assert_called_once_with('CREATE SCHEMA IF NOT EXISTS "tianshu"')
        # psycopg 3 __exit__ does not close(); the sync path must close explicitly.
        mock_conn.close.assert_called_once_with()
        called_dsn = mock_saver_cls.from_conn_string.call_args.args[0]
        assert "options=-c%20search_path%3Dtianshu" in called_dsn
        mock_saver_instance.setup.assert_called_once()

    def test_store_postgres_schema_creates_schema_and_sets_search_path(self):
        """Sync Postgres store should use the legacy checkpointer schema."""
        load_checkpointer_config_from_dict({"type": "postgres", "connection_string": "postgresql://localhost/db", "postgres_schema": "tianshu"})

        mock_store_instance = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_store_instance)
        mock_cm.__exit__ = MagicMock(return_value=False)

        mock_store_cls = MagicMock()
        mock_store_cls.from_conn_string = MagicMock(return_value=mock_cm)

        mock_pg_module = MagicMock()
        mock_pg_module.PostgresStore = mock_store_cls

        mock_conn = MagicMock()
        mock_psycopg = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        with (
            patch.dict(sys.modules, {"langgraph.store.postgres": mock_pg_module}),
            patch.dict(sys.modules, {"psycopg": mock_psycopg}),
        ):
            reset_store()
            store = get_store()

        assert store is mock_store_instance
        mock_psycopg.connect.assert_called_once_with("postgresql://localhost/db", autocommit=True)
        mock_conn.execute.assert_called_once_with('CREATE SCHEMA IF NOT EXISTS "tianshu"')
        # psycopg 3 __exit__ does not close(); the sync path must close explicitly.
        mock_conn.close.assert_called_once_with()
        called_dsn = mock_store_cls.from_conn_string.call_args.args[0]
        assert "options=-c%20search_path%3Dtianshu" in called_dsn
        mock_store_instance.setup.assert_called_once()


class TestSyncSingletonThreadSafety:
    def test_store_reset_clears_singleton(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        store1 = get_store()
        reset_store()
        store2 = get_store()
        assert store1 is not store2

    def test_concurrent_checkpointer_getter_creates_one_instance(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        factory = _BlockingSingletonFactory()

        with patch("tianshu.runtime.checkpointer.provider._sync_checkpointer_cm", side_effect=factory.context_manager):
            futures_started = ThreadPoolExecutor(max_workers=1)
            try:
                result_future = futures_started.submit(_call_getter_concurrently, get_checkpointer)
                assert factory.entered.wait(timeout=3)
                factory.release.wait(timeout=0.05)
                factory.release.set()
                results = result_future.result(timeout=3)
            finally:
                futures_started.shutdown(wait=True)

        assert all(result is factory.value for result in results)
        assert factory.enter_count() == 1

    def test_concurrent_store_getter_creates_one_instance(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        factory = _BlockingSingletonFactory()

        with patch("tianshu.runtime.store.provider._sync_store_cm", side_effect=factory.context_manager):
            futures_started = ThreadPoolExecutor(max_workers=1)
            try:
                result_future = futures_started.submit(_call_getter_concurrently, get_store)
                assert factory.entered.wait(timeout=3)
                factory.release.wait(timeout=0.05)
                factory.release.set()
                results = result_future.result(timeout=3)
            finally:
                futures_started.shutdown(wait=True)

        assert all(result is factory.value for result in results)
        assert factory.enter_count() == 1

    def test_checkpointer_loads_config_outside_singleton_lock(self):
        tracking_lock = _TrackingLock()

        def fake_ensure_config_loaded():
            assert not tracking_lock.locked()
            load_checkpointer_config_from_dict({"type": "memory"})

        with (
            patch("tianshu.runtime.checkpointer.provider._checkpointer_lock", tracking_lock),
            patch("tianshu.runtime.checkpointer.provider.ensure_config_loaded", side_effect=fake_ensure_config_loaded),
        ):
            checkpointer = get_checkpointer()

        assert checkpointer is not None
        assert tracking_lock.acquired.is_set()

    def test_store_loads_config_outside_singleton_lock(self):
        tracking_lock = _TrackingLock()

        def fake_ensure_config_loaded():
            assert not tracking_lock.locked()
            load_checkpointer_config_from_dict({"type": "memory"})

        with (
            patch("tianshu.runtime.store.provider._store_lock", tracking_lock),
            patch("tianshu.runtime.store.provider.ensure_config_loaded", side_effect=fake_ensure_config_loaded),
        ):
            store = get_store()

        assert store is not None
        assert tracking_lock.acquired.is_set()

    def test_checkpointer_reset_waits_for_initialization(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        factory = _BlockingSingletonFactory()

        with (
            patch("tianshu.runtime.checkpointer.provider._sync_checkpointer_cm", side_effect=factory.context_manager),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            get_future = executor.submit(get_checkpointer)
            assert factory.entered.wait(timeout=3)

            reset_started = Event()

            def reset_worker():
                reset_started.set()
                reset_checkpointer()

            reset_future = executor.submit(reset_worker)
            assert reset_started.wait(timeout=3)
            factory.release.wait(timeout=0.05)

            assert not reset_future.done()
            assert factory.exit_count() == 0

            factory.release.set()
            assert get_future.result(timeout=3) is factory.value
            reset_future.result(timeout=3)

        assert factory.exit_count() == 1

    def test_store_reset_waits_for_initialization(self):
        load_checkpointer_config_from_dict({"type": "memory"})
        factory = _BlockingSingletonFactory()

        with (
            patch("tianshu.runtime.store.provider._sync_store_cm", side_effect=factory.context_manager),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            get_future = executor.submit(get_store)
            assert factory.entered.wait(timeout=3)

            reset_started = Event()

            def reset_worker():
                reset_started.set()
                reset_store()

            reset_future = executor.submit(reset_worker)
            assert reset_started.wait(timeout=3)
            factory.release.wait(timeout=0.05)

            assert not reset_future.done()
            assert factory.exit_count() == 0

            factory.release.set()
            assert get_future.result(timeout=3) is factory.value
            reset_future.result(timeout=3)

        assert factory.exit_count() == 1


class TestAsyncCheckpointer:
    @pytest.mark.anyio
    async def test_postgres_uses_connection_pool(self):
        """Async postgres checkpointer should use AsyncConnectionPool, not a single connection."""
        from tianshu.runtime.checkpointer.async_provider import make_checkpointer

        mock_config = MagicMock()
        mock_config.checkpointer = CheckpointerConfig(type="postgres", connection_string="postgresql://localhost/db", postgres_schema="tianshu")

        mock_saver = AsyncMock()

        mock_saver_cls = MagicMock(return_value=mock_saver)

        mock_pool_instance = AsyncMock()
        mock_pool_instance.__aenter__.return_value = mock_pool_instance
        mock_pool_instance.__aexit__.return_value = False
        mock_conn = AsyncMock()
        mock_conn_cm = AsyncMock()
        mock_conn_cm.__aenter__.return_value = mock_conn
        mock_conn_cm.__aexit__.return_value = False
        mock_pool_instance.connection = MagicMock(return_value=mock_conn_cm)

        mock_pool_cls = MagicMock(return_value=mock_pool_instance)
        mock_pool_cls.check_connection = AsyncMock()
        mock_dict_row = MagicMock()

        mock_pg_module = MagicMock()
        mock_pg_module.AsyncPostgresSaver = mock_saver_cls

        mock_psycopg_rows = MagicMock()
        mock_psycopg_rows.dict_row = mock_dict_row

        with (
            patch("tianshu.runtime.checkpointer.async_provider.get_app_config", return_value=mock_config),
            patch.dict(sys.modules, {"langgraph.checkpoint.postgres.aio": mock_pg_module}),
            patch.dict(sys.modules, {"psycopg.rows": mock_psycopg_rows}),
            patch.dict(sys.modules, {"psycopg_pool": MagicMock(AsyncConnectionPool=mock_pool_cls)}),
        ):
            # AsyncConnectionPool() is a callable that returns mock_pool_instance
            # We need the constructor to be an async context manager
            async with make_checkpointer() as saver:
                assert saver is mock_saver

        # Verify the pool was constructed with check Connection
        mock_pool_cls.assert_called_once()
        call_kwargs = mock_pool_cls.call_args
        # search_path is injected into the DSN (merged with any existing libpq
        # options), not via kwargs["options"] which would clobber DSN options.
        assert "options=-c%20search_path%3Dtianshu" in call_kwargs[0][0]
        assert call_kwargs[1]["check"] is mock_pool_cls.check_connection
        assert "options" not in call_kwargs[1]["kwargs"]
        mock_conn.execute.assert_awaited_once_with('CREATE SCHEMA IF NOT EXISTS "tianshu"')

        # Verify saver was constructed with the pool (not via from_conn_string)
        mock_saver_cls.assert_called_once_with(conn=mock_pool_instance)
        mock_saver.setup.assert_awaited_once()

    @pytest.mark.anyio
    async def test_database_postgres_uses_connection_pool(self):
        """Unified database postgres path should use AsyncConnectionPool with keepalive."""
        from tianshu.config.database_config import DatabaseConfig
        from tianshu.runtime.checkpointer.async_provider import make_checkpointer

        db_config = DatabaseConfig(backend="postgres", postgres_url="postgresql://localhost/db", postgres_schema="tianshu")
        mock_config = MagicMock()
        mock_config.checkpointer = None
        mock_config.database = db_config

        mock_saver = AsyncMock()

        mock_saver_cls = MagicMock(return_value=mock_saver)

        mock_pool_instance = AsyncMock()
        mock_pool_instance.__aenter__.return_value = mock_pool_instance
        mock_pool_instance.__aexit__.return_value = False
        mock_conn = AsyncMock()
        mock_conn_cm = AsyncMock()
        mock_conn_cm.__aenter__.return_value = mock_conn
        mock_conn_cm.__aexit__.return_value = False
        mock_pool_instance.connection = MagicMock(return_value=mock_conn_cm)

        mock_pool_cls = MagicMock(return_value=mock_pool_instance)
        mock_pool_cls.check_connection = AsyncMock()
        mock_dict_row = MagicMock()

        mock_pg_module = MagicMock()
        mock_pg_module.AsyncPostgresSaver = mock_saver_cls

        mock_psycopg_rows = MagicMock()
        mock_psycopg_rows.dict_row = mock_dict_row

        with (
            patch("tianshu.runtime.checkpointer.async_provider.get_app_config", return_value=mock_config),
            patch.dict(sys.modules, {"langgraph.checkpoint.postgres.aio": mock_pg_module}),
            patch.dict(sys.modules, {"psycopg.rows": mock_psycopg_rows}),
            patch.dict(sys.modules, {"psycopg_pool": MagicMock(AsyncConnectionPool=mock_pool_cls)}),
        ):
            async with make_checkpointer() as saver:
                assert saver is mock_saver

        mock_pool_cls.assert_called_once()
        call_kwargs = mock_pool_cls.call_args
        assert "options=-c%20search_path%3Dtianshu" in call_kwargs[0][0]
        assert call_kwargs[1]["check"] is mock_pool_cls.check_connection
        assert "options" not in call_kwargs[1]["kwargs"]
        mock_conn.execute.assert_awaited_once_with('CREATE SCHEMA IF NOT EXISTS "tianshu"')

        mock_saver_cls.assert_called_once_with(conn=mock_pool_instance)
        mock_saver.setup.assert_awaited_once()


class TestAsyncStore:
    @pytest.mark.anyio
    async def test_postgres_schema_creates_schema_and_sets_search_path(self):
        """Async Postgres store should use the legacy checkpointer schema."""
        from tianshu.runtime.store.async_provider import make_store

        mock_config = MagicMock()
        mock_config.checkpointer = CheckpointerConfig(type="postgres", connection_string="postgresql://localhost/db", postgres_schema="tianshu")

        mock_store = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_store
        mock_cm.__aexit__.return_value = False

        mock_store_cls = MagicMock()
        mock_store_cls.from_conn_string.return_value = mock_cm

        mock_pg_module = MagicMock()
        mock_pg_module.AsyncPostgresStore = mock_store_cls

        mock_conn = AsyncMock()
        mock_async_connection = MagicMock()
        mock_async_connection.connect = AsyncMock(return_value=mock_conn)
        mock_psycopg = MagicMock()
        mock_psycopg.AsyncConnection = mock_async_connection

        with (
            patch.dict(sys.modules, {"langgraph.store.postgres.aio": mock_pg_module}),
            patch.dict(sys.modules, {"psycopg": mock_psycopg}),
        ):
            async with make_store(mock_config) as store:
                assert store is mock_store

        mock_async_connection.connect.assert_awaited_once_with("postgresql://localhost/db", autocommit=True)
        mock_conn.execute.assert_awaited_once_with('CREATE SCHEMA IF NOT EXISTS "tianshu"')
        mock_conn.close.assert_awaited_once()
        called_dsn = mock_store_cls.from_conn_string.call_args.args[0]
        assert "options=-c%20search_path%3Dtianshu" in called_dsn
        mock_store.setup.assert_awaited_once()

    @pytest.mark.anyio
    async def test_database_postgres_schema_creates_schema_and_sets_search_path(self):
        """Unified database postgres store should use database.postgres_schema."""
        from tianshu.config.database_config import DatabaseConfig
        from tianshu.runtime.store.async_provider import make_store

        mock_config = MagicMock()
        mock_config.checkpointer = None
        mock_config.database = DatabaseConfig(backend="postgres", postgres_url="postgresql://localhost/db", postgres_schema="tianshu")

        mock_store = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_store
        mock_cm.__aexit__.return_value = False

        mock_store_cls = MagicMock()
        mock_store_cls.from_conn_string.return_value = mock_cm

        mock_pg_module = MagicMock()
        mock_pg_module.AsyncPostgresStore = mock_store_cls

        mock_conn = AsyncMock()
        mock_async_connection = MagicMock()
        mock_async_connection.connect = AsyncMock(return_value=mock_conn)
        mock_psycopg = MagicMock()
        mock_psycopg.AsyncConnection = mock_async_connection

        with (
            patch.dict(sys.modules, {"langgraph.store.postgres.aio": mock_pg_module}),
            patch.dict(sys.modules, {"psycopg": mock_psycopg}),
        ):
            async with make_store(mock_config) as store:
                assert store is mock_store

        mock_async_connection.connect.assert_awaited_once_with("postgresql://localhost/db", autocommit=True)
        mock_conn.execute.assert_awaited_once_with('CREATE SCHEMA IF NOT EXISTS "tianshu"')
        mock_conn.close.assert_awaited_once()
        called_dsn = mock_store_cls.from_conn_string.call_args.args[0]
        assert "options=-c%20search_path%3Dtianshu" in called_dsn
        mock_store.setup.assert_awaited_once()


class TestCheckpointerDatabaseConfig:
    """The sync checkpointer must follow the unified ``database`` section when no
    legacy ``checkpointer`` section is configured — matching the async
    ``make_checkpointer`` factory and the sync Store provider.

    Regression: ``get_checkpointer`` / ``checkpointer_context`` previously read
    only the legacy ``checkpointer`` section and fell back to ``InMemorySaver``,
    silently ignoring ``database``. Embedded callers (``TianShuClient``) and the
    TUI then persisted Store rows to sqlite/postgres while checkpoints went to an
    in-memory saver and were lost on exit.
    """

    def test_sync_checkpointer_context_uses_database_config(self):
        """The one-shot sync checkpointer factory must follow unified database config."""
        from tianshu.runtime.checkpointer.provider import checkpointer_context

        app_config = SimpleNamespace(
            checkpointer=None,
            database=DatabaseConfig(backend="postgres", postgres_url="postgresql://localhost/db"),
        )
        expected = object()
        factory = MagicMock(return_value=nullcontext(expected))

        with (
            patch("tianshu.runtime.checkpointer.provider.get_app_config", return_value=app_config),
            patch("tianshu.runtime.checkpointer.provider._sync_checkpointer_cm", factory),
            checkpointer_context() as cp,
        ):
            assert cp is expected

        resolved = factory.call_args.args[0]
        assert resolved.type == "postgres"
        assert resolved.connection_string == "postgresql://localhost/db"

    def test_sync_checkpointer_singleton_uses_database_config(self):
        """The cached sync checkpointer factory must resolve database config before locking."""
        app_config = SimpleNamespace(
            checkpointer=None,
            database=DatabaseConfig(backend="postgres", postgres_url="postgresql://localhost/db"),
        )
        expected = object()
        factory = MagicMock(return_value=nullcontext(expected))

        with (
            patch("tianshu.runtime.checkpointer.provider.ensure_config_loaded"),
            patch("tianshu.runtime.checkpointer.provider.get_app_config", return_value=app_config),
            patch("tianshu.runtime.checkpointer.provider._sync_checkpointer_cm", factory),
        ):
            assert get_checkpointer() is expected

        resolved = factory.call_args.args[0]
        assert resolved.type == "postgres"
        assert resolved.connection_string == "postgresql://localhost/db"

    def test_sync_checkpointer_falls_back_to_memory_when_config_file_is_missing(self):
        """The sync checkpointer keeps its no-config fallback for embedded callers."""
        from langgraph.checkpoint.memory import InMemorySaver

        with (
            patch("tianshu.runtime.checkpointer.provider.ensure_config_loaded"),
            patch("tianshu.runtime.checkpointer.provider.get_checkpointer_config", return_value=None),
            patch("tianshu.runtime.checkpointer.provider.get_app_config", side_effect=FileNotFoundError),
        ):
            assert isinstance(get_checkpointer(), InMemorySaver)

    def test_legacy_checkpointer_config_takes_precedence(self):
        """Backward-compatible checkpointer config must override database."""
        from tianshu.runtime.checkpointer.provider import checkpointer_context

        app_config = SimpleNamespace(
            checkpointer=CheckpointerConfig(type="memory"),
            database=DatabaseConfig(backend="postgres", postgres_url="postgresql://localhost/db"),
        )
        expected = object()
        factory = MagicMock(return_value=nullcontext(expected))

        with (
            patch("tianshu.runtime.checkpointer.provider.get_app_config", return_value=app_config),
            patch("tianshu.runtime.checkpointer.provider._sync_checkpointer_cm", factory),
            checkpointer_context() as cp,
        ):
            assert cp is expected

        resolved = factory.call_args.args[0]
        assert resolved.type == "memory"
        assert resolved.connection_string is None

    def test_explicit_memory_database_uses_in_memory_saver(self):
        """Explicit memory mode remains an intentional non-persistent checkpointer."""
        from langgraph.checkpoint.memory import InMemorySaver

        from tianshu.runtime.checkpointer.provider import checkpointer_context

        app_config = SimpleNamespace(checkpointer=None, database=DatabaseConfig(backend="memory"))

        with (
            patch("tianshu.runtime.checkpointer.provider.get_app_config", return_value=app_config),
            checkpointer_context() as cp,
        ):
            assert isinstance(cp, InMemorySaver)


class TestStoreDatabaseConfig:
    def test_sync_store_falls_back_to_memory_when_config_file_is_missing(self):
        """The sync Store keeps its no-config fallback for embedded callers."""
        from langgraph.store.memory import InMemoryStore

        with (
            patch("tianshu.runtime.store.provider.ensure_config_loaded"),
            patch("tianshu.runtime.store.provider.get_checkpointer_config", return_value=None),
            patch("tianshu.runtime.store.provider.get_app_config", side_effect=FileNotFoundError),
        ):
            assert isinstance(get_store(), InMemoryStore)

    @pytest.mark.anyio
    async def test_async_postgres_store_uses_database_config(self, caplog):
        """Unified database postgres config must not fall back to InMemoryStore."""
        from tianshu.runtime.store.async_provider import make_store

        caplog.set_level("WARNING", logger="tianshu.runtime.store.async_provider")
        app_config = SimpleNamespace(
            checkpointer=None,
            database=DatabaseConfig(backend="postgres", postgres_url="postgresql://localhost/db"),
        )
        mock_store = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_store
        mock_cm.__aexit__.return_value = False
        mock_store_cls = MagicMock()
        mock_store_cls.from_conn_string.return_value = mock_cm
        mock_module = MagicMock(AsyncPostgresStore=mock_store_cls)

        with patch.dict(sys.modules, {"langgraph.store.postgres.aio": mock_module}):
            async with make_store(app_config) as store:
                assert store is mock_store

        mock_store_cls.from_conn_string.assert_called_once_with("postgresql://localhost/db")
        mock_store.setup.assert_awaited_once()
        assert "No 'checkpointer' section" not in caplog.text

    def test_sync_store_context_uses_database_config(self):
        """The one-shot sync Store factory must follow unified database config."""
        from tianshu.runtime.store.provider import store_context

        app_config = SimpleNamespace(
            checkpointer=None,
            database=DatabaseConfig(backend="postgres", postgres_url="postgresql://localhost/db"),
        )
        expected_store = object()
        factory = MagicMock(return_value=nullcontext(expected_store))

        with (
            patch("tianshu.runtime.store.provider.get_app_config", return_value=app_config),
            patch("tianshu.runtime.store.provider._sync_store_cm", factory),
            store_context() as store,
        ):
            assert store is expected_store

        resolved = factory.call_args.args[0]
        assert resolved.type == "postgres"
        assert resolved.connection_string == "postgresql://localhost/db"

    def test_sync_store_singleton_uses_database_config(self):
        """The cached sync Store factory must resolve database config before locking."""
        app_config = SimpleNamespace(
            checkpointer=None,
            database=DatabaseConfig(backend="postgres", postgres_url="postgresql://localhost/db"),
        )
        expected_store = object()
        factory = MagicMock(return_value=nullcontext(expected_store))

        with (
            patch("tianshu.runtime.store.provider.ensure_config_loaded"),
            patch("tianshu.runtime.store.provider.get_app_config", return_value=app_config),
            patch("tianshu.runtime.store.provider._sync_store_cm", factory),
        ):
            assert get_store() is expected_store

        resolved = factory.call_args.args[0]
        assert resolved.type == "postgres"
        assert resolved.connection_string == "postgresql://localhost/db"

    def test_legacy_checkpointer_config_takes_precedence_for_store(self):
        """Backward-compatible checkpointer config must override database for Store."""
        from tianshu.runtime.store.provider import store_context

        app_config = SimpleNamespace(
            checkpointer=CheckpointerConfig(type="memory"),
            database=DatabaseConfig(backend="postgres", postgres_url="postgresql://localhost/db"),
        )
        expected_store = object()
        factory = MagicMock(return_value=nullcontext(expected_store))

        with (
            patch("tianshu.runtime.store.provider.get_app_config", return_value=app_config),
            patch("tianshu.runtime.store.provider._sync_store_cm", factory),
            store_context() as store,
        ):
            assert store is expected_store

        resolved = factory.call_args.args[0]
        assert resolved.type == "memory"
        assert resolved.connection_string is None

    def test_explicit_memory_database_uses_in_memory_store(self):
        """Explicit memory mode remains an intentional non-persistent Store."""
        from langgraph.store.memory import InMemoryStore

        from tianshu.runtime.store.provider import store_context

        app_config = SimpleNamespace(
            checkpointer=None,
            database=DatabaseConfig(backend="memory"),
        )
        with patch("tianshu.runtime.store.provider.get_app_config", return_value=app_config):
            with store_context() as store:
                assert isinstance(store, InMemoryStore)


# ---------------------------------------------------------------------------
# app_config.py integration
# ---------------------------------------------------------------------------


class TestAppConfigLoadsCheckpointer:
    def test_load_checkpointer_section(self):
        """load_checkpointer_config_from_dict populates the global config."""
        set_checkpointer_config(None)
        load_checkpointer_config_from_dict({"type": "memory"})
        cfg = get_checkpointer_config()
        assert cfg is not None
        assert cfg.type == "memory"


# ---------------------------------------------------------------------------
# TianShuClient falls back to config checkpointer
# ---------------------------------------------------------------------------


class TestClientCheckpointerFallback:
    def test_client_uses_config_checkpointer_when_none_provided(self):
        """TianShuClient._ensure_agent falls back to get_checkpointer() when checkpointer=None."""
        from langgraph.checkpoint.memory import InMemorySaver

        from tianshu.client import TianShuClient

        load_checkpointer_config_from_dict({"type": "memory"})

        captured_kwargs = {}

        def fake_create_agent(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        model_mock = MagicMock()
        config_mock = MagicMock()
        config_mock.models = [model_mock]
        config_mock.database.checkpoint_delta.snapshot_frequency = 10
        config_mock.get_model_config.return_value = MagicMock(supports_vision=False)
        config_mock.checkpointer = None

        config_mock.skills.deferred_discovery = False
        config_mock.skills.container_path = "/mnt/skills"
        config_mock.tool_search.enabled = False

        with (
            patch("tianshu.client.get_app_config", return_value=config_mock),
            patch("tianshu.client.create_agent", side_effect=fake_create_agent),
            patch("tianshu.client.create_chat_model", return_value=MagicMock()),
            patch("tianshu.client.build_middlewares", return_value=[]),
            patch("tianshu.client.apply_prompt_template", return_value=""),
            patch("tianshu.client.get_enabled_skills_for_config", return_value=[]),
            patch("tianshu.client.TianShuClient._get_tools", return_value=[]),
        ):
            client = TianShuClient(checkpointer=None)
            config = client._get_runnable_config("test-thread")
            client._ensure_agent(config)

        assert "checkpointer" in captured_kwargs
        assert isinstance(captured_kwargs["checkpointer"], InMemorySaver)

    def test_client_explicit_checkpointer_takes_precedence(self):
        """An explicitly provided checkpointer is used even when config checkpointer is set."""
        from tianshu.client import TianShuClient

        load_checkpointer_config_from_dict({"type": "memory"})

        explicit_cp = MagicMock()
        captured_kwargs = {}

        def fake_create_agent(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        model_mock = MagicMock()
        config_mock = MagicMock()
        config_mock.models = [model_mock]
        config_mock.database.checkpoint_delta.snapshot_frequency = 10
        config_mock.get_model_config.return_value = MagicMock(supports_vision=False)
        config_mock.checkpointer = None

        config_mock.skills.deferred_discovery = False
        config_mock.skills.container_path = "/mnt/skills"
        config_mock.tool_search.enabled = False

        with (
            patch("tianshu.client.get_app_config", return_value=config_mock),
            patch("tianshu.client.create_agent", side_effect=fake_create_agent),
            patch("tianshu.client.create_chat_model", return_value=MagicMock()),
            patch("tianshu.client.build_middlewares", return_value=[]),
            patch("tianshu.client.apply_prompt_template", return_value=""),
            patch("tianshu.client.get_enabled_skills_for_config", return_value=[]),
            patch("tianshu.client.TianShuClient._get_tools", return_value=[]),
        ):
            client = TianShuClient(checkpointer=explicit_cp)
            config = client._get_runnable_config("test-thread")
            client._ensure_agent(config)

        assert captured_kwargs["checkpointer"] is explicit_cp
