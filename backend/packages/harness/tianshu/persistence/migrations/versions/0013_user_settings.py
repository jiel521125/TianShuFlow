"""user_settings.

Revision ID: 0013_user_settings
Revises: 0012_user_models
Create Date: 2026-08-06

Adds ``user_settings`` -- the per-user settings store that backs
``GET/PUT/DELETE /api/user/settings`` and gives each user their own
copy of appearance / notification / channels / integrations / tools
configuration ("千人千面").

Each row stores one *override* for one settings section under a
``(user_id, key)`` namespace. The gateway merges these overrides over
the server-side defaults registered in
``tianshu.settings.defaults`` -- a section with no row simply uses the
default. ``value`` is a schema-less JSON object validated by the
defaults registry before it is persisted.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_user_settings"
down_revision: str | Sequence[str] | None = "0012_user_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("user_settings"):
        # Idempotent: full-metadata create_all (legacy test seeds) may
        # already have provisioned the table. Same pattern as
        # 0012_user_models / 0006_agents.
        return
    op.create_table(
        "user_settings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        # No server_default: matches the ORM's Python-side default=dict.
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_user_settings_user_key"),
    )
    with op.batch_alter_table("user_settings", schema=None) as batch_op:
        batch_op.create_index("ix_user_settings_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("user_settings", schema=None) as batch_op:
        batch_op.drop_index("ix_user_settings_user_id")
    op.drop_table("user_settings")
