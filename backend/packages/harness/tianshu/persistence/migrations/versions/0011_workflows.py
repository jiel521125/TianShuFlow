"""workflow orchestration tables.

Revision ID: 0011_workflows
Revises: 0010_run_cancel_request
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_workflows"
down_revision: str | Sequence[str] | None = "0010_run_cancel_request"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("workflows"):
        op.create_table(
            "workflows",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("definition", sa.JSON(), nullable=False),
            sa.Column("input_schema", sa.JSON(), nullable=False),
            sa.Column("output_schema", sa.JSON(), nullable=True),
            sa.Column("is_template", sa.Boolean(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("workflows", schema=None) as batch_op:
            batch_op.create_index("ix_workflows_user_id", ["user_id"], unique=False)

    if not inspector.has_table("workflow_nodes"):
        op.create_table(
            "workflow_nodes",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("workflow_id", sa.String(length=64), nullable=False),
            sa.Column("node_type", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("input_mapping", sa.JSON(), nullable=False),
            sa.Column("position_x", sa.Integer(), nullable=False),
            sa.Column("position_y", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("workflow_nodes", schema=None) as batch_op:
            batch_op.create_index("ix_workflow_nodes_workflow_id", ["workflow_id"], unique=False)

    if not inspector.has_table("workflow_edges"):
        op.create_table(
            "workflow_edges",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("workflow_id", sa.String(length=64), nullable=False),
            sa.Column("source_node_id", sa.String(length=64), nullable=False),
            sa.Column("target_node_id", sa.String(length=64), nullable=False),
            sa.Column("label", sa.String(length=128), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["source_node_id"], ["workflow_nodes.id"]),
            sa.ForeignKeyConstraint(["target_node_id"], ["workflow_nodes.id"]),
            sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("workflow_edges", schema=None) as batch_op:
            batch_op.create_index("ix_workflow_edges_workflow_id", ["workflow_id"], unique=False)
            batch_op.create_index("ix_workflow_edges_source_node", ["source_node_id"], unique=False)
            batch_op.create_index("ix_workflow_edges_target_node", ["target_node_id"], unique=False)

    if not inspector.has_table("workflow_executions"):
        op.create_table(
            "workflow_executions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("workflow_id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("inputs", sa.JSON(), nullable=False),
            sa.Column("outputs", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("workflow_executions", schema=None) as batch_op:
            batch_op.create_index("ix_workflow_executions_workflow_id", ["workflow_id"], unique=False)
            batch_op.create_index("ix_workflow_executions_user_id", ["user_id"], unique=False)
            batch_op.create_index("ix_workflow_executions_status", ["status"], unique=False)

    if not inspector.has_table("workflow_execution_steps"):
        op.create_table(
            "workflow_execution_steps",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("execution_id", sa.String(length=64), nullable=False),
            sa.Column("node_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("input_data", sa.JSON(), nullable=True),
            sa.Column("output_data", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"]),
            sa.ForeignKeyConstraint(["node_id"], ["workflow_nodes.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("workflow_execution_steps", schema=None) as batch_op:
            batch_op.create_index("ix_exec_steps_execution_id", ["execution_id"], unique=False)
            batch_op.create_index("ix_exec_steps_node_id", ["node_id"], unique=False)
            batch_op.create_index("ix_exec_steps_status", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("workflow_execution_steps")
    op.drop_table("workflow_executions")
    op.drop_table("workflow_edges")
    op.drop_table("workflow_nodes")
    op.drop_table("workflows")
