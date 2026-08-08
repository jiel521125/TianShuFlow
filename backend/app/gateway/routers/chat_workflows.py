"""Chat-Workflow integration API router.

Provides endpoints for executing workflows within chat conversations,
making workflows usable as chat processing tools.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from tianshu.config.workflows_config import get_workflows_api_config
from tianshu.runtime.user_context import get_effective_user_id
from tianshu.workflow.engine.engine import WorkflowEngine, WorkflowEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat-workflows"])


def _require_workflows_api_enabled() -> None:
    if not get_workflows_api_config().enabled:
        raise HTTPException(
            status_code=403,
            detail="Workflow orchestration API is disabled.",
        )


@router.post(
    "/chat/workflows/{workflow_id}/execute",
    summary="Execute Workflow from Chat",
    description="Execute a workflow using a chat message as input and return results via SSE.",
)
async def execute_workflow_from_chat(
    workflow_id: str,
    body: dict[str, Any],
) -> StreamingResponse:
    """Execute a workflow triggered from a chat message.

    The workflow receives the chat message as input and its execution
    events are streamed back via SSE so the chat UI can display
    real-time progress.

    Data flow:
        chat message → workflow input → node1 output → node2 input → node2 output → ... → output node → result
    """
    _require_workflows_api_enabled()
    user_id = get_effective_user_id()

    message = body.get("message", "")
    thread_id = body.get("thread_id", "")
    additional_inputs = body.get("inputs", {})

    # Load workflow
    from tianshu.workflow.repository import WorkflowRepository
    from tianshu.persistence import get_session_factory

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="Database is not available.",
        )

    session = factory()
    repo = WorkflowRepository(session)

    workflow = await repo.get_by_id(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Build inputs from chat message — the message becomes the primary
    # data that flows through the workflow nodes.
    inputs = {
        "message": message,
        "user_input": message,
        "query": message,
        "text": message,
        "input": message,  # Generic key for input nodes to use
        **additional_inputs,
    }

    # Merge with workflow's input schema defaults
    definition = workflow.definition
    nodes = definition.get("nodes", [])
    for node in nodes:
        if node.get("type") == "input":
            config = node.get("config", {})
            input_key = config.get("input_key", "input")
            default_value = config.get("default_value", "")
            if input_key not in inputs and default_value:
                inputs[input_key] = default_value

    # Create execution record
    execution_id = str(uuid.uuid4())
    await repo.create_execution(
        workflow_id=workflow_id,
        user_id=user_id,
        inputs=inputs,
        execution_id=execution_id,
    )

    # Execute workflow
    engine = WorkflowEngine()

    async def event_generator():
        try:
            # Send initial event with message context
            yield WorkflowEvent(
                event_type="chat_workflow_started",
                execution_id=execution_id,
                data={
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "thread_id": thread_id,
                    "message": message,
                    "user_id": user_id,
                },
            ).to_sse()

            async for event in engine.execute(
                workflow_id=workflow_id,
                definition=definition,
                inputs=inputs,
                user_id=user_id,
                execution_id=execution_id,
            ):
                yield event.to_sse()

                # After workflow completes, send the result as a chat-compatible event
                if event.event_type == "workflow_completed":
                    # ── Extract the primary result from the workflow ────
                    # The engine now provides a "result" field containing
                    # the exit node's output.
                    primary_result = event.data.get("result", {})
                    all_results = event.data.get("results", {})

                    # Build a human-readable summary
                    final_output = ""
                    if primary_result:
                        # ── Extract a clean, human-readable result ─────────
                        # Strip internal `__inputs__` metadata that nodes use
                        # to pass context to downstream nodes — the user only
                        # cares about the actual output value.
                        clean_result = {
                            k: v for k, v in primary_result.items()
                            if k != "__inputs__"
                        }

                        # Try to extract the most relevant text content
                        # Check common output keys, including code_result
                        # which is what Code nodes produce.
                        for key in (
                            "response", "output", "result", "text",
                            "content", "message", "greeting",
                            "code_result", "analysis", "processed_message",
                        ):
                            if key in clean_result:
                                val = clean_result[key]
                                if isinstance(val, str):
                                    final_output = val
                                    break
                                elif isinstance(val, (dict, list)):
                                    final_output = json.dumps(val, ensure_ascii=False, indent=2)
                                    break
                        if not final_output:
                            final_output = json.dumps(clean_result, ensure_ascii=False, indent=2)

                    if not final_output:
                        final_output = json.dumps(all_results, ensure_ascii=False)

                    yield WorkflowEvent(
                        event_type="chat_workflow_result",
                        execution_id=execution_id,
                        data={
                            "execution_id": execution_id,
                            "workflow_id": workflow_id,
                            "thread_id": thread_id,
                            "result": final_output,
                            "result_detail": primary_result,
                            "results": all_results,
                        },
                    ).to_sse()

                elif event.event_type == "workflow_failed":
                    yield WorkflowEvent(
                        event_type="chat_workflow_error",
                        execution_id=execution_id,
                        data={
                            "execution_id": execution_id,
                            "workflow_id": workflow_id,
                            "thread_id": thread_id,
                            "error": event.data.get("error", "Unknown error"),
                        },
                    ).to_sse()

            # Update execution status
            final_row = await repo.get_execution(execution_id)
            if final_row:
                if final_row.status == "pending":
                    await repo.update_execution(execution_id, "completed")

        except Exception as e:
            logger.exception("Chat workflow execution error")
            yield WorkflowEvent(
                event_type="workflow_failed",
                execution_id=execution_id,
                data={
                    "execution_id": execution_id,
                    "error": str(e),
                },
            ).to_sse()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/chat/workflows/{workflow_id}/cancel",
    summary="Cancel Chat Workflow Execution",
)
async def cancel_chat_workflow(workflow_id: str, execution_id: str) -> dict[str, Any]:
    """Cancel a running chat workflow execution."""
    _require_workflows_api_enabled()

    engine = WorkflowEngine()
    engine.cancel_execution(execution_id)

    return {
        "execution_id": execution_id,
        "status": "cancelled",
        "workflow_id": workflow_id,
    }