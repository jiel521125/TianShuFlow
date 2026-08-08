"""User-model builder for the model factory.

When ``create_chat_model`` is asked for a model that does not exist
in the system ``AppConfig.models`` list, it consults the user's
``user_models`` rows and instantiates one of the providers registered
in :mod:`tianshu.models.user_provider_registry`.

The user row carries:

* ``name`` -- the system-wide handle used by ``create_chat_model``
* ``provider`` -- one of the registry keys
* ``api_key`` / ``base_url`` -- credentials
* ``model`` -- the actual provider-side model identifier
* ``parameters`` -- free-form kwargs forwarded to the chat-model ctor
* ``supports_thinking`` / ``supports_reasoning_effort`` /
  ``context_window`` -- mirrored onto ``ModelConfig``

Lookup order:
1. ``AppConfig.models`` (system yaml)
2. The caller-supplied ``user_id``'s ``user_models`` rows

A user row never shadows a *system* row with the same ``name`` --
this lets platform admins guarantee the availability of a baseline
model. If a user wants their own ``"gpt-4"`` they must pick a
distinct name.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.chat_models import BaseChatModel

from tianshu.config.app_config import AppConfig
from tianshu.config.model_config import ModelConfig
from tianshu.models.user_provider_registry import (
    USER_PROVIDERS,
    UserProviderSpec,
    get_provider_spec,
)
from tianshu.persistence.user_models.model import UserModelRow
from tianshu.tracing import build_tracing_callbacks

logger = logging.getLogger(__name__)


def user_row_to_model_config(row: UserModelRow) -> ModelConfig:
    """Translate a :class:`UserModelRow` into the in-memory ``ModelConfig`` shape.

    We deliberately translate into ``ModelConfig`` so the rest of the
    factory pipeline (thinking handling, fallback, _normalize_openai_base_url,
    tracing, ...) treats the user row identically to a system row. The
    only loss is the ``use`` class-path, which the factory reads once.

    Free-form kwargs (``api_key``, ``base_url``, ``parameters``) flow
    through ``ModelConfig``'s ``extra="allow"`` config so the factory
    picks them up alongside the schema-defined fields.
    """
    spec = get_provider_spec(row.provider)
    extra: dict[str, Any] = {
        "model": row.model,
    }
    if row.base_url:
        extra["base_url"] = row.base_url
    # Free-form parameters (temperature, max_tokens, extra_headers, ...)
    if row.parameters:
        for key, value in row.parameters.items():
            if value is not None:
                extra[key] = value
    # Provider-specific API key kwarg (api_key / google_api_key / ...)
    if row.api_key:
        extra[spec.api_key_kwarg] = row.api_key

    cfg = ModelConfig(
        name=row.name,
        display_name=row.display_name,
        description=row.description,
        use=spec.class_path,
        model=row.model,
        supports_thinking=row.supports_thinking,
        supports_reasoning_effort=row.supports_reasoning_effort,
        context_window=row.context_window,
    )
    # Inject extras via pydantic's ``model_fields`` setattr so we don't
    # need a custom validator. ``ModelConfig`` declares
    # ``model_config = ConfigDict(extra="allow")`` which permits this.
    for key, value in extra.items():
        setattr(cfg, key, value)
    return cfg


def is_user_model_name(app_config: AppConfig, name: str) -> bool:
    """True when ``name`` is NOT in the system yaml and may resolve to a user row."""
    return app_config.get_model_config(name) is None


async def resolve_user_model_row(user_id: str, name: str) -> UserModelRow | None:
    """Return the raw row for ``name`` (or ``None``) via the persistence layer."""
    from tianshu.persistence.user_models.sql import UserModelRepository

    repo = UserModelRepository()
    return await repo.get_row_for_factory(user_id, name)


async def build_user_model_instance(
    *,
    user_id: str,
    name: str,
    app_config: AppConfig,
    thinking_enabled: bool = False,
    attach_tracing: bool = True,
    model_overrides: dict | None = None,
) -> BaseChatModel:
    """Build a chat-model instance from a user ``user_models`` row.

    Mirrors the public surface of
    :func:`tianshu.models.factory._build_model_instance` but pulls the
    config from a database row instead of yaml. Throws
    ``ValueError`` if the row does not exist or the provider is
    unknown.
    """
    from tianshu.models.factory import _build_model_instance

    row = await resolve_user_model_row(user_id, name)
    if row is None:
        raise ValueError(
            f"Model {name!r} not found in user_models for user {user_id!r}"
        ) from None
    if not row.enabled:
        raise ValueError(f"User model {name!r} is disabled") from None

    # Inject the synthesized ModelConfig into a *temporary* AppConfig
    # so the existing factory pipeline can stay unchanged. The system
    # model list stays untouched (we copy it). ``model_copy`` does not
    # re-run validators, so the transient ``_models_by_name`` lookup
    # table has to be rebuilt explicitly.
    from tianshu.config.app_config import AppConfig

    model_config = user_row_to_model_config(row)
    transient_cfg: AppConfig = app_config.model_copy(update={"models": [model_config]})
    # ``PrivateAttr`` is not preserved across ``model_copy``; rebuild it.
    transient_cfg._models_by_name = {model_config.name: model_config}
    return _build_model_instance(
        name=name,
        thinking_enabled=thinking_enabled,
        app_config=transient_cfg,
        attach_tracing=attach_tracing,
        model_overrides=model_overrides,
    )


# Key the gateway injects into ``config["context"]``; ``_make_lead_agent`` /
# ``TianShuClient._ensure_agent`` read it via the merged runtime config. It
# maps a user-registered model name to its already-translated ``ModelConfig``
# (with the decrypted ``api_key`` baked in), mirroring the per-user MCP server
# allowlist pattern in ``tianshu.tools.mcp_filter``.
USER_MODELS_CONTEXT_KEY = "user_models"


def _model_user_ids(user_id: str) -> list[str]:
    """Order user-model lookup: the real user first, then the system ``default`` user.

    Seed rows live under ``'default'`` (the platform baseline). A real user's
    own rows — when they registered models in Settings — take precedence; rows
    the user has not overridden fall back to the ``'default'`` baseline so a
    freshly created account still sees the seeded models.
    """
    from tianshu.runtime.user_context import DEFAULT_USER_ID

    if not user_id or user_id == DEFAULT_USER_ID:
        return [DEFAULT_USER_ID]
    return [user_id, DEFAULT_USER_ID]


async def resolve_user_model_config(user_id: str, name: str) -> ModelConfig | None:
    """Resolve a single user model row, falling back to the ``default`` user.

    Returns ``None`` when neither the user nor the system baseline has an
    enabled row for ``name``. Runs in the async layer because the psycopg
    session is bound to the event loop.
    """
    from tianshu.persistence.user_models.sql import UserModelRepository

    repo = UserModelRepository()
    for uid in _model_user_ids(user_id):
        try:
            raw = await repo.get_row_for_factory(uid, name)
        except Exception:
            logger.warning(
                "Failed to load user model %r for user %s; skipping",
                name,
                uid,
                exc_info=True,
            )
            continue
        if raw is None:
            continue
        try:
            return user_row_to_model_config(raw)
        except Exception:
            logger.warning(
                "Failed to translate user model %r for user %s; skipping",
                name,
                uid,
                exc_info=True,
            )
    return None


async def resolve_user_model_configs(user_id: str) -> dict[str, ModelConfig]:
    """Resolve every enabled user-model row into ``{name: ModelConfig}``.

    Runs in the async layer (the psycopg session is bound to the event
    loop) so the synchronous agent builders can consume the result without
    awaiting. Rows with an unknown provider or missing credentials are
    skipped individually so one bad row cannot break the whole set. The
    real user's rows override the ``'default'`` baseline on name collision.
    """
    from tianshu.persistence.user_models.sql import UserModelRepository

    repo = UserModelRepository()
    configs: dict[str, ModelConfig] = {}
    for uid in _model_user_ids(user_id):
        try:
            rows = await repo.list_for_user(uid)
        except Exception:
            logger.warning(
                "Could not resolve user models for user %s; falling back to config.yaml models",
                uid,
                exc_info=True,
            )
            continue
        for row in rows:
            if not row.get("enabled", True):
                continue
            if row["name"] in configs:
                # The real user's row already won over the baseline.
                continue
            try:
                raw = await repo.get_row_for_factory(uid, row["name"])
            except Exception:
                logger.warning(
                    "Failed to load user model %r for user %s; skipping",
                    row.get("name"),
                    uid,
                    exc_info=True,
                )
                continue
            if raw is None:
                continue
            try:
                configs[raw.name] = user_row_to_model_config(raw)
            except Exception:
                logger.warning(
                    "Failed to translate user model %r for user %s; skipping",
                    row.get("name"),
                    uid,
                    exc_info=True,
                )
                continue
    return configs


def inject_user_models(config: dict[str, Any], models: dict[str, ModelConfig]) -> None:
    """Write the resolved user-model map into a run config's ``context`` section.

    ``_make_lead_agent`` and ``TianShuClient._ensure_agent`` read it via the
    merged runtime config (``_get_runtime_config``) when ``config.yaml`` has no
    row for the requested model name. An empty dict keeps the current
    config.yaml-only behaviour.
    """
    context = config.setdefault("context", {})
    if isinstance(context, dict):
        context[USER_MODELS_CONTEXT_KEY] = models


def list_registered_providers() -> list[dict[str, Any]]:
    """Return the public provider list for the settings UI."""
    return [
        {
            "id": pid,
            "class_path": spec.class_path,
            "requires_base_url": spec.requires_base_url,
            "api_key_kwarg": spec.api_key_kwarg,
            "default_base_url": spec.default_base_url,
        }
        for pid, spec in sorted(USER_PROVIDERS.items())
    ]


__all__ = [
    "UserProviderSpec",
    "USER_PROVIDERS",
    "USER_MODELS_CONTEXT_KEY",
    "build_user_model_instance",
    "get_provider_spec",
    "inject_user_models",
    "is_user_model_name",
    "list_registered_providers",
    "resolve_user_model_config",
    "resolve_user_model_configs",
    "resolve_user_model_row",
    "user_row_to_model_config",
]