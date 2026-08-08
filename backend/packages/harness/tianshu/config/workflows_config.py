"""Configuration for the workflow orchestration API."""

from pydantic import BaseModel, Field


class WorkflowsApiConfig(BaseModel):
    """Configuration for workflow management routes."""

    enabled: bool = Field(
        default=True,
        description="Whether to expose the workflow management API over HTTP.",
    )


class WorkflowEngineConfig(BaseModel):
    """Configuration for the workflow execution engine."""

    max_parallel_nodes: int = Field(
        default=10,
        description="Maximum number of nodes that can execute in parallel.",
    )
    node_timeout: int = Field(
        default=300,
        description="Default timeout for node execution in seconds.",
    )
    max_retries: int = Field(
        default=0,
        description="Maximum number of retries for failed nodes.",
    )


_workflows_api_config: WorkflowsApiConfig = WorkflowsApiConfig()
_engine_config: WorkflowEngineConfig = WorkflowEngineConfig()


def get_workflows_api_config() -> WorkflowsApiConfig:
    return _workflows_api_config


def set_workflows_api_config(config: WorkflowsApiConfig) -> None:
    global _workflows_api_config
    _workflows_api_config = config


def get_engine_config() -> WorkflowEngineConfig:
    return _engine_config


def load_workflows_config_from_dict(config_dict: dict) -> None:
    global _workflows_api_config, _engine_config
    api_dict = config_dict.get("api", {})
    if api_dict:
        _workflows_api_config = WorkflowsApiConfig(**api_dict)
    engine_dict = config_dict.get("engine", {})
    if engine_dict:
        _engine_config = WorkflowEngineConfig(**engine_dict)
