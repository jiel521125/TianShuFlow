"""workspaces.

Revision ID: 0014_workspaces
Revises: 0013_user_settings
Create Date: 2026-08-06

Adds the per-user personal space ("工作空间") hierarchy that backs
``/api/workspaces``:

- ``user_workspaces``    -- one personal space per user
- ``workspace_folders``  -- project folders inside a space (folder = project)
- ``workspace_files``    -- documents / file records inside a folder

Storage policy: metadata plus Markdown body only; binary content is
never stored (``storage_status``/``content_ref`` reserve the seam for a
future cloud-storage backend). Owner isolation is enforced with a
redundant ``user_id`` column on every row plus per-user unique names.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_workspaces"
down_revision: str | Sequence[str] | None = "0013_user_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("user_workspaces"):
        # Idempotent: full-metadata create_all (legacy test seeds) may
        # already have provisioned the tables. Same pattern as 0013.
        return

    op.create_table(
        "user_workspaces",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_user_workspaces_user_name"),
    )
    with op.batch_alter_table("user_workspaces", schema=None) as batch_op:
        batch_op.create_index("ix_user_workspaces_user_id", ["user_id"], unique=False)

    op.create_table(
        "workspace_folders",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_workspace_folders_ws_name"),
    )
    with op.batch_alter_table("workspace_folders", schema=None) as batch_op:
        batch_op.create_index("ix_workspace_folders_ws_id", ["workspace_id"], unique=False)
        batch_op.create_index("ix_workspace_folders_user_id", ["user_id"], unique=False)

    op.create_table(
        "workspace_files",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("folder_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("extension", sa.String(length=20), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("storage_status", sa.String(length=20), nullable=False, server_default="embedded"),
        sa.Column("content_ref", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folder_id", "name", name="uq_workspace_files_folder_name"),
    )
    with op.batch_alter_table("workspace_files", schema=None) as batch_op:
        batch_op.create_index("ix_workspace_files_folder_id", ["folder_id"], unique=False)
        batch_op.create_index("ix_workspace_files_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("workspace_files", schema=None) as batch_op:
        batch_op.drop_index("ix_workspace_files_user_id")
        batch_op.drop_index("ix_workspace_files_folder_id")
    op.drop_table("workspace_files")

    with op.batch_alter_table("workspace_folders", schema=None) as batch_op:
        batch_op.drop_index("ix_workspace_folders_user_id")
        batch_op.drop_index("ix_workspace_folders_ws_id")
    op.drop_table("workspace_folders")

    with op.batch_alter_table("user_workspaces", schema=None) as batch_op:
        batch_op.drop_index("ix_user_workspaces_user_id")
    op.drop_table("user_workspaces")
