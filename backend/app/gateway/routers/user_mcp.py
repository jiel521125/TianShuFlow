"""CRUD API for user-registered MCP servers.

Each user manages their own list of MCP servers via ``/api/user/mcp``.
Rows are stored in the ``user_mcp`` table and *scoped* to the caller:
every endpoint reads the effective user id from the request context
(:func:`tianshu.runtime.user_context.get_effective_user_id`) and only
touches that user's rows.

This registry is the **only** runtime MCP tool source for user sessions
-- the system-global ``extensions_config.json`` servers never enter a
user chat (see ``docs/user-mcp/architecture.md``). Every successful
write invalidates the user's MCP tool cache so the next chat run picks
up the change.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError

from tianshu.mcp.user_registry import invalidate_user_mcp_tools
from tianshu.persistence.user_mcp.sql import UserMCPServerRepository
from tianshu.runtime.user_context import get_effective_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user-mcp"])

# Identical regex as the user_models router so the UI can reuse validators.
_SERVER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_VALID_TRANSPORTS = frozenset({"stdio", "sse", "http"})


# ---------- request/response models ----------

class UserMCPServerResponse(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    description: str | None = None
    transport: str
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    env_set: bool = False
    url: str | None = None
    tool_name_prefix: bool = True
    tool_call_timeout: float | None = None
    created_at: str | None = None
    updated_at: str | None = None


class UserMCPServerListResponse(BaseModel):
    servers: list[UserMCPServerResponse]


class UserMCPServerCreateRequest(BaseModel):
    name: str = Field(..., description="Unique per-user handle, used in the tools menu")
    display_name: str | None = Field(default=None, description="Human-friendly name shown in the UI")
    description: str | None = Field(default=None, description="Optional description")
    transport: str = Field(..., description="One of: stdio, sse, http")
    command: str | None = Field(default=None, description="stdio launch command (required for stdio)")
    args: list[str] | None = Field(default=None, description="stdio launch arguments (strings)")
    env: dict[str, str] | None = Field(default=None, description="stdio environment variables (may contain secrets)")
    url: str | None = Field(default=None, description="sse/http server URL (required for sse/http)")
    tool_name_prefix: bool = Field(default=True, description="Prefix built tool names with the server name")
    tool_call_timeout: float | None = Field(default=None, gt=0, description="Per-tool-call timeout in seconds")

    @field_validator("name")
    @classmethod
    def _name_pattern(cls, v: str) -> str:
        if not _SERVER_NAME_PATTERN.match(v):
            raise ValueError(
                "Invalid server name; must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
            )
        return v

    @field_validator("transport")
    @classmethod
    def _known_transport(cls, v: str) -> str:
        if v not in _VALID_TRANSPORTS:
            raise ValueError("transport must be one of: stdio, sse, http")
        return v

    @model_validator(mode="after")
    def _transport_fields(self) -> "UserMCPServerCreateRequest":
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("transport 'stdio' requires 'command'")
            if self.url:
                raise ValueError("transport 'stdio' cannot have 'url'")
        else:
            if not self.url:
                raise ValueError(f"transport '{self.transport}' requires 'url'")
            if self.command or self.args:
                raise ValueError(f"transport '{self.transport}' cannot have 'command'/'args'")
        return self


class UserMCPServerUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    transport: str | None = None
    command: str | None = None
    args: list[str] | None = None
    set_env: dict[str, str] | None = Field(
        default=None,
        description="Replace the whole env map; pass {} to clear (secrets never round-trip through GET)",
    )
    clear_env: bool = Field(default=False, description="Explicit env clear flag")
    url: str | None = None
    tool_name_prefix: bool | None = None
    tool_call_timeout: float | None = Field(default=None, gt=0)

    @field_validator("transport")
    @classmethod
    def _known_transport(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_TRANSPORTS:
            raise ValueError("transport must be one of: stdio, sse, http")
        return v

    @model_validator(mode="after")
    def _env_flags_exclusive(self) -> "UserMCPServerUpdateRequest":
        if self.set_env is not None and self.clear_env:
            raise ValueError("set_env and clear_env are mutually exclusive")
        return self


# ---------- helpers ----------

def _repo() -> UserMCPServerRepository:
    return UserMCPServerRepository()


def _row_to_response(row: dict[str, Any]) -> UserMCPServerResponse:
    return UserMCPServerResponse(**row)


# ---------- endpoints ----------

@router.get(
    "/mcp",
    response_model=UserMCPServerListResponse,
    summary="List the current user's MCP servers",
)
async def list_user_mcp_servers(request: Request) -> UserMCPServerListResponse:
    user_id = get_effective_user_id()
    rows = await _repo().list_for_user(user_id)
    return UserMCPServerListResponse(servers=[_row_to_response(r) for r in rows])


@router.get(
    "/mcp/{name}",
    response_model=UserMCPServerResponse,
    summary="Get one of the current user's MCP servers",
)
async def get_user_mcp_server(name: str, request: Request) -> UserMCPServerResponse:
    user_id = get_effective_user_id()
    row = await _repo().get(user_id, name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    return _row_to_response(row)


@router.post(
    "/mcp",
    response_model=UserMCPServerResponse,
    status_code=201,
    summary="Register a new MCP server for the current user",
)
async def create_user_mcp_server(
    body: UserMCPServerCreateRequest, request: Request
) -> UserMCPServerResponse:
    user_id = get_effective_user_id()
    try:
        row = await _repo().create(
            user_id=user_id,
            name=body.name,
            display_name=body.display_name,
            description=body.description,
            transport=body.transport,
            command=body.command,
            args=body.args,
            env=body.env,
            url=body.url,
            tool_name_prefix=body.tool_name_prefix,
            tool_call_timeout=body.tool_call_timeout,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"MCP server '{body.name}' already exists",
        ) from None
    await invalidate_user_mcp_tools(user_id)
    return _row_to_response(row)


@router.patch(
    "/mcp/{name}",
    response_model=UserMCPServerResponse,
    summary="Update one of the current user's MCP servers",
)
async def update_user_mcp_server(
    name: str, body: UserMCPServerUpdateRequest, request: Request
) -> UserMCPServerResponse:
    user_id = get_effective_user_id()
    # Present-value semantics: only fields explicitly sent are updated.
    # ``env`` is the exception -- the GET response masks values to ``***``,
    # so round-tripping it would overwrite real secrets with the mask. It is
    # updated only through the explicit set_env / clear_env flags.
    fields: dict[str, Any] = {}
    for key in ("display_name", "description", "transport", "command", "args", "url", "tool_name_prefix", "tool_call_timeout"):
        if key in body.model_fields_set:
            fields[key] = getattr(body, key)
    if body.clear_env:
        fields["env"] = None
    elif body.set_env is not None:
        fields["env"] = body.set_env

    # Cross-field validation against the *merged* state when transport or its
    # siblings change, so a PATCH cannot leave the row in an invalid shape.
    existing = await _repo().get(user_id, name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    merged = {**existing, **fields}
    _validate_merged_transport(merged)

    try:
        row = await _repo().update(user_id=user_id, name=name, fields=fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if row is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    await invalidate_user_mcp_tools(user_id)
    return _row_to_response(row)


@router.delete(
    "/mcp/{name}",
    status_code=204,
    summary="Delete one of the current user's MCP servers",
)
async def delete_user_mcp_server(name: str, request: Request) -> None:
    user_id = get_effective_user_id()
    ok = await _repo().delete(user_id=user_id, name=name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    await invalidate_user_mcp_tools(user_id)


def _validate_merged_transport(merged: dict[str, Any]) -> None:
    """Reject a merged (existing + patch) server shape that violates transport rules."""
    transport = merged.get("transport") or "stdio"
    if transport == "stdio":
        if not merged.get("command"):
            raise HTTPException(status_code=400, detail="transport 'stdio' requires 'command'")
    else:
        if not merged.get("url"):
            raise HTTPException(
                status_code=400, detail=f"transport '{transport}' requires 'url'"
            )


__all__ = ["router"]
