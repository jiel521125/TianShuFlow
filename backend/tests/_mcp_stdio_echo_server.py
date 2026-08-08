"""Real stdio MCP server used by the MCP end-to-end integration test.

A minimal, deterministic MCP server exposing two tools:

- ``echo``: returns the input text verbatim (no state).
- ``add``: returns the sum of two integers.

It runs as a child process over stdio via the ``mcp`` SDK, so the integration
test exercises the real MCP handshake (initialize -> tools/list -> tools/call)
instead of mocks.
"""

from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


def _build_server() -> Server:
    server = Server("tianshu-e2e-stdio")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="echo",
                description="Echo the input text back unchanged.",
                inputSchema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            ),
            Tool(
                name="add",
                description="Add two integers and return the sum.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                    "required": ["a", "b"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "echo":
            text = arguments.get("text", "")
            return [TextContent(type="text", text=text)]
        if name == "add":
            total = int(arguments.get("a", 0)) + int(arguments.get("b", 0))
            return [TextContent(type="text", text=str(total))]
        raise ValueError(f"Unknown tool: {name}")

    return server


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await _build_server().run(
            read_stream,
            write_stream,
            _build_server().create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
