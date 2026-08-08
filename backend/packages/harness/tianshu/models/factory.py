import logging

from langchain.chat_models import BaseChatModel
from langchain_openai.chat_models.base import BaseChatOpenAI

from tianshu.config import get_app_config
from tianshu.config.app_config import AppConfig
from tianshu.config.model_config import ModelConfig
from tianshu.reflection import resolve_class
from tianshu.tracing import build_tracing_callbacks

logger = logging.getLogger(__name__)


def _deep_merge_dicts(base: dict | None, override: dict) -> dict:
    """Recursively merge two dictionaries without mutating the inputs."""
    merged = dict(base or {})
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _vllm_disable_chat_template_kwargs(chat_template_kwargs: dict) -> dict:
    """Build the disable payload for vLLM/Qwen chat template kwargs."""
    disable_kwargs: dict[str, bool] = {}
    if "thinking" in chat_template_kwargs:
        disable_kwargs["thinking"] = False
    if "enable_thinking" in chat_template_kwargs:
        disable_kwargs["enable_thinking"] = False
    return disable_kwargs


def _declares_api_base(model_class: type) -> bool:
    """Whether *model_class* declares ``api_base`` as its own constructor field.

    ``langchain_deepseek:ChatDeepSeek`` (and therefore ``PatchedChatDeepSeek``) does, so for it
    ``api_base`` is the canonical endpoint key and must be passed through untouched. Every other
    ``BaseChatOpenAI`` subclass inherits only ``openai_api_base`` (alias ``base_url``).
    """
    return "api_base" in getattr(model_class, "model_fields", {})


def _normalize_openai_base_url(model_class: type, model_settings_from_config: dict) -> None:
    """Map the common ``api_base`` alias to ``base_url`` for OpenAI-compatible clients.

    ``BaseChatOpenAI`` subclasses accept the OpenAI endpoint override as ``base_url`` (with
    ``openai_api_base`` as a legacy alias). Several providers in ``config.example.yaml`` use
    ``api_base`` for *other* model classes, so users frequently copy ``api_base`` onto such a model
    by mistake. Because ``ModelConfig`` is ``extra="allow"``, the bad key is not caught at
    config-load time — it is forwarded to the constructor, which does not reject it but transfers it
    into ``model_kwargs``; that is then spread into every ``Completions.create()`` call and rejected
    by the OpenAI SDK at *request* time with an opaque ``unexpected keyword argument 'api_base'``
    error (and the endpoint override is silently dropped). Rename it here so the model works as the
    user intended.

    Gated on ``issubclass(model_class, BaseChatOpenAI)`` rather than a class-path allowlist, so any
    OpenAI-compatible subclass is covered automatically — the divert-and-crash behaviour is a
    property of the base class, not of the two paths that used to be listed. Classes that declare
    ``api_base`` themselves are skipped: there the key is canonical, not a typo.
    """
    if not issubclass(model_class, BaseChatOpenAI) or _declares_api_base(model_class):
        return
    if "api_base" not in model_settings_from_config:
        return
    if "base_url" in model_settings_from_config or "openai_api_base" in model_settings_from_config:
        # Canonical key already present; drop the alias to avoid a duplicate-intent kwarg.
        model_settings_from_config.pop("api_base", None)
        logger.warning("Model config sets both an endpoint key (base_url/openai_api_base) and 'api_base'; using the former and ignoring 'api_base'.")
        return
    model_settings_from_config["base_url"] = model_settings_from_config.pop("api_base")
    logger.debug("Normalized model config key 'api_base' -> 'base_url' for OpenAI-compatible client.")


def _warn_unknown_model_settings(model_class, model_name: str, model_settings_from_config: dict) -> None:
    """Warn about config keys the OpenAI client will silently divert into ``model_kwargs``.

    ``ModelConfig`` is ``extra="allow"``, so a typo'd key (e.g. ``maxx_tokens``) is not caught at
    config-load time. LangChain's OpenAI client does not reject an unknown constructor kwarg — it
    emits a ``UserWarning`` and transfers the key into ``model_kwargs``, which is then spread into
    every ``Completions.create()`` call and rejected by the OpenAI SDK at *request* time with an
    opaque ``unexpected keyword argument`` error that is very hard to trace back to a config typo.

    This turns that latent failure into an explicit, actionable log line at model-build time. It is
    **scoped to the OpenAI-compatible family** — that is where the ``model_kwargs``
    divert-and-crash behavior occurs and where the known field/alias set is accurate. The family is
    ``issubclass(model_class, BaseChatOpenAI)``: the divert is implemented in that base class, so
    every subclass inherits it. Other providers (e.g. ``ChatAnthropic``) route extra kwargs
    differently and would false-positive against this allow-list, so they are intentionally left
    alone. Best-effort and non-fatal: it only fires when the class exposes a pydantic
    ``model_fields`` schema, treats both field names and their aliases as valid, and allow-lists the
    standard passthrough kwargs the factory injects and the OpenAI client accepts.
    """
    if not issubclass(model_class, BaseChatOpenAI):
        return
    known = getattr(model_class, "model_fields", None)
    if not known:
        return
    valid_names = set(known.keys())
    for field in known.values():
        alias = getattr(field, "alias", None)
        if alias:
            valid_names.add(alias)
    # Standard kwargs the factory injects or the OpenAI client accepts beyond declared fields.
    valid_names |= {
        "model",
        "model_kwargs",
        "extra_body",
        "default_headers",
        "default_query",
        "stream_usage",
        "stream_chunk_timeout",
        "reasoning_effort",
    }
    unknown = sorted(k for k in model_settings_from_config if k not in valid_names)
    if unknown:
        logger.warning(
            "Model '%s' (%s): config key(s) %s are not recognized parameters of the model class and will be forwarded as-is; this may raise at request time. Check for typos (e.g. 'maxx_tokens' -> 'max_tokens').",
            model_name,
            getattr(model_class, "__name__", "?"),
            unknown,
        )


# Default chunk-gap budget for OpenAI-compatible streaming responses.
#
# langchain-openai raises ``StreamChunkTimeoutError`` after this many seconds
# without receiving a chunk. Its own default is 120s, which is too aggressive for
# reasoning models (DeepSeek-R1, Doubao-thinking, GPT-5) whose first chunk can
# legitimately take 90~150s. We default to 240s so the streaming layer rarely
# trips on long thinking pauses; the LLMErrorHandlingMiddleware still retries
# (budget=2) if a real stall happens. Users can override per-model in config.yaml.
_DEFAULT_STREAM_CHUNK_TIMEOUT_SECONDS: float = 240.0


def _apply_stream_chunk_timeout_default(model_class: type, model_settings_from_config: dict) -> None:
    """Inject a generous ``stream_chunk_timeout`` for OpenAI-compatible clients.

    ``stream_chunk_timeout`` is a field of langchain-openai's ``BaseChatOpenAI``, so
    it is accepted by ``ChatOpenAI`` and by every TianShu provider that subclasses
    it: ``PatchedChatOpenAI`` plus the self-hosted / reasoning adapters
    ``VllmChatModel``, ``MindIEChatModel``, ``PatchedChatDeepSeek``,
    ``PatchedChatMiMo``, ``PatchedChatStepFun`` and ``PatchedChatMiniMax``. We gate on
    ``issubclass(model_class, BaseChatOpenAI)`` rather than an explicit class-path
    allowlist so any OpenAI-compatible subclass inherits the default (and honors an
    explicit override) automatically. Issue #3189 was reported against ``mimo-v2.5``
    (``PatchedChatMiMo``); the original fix (#3195) matched only ``ChatOpenAI`` /
    ``PatchedChatOpenAI``, so those subclasses kept langchain-openai's aggressive
    built-in chunk-gap timeout and — worse — silently discarded a user's explicit
    ``stream_chunk_timeout``.

    Behaviour:

    * ``BaseChatOpenAI`` subclass: an explicit value in ``config.yaml`` is preserved.
      An explicit ``null`` is dropped upstream by ``model_dump(exclude_none=True)``
      and therefore treated as "unset", so the default is injected.
    * Any other client (e.g. ``ChatAnthropic``): drop the key so it is never
      forwarded to a constructor that does not declare it. The kwarg is not a
      declared field of these clients: depending on the client it is either
      silently dropped (``ChatAnthropic`` declares ``extra="ignore"``) or, for
      other OpenAI-style clients, diverted into ``model_kwargs`` and rejected
      at request time. Either way the user's intent is lost, so we drop it
      proactively instead.
    """
    if not issubclass(model_class, BaseChatOpenAI):
        model_settings_from_config.pop("stream_chunk_timeout", None)
        return
    if "stream_chunk_timeout" in model_settings_from_config:
        return
    model_settings_from_config["stream_chunk_timeout"] = _DEFAULT_STREAM_CHUNK_TIMEOUT_SECONDS


def _build_model_instance(
    name: str,
    *,
    thinking_enabled: bool = False,
    app_config: AppConfig | None = None,
    attach_tracing: bool = True,
    model_overrides: dict | None = None,
    **kwargs,
) -> BaseChatModel:
    """Build a single ``BaseChatModel`` instance from config.

    Extracted from :func:`create_chat_model` so fallback chain construction can
    build N independent model instances without duplicating the 120-line config
    normalization logic. No fallback wrapping happens here.
    """
    config = app_config or get_app_config()
    model_config = config.get_model_config(name)
    if model_config is None:
        raise ValueError(f"Model {name} not found in config") from None
    model_class = resolve_class(model_config.use, BaseChatModel)
    model_settings_from_config = model_config.model_dump(
        exclude_none=True,
        exclude={
            "use",
            "name",
            "display_name",
            "description",
            "supports_thinking",
            "supports_reasoning_effort",
            "when_thinking_enabled",
            "when_thinking_disabled",
            "thinking",
            "supports_vision",
            "context_window",
            "pricing",
        },
    )
    if model_overrides:
        model_settings_from_config.update({key: value for key, value in model_overrides.items() if value is not None})
    has_thinking_settings = (model_config.when_thinking_enabled is not None) or (model_config.thinking is not None)
    effective_wte: dict = dict(model_config.when_thinking_enabled) if model_config.when_thinking_enabled else {}
    if model_config.thinking is not None:
        merged_thinking = {**(effective_wte.get("thinking") or {}), **model_config.thinking}
        effective_wte = {**effective_wte, "thinking": merged_thinking}
    if thinking_enabled and has_thinking_settings:
        if not model_config.supports_thinking:
            raise ValueError(f"Model {name} does not support thinking. Set `supports_thinking` to true in the `config.yaml` to enable thinking.") from None
        if effective_wte:
            model_settings_from_config.update(effective_wte)
    if not thinking_enabled:
        if model_config.when_thinking_disabled is not None:
            model_settings_from_config.update(model_config.when_thinking_disabled)
        elif has_thinking_settings and effective_wte.get("extra_body", {}).get("thinking", {}).get("type"):
            model_settings_from_config["extra_body"] = _deep_merge_dicts(
                model_settings_from_config.get("extra_body"),
                {"thinking": {"type": "disabled"}},
            )
            model_settings_from_config["reasoning_effort"] = "minimal"
        elif has_thinking_settings and (disable_chat_template_kwargs := _vllm_disable_chat_template_kwargs(effective_wte.get("extra_body", {}).get("chat_template_kwargs") or {})):
            model_settings_from_config["extra_body"] = _deep_merge_dicts(
                model_settings_from_config.get("extra_body"),
                {"chat_template_kwargs": disable_chat_template_kwargs},
            )
        elif has_thinking_settings and effective_wte.get("thinking", {}).get("type"):
            model_settings_from_config["thinking"] = {"type": "disabled"}
    if not model_config.supports_reasoning_effort:
        kwargs.pop("reasoning_effort", None)
        model_settings_from_config.pop("reasoning_effort", None)

    _normalize_openai_base_url(model_class, model_settings_from_config)
    _apply_stream_chunk_timeout_default(model_class, model_settings_from_config)

    from tianshu.models.openai_codex_provider import CodexChatModel

    if issubclass(model_class, CodexChatModel):
        model_settings_from_config.pop("max_tokens", None)
        explicit_effort = kwargs.pop("reasoning_effort", None)
        if not thinking_enabled:
            model_settings_from_config["reasoning_effort"] = "none"
        elif explicit_effort and explicit_effort in ("low", "medium", "high", "xhigh"):
            model_settings_from_config["reasoning_effort"] = explicit_effort
        elif "reasoning_effort" not in model_settings_from_config:
            model_settings_from_config["reasoning_effort"] = "medium"

    if getattr(model_class, "__name__", "") == "MindIEChatModel":
        model_settings_from_config["max_retries"] = model_settings_from_config.get("max_retries", 1)

    if "stream_usage" not in model_settings_from_config and "stream_usage" not in kwargs:
        if "stream_usage" in getattr(model_class, "model_fields", {}):
            model_settings_from_config["stream_usage"] = True

    _warn_unknown_model_settings(model_class, name, model_settings_from_config)

    model_instance = model_class(**kwargs, **model_settings_from_config)

    if attach_tracing:
        callbacks = build_tracing_callbacks()
        if callbacks:
            existing_callbacks = model_instance.callbacks or []
            model_instance.callbacks = [*existing_callbacks, *callbacks]
            logger.debug(f"Tracing attached to model '{name}' with providers={len(callbacks)}")
    return model_instance


def _build_fallback_chain(
    *,
    primary_name: str | None,
    thinking_enabled: bool,
    app_config: AppConfig,
    attach_tracing: bool,
    model_overrides: dict | None = None,
) -> list[BaseChatModel]:
    """Build ordered fallback model instances from config.

    Returns an empty list when fallback is disabled, only one model is
    configured, or all fallback candidates fail to build (defensive — a broken
    fallback config must not crash agent construction).
    """
    cfg = app_config.model_fallback
    if not cfg.enabled:
        return []
    resolved_primary = primary_name or (app_config.models[0].name if app_config.models else None)
    if cfg.fallback_chain:
        candidates = list(cfg.fallback_chain)
    else:
        candidates = [m.name for m in app_config.models]
    candidates = [n for n in candidates if n != resolved_primary]
    seen: set[str] = set()
    candidates = [n for n in candidates if not (n in seen or seen.add(n))]
    built: list[BaseChatModel] = []
    for name in candidates:
        try:
            built.append(_build_model_instance(
                name=name,
                thinking_enabled=thinking_enabled,
                app_config=app_config,
                attach_tracing=attach_tracing,
                model_overrides=model_overrides,
            ))
        except Exception:
            logger.warning("Failed to build fallback model %r; skipping from fallback chain", name, exc_info=True)
    return built


def create_chat_model(
    name: str | None = None,
    thinking_enabled: bool = False,
    *,
    app_config: AppConfig | None = None,
    attach_tracing: bool = True,
    model_overrides: dict | None = None,
    with_fallbacks: bool = False,
    model_config: ModelConfig | None = None,
    **kwargs,
) -> BaseChatModel:
    """Create a chat model instance from the config.

    Args:
        name: The name of the model to create. If None, the first model in the config will be used.
        thinking_enabled: Enable the model's extended-thinking mode when supported.
        app_config: Explicit application config; falls back to the cached global if omitted.
        model_overrides: Optional per-caller sampling overrides (e.g. a custom
            agent's ``temperature`` / ``max_tokens``) layered on top of the
            model profile. ``None`` values are ignored so an unset override
            never clobbers a profile value. Applied before the thinking / Codex
            transforms so provider-specific normalization (e.g. Codex dropping
            ``max_tokens``) still governs an overridden value.
        attach_tracing: When True (default), attach tracing callbacks (Langfuse,
            LangSmith) directly to the model instance. Standalone callers — anything
            that invokes the model outside a LangGraph run that already wires tracing
            at the invocation root (``MemoryUpdater``, ad-hoc utilities, etc.) — keep
            this default so the model-level callback still produces traces. Callers
            that already attach tracing at the graph root (``make_lead_agent``, the
            in-graph ``TitleMiddleware``) MUST pass ``attach_tracing=False``; otherwise
            the same LLM call emits duplicate spans (one rooted at the graph, one at
            the model) and ``session_id`` / ``user_id`` metadata never reach the trace
            because the model becomes a nested observation whose ``langfuse_*`` keys
            get stripped.
        with_fallbacks: When True, wrap the primary model with
            ``with_fallbacks()`` so fallback-eligible exceptions (quota, rate
            limit, transient) automatically retry on alternative models. Only
            use this for non-agent callers (``oneshot_llm``, ``security_scanner``,
            etc.) that invoke the model via ``.ainvoke()`` / ``.invoke()``. Agent
            callers must keep ``with_fallbacks=False`` (the default) because
            ``create_agent`` requires a ``BaseChatModel``, not a
            ``RunnableWithFallbacks``. Agent-path fallback is handled by
            ``TianShuModelFallbackMiddleware`` instead.

    Returns:
        A chat model instance (``BaseChatModel`` by default, or
        ``RunnableWithFallbacks`` when ``with_fallbacks=True`` and multiple
        models are configured).
    """
    config = app_config or get_app_config()
    if name is None and model_config is None:
        name = config.models[0].name
    if model_config is not None:
        # Caller has already resolved a ``ModelConfig`` (typically a
        # user-registered model that lives in the ``user_models`` table
        # rather than ``config.yaml``). Inject it into a transient
        # AppConfig so ``_build_model_instance`` keeps its single
        # code path. ``_models_by_name`` uses ``setdefault``-like
        # semantics so a system row with the same name still wins.
        cfg_with_user = config.model_copy(update={"models": [*config.models, model_config]})
        merged_index = {m.name: m for m in config.models}
        # System rows first so a same-name user row never shadows
        # platform-admin baseline models.
        if model_config.name not in merged_index:
            merged_index[model_config.name] = model_config
        cfg_with_user._models_by_name = merged_index
        primary = _build_model_instance(
            name=model_config.name,
            thinking_enabled=thinking_enabled,
            app_config=cfg_with_user,
            attach_tracing=attach_tracing,
            model_overrides=model_overrides,
            **kwargs,
        )
    else:
        primary = _build_model_instance(
            name=name,
            thinking_enabled=thinking_enabled,
            app_config=config,
            attach_tracing=attach_tracing,
            model_overrides=model_overrides,
            **kwargs,
        )
    if not with_fallbacks:
        return primary
    fallbacks = _build_fallback_chain(
        primary_name=name,
        thinking_enabled=thinking_enabled,
        app_config=config,
        attach_tracing=attach_tracing,
        model_overrides=model_overrides,
    )
    if not fallbacks:
        return primary

    # LangChain's with_fallbacks: when the primary model raises an exception
    # in exceptions_to_handle, it automatically tries each fallback in order.
    # We capture all exceptions (Exception) so quota/rate-limit/transient
    # errors all trigger fallback. Non-eligible errors (e.g. auth) will also
    # fallback, but the fallback model will likely fail with the same error
    # class — the caller (e.g. input_polish) handles the final exception.
    import openai

    _fallback_exceptions = (
        openai.RateLimitError,
        openai.APIStatusError,  # covers 5xx
        openai.APITimeoutError,
        openai.APIConnectionError,
        Exception,  # catch-all: ensures quota/billing errors (which may be
                     # APIStatusError subclasses) always trigger fallback
    )
    return primary.with_fallbacks(
        fallbacks,
        exceptions_to_handle=_fallback_exceptions,
    )
