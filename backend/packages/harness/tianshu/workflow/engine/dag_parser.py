"""DAG parser and validator for workflow definitions.

Parses a workflow definition (nodes + edges) into a directed graph,
validates structural correctness (no cycles, all connections valid),
and computes execution metadata (entry nodes, exit nodes, parallel groups).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class DAGNode:
    id: str
    node_type: str
    name: str
    config: dict = field(default_factory=dict)
    input_mapping: dict = field(default_factory=dict)
    position: dict = field(default_factory=lambda: {"x": 0, "y": 0})


@dataclass
class DAGEdge:
    id: str
    source: str
    target: str
    label: str = ""


@dataclass
class DAGGraph:
    nodes: dict[str, DAGNode]
    edges: list[DAGEdge]
    adjacency: dict[str, list[str]]
    in_degree: dict[str, int]
    entry_nodes: list[str]
    exit_nodes: list[str]


@dataclass
class ValidationError:
    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DAGParser:
    """Parses and validates workflow DAG definitions."""

    @staticmethod
    def parse(definition: dict) -> DAGGraph:
        """Parse a workflow definition into a DAG graph.

        Args:
            definition: Dict with 'nodes' and 'edges' lists.

        Returns:
            DAGGraph with adjacency lists and node metadata.
        """
        raw_nodes = definition.get("nodes", [])
        raw_edges = definition.get("edges", [])

        nodes: dict[str, DAGNode] = {}
        for rn in raw_nodes:
            node = DAGNode(
                id=rn["id"],
                node_type=rn.get("type", "code"),
                name=rn.get("name", rn["id"]),
                config=rn.get("config", {}),
                input_mapping=rn.get("input_mapping", {}),
                position=rn.get("position", {"x": 0, "y": 0}),
            )
            nodes[node.id] = node

        edges: list[DAGEdge] = []
        adjacency: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = defaultdict(int)

        for re in raw_edges:
            edge = DAGEdge(
                id=re.get("id", f"edge-{re['source']}-{re['target']}"),
                source=re["source"],
                target=re["target"],
                label=re.get("label", ""),
            )
            edges.append(edge)
            adjacency[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        entry_nodes = [nid for nid in nodes if in_degree[nid] == 0]
        exit_nodes = [nid for nid in nodes if nid not in adjacency or len(adjacency[nid]) == 0]

        return DAGGraph(
            nodes=nodes,
            edges=edges,
            adjacency=dict(adjacency),
            in_degree=dict(in_degree),
            entry_nodes=entry_nodes,
            exit_nodes=exit_nodes,
        )

    @staticmethod
    def validate(definition: dict) -> ValidationResult:
        """Validate a workflow definition.

        Checks:
        - All edges reference existing nodes
        - No cycles (DAG property)
        - At least one entry node and one exit node
        - Node IDs are unique

        Args:
            definition: Dict with 'nodes' and 'edges' lists.

        Returns:
            ValidationResult with errors and warnings.
        """
        errors: list[ValidationError] = []
        warnings: list[str] = []

        raw_nodes = definition.get("nodes", [])
        raw_edges = definition.get("edges", [])

        node_ids = set()
        for rn in raw_nodes:
            nid = rn.get("id", "")
            if not nid:
                errors.append(ValidationError(code="empty_node_id", message="Node has empty ID"))
            elif nid in node_ids:
                errors.append(ValidationError(code="duplicate_node_id", message=f"Duplicate node ID: {nid}", node_id=nid))
            node_ids.add(nid)

        if len(node_ids) == 0:
            errors.append(ValidationError(code="empty_workflow", message="Workflow has no nodes"))

        referenced_nodes: set[str] = set()
        for re in raw_edges:
            src = re.get("source", "")
            tgt = re.get("target", "")
            eid = re.get("id", "")

            if src and src not in node_ids:
                errors.append(ValidationError(code="invalid_edge_source", message=f"Edge source '{src}' does not exist", edge_id=eid))
            if tgt and tgt not in node_ids:
                errors.append(ValidationError(code="invalid_edge_target", message=f"Edge target '{tgt}' does not exist", edge_id=eid))

            if src:
                referenced_nodes.add(src)
            if tgt:
                referenced_nodes.add(tgt)

        if errors:
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        graph = DAGParser.parse(definition)

        if not graph.entry_nodes:
            errors.append(ValidationError(code="no_entry_node", message="Workflow has no entry nodes (nodes with no incoming edges)"))
        if not graph.exit_nodes:
            errors.append(ValidationError(code="no_exit_node", message="Workflow has no exit nodes (nodes with no outgoing edges)"))

        cycles = DAGParser.detect_cycles(graph)
        if cycles:
            for cycle in cycles:
                errors.append(ValidationError(
                    code="cycle_detected",
                    message=f"Cycle detected: {' -> '.join(cycle)}",
                ))

        for nid in node_ids:
            node_type = graph.nodes[nid].node_type
            if node_type not in ("agent", "code", "input", "output", "condition"):
                warnings.append(f"Node '{nid}' has unknown type '{node_type}'")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    @staticmethod
    def detect_cycles(graph: DAGGraph) -> list[list[str]]:
        """Detect cycles in a DAG using DFS.

        Args:
            graph: Parsed DAG graph.

        Returns:
            List of cycles found (each cycle is a list of node IDs).
        """
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for neighbor in graph.adjacency.get(node_id, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.discard(node_id)

        for node_id in graph.nodes:
            if node_id not in visited:
                dfs(node_id)

        return cycles

    @staticmethod
    def get_upstream_nodes(graph: DAGGraph, node_id: str) -> list[str]:
        """Get all nodes that have edges pointing to the given node.

        Args:
            graph: Parsed DAG graph.
            node_id: Target node ID.

        Returns:
            List of upstream node IDs.
        """
        upstream = []
        for edge in graph.edges:
            if edge.target == node_id:
                upstream.append(edge.source)
        return upstream

    @staticmethod
    def get_downstream_nodes(graph: DAGGraph, node_id: str) -> list[str]:
        """Get all nodes that the given node points to.

        Args:
            graph: Parsed DAG graph.
            node_id: Source node ID.

        Returns:
            List of downstream node IDs.
        """
        return graph.adjacency.get(node_id, [])
