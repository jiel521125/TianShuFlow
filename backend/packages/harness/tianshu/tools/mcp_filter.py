"""Per-user MCP server filtering ("千人千面").

The global MCP cache holds tools from every server enabled by the operator.
Users can opt out of that global set with a ``tools`` settings override
(``inherit_global: false`` + ``enabled_servers: [...]``) from the Settings →
Tools page (and, since the toolbar menu, directly from the chat input box).

Two pieces make that preference real at runtime:

1. :func:`resolve_mcp_enabled_servers` reads the user's ``tools`` override
   (async, DB-backed) and returns either ``None`` (inherit the global server
   set) or the user's allowlist.
2. :func:`filter_mcp_tools` applies that allowlist synchronously at agent
   build time, dropping MCP tools from non-allowed servers while leaving every
   non-MCP tool untouched.

The gateway injects the resolved allowlist into the run config
(``config["context"]["mcp_enabled_servers"]``); ``make_lead_agent`` reads it
and filters before deferred-tool assembly / MCP routing middleware are built,
so withheld servers contribute neither bound tools nor deferred catalog names.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from langchain_core.tools import BaseTool

from tianshu.tools.mcp_metadata import get_mcp_server, is_mcp_tool

logger = logging.getLogger(__name__)

# Key the gateway injects into ``config["context"]``; ``_make_lead_agent``
# reads it via ``_get_runtime_config``. A value of ``None`` (absent) means
# "inherit the global MCP server set".
MCP_ENABLED_SERVERS_CONTEXT_KEY = "mcp_enabled_servers"


async def resolve_mcp_enabled_servers(user_id: str) -> list[str] | None:
    """Return the user's MCP server allowlist, or ``None`` to inherit global config.

    ``None`` means no per-user restriction: the full operator-enabled MCP
    server set applies. An empty list means the user disabled every MCP
    server. Any DB failure degrades to ``None`` so an unavailable settings
    table can never take MCP tools away from a conversation.
    """
    try:
        from tianshu.persistence.user_settings.sql import UserSettingsRepository

        raw = await UserSettingsRepository().get(user_id, "tools")
    except Exception:
        logger.warning(
            "Could not resolve per-user MCP settings for user %s; falling back to global config",
            user_id,
            exc_info=True,
        )
        return None

    if raw is None or raw.get("inherit_global", True):
        return None
    enabled = raw.get("enabled_servers")
    if not isinstance(enabled, list):
        return []
    return [name for name in enabled if isinstance(name, str) and name]


def filter_mcp_tools(
    tools: Iterable[BaseTool],
    enabled_servers: list[str] | None,
) -> list[BaseTool]:
    """Filter MCP tools down to *enabled_servers*; non-MCP tools always pass.

    ``enabled_servers is None`` keeps every tool (inherit global). An empty
    list keeps only non-MCP tools. Tools whose source server is unknown (no
    ``tianshu_mcp_server`` tag) are treated as from a non-allowed server and
    dropped when a restriction is active, since we cannot prove they belong to
    an allowed server.
    """
    if enabled_servers is None:
        return list(tools)
    allow: set[str] = {name for name in enabled_servers if isinstance(name, str)}
    kept: list[BaseTool] = []
    for tool in tools:
        if not is_mcp_tool(tool):
            kept.append(tool)
            continue
        if get_mcp_server(tool) in allow:
            kept.append(tool)
    return kept


def inject_mcp_enabled_servers(
    config: dict[str, Any],
    enabled_servers: list[str] | None,
) -> None:
    """Write the resolved allowlist into a run config's ``context`` section.

    ``None`` explicitly records "inherit global" so callers that later need to
    distinguish unset from all-disabled can rely on the key always being a
    list or ``None``.
    """
    context = config.setdefault("context", {})
    if isinstance(context, dict):
        context[MCP_ENABLED_SERVERS_CONTEXT_KEY] = enabled_servers
