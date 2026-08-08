"""git folder fields.

Revision ID: 0016_git_folder_fields
Revises: 0015_user_mcp
Create Date: 2026-08-07

Adds the Git binding columns to ``workspace_folders``:

- ``git_provider``   -- ``github`` / ``gitee`` / NULL (not bound)
- ``git_repo_url``   -- remote repository URL (no token embedded)
- ``git_repo_name``  -- ``owner/repo`` display name
- ``git_updated_at`` -- last successful pull/push timestamp

A folder links to **one** remote repository at a time (write = replace).
Credentials stay out of this table entirely: they live in
``user_settings`` (section ``git``, keys ``github_token``/``gitee_token``)
and are resolved per-user at run time.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_git_folder_fields"
down_revision: str | Sequence[str] | None = "0015_user_mcp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(bind: sa.engine.Connection, column: str) -> bool:
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("workspace_folders")}
    return column in columns


def upgrade() -> None:
    bind = op.get_bind()
    if not bind.dialect.has_table(bind, "workspace_folders"):
        return
    with op.batch_alter_table("workspace_folders", schema=None) as batch_op:
        if not _has_column(bind, "git_provider"):
            batch_op.add_column(
                sa.Column("git_provider", sa.String(length=16), nullable=True)
            )
        if not _has_column(bind, "git_repo_url"):
            batch_op.add_column(
                sa.Column("git_repo_url", sa.String(length=2048), nullable=True)
            )
        if not _has_column(bind, "git_repo_name"):
            batch_op.add_column(
                sa.Column("git_repo_name", sa.String(length=255), nullable=True)
            )
        if not _has_column(bind, "git_updated_at"):
            batch_op.add_column(
                sa.Column("git_updated_at", sa.DateTime(timezone=True), nullable=True)
            )


def downgrade() -> None:
    bind = op.get_bind()
    if not bind.dialect.has_table(bind, "workspace_folders"):
        return
    with op.batch_alter_table("workspace_folders", schema=None) as batch_op:
        if _has_column(bind, "git_updated_at"):
            batch_op.drop_column("git_updated_at")
        if _has_column(bind, "git_repo_name"):
            batch_op.drop_column("git_repo_name")
        if _has_column(bind, "git_repo_url"):
            batch_op.drop_column("git_repo_url")
        if _has_column(bind, "git_provider"):
            batch_op.drop_column("git_provider")
