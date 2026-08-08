"""Node executor dispatch and registry.

Routes node execution to the appropriate executor based on node type.
Provides a registry for extensible node type registration.
"""

from __future__ import annotations

import ast
import logging
import operator
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tianshu.workflow.engine.dag_parser import DAGNode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safe expression evaluator for condition nodes.
#
# Replaces the previous ``eval(expression, ...)`` call which was vulnerable
# to sandbox escape (``__builtins__`` restriction is bypassable in CPython).
# This AST-based evaluator only allows a fixed set of node types and
# operators — no attribute access, no calls (except a tiny allowlist), no
# imports, no comprehensions with side effects.
# ---------------------------------------------------------------------------

_BIN_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_CMP_OPS: dict[type, Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_BOOL_OPS: dict[type, Any] = {
    ast.And: all,
    ast.Or: any,
}

_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

_ALLOWED_FUNCS = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
}


class _SafeExprVisitor(ast.NodeVisitor):
    """Evaluates an AST expression tree with a restricted node allowlist."""

    def __init__(self, variables: dict[str, Any]) -> None:
        self._vars = variables

    def evaluate(self, expression: str) -> Any:
        tree = ast.parse(expression, mode="eval")
        return self.visit(tree.body)

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        name = node.id
        if name in _ALLOWED_FUNCS:
            return _ALLOWED_FUNCS[name]
        if name in self._vars:
            return self._vars[name]
        if name in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[name]
        raise NameError(f"Name '{name}' is not defined")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_func = _BIN_OPS.get(type(node.op))
        if op_func is None:
            raise TypeError(f"Operator {type(node.op).__name__} is not allowed")
        return op_func(left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        op_func = _UNARY_OPS.get(type(node.op))
        if op_func is None:
            raise TypeError(f"Unary operator {type(node.op).__name__} is not allowed")
        return op_func(operand)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [self.visit(v) for v in node.values]
        op_func = _BOOL_OPS.get(type(node.op))
        if op_func is None:
            raise TypeError(f"Boolean operator {type(node.op).__name__} is not allowed")
        return op_func(values)

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            op_func = _CMP_OPS.get(type(op))
            if op_func is None:
                raise TypeError(f"Comparison {type(op).__name__} is not allowed")
            if not op_func(left, right):
                return False
            left = right
        return True

    def visit_Call(self, node: ast.Call) -> Any:
        func = self.visit(node.func)
        if not callable(func) or func not in _ALLOWED_FUNCS.values():
            raise TypeError("Only allowlisted functions may be called")
        args = [self.visit(a) for a in node.args]
        if node.keywords:
            raise TypeError("Keyword arguments are not allowed")
        return func(*args)

    def visit_List(self, node: ast.List) -> list:
        return [self.visit(e) for e in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> tuple:
        return tuple(self.visit(e) for e in node.elts)

    def visit_Dict(self, node: ast.Dict) -> dict:
        return {
            self.visit(k): self.visit(v)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        value = self.visit(node.value)
        slice_val = self.visit(node.slice)
        return value[slice_val]

    def generic_visit(self, node: ast.AST) -> Any:
        raise TypeError(f"AST node {type(node).__name__} is not allowed in condition expressions")


def safe_eval_expression(expression: str, variables: dict[str, Any]) -> Any:
    """Safely evaluate a restricted Python expression.

    Only allows: literals, names, binary/unary/boolean/comparison operators,
    subscripting, and calls to a small allowlist of built-in functions
    (len, str, int, float, bool, abs, round, min, max, sum).

    Raises:
        SyntaxError: if the expression is not valid Python.
        TypeError: if the expression contains a disallowed AST node.
        NameError: if a name is not in ``variables`` or the allowlist.
    """
    visitor = _SafeExprVisitor(variables)
    return visitor.evaluate(expression)


# ---------------------------------------------------------------------------
# Execution context and result types
# ---------------------------------------------------------------------------


@dataclass
class ExecutionContext:
    """Context passed to each node during workflow execution.

    The context maintains the data flow between nodes:
    - ``inputs``: user-provided workflow inputs (e.g. chat message)
    - ``node_outputs``: map of node_id -> output_dict, populated as nodes complete
    - ``metadata``: execution metadata (upstream_ids, etc.)

    The ``get_node_inputs()`` method resolves what a specific node should
    receive as input: it merges the user inputs with the outputs of that
    node's upstream (predecessor) nodes, respecting any ``input_mapping``
    defined on the target node.
    """

    execution_id: str
    workflow_id: str
    user_id: str
    inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_upstream_output(self, node_id: str) -> dict[str, Any]:
        """Get the output of a specific upstream node."""
        return self.node_outputs.get(node_id, {})

    def get_node_inputs(self, upstream_ids: list[str], input_mapping: dict[str, Any] | None = None) -> dict[str, Any]:
        """Resolve inputs for a node by merging upstream outputs.

        1. Start with the user-provided ``inputs``.
        2. Merge the output dict of every upstream node.
        3. If an ``input_mapping`` is defined, remap keys from upstream
           outputs to the names expected by the target node.
        4. Return the final resolved input dictionary.

        Args:
            upstream_ids: IDs of nodes whose outputs should be consumed.
            input_mapping: Optional mapping of {source_node_id: {source_key: target_key}}.
                           Example: {"n1": {"topic": "question"}} maps the "topic" key
                           from node n1's output to "question" in the resolved inputs.

        Returns:
            Dictionary of resolved inputs for the target node.
        """
        resolved: dict[str, Any] = {}

        # Step 1: user inputs (e.g. {"message": "hello", "topic": "AI"})
        resolved.update(self.inputs)

        # Step 2: upstream node outputs
        for uid in upstream_ids:
            upstream_out = self.node_outputs.get(uid, {})
            if not upstream_out:
                continue

            if input_mapping and uid in input_mapping:
                mapping: dict[str, str] = input_mapping[uid]
                for src_key, tgt_key in mapping.items():
                    if src_key in upstream_out:
                        resolved[tgt_key] = upstream_out[src_key]
            else:
                # No mapping — merge all keys directly
                resolved.update(upstream_out)

        return resolved


@dataclass
class NodeResult:
    """Result of a node execution."""

    node_id: str
    node_type: str
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0


class NodeExecutor(ABC):
    """Abstract base class for node executors."""

    @abstractmethod
    def node_type(self) -> str:
        """Return the node type this executor handles."""
        ...

    @abstractmethod
    async def execute(self, node: DAGNode, context: ExecutionContext) -> NodeResult:
        """Execute a node and return its result.

        Args:
            node: The DAG node to execute.
            context: The execution context with inputs and upstream outputs.

        Returns:
            NodeResult with the execution output.
        """
        ...


class NodeExecutorRegistry:
    """Registry mapping node types to executors."""

    _executors: dict[str, NodeExecutor] = {}

    @classmethod
    def register(cls, executor: NodeExecutor) -> None:
        """Register an executor for a node type."""
        node_type = executor.node_type()
        cls._executors[node_type] = executor
        logger.info("Registered node executor for type: %s", node_type)

    @classmethod
    def get(cls, node_type: str) -> NodeExecutor | None:
        """Get the executor for a node type."""
        return cls._executors.get(node_type)

    @classmethod
    def available_types(cls) -> list[str]:
        """Return all registered node types."""
        return list(cls._executors.keys())


class DefaultInputExecutor(NodeExecutor):
    """Executor for input nodes - passes initial inputs through.

    Input nodes are typically entry points (no upstream dependencies).
    They read values from the user-provided ``context.inputs`` dict.
    If the node has upstream nodes (e.g. it's not an entry point),
    those outputs are merged in as well, allowing the input node to
    act as a data aggregation step.

    Config:
        - input_key (str): The key to extract from context.inputs.
        - default_value (Any): Fallback when the key is not found.
    """

    def node_type(self) -> str:
        return "input"

    async def execute(self, node: DAGNode, context: ExecutionContext) -> NodeResult:
        input_key = node.config.get("input_key", node.id)
        default_value = node.config.get("default_value", "")

        upstream_ids = context.metadata.get("upstream_ids", [])
        if upstream_ids:
            resolved = context.get_node_inputs(upstream_ids, node.input_mapping)
            value = resolved.get(input_key, default_value)
        else:
            value = context.inputs.get(input_key, default_value)

        output: dict[str, Any] = {input_key: value}

        # Also expose all resolved inputs so downstream nodes can
        # reference them without knowing the exact key structure.
        upstream_ids = context.metadata.get("upstream_ids", [])
        if upstream_ids:
            resolved = context.get_node_inputs(upstream_ids, node.input_mapping)
            output.update(resolved)

        return NodeResult(
            node_id=node.id,
            node_type="input",
            success=True,
            output=output,
        )


class DefaultOutputExecutor(NodeExecutor):
    """Executor for output nodes - aggregates upstream node outputs.

    Output nodes collect the outputs of all upstream nodes and present
    them as the final workflow result. Supports two aggregation modes:

    - ``"merge"`` (default): merge all upstream output dicts.  Later
      nodes' keys overwrite earlier ones in case of collision.
    - ``"last"``: use only the output of the most recently completed
      upstream node (determined by topological order).

    The resolved inputs (user inputs + upstream outputs) are also
    included as ``__inputs__`` in the output for downstream nodes
    that may need the full context.
    """

    def node_type(self) -> str:
        return "output"

    async def execute(self, node: DAGNode, context: ExecutionContext) -> NodeResult:
        aggregation = node.config.get("aggregation", "merge")
        upstream_ids = context.metadata.get("upstream_ids", [])

        if aggregation == "last":
            output = {}
            for uid in reversed(upstream_ids):
                if uid in context.node_outputs:
                    output = context.node_outputs[uid]
                    break
            return NodeResult(
                node_id=node.id,
                node_type="output",
                success=True,
                output=output,
            )
        else:
            merged: dict[str, Any] = {}
            for uid in upstream_ids:
                if uid in context.node_outputs:
                    merged.update(context.node_outputs[uid])

            # Include the fully resolved inputs so downstream consumers
            # (e.g. the chat-workflow bridge) can access the full context.
            resolved = context.get_node_inputs(upstream_ids, node.input_mapping)
            merged["__inputs__"] = resolved

            return NodeResult(
                node_id=node.id,
                node_type="output",
                success=True,
                output=merged,
            )


class DefaultConditionExecutor(NodeExecutor):
    """Executor for condition nodes - evaluates a condition expression.

    The condition expression is evaluated using a safe AST-based evaluator
    (``safe_eval_expression``) that only allows basic arithmetic, comparisons,
    boolean operations, and a small allowlist of built-in functions.
    No attribute access, imports, or arbitrary function calls are permitted.

    The variables available in the expression are the resolved inputs —
    that is, the user inputs merged with the outputs of upstream nodes
    (respecting ``input_mapping``).

    Config:
        - expression (str): Python expression that evaluates to a bool.
    """

    def node_type(self) -> str:
        return "condition"

    async def execute(self, node: DAGNode, context: ExecutionContext) -> NodeResult:
        expression = node.config.get("expression", "True")
        upstream_ids = context.metadata.get("upstream_ids", [])

        # Resolve inputs: user inputs + upstream node outputs
        variables = context.get_node_inputs(upstream_ids, node.input_mapping)

        try:
            result = bool(safe_eval_expression(expression, variables))
        except Exception as e:
            return NodeResult(
                node_id=node.id,
                node_type="condition",
                success=False,
                error=f"Condition evaluation failed: {e}",
            )

        return NodeResult(
            node_id=node.id,
            node_type="condition",
            success=True,
            output={
                "condition_result": result,
                "branch": "true" if result else "false",
                "evaluated_inputs": variables,
            },
        )


def register_default_executors() -> None:
    """Register all default node executors."""
    NodeExecutorRegistry.register(DefaultInputExecutor())
    NodeExecutorRegistry.register(DefaultOutputExecutor())
    NodeExecutorRegistry.register(DefaultConditionExecutor())
