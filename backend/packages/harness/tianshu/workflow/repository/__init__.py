"""Workflow data access layer (Repository pattern).

Provides CRUD operations for workflow definitions, nodes, edges,
and execution tracking. Uses SQLAlchemy async sessions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tianshu.persistence.workflows.model import (
    WorkflowEdgeRow,
    WorkflowExecutionRow,
    WorkflowExecutionStepRow,
    WorkflowNodeRow,
    WorkflowRow,
)


class WorkflowRepository:
    """Data access layer for workflow entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: str,
        name: str,
        description: str,
        definition: dict[str, Any],
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> WorkflowRow:
        """Create a new workflow with its nodes and edges.

        Workflow is flushed before nodes, and nodes before edges, to
        satisfy foreign-key ordering.
        """
        wf_id = str(uuid.uuid4())

        row = WorkflowRow(
            id=wf_id,
            user_id=user_id,
            name=name,
            description=description,
            definition=definition,
            input_schema=input_schema or {},
            output_schema=output_schema,
            is_template=False,
            version=1,
        )
        self._session.add(row)
        # Flush workflow so its PK is persisted before nodes reference it
        await self._session.flush()

        nodes = definition.get("nodes", [])
        # Generate unique node IDs scoped to this workflow so that
        # node IDs like "n1", "n2" can be reused across workflows.
        id_mapping: dict[str, str] = {}
        for node_data in nodes:
            original_id = node_data.get("id", str(uuid.uuid4()))
            unique_id = f"{wf_id}_{original_id}"
            id_mapping[original_id] = unique_id

        for node_data in nodes:
            original_id = node_data.get("id", str(uuid.uuid4()))
            node_id = id_mapping[original_id]
            pos = node_data.get("position", {})
            node_row = WorkflowNodeRow(
                id=node_id,
                workflow_id=wf_id,
                node_type=node_data.get("type", "code"),
                name=node_data.get("name", node_id),
                config=node_data.get("config", {}),
                input_mapping=node_data.get("input_mapping", {}),
                position_x=pos.get("x", 0),
                position_y=pos.get("y", 0),
                sort_order=node_data.get("sort_order", 0),
            )
            self._session.add(node_row)

        # Update the definition to use unique node IDs and edge IDs
        import copy
        updated_definition = copy.deepcopy(definition)
        for node in updated_definition.get("nodes", []):
            if node["id"] in id_mapping:
                node["id"] = id_mapping[node["id"]]
        for edge in updated_definition.get("edges", []):
            if edge.get("id"):
                edge["id"] = f"{wf_id}_{edge['id']}"
            if edge.get("source") in id_mapping:
                edge["source"] = id_mapping[edge["source"]]
            if edge.get("target") in id_mapping:
                edge["target"] = id_mapping[edge["target"]]
        row.definition = updated_definition

        # Flush nodes so their PKs are persisted before edges reference them
        await self._session.flush()

        edges = definition.get("edges", [])
        # Generate unique edge IDs scoped to this workflow
        for edge_data in edges:
            original_edge_id = edge_data.get("id", str(uuid.uuid4()))
            unique_edge_id = f"{wf_id}_{original_edge_id}"
            edge_row = WorkflowEdgeRow(
                id=unique_edge_id,
                workflow_id=wf_id,
                source_node_id=id_mapping.get(
                    edge_data.get("source", ""),
                    edge_data.get("source", ""),
                ),
                target_node_id=id_mapping.get(
                    edge_data.get("target", ""),
                    edge_data.get("target", ""),
                ),
                label=edge_data.get("label", ""),
                sort_order=edge_data.get("sort_order", 0),
            )
            self._session.add(edge_row)

        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def get_by_id(self, workflow_id: str) -> WorkflowRow | None:
        """Get a workflow by ID."""
        result = await self._session.execute(
            select(WorkflowRow).where(WorkflowRow.id == workflow_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: str,
        *,
        search: str = "",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[WorkflowRow], int]:
        """List workflows for a user with optional search."""
        query = select(WorkflowRow).where(WorkflowRow.user_id == user_id)

        if search:
            query = query.where(WorkflowRow.name.ilike(f"%{search}%"))

        count_query = select(WorkflowRow).where(WorkflowRow.user_id == user_id)
        if search:
            count_query = count_query.where(WorkflowRow.name.ilike(f"%{search}%"))

        from sqlalchemy import func

        count_result = await self._session.execute(
            select(func.count()).select_from(count_query.subquery())
        )
        total = count_result.scalar() or 0

        result = await self._session.execute(
            query.order_by(WorkflowRow.updated_at.desc()).offset(offset).limit(limit)
        )
        rows = result.scalars().all()

        return list(rows), total

    async def update(
        self,
        workflow_id: str,
        user_id: str,
        name: str | None = None,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
        input_schema: dict[str, Any] | None = None,
    ) -> WorkflowRow | None:
        """Update a workflow."""
        row = await self.get_by_id(workflow_id)
        if row is None or row.user_id != user_id:
            return None

        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        if definition is not None:
            row.definition = definition
            nodes = definition.get("nodes", [])
            await self._session.execute(
                WorkflowNodeRow.__table__.delete().where(WorkflowNodeRow.workflow_id == workflow_id)
            )
            await self._session.execute(
                WorkflowEdgeRow.__table__.delete().where(WorkflowEdgeRow.workflow_id == workflow_id)
            )

            # Generate unique node IDs scoped to this workflow
            id_mapping: dict[str, str] = {}
            for node_data in nodes:
                original_id = node_data.get("id", str(uuid.uuid4()))
                unique_id = f"{workflow_id}_{original_id}"
                id_mapping[original_id] = unique_id

            for node_data in nodes:
                original_id = node_data.get("id", str(uuid.uuid4()))
                node_id = id_mapping[original_id]
                pos = node_data.get("position", {})
                self._session.add(WorkflowNodeRow(
                    id=node_id,
                    workflow_id=workflow_id,
                    node_type=node_data.get("type", "code"),
                    name=node_data.get("name", node_id),
                    config=node_data.get("config", {}),
                    input_mapping=node_data.get("input_mapping", {}),
                    position_x=pos.get("x", 0),
                    position_y=pos.get("y", 0),
                ))

            # Update definition with unique IDs
            import copy
            updated_def = copy.deepcopy(definition)
            for node in updated_def.get("nodes", []):
                if node["id"] in id_mapping:
                    node["id"] = id_mapping[node["id"]]
            for edge in updated_def.get("edges", []):
                if edge.get("id"):
                    edge["id"] = f"{workflow_id}_{edge['id']}"
                if edge.get("source") in id_mapping:
                    edge["source"] = id_mapping[edge["source"]]
                if edge.get("target") in id_mapping:
                    edge["target"] = id_mapping[edge["target"]]
            row.definition = updated_def

            # Flush nodes before edges to satisfy FK ordering
            await self._session.flush()
            # Use original definition edges (not updated_def which has prefixed IDs)
            for edge_data in definition.get("edges", []):
                original_edge_id = edge_data.get("id", str(uuid.uuid4()))
                unique_edge_id = f"{workflow_id}_{original_edge_id}"
                self._session.add(WorkflowEdgeRow(
                    id=unique_edge_id,
                    workflow_id=workflow_id,
                    source_node_id=id_mapping.get(edge_data.get("source", ""), edge_data.get("source", "")),
                    target_node_id=id_mapping.get(edge_data.get("target", ""), edge_data.get("target", "")),
                    label=edge_data.get("label", ""),
                ))
        if input_schema is not None:
            row.input_schema = input_schema

        row.version += 1
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def delete(self, workflow_id: str, user_id: str) -> bool:
        """Delete a workflow and all related data."""
        row = await self.get_by_id(workflow_id)
        if row is None or row.user_id != user_id:
            return False

        await self._session.execute(
            WorkflowExecutionStepRow.__table__.delete().where(
                WorkflowExecutionStepRow.execution_id.in_(
                    select(WorkflowExecutionRow.id).where(WorkflowExecutionRow.workflow_id == workflow_id)
                )
            )
        )
        await self._session.execute(
            WorkflowExecutionRow.__table__.delete().where(WorkflowExecutionRow.workflow_id == workflow_id)
        )
        await self._session.execute(
            WorkflowEdgeRow.__table__.delete().where(WorkflowEdgeRow.workflow_id == workflow_id)
        )
        await self._session.execute(
            WorkflowNodeRow.__table__.delete().where(WorkflowNodeRow.workflow_id == workflow_id)
        )
        await self._session.execute(
            WorkflowRow.__table__.delete().where(WorkflowRow.id == workflow_id)
        )
        await self._session.commit()
        return True

    async def create_execution(
        self,
        workflow_id: str,
        user_id: str,
        inputs: dict[str, Any],
        execution_id: str,
    ) -> WorkflowExecutionRow:
        """Create a new execution record."""
        row = WorkflowExecutionRow(
            id=execution_id,
            workflow_id=workflow_id,
            user_id=user_id,
            status="pending",
            inputs=inputs,
        )
        self._session.add(row)
        await self._session.commit()
        return row

    async def update_execution(
        self,
        execution_id: str,
        status: str,
        outputs: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> WorkflowExecutionRow | None:
        """Update execution status and results."""
        result = await self._session.execute(
            select(WorkflowExecutionRow).where(WorkflowExecutionRow.id == execution_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        row.status = status
        if outputs is not None:
            row.outputs = outputs
        if error_message:
            row.error_message = error_message
        if status in ("completed", "failed", "cancelled"):
            row.completed_at = datetime.now(UTC)

        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def list_executions(
        self,
        workflow_id: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[WorkflowExecutionRow], int]:
        """List executions for a workflow."""
        from sqlalchemy import func

        count_result = await self._session.execute(
            select(func.count()).select_from(WorkflowExecutionRow).where(
                WorkflowExecutionRow.workflow_id == workflow_id
            )
        )
        total = count_result.scalar() or 0

        result = await self._session.execute(
            select(WorkflowExecutionRow)
            .where(WorkflowExecutionRow.workflow_id == workflow_id)
            .order_by(WorkflowExecutionRow.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = result.scalars().all()
        return list(rows), total

    async def get_execution(self, execution_id: str) -> WorkflowExecutionRow | None:
        """Get an execution with its steps."""
        result = await self._session.execute(
            select(WorkflowExecutionRow).where(WorkflowExecutionRow.id == execution_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        steps_result = await self._session.execute(
            select(WorkflowExecutionStepRow)
            .where(WorkflowExecutionStepRow.execution_id == execution_id)
            .order_by(WorkflowExecutionStepRow.started_at)
        )
        steps = steps_result.scalars().all()
        row._steps = list(steps)
        return row

    async def get_nodes_for_workflow(self, workflow_id: str) -> list[WorkflowNodeRow]:
        """Get all nodes for a workflow."""
        result = await self._session.execute(
            select(WorkflowNodeRow)
            .where(WorkflowNodeRow.workflow_id == workflow_id)
            .order_by(WorkflowNodeRow.sort_order)
        )
        return list(result.scalars().all())

    async def get_edges_for_workflow(self, workflow_id: str) -> list[WorkflowEdgeRow]:
        """Get all edges for a workflow."""
        result = await self._session.execute(
            select(WorkflowEdgeRow)
            .where(WorkflowEdgeRow.workflow_id == workflow_id)
            .order_by(WorkflowEdgeRow.sort_order)
        )
        return list(result.scalars().all())
