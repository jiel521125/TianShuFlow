"""Tests for per-user MCP server filtering ("千人千面")."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tianshu.tools.mcp_filter import (
    MCP_ENABLED_SERVERS_CONTEXT_KEY,
    filter_mcp_tools,
    inject_mcp_enabled_servers,
    resolve_mcp_enabled_servers,
)
from tianshu.tools.mcp_metadata import (
    get_mcp_server,
    tag_mcp_server,
    tag_mcp_tool,
)


def _make_tool(name: str, *, mcp: bool = False, server: str | None = None):
    from langchain_core.tools import tool

    @tool(name)
    def _noop() -> str:
        """Tool stub."""
        return "ok"

    if mcp:
        tag_mcp_tool(_noop)
    if server is not None:
        tag_mcp_server(_noop, server)
    return _noop


# ---------------------------------------------------------------------------
# tag_mcp_server / get_mcp_server
# ---------------------------------------------------------------------------


def test_mcp_server_tag_roundtrip():
    tool = _make_tool("echo")
    assert get_mcp_server(tool) is None
    tag_mcp_server(tool, "filesystem")
    assert get_mcp_server(tool) == "filesystem"
    # Tagging an MCP tool does not remove its MCP-source flag.
    tag_mcp_tool(tool)
    assert get_mcp_server(tool) == "filesystem"


# ---------------------------------------------------------------------------
# filter_mcp_tools
# ---------------------------------------------------------------------------


def test_filter_none_keeps_everything():
    tools = [
        _make_tool("builtin"),
        _make_tool("mcp_a_t", mcp=True, server="mcp_a"),
        _make_tool("mcp_b_t", mcp=True, server="mcp_b"),
    ]
    assert filter_mcp_tools(tools, None) == tools


def test_filter_keeps_non_mcp_tools_always():
    builtin = _make_tool("builtin")
    mcp_a = _make_tool("mcp_a_t", mcp=True, server="mcp_a")
    mcp_b = _make_tool("mcp_b_t", mcp=True, server="mcp_b")
    kept = filter_mcp_tools([builtin, mcp_a, mcp_b], ["mcp_a"])
    assert kept == [builtin, mcp_a]


def test_filter_empty_allowlist_drops_all_mcp_tools():
    builtin = _make_tool("builtin")
    mcp = _make_tool("mcp_a_t", mcp=True, server="mcp_a")
    kept = filter_mcp_tools([builtin, mcp], [])
    assert kept == [builtin]


def test_filter_drops_untagged_mcp_tools_when_restriction_active():
    """An MCP tool without a server tag cannot be proven allowed → dropped."""
    builtin = _make_tool("builtin")
    untagged_mcp = _make_tool("mystery", mcp=True)
    kept = filter_mcp_tools([builtin, untagged_mcp], ["mcp_a"])
    assert kept == [builtin]


def test_filter_is_case_sensitive_and_exact():
    mcp_a = _make_tool("mcp_a_t", mcp=True, server="mcp_a")
    mcp_upper = _make_tool("mcp_A_t", mcp=True, server="mcp_A")
    kept = filter_mcp_tools([mcp_a, mcp_upper], ["mcp_a"])
    assert kept == [mcp_a]


# ---------------------------------------------------------------------------
# resolve_mcp_enabled_servers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_no_override_returns_none():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    with patch(
        "tianshu.persistence.user_settings.sql.UserSettingsRepository",
        return_value=repo,
    ):
        assert await resolve_mcp_enabled_servers("user-1") is None
    repo.get.assert_awaited_once_with("user-1", "tools")


@pytest.mark.asyncio
async def test_resolve_inherit_global_returns_none():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value={"inherit_global": True, "enabled_servers": []})
    with patch(
        "tianshu.persistence.user_settings.sql.UserSettingsRepository",
        return_value=repo,
    ):
        assert await resolve_mcp_enabled_servers("user-1") is None


@pytest.mark.asyncio
async def test_resolve_override_returns_allowlist():
    repo = AsyncMock()
    repo.get = AsyncMock(
        return_value={
            "inherit_global": False,
            "enabled_servers": ["mcp_a", "mcp_b", "", 42],
        }
    )
    with patch(
        "tianshu.persistence.user_settings.sql.UserSettingsRepository",
        return_value=repo,
    ):
        assert await resolve_mcp_enabled_servers("user-1") == ["mcp_a", "mcp_b"]


@pytest.mark.asyncio
async def test_resolve_empty_override_returns_empty_list():
    repo = AsyncMock()
    repo.get = AsyncMock(
        return_value={"inherit_global": False, "enabled_servers": []}
    )
    with patch(
        "tianshu.persistence.user_settings.sql.UserSettingsRepository",
        return_value=repo,
    ):
        assert await resolve_mcp_enabled_servers("user-1") == []


@pytest.mark.asyncio
async def test_resolve_db_failure_falls_back_to_global():
    repo = AsyncMock()
    repo.get = AsyncMock(side_effect=RuntimeError("db down"))
    with patch(
        "tianshu.persistence.user_settings.sql.UserSettingsRepository",
        return_value=repo,
    ):
        assert await resolve_mcp_enabled_servers("user-1") is None


# ---------------------------------------------------------------------------
# inject_mcp_enabled_servers
# ---------------------------------------------------------------------------


def test_inject_creates_context_when_missing():
    config: dict = {}
    inject_mcp_enabled_servers(config, ["mcp_a"])
    assert config["context"][MCP_ENABLED_SERVERS_CONTEXT_KEY] == ["mcp_a"]


def test_inject_merges_into_existing_context():
    config: dict = {"context": {"user_id": "user-1"}}
    inject_mcp_enabled_servers(config, None)
    assert config["context"]["user_id"] == "user-1"
    assert config["context"][MCP_ENABLED_SERVERS_CONTEXT_KEY] is None
