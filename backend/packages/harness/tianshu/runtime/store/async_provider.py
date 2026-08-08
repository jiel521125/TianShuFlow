"""Async Store factory — backend mirrors runtime persistence configuration.

The deprecated ``checkpointer`` section takes precedence when present;
otherwise Store follows the unified ``database`` section in *config.yaml*:

- ``memory``   → :class:`langgraph.store.memory.InMemoryStore`
- ``postgres`` → :class:`langgraph.store.postgres.aio.AsyncPostgresStore`

Usage (e.g. FastAPI lifespan)::

    from tianshu.runtime.store import make_store

    async with make_store() as store:
        app.state.store = store
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator

from langgraph.store.base import BaseStore

from tianshu.config.app_config import AppConfig, get_app_config
from tianshu.persistence.postgres_schema import dsn_with_search_path, ensure_postgres_schema_async
from tianshu.runtime.store.provider import (
    POSTGRES_CONN_REQUIRED,
    POSTGRES_STORE_INSTALL,
    _resolve_store_config,
)

logger = logging.getLogger(__name__)


async def _ensure_postgres_schema(conn_string: str, schema: str) -> None:
    """Create the configured schema before LangGraph creates its store tables."""
    await ensure_postgres_schema_async(conn_string, schema, install_hint=POSTGRES_STORE_INSTALL)


# ---------------------------------------------------------------------------
# Internal backend factory
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _async_store(config) -> AsyncIterator[BaseStore]:
    """Async context manager that constructs and tears down a Store.

    The ``config`` argument is a :class:`tianshu.config.checkpointer_config.CheckpointerConfig`
    instance — the same object used by the checkpointer factory.
    """
    if config.type == "memory":
        from langgraph.store.memory import InMemoryStore

        logger.info("Store: using InMemoryStore (in-process, not persistent)")
        yield InMemoryStore()
        return

    if config.type == "postgres":
        try:
            from langgraph.store.postgres.aio import AsyncPostgresStore  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(POSTGRES_STORE_INSTALL) from exc

        if not config.connection_string:
            raise ValueError(POSTGRES_CONN_REQUIRED)

        await _ensure_postgres_schema(config.connection_string, config.postgres_schema)
        conn_string = dsn_with_search_path(config.connection_string, config.postgres_schema)
        async with AsyncPostgresStore.from_conn_string(conn_string) as store:
            await store.setup()
            logger.info("Store: using AsyncPostgresStore")
            yield store
        return

    raise ValueError(f"Unknown store backend type: {config.type!r}")


# ---------------------------------------------------------------------------
# Public async context manager
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def make_store(app_config: AppConfig | None = None) -> AsyncIterator[BaseStore]:
    """Yield a Store selected from legacy or unified persistence config.

    The legacy ``checkpointer`` section takes precedence when configured;
    otherwise the unified ``database`` section selects the backend, matching
    :func:`tianshu.runtime.checkpointer.async_provider.make_checkpointer`::

        async with make_store(app_config) as store:
            app.state.store = store

    An :class:`~langgraph.store.memory.InMemoryStore` is returned only when the
    resolved backend is explicitly ``memory``.
    """
    if app_config is None:
        app_config = get_app_config()

    config = _resolve_store_config(app_config)
    async with _async_store(config) as store:
        yield store
