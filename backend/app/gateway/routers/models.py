import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.gateway.authz import (
    _AuthorizationUnavailable,
    _is_internal_caller,
    resolve_model_authorization,
)
from app.gateway.deps import get_config, get_optional_user_from_request
from tianshu.authz.provider import AuthzDecision, AuthzRequest
from tianshu.config.app_config import AppConfig
from tianshu.config.model_config import ModelConfig
from tianshu.models.user_provider_registry import get_provider_spec
from tianshu.persistence.user_models.sql import UserModelRepository
from tianshu.runtime.user_context import get_effective_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["models"])


async def _list_user_models_for_caller(request: Request) -> list[ModelConfig]:
    """Return ``ModelConfig``-shaped rows for the caller's ``user_models``.

    Translates each :class:`UserModelRow` into a ``ModelConfig`` so
    the downstream rendering loop can treat user rows identically to
    system rows. The api_key is *not* loaded here -- the factory
    layer is the only consumer that needs the decrypted value, and
    only at the moment a chat model is built.
    """
    user_id = get_effective_user_id()
    if not user_id:
        return []
    repo = UserModelRepository()
    rows = await repo.list_for_user(user_id)
    configs: list[ModelConfig] = []
    for row in rows:
        if not row.get("enabled", True):
            continue
        try:
            spec = get_provider_spec(row["provider"])
        except KeyError:
            logger.warning("Skipping user model %r: unknown provider %r", row.get("name"), row.get("provider"))
            continue
        extras: dict[str, object] = {"model": row["model"]}
        if row.get("base_url"):
            extras["base_url"] = row["base_url"]
        for key, value in (row.get("parameters") or {}).items():
            if value is not None:
                extras[key] = value
        # The api_key column is redacted on read; we still need to
        # forward the underlying key into the factory. The repo
        # returns ``api_key_set`` (boolean) for the public surface, so
        # the factory has to fetch the row again with decryption when
        # it needs the real value. For the *list* endpoint we skip the
        # secret because it would never be useful to the UI.
        cfg = ModelConfig(
            name=row["name"],
            display_name=row.get("display_name"),
            description=row.get("description"),
            use=spec.class_path,
            model=row["model"],
            supports_thinking=row.get("supports_thinking", False),
            supports_reasoning_effort=row.get("supports_reasoning_effort", False),
            context_window=row.get("context_window"),
        )
        for key, value in extras.items():
            setattr(cfg, key, value)
        configs.append(cfg)
    return configs


class ModelResponse(BaseModel):
    """Response model for model information."""

    name: str = Field(..., description="Unique identifier for the model")
    model: str = Field(..., description="Actual provider model identifier")
    display_name: str | None = Field(None, description="Human-readable name")
    description: str | None = Field(None, description="Model description")
    supports_thinking: bool = Field(default=False, description="Whether model supports thinking mode")
    supports_reasoning_effort: bool = Field(default=False, description="Whether model supports reasoning effort")


class TokenUsageResponse(BaseModel):
    """Token usage display configuration."""

    enabled: bool = Field(default=False, description="Whether token usage display is enabled")


class ModelsListResponse(BaseModel):
    """Response model for listing all models."""

    models: list[ModelResponse]
    token_usage: TokenUsageResponse


@router.get(
    "/models",
    response_model=ModelsListResponse,
    summary="List All Models",
    description="Retrieve a list of all available AI models configured in the system.",
)
async def list_models(
    request: Request,
    config: AppConfig = Depends(get_config),
) -> ModelsListResponse:
    """List all available models from configuration.

    Returns model information suitable for frontend display,
    excluding sensitive fields like API keys and internal configuration.

    When ``authorization.enabled`` is true, only models the caller's role may
    ``list`` are returned (filtered via ``provider.filter_resources``). A
    provider error yields an empty list (fail-closed) or all models (fail-open).

    Returns:
        A list of all configured models with their metadata and token usage display settings.

    Example Response:
        ```json
        {
            "models": [
                {
                    "name": "gpt-4",
                    "model": "gpt-4",
                    "display_name": "GPT-4",
                    "description": "OpenAI GPT-4 model",
                    "supports_thinking": false,
                    "supports_reasoning_effort": false
                },
                {
                    "name": "claude-3-opus",
                    "model": "claude-3-opus",
                    "display_name": "Claude 3 Opus",
                    "description": "Anthropic Claude 3 Opus model",
                    "supports_thinking": true,
                    "supports_reasoning_effort": false
                }
            ],
            "token_usage": {
                "enabled": true
            }
        }
        ```
    """
    visible_models = config.models
    fail_closed = config.authorization.fail_closed

    user = await get_optional_user_from_request(request)
    # Merge in user-defined models so the dropdown shows both system
    # and per-user configurations. User rows are added last so they
    # never shadow a system row with the same name -- admins can
    # always guarantee a baseline model is available.
    user_models = await _list_user_models_for_caller(request)
    user_model_names = {m.name for m in user_models}
    visible_models = [*visible_models, *user_models]

    if user is not None:
        try:
            provider, principal = resolve_model_authorization(user, is_internal=_is_internal_caller(request, user))
        except _AuthorizationUnavailable as exc:
            if exc.fail_closed:
                visible_models = []
        else:
            if provider is not None and principal is not None:
                try:
                    allowed_names = provider.filter_resources(principal, "model", [m.name for m in config.models])
                    if not isinstance(allowed_names, list) or any(not isinstance(n, str) for n in allowed_names):
                        raise TypeError("AuthorizationProvider.filter_resources must return list[str]")
                    allowed_set = set(allowed_names)
                    # Re-filter from the merged list (system + user rows)
                    # so user-defined models survive authz as long as
                    # the role can ``list`` them. Same-shape behavior as
                    # before -- the authz layer only knows about system
                    # model names.
                    visible_models = [m for m in visible_models if m.name in allowed_set or m.name in user_model_names]
                except Exception:
                    logger.warning("Authorization provider failed while filtering models", exc_info=True)
                    visible_models = [] if fail_closed else config.models

    models = [
        ModelResponse(
            name=model.name,
            model=model.model,
            display_name=model.display_name,
            description=model.description,
            supports_thinking=model.supports_thinking,
            supports_reasoning_effort=model.supports_reasoning_effort,
        )
        for model in visible_models
    ]
    return ModelsListResponse(
        models=models,
        token_usage=TokenUsageResponse(enabled=config.token_usage.enabled),
    )


@router.get(
    "/models/{model_name}",
    response_model=ModelResponse,
    summary="Get Model Details",
    description="Retrieve detailed information about a specific AI model by its name.",
)
async def get_model(
    model_name: str,
    request: Request,
    config: AppConfig = Depends(get_config),
) -> ModelResponse:
    """Get a specific model by name.

    Args:
        model_name: The unique name of the model to retrieve.

    Returns:
        Model information if found.

    Raises:
        HTTPException: 404 if model not found; 403 if the caller's role may not
        ``use`` the model (only when ``authorization.enabled`` is true). A
        provider resolution error yields 403 (fail-closed) or allows the request
        (fail-open), mirroring ``list_models``'s provider-error semantics.

    Example Response:
        ```json
        {
            "name": "gpt-4",
            "display_name": "GPT-4",
            "description": "OpenAI GPT-4 model",
            "supports_thinking": false
        }
        ```
    """
    model = config.get_model_config(model_name)
    if model is None:
        # Fall back to the caller's user_models rows so a user-defined
        # model can be inspected via GET /api/models/{name} just like a
        # system model. Returns 404 if neither path knows ``model_name``.
        user_models = await _list_user_models_for_caller(request)
        user_model = next((m for m in user_models if m.name == model_name), None)
        if user_model is None:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
        return ModelResponse(
            name=user_model.name,
            model=user_model.model,
            display_name=user_model.display_name,
            description=user_model.description,
            supports_thinking=user_model.supports_thinking,
            supports_reasoning_effort=user_model.supports_reasoning_effort,
        )

    # Phase 3: enforce model:use authorization (deny → 403, not 404, since the
    # model exists but the role lacks permission to use it).
    fail_closed = config.authorization.fail_closed
    user = await get_optional_user_from_request(request)
    if user is not None:
        try:
            provider, principal = resolve_model_authorization(user, is_internal=_is_internal_caller(request, user))
        except _AuthorizationUnavailable:
            if fail_closed:
                raise HTTPException(status_code=403, detail=f"Model '{model_name}' is not available for your role")
        else:
            if provider is not None and principal is not None:
                try:
                    decision = provider.authorize(AuthzRequest(principal=principal, resource="model", action="use", target=model_name))
                    if not isinstance(decision, AuthzDecision):
                        raise TypeError("AuthorizationProvider.authorize must return AuthzDecision")
                    allowed = decision.allow
                except Exception:
                    logger.warning(
                        "Authorization provider failed while checking model:use for %s",
                        model_name,
                        exc_info=True,
                    )
                    allowed = not fail_closed
                if not allowed:
                    raise HTTPException(status_code=403, detail=f"Model '{model_name}' is not available for your role")

    return ModelResponse(
        name=model.name,
        model=model.model,
        display_name=model.display_name,
        description=model.description,
        supports_thinking=model.supports_thinking,
        supports_reasoning_effort=model.supports_reasoning_effort,
    )
