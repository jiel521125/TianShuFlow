"""Pydantic schemas for workflow API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkflowDefinitionSchema(BaseModel):
    """Schema for a full workflow definition (nodes + edges)."""

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowCreateRequest(BaseModel):
    """Request to create a new workflow."""

    name: str = Field(..., description="Workflow name", max_length=256)
    description: str = Field(default="", description="Workflow description")
    definition: WorkflowDefinitionSchema = Field(..., description="Workflow DAG definition")
    input_schema: dict[str, Any] | None = Field(default=None, description="Input parameter schema")


class WorkflowUpdateRequest(BaseModel):
    """Request to update an existing workflow."""

    name: str | None = Field(default=None, description="Updated name")
    description: str | None = Field(default=None, description="Updated description")
    definition: WorkflowDefinitionSchema | None = Field(default=None, description="Updated DAG definition")
    input_schema: dict[str, Any] | None = Field(default=None, description="Updated input schema")


class WorkflowResponse(BaseModel):
    """Response model for a workflow."""

    id: str
    name: str
    description: str
    definition: dict[str, Any]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    is_template: bool = False
    version: int = 1
    created_at: datetime
    updated_at: datetime


class WorkflowListResponse(BaseModel):
    """Response model for workflow list."""

    total: int
    workflows: list[WorkflowResponse]


class WorkflowValidateRequest(BaseModel):
    """Request to validate a workflow definition."""

    definition: WorkflowDefinitionSchema


class ValidationErrorResponse(BaseModel):
    """Single validation error."""

    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None


class ValidationResultResponse(BaseModel):
    """Validation result for a workflow definition."""

    valid: bool
    errors: list[ValidationErrorResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    topology: dict[str, Any] | None = None


class WorkflowExecuteRequest(BaseModel):
    """Request to execute a workflow."""

    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowCopyRequest(BaseModel):
    """Request to copy a workflow."""

    name: str | None = Field(default=None, description="Name for the copied workflow")


class WorkflowExecutionResponse(BaseModel):
    """Response model for execution status."""

    id: str
    workflow_id: str
    status: str
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None = None
    error_message: str = ""
    started_at: datetime
    completed_at: datetime | None = None


class WorkflowExecutionListResponse(BaseModel):
    """Response model for execution list."""

    total: int
    executions: list[WorkflowExecutionResponse]


class WorkflowExecutionStepResponse(BaseModel):
    """Response model for an execution step."""

    id: str
    node_id: str
    status: str
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error_message: str = ""
    duration_ms: int = 0
    started_at: datetime
    completed_at: datetime | None = None


class WorkflowExecutionDetailResponse(BaseModel):
    """Response model for execution detail with steps."""

    id: str
    workflow_id: str
    status: str
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None = None
    error_message: str = ""
    started_at: datetime
    completed_at: datetime | None = None
    steps: list[WorkflowExecutionStepResponse] = Field(default_factory=list)
