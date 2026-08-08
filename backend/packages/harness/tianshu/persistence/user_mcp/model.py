"""ORM model for user-registered MCP servers.

One row per ``(user_id, name)`` MCP server registered by a user. Each
user manages their own registry; rows are *visible* only to their owner
(``user_id == caller``), matching the isolation semantics of
``user_models``.

The runtime builds tools **only** from the current user's own rows --
the system-global ``extensions_config.json`` servers are no longer
injected into any user session. ``user_settings.tools``
(``inherit_global`` / ``enabled_servers``) decides which of the user's
own servers are actually loaded per chat.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from tianshu.persistence.base import Base


class UserMCPServerRow(Base):
    __tablename__ = "user_mcp"
    # Bind ORM to the application schema when database.backend=postgres,
    # same rationale as ``user_models`` / ``agents`` (psycopg server-side
    # prepared statements bypass search_path).
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_mcp_user_name"),
        {"schema": "tianshu"},
    )

    # Surrogate PK; (user_id, name) is the natural key.
    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex
    )

    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # User-facing handle used in the tools menu and in
    # ``user_settings.tools.enabled_servers``. Unique per user.
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Transport selector, mirroring the global server config:
    #   - "stdio" -> local command + args + env
    #   - "sse"   -> remote SSE endpoint (url)
    #   - "http"  -> remote HTTP endpoint (url)
    transport: Mapped[str] = mapped_column(String(16), nullable=False)

    # stdio transport fields.
    command: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    args: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    env: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # sse / http transport field.
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Whether built tool names are prefixed with the server name
    # (mirrors the global ``tool_name_prefix`` option).
    tool_name_prefix: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # Per-tool-call timeout in seconds (None -> global default).
    tool_call_timeout: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
