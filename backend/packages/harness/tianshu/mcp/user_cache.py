"""Per-user cache for MCP tools built from the ``user_mcp`` registry.

Each user's tools are cached under their ``user_id`` and explicitly
invalidated on CRUD. Unlike the global cache
(:mod:`tianshu.mcp.cache`), there is no config-signature staleness check:
the authoritative change signal is the repository write, and the CRUD
router calls :func:`invalidate_user_mcp_tools` after every mutation.
"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

_user_mcp_tools_cache: dict[str, list[BaseTool]] = {}
_cache_lock = asyncio.Lock()


def get_cached_user_mcp_tools(user_id: str) -> list[BaseTool] | None:
    """Return the cached tools for *user_id*, or ``None`` when not cached."""
    return _user_mcp_tools_cache.get(user_id)


def store_cached_user_mcp_tools(user_id: str, tools: list[BaseTool]) -> None:
    """Store the built tools for *user_id* under its cache key."""
    _user_mcp_tools_cache[user_id] = tools


async def invalidate_user_mcp_tools(user_id: str) -> None:
    """Drop *user_id*'s cached tools and close its pooled MCP sessions.

    Closing sessions matters because the pool keys sessions by
    ``(server_name, user_id:thread_id)`` -- an edited server definition
    would otherwise be masked by the stale pooled session on the next tool
    call. Session teardown is best-effort: failures are logged, never
    raised, so a CRUD request is not rejected because of cleanup trouble.
    """
    _user_mcp_tools_cache.pop(user_id, None)
    try:
        from tianshu.mcp.session_pool import get_session_pool

        await get_session_pool().close_user(user_id)
    except Exception:
        logger.debug(
            "Could not close MCP sessions for user %s on cache invalidation",
            user_id,
            exc_info=True,
        )
