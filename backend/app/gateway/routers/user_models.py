"""CRUD API for user-defined model configurations.

Each user manages their own list of LLM providers/models via
``/api/user/models``. Rows are stored in the ``user_models`` table and
*added* to the global model list (``GET /api/models``) so the chat UI
shows them immediately, without restarting the gateway.

The factory side is wired through
:func:`tianshu.models.factory.create_chat_model`, which accepts a
pre-resolved ``model_config`` to bypass the yaml-only lookup.

Naming follows the ``agent`` package convention (lower-case
hyphenated handle, validated against a regex) so a future UI can
share input components between agents and models.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from tianshu.models.factory_user import (
    list_registered_providers,
    get_provider_spec,
)
from tianshu.persistence.user_models.model import UserModelRow
from tianshu.persistence.user_models.sql import (
    NO_UPDATE,
    UserModelRepository,
    get_api_key_cipher,
    set_value,
)
from tianshu.runtime.user_context import get_effective_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user-models"])

# Identical regex as the agents router so the UI can reuse validators.
_MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


# ---------- request/response models ----------

class UserModelResponse(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    description: str | None = None
    provider: str
    api_key_set: bool
    base_url: str | None = None
    model: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    supports_thinking: bool = False
    supports_reasoning_effort: bool = False
    context_window: int | None = None
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class UserModelListResponse(BaseModel):
    models: list[UserModelResponse]


class UserModelCreateRequest(BaseModel):
    name: str = Field(..., description="Unique per-user handle, used in the model selector")
    display_name: str | None = Field(default=None, description="Human-friendly name shown in the UI")
    description: str | None = Field(default=None, description="Optional description")
    provider: str = Field(..., description="Provider identifier (see /api/user/models/providers)")
    api_key: str | None = Field(default=None, description="Provider API key (encrypted-at-rest when configured)")
    base_url: str | None = Field(default=None, description="Provider base URL (required for custom_openai)")
    model: str = Field(..., description="Actual model identifier passed to the provider")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Free-form kwargs forwarded to the chat-model ctor")
    supports_thinking: bool = Field(default=False, description="Whether the model supports thinking mode")
    supports_reasoning_effort: bool = Field(default=False, description="Whether the model supports reasoning_effort")
    context_window: int | None = Field(default=None, gt=0, description="Total context window in tokens")
    enabled: bool = Field(default=True, description="Set false to keep the row but exclude from the selector")

    @field_validator("name")
    @classmethod
    def _name_pattern(cls, v: str) -> str:
        if not _MODEL_NAME_PATTERN.match(v):
            raise ValueError(
                "Invalid model name; must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
            )
        return v

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, v: str) -> str:
        try:
            get_provider_spec(v)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        return v

    @field_validator("base_url")
    @classmethod
    def _base_url_consistent(cls, v: str | None, info) -> str | None:
        # ``info.data`` is the partially-validated dict; provider is
        # already validated above.
        provider = info.data.get("provider") if hasattr(info, "data") else None
        if v is None and provider == "custom_openai":
            raise ValueError("provider 'custom_openai' requires a base_url")
        return v


class UserModelUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    set_api_key: str | None = Field(default=None, description="Pass a non-empty value to set the api_key, or empty string to clear")
    clear_api_key: bool = Field(default=False, description="Explicit clear flag")
    set_base_url: str | None = Field(default=None, description="Set the base_url; pass empty string + clear flag to remove")
    clear_base_url: bool = Field(default=False, description="Explicit clear flag")
    model: str | None = None
    parameters: dict[str, Any] | None = None
    supports_thinking: bool | None = None
    supports_reasoning_effort: bool | None = None
    context_window: int | None = None
    enabled: bool | None = None


class UserModelProvidersResponse(BaseModel):
    providers: list[dict[str, Any]]


# ---------- helpers ----------

def _repo() -> UserModelRepository:
    return UserModelRepository(cipher=get_api_key_cipher())


def _row_to_response(row: dict[str, Any]) -> UserModelResponse:
    return UserModelResponse(**row)


# ---------- endpoints ----------

@router.get(
    "/models/providers",
    response_model=UserModelProvidersResponse,
    summary="List supported model providers",
)
async def list_providers() -> UserModelProvidersResponse:
    """Return the registered provider identifiers + metadata for the UI."""
    return UserModelProvidersResponse(providers=list_registered_providers())


@router.get(
    "/models",
    response_model=UserModelListResponse,
    summary="List the current user's models",
)
async def list_user_models(request: Request) -> UserModelListResponse:
    user_id = get_effective_user_id()
    rows = await _repo().list_for_user(user_id)
    return UserModelListResponse(models=[_row_to_response(r) for r in rows])


@router.get(
    "/models/{name}",
    response_model=UserModelResponse,
    summary="Get one of the current user's models",
)
async def get_user_model(name: str, request: Request) -> UserModelResponse:
    user_id = get_effective_user_id()
    row = await _repo().get(user_id, name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"User model '{name}' not found")
    return _row_to_response(row)


@router.post(
    "/models",
    response_model=UserModelResponse,
    status_code=201,
    summary="Create a new user model",
)
async def create_user_model(body: UserModelCreateRequest, request: Request) -> UserModelResponse:
    user_id = get_effective_user_id()
    try:
        row = await _repo().create(
            user_id=user_id,
            name=body.name,
            display_name=body.display_name,
            description=body.description,
            provider=body.provider,
            api_key=body.api_key,
            base_url=body.base_url,
            model=body.model,
            parameters=body.parameters,
            supports_thinking=body.supports_thinking,
            supports_reasoning_effort=body.supports_reasoning_effort,
            context_window=body.context_window,
            enabled=body.enabled,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"User model '{body.name}' already exists",
        ) from None
    return _row_to_response(row)


@router.patch(
    "/models/{name}",
    response_model=UserModelResponse,
    summary="Update one of the current user's models",
)
async def update_user_model(name: str, body: UserModelUpdateRequest, request: Request) -> UserModelResponse:
    user_id = get_effective_user_id()
    # Compose the partial-update payload. ``set_api_key`` / ``set_base_url``
    # are (present, value) tuples so callers can distinguish "leave alone"
    # from "clear".
    set_api_key = NO_UPDATE
    if body.clear_api_key:
        set_api_key = set_value(None)
    elif body.set_api_key is not None and body.set_api_key != "":
        set_api_key = set_value(body.set_api_key)
    set_base_url = NO_UPDATE
    if body.clear_base_url:
        set_base_url = set_value(None)
    elif body.set_base_url is not None and body.set_base_url != "":
        set_base_url = set_value(body.set_base_url)

    row = await _repo().update(
        user_id=user_id,
        name=name,
        display_name=body.display_name,
        description=body.description,
        set_api_key=set_api_key,
        set_base_url=set_base_url,
        model=body.model,
        parameters=body.parameters,
        supports_thinking=body.supports_thinking,
        supports_reasoning_effort=body.supports_reasoning_effort,
        context_window=body.context_window,
        enabled=body.enabled,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"User model '{name}' not found")
    return _row_to_response(row)


@router.delete(
    "/models/{name}",
    status_code=204,
    summary="Delete one of the current user's models",
)
async def delete_user_model(name: str, request: Request) -> None:
    user_id = get_effective_user_id()
    ok = await _repo().delete(user_id=user_id, name=name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"User model '{name}' not found")


__all__ = ["router", "UserModelRow"]