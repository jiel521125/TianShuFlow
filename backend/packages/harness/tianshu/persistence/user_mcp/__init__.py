"""Per-user MCP server registry (``user_mcp`` table).

Mirrors ``persistence.user_models``: each user registers their own MCP
servers, rows are isolated by ``user_id``, and the runtime builds tools
only from the current user's own registrations.
"""

from tianshu.persistence.user_mcp.model import UserMCPServerRow
from tianshu.persistence.user_mcp.sql import UserMCPServerRepository

__all__ = ["UserMCPServerRow", "UserMCPServerRepository"]
