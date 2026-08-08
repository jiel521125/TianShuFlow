"""user_models.

Revision ID: 0012_user_models
Revises: 0011_workflows
Create Date: 2026-08-06

Adds ``user_models`` -- the per-user model registration table that
backs ``GET /api/user/models`` and the new "Models" section of the
settings dialog. Each row stores a (user_id, name) handle plus the
provider type, model identifier, optional base_url/api_key, and a
free-form ``parameters`` JSON blob forwarded to the langchain chat
model constructor.

A user can register an arbitrary number of models; they appear in the
frontend model selector alongside the system-configured models from
``AppConfig.models``. ``name`` collisions between system and user
models are resolved in favour of the user row (matches the same
override semantics used for agents).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_user_models"
down_revision: str | Sequence[str] | None = "0011_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("user_models"):
        # Idempotent: a DB whose full-metadata create_all already
        # provisioned the table (e.g. legacy test seeds) must not have
        # it re-created here. Same pattern as 0006_agents.
        return
    op.create_table(
        "user_models",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("model", sa.String(length=256), nullable=False),
        # No server_default: matches the ORM's Python-side default=dict.
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("supports_thinking", sa.Boolean(), nullable=False),
        sa.Column("supports_reasoning_effort", sa.Boolean(), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_user_models_user_name"),
    )
    with op.batch_alter_table("user_models", schema=None) as batch_op:
        batch_op.create_index("ix_user_models_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("user_models", schema=None) as batch_op:
        batch_op.drop_index("ix_user_models_user_id")
    op.drop_table("user_models")