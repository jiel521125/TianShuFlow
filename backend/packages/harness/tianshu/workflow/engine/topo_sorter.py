"""Topological sort for DAG execution ordering.

Implements Kahn's algorithm for level-based topological sorting,
which naturally identifies parallel execution groups.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from tianshu.workflow.engine.dag_parser import DAGGraph


@dataclass
class TopologicalResult:
    ordered_nodes: list[str]
    parallel_groups: list[list[str]]
    node_depth: dict[str, int] = field(default_factory=dict)


class TopologicalSorter:
    """Topological sort for DAG graphs with parallel group detection."""

    @staticmethod
    def sort(graph: DAGGraph) -> TopologicalResult:
        """Compute a level-based topological ordering.

        Each level (parallel group) contains nodes that can execute
        concurrently because they only depend on nodes from previous levels.

        Args:
            graph: Parsed DAG graph.

        Returns:
            TopologicalResult with ordered nodes and parallel groups.
        """
        in_degree = dict(graph.in_degree)
        for nid in graph.nodes:
            if nid not in in_degree:
                in_degree[nid] = 0

        adjacency = defaultdict(list)
        for src, targets in graph.adjacency.items():
            for tgt in targets:
                adjacency[src].append(tgt)

        queue: deque[str] = deque()
        for nid, deg in in_degree.items():
            if deg == 0:
                queue.append(nid)

        ordered: list[str] = []
        groups: list[list[str]] = []
        depth: dict[str, int] = {}
        current_depth = 0

        while queue:
            level_size = len(queue)
            current_group: list[str] = []

            for _ in range(level_size):
                node_id = queue.popleft()
                ordered.append(node_id)
                current_group.append(node_id)
                depth[node_id] = current_depth

                for neighbor in adjacency.get(node_id, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            if current_group:
                groups.append(current_group)
            current_depth += 1

        return TopologicalResult(
            ordered_nodes=ordered,
            parallel_groups=groups,
            node_depth=depth,
        )

    @staticmethod
    def get_execution_order(graph: DAGGraph) -> list[str]:
        """Get a simple flat topological order (no grouping).

        Args:
            graph: Parsed DAG graph.

        Returns:
            List of node IDs in execution order.
        """
        result = TopologicalSorter.sort(graph)
        return result.ordered_nodes
