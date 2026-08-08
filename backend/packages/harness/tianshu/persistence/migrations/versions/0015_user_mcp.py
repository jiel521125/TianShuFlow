"""user_mcp.

Revision ID: 0015_user_mcp
Revises: 0014_workspaces
Create Date: 2026-08-07

Adds ``user_mcp`` -- the per-user MCP server registry that backs
``/api/user/mcp`` and the "Tools" section of the settings dialog.

Each user registers their own MCP servers; the runtime builds tools
**only** from the current user's own rows. The system-global
``extensions_config.json`` servers are no longer injected into any user
session. ``user_settings.tools`` (``inherit_global`` / ``enabled_servers``)
decides which of the user's own servers are loaded per chat --
"inherit_global" means the user's *own* full registry, not the system
global config.

Rows are isolated by ``(user_id, name)`` with a per-user unique
constraint, mirroring ``user_models``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_user_mcp"
down_revision: str | Sequence[str] | None = "0014_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("user_mcp"):
        # Idempotent: full-metadata create_all (legacy test seeds) may
        # already have provisioned the table. Same pattern as 0014.
        return
    op.create_table(
        "user_mcp",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("transport", sa.String(length=16), nullable=False),
        sa.Column("command", sa.String(length=1024), nullable=True),
        sa.Column("args", sa.JSON(), nullable=True),
        sa.Column("env", sa.JSON(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("tool_name_prefix", sa.Boolean(), nullable=False),
        sa.Column("tool_call_timeout", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_user_mcp_user_name"),
    )
    with op.batch_alter_table("user_mcp", schema=None) as batch_op:
        batch_op.create_index("ix_user_mcp_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("user_mcp", schema=None) as batch_op:
        batch_op.drop_index("ix_user_mcp_user_id")
    op.drop_table("user_mcp")
