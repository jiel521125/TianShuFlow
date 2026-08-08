"""Agent and Code node executors for the workflow engine.

The CodeNodeExecutor runs user-supplied Python in an isolated subprocess
(not via ``exec()`` in the host process) so that workflow definitions
cannot achieve RCE on the gateway process. Inputs are injected as JSON
via a temp file; the subprocess writes its ``output`` variable back as
JSON on stdout.

The AgentNodeExecutor bridges the workflow engine with TianShu's existing
agent infrastructure. It creates an ephemeral thread, invokes the
specified agent, and captures the response as the node output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from typing import Any

from tianshu.workflow.engine.dag_parser import DAGNode
from tianshu.workflow.engine.node_executor import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
)

logger = logging.getLogger(__name__)

# Template for the sandboxed subprocess script. It loads inputs from a
# JSON file, runs the user code, and writes the ``output`` variable back
# as JSON on stdout. The user code runs in a restricted namespace that
# exposes only safe builtins — no ``__import__``, no ``open``, no
# ``eval``/``exec``/``compile``.
_SANDBOX_SCRIPT_TEMPLATE = '''\
import json
import sys

_INPUTS_PATH = sys.argv[1]

with open(_INPUTS_PATH, "r", encoding="utf-8") as _f:
    inputs = json.load(_f)

_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "int": int,
    "isinstance": isinstance, "len": len, "list": list, "map": map,
    "max": max, "min": min, "print": print, "range": range,
    "round": round, "set": set, "sorted": sorted, "str": str,
    "sum": sum, "tuple": tuple, "zip": zip, "True": True, "False": False,
    "None": None,
    "json": json,
}

_GANIMALS_GLOBALS = {"__builtins__": _SAFE_BUILTINS, "inputs": inputs}
_GANIMALS_LOCALS = dict(inputs)
_GANIMALS_LOCALS["output"] = {}

try:
    exec(compile(__user_code__, "<workflow_code>", "exec"), _GANIMALS_GLOBALS, _GANIMALS_LOCALS)
except Exception as _e:
    _GANIMALS_LOCALS["output"] = {"error": str(_e)}

_output_val = _GANIMALS_LOCALS.get("output", {})
if _output_val is None:
    _output_val = {}
if not isinstance(_output_val, dict):
    _output_val = {"result": _output_val}

print(json.dumps(_output_val, default=str, ensure_ascii=False))
'''


class AgentNodeExecutor(NodeExecutor):
    """Executes agent nodes by invoking the TianShu agent system.

    The agent node receives its inputs from the outputs of upstream
    nodes (resolved via ``ExecutionContext.get_node_inputs()``).
    These resolved inputs become the prompt context for the agent.

    Data flow:
        upstream node outputs → resolved inputs → prompt template → agent LLM call → output

    Config:
        - agent_name (str): Name of the custom agent to invoke.
        - prompt_template (str): Optional template with ``{variable}``
          placeholders.  If not provided, the resolved inputs are
          serialized and injected into a default template.
        - system_prompt (str): Optional system prompt override.
        - timeout (int): Execution timeout in seconds (default 120).
    """

    def node_type(self) -> str:
        return "agent"

    async def execute(self, node: DAGNode, context: ExecutionContext) -> NodeResult:
        start_time = time.time()
        agent_name = node.config.get("agent_name", "")
        prompt_template = node.config.get("prompt_template", "")
        system_prompt = node.config.get("system_prompt", "")
        model_name = node.config.get("model") or None
        timeout = int(node.config.get("timeout", 120))

        if not agent_name:
            return NodeResult(
                node_id=node.id,
                node_type="agent",
                success=False,
                error="Agent node missing 'agent_name' config",
                duration_ms=int((time.time() - start_time) * 1000),
            )

        # ── Resolve inputs from upstream nodes ────────────────────────
        upstream_ids = context.metadata.get("upstream_ids", [])
        resolved_inputs = context.get_node_inputs(upstream_ids, node.input_mapping)

        # ── Build the prompt ─────────────────────────────────────────
        if prompt_template:
            try:
                prompt = prompt_template.format(**resolved_inputs)
            except KeyError as e:
                return NodeResult(
                    node_id=node.id,
                    node_type="agent",
                    success=False,
                    error=f"Prompt template variable not found: {e}",
                    duration_ms=int((time.time() - start_time) * 1000),
                )
        else:
            # Default prompt: show the upstream context clearly
            input_str = json.dumps(resolved_inputs, default=str, ensure_ascii=False, indent=2)
            prompt = (
                f"Process the following input using agent '{agent_name}':\n\n"
                f"---INPUT DATA---\n{input_str}\n---END INPUT DATA---\n\n"
                f"Please analyze and process this data."
            )

        try:
            output = await self._invoke_agent(
                agent_name=agent_name,
                prompt=prompt,
                system_prompt=system_prompt,
                timeout=timeout,
                context=context,
                model_name=model_name,
            )

            # Attach the resolved inputs for downstream nodes
            output["__inputs__"] = resolved_inputs

            return NodeResult(
                node_id=node.id,
                node_type="agent",
                success=True,
                output=output,
                duration_ms=int((time.time() - start_time) * 1000),
            )

        except Exception as e:
            logger.exception("Agent execution failed for node %s", node.id)
            return NodeResult(
                node_id=node.id,
                node_type="agent",
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _invoke_agent(
        self,
        agent_name: str,
        prompt: str,
        system_prompt: str,
        timeout: int,
        context: ExecutionContext,
        *,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Invoke an agent and return its output.

        Uses the TianShu client to create an ephemeral thread, invoke
        the specified agent, and collect the response. The agent's own
        SOUL (system prompt) from the agent management system is used
        automatically; the node-level ``system_prompt`` is currently
        informational only. The node-level ``model`` config (when set)
        is forwarded to the client so workflow agent nodes honour their
        configured model instead of silently using the default.
        """
        import asyncio

        try:
            from tianshu.client import TianShuClient
            from tianshu.config.app_config import get_app_config

            # agent_name is a constructor parameter, not a per-call kwarg.
            # When the node's ``model`` config names a user-registered model
            # (a ``user_models`` row, not config.yaml), resolve it here in the
            # async layer — the psycopg session is bound to the event loop —
            # and hand the translated ``ModelConfig`` to the client so the
            # synchronous agent builder never touches the DB.
            user_model_config = None
            if model_name:
                app_config = get_app_config()
                if app_config.get_model_config(model_name) is None and context.user_id:
                    from tianshu.models.factory_user import resolve_user_model_config

                    user_model_config = await resolve_user_model_config(
                        context.user_id,
                        model_name,
                    )
            # Honor the deployment-wide recursion ceiling instead of the
            # client's hardcoded default (100), which long tool-calling
            # agent turns routinely exhaust.
            recursion_limit = get_app_config().max_recursion_limit

            # ``achat`` runs the agent's LangGraph ``astream``, which needs an
            # async checkpointer (``aget_tuple``). The sync ``get_checkpointer()``
            # saver only implements ``get_tuple``, so borrow the async provider
            # that the gateway lifespan uses (AsyncPostgresSaver). It also keeps
            # MCP tools on the main event loop — the sync ``chat()`` path runs
            # tools via ``asyncio.run()`` in a worker thread and hits a
            # cross-loop CancelledError on the MCP session. The node timeout
            # bounds the call so a model that loops on tools cannot pin the
            # workflow node forever.
            from tianshu.runtime.checkpointer.async_provider import make_checkpointer

            async with make_checkpointer() as checkpointer:
                client = TianShuClient(
                    agent_name=agent_name,
                    model_name=model_name,
                    model_config=user_model_config,
                    checkpointer=checkpointer,
                )

                response_text = await asyncio.wait_for(
                    client.achat(
                        prompt,
                        thread_id=None,  # auto-generate ephemeral thread
                        recursion_limit=recursion_limit,
                    ),
                    timeout=timeout,
                )

            return {
                "agent_name": agent_name,
                "model": model_name,
                "response": response_text or "",
            }

        except asyncio.TimeoutError:
            logger.warning(
                "Agent node invocation timed out after %ss for agent '%s'",
                timeout,
                agent_name,
            )
            return {
                "agent_name": agent_name,
                "response": "",
                "error": f"Agent invocation timed out after {timeout}s",
            }
        except ImportError:
            logger.warning("TianShuClient not available; agent node cannot execute")
            return {
                "agent_name": agent_name,
                "response": "",
                "error": "TianShuClient not available — agent system is not initialized",
            }
        except Exception as e:
            logger.exception("Agent invocation failed")
            return {
                "agent_name": agent_name,
                "response": "",
                "error": str(e),
            }


class CodeNodeExecutor(NodeExecutor):
    """Executes code nodes by running Python in an isolated subprocess.

    The code node receives inputs from the outputs of upstream nodes
    (resolved via ``ExecutionContext.get_node_inputs()``).  These are
    passed into the sandbox as the ``inputs`` variable, which the user
    code can read from to access data produced by previous nodes.

    Data flow:
        upstream node outputs → resolved inputs → sandbox ``inputs`` var → user code → output

    The user code runs in a separate ``python`` process with a restricted
    ``__builtins__`` namespace (no ``__import__``, ``open``, ``eval``,
    ``exec``, or ``compile`` on the host). Inputs are passed via a temp
    JSON file; the subprocess writes its ``output`` variable back as JSON
    on stdout. A timeout kills the process if it runs too long.

    Config:
        - code (str): Python code to execute.
        - language (str): Programming language (default 'python').
        - timeout (int): Execution timeout in seconds (default 60).
    """

    def node_type(self) -> str:
        return "code"

    async def execute(self, node: DAGNode, context: ExecutionContext) -> NodeResult:
        start_time = time.time()
        code = node.config.get("code", "")
        language = node.config.get("language", "python")
        timeout = int(node.config.get("timeout", 60))

        if not code:
            return NodeResult(
                node_id=node.id,
                node_type="code",
                success=False,
                error="Code node has empty code",
                duration_ms=int((time.time() - start_time) * 1000),
            )

        if language != "python":
            return NodeResult(
                node_id=node.id,
                node_type="code",
                success=False,
                error=f"Unsupported language: {language}. Only Python is supported.",
                duration_ms=int((time.time() - start_time) * 1000),
            )

        # ── Resolve inputs from upstream nodes ────────────────────────
        upstream_ids = context.metadata.get("upstream_ids", [])
        resolved_inputs = context.get_node_inputs(upstream_ids, node.input_mapping)

        try:
            output = await self._execute_code_sandboxed(code, resolved_inputs, timeout)

            # Attach the resolved inputs for downstream nodes
            output["__inputs__"] = resolved_inputs

            return NodeResult(
                node_id=node.id,
                node_type="code",
                success=True,
                output=output,
                duration_ms=int((time.time() - start_time) * 1000),
            )

        except Exception as e:
            logger.exception("Code execution failed for node %s", node.id)
            return NodeResult(
                node_id=node.id,
                node_type="code",
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _execute_code_sandboxed(
        self,
        code: str,
        inputs: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        """Execute Python code in an isolated subprocess.

        The user code is embedded into a sandbox script that restricts
        ``__builtins__`` to a safe allowlist. Inputs are passed via a
        temp JSON file. The subprocess prints its ``output`` variable
        as JSON on stdout.
        """
        # Build the sandbox script by splicing the user code into the
        # template. The user code is placed as a string literal so it
        # cannot break out of the template structure.
        user_code_literal = repr(code)
        script = _SANDBOX_SCRIPT_TEMPLATE.replace("__user_code__", user_code_literal)

        inputs_fd, inputs_path = tempfile.mkstemp(
            suffix=".json",
            prefix="workflow_inputs_",
        )
        script_fd, script_path = tempfile.mkstemp(
            suffix=".py",
            prefix="workflow_script_",
        )
        try:
            with os.fdopen(inputs_fd, "w", encoding="utf-8") as f:
                json.dump(inputs, f, ensure_ascii=False, default=str)

            with os.fdopen(script_fd, "w", encoding="utf-8") as f:
                f.write(script)

            # Run in a subprocess with the same Python interpreter.
            # The subprocess inherits no network or file access beyond
            # what the OS user has, and is killed after ``timeout``.
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                script_path,
                inputs_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "code_result": {"error": f"Execution timed out after {timeout}s"},
                }

            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                return {
                    "code_result": {
                        "error": f"Process exited with code {proc.returncode}",
                        "stderr": stderr[-2000:] if stderr else "",
                    },
                }

            if not stdout:
                return {
                    "code_result": {
                        "error": "No output produced",
                        "stderr": stderr[-2000:] if stderr else "",
                    },
                }

            # Parse the JSON output from the last line of stdout
            # (the sandbox script prints exactly one JSON line).
            last_line = stdout.splitlines()[-1] if stdout else ""
            try:
                result = json.loads(last_line)
            except json.JSONDecodeError:
                # If the user code printed other things, the last line
                # might not be JSON. Try to find the JSON line.
                for line in reversed(stdout.splitlines()):
                    line = line.strip()
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            result = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue
                else:
                    return {
                        "code_result": {
                            "error": "Could not parse output as JSON",
                            "stdout": stdout[-2000:],
                        },
                    }

            return {"code_result": result}

        finally:
            for path in (inputs_path, script_path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


def register_workflow_executors() -> None:
    """Register all workflow node executors."""
    from tianshu.workflow.engine.node_executor import NodeExecutorRegistry

    NodeExecutorRegistry.register(AgentNodeExecutor())
    NodeExecutorRegistry.register(CodeNodeExecutor())
