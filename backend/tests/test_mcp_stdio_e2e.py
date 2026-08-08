"""End-to-end integration tests against a REAL stdio MCP server.

The rest of the MCP test suite is mock-based; this file is the exception. It
boots a real MCP server as a stdio child process (``_mcp_stdio_echo_server.py``,
built on the ``mcp`` SDK), then drives two production paths end to end:

- ``tianshu.mcp.tools.get_mcp_tools()`` — real MCP handshake + tool discovery
- langchain ``create_agent`` with the fake chat model from
  ``_agent_e2e_helpers`` — the model emits a tool_call that the agent's ToolNode
  routes to the real MCP tool, and the tool result comes back to the model

This closes the coverage gap for "the model actually calls an MCP tool in a
conversation" that unit tests with mocked sessions cannot cover.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio

from tianshu.mcp.cache import reset_mcp_tools_cache
from tianshu.mcp.session_pool import get_session_pool, reset_session_pool
from tianshu.tools.mcp_metadata import MCP_TOOL_METADATA_KEY


def _write_extensions_config(tmp_path: Path) -> Path:
    server_script = Path(__file__).resolve().parent / "_mcp_stdio_echo_server.py"
    config = {
        "mcpServers": {
            "echo-server": {
                "enabled": True,
                "type": "stdio",
                "command": sys.executable,
                "args": [str(server_script)],
            }
        },
        "skills": {},
    }
    config_file = tmp_path / "extensions_config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    return config_file


@pytest_asyncio.fixture
async def mcp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Stage a real stdio MCP server and reset MCP process-wide state.

    Points ``TIAN_SHU_EXTENSIONS_CONFIG_PATH`` at a config that launches the
    real stdio server, then clears the tool cache and session pool so each
    test loads fresh state. Teardown kills the pooled child processes via
    ``close_all()`` so no subprocess leaks into later tests.
    """
    from tianshu.config.extensions_config import reload_extensions_config

    config_file = _write_extensions_config(tmp_path)
    monkeypatch.setenv("TIAN_SHU_EXTENSIONS_CONFIG_PATH", str(config_file))
    monkeypatch.setenv("TIAN_SHU_HOME", str(tmp_path / "tian-shu-home"))

    reset_session_pool()
    reset_mcp_tools_cache()
    reload_extensions_config()
    yield
    await get_session_pool().close_all()
    reset_session_pool()
    reset_mcp_tools_cache()


@pytest.mark.asyncio
async def test_real_stdio_mcp_server_loads_tools(mcp_env) -> None:
    """get_mcp_tools() discovers tools over a real stdio MCP handshake."""
    from tianshu.mcp.tools import get_mcp_tools

    tools = await get_mcp_tools()
    names = {tool.name for tool in tools}

    assert names == {"echo-server_echo", "echo-server_add"}
    for tool in tools:
        # Production tagging metadata must survive the load path.
        assert (tool.metadata or {}).get(MCP_TOOL_METADATA_KEY) is True
        # The source server is recorded for per-user MCP filtering.
        assert (tool.metadata or {}).get("tianshu_mcp_server") == "echo-server"


@pytest.mark.asyncio
async def test_real_stdio_mcp_server_executes_tool_calls(mcp_env) -> None:
    """Tool calls reach the real child process and return its output."""
    from tianshu.mcp.tools import get_mcp_tools

    tools = await get_mcp_tools()
    by_name = {tool.name: tool for tool in tools}

    echo_result = await by_name["echo-server_echo"].ainvoke({"text": "hello-mcp"})
    assert echo_result[0]["type"] == "text"
    assert echo_result[0]["text"] == "hello-mcp"

    add_result = await by_name["echo-server_add"].ainvoke({"a": 2, "b": 3})
    assert add_result[0]["type"] == "text"
    assert add_result[0]["text"] == "5"


@pytest.mark.asyncio
async def test_model_invokes_real_stdio_mcp_tool_in_agent_loop(mcp_env) -> None:
    """A model-emitted tool_call executes the real MCP tool mid-conversation."""
    from _agent_e2e_helpers import build_single_tool_call_model
    from langchain.agents import create_agent

    from tianshu.mcp.tools import get_mcp_tools

    tools = await get_mcp_tools()
    model = build_single_tool_call_model(
        tool_name="echo-server_echo",
        tool_args={"text": "hello-from-model"},
        tool_call_id="call_mcp_e2e_1",
        final_text="The tool echoed: hello-from-model",
    )

    agent = create_agent(model=model, tools=tools, system_prompt="test")
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "please echo hello-from-model",
                }
            ]
        },
        {"configurable": {"thread_id": "mcp-e2e-thread"}},
    )

    messages = result["messages"]
    final_text = messages[-1].content
    assert final_text == "The tool echoed: hello-from-model"
    # The ToolNode result must contain the real server's output.
    tool_result = messages[-2].content
    assert "hello-from-model" in str(tool_result)
