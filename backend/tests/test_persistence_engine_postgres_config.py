"""Tests for hardened PostgreSQL async engine configuration."""

from __future__ import annotations

import asyncio
import sys
from time import monotonic
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from tianshu.config.database_config import DatabaseConfig
from tianshu.persistence import engine as engine_mod


def test_postgres_engine_kwargs_include_connection_hardening() -> None:
    kwargs = engine_mod._postgres_engine_kwargs(echo=False, pool_size=5)

    assert kwargs["echo"] is False
    assert kwargs["pool_size"] == 5
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == engine_mod.POSTGRES_POOL_RECYCLE_SECONDS
    assert kwargs["connect_args"]["command_timeout"] == engine_mod.POSTGRES_COMMAND_TIMEOUT_SECONDS
    assert kwargs["json_serializer"] is engine_mod._json_serializer


def test_database_command_timeout_defaults_to_30_seconds() -> None:
    config = DatabaseConfig()

    assert config.command_timeout == 30


def test_database_pool_recycle_defaults_to_300_seconds() -> None:
    config = DatabaseConfig()

    assert config.pool_recycle == 300


def test_postgres_engine_kwargs_preserve_caller_values() -> None:
    kwargs = engine_mod._postgres_engine_kwargs(echo=True, pool_size=20, pool_recycle=120, command_timeout=90)

    assert kwargs["echo"] is True
    assert kwargs["pool_size"] == 20
    assert kwargs["pool_recycle"] == 120
    assert kwargs["connect_args"] == {"command_timeout": 90}


def test_postgres_engine_kwargs_allow_command_timeout_opt_out() -> None:
    config = DatabaseConfig(command_timeout=None)
    kwargs = engine_mod._postgres_engine_kwargs(echo=False, pool_size=5, command_timeout=config.command_timeout)

    assert config.command_timeout is None
    assert kwargs["connect_args"] == {}


@pytest.mark.asyncio
async def test_configured_command_timeout_ends_stalled_command() -> None:
    config = DatabaseConfig(
        backend="postgres",
        postgres_url="postgresql://user:password@localhost/tianshu",
        command_timeout=0.01,
    )

    class _StalledAsyncpgEngine:
        def __init__(self, command_timeout: float) -> None:
            self.command_timeout = command_timeout

        async def checkout(self) -> None:
            async with asyncio.timeout(self.command_timeout):
                await asyncio.Event().wait()

        async def dispose(self) -> None:
            return None

    def _create_engine(_url: str, **kwargs) -> _StalledAsyncpgEngine:
        assert kwargs["pool_pre_ping"] is True
        return _StalledAsyncpgEngine(kwargs["connect_args"]["command_timeout"])

    bootstrap_schema = AsyncMock()

    with (
        patch.dict(sys.modules, {"asyncpg": ModuleType("asyncpg")}),
        patch.object(engine_mod, "create_async_engine", side_effect=_create_engine),
        patch.object(engine_mod, "async_sessionmaker", return_value=MagicMock()),
        patch("tianshu.persistence.bootstrap.bootstrap_schema", new=bootstrap_schema),
    ):
        try:
            await engine_mod.init_engine_from_config(config)
            engine = engine_mod.get_engine()
            assert isinstance(engine, _StalledAsyncpgEngine)
            started_at = monotonic()
            with pytest.raises(TimeoutError):
                await engine.checkout()
            elapsed = monotonic() - started_at

            assert engine.command_timeout == config.command_timeout
            assert elapsed < 1
        finally:
            await engine_mod.close_engine()


@pytest.mark.asyncio
async def test_init_engine_from_config_preserves_longer_command_timeout_override() -> None:
    config = DatabaseConfig(
        backend="postgres",
        postgres_url="postgresql://user:password@localhost/tianshu",
        pool_recycle=120,
        command_timeout=90,
    )
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    bootstrap_schema = AsyncMock()

    with (
        patch.dict(sys.modules, {"asyncpg": ModuleType("asyncpg")}),
        patch.object(engine_mod, "create_async_engine", return_value=mock_engine) as create_engine,
        patch.object(engine_mod, "async_sessionmaker", return_value=MagicMock()),
        patch("tianshu.persistence.bootstrap.bootstrap_schema", new=bootstrap_schema),
    ):
        try:
            await engine_mod.init_engine_from_config(config)

            kwargs = create_engine.call_args.kwargs
            assert kwargs["connect_args"]["command_timeout"] == 90
            assert kwargs["pool_recycle"] == 120
        finally:
            await engine_mod.close_engine()


@pytest.mark.asyncio
async def test_init_engine_postgres_uses_hardened_kwargs() -> None:
    url = "postgresql+asyncpg://user:password@localhost/tianshu"
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    bootstrap_schema = AsyncMock()

    with (
        patch.dict(sys.modules, {"asyncpg": ModuleType("asyncpg")}),
        patch.object(engine_mod, "create_async_engine", return_value=mock_engine) as create_engine,
        patch.object(engine_mod, "async_sessionmaker", return_value=MagicMock()),
        patch("tianshu.persistence.bootstrap.bootstrap_schema", new=bootstrap_schema),
    ):
        try:
            await engine_mod.init_engine(backend="postgres", url=url, echo=True, pool_size=12)

            create_engine.assert_called_once_with(url, **engine_mod._postgres_engine_kwargs(echo=True, pool_size=12))
            bootstrap_schema.assert_awaited_once_with(mock_engine, backend="postgres", postgres_schema="")
        finally:
            await engine_mod.close_engine()


@pytest.mark.asyncio
async def test_init_engine_postgres_retry_uses_hardened_kwargs() -> None:
    url = "postgresql+asyncpg://user:password@localhost/tianshu"
    initial_engine = MagicMock()
    initial_engine.dispose = AsyncMock()
    retry_engine = MagicMock()
    retry_engine.dispose = AsyncMock()
    bootstrap_schema = AsyncMock(side_effect=[Exception("database does not exist"), None])
    auto_create = AsyncMock()

    with (
        patch.dict(sys.modules, {"asyncpg": ModuleType("asyncpg")}),
        patch.object(engine_mod, "create_async_engine", side_effect=[initial_engine, retry_engine]) as create_engine,
        patch.object(engine_mod, "async_sessionmaker", return_value=MagicMock()),
        patch.object(engine_mod, "_auto_create_postgres_db", new=auto_create),
        patch("tianshu.persistence.bootstrap.bootstrap_schema", new=bootstrap_schema),
    ):
        try:
            await engine_mod.init_engine(backend="postgres", url=url, echo=False, pool_size=8)

            kwargs = engine_mod._postgres_engine_kwargs(echo=False, pool_size=8)
            assert create_engine.call_args_list == [call(url, **kwargs), call(url, **kwargs)]
            auto_create.assert_awaited_once_with(url)
            initial_engine.dispose.assert_awaited_once()
            assert bootstrap_schema.await_args_list == [
                call(initial_engine, backend="postgres", postgres_schema=""),
                call(retry_engine, backend="postgres", postgres_schema=""),
            ]
        finally:
            await engine_mod.close_engine()
