"""Main workflow engine - orchestrates DAG parsing, topological sorting,
node execution, and event streaming.

This is the central orchestrator for workflow execution. It:
1. Loads a workflow definition from the repository
2. Parses and validates the DAG structure
3. Computes topological ordering for execution
4. Executes nodes in order (serially or in parallel by level)
5. Emits SSE events for real-time monitoring
6. Persists execution results
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from tianshu.workflow.engine.dag_parser import (
    DAGGraph,
    DAGNode,
    DAGParser,
    ValidationResult,
)
from tianshu.workflow.engine.node_executor import (
    ExecutionContext,
    NodeExecutor,
    NodeExecutorRegistry,
    NodeResult,
    register_default_executors,
)
from tianshu.workflow.engine.topo_sorter import TopologicalSorter

logger = logging.getLogger(__name__)

register_default_executors()
try:
    from tianshu.workflow.engine.executors import register_workflow_executors
    register_workflow_executors()
except Exception:
    pass


@dataclass
class WorkflowEvent:
    """SSE event emitted during workflow execution."""

    event_type: str
    data: dict[str, Any]
    execution_id: str
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Format as SSE event string."""
        return f"event: {self.event_type}\ndata: {json.dumps(self.data)}\n\n"


class WorkflowEngine:
    """Core workflow execution engine.

    Usage:
        engine = WorkflowEngine()
        async for event in engine.execute(workflow_id, inputs):
            # Handle SSE event
            print(event.to_sse())
    """

    def __init__(self) -> None:
        self._cancel_requested: dict[str, bool] = {}
        self._execution_states: dict[str, dict[str, Any]] = {}

    def cancel_execution(self, execution_id: str) -> None:
        """Request cancellation of a running execution."""
        self._cancel_requested[execution_id] = True

    def is_cancelled(self, execution_id: str) -> bool:
        """Check if cancellation has been requested."""
        return self._cancel_requested.get(execution_id, False)

    async def execute(
        self,
        workflow_id: str,
        definition: dict[str, Any],
        inputs: dict[str, Any],
        user_id: str,
        execution_id: str,
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """Execute a workflow and yield SSE events.

        Args:
            workflow_id: The workflow identifier.
            definition: The workflow definition (nodes + edges).
            inputs: User-provided input parameters.
            user_id: The user executing the workflow.
            execution_id: Unique execution identifier.

        Yields:
            WorkflowEvent objects for each lifecycle event.
        """
        self._cancel_requested[execution_id] = False

        yield WorkflowEvent(
            event_type="workflow_started",
            execution_id=execution_id,
            data={
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "user_id": user_id,
            },
        )

        try:
            graph = DAGParser.parse(definition)
            validation = DAGParser.validate(definition)

            if not validation.valid:
                error_msgs = [e.message for e in validation.errors]
                yield WorkflowEvent(
                    event_type="workflow_failed",
                    execution_id=execution_id,
                    data={
                        "execution_id": execution_id,
                        "error": f"Workflow validation failed: {'; '.join(error_msgs)}",
                        "errors": [e.__dict__ for e in validation.errors],
                    },
                )
                return

            sorter_result = TopologicalSorter.sort(graph)
            parallel_groups = sorter_result.parallel_groups

            context = ExecutionContext(
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                inputs=inputs,
                node_outputs={},
                metadata={},
            )

            for group_idx, group in enumerate(parallel_groups):
                if self.is_cancelled(execution_id):
                    yield WorkflowEvent(
                        event_type="workflow_cancelled",
                        execution_id=execution_id,
                        data={"execution_id": execution_id},
                    )
                    return

                if len(group) == 1:
                    node_id = group[0]
                    yield WorkflowEvent(
                        event_type="node_started",
                        execution_id=execution_id,
                        data={
                            "execution_id": execution_id,
                            "node_id": node_id,
                            "node_type": graph.nodes[node_id].node_type,
                        },
                    )
                    result = await self._execute_single_node(node_id, graph, context, execution_id)
                    if result:
                        yield WorkflowEvent(
                            event_type="node_completed" if result.success else "node_failed",
                            execution_id=execution_id,
                            data={
                                "execution_id": execution_id,
                                "node_id": node_id,
                                "node_type": graph.nodes[node_id].node_type,
                                "success": result.success,
                                "output": result.output,
                                "error": result.error,
                                "duration_ms": result.duration_ms,
                            },
                        )
                        if not result.success:
                            yield WorkflowEvent(
                                event_type="workflow_failed",
                                execution_id=execution_id,
                                data={
                                    "execution_id": execution_id,
                                    "error": f"Node '{node_id}' failed: {result.error}",
                                    "failed_node_id": node_id,
                                },
                            )
                            return
                else:
                    for node_id in group:
                        yield WorkflowEvent(
                            event_type="node_started",
                            execution_id=execution_id,
                            data={
                                "execution_id": execution_id,
                                "node_id": node_id,
                                "node_type": graph.nodes[node_id].node_type,
                            },
                        )
                    results = await self._execute_parallel_group(group, graph, context, execution_id)
                    for node_id, result in results:
                        yield WorkflowEvent(
                            event_type="node_completed" if result.success else "node_failed",
                            execution_id=execution_id,
                            data={
                                "execution_id": execution_id,
                                "node_id": node_id,
                                "node_type": graph.nodes[node_id].node_type,
                                "success": result.success,
                                "output": result.output,
                                "error": result.error,
                                "duration_ms": result.duration_ms,
                            },
                        )
                        if not result.success:
                            yield WorkflowEvent(
                                event_type="workflow_failed",
                                execution_id=execution_id,
                                data={
                                    "execution_id": execution_id,
                                    "error": f"Node '{node_id}' failed: {result.error}",
                                    "failed_node_id": node_id,
                                },
                            )
                            return

            final_outputs: dict[str, Any] = {}
            for nid, out in context.node_outputs.items():
                final_outputs[nid] = out

            # ── Extract the primary result from exit node(s) ───────────
            exit_nodes = graph.exit_nodes
            primary_result: dict[str, Any] = {}
            for exit_nid in exit_nodes:
                if exit_nid in context.node_outputs:
                    primary_result = context.node_outputs[exit_nid]
                    break

            # If no explicit exit node output, fall back to the last node
            if not primary_result and context.node_outputs:
                last_nid = sorted(context.node_outputs.keys())[-1]
                primary_result = context.node_outputs[last_nid]

            yield WorkflowEvent(
                event_type="workflow_completed",
                execution_id=execution_id,
                data={
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "results": final_outputs,
                    "result": primary_result,
                    "node_count": len(graph.nodes),
                    "execution_steps": len(graph.nodes),
                },
            )

        except Exception as e:
            logger.exception("Workflow execution failed for %s", execution_id)
            yield WorkflowEvent(
                event_type="workflow_failed",
                execution_id=execution_id,
                data={
                    "execution_id": execution_id,
                    "error": str(e),
                },
            )
        finally:
            self._cancel_requested.pop(execution_id, None)

    async def _execute_single_node(
        self,
        node_id: str,
        graph: DAGGraph,
        context: ExecutionContext,
        execution_id: str,
    ) -> NodeResult | None:
        """Execute a single node and update context."""
        if node_id not in graph.nodes:
            return None

        node = graph.nodes[node_id]
        upstream_ids = DAGParser.get_upstream_nodes(graph, node_id)
        context.metadata["upstream_ids"] = upstream_ids

        executor = NodeExecutorRegistry.get(node.node_type)
        if executor is None:
            return NodeResult(
                node_id=node_id,
                node_type=node.node_type,
                success=False,
                error=f"No executor registered for node type: {node.node_type}",
            )

        result = await executor.execute(node, context)

        if result.success:
            context.node_outputs[node_id] = result.output

        return result

    async def _execute_parallel_group(
        self,
        group: list[str],
        graph: DAGGraph,
        context: ExecutionContext,
        execution_id: str,
    ) -> list[tuple[str, NodeResult]]:
        """Execute a group of nodes in parallel."""
        tasks = []
        for node_id in group:
            if node_id not in graph.nodes:
                continue

            node = graph.nodes[node_id]
            upstream_ids = DAGParser.get_upstream_nodes(graph, node_id)

            context.metadata["upstream_ids"] = upstream_ids

            executor = NodeExecutorRegistry.get(node.node_type)
            if executor is None:
                tasks.append(
                    (
                        node_id,
                        NodeResult(
                            node_id=node_id,
                            node_type=node.node_type,
                            success=False,
                            error=f"No executor for type: {node.node_type}",
                        ),
                    )
                )
                continue

            tasks.append((node_id, executor.execute(node, context)))

        results: list[tuple[str, NodeResult]] = []
        coros = [(nid, coro) for nid, coro in tasks]

        if not coros:
            return results

        executed = await asyncio.gather(*(coro for _, coro in coros), return_exceptions=True)

        for (nid, _), result in zip(coros, executed):
            if isinstance(result, Exception):
                result_obj = NodeResult(
                    node_id=nid,
                    node_type=graph.nodes[nid].node_type if nid in graph.nodes else "unknown",
                    success=False,
                    error=str(result),
                )
            else:
                result_obj = result
                if result_obj.success:
                    context.node_outputs[nid] = result_obj.output

            results.append((nid, result_obj))

        return results
