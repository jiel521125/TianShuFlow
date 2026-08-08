"""Workflow orchestration API router - CRUD + Execution + SSE.

Provides endpoints for managing workflow definitions and executing
them through the workflow engine with real-time SSE event streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from tianshu.config.workflows_config import get_workflows_api_config
from tianshu.persistence.workflows.model import (
    WorkflowEdgeRow,
    WorkflowExecutionRow,
    WorkflowExecutionStepRow,
    WorkflowNodeRow,
    WorkflowRow,
)
from tianshu.runtime.user_context import get_effective_user_id
from tianshu.workflow.engine.dag_parser import DAGParser
from tianshu.workflow.engine.engine import WorkflowEngine, WorkflowEvent
from tianshu.workflow.repository import WorkflowRepository
from tianshu.workflow.schemas import (
    ValidationErrorResponse,
    ValidationResultResponse,
    WorkflowCopyRequest,
    WorkflowCreateRequest,
    WorkflowExecutionDetailResponse,
    WorkflowExecutionListResponse,
    WorkflowExecutionResponse,
    WorkflowExecutionStepResponse,
    WorkflowExecuteRequest,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowUpdateRequest,
    WorkflowValidateRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["workflows"])


def _require_workflows_api_enabled() -> None:
    if not get_workflows_api_config().enabled:
        raise HTTPException(
            status_code=403,
            detail="Workflow orchestration API is disabled. Set workflows.api.enabled=true in config.yaml.",
        )


def _row_to_response(row: WorkflowRow) -> WorkflowResponse:
    return WorkflowResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        definition=row.definition,
        input_schema=row.input_schema or {},
        output_schema=row.output_schema,
        is_template=row.is_template,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _execution_to_response(row: WorkflowExecutionRow) -> WorkflowExecutionResponse:
    return WorkflowExecutionResponse(
        id=row.id,
        workflow_id=row.workflow_id,
        status=row.status,
        inputs=row.inputs or {},
        outputs=row.outputs,
        error_message=row.error_message or "",
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _step_to_response(row: WorkflowExecutionStepRow) -> WorkflowExecutionStepResponse:
    return WorkflowExecutionStepResponse(
        id=row.id,
        node_id=row.node_id,
        status=row.status,
        input_data=row.input_data,
        output_data=row.output_data,
        error_message=row.error_message or "",
        duration_ms=row.duration_ms,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _get_session() -> AsyncSession:
    from tianshu.persistence import get_session_factory

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="Database is not available. The workflow API requires a SQL database backend.",
        )
    return factory()


@router.post(
    "/workflows",
    response_model=WorkflowResponse,
    status_code=201,
    summary="Create Workflow",
    description="Create a new workflow definition with its DAG structure.",
)
async def create_workflow(request: WorkflowCreateRequest) -> WorkflowResponse:
    _require_workflows_api_enabled()
    user_id = get_effective_user_id()
    session = _get_session()

    definition_dict = request.definition.model_dump()

    validation = DAGParser.validate(definition_dict)
    if not validation.valid:
        errors = [ValidationErrorResponse(**e.__dict__) for e in validation.errors]
        raise HTTPException(status_code=400, detail={"errors": [e.model_dump() for e in errors]})

    repo = WorkflowRepository(session)
    row = await repo.create(
        user_id=user_id,
        name=request.name,
        description=request.description,
        definition=definition_dict,
        input_schema=request.input_schema,
    )
    return _row_to_response(row)


@router.get(
    "/workflows",
    response_model=WorkflowListResponse,
    summary="List Workflows",
    description="List all workflows for the current user.",
)
async def list_workflows(
    search: str = "",
    offset: int = 0,
    limit: int = 20,
) -> WorkflowListResponse:
    _require_workflows_api_enabled()
    user_id = get_effective_user_id()
    session = _get_session()
    repo = WorkflowRepository(session)
    rows, total = await repo.list_by_user(user_id, search=search, offset=offset, limit=limit)
    return WorkflowListResponse(
        total=total,
        workflows=[_row_to_response(r) for r in rows],
    )


@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get Workflow",
    description="Get a specific workflow by ID.",
)
async def get_workflow(workflow_id: str) -> WorkflowResponse:
    _require_workflows_api_enabled()
    session = _get_session()
    repo = WorkflowRepository(session)
    row = await repo.get_by_id(workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _row_to_response(row)


@router.put(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Update Workflow",
    description="Update a workflow definition.",
)
async def update_workflow(
    workflow_id: str,
    request: WorkflowUpdateRequest,
) -> WorkflowResponse:
    _require_workflows_api_enabled()
    user_id = get_effective_user_id()
    session = _get_session()
    repo = WorkflowRepository(session)

    if request.definition is not None:
        definition_dict = request.definition.model_dump()
        validation = DAGParser.validate(definition_dict)
        if not validation.valid:
            errors = [ValidationErrorResponse(**e.__dict__) for e in validation.errors]
            raise HTTPException(status_code=400, detail={"errors": [e.model_dump() for e in errors]})

    row = await repo.update(
        workflow_id=workflow_id,
        user_id=user_id,
        name=request.name,
        description=request.description,
        definition=request.definition.model_dump() if request.definition else None,
        input_schema=request.input_schema,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _row_to_response(row)


@router.delete(
    "/workflows/{workflow_id}",
    status_code=204,
    summary="Delete Workflow",
    description="Delete a workflow and all its related data.",
)
async def delete_workflow(workflow_id: str) -> None:
    _require_workflows_api_enabled()
    user_id = get_effective_user_id()
    session = _get_session()
    repo = WorkflowRepository(session)
    deleted = await repo.delete(workflow_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post(
    "/workflows/{workflow_id}/validate",
    response_model=ValidationResultResponse,
    summary="Validate Workflow DAG",
    description="Validate a workflow definition without saving it.",
)
async def validate_workflow(
    workflow_id: str,
    request: WorkflowValidateRequest,
) -> ValidationResultResponse:
    _require_workflows_api_enabled()
    definition_dict = request.definition.model_dump()
    result = DAGParser.validate(definition_dict)

    topology = None
    if result.valid:
        from tianshu.workflow.engine.topo_sorter import TopologicalSorter
        graph = DAGParser.parse(definition_dict)
        sorter_result = TopologicalSorter.sort(graph)
        topology = {
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "has_cycle": False,
            "entry_nodes": graph.entry_nodes,
            "exit_nodes": graph.exit_nodes,
            "parallel_groups": sorter_result.parallel_groups,
        }

    errors = [ValidationErrorResponse(**e.__dict__) for e in result.errors]
    return ValidationResultResponse(
        valid=result.valid,
        errors=errors,
        warnings=result.warnings,
        topology=topology,
    )


@router.post(
    "/workflows/{workflow_id}/copy",
    response_model=WorkflowResponse,
    status_code=201,
    summary="Copy Workflow",
    description="Copy an existing workflow as a new one.",
)
async def copy_workflow(
    workflow_id: str,
    request: WorkflowCopyRequest,
) -> WorkflowResponse:
    _require_workflows_api_enabled()
    user_id = get_effective_user_id()
    session = _get_session()
    repo = WorkflowRepository(session)

    source = await repo.get_by_id(workflow_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    import copy
    new_definition = copy.deepcopy(source.definition)
    new_id = str(uuid.uuid4())
    for node in new_definition.get("nodes", []):
        node["id"] = str(uuid.uuid4())
    for edge in new_definition.get("edges", []):
        edge["id"] = str(uuid.uuid4())

    new_name = request.name or f"{source.name} (Copy)"
    row = await repo.create(
        user_id=user_id,
        name=new_name,
        description=source.description,
        definition=new_definition,
        input_schema=source.input_schema,
    )
    return _row_to_response(row)


@router.post(
    "/workflows/{workflow_id}/execute",
    summary="Execute Workflow (SSE)",
    description="Execute a workflow and stream real-time events via SSE.",
)
async def execute_workflow(
    workflow_id: str,
    request: WorkflowExecuteRequest,
) -> StreamingResponse:
    _require_workflows_api_enabled()
    user_id = get_effective_user_id()
    session = _get_session()
    repo = WorkflowRepository(session)

    workflow = await repo.get_by_id(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    definition = workflow.definition
    inputs = request.inputs

    execution_id = str(uuid.uuid4())
    await repo.create_execution(
        workflow_id=workflow_id,
        user_id=user_id,
        inputs=inputs,
        execution_id=execution_id,
    )

    engine = WorkflowEngine()

    async def event_generator():
        try:
            async for event in engine.execute(
                workflow_id=workflow_id,
                definition=definition,
                inputs=inputs,
                user_id=user_id,
                execution_id=execution_id,
            ):
                yield event.to_sse()

            final_row = await repo.get_execution(execution_id)
            if final_row:
                if final_row.status == "pending":
                    await repo.update_execution(execution_id, "completed")
        except Exception as e:
            logger.exception("Workflow execution stream error")
            yield WorkflowEvent(
                event_type="workflow_failed",
                execution_id=execution_id,
                data={"execution_id": execution_id, "error": str(e)},
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


@router.get(
    "/workflows/{workflow_id}/executions",
    response_model=WorkflowExecutionListResponse,
    summary="List Workflow Executions",
    description="List execution history for a workflow.",
)
async def list_executions(
    workflow_id: str,
    offset: int = 0,
    limit: int = 20,
) -> WorkflowExecutionListResponse:
    _require_workflows_api_enabled()
    session = _get_session()
    repo = WorkflowRepository(session)
    rows, total = await repo.list_executions(workflow_id, offset=offset, limit=limit)
    return WorkflowExecutionListResponse(
        total=total,
        executions=[_execution_to_response(r) for r in rows],
    )


@router.get(
    "/workflows/executions/{execution_id}",
    response_model=WorkflowExecutionDetailResponse,
    summary="Get Execution Detail",
    description="Get detailed execution with all steps.",
)
async def get_execution(execution_id: str) -> WorkflowExecutionDetailResponse:
    _require_workflows_api_enabled()
    session = _get_session()
    repo = WorkflowRepository(session)
    row = await repo.get_execution(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    steps = getattr(row, "_steps", [])
    return WorkflowExecutionDetailResponse(
        id=row.id,
        workflow_id=row.workflow_id,
        status=row.status,
        inputs=row.inputs or {},
        outputs=row.outputs,
        error_message=row.error_message or "",
        started_at=row.started_at,
        completed_at=row.completed_at,
        steps=[_step_to_response(s) for s in steps],
    )


@router.post(
    "/workflows/executions/{execution_id}/cancel",
    response_model=WorkflowExecutionResponse,
    summary="Cancel Execution",
    description="Cancel a running workflow execution.",
)
async def cancel_execution(execution_id: str) -> WorkflowExecutionResponse:
    _require_workflows_api_enabled()
    session = _get_session()
    repo = WorkflowRepository(session)

    engine = WorkflowEngine()
    engine.cancel_execution(execution_id)

    row = await repo.update_execution(execution_id, "cancelled")
    if row is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return _execution_to_response(row)
