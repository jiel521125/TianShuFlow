"""Per-user MCP registry resolution.

Builds MCP tools **only** from the current user's own ``user_mcp`` rows.
The system-global ``extensions_config.json`` servers are deliberately not
loaded here: since the per-user registry became the runtime tool source,
global servers never enter a user session (see the approved
``docs/user-mcp/architecture.md`` decision "运行时来源唯一").

The "inherit_global" semantics of ``settings.tools`` therefore naturally
mean "the user's *own* full registry" -- because the tool source already
is the user's registry, filtering with ``inherit_global: true`` (→ all
kept) cannot leak anyone else's tools.
"""

from __future__ import annotations

import logging

from langchain_core.tools import BaseTool

from tianshu.mcp.user_cache import (
    get_cached_user_mcp_tools,
    invalidate_user_mcp_tools,
    store_cached_user_mcp_tools,
)
from tianshu.persistence.user_mcp.sql import UserMCPServerRepository

logger = logging.getLogger(__name__)

# Key the gateway injects into ``config["context"]`` holding the current
# user's own MCP tools; ``_make_lead_agent`` reads it via
# ``_get_runtime_config`` and REPLACES the global MCP tools with these.
# A value of ``None`` (absent) keeps the pre-registry behaviour.
USER_MCP_TOOLS_CONTEXT_KEY = "user_mcp_tools"


def _repo() -> UserMCPServerRepository:
    return UserMCPServerRepository()


async def resolve_user_mcp_servers(user_id: str) -> dict[str, dict]:
    """Build a langchain-mcp-adapters ``servers_config`` from *user_id*'s rows.

    Returns a mapping of server name -> connection params (``transport`` /
    ``command`` / ``args`` / ``env`` / ``url``) exactly like the global
    :func:`tianshu.mcp.client.build_servers_config`, but sourced from the
    user's own ``user_mcp`` table. Rows that fail transport validation are
    skipped with a warning (one broken server does not block the rest).
    """
    rows = await _repo().get_all_for_runtime(user_id)
    if not rows:
        return {}

    servers_config: dict[str, dict] = {}
    for row in rows:
        name = row["name"]
        transport = (row.get("transport") or "stdio").lower()
        params: dict = {"transport": transport}
        if transport == "stdio":
            if not row.get("command"):
                logger.warning(
                    "Skipping user MCP server '%s' (user %s): stdio transport requires 'command'",
                    name,
                    user_id,
                )
                continue
            params["command"] = row["command"]
            params["args"] = row.get("args") or []
            if row.get("env"):
                params["env"] = row["env"]
        elif transport in ("sse", "http"):
            if not row.get("url"):
                logger.warning(
                    "Skipping user MCP server '%s' (user %s): %s transport requires 'url'",
                    name,
                    user_id,
                    transport,
                )
                continue
            params["url"] = row["url"]
        else:
            logger.warning(
                "Skipping user MCP server '%s' (user %s): unsupported transport %r",
                name,
                user_id,
                transport,
            )
            continue
        servers_config[name] = params
    return servers_config


async def build_user_mcp_tools(user_id: str) -> list[BaseTool]:
    """Build (and cache) the current user's MCP tools.

    Returns ``[]`` when the user has no registered servers or when tool
    discovery fails -- never raises. Results are cached per user and
    invalidated by :func:`invalidate_user_mcp_tools` after any CRUD write.
    A double-checked read after the initial cache miss tolerates concurrent
    in-flight builds without holding a cross-event-loop lock.
    """
    cached = get_cached_user_mcp_tools(user_id)
    if cached is not None:
        return cached

    from tianshu.mcp.tools import build_mcp_tools

    rows = await _repo().get_all_for_runtime(user_id)
    if not rows:
        store_cached_user_mcp_tools(user_id, [])
        return []
    servers_config = await resolve_user_mcp_servers(user_id)
    server_options = {
        row["name"]: {
            "tool_name_prefix": row["tool_name_prefix"],
            "tool_call_timeout": row["tool_call_timeout"],
        }
        for row in rows
        if row["name"] in servers_config
    }
    tools = await build_mcp_tools(
        servers_config,
        server_options=server_options,
    )
    store_cached_user_mcp_tools(user_id, tools)
    return tools


__all__ = [
    "USER_MCP_TOOLS_CONTEXT_KEY",
    "resolve_user_mcp_servers",
    "build_user_mcp_tools",
    "invalidate_user_mcp_tools",
]
